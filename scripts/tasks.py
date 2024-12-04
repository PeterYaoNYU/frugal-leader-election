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
from datetime import datetime
import time

# Define the ports and peers
PORTS = [5000, 5001, 5002, 5003]
IP = "127.0.0.1"

# Dictionary to store process PIDs
processes = {}

# Define node connection details
# nodes = [
#     # {"host": "c240g5-110103.wisc.cloudlab.us", "port": 26010},
#     {"host": "c240g5-110103.wisc.cloudlab.us", "port": 26011},
#     {"host": "c240g5-110103.wisc.cloudlab.us", "port": 26012},
#     {"host": "c240g5-110103.wisc.cloudlab.us", "port": 26013},
#     {"host": "c240g5-110103.wisc.cloudlab.us", "port": 26014},
#     {"host": "c240g5-110103.wisc.cloudlab.us", "port": 26015},
# ]


# nodes = [
#     {"host": "c220g2-011125.wisc.cloudlab.us", "port": 26610},
#     {"host": "c220g2-011125.wisc.cloudlab.us", "port": 26611},
#     {"host": "c220g2-011125.wisc.cloudlab.us", "port": 26612},
#     {"host": "c220g2-011125.wisc.cloudlab.us", "port": 26613},
#     {"host": "c220g2-011125.wisc.cloudlab.us", "port": 26614},
# ]

# nodes = [
#     {"host": "pc605.emulab.net", "port": 29442},
#     {"host": "pc604.emulab.net", "port": 29442},
#     {"host": "pc605.emulab.net", "port": 29443},
#     {"host": "pc606.emulab.net", "port": 29442},
#     {"host": "pc603.emulab.net", "port": 29442},
# ]

# nodes = [
#     {"host": "c220g1-031113.wisc.cloudlab.us", "port": 22},
#     {"host": "c220g1-031130.wisc.cloudlab.us", "port": 22},
#     {"host": "c220g1-031108.wisc.cloudlab.us", "port": 22},
#     {"host": "c220g1-031125.wisc.cloudlab.us", "port": 22},
#     {"host": "c220g1-031129.wisc.cloudlab.us", "port": 22},
# ]

# nodes = [
#     {"host": "c220g2-010828.wisc.cloudlab.us", "port": 26610},
#     {"host": "c220g2-010823.wisc.cloudlab.us", "port": 26610},
#     {"host": "c220g2-010823.wisc.cloudlab.us", "port": 26611},
#     {"host": "c220g2-010828.wisc.cloudlab.us", "port": 26611},
#     {"host": "c220g2-010823.wisc.cloudlab.us", "port": 26612},
#     # {"host": "c240g5-110103.wisc.cloudlab.us", "port": 26612},
# ]


nodes = [
    {"host": "c220g1-030822.wisc.cloudlab.us", "port": 28010},
    {"host": "c220g1-030822.wisc.cloudlab.us", "port": 28011},
    {"host": "c220g1-030822.wisc.cloudlab.us", "port": 28012},
    {"host": "c220g1-030822.wisc.cloudlab.us", "port": 28013},
    {"host": "c220g1-030822.wisc.cloudlab.us", "port": 28014},
]


# SSH username
username = "PeterYao"



