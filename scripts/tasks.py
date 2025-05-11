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
from time import sleep

import shutil                          # <<< NEW >>>
import glob                            # <<< NEW >>>

# Define the ports and peers
PORTS = [5000, 5001, 5002, 5003]
IP = "127.0.0.1"

# Dictionary to store process PIDs
processes = {}

# Define node connection details

nodes = [
    {"host": "amd128.utah.cloudlab.us", "port": 22},
    {"host": "amd141.utah.cloudlab.us", "port": 22},
    {"host": "amd147.utah.cloudlab.us", "port": 22},
    {"host": "amd139.utah.cloudlab.us", "port": 22},
    {"host": "amd158.utah.cloudlab.us", "port": 22},
]

# nodes = [
#     {"host": "pc532.emulab.net", "port": 22},
#     {"host": "pc417.emulab.net", "port": 22},
#     {"host": "pc559.emulab.net", "port": 22},
#     {"host": "pc509.emulab.net", "port": 22},
#     {"host": "pc545.emulab.net", "port": 22},
#     # {"host": "pc503.emulab.net", "port": 22},
# ]

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
def start_remote_default_with_client(c, leaderId, serverPort, sendMode, value):
    """
    Starts instances of the leader_election binary on remote nodes as specified in the config file.
    Logs are stored in the logs/ directory of each respective node.
    """
    config_path = "../configs/remote.yaml"
    remote_config_path = "/users/PeterYao/frugal-leader-election/configs/remote.yaml"
    
    full_remote_config_path = f"/home/peter/frugal-leader-election/configs/remote.yaml"
    
    # put the local remote.yaml file to the remote nodes
    for replica_id, node in enumerate(nodes):
        replica_ip = node["host"]
        replica_port = node["port"]
        print(f"putting remote config file to remote node {replica_id} on remote node {replica_ip} with port {replica_port}")

        try:
            # Establish connection to the remote node
            print("File exists:", os.path.exists(full_remote_config_path))
            conn = Connection(host=replica_ip, user=username, port=node["port"])
            conn.put(full_remote_config_path, remote_config_path)
        except Exception as e:
            print(f"Failed to put remote config file to replica {replica_id} on {replica_ip}: {e}")
            continue

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
            
            cmd = f"cd frugal-leader-election && nohup {binary_path} --config={remote_config_path} --replicaId={replica_id} --minloglevel=1 > scripts/logs/node_{replica_id + 1}.log 2>&1 &"
            # cmd = f"cd frugal-leader-election && nohup {binary_path} --config={remote_config_path} --replicaId={replica_id} > scripts/logs/node_{replica_id + 1}.log 2>&1 &"
            
            print(cmd)
            conn.run(cmd, pty=False, asynchronous=True)

            print(f"Replica {replica_id+1} started on {replica_ip}, logging to ./logs/node_{replica_id+1}.log")
        except Exception as e:
            print(f"Failed to start replica {replica_id+1} on {replica_ip}: {e}")
            continue
        
        
    bind_ips = ["10.0.0.2", "10.0.0.3", "10.0.4.2", "10.0.1.2", "10.0.1.3"]
    conn = Connection(host=nodes[0]["host"], user=username, port=nodes[0]["port"])
    cmd = f"cd frugal-leader-election && nohup bazel-bin/client {bind_ips[leaderId]} {serverPort} {sendMode} {value} {str(random.randint(1, 9999))} {bind_ips[replica_id]} > client_remote.log 2>&1"
    conn.run(cmd, pty=False, asynchronous=True)
    
    sleep(100)
    
    
    print("All remote nodes have been started.")
    print("Logs are available in the 'logs/' directory on each respective node.")

@task
def start_remote_default(c):
    """
    Starts instances of the leader_election binary on remote nodes as specified in the config file.
    Logs are stored in the logs/ directory of each respective node.
    """
    config_path = "../configs/remote.yaml"
    remote_config_path = "/users/PeterYao/frugal-leader-election/configs/remote.yaml"
    
    full_remote_config_path = f"/home/peter/frugal-leader-election/configs/remote.yaml"
    
    # put the local remote.yaml file to the remote nodes
    for replica_id, node in enumerate(nodes):
        replica_ip = node["host"]
        replica_port = node["port"]
        print(f"putting remote config file to remote node {replica_id} on remote node {replica_ip} with port {replica_port}")

        try:
            # Establish connection to the remote node
            print("File exists:", os.path.exists(full_remote_config_path))
            conn = Connection(host=replica_ip, user=username, port=node["port"])
            conn.put(full_remote_config_path, remote_config_path)
        except Exception as e:
            print(f"Failed to put remote config file to replica {replica_id} on {replica_ip}: {e}")
            continue

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
        conn.sudo("killall client", warn=True)
        
        conn.run("mkdir -p frugal-leader-election/scripts/logs", warn=True)
        conn.run("rm -f frugal-leader-election/scripts/logs/*", warn=True)

    for replica_id, node in enumerate(nodes):
        replica_ip = node["host"]
        replica_port = node["port"]
        print(f"Starting replica {replica_id+1} on remote node {replica_ip} with port {replica_port}")

        try:
            
            conn = Connection(host=replica_ip, user=username, port=node["port"])
            
            cmd = f"cd frugal-leader-election && nohup {binary_path} --config={remote_config_path} --replicaId={replica_id} --minloglevel=0 > scripts/logs/node_{replica_id + 1}.log 2>&1 &"
            # cmd = f"cd frugal-leader-election && nohup {binary_path} --config={remote_config_path} --replicaId={replica_id} > scripts/logs/node_{replica_id + 1}.log 2>&1 &"
            
            print(cmd)
            conn.run(cmd, pty=False, asynchronous=True)

            print(f"Replica {replica_id+1} started on {replica_ip}, logging to ./logs/node_{replica_id+1}.log")
        except Exception as e:
            print(f"Failed to start replica {replica_id+1} on {replica_ip}: {e}")
            continue

    print("All remote nodes have been started.")
    print("Logs are available in the 'logs/' directory on each respective node.")
    
    
