# tasks.py

from invoke import task
import subprocess
import os
import signal
import sys
from pathlib import Path
import yaml
import threading
from fabric import Connection, ThreadingGroup

# Define the ports and peers
PORTS = [5000, 5001, 5002, 5003]
IP = "127.0.0.1"

# Dictionary to store process PIDs
processes = {}

# Define node connection details
nodes = [
    {"host": "c220g2-011121.wisc.cloudlab.us", "port": 25611},
    {"host": "c220g2-011121.wisc.cloudlab.us", "port": 25612},
    {"host": "c220g2-011121.wisc.cloudlab.us", "port": 25613},
    {"host": "c220g2-011121.wisc.cloudlab.us", "port": 25614},
    {"host": "c220g2-011121.wisc.cloudlab.us", "port": 25615},
]

# SSH username
username = "PeterYao"

@task
def start_remote(c):
    """
    Starts instances of the leader_election binary on remote nodes as specified in the config file.
    Logs are stored in the logs/ directory of each respective node.
    """
    config_path = "../configs/remote.yaml"
    remote_config_path = "configs/remote.yaml"

    # Ensure the binary path is defined
    binary_path = "bazel-bin/leader_election"

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    replica_ips = config["replica"]["ips"]
    n_replicas = len(replica_ips)
    print("Number of replicas: ", n_replicas)
    
    for replica_id, node in enumerate(nodes):
        replica_ip = node["host"]
        replica_port = node["port"]
        print(f"clearing away logs and running processes replica {replica_id} on remote node {replica_ip} with port {replica_port}")

            # Establish connection to the remote node
        conn = Connection(host=replica_ip, user=username, port=node["port"])
        
        # conn.sudo("killall leader_election", warn=True)
        conn.run("mkdir -p frugal-leader-election/scripts/logs", warn=True)
        conn.run("rm -f frugal-leader-election/scripts/logs/*", warn=True)

    for replica_id, node in enumerate(nodes):
        replica_ip = node["host"]
        replica_port = node["port"]
        print(f"Starting replica {replica_id+1} on remote node {replica_ip} with port {replica_port}")

        try:
            
            conn = Connection(host=replica_ip, user=username, port=node["port"])
            
            cmd = f"cd frugal-leader-election && nohup {binary_path} --config={remote_config_path} --replicaId={replica_id + 1} > scripts/logs/node_{replica_id + 1}.log 2>&1 &"
            print(cmd)
            conn.run(cmd, pty=False, asynchronous=True)

            print(f"Replica {replica_id+1} started on {replica_ip}, logging to ./logs/node_{replica_id+1}.log")
        except Exception as e:
            print(f"Failed to start replica {replica_id+1} on {replica_ip}: {e}")
            continue

    print("All remote nodes have been started.")
    print("Logs are available in the 'logs/' directory on each respective node.")

@task
def start(c):
    """
    Starts 4 instances of the leader_election binary, each on a unique port.
    Logs are stored in the logs/ directory.
    """
    global processes
    
    config_path = "../configs/local.yaml"
    
    # Ensure the binary exists
    binary_path = "../bazel-bin/leader_election"
    if not os.path.isfile(binary_path):
        print(f"Binary not found at {binary_path}. Please build it using Bazel.")
        sys.exit(1)
        
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
        
    replica_ips = config["replica"]["ips"]
    n_replicas = len(replica_ips)   
    print("num replicas: ", n_replicas)
    
    # Create logs directory if it doesn't exist
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    
    for replica_id in range(n_replicas):
        log_file = logs_dir / f"node_{replica_id}.log"
        cmd = [binary_path, f"--config={config_path}", f"--replicaId={replica_id}"]
        
        print(f"Starting replica {replica_id} with command: {' '.join(cmd)}")
    
        log_file = logs_dir / f"node_{replica_id}.log"
        # Open the log file
        with open(log_file, "w") as logf:
            # Start the process
            process = subprocess.Popen(
                cmd,
                stdout=logf,
                stderr=subprocess.STDOUT,
                preexec_fn=os.setsid  # To allow killing the whole process group
            )
            processes[replica_id] = process
            print(f"Replica {replica_id} started with PID {process.pid}, logging to {log_file}")
    print("All nodes have been started.")
    print("Check the 'logs/' directory for individual node logs.")

@task
def stop(c):
    """
    Stops all running leader_election processes.
    """
    global processes

    if not processes:
        print("No running processes found. Ensure you started the nodes using the 'start' task.")
        return
    
    for port, process in processes.items():
        try:
            print(f"Terminating node on port {port} with PID {process.pid}")
            # Terminate the process group
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except Exception as e:
            print(f"Error terminating node on port {port}: {e}")
    
    # Clear the processes dictionary
    processes.clear()
    print("All nodes have been terminated.")

@task
def restart(c):
    """
    Restarts all leader_election processes.
    """
    stop(c)
    start(c)

@task
def status(c):
    """
    Checks the status of all leader_election processes.
    """
    global processes

    if not processes:
        print("No running processes found.")
        return
    
    for port, process in processes.items():
        ret = process.poll()
        if ret is None:
            print(f"Node on port {port} is running with PID {process.pid}")
        else:
            print(f"Node on port {port} has terminated with exit code {ret}")