@task
def start_remote(c, config_file, log_suffix=""):
    """
    Starts instances of the leader_election binary on remote nodes as specified in the given config file.
    Logs are stored in the logs/ directory with a subdirectory named after the config file.
    
    Parameters:
        config_file (str): The path to the configuration file to use.
    """
    remote_config_path = f"configs/{config_file}"
    log_subdir = f"logs/{config_file.replace('.yaml', '')}"

    # Ensure the binary path is defined
    binary_path = "bazel-bin/leader_election"

    with open(f"../{remote_config_path}", "r") as f:
        config = yaml.safe_load(f)

    replica_ips = config["replica"]["ips"]
    n_replicas = len(replica_ips)
    print("Number of replicas: ", n_replicas)
    
    for replica_id, node in enumerate(nodes):
        replica_ip = node["host"]
        replica_port = node["port"]
        print(f"Clearing logs and running processes for replica {replica_id} on {replica_ip} with port {replica_port}")

        # Establish connection to the remote node
        conn = Connection(host=replica_ip, user=username, port=node["port"])
        
        conn.sudo("killall leader_election", warn=True)
        conn.run(f"mkdir -p frugal-leader-election/scripts/{log_subdir}", warn=True)
        # conn.run(f"rm -f frugal-leader-election/scripts/{log_subdir}/*", warn=True)

    for replica_id, node in enumerate(nodes):
        replica_ip = node["host"]
        replica_port = node["port"]
        print(f"Starting replica {replica_id+1} on remote node {replica_ip} with port {replica_port}")

        try:
            conn = Connection(host=replica_ip, user=username, port=node["port"])
            
            cmd = f"cd frugal-leader-election && nohup {binary_path} --config={remote_config_path} --replicaId={replica_id} > scripts/{log_subdir}/node_{replica_id + 1}_{log_suffix}.log 2>&1 &"
            print(cmd)
            conn.run(cmd, pty=False, asynchronous=True)

            print(f"Replica {replica_id+1} started on {replica_ip}, logging to ./{log_subdir}/node_{replica_id+1}_{log_suffix}.log")
        except Exception as e:
            print(f"Failed to start replica {replica_id+1} on {replica_ip}: {e}")
            continue

    print("All remote nodes have been started.")
    print(f"Logs are available in the '{log_subdir}/' directory on each respective node.")


@task
def download_logs(c, log_dir_name=None, log_suffix=""):
    """
    Downloads log files from remote nodes into a local folder named with the provided log_dir_name or the current timestamp.
    
    Parameters:
        log_dir_name (str, optional): The name for the local logs directory. Defaults to a timestamp-based name.
        log_suffix (str, optional): A suffix to identify log files for specific experiment iterations.
    """
    # Create a folder with the specified name or current timestamp
    if log_dir_name is None:
        log_dir_name = datetime.now().strftime("%Y%m%d_%H%M%S")
    logs_dir = Path("downloaded_logs") / log_dir_name
    logs_dir.mkdir(parents=True, exist_ok=True)

    # For each node, download the log file with the specified suffix
    for replica_id, node in enumerate(nodes[0:1]):
        replica_ip = node["host"]
        replica_port = node["port"]
        node_name = f"node_{replica_id + 1}"

        # Append log_suffix to both remote and local log file paths
        remote_log_path = f"/users/{username}/frugal-leader-election/scripts/logs/{log_dir_name}/{node_name}_{log_suffix}.log"
        local_log_path = logs_dir / f"{node_name}_{log_suffix}.log"

        print(f"Downloading log file from {replica_ip}:{remote_log_path} to {local_log_path}")

        try:
            conn = Connection(host=replica_ip, user=username, port=replica_port)
            # Use conn.get() to download the file
            conn.get(remote=remote_log_path, local=str(local_log_path))
        except Exception as e:
            print(f"Failed to download log file from {replica_ip}: {e}")

    print(f"Logs downloaded into {logs_dir}")


@task
def download_multi_logs(c, log_dir_name=None, start_idx=1, end_idx=5):
    """
    Downloads log files for multiple runs from remote nodes within a specified range.
    Each log file is distinguished by an index-based suffix.

    Parameters:
        log_dir_name (str, optional): The name for the local logs directory. Defaults to a timestamp-based name.
        start_idx (int): The starting index for the log files to download.
        end_idx (int): The ending index for the log files to download.
    """
    if log_dir_name is None:
        log_dir_name = datetime.now().strftime("%Y%m%d_%H%M%S")
    logs_dir = Path("downloaded_logs") / log_dir_name
    logs_dir.mkdir(parents=True, exist_ok=True)

    for idx in range(start_idx, end_idx + 1):
        log_suffix = f"run_{idx}"
        print(f"\n=== Downloading logs for iteration {log_suffix} ===")
        download_logs(c, log_dir_name=log_dir_name, log_suffix=log_suffix)

    print(f"\nAll logs from run {start_idx} to {end_idx} have been downloaded.")



