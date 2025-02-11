# the command to check that zookeeper is running correctly on the remote:
# ./zkServer.sh status

from fabric import Connection, Config, ThreadingGroup
from time import sleep

# List of nodes (replace with actual hostnames or IPs)
nodes = [
    "PeterYao@c220g1-031111.wisc.cloudlab.us",
    "PeterYao@c220g1-031117.wisc.cloudlab.us",
    "PeterYao@c220g1-031130.wisc.cloudlab.us",
    "PeterYao@c220g1-031119.wisc.cloudlab.us",
    "PeterYao@c220g1-031105.wisc.cloudlab.us",
]

nodes_id_correspondence = [0, 2, 1, 3, 4]


def get_leader(group):
    leader_conn = None
    for id, conn in enumerate(group):
        node_id = nodes_id_correspondence[id]
        result = conn.run("/users/PeterYao/apache-zookeeper-3.8.4-bin/bin/zkServer.sh status", hide=True)
        if "leader" in result.stdout:
            print(f"Leader found: Node {node_id} is the current leader in the ZK ensemble")
            leader_conn = conn
        elif "follower" in result.stdout:
            print(f"Node {node_id} is the follower")
    return leader_conn


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
    # for connection in group:
    #     connection.run("sudo apt update && sudo apt install -y default-jdk && java -version")
    #     download_zookeeper(connection)
    #     upload_zoo_cfg(connection)   
    # create_my_id(group)     
    # kill_running_zk(group)
    # start_zookeeper_server(group)
    # check_leader_node(group)
    # start_zk_ensemble_with_designated_leader(group, 0)
    get_leader(group)
