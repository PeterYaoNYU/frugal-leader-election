# fabric ssh setup
from fabric import Connection


node0 = Connection(
    host='c220g1-031111.wisc.cloudlab.us',
    user = 'PeterYao',
    port=22,
)



node1 = Connection(
    host='c220g1-031130.wisc.cloudlab.us',
    user = 'PeterYao',
    port=22,
)


node2 = Connection(
    host='c220g1-031117.wisc.cloudlab.us',
    user='PeterYao',
    port=22,
)

node3 = Connection(
    host='c220g1-031119.wisc.cloudlab.us',
    user= 'PeterYao',  
    port=22,
)

node4 = Connection(
    host='c220g1-031105.wisc.cloudlab.us',
    user = 'PeterYao',
    port=22,
)

connections = [node0, node1, node2, node3, node4]

node_interfaces = {
    "node0": ["enp129s0f0", "enp129s0f1"],
    "node1": ["enp6s0f0", "enp6s0f1"],
    "node2": ["enp6s0f0", "enp6s0f1"],
    "node3": ["enp6s0f0", "enp6s0f1"],
    "node4": ["enp129s0f0"],
}

# Function to add delay to specified interfaces
def add_delay(connection, hostname, interfaces):
    try:
        print(f"Configuring tc delay on {hostname}...")
        for interface in interfaces:
            print(f"Adding delay to {interface} on {hostname}...")
            
            delete_command = f"sudo tc qdisc del dev {interface} root || true"
            connection.run(delete_command, hide=True)
            
            # Then, add the new delay rule
            add_command = (
                f"sudo tc qdisc add dev {interface} root netem delay 3ms 3ms distribution pareto"
                # f"sudo tc qdisc add dev {interface} root netem delay 0.5ms distribution exponential"
                # f"sudo tc qdisc add dev {interface} root netem delay 0.1ms 5ms distribution exponential"
            )
            connection.run(add_command)
            
        print(f"Delay added successfully on {hostname}!")
    except Exception as e:
        print(f"Error configuring tc delay on {hostname}: {e}")

# Apply delay to relevant interfaces for all nodes
for idx, conn in enumerate(connections):
    hostname = f"node{idx}"
    if hostname in node_interfaces:
        add_delay(conn, hostname, node_interfaces[hostname])