@task
def count_leader(c):
    for i in range(1, 6):
        print("=========== Node ", i-1, " ===========")
        conn = Connection(host=nodes[i-1]["host"], user=username, port=nodes[i-1]["port"])
        cmd = f"cd frugal-leader-election/scripts && python3 count_leader.py logs/node_{i}.log"
        # print(f"Running command on remote node: {cmd}")
        conn.run(cmd)
     


# invoke start-client --serverIp 127.0.0.4 --serverPort 10892 --value 5 --bindIp 127.0.0.18
@task
def start_client(c, serverIp, serverPort, value, bindIp, log_suffix="client"):
    """
    Starts the client process locally.
    
    Parameters:
      server_ip (str): The IP address of the server to connect to.
      server_port (int): The port number of the server.
      sendMode (str): The sending mode ("fixed" or "maxcap").
      value (str): If sendMode is "fixed", the fixed interval in seconds (as a float);
                   if sendMode is "maxcap", the maximum number of in-flight requests (as an int).
    """
    # print("sendMode is: ", sendMode)
    # if sendMode.lower() == "fixed":
    #     mode_arg = "fixed"
    # elif sendMode.lower() == "maxcap":
    #     mode_arg = "maxcap"
    # else:
    #     print("Unknown mode. Use 'fixed' or 'maxcap'.")
    #     return

    # sendMode = "fixed"
    sendMode = "maxcap"

    binary_path = "../bazel-bin/client"  # Path to the built client binary.
    # Build the command-line arguments. (Client expects: server_ip server_port mode value)
    client_id = random.randint(1, 9999)
    cmd = [binary_path, serverIp, str(serverPort), sendMode, value, str(client_id), bindIp]
    
    # Create logs directory if it doesn't exist
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    log_file = logs_dir / f"{log_suffix}.log"
    
    try:
        with open(log_file, "w") as logf:
            client_proc = subprocess.Popen(
                cmd,
                stdout=logf,
                stderr=subprocess.STDOUT,
                preexec_fn=os.setsid  # To allow killing the whole process group if needed
            )
            processes["client"] = client_proc
            print(f"Client started with PID {client_proc.pid}, logging to {log_file}")
    except Exception as e:
        print(f"Failed to start client: {e}")
        
        
processes = {}  # To store the client processes

# invoke start-clients --serverIp 127.0.0.4 --serverPort 10046 --value 5
@task
def start_clients(c, serverIp, serverPort, value):
    """
    Starts two client processes concurrently.
    
    Parameters:
      serverIp (str): The IP address of the server to connect to.
      serverPort (int): The port number of the server.
      value (str): For 'fixed' mode, the fixed interval in seconds (as a float);
                   for 'maxcap' mode, the maximum number of in-flight requests (as an int).
    """
    # sendMode = "fixed"
    sendMode = "maxcap"
    binary_path = "../bazel-bin/client"  # Path to the built client binary.
    
    # Create logs directory if it doesn't exist
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    
    client_id_one = 123
    client_id_two = 456
    client_id_three = 789
    client_id_four = 1011
    client_ids = [client_id_one, client_id_two, client_id_three, client_id_four]
    # client_ids = [client_id_one, client_id_two]
    
    
    # Loop to start two clients.
    for i in range(1, 5):
        # Create a unique log file for each client.
        log_file = logs_dir / f"client_{i}.log"
        cmd = [binary_path, serverIp, str(serverPort), sendMode, value, str(client_ids[i-1])]
        
        try:
            with open(log_file, "w") as logf:
                client_proc = subprocess.Popen(
                    cmd,
                    stdout=logf,
                    stderr=subprocess.STDOUT,
                    preexec_fn=os.setsid  # To allow killing the whole process group if needed
                )
                processes[f"client_{i}"] = client_proc
                print(f"Client {i} started with PID {client_proc.pid}, logging to {log_file}")
        except Exception as e:
            print(f"Failed to start client {i}: {e}")

