from fabric import Connection
import threading

# Define node connection details

# VERY IMPORTANT!
# the order should reeally match the ip list

nodes = [
    {"host": "amd128.utah.cloudlab.us", "port": 22},
    {"host": "amd141.utah.cloudlab.us", "port": 22},
    {"host": "amd147.utah.cloudlab.us", "port": 22},
    {"host": "amd139.utah.cloudlab.us", "port": 22},
    {"host": "amd158.utah.cloudlab.us", "port": 22},
]
# SSH username
username = "PeterYao"

# Git repository to clone
repo_url = "https://github.com/PeterYaoNYU/frugal-leader-election.git"

# Python script to run after cloning
target_script = "~/frugal-leader-election/scripts/background_tcp_simulation/tcp_sim.py"

def execute_on_node(node, id):
    try:
        # Establish SSH connection
        conn = Connection(host=node["host"], user=username, port=node["port"])
        
        # conn.run(f"rm -rf frugal-leader-election", hide=True)
        
        # Clone the repository
        # conn.run(f"git clone {repo_url}", hide=True)
        # print(f"Repository cloned on {node['host']}:{node['port']}")
        
        # Run the target Python script without waiting for it to finish
        conn.run(f"nohup python3 {target_script} {id} 7899 &", hide=False, warn=True, asynchronous=True)
        
        print(f"Script executed on {node['host']}:{node['port']}")
    except Exception as e:
        print(f"Failed on {node['host']}:{node['port']} - {e}")

# Start threads to connect to each node and perform the actions
threads = []
for id, node in enumerate(nodes):
    thread = threading.Thread(target=execute_on_node, args=(node, id+1,))
    thread.start()
    threads.append(thread)

# Wait for all threads to complete
for thread in threads:
    thread.join()

print("All tasks completed.")