@task
def start_remote_default(c):
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
        
        conn.sudo("killall leader_election", warn=True)
        conn.run("mkdir -p frugal-leader-election/scripts/logs", warn=True)
        conn.run("rm -f frugal-leader-election/scripts/logs/*", warn=True)

    for replica_id, node in enumerate(nodes):
        replica_ip = node["host"]
        replica_port = node["port"]
        print(f"Starting replica {replica_id+1} on remote node {replica_ip} with port {replica_port}")

        try:
            
            conn = Connection(host=replica_ip, user=username, port=node["port"])
            
            cmd = f"cd frugal-leader-election && nohup {binary_path} --config={remote_config_path} --replicaId={replica_id} > scripts/logs/node_{replica_id + 1}.log 2>&1 &"
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


@task
def analyze_logs_false_pos(c):
    """
    Runs extract_failure.py on all remote hosts using the respective replica ID as the argument.
    """
    for replica_id, node in enumerate(nodes):
        replica_ip = node["host"]
        replica_port = node["port"]

        print(f"Analyzing logs for replica {replica_id + 1} on remote node {replica_ip} with port {replica_port}")

        try:
            # Establish connection to the remote node
            conn = Connection(host=replica_ip, user=username, port=node["port"])
            
            
            # Install matplotlib using pip with the -y flag
            # install_cmd = "pip install matplotlib"
            # print(f"Installing matplotlib on remote node: {install_cmd}")
            # conn.run(install_cmd, pty=True)

            # Run extract_failure.py on the remote node
            cmd = f"cd frugal-leader-election/scripts && python3 extract_failure.py {replica_id + 1}"
            print(f"Running command on remote node: {cmd}")
            result = conn.run(cmd, hide=True)

            # Print the output of the command
            print(result.stdout)
            
            
            # Download the plot file from the remote node
            remote_plot_path = f"failure_occurrences.png"
            local_plot_path = f"plots/leader_failure_node_{replica_id + 1}_downloaded.png"
            print(f"Downloading plot file from {replica_ip}: {remote_plot_path} to local path: {local_plot_path}")
            
            # Ensure local plot directory exists
            Path("plots").mkdir(exist_ok=True)
            
            # Download the plot file
            conn.get(remote=remote_plot_path, local=local_plot_path)
            
            
        except Exception as e:
            print(f"Failed to analyze logs for replica {replica_id + 1} on {replica_ip}: {e}")
            continue

    print("Log analysis completed for all remote nodes.")
    
    
@task
def run_iperf3_servers(c):
    """
    Task to automate the running of iperf3 servers on all nodes using Fabric.
    """

    for node_id, node in enumerate(nodes, start=1):
        node_host = node["host"]
        print(f"Running iperf3 client script on node {node_id} with host {node_host}")

        try:
            conn = Connection(host=node_host, user=username, port=node["port"])
            cmd = f"python3 frugal-leader-election/scripts/background_tcp_simulation/iperf_tcp_gen.py {node_id} server"
            # Replace "username" with your actual SSH username
            result = conn.run(cmd, hide=True)
            print(result.stdout)
        except Exception as e:
            print(f"Failed to run iperf3 server script on node {node_id} ({node_host}): {e}")
            continue

    print("iperf3 server script execution completed for all nodes.")

@task
def run_iperf3_clients(c):
    """
    Task to automate the running of iperf3 clients on all nodes using Fabric.
    """

    for node_id, node in enumerate(nodes, start=1):
        node_host = node["host"]
        print(f"Running iperf3 client script on node {node_id} with host {node_host}")

        try:
            conn = Connection(host=node_host, user=username, port=node["port"])
            cmd = f"python3 frugal-leader-election/scripts/background_tcp_simulation/iperf_tcp_gen.py {node_id} client"
            result = conn.sudo(cmd, hide=True)
            print(result.stdout)
        except Exception as e:
            print(f"Failed to run iperf3 client script on node {node_id} ({node_host}): {e}")
            continue

    print("iperf3 client script execution completed for all nodes.")
    
    
