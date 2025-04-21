# the command to check that zookeeper is running correctly on the remote:
# ./zkServer.sh status

from fabric import Connection, Config, ThreadingGroup
from time import sleep
import yaml
from ycsb_analysis import *
from delay_setup.delay_setup_asymmetric_topo import *

import threading
from fabric import ThreadingGroup

from datetime import datetime
from zoneinfo import ZoneInfo
import re
import matplotlib.pyplot as plt

# List of nodes (replace with actual hostnames or IPs)
nodes = [
    "PeterYao@c220g1-031111.wisc.cloudlab.us",
    "PeterYao@c220g1-031117.wisc.cloudlab.us",
    "PeterYao@c220g1-031130.wisc.cloudlab.us",
    "PeterYao@c220g1-031119.wisc.cloudlab.us",
    "PeterYao@c220g1-031105.wisc.cloudlab.us",
]

yaml_file_name = "fattree_physical.yaml"

nodes_id_correspondence = [0, 2, 1, 3, 4]

connections = {}

switch_info = []


def get_london_time():
    """Return the current time in London time zone."""
    return datetime.now(ZoneInfo("Europe/London"))

def download_zookeeper_log(leader_node_id, conn):
    """
    Download the Zookeeper log file from the remote node.
    Assumes the log is in /users/PeterYao/zookeeper/logs and that the file name starts with 'zookeeper-root-server-node-<leader>'.
    """
    remote_dir = "/users/PeterYao/zookeeper/logs/"
    # Construct the expected filename.
    file_name = f"zookeeper-root-server-node-{leader_node_id}.quorum.nyunetworks.emulab.net.out"
    remote_file = remote_dir + file_name
    local_file = file_name  # Save under the same name locally.
    try:
        conn.get(remote_file, local_file)
        print(f"Downloaded log file: {remote_file} -> {local_file}")
    except Exception as e:
        print(f"Error downloading log file {remote_file} from node {leader_node_id}: {e}")
    return local_file

def parse_zookeeper_log(log_file, start_time, end_time):
    """
    Parse the given log file and count the occurrence of each node in the quorum.
    Only lines with "All quorums present in synced leader tracker:" between start_time and end_time are considered.
    """
    counts = {i: 0 for i in range(1, 6)}  # nodes 1 to 5
    time_format = "%Y-%m-%d %H:%M:%S,%f"
    with open(log_file, 'r') as f:
        for line in f:
            if "All quorums present in synced leader tracker:" in line:
                # Get timestamp from beginning of the line.
                tokens = line.split()
                if len(tokens) < 2:
                    continue
                timestamp_str = tokens[0] + " " + tokens[1]
                try:
                    # line_time = datetime.strptime(timestamp_str, time_format)
                    line_time = datetime.strptime(timestamp_str, time_format).replace(tzinfo=ZoneInfo("Europe/London"))
                except Exception as e:
                    print(f"Error parsing timestamp '{timestamp_str}': {e}")
                    continue
                # Only consider lines within the experiment window.
                if start_time <= line_time <= end_time:
                    m = re.search(r"\[([0-9,\s]+)\]", line)
                    if m:
                        quorum_str = m.group(1)
                        quorum_list = [int(x) for x in quorum_str.split(",") if x.strip().isdigit()]
                        for node in quorum_list:
                            if node in counts:
                                counts[node] += 1
    return counts

def plot_quorum_counts(counts, experiment_info):
    """
    Plot a bar chart (nodes 1 to 5) of the counts.
    """
    nodes = sorted(counts.keys())
    freq = [counts[node] for node in nodes]
    plt.figure()
    plt.bar(nodes, freq)
    plt.xlabel("Node")
    plt.ylabel("Count")
    plt.title(f"Quorum Counts for {experiment_info}")
    plt.xticks(nodes)
    # plt.show()
    plt.savefig(f"quorum_counts_{experiment_info}.png")
    
    
