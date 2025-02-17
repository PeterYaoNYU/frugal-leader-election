# the command to check that zookeeper is running correctly on the remote:
# ./zkServer.sh status

from fabric import Connection, Config, ThreadingGroup
from time import sleep
import yaml
from ycsb_analysis import *

# List of nodes (replace with actual hostnames or IPs)
nodes = [
    "PeterYao@c220g1-031111.wisc.cloudlab.us",
    "PeterYao@c220g1-031117.wisc.cloudlab.us",
    "PeterYao@c220g1-031130.wisc.cloudlab.us",
    "PeterYao@c220g1-031119.wisc.cloudlab.us",
    "PeterYao@c220g1-031105.wisc.cloudlab.us",
]

nodes_id_correspondence = [0, 2, 1, 3, 4]

connections = {}

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
                conn.run("sudo apt update && sudo apt install -y maven", hide=True)
            conn.run("git clone http://github.com/brianfrankcooper/YCSB.git", hide=True)
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
    
    
def run_ycsb_workload_from_node(client_node_id, server_node_id, output_file_name="zkProfile.txt", contact_leader=True):
    # load the yaml file:
    with open("nodes.yaml", 'r') as f:
        data = yaml.safe_load(f)
    if contact_leader:
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
        # run the ycsb workload on the leader node
        ycsb_command = f'''
            cd ~/YCSB
            ./bin/ycsb run zookeeper -threads 1 -P workloads/workloadb \
            -p zookeeper.connectString={leader_zk_connection_ip}:2181/benchmark \
            -p readproportion=0.1 -p updateproportion=0.9 \
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
            ./bin/ycsb run zookeeper -threads 1 -P workloads/workloadb \
            -p zookeeper.connectString={server_zk_connection_ip}:2181/benchmark \
            -p readproportion=0.1 -p updateproportion=0.9 \
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
        conn.sudo("~/apache-zookeeper-3.8.4-bin/bin/zkServer.sh stop", hide=True)
        print(f"Node {node_id} killed")
    except Exception as e:
        print(f"Error killing node {node_id}: {e}")
        
def start_node(node_id):
    conn = connections.get(node_id)
    if conn is None:
        print(f"Node {node_id} not found in connections.")
        return
    try:
        conn.sudo("~/apache-zookeeper-3.8.4-bin/bin/zkServer.sh start", hide=True)
        print(f"Node {node_id} started")
    except Exception as e:
        print(f"Error starting node {node_id}: {e}")
        


# return the current leader node id along with the connection itself.
def get_leader(group):
    leader_conn = None
    leader_node_id = None
    for id, conn in enumerate(group):
        node_id = nodes_id_correspondence[id]
        result = conn.run("/users/PeterYao/apache-zookeeper-3.8.4-bin/bin/zkServer.sh status", hide=True)
        if "leader" in result.stdout:
            print(f"Leader found: Node {node_id} is the current leader in the ZK ensemble")
            leader_conn = conn
            leader_node_id = node_id
        elif "follower" in result.stdout:
            print(f"Node {node_id} is the follower")
    return leader_node_id, leader_conn


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
            conn.sudo("~/apache-zookeeper-3.8.4-bin/bin/zkServer.sh stop", hide=True)
            # Force-kill any remaining process (if needed)
            conn.sudo("pkill -f QuorumPeerMain", warn=True, hide=True)
            print(f"Zookeeper process killed on {conn.host}")
        except Exception as e:
            print(f"Error killing Zookeeper process on {conn.host}: {e}")

def start_zookeeper_server(group):
    for conn in (list(group)):
        try:
            conn.sudo("~/apache-zookeeper-3.8.4-bin/bin/zkServer.sh start", hide=True)
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

def create_my_id(group):
    for id, conn in enumerate(group):
        # conn.sudo("mkdir -p /var/lib/zookeeper", hide=True)
        # conn.sudo("touch /var/lib/zookeeper/myid", hide=True)
        conn.run("mkdir -p /users/PeterYao/apache-zookeeper-3.8.4-bin/data", hide=True)
        myid= nodes_id_correspondence[id] + 1
        conn.run(f"echo {myid} | sudo tee /users/PeterYao/apache-zookeeper-3.8.4-bin/data/myid", hide=True)
        print(f"myid file created on {conn}")
        

def upload_zoo_cfg(conn):
    try:
        conn.put("zoo.cfg", "apache-zookeeper-3.8.4-bin/conf/zoo.cfg")
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

# Execute setup on all nodes concurrently
if __name__ == "__main__":
    group = ThreadingGroup(*nodes)
    load_connections("nodes.yaml")
    # setup_ycsb([1, 2, 3, 4])
    # for connection in group:
    #     connection.run("sudo apt update && sudo apt install -y default-jdk && java -version")
    #     download_zookeeper(connection)
    #     upload_zoo_cfg(connection)   
    # create_my_id(group)     
    # kill_running_zk(group)
    # start_zookeeper_server(group)
    # start_zk_ensemble_with_designated_leader(group, 0)
    # get_leader(group)
    # run_ycsb_workload_from_node(1, 1, "zkProfile13.txt", contact_leader=False)
    
    # kill_leader_then_reinstatiate()
    kill_node(3)
    kill_node(2)   
    kill_node(4) 
    sleep(10)
    start_node(3)
    start_node(2)
    start_node(4)
    
    get_leader(group)
    # plot_ycsb_profile("zkProfile13.txt")
    # lat = [1, 2, 4, 6, 8]
    # for i in range(5):
    #     vary_link_latency(4, "enp129s0f0", lat[i] , 1, "pareto")
    #     run_ycsb_workload_from_node(4, 4, f"zk_different_rack_lat_{lat[i]}ms.txt", contact_leader=True)
    #     plot_ycsb_profile(f"zk_client_{i}_to_server.txt")
