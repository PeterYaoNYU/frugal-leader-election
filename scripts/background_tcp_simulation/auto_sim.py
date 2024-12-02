from fabric import Connection
import threading

# Define node connection details

# for vms 
# nodes = [
#     # {"host": "c240g5-110103.wisc.cloudlab.us", "port": 26010},
#     {"host": "c240g5-110103.wisc.cloudlab.us", "port": 26011},
#     {"host": "c240g5-110103.wisc.cloudlab.us", "port": 26012},
#     {"host": "c240g5-110103.wisc.cloudlab.us", "port": 26013},
#     {"host": "c240g5-110103.wisc.cloudlab.us", "port": 26014},
#     {"host": "c240g5-110103.wisc.cloudlab.us", "port": 26015},
# ]



# nodes = [
#     {"host": "c220g2-011125.wisc.cloudlab.us", "port": 26610},
#     {"host": "c220g2-011125.wisc.cloudlab.us", "port": 26611},
#     {"host": "c220g2-011125.wisc.cloudlab.us", "port": 26612},
#     {"host": "c220g2-011125.wisc.cloudlab.us", "port": 26613},
#     {"host": "c220g2-011125.wisc.cloudlab.us", "port": 26614},
# ]


# nodes = [
#     {"host": "pc605.emulab.net", "port": 29442},
#     {"host": "pc604.emulab.net", "port": 29442},
#     {"host": "pc605.emulab.net", "port": 29443},
#     {"host": "pc606.emulab.net", "port": 29442},
#     {"host": "pc603.emulab.net", "port": 29442},
# ]


# VERY IMPORTANT!
# the order should reeally match the ip list

nodes = [
    {"host": "c220g2-010828.wisc.cloudlab.us", "port": 26610},
    {"host": "c220g2-010823.wisc.cloudlab.us", "port": 26610},
    {"host": "c220g2-010823.wisc.cloudlab.us", "port": 26611},
    {"host": "c220g2-010828.wisc.cloudlab.us", "port": 26611},
    {"host": "c220g2-010823.wisc.cloudlab.us", "port": 26612},
    # {"host": "c240g5-110103.wisc.cloudlab.us", "port": 26612},
]


# nodes = [
#     {"host": "c220g1-031113.wisc.cloudlab.us", "port": 22},
#     {"host": "c220g1-031130.wisc.cloudlab.us", "port": 22},
#     {"host": "c220g1-031108.wisc.cloudlab.us", "port": 22},
#     {"host": "c220g1-031125.wisc.cloudlab.us", "port": 22},
#     {"host": "c220g1-031129.wisc.cloudlab.us", "port": 22},
# ]

# nodes = [
#     {"host": "c220g2-010808.wisc.cloudlab.us", "port": 22},
#     {"host": "c220g2-010608.wisc.cloudlab.us", "port": 22},
#     {"host": "c220g2-010804.wisc.cloudlab.us", "port": 22},
#     {"host": "c220g2-010813.wisc.cloudlab.us", "port": 22},
#     {"host": "c220g2-010604.wisc.cloudlab.us", "port": 22},
# ]

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