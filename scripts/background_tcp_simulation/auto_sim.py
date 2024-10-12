from fabric import Connection
import threading

# Define node connection details
nodes = [
    # {"host": "ssh PeterYao@c220g2-011121.wisc.cloudlab.us", "port": 29210},
    {"host": "c220g2-011121.wisc.cloudlab.us", "port": 25611},
    {"host": "c220g2-011121.wisc.cloudlab.us", "port": 25612},
    {"host": "c220g2-011121.wisc.cloudlab.us", "port": 25613},
    {"host": "c220g2-011121.wisc.cloudlab.us", "port": 25614},
    {"host": "c220g2-011121.wisc.cloudlab.us", "port": 25615},
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
        
        # Run the target Python script
        # conn.run(f"python3 {target_script} {id} 7777", hide=True)
        
        # Run the target Python script without waiting for it to finish
        conn.run(f"nohup python3 {target_script} {id} 7777 &", hide=True, warn=True, asynchronous=True)
        
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