# invoke start-client-remote --remoteHostId 5 --serverIp 10.0.0.3 --serverPort 10083 --value 5 --bindIp 10.0.3.1
# invoke start-client-remote --remoteHostId 5 --serverIp 10.0.0.3 --serverPort 10083 --value 0.001 --bindIp 10.0.3.1
# ./bazel-bin/client 10.0.0.3 6114 maxcap 5 789 > client_nochange.log 2>&1
@task
def start_client_remote(c, remoteHostId, serverIp, serverPort, value, bindIp, logSuffix=""):
    """
    Starts the client process on a remote node.
    
    Parameters:
      remote_host_id: The index of the remote node in the 'nodes' list.
      serverIp (str): The IP address of the server to connect to.
      serverPort (int): The port number of the server.
      value (str): For 'fixed' mode, the fixed interval in seconds; for 'maxcap' mode, the maximum number of in-flight requests.
      
    This function is similar to start_client() but executes the client on the specified remote node.
    """
    # For this example we assume fixed mode.
    sendMode = "maxcap"
    # sendMode = "fixed"
    binary_path = "bazel-bin/client"  # Path to the built client binary on the remote node.
    # Build the command-line string (client expects: serverIp serverPort mode value)
    killall_cmd = "killall client"
    cmd = f"cd frugal-leader-election && nohup {binary_path} {serverIp} {serverPort} {sendMode} {value} 316 {bindIp}> client.log 2>&1 &"
    
    remote_host = nodes[int(remoteHostId)]["host"]    

    print(f"Starting remote client on {remote_host} with command: {cmd}")
    
    try:
        # Connect to the remote node (using default SSH port 22)
        conn = Connection(host=remote_host, user=username, port=22)
        conn.sudo(killall_cmd, warn=True)
        # Run the command asynchronously; pty is set to False to avoid allocation of a pseudo-terminal.
        conn.run(cmd, pty=False, asynchronous=True)
        print(f"Remote client started on {remote_host}, logging to client_remote.log")
        sleep(100)
        conn.run("killall client", warn=True)
        # conn.get("frugal-leader-election/client_remote.log", local=f"client_remote_{logSuffix}.log")
        
    except Exception as e:
        print(f"Failed to start remote client on {remote_host}: {e}")

import random
# invoke start-clients-remote --leaderId 1 --serverPort 10083 --value 5
@task
def start_clients_remote(c, leaderId ,serverPort, value, logSuffix=""):
    """
    Starts the client process on a remote node.
    
    Parameters:
      remote_host_id: The index of the remote node in the 'nodes' list.
      serverIp (str): The IP address of the server to connect to.
      serverPort (int): The port number of the server.
      value (str): For 'fixed' mode, the fixed interval in seconds; for 'maxcap' mode, the maximum number of in-flight requests.
      
    This function is similar to start_client() but executes the client on the specified remote node.
    """
    # For this example we assume fixed mode.
    sendMode = "maxcap"
    binary_path = "bazel-bin/client"  # Path to the built client binary on the remote node.
    # Build the command-line string (client expects: serverIp serverPort mode value)
    

    client_id_one = 123
    client_id_two = 456
    client_id_three = 789
    client_id_four = 1011
    client_id_five = 1213
    # client_ids = [client_id_one, client_id_two, client_id_three, client_id_four, client_id_five]
    client_ids = [random.randint(1, 9999) for _ in range(5)]
    bind_ips = ["10.0.0.2", "10.0.0.3", "10.0.4.2", "10.0.1.2", "10.0.1.3"]
    serverIp = bind_ips[int(leaderId)]
    # client_ids = [client_id_one, client_id_two]
    
    for replica_id, node in enumerate(nodes[:5]):
        replica_ip = node["host"]
        replica_port = node["port"]
        print(f"Starting client {replica_id+1} on remote node {replica_ip} with port {replica_port}")

        try:
            conn = Connection(host=replica_ip, user=username, port=node["port"])
            conn.sudo("killall client", warn=True)  
            cmd = f"cd frugal-leader-election && nohup {binary_path} {serverIp} {serverPort} {sendMode} {value} {str(client_ids[replica_id])} {bind_ips[replica_id]} > client_remote.log 2>&1 &"
            conn.run(cmd, pty=False, asynchronous=True)
        except Exception as e:
            print(f"Failed to start client {replica_id+1} on {replica_ip}: {e}")
            continue
        
    sleep(200)
    for replica_id, node in enumerate(nodes):
        replica_ip = node["host"]
        replica_port = node["port"]
        print(f"Stopping client {replica_id+1} on remote node {replica_ip} with port {replica_port}")

        try:
            conn = Connection(host=replica_ip, user=username, port=node["port"])
            cmd = "killall client"
            conn.sudo(cmd, pty=False, asynchronous=True)
        except Exception as e:
            print(f"Failed to stop client {replica_id+1} on {replica_ip}: {e}")
            continue
        
        
    for replica_id, node in enumerate(nodes[:5]):
        replica_ip = node["host"]
        replica_port = node["port"]
        print(f"Downloading client log file from {replica_ip} to client_remote_{replica_id}.log")

        try:
            conn = Connection(host=replica_ip, user=username, port=node["port"])
            cmd = "cd ~/frugal-leader-election && python3 scripts/analyze_resp_time.py client_remote.log > result.txt 2>&1"
            conn.run(cmd, pty=False, asynchronous=False)
            conn.get("/users/PeterYao/frugal-leader-election/result.txt", local=f"client_remote_{replica_id}.log")
        except Exception as e:
            print(f"Failed to download client log file from {replica_ip}: {e} to client_remote_{replica_id}.log")
            continue
        
    # ----------------------------------------------------------------------
    # >>>> NEW STEP 1: Run sum_all_clients.py locally
    # ----------------------------------------------------------------------
    try:
        # You can also use `c.local` if preferred:
        # c.local("python3 sum_all_clients.py", replace_env=False)
        subprocess.run(["python3", "sum_all_clients.py"], check=True)  # <<< NEW >>>
        print("Executed sum_all_clients.py")                           # <<< NEW >>>
    except Exception as e:
        print(f"Failed to run sum_all_clients.py: {e}")                # <<< NEW >>>

    # ----------------------------------------------------------------------
    # >>>> NEW STEP 2: Create archive folder and move logs
    # ----------------------------------------------------------------------
    current_time = datetime.now().strftime("%Y%m%d_%H%M%S")           # <<< NEW >>>
    folder_name  = f"leader{leaderId}_{current_time}"                 # <<< NEW >>>
    os.makedirs(folder_name, exist_ok=True)                           # <<< NEW >>>

    for f in glob.glob("client_remote_*.log"):                        # <<< NEW >>>
        try:
            shutil.move(f, os.path.join(folder_name, f))              # <<< NEW >>>
        except Exception as e:
            print(f"Failed moving {f}: {e}")                          # <<< NEW >>>

    print(f"Archived logs in ./{folder_name}")                        # <<< NEW >>>
    
    
