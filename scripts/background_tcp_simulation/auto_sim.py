import argparse
from fabric import Connection
import threading

# Define node connection details
nodes = [
    {"host": "c240g5-110103.wisc.cloudlab.us", "port": 26011},
    {"host": "c240g5-110103.wisc.cloudlab.us", "port": 26012},
    {"host": "c240g5-110103.wisc.cloudlab.us", "port": 26013},
    {"host": "c240g5-110103.wisc.cloudlab.us", "port": 26014},
    {"host": "c240g5-110103.wisc.cloudlab.us", "port": 26015},
]

# SSH username
username = "PeterYao"

# Git repository to clone
repo_url = "https://github.com/PeterYaoNYU/frugal-leader-election.git"

# Python script to run after cloning
target_script = "~/frugal-leader-election/scripts/background_tcp_simulation/tcp_sim.py"

def execute_on_node(node, id, port, duration):
    try:
        # Establish SSH connection
        conn = Connection(host=node["host"], user=username, port=node["port"])
        
        # Run the target Python script without waiting for it to finish
        conn.run(f"nohup python3 {target_script} {id} {port} {duration} &", hide=True, warn=True, asynchronous=True)
        
        print(f"Script executed on {node['host']}:{node['port']} with port {port} and duration {duration}")
    except Exception as e:
        print(f"Failed on {node['host']}:{node['port']} - {e}")

def main(port, duration):
    # Start threads to connect to each node and perform the actions
    threads = []
    for id, node in enumerate(nodes):
        thread = threading.Thread(target=execute_on_node, args=(node, id + 1, port, duration))
        thread.start()
        threads.append(thread)

    # Wait for all threads to complete
    for thread in threads:
        thread.join()

    print("All tasks completed.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run TCP simulations on remote nodes.")
    parser.add_argument("port", type=int, help="Port to use for the TCP connections")
    parser.add_argument("duration", type=int, help="Duration of the TCP connections in seconds")

    args = parser.parse_args()

    main(args.port, args.duration)