def varying_leader_quorum_exp():
    """
    For each leader:
      1. Run all experiments (recording the London start and end time for each).
      2. Download the zookeeper log file from the leader only once.
      3. For each experiment, parse the log (only considering lines between the recorded start and end time) to count quorum appearances.
      4. Plot the resulting bar chart.
    """
    experiment_logs = {}  # Dictionary to store experiments per leader.
    for node_id in [1, 2, 3]:
        clear_all_switch_weights()
        designate_leader(node_id, [0, 1, 2, 3, 4])
        base_delay = 0
        leader_experiments = []  # To hold experiment info tuples: (experiment_key, start_time, end_time)
        
        for lat in [0.5, 1.0, 1.5, 2.0]:
            if lat != 0:
                setup_delay_fat_tree(lat)
            thd_cnt = 20
            for j in range(0, 3):
                experiment_key = (node_id, lat, j)
                start_time = get_london_time()
                print(f"Starting experiment {experiment_key} at {start_time}")
                
                # Run the YCSB workload experiment.
                run_ycsb_workload_from_node(
                    0, 0,
                    f"zk_leader_node{node_id}_{lat}ms_{thd_cnt}threads_base_delay_{base_delay}_ms_run{j}_quorum.txt",
                    contact_leader=True, threads_count=thd_cnt, num_operations=10000, read_ratio=0.1
                )
                
                end_time = get_london_time()
                print(f"Finished experiment {experiment_key} at {end_time}")
                leader_experiments.append((experiment_key, start_time, end_time))
        
        # Save all experiments for this leader.
        experiment_logs[node_id] = leader_experiments
        
        # Download the log file from the leader once.
        leader_conn = connections.get(node_id)
        if leader_conn is None:
            print(f"Leader connection for node {node_id} not found.")
            continue
        log_file = download_zookeeper_log(node_id, leader_conn)
        
        # For each experiment, parse the log file and plot the quorum counts.
        for exp_info in leader_experiments:
            experiment_key, start_time, end_time = exp_info
            counts = parse_zookeeper_log(log_file, start_time, end_time)
            experiment_info = f"Leader {node_id}, latency {experiment_key[1]}ms, run {experiment_key[2]}"
            plot_quorum_counts(counts, experiment_info)
                
    print("Experiment logs:", experiment_logs)


def load_connections(yaml_file):
    with open(yaml_file, 'r') as f:
        data = yaml.safe_load(f)

    # print(data)
    
    for node in data.get("nodes", []):
        node_id = node["id"]    
        conn_str = node["connection"]
        port = node.get("port", 22)
        if "@" in conn_str:
            user, host = conn_str.split("@", 1)
        else:
            user = None
            host = conn_str
        
        if user:
            conn = Connection(host=host, user=user, port=port)
        else:
            conn = Connection(host=host, port=port)
        connections[node_id] = conn
    print(connections)
    
    switches = data.get("switches", [])
    for switch in switches:
        info = {
            'id': switch.get('id'),
            # 'connection': switch.get('connection'),
            'connection': Connection(host=switch.get('connection')),
            'interfaces': switch.get('interfaces', {})
        }
        switch_info.append(info)
    
    return connections

# setup ycsb on the specified node
def setup_ycsb(node_id_list, install_maven=True):
    for node_id in node_id_list:
        try:
            conn = connections.get(node_id)
            if conn is None:
                print(f"Node {node_id} not found in connections.")
                return
            if install_maven:
                conn.run("sudo apt update && sudo apt install -y maven")
            conn.run("git clone http://github.com/brianfrankcooper/YCSB.git")
            conn.run("cd YCSB && mvn -pl site.ycsb:zookeeper-binding -am clean package -DskipTests", hide=True)
            
            print(f"YCSB setup completed on Node {node_id}")
        except Exception as e:
            print(f"Failed to setup YCSB on Node {node_id}: {e}")
            
            
def vary_link_latency(node_id, interface_name, mean_delay, std_dev, dist_name):
    conn = connections.get(node_id)
    if conn is None:
        print(f"Node {node_id} not found in connections.")
        return
    try:
        delete_command = f"sudo tc qdisc del dev {interface_name} root || true"
        conn.run(delete_command)
        add_command = f"sudo tc qdisc add dev {interface_name} root netem delay {mean_delay}ms {std_dev}ms distribution {dist_name}"
        conn.run(add_command)
        print(f"Delay added to {interface_name} on Node {node_id} with mean {mean_delay}ms and std_dev {std_dev}ms, following {dist_name} distribution")
    except Exception as e:
        print(f"Error adding delay to {interface_name} on Node {node_id}: {e}")
    
    