# invoke batch-experiments-motivation --leaderId 1 --serverPort 10083 --value 5 --runs 1
@task
def batch_experiments_motivation(c, leaderId, serverPort, value, runs=5):
    """
    Run start_clients_remote `runs` times, parse the resulting
    Overall Throughput and Average latency from sum_all_clients.py,
    then print mean and standard deviation.
    """
    throughputs = []
    latencies   = []

    for i in range(1, runs + 1):
        print(f"\n=== Run {i}/{runs} ===")
        # 1) kick off the remote clients and archive logs
        start_remote_default(c)
        # start_clients_remote(c, leaderId, serverPort, value)
        start_clients_remote_collect(c, leaderId, serverPort, value)    
        
# invoke overhead-exp --serverIp 127.0.0.2 --serverPort 10999 --value 5 --bindIp 127.0.0.18  --bindIpTwo 127.0.0.19
@task
def overhead_exp(c, serverIp, serverPort, value, bindIp, bindIpTwo):
    start(c)
    sleep(10)
    start_client(c, serverIp, serverPort, value, bindIp)
    # start_client(c, serverIp, serverPort, value, bindIpTwo, log_suffix="client_2")
    sleep(180)
    stop(c)
    try:
        subprocess.run(["python3", "analyze_resp_time.py", "logs/client.log"], check=True)  # <<< NEW >>>
        # subprocess.run(["python3", "analyze_resp_time.py", "logs/client_2.log"], check=True)  # <<< NEW >>>
        print("Executed analyze_resp_time.py")                           # <<< NEW >>>
    except Exception as e:
        print(f"Failed to run analyze_resp_time.py: {e}")                # <<< NEW >>>
    try:
        subprocess.run(["python3", "avg_bps.py", "logs/"], check=True)  # <<< NEW >>>
        print("Executed avg_bps.py")                           # <<< NEW >>>
    except Exception as e:
        print(f"Failed to run avg_bps.py: {e}")                # <<< NEW >>>