@task
def killall_remote(c):
    for replica_id, node in enumerate(nodes):
        replica_ip = node["host"]
        replica_port = node["port"]


        try:
            # Establish connection to the remote node
            conn = Connection(host=replica_ip, user=username, port=node["port"])

            cmd = "killall leader_election"
            result = conn.sudo(cmd, hide=True)
            print(result.stdout)
        except Exception as e:
            print(f"Failed to kill all leader_election processes on node {replica_ip}: {e}")
            continue
        
@task
def killall_python(c):
    for replica_id, node in enumerate(nodes):
        replica_ip = node["host"]
        replica_port = node["port"]


        try:
            # Establish connection to the remote node
            conn = Connection(host=replica_ip, user=username, port=node["port"])

            cmd = "killall python3"
            result = conn.sudo(cmd, hide=True)
            print(result.stdout)
        except Exception as e:
            print(f"Failed to kill all python3 processes on node {replica_ip}: {e}")
            continue
        
@task
def killall_remote_iperf(c):
    for replica_id, node in enumerate(nodes):
        replica_ip = node["host"]
        replica_port = node["port"]


        try:
            # Establish connection to the remote node
            conn = Connection(host=replica_ip, user=username, port=node["port"])

            cmd = "killall iperf3"
            result = conn.sudo(cmd, hide=True)
            print(result.stdout)
        except Exception as e:
            print(f"Failed to kill all iperf3 processes on node {replica_ip}: {e}")
            continue
        
username = "PeterYao"

@task
def download_logs_default(c):
    """
    Downloads log files from remote nodes into a local folder named with the current timestamp.
    """
    # Create a folder with the current timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    logs_dir = Path("downloaded_logs") / timestamp
    logs_dir.mkdir(parents=True, exist_ok=True)

    # For each node, download the log file
    for replica_id, node in enumerate(nodes):
        replica_ip = node["host"]
        replica_port = node["port"]
        node_name = f"node_{replica_id + 1}"

        remote_log_path = f"/users/{username}/frugal-leader-election/scripts/logs/{node_name}.log"
        local_log_path = logs_dir / f"{node_name}.log"

        print(f"Downloading log file from {replica_ip}:{remote_log_path} to {local_log_path}")

        try:
            conn = Connection(host=replica_ip, user=username, port=replica_port)
            # Use conn.get() to download the file
            conn.get(remote=remote_log_path, local=str(local_log_path))
        except Exception as e:
            print(f"Failed to download log file from {replica_ip}: {e}")

    print(f"Logs downloaded into {logs_dir}")


@task
def run_multiple_experiments(c, config_file, times=5, wait_time=530):
    """
    Runs the remote experiment multiple times.
    After each run, downloads the logs to the local machine before starting the next experiment.
    Parameters:
        times (int): Number of times to run the experiment.
        wait_time (int): Time in seconds to wait between starting the experiment and downloading logs.
    """
    for i in range(times):
        log_suffix = f"run_{i+1}"
        print(f"\n=== Starting experiment iteration {i+1}/{times} ===")
        start_remote(c, config_file, log_suffix=log_suffix)
        print(f"Experiment {i+1} started. Waiting for {wait_time} seconds to let it run...")
        time.sleep(wait_time)
        # print(f"Downloading logs for experiment {i+1}")
        # download_logs(c)
        print(f"Stopping remote processes after experiment {i+1}")
        killall_remote(c)
        print(f"Experiment {i+1} completed.")
    print("\nAll experiments completed.")
    
    
    
@task
def automate_exp(c, config_files):
    """
    Automates a series of experiments using the given list of configuration files.
    Each experiment runs for multiple iterations as defined in run_multiple_experiments.
    
    Parameters:
        config_files (str): A comma-separated string of configuration file names (YAML files) to use for each experiment.
    """
    # Split the config_files string into a list
    config_files_list = config_files.split(',')

    if not config_files_list:
        print("No configuration files provided. Please specify at least one configuration file.")
        return

    for config_file in config_files_list:
        config_file = config_file.strip()
        print(f"\n=== Starting automated experiments with config file: {config_file} ===")
        
        # Run multiple experiments with the current config file
        run_multiple_experiments(c, config_file=config_file, times=5, wait_time=530)
        download_logs_default(c)

    print("\nAll automated experiments completed.")