def run_ycsb_workload_from_node(client_node_id, server_node_id, output_file_name="zkProfile.txt", contact_leader=True, threads_count=3, num_operations=5000, read_ratio=0.1):
    # load the yaml file:
    # read ratio default to 0.1, write ratio is implicit: 1-read_ratio
    write_ratio = 1 - read_ratio
    with open(yaml_file_name, 'r') as f:
        data = yaml.safe_load(f)
    if contact_leader:
        # this means that both the client and the ZK server is ont he leadeer node, basically we neglect client_node_id and server_node_id in this case
        leader_node_id, conn = get_leader(connections)
        if leader_node_id is None:
            print("No leader found in the ZK ensemble")
            return
        # instantiate the zookeeper test on the leader.
        # first get the leader ip address running zookeeper from the yaml file:
        for node in data.get("nodes", []):
            if node["id"] == leader_node_id:
                leader_zk_connection_ip = node["zk_ip_addr"]
                break               
        # run the ycsb workload on the leader node
        ycsb_command = f'''
            cd ~/YCSB
            ./bin/ycsb run zookeeper -threads {threads_count} -P workloads/workloadb \
            -p zookeeper.connectString={leader_zk_connection_ip}:2181/benchmark \
            -p readproportion={read_ratio} -p updateproportion={write_ratio} \
            -p operationcount={num_operations} \
            -p hdrhistogram.percentiles=10,25,50,75,90,95,99,99.5 \
            -p histogram.buckets=500 > {output_file_name}
        '''
        conn.run(ycsb_command)
        # download the file from the remote node to local for analysis:
        remote_path = f"/users/PeterYao/YCSB/{output_file_name}"
        try:
            conn.get(remote_path, output_file_name)
        except Exception as e:
            print(f"Failed to download {output_file_name} from Node {leader_node_id}: {e}")
    elif not contact_leader:
        # get the connection for the client and server of zookeeper respectively
        client_conn = connections.get(client_node_id)
        server_conn = connections.get(server_node_id)
        
        # get the server address of the zookeeper from the yaml file
        for node in data.get("nodes", []):
            if node["id"] == server_node_id:
                server_zk_connection_ip = node["zk_ip_addr"]
        
        # after loading the connection, check if the connection is valid, if not, warn and return
        if client_conn is None or server_conn is None:
            print(f"Node {client_node_id} or {server_node_id} not found in connections.")
            return
        # if the ip addresses are valid, then run the ycsb workload on the client node
        ycsb_command = f'''
            cd ~/YCSB
            ./bin/ycsb run zookeeper -threads {threads_count} -P workloads/workloadb \
            -p zookeeper.connectString={leader_zk_connection_ip}:2181/benchmark \
            -p readproportion=0.2 -p updateproportion=0.8 \
            -p insertorder=HASHED -p requestdistribution=uniform \
            -p operationcount={num_operations} \
            -p hdrhistogram.percentiles=10,25,50,75,90,95,99,99.5 \
            -p histogram.buckets=500 > {output_file_name}
        '''
        
        client_conn.run(ycsb_command)
        # download the file from the remote node to local for analysis:
        remote_path = f"/users/PeterYao/YCSB/{output_file_name}"
        try:
            client_conn.get(remote_path, output_file_name)
        except Exception as e:
            print(f"Failed to download {output_file_name} from Node {client_node_id}: {e}")
    print(f"YCSB workload completed, saved to {output_file_name}")
        

# kill the current leader and reinstantiate the node after a while, so that a new leader will be selected
# by the ZK ensemble. 
def kill_leader_then_reinstatiate():
    leader_node_id, conn = get_leader(group)
    seq = nodes_id_correspondence.index(leader_node_id)
    leader_conn = group[seq]
    try:
        leader_conn.sudo("~/apache-zookeeper-3.8.4-bin/bin/zkServer.sh stop", hide=True)
        print(f"Leader node {leader_node_id} killed")
        sleep(4)
        leader_conn.sudo("~/apache-zookeeper-3.8.4-bin/bin/zkServer.sh start", hide=True)
        print(f"Leader node {leader_node_id} reinstated")
        leader_node_id, conn = get_leader(group) 
        print(f"New leader is now node {leader_node_id}")
    except Exception as e:
        print(f"Error killing/reinstating leader node {leader_node_id}: {e}")
            