@task
def get_results(c):
            
    for replica_id, node in enumerate(nodes[:5]):
        replica_ip = node["host"]
        replica_port = node["port"]
        print(f"Downloading client log file from {replica_ip} with port {replica_port}")

        try:
            conn = Connection(host=replica_ip, user=username, port=node["port"])
            cmd = "cd ~/frugal-leader-election && python3 scripts/analyze_resp_time.py client_remote.log > result.txt 2>&1 "
            conn.run(cmd, pty=False, asynchronous=False)
            conn.get("/users/PeterYao/frugal-leader-election/result.txt", local=f"client_remote_{replica_id}.log")
            print(f"Downloading client log file from {replica_ip} with port {replica_port} to client_remote_{replica_id}.log")
            
            
        except Exception as e:
            print(f"Failed to download client log file from {replica_ip}: {e} to client_remote_{replica_id}.log")
            continue
        
        
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
    
    # remove all logs:
    cmd = "rm -f logs/*"
    os.system(cmd)
    
    sleep(5)
    
    # Create logs directory if it doesn't exist
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    
    for replica_id in range(n_replicas):
        log_file = logs_dir / f"node_{replica_id}.log"
        cmd = [binary_path, f"--config={config_path}", f"--replicaId={replica_id}", "--minloglevel=3"]
        # cmd = [binary_path, f"--config={config_path}", f"--replicaId={replica_id}"]
        
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



# ----------------------------------------------------------------------
# Assumes `nodes` and `username` are already defined globally, and that
# remote_thp_summary.py / merge_thp_summaries.py are in ~/frugal-leader-election/scripts
# ----------------------------------------------------------------------

REMOTE_BASE = "~/frugal-leader-election"
BIN_CLIENT  = "bazel-bin/client"
SCRIPT_DIR  = f"{REMOTE_BASE}/scripts"
REMOTE_THP  = f"{SCRIPT_DIR}/remote_thp_summary.py"
LOCAL_MERGE = "merge_thp_summaries.py"           # must be in $PWD or give full path

@task
def start_clients_remote_collect(c,
                                 leaderId,
                                 serverPort,
                                 value,
                                 logSuffix="raft",
                                 run_seconds=300):
    """
    Launch clients on 5 remote nodes, wait, stop them, generate per‑node
    throughput summaries remotely, download them, and merge into a single plot.
    """

    # -------------------------------------------------
    # 0.  Convenience data
    # -------------------------------------------------
    sendMode = "maxcap"
    bind_ips   = ["10.0.0.2", "10.0.0.3", "10.0.4.2", "10.0.1.2", "10.0.1.3"]
    serverIp   = bind_ips[int(leaderId)]
    client_ids = [random.randint(1, 9999) for _ in range(5)]

    # -------------------------------------------------
    # 1.  Start clients
    # -------------------------------------------------
    for replica_id, node in enumerate(nodes[:5]):
        replica_ip = node["host"]
        print(f"[{replica_ip}] launching client")
        try:
            conn = Connection(host=replica_ip, user=username, port=node["port"])
            conn.sudo("killall client", warn=True)
            cmd = (
                f"cd {REMOTE_BASE} && "
                f"nohup {BIN_CLIENT} {serverIp} {serverPort} {sendMode} {value} "
                f"{client_ids[replica_id]} {bind_ips[replica_id]} "
                f"> client_remote.log 2>&1 &"
            )
            conn.run(cmd, pty=False, asynchronous=True)
        except Exception as e:
            print(f"‼️  start failed on {replica_ip}: {e}")

    # -------------------------------------------------
    # 2.  Wait for experiment, then kill clients
    # -------------------------------------------------
    sleep(run_seconds)
    for node in nodes[:5]:
        replica_ip = node["host"]
        try:
            Connection(host=replica_ip, user=username, port=node["port"]).sudo(
                "killall client", pty=False, asynchronous=True
            )
        except Exception as e:
            print(f"‼️  kill failed on {replica_ip}: {e}")

    # -------------------------------------------------
    # 3.  Run remote_thp_summary.py on each node
    # -------------------------------------------------
    for node in nodes[:5]:
        replica_ip = node["host"]
        try:
            conn = Connection(host=replica_ip, user=username, port=node["port"])
            cmd = (
                f"cd {REMOTE_BASE} && "
                f"python3 {REMOTE_THP} client_remote.log --out thp_summary.csv"
            )
            conn.run(cmd, hide="stdout")
        except Exception as e:
            print(f"‼️  summary generation failed on {replica_ip}: {e}")

    # -------------------------------------------------
    # 4.  Pull logs & CSVs back to workstation
    # -------------------------------------------------
    for replica_id, node in enumerate(nodes[:5]):
        replica_ip = node["host"]
        try:
            conn = Connection(host=replica_ip, user=username, port=node["port"])
            # conn.get(f"{REMOTE_BASE}/client_remote.log",
            #          local=f"client_remote_{replica_id}.log")
            conn.get(f"/users/PeterYao/frugal-leader-election/thp_summary.csv",
                     local=f"thp_{replica_id}.csv")
        except Exception as e:
            print(f"‼️  download failed from {replica_ip}: {e}")

    # -------------------------------------------------
    # 5.  Merge summaries locally
    # -------------------------------------------------
    csv_files = sorted(glob.glob("thp_*.csv"))
    if csv_files:
        try:
            subprocess.run(
                ["python3", LOCAL_MERGE, *csv_files,
                 "--plot", "combined_throughput.png",
                 "--csv",  "combined_throughput.csv"],
                check=True)
            print("✅ merged plot generated: combined_throughput.png")
        except subprocess.CalledProcessError as e:
            print(f"‼️  merge script failed: {e}")

    # -------------------------------------------------
    # 6.  Archive everything (logs, thp CSVs, and merged outputs)
    # -------------------------------------------------
    ts_folder = datetime.now().strftime(f"leader{leaderId}_%Y%m%d_%H%M%S{logSuffix}")
    os.makedirs(ts_folder, exist_ok=True)

    # move client logs and per-node CSVs
    for f in glob.glob("client_remote_*.log") + glob.glob("thp_*.csv"):
        try:
            shutil.move(f, os.path.join(ts_folder, f))
        except Exception as e:
            print(f"‼️  archiving {f} failed: {e}")

    # move the combined plot and CSV if they exist
    for fname in ("combined_throughput.png", "combined_throughput.csv"):
        if os.path.exists(fname):
            try:
                shutil.move(fname, os.path.join(ts_folder, fname))
            except Exception as e:
                print(f"‼️  moving {fname} to archive failed: {e}")

    print(f"📦  archived logs, CSVs, and merged outputs → {ts_folder}")
    
    
    
