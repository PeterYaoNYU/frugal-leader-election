from fabric import Connection
import threading

# Define node connection details
# nodes = [
#     {"host": "c240g5-110103.wisc.cloudlab.us", "port": 26010},
#     {"host": "c240g5-110103.wisc.cloudlab.us", "port": 26011},
#     {"host": "c240g5-110103.wisc.cloudlab.us", "port": 26012},
#     {"host": "c240g5-110103.wisc.cloudlab.us", "port": 26013},
#     {"host": "c240g5-110103.wisc.cloudlab.us", "port": 26014},
#     {"host": "c240g5-110103.wisc.cloudlab.us", "port": 26015},
# ]

nodes = [
    {"host": "c220g1-031113.wisc.cloudlab.us", "port": 22},
    {"host": "c220g1-031130.wisc.cloudlab.us", "port": 22},
    {"host": "c220g1-031108.wisc.cloudlab.us", "port": 22},
    {"host": "c220g1-031125.wisc.cloudlab.us", "port": 22},
    {"host": "c220g1-031129.wisc.cloudlab.us", "port": 22},
]

# nodes = [
#     {"host": "pc605.emulab.net", "port": 29442},
#     {"host": "pc604.emulab.net", "port": 29442},
#     {"host": "pc605.emulab.net", "port": 29443},
#     {"host": "pc606.emulab.net", "port": 29442},
#     {"host": "pc603.emulab.net", "port": 29442},
# ]

# SSH username
username = "PeterYao"

# Git repository to clone
repo_url = "https://github.com/PeterYaoNYU/frugal-leader-election.git"

# Python script to run after cloning
target_script = "~/frugal-leader-election/scripts/background_tcp_simulation/tcp_sim.py"

# Function to install Bazel on the node
def build_install_bazel(conn):
    try:
        # conn.run("sudo apt update && sudo apt install -y openjdk-11-jdk", hide=True)
        # Add Bazel Distribution URI and keys
        conn.run("sudo apt install apt-transport-https curl gnupg -y")
        conn.run("curl -fsSL https://bazel.build/bazel-release.pub.gpg | gpg --dearmor > bazel-archive-keyring.gpg")
        conn.run("sudo mv bazel-archive-keyring.gpg /usr/share/keyrings/bazel-archive-keyring.gpg")
        conn.run("echo 'deb [signed-by=/usr/share/keyrings/bazel-archive-keyring.gpg] https://storage.googleapis.com/bazel-apt stable jdk1.8' | sudo tee /etc/apt/sources.list.d/bazel.list")
        # Update and install Bazel
        conn.run("sudo apt update && sudo apt install -y bazel")
        # Confirm Bazel installation
        conn.run("bazel --version")
        print(f"Bazel installed successfully on {conn.host}:{conn.port}")
    except Exception as e:
        print(f"Failed to install Bazel on {conn.host}:{conn.port} - {e}")
    
    
# def execute_on_node(node, id, build_bazel=False, build_invoke=False, build_fabric=False):    
def execute_on_node(node, id, build_bazel=True, build_invoke=True, build_fabric=True):
    try:
        # Establish SSH connection
        conn = Connection(host=node["host"], user=username, port=node["port"])
        
        # Install Bazel on the node
        if build_bazel:
            build_install_bazel(conn)
            
        if build_invoke:
            conn.run("sudo apt install python3-invoke -y", warn=True)
            
        if build_fabric:
            conn.run("sudo apt install python3-pip -y", warn=True)
            conn.run("pip install fabric", warn=True)
            
        
        # conn.run(f"rm -rf frugal-leader-election", hide=True)
        
        # # Clone the repository
        conn.run(f"git clone {repo_url}", hide=True)
        # print(f"Repository cloned on {node['host']}:{node['port']}")
        
        conn.run(f"cd frugal-leader-election && git checkout main && git pull && bazel build //:leader_election")
        
        # conn.run("cd frugal-leader-election && git pull")

        
        print(f"Script executed on {node['host']}:{node['port']}")
    except Exception as e:
        print(f"Failed on {node['host']}:{node['port']} - {e}")

# Start threads to connect to each node and perform the actions
threads = []
for id, node in enumerate(nodes):
    thread = threading.Thread(target=execute_on_node, args=(node, id+1,))
    # thread = threading.Thread(target=build_install_bazel, args=(Connection(host=node["host"], user=username, port=node["port"]),))
    thread.start()
    threads.append(thread)

# Wait for all threads to complete
for thread in threads:
    thread.join()

print("All tasks completed.")