def kill_node(node_id):
    conn = connections.get(node_id)
    if conn is None:
        print(f"Node {node_id} not found in connections.")
        return
    try:
        # conn.sudo("~/apache-zookeeper-3.8.4-bin/bin/zkServer.sh stop", hide=True)
        conn.sudo("~/zookeeper/bin/zkServer.sh stop", hide=True)
        
        print(f"Node {node_id} killed")
    except Exception as e:
        print(f"Error killing node {node_id}: {e}")
        
def start_node(node_id):
    conn = connections.get(node_id)
    if conn is None:
        print(f"Node {node_id} not found in connections.")
        return
    try:
        # conn.sudo("~/apache-zookeeper-3.8.4-bin/bin/zkServer.sh start", hide=True)
        conn.sudo("~/zookeeper/bin/zkServer.sh start", hide=True)
        
        print(f"Node {node_id} started")
    except Exception as e:
        print(f"Error starting node {node_id}: {e}")
        


# return the current leader node id along with the connection itself.
def get_leader(group):
    leader_conn = None
    leader_node_id = None
    for id, conn in connections.items():
        node_id = id
        try:
            
            result = conn.run("/users/PeterYao/zookeeper/bin/zkServer.sh status", hide=True)
            # result = conn.run("/users/PeterYao/apache-zookeeper-3.8.4-bin/bin/zkServer.sh status", hide=True)
        except Exception as e:
            print(f"Error checking Zookeeper process stauts on {conn.host}: {e}")
            continue
        if "leader" in result.stdout:
            print(f"Leader found: Node {node_id} is the current leader in the ZK ensemble")
            leader_conn = conn
            leader_node_id = node_id
        elif "follower" in result.stdout:
            print(f"Node {node_id} is the follower")
    return leader_node_id, leader_conn


# designate node_id as the leader of the ZK ensemble
def designate_leader(node_id, node_id_list):
    # get the current leader:
    leader_node_id, leader_conn = get_leader(connections)
    # do not stop the while loop until the current leader is the 
    while (leader_node_id != node_id):
        # kill the other nodes, and sleep, and then restart. 
        temp_node_list = node_id_list.copy()
        temp_node_list.remove(node_id)
        for node in temp_node_list:
            try:
                kill_node(node)
            except Exception as e:
                print(f"Error killing node {node}, maybe already killed: {e}")
        sleep(25)
        for node in temp_node_list:
            start_node(node)
        leader_node_id, leader_conn = get_leader(connections)
    print(f"Node {node_id} is now the leader of the ZK ensemble")
    
# comprehensive experiment. 
# once we have designated a leader, need to run a comprehensive set of experiments, 
# varying the  read-write ratio, and the latency of each individual link.
def comprehensive_exp(latency_mean, latencystd_dev, dist_name, client_node, server_node, run_from_leader=True):
    # 1. setup the latency on all the links. 
    add_delay_to_all_nodes(latency_mean, latencystd_dev, dist_name, connections)
    print("[INFO] done adding delay to all nodes!")
    # load the yaml file:
    with open("nodes.yaml", 'r') as f:
        data = yaml.safe_load(f)
    # 2. run comprehensive experiments, vary the read-write ratio
    if not run_from_leader:
        print("not supported: run_from_leader=False")
    for i in range(1, 10):
        if run_from_leader:
            # this means that both the client and the ZK server is ont he leadeer node, basically we neglect client_node_id and server_node_id in this case
            leader_node_id, conn = get_leader(group)
            if leader_node_id is None:
                print("No leader found in the ZK ensemble")
                return
            # instantiate the zookeeper test on the leader.
            # first get the leader ip address running zookeeper from the yaml file:
            for node in data.get("nodes", []):
                if node["id"] == leader_node_id:
                    leader_zk_connection_ip = node["zk_ip_addr"]
                    break   
            read_ratio = 0.1 * i
            write_ratio = 1.0 - read_ratio
            output_file_name = f"zk_lat_leader_node{leader_node_id}_{latency_mean}_{latencystd_dev}_{dist_name}_read_{read_ratio:.1f}_write_{write_ratio:.1f}.txt"
            # run the ycsb workload on the leader node
            ycsb_command = f'''
                cd ~/YCSB
                ./bin/ycsb run zookeeper -threads 1 -P workloads/workloadb \
                -p zookeeper.connectString={leader_zk_connection_ip}:2181/benchmark \
                -p readproportion={read_ratio} -p updateproportion={write_ratio} \
                -p operationcount=1000000 \
                -p hdrhistogram.percentiles=10,25,50,75,90,95,99,99.5 \
                -p histogram.buckets=500 > {output_file_name}
            '''
            conn.run(ycsb_command)
            conn.get(f"/users/PeterYao/YCSB/{output_file_name}", output_file_name)
        else:
            pass
        
        
