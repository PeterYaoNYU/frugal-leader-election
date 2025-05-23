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
def add_delay(connection, hostname, interfaces, no_delay = True):
    try:
        print(f"Configuring tc delay on {hostname}...")
        for interface in interfaces:
            print(f"Adding delay to {interface} on {hostname}...")
            
            delete_command = f"sudo tc qdisc del dev {interface} root || true"
            connection.run(delete_command, hide=True)
            

            # Then, add the new delay rule
            add_command = (
                f"sudo tc qdisc add dev {interface} root netem delay 2ms"
                # f"sudo tc qdisc show dev {interface}"
                # f"sudo tc qdisc add dev {interface} root netem delay 0.5ms distribution exponential"
                # f"sudo tc qdisc add dev {interface} root netem delay 0.1ms 5ms distribution exponential"
            )
            if no_delay==False:
                connection.run(add_command)
            
        print(f"Delay added successfully on {hostname}!")
    except Exception as e:
        print(f"Error configuring tc delay on {hostname}: {e}")
        
# Function to add delay to specified interfaces, with high level of customization
# delay mean and delay std dev are in milliseconds
# delay distribution can be "pareto" or "normal"
def add_delay_to_node(node_id, delay_mean, delay_std_dev, delay_distribution, connections, interface_list=[]):
    try:
        print(f"Configuring tc delay on node{node_id}...")
        interfaces = node_interfaces.get(f"node{node_id}")
        hostname = f"node{node_id}"
        for interface in interfaces:
            if interface_list and interface not in interface_list:
                continue
            delete_command = f"sudo tc qdisc del dev {interface} root || true"
            connections.get(node_id).run(delete_command, hide=True)
            
            # Then, add the new delay rule
            if delay_distribution != "constant":
                add_command = (
                    f"sudo tc qdisc add dev {interface} root netem delay {delay_mean}ms {delay_std_dev}ms distribution {delay_distribution}"
                )
            elif delay_distribution == "constant":
                add_command = (
                    f"sudo tc qdisc add dev {interface} root netem delay {delay_mean}ms"
                )
            connections.get(node_id).run(add_command)
            
        print(f"Delay added successfully on {hostname}!")
    except Exception as e:
        print(f"Error configuring tc delay on {hostname}: {e}")
        
def add_delay_to_all_nodes(delay_mean, delay_std_dev, delay_distribution, connections):
    try:
        for node_id, v in connections.items():
            hostname = f"node{node_id}"
            if hostname in node_interfaces.keys():
                print(f"Configuring tc delay on {hostname}...")
                add_delay_to_node(node_id, delay_mean, delay_std_dev, delay_distribution, connections)
    except Exception as e:
        print(f"Error configuring tc delay on all nodes: {e}")
    # double check by priniting the netem delay on all nodes.
    for node_id, v in connections.items():
        hostname = f"node{node_id}"
        if hostname in node_interfaces.keys():
            for interface in node_interfaces[hostname]:
                print(f"Checking delay on {interface} on {hostname}...")
                connections.get(node_id).run(f"sudo tc qdisc show dev {interface}")

def clear_all_weights():
    for idx, conn in enumerate(connections):
        hostname = f"node{idx}"
        if hostname in node_interfaces:
            add_delay(conn, hostname, node_interfaces[hostname], no_delay=True)

# Apply delay to relevant interfaces for all nodes
if __name__ == "__main__":
    for idx, conn in enumerate(connections):
        hostname = f"node{idx}"
        if hostname in node_interfaces:
            add_delay(conn, hostname, node_interfaces[hostname], no_delay=True)