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

# Define the ports and peers
PORTS = [5000, 5001, 5002, 5003]
IP = "127.0.0.1"

# Dictionary to store process PIDs
processes = {}

# Define node connection details

# nodes = [
#     {"host": "c220g5-111004.wisc.cloudlab.us", "port": 32410},
#     {"host": "c220g5-111012.wisc.cloudlab.us", "port": 32410},
#     {"host": "c220g5-111004.wisc.cloudlab.us", "port": 32411},
#     {"host": "c220g5-111004.wisc.cloudlab.us", "port": 32412},
#     {"host": "c220g5-111012.wisc.cloudlab.us", "port": 32411},
# ]

nodes = [
    {"host": "pc532.emulab.net", "port": 22},
    {"host": "pc417.emulab.net", "port": 22},
    {"host": "pc559.emulab.net", "port": 22},
    {"host": "pc509.emulab.net", "port": 22},
    {"host": "pc545.emulab.net", "port": 22},
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
            
            cmd = f"cd frugal-leader-election && nohup {binary_path} --config={remote_config_path} --replicaId={replica_id} > scripts/logs/node_{replica_id + 1}.log 2>&1 &"
            print(cmd)
            conn.run(cmd, pty=False, asynchronous=True)

            print(f"Replica {replica_id+1} started on {replica_ip}, logging to ./logs/node_{replica_id+1}.log")
        except Exception as e:
            print(f"Failed to start replica {replica_id+1} on {replica_ip}: {e}")
            continue

    print("All remote nodes have been started.")
    print("Logs are available in the 'logs/' directory on each respective node.")


# invoke start-client --serverIp 127.0.0.4 --serverPort 7899 --value 0.5
@task
def start_client(c, serverIp, serverPort, value):
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
    cmd = [binary_path, serverIp, str(serverPort), sendMode, value, "778"]
    
    # Create logs directory if it doesn't exist
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    log_file = logs_dir / "client.log"
    
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

# invoke start-client-remote --remoteHostId 1 --serverIp 10.0.0.3 --serverPort 6772 --value 5
# ./bazel-bin/client 10.0.0.3 6114 maxcap 5 789 > client_nochange.log 2>&1
@task
def start_client_remote(c, remoteHostId, serverIp, serverPort, value, logSuffix=""):
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
    cmd = f"cd frugal-leader-election && nohup {binary_path} {serverIp} {serverPort} {sendMode} {value} 123 > client_remote.log 2>&1 &"
    
    remote_host = nodes[int(remoteHostId)]["host"]    

    print(f"Starting remote client on {remote_host} with command: {cmd}")
    
    try:
        # Connect to the remote node (using default SSH port 22)
        conn = Connection(host=remote_host, user=username, port=22)
        # Run the command asynchronously; pty is set to False to avoid allocation of a pseudo-terminal.
        conn.run(cmd, pty=False, asynchronous=True)
        print(f"Remote client started on {remote_host}, logging to client_remote.log")
        sleep(90)
        conn.run("killall client", warn=True)
        # conn.get("frugal-leader-election/client_remote.log", local=f"client_remote_{logSuffix}.log")
        
    except Exception as e:
        print(f"Failed to start remote client on {remote_host}: {e}")


# invoke start-client-remote --remoteHostId 1 --serverIp 10.0.0.3 --serverPort 6788 --value 5
@task
def start_clients_remote(c, remoteHostId, serverIp, serverPort, value, logSuffix=""):
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
    cmd = f"cd frugal-leader-election && nohup {binary_path} {serverIp} {serverPort} {sendMode} {value} {str(client_ids[i-1])} > client_remote.log 2>&1 &"
    
    remote_host = nodes[int(remoteHostId)]["host"]    

    print(f"Starting remote client on {remote_host} with command: {cmd}")
    

    client_id_one = 123
    client_id_two = 456
    client_id_three = 789
    client_id_four = 1011
    client_ids = [client_id_one, client_id_two, client_id_three, client_id_four]
    # client_ids = [client_id_one, client_id_two]
    
    conn = Connection(host=remote_host, user=username, port=22)
    
    # Loop to start two clients.
    for i in range(1, 5):
        try:
            conn.run(cmd, pty=False, asynchronous=True)
            
        except Exception as e:
            print(f"Failed to start client {i}: {e}")
    
    try:
        # Connect to the remote node (using default SSH port 22)
        conn = Connection(host=remote_host, user=username, port=22)
        # Run the command asynchronously; pty is set to False to avoid allocation of a pseudo-terminal.
        conn.run(cmd, pty=False, asynchronous=True)
        print(f"Remote client started on {remote_host}, logging to client_remote.log")
        sleep(90)
        conn.run("killall client", warn=True)
        conn.get("frugal-leader-election/client_remote.log", local=f"client_remote_{logSuffix}.log")
        
    except Exception as e:
        print(f"Failed to start remote client on {remote_host}: {e}")
        
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
        # cmd = [binary_path, f"--config={config_path}", f"--replicaId={replica_id}", "--minloglevel=1"]
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