def varying_thread_count_exp(learder_id, latency):
    clear_all_switch_weights()
    designate_leader(learder_id, [0, 1, 2, 3, 4])
    if latency != 0:
        setup_delay_fat_tree(latency)
    for thd_cnt in range(10, 28, 2):
        run_ycsb_workload_from_node(0, 0, f"zk_leader_node{learder_id}_{latency}ms_{thd_cnt}threads.txt", contact_leader=True, threads_count=thd_cnt, num_operations=5000)
        
        
def setup_delay_fat_tree(lat):
    # enfore a delay to all siwtches interfaces. 
    for switch in switch_info:
        switch_id = switch.get("id")
        switch_conn = switch.get("connection")
        if switch_conn is None:
            print(f"Switch {switch_id} not found in connections.")
        interface_info = switch.get("interfaces")
        print("switch id: ", switch_id)
        for interface in interface_info.keys():
            print("Interface name: ", interface)
            delete_command = f"sudo tc qdisc del dev {interface} root || true"
            if switch_id == 4:
                temp_lat = lat * 3
                add_command = (
                    f"sudo tc qdisc add dev {interface} root netem delay {temp_lat}ms"
                )
            else:
                add_command = (
                    f"sudo tc qdisc add dev {interface} root netem delay {lat}ms"
                )
            switch_conn.run(delete_command)
            switch_conn.run(add_command)
            print(f"Delay added to {interface} on Switch {switch_id} with {lat}ms")

def clear_all_switch_weights():
    for switch in switch_info:
        switch_id = switch.get("id")
        switch_conn = switch.get("connection")
        if switch_conn is None:
            print(f"Switch {switch_id} not found in connections.")
        interface_info = switch.get("interfaces")
        for interface in interface_info.keys():
            delete_command = f"sudo tc qdisc del dev {interface} root || true"
            switch_conn.run(delete_command)
            print(f"Delay removed from {interface} on Switch {switch_id}")

import numpy as np
def varying_leader_exp():
    # for i in range(5):
    #     designate_leader(i, [0, 1, 2, 3, 4])
    #     for lat in [7, 9]:
    #         comprehensive_exp(lat, 2, "pareto", i, i, run_from_leader=True)
    # designate_leader(4, [0, 1, 2, 3, 4])
    # for lat in range(8, 9):
    #     add_delay_to_node(4, lat, 1, "pareto", connections)
    #     for thd_cnt in range(18, 36, 2):
    #         run_ycsb_workload_from_node(4, 4, f"zk_leader_node4_{lat}ms_{thd_cnt}threads.txt", contact_leader=True, threads_count=thd_cnt, num_operations=3000)
    for node_id in [1]:
        clear_all_switch_weights()
        designate_leader(node_id, [0, 1, 2, 3, 4])
        base_delay = 0
        for lat in [0, 2.0]:
            if lat != 0:
                setup_delay_fat_tree(lat)
            thd_cnt = 20
            for j in range(0, 3):
                run_ycsb_workload_from_node(0, 0, f"zk_leader_node{node_id}_{lat}ms_{thd_cnt}threads_base_delay_{base_delay}_ms_run{j}_triple.txt", contact_leader=True, threads_count=thd_cnt, num_operations=10000, read_ratio=0.1)

def run_once(connections):
    get_leader(connections.values())
    run_ycsb_workload_from_node(1, 1, "logtest.txt", contact_leader=True, num_operations=5, read_ratio=0, threads_count=1)
    kill_running_zk(connections.values())