REMOTE_BASE   = "~/frugal-leader-election"
SCRIPT_DIR    = f"{REMOTE_BASE}/scripts"
REMOTE_COUNT  = f"remote_count_timeouts.py"

@task
def sum_remote_timeouts(c,
                        # logfile="node.log",
                        skip_first=30,
                        skip_last=50,
                        log_suffix="timeouts",
                        suffix="raft"):
    """
    Execute remote_count_timeouts.py on all 5 nodes, fetch the results, and
    output the grand total.

    Parameters
    ----------
    logfile     : filename of the Raft log on each node (default: node.log)
    skip_first  : seconds to skip from the beginning (default: 30)
    skip_last   : seconds to skip from the end      (default: 0)
    """
    
    start_remote_default(c)
    sleep(504)
    # -------------------------------------------------
    # 1.  Run remote_count_timeouts.py on every node
    # -------------------------------------------------
    for idx, node in enumerate(nodes[:5]):
        replica_ip = node["host"]
        print(f"[{replica_ip}] counting election timeouts")
        try:
            conn = Connection(host=replica_ip, user=username, port=node["port"])
            log_file = f"logs/node_{idx+1}.log"
            cmd = (
                f"cd /users/PeterYao/frugal-leader-election/scripts && "
                f"python3 {REMOTE_COUNT} {log_file} "
                f"--skip-first {skip_first} --skip-last {skip_last} "
                f"--out timeout_count.txt"
            )
            conn.run(cmd, hide="stdout")
        except Exception as e:
            print(f"‼️  counting failed on {replica_ip}: {e}")

    # -------------------------------------------------
    # 2.  Pull timeout_count.txt files back
    # -------------------------------------------------
    totals = []
    for replica_id, node in enumerate(nodes[:5]):
        replica_ip = node["host"]
        local_name = f"timeout_{replica_id}.txt"
        try:
            conn = Connection(host=replica_ip, user=username, port=node["port"])
            conn.get(f"/users/PeterYao/frugal-leader-election/scripts/timeout_count.txt", local=local_name)
            with open(local_name, "r") as f:
                val = int(f.read().strip())
            totals.append(val)
            print(f"{replica_ip}: {val}")
        except Exception as e:
            print(f"‼️  download/parse failed from {replica_ip}: {e}")

    grand_total = sum(totals)
    print(f"\nTOTAL election‑timeouts: {grand_total}")

    # also write a local file
    with open("total_timeouts.txt", "w") as f:
        f.write(str(grand_total) + "\n")

    # -------------------------------------------------
    # 3.  Archive the per‑node counts + total
    # -------------------------------------------------
    ts_folder = datetime.now().strftime(f"timeouts_%Y%m%d_%H%M%S{suffix}")
    os.makedirs(ts_folder, exist_ok=True)
    for f in glob.glob("timeout_*.txt") + ["total_timeouts.txt"]:
        try:
            shutil.move(f, os.path.join(ts_folder, f))
        except Exception as e:
            print(f"‼️  archiving {f} failed: {e}")

    print(f"📦  archived timeout counts → {ts_folder}")
    
    


REMOTE_BASE   = "/users/PeterYao/frugal-leader-election"
SCRIPT_DIR    = f"{REMOTE_BASE}/scripts"
REMOTE_DETECT = f"{SCRIPT_DIR}/remote_detect_stats.py"
from math import sqrt

