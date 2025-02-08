from fabric import Connection, Config, ThreadingGroup

# List of nodes (replace with actual hostnames or IPs)
nodes = [
    "PeterYao@c220g5-120103.wisc.cloudlab.us",
    "PeterYao@c220g5-120101.wisc.cloudlab.us",
    "PeterYao@c220g5-120102.wisc.cloudlab.us",
    "PeterYao@c220g5-120108.wisc.cloudlab.us",
    "PeterYao@c220g5-120104.wisc.cloudlab.us",
]

nodes_id_correspondence = [0, 2, 1, 3, 4]

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
    for conn in group:
        try:
            conn.sudo("~/apache-zookeeper-3.8.4-bin/bin/zkServer.sh start", hide=True)
            print(f"Zookeeper server started on {conn}")
        except Exception as e:
            print(f"Error starting Zookeeper server on {conn}: {e}")
    

def create_my_id(group):
    for id, conn in enumerate(group):
        # conn.sudo("mkdir -p /var/lib/zookeeper", hide=True)
        # conn.sudo("touch /var/lib/zookeeper/myid", hide=True)
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
    for connection in group:
    #     connection.run("sudo apt update && sudo apt install -y default-jdk && java -version")
    #     download_zookeeper(connection)
        upload_zoo_cfg(connection)   
    create_my_id(group)     
    kill_running_zk(group)
    start_zookeeper_server(group)