def varying_read_write_exp():
    # for i in range(5):
    #     designate_leader(i, [0, 1, 2, 3, 4])
    #     for lat in [7, 9]:
    #         comprehensive_exp(lat, 2, "pareto", i, i, run_from_leader=True)
    # designate_leader(4, [0, 1, 2, 3, 4])
    # for lat in range(8, 9):
    #     add_delay_to_node(4, lat, 1, "pareto", connections)
    #     for thd_cnt in range(18, 36, 2):
    #         run_ycsb_workload_from_node(4, 4, f"zk_leader_node4_{lat}ms_{thd_cnt}threads.txt", contact_leader=True, threads_count=thd_cnt, num_operations=3000)
    node_id = 4
    clear_all_weights()
    designate_leader(node_id, [0, 1, 2, 3, 4])
    base_delay = 0
    lat = 3
    if lat != 0:
        # add_delay_to_node(1, 2 * lat, 1, "constant", connections, interface_list=["enp6s0f1"])
        add_delay_to_node(4, lat, 1, "constant", connections)
        # add_delay_to_node(0, lat, 1, "constant", connections, interface_list=["enp129s0f1"])
    thd_cnt = 20
    # let j be the read ratio
    for j in np.arange(0.0, 1.1, 0.1):
        for run in range(0, 3):
            run_ycsb_workload_from_node(0, 0, f"zk_leader_node{node_id}_{lat}ms_{thd_cnt}threads_base_delay_{base_delay}_ms_read_ratio_{j:.1f}_run{run}.txt", contact_leader=True, threads_count=thd_cnt, num_operations=10000, read_ratio=j)


def check_leader_node(group):
    for conn in group:
        try:
            print(conn)
            conn.run("/users/PeterYao/apache-zookeeper-3.8.4-bin/bin/zkServer.sh status")
        except Exception as e:
            print(f"Error checking Zookeeper process stauts on {conn.host}: {e}")

def kill_running_zk(group):
    for conn in group:
        try:
            # Attempt a graceful stop
            # conn.sudo("~/apache-zookeeper-3.8.4-bin/bin/zkServer.sh stop", hide=True)
            conn.sudo("~/zookeeper/bin/zkServer.sh stop", hide=True)
            
            # Force-kill any remaining process (if needed)
            conn.sudo("pkill -f QuorumPeerMain", warn=True, hide=True)
            print(f"Zookeeper process killed on {conn.host}")
        except Exception as e:
            print(f"Error killing Zookeeper process on {conn.host}: {e}")

def start_zookeeper_server(group):
    for conn in (list(group)):
        try:
            # conn.run("sudo ~/apache-zookeeper-3.8.4-bin/bin/zkServer.sh start")
            conn.run("sudo ~/zookeeper/bin/zkServer.sh start")
            
            print(f"Zookeeper server started on {conn}")
        except Exception as e:
            print(f"Error starting Zookeeper server on {conn}: {e}")
            
def start_zk_ensemble_with_designated_leader(group, leader):
    group_list = list(group)
    idx = nodes_id_correspondence.index(leader)
    for i in range(len(group_list)):
        conn = group_list[(idx + i) % len(group_list)]
        print("Init ZK on ", conn)
        try:
            conn.sudo("~/apache-zookeeper-3.8.4-bin/bin/zkServer.sh start", hide=True)
            print(f"Zookeeper server started on {conn}")
            sleep(1)
        except Exception as e:
            print(f"Error starting Zookeeper server on {conn}: {e}")

def create_my_id(group_dict):
    for id, conn in group_dict.items():
        # conn.sudo("mkdir -p /var/lib/zookeeper", hide=True)
        # conn.sudo("touch /var/lib/zookeeper/myid", hide=True)
        # conn.run("mkdir -p /users/PeterYao/apache-zookeeper-3.8.4-bin/data", hide=True)
        conn.run("mkdir -p /users/PeterYao/zookeeper/data", hide=True)
        
        myid= id + 1
        # conn.run(f"echo {myid} | sudo tee /users/PeterYao/apache-zookeeper-3.8.4-bin/data/myid", hide=True)
        conn.run(f"echo {myid} | sudo tee /users/PeterYao/zookeeper/data/myid", hide=True)
        
        print(f"myid file created on {conn}")
        