@task
def sum_remote_detect(c,
                      skip_first=30,
                      skip_last=30,
                      log_suffix=""):
    """
    Run remote_detect_stats.py on all 5 nodes, pull results, and compute
    the weighted mean/std‑dev of detection time (ms).

    Parameters
    ----------
    logfile     : path *relative to REMOTE_BASE* for each node
    skip_first  : seconds to skip at start of each log
    skip_last   : seconds to skip at end of each log
    """
    # -------------------------------------------------
    # 1.  Execute remote_detect_stats.py on each node
    # -------------------------------------------------
    for idx, node in enumerate(nodes[:5]):
        replica_ip = node["host"]
        print(f"[{replica_ip}] computing detection‑time stats")
        try:
            conn = Connection(host=replica_ip, user=username, port=node["port"])
            log_file = f"logs/node_{idx+1}.log"
            cmd = (
                f"cd {SCRIPT_DIR} && "
                f"python3 {REMOTE_DETECT} {log_file} "
                f'--skip-first {skip_first} --skip-last {skip_last} '
                f'--out detect_stats.txt'
            )
            conn.run(cmd, hide="stdout")
        except Exception as e:
            print(f"‼️  stats generation failed on {replica_ip}: {e}")

    # -------------------------------------------------
    # 2.  Pull detect_stats.txt files back
    # -------------------------------------------------
    per_node = []   # list of (count, mean, std)
    for replica_id, node in enumerate(nodes[:5]):
        replica_ip = node["host"]
        local_name = f"detect_{replica_id}.txt"
        try:
            conn = Connection(host=replica_ip, user=username, port=node["port"])
            conn.get(f"{SCRIPT_DIR}/detect_stats.txt", local=local_name)
            with open(local_name) as f:
                cnt, m, s = map(float, f.read().split())
            per_node.append((int(cnt), m, s))
            print(f"{replica_ip}: n={cnt}, mean={m:.3f} ms, std={s:.3f} ms")
        except Exception as e:
            print(f"‼️  download/parse failed from {replica_ip}: {e}")

    # -------------------------------------------------
    # 3.  Weighted mean & std across all nodes
    # -------------------------------------------------
    total_n = sum(n for n, _, _ in per_node)
    if total_n == 0:
        print("⚠️  No samples found on any node.")
        return

    weighted_mean = sum(n * m for n, m, _ in per_node) / total_n

    # Weighted population variance:
    var = sum(n * (s**2 + (m - weighted_mean)**2) for n, m, s in per_node) / total_n
    weighted_std = sqrt(var)

    print(f"\nOverall weighted mean = {weighted_mean:.3f} ms")
    print(f"Overall weighted std  = {weighted_std:.3f} ms")

    # Save summary
    with open("detect_summary.txt", "w") as f:
        f.write(f"total_samples {total_n}\n")
        f.write(f"weighted_mean_ms {weighted_mean:.6f}\n")
        f.write(f"weighted_std_ms  {weighted_std:.6f}\n")

    # -------------------------------------------------
    # 4.  Archive everything
    # -------------------------------------------------
    ts_folder = datetime.now().strftime(f"detect_%Y%m%d_%H%M%S{log_suffix}")
    os.makedirs(ts_folder, exist_ok=True)
    for f in glob.glob("detect_*.txt") + ["detect_summary.txt"]:
        try:
            shutil.move(f, os.path.join(ts_folder, f))
        except Exception as e:
            print(f"‼️  archiving {f} failed: {e}")
    print(f"📦  archived detection stats → {ts_folder}")
    
@task
def batch_sum_remote_detect(c):
    for i in range(1, 2):
        print(f"\n=== Starting experiment iteration {i} ===")
        start_remote_default(c)
        sleep(305)
        sum_remote_detect(c, skip_first=30, skip_last=30, log_suffix=f"{i}")
        
import zookeeper_setup
@task
def batch_sum_remote_timeouts(c):
    # for dev in range(10, 60, 10):
        # zookeeper_setup.load_connections("fattree.yaml")
    #     zookeeper_setup.setup_delay_fat_tree_normal(0.2, dev)
        # zookeeper_setup.clear_all_switch_weights()
        for i in range(2):
            print(f"\n=== Starting experiment iteration {i} ===")
            sum_remote_timeouts(c, skip_first=30, skip_last=30, log_suffix="Jacob", suffix=f"raft_{i}")
            sum_remote_detect(c, skip_first=30, skip_last=30, log_suffix=f"{i}")

# invoke test-petition --leaderId 3 --serverPort 10083 --value 5
@task
def test_petition(c, leaderId, serverPort, value):
    replica_ip = nodes[3]["host"]
    print(f"[{replica_ip}] adding delay")
    conn = Connection(host=replica_ip, user=username, port=nodes[3]["port"])
    cmd = f"sudo tc qdisc del dev enp65s0f0np0 root || true ; sudo tc qdisc add dev enp65s0f0np0 root netem delay 0.5ms"
    conn.run(cmd, warn=True)
    
    start_remote_default(c)
    
    # -------------------------------------------------
    # 0.  Convenience data
    # -------------------------------------------------
    sendMode = "maxcap"
    bind_ips   = ["10.0.0.2", "10.0.0.3", "10.0.4.2", "10.0.1.2", "10.0.1.3"]
    serverIp   = bind_ips[int(leaderId)]
    client_ids = [random.randint(1, 9999) for _ in range(5)]

    # -------------------------------------------------
    # 1.  Start clients
    # -------------------------------------------------
    for replica_id, node in enumerate(nodes[:5]):
        replica_ip = node["host"]
        print(f"[{replica_ip}] launching client")
        try:
            conn = Connection(host=replica_ip, user=username, port=node["port"])
            conn.sudo("killall client", warn=True)
            cmd = (
                f"cd {REMOTE_BASE} && "
                f"nohup {BIN_CLIENT} {serverIp} {serverPort} {sendMode} {value} "
                f"{client_ids[replica_id]} {bind_ips[replica_id]} "
                f"> client_remote.log 2>&1 &"
            )
            conn.run(cmd, pty=False, asynchronous=True)
        except Exception as e:
            print(f"‼️  start failed on {replica_ip}: {e}")
    
    
    
    # -------------------------------------------------
    # Inject Delay
    # ------------------------------------------------- 
    sleep(30)

    print("Injecting delay...!!!")
    replica_ip = nodes[3]["host"]
    print(f"[{replica_ip}] adding delay")
    conn = Connection(host=replica_ip, user=username, port=nodes[3]["port"])
    cmd = f"sudo tc qdisc del dev enp65s0f0np0 root || true ; sudo tc qdisc add dev enp65s0f0np0 root netem delay 8ms"
    conn.run(cmd, warn=True)
    cmd_check = "sudo tc qdis show dev enp65s0f0np0"
    conn.run(cmd_check, warn=True)
    
    sleep(140)
    
    # -------------------------------------------------
    
    for node in nodes[:5]:
        replica_ip = node["host"]
        try:
            Connection(host=replica_ip, user=username, port=node["port"]).sudo(
                "killall client leader_election", pty=False, asynchronous=True
            )
        except Exception as e:
            print(f"‼️  kill failed on {replica_ip}: {e}")

    # -------------------------------------------------
    # 3.  Run remote_thp_summary.py on each node
    # -------------------------------------------------
    for node in nodes[:5]:
        replica_ip = node["host"]
        try:
            conn = Connection(host=replica_ip, user=username, port=node["port"])
            cmd = (
                f"cd {REMOTE_BASE} && "
                f"python3 {REMOTE_THP} client_remote.log --out thp_summary.csv"
            )
            conn.run(cmd, hide="stdout")
        except Exception as e:
            print(f"‼️  summary generation failed on {replica_ip}: {e}")

    # -------------------------------------------------
    # 4.  Pull logs & CSVs back to workstation
    # -------------------------------------------------
    for replica_id, node in enumerate(nodes[:5]):
        replica_ip = node["host"]
        try:
            conn = Connection(host=replica_ip, user=username, port=node["port"])
            # conn.get(f"{REMOTE_BASE}/client_remote.log",
            #          local=f"client_remote_{replica_id}.log")
            conn.get(f"/users/PeterYao/frugal-leader-election/thp_summary.csv",
                     local=f"thp_{replica_id}.csv")
        except Exception as e:
            print(f"‼️  download failed from {replica_ip}: {e}")

    # -------------------------------------------------
    # 5.  Merge summaries locally
    # -------------------------------------------------
    csv_files = sorted(glob.glob("thp_*.csv"))
    if csv_files:
        try:
            subprocess.run(
                ["python3", LOCAL_MERGE, *csv_files,
                 "--plot", "combined_throughput.png",
                 "--csv",  "combined_throughput.csv"],
                check=True)
            print("✅ merged plot generated: combined_throughput.png")
        except subprocess.CalledProcessError as e:
            print(f"‼️  merge script failed: {e}")

    # -------------------------------------------------
    # 6.  Archive everything (logs, thp CSVs, and merged outputs)
    # -------------------------------------------------
    ts_folder = datetime.now().strftime(f"petition_%Y%m%d_%H%M%S")
    os.makedirs(ts_folder, exist_ok=True)

    # move client logs and per-node CSVs
    for f in glob.glob("client_remote_*.log") + glob.glob("thp_*.csv"):
        try:
            shutil.move(f, os.path.join(ts_folder, f))
        except Exception as e:
            print(f"‼️  archiving {f} failed: {e}")

    # move the combined plot and CSV if they exist
    for fname in ("combined_throughput.png", "combined_throughput.csv"):
        if os.path.exists(fname):
            try:
                shutil.move(fname, os.path.join(ts_folder, fname))
            except Exception as e:
                print(f"‼️  moving {fname} to archive failed: {e}")

    print(f"📦  archived logs, CSVs, and merged outputs → {ts_folder}")
    
    
    
       
    