def upload_zoo_cfg(conn):
    try:
        # conn.put("zoo.cfg", "apache-zookeeper-3.8.4-bin/conf/zoo.cfg")
        conn.put("zoo.cfg", "zookeeper/conf/zoo.cfg")
        
        print(f"zoo.cfg uploaded on {conn}")
    except Exception as e:
        print(f"Error uploading zoo.cfg on {conn}: {e}")

def download_zookeeper(conn):
    try:
        conn.run("wget https://dlcdn.apache.org/zookeeper/zookeeper-3.8.4/apache-zookeeper-3.8.4-bin.tar.gz", hide=True)
        conn.run("tar -xvf apache-zookeeper-3.8.4-bin.tar.gz", hide=True)
        conn.run("rm apache-zookeeper-3.8.4-bin.tar.gz", hide=True)
        print(f"Zookeeper downloaded on {conn}")
    except Exception as e:
        print(f"Error downloading Zookeeper on {conn}: {e}")
        
def download_zookeeper_github(conn):
    try:
        # conn.run("git clone https://github.com/PeterYaoNYU/zookeeper.git", hide=True)
        # conn.run("sudo apt update && sudo apt install openjdk-11-jdk -y")
        # conn.run("export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64")
        conn.run("export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64 && cd zookeeper && mvn clean install -DskipTests")
        print(f"Zookeeper downloaded on {conn}")
    except Exception as e:
        print(f"Error downloading Zookeeper on {conn}: {e}")

def install_zookeeper_parallel(connections):
    threads = []
    for conn in connections.values():
        t = threading.Thread(target=download_zookeeper_github, args=(conn,))
        t.start()
        threads.append(t)
    for t in threads:
        t.join()

# Function to set up Java
def setup_java(host):
    try:
        print(f"Setting up Java on {host}")
        conn = Connection(host)
        conn.run("sudo apt update", hide=True)
        conn.run("sudo apt install -y default-jdk", hide=True)
        conn.run("java -version", hide=False)
        print(f"Java setup completed on {host}")
    except Exception as e:
        print(f"Error setting up Java on {host}: {e}")
        
def upload_new_logback_xml(connections):
    for conn in connections.values():
        try:
            conn.put("logback.xml", "/users/PeterYao/apache-zookeeper-3.8.4-bin/conf")
            print(f"logback.xml uploaded on {conn}")
        except Exception as e:
            print(f"Error uploading logback.xml on {conn}: {e}")

# Execute setup on all nodes concurrently
if __name__ == "__main__":
    group = ThreadingGroup(*nodes)
    load_connections("fattree_physical.yaml")
    # upload_new_logback_xml(connections)
    # setup_ycsb([0, 1, 2, 3, 4])
    # install_zookeeper_parallel(connections)
    # for connection in connections.values():
    #     connection.run("sudo apt update && sudo apt install -y default-jdk && java -version")
    #     download_zookeeper(connection)
        # upload_zoo_cfg(connection)   
    # create_my_id(connections)     
    # kill_running_zk(connections.values())
    # start_zookeeper_server(connections.values())
    # check_leader_node(connections.values())
    # start_zk_ensemble_with_designated_leader(group, 0)
    # run_ycsb_workload_from_node(1, 1, "zkProfile13.txt", contact_leader=False)
    clear_all_switch_weights()
    # setup_delay_fat_tree(0.2)
    
    # kill_leader_then_reinstatiate()
    # designate_leader(1, [0, 1, 2, 3, 4])
    # get_leader(group)
    
    # comprehensive_exp(1, 1, "pareto", 0.1, 0.9)
    # varying_leader_exp()
    # varying_leader_quorum_exp()
    # run_once(connections)
    # varying_read_write_exp()
    
    # varying_thread_count_exp(1, 1)
    
    # plot_ycsb_profile("zkProfile13.txt")
    # lat = [1, 2, 4, 6, 8]
    # for i in range(5):
    #     vary_link_latency(4, "enp129s0f0", lat[i] , 1, "pareto")
    #     run_ycsb_workload_from_node(4, 4, f"zk_different_rack_lat_{lat[i]}ms.txt", contact_leader=True)
    #     plot_ycsb_profile(f"zk_client_{i}_to_server.txt")
