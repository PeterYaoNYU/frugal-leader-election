#!/usr/bin/env python3
import matplotlib.pyplot as plt
import re
from fabric import Connection
import yaml

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
        
    

def download_ycsb_from_remote(node_id, filename):
    # Download the YCSB output file from the remote node.
    node = connections.get(node_id)
    if node is None:
        print(f"Node {node_id} not found in connections.")
        return
    print("Connewction: {0}".format(node))
    filename = f"{filename}"
    remote_path = f"/users/PeterYao/YCSB/{filename}"
    try:
        node.get(remote_path, filename)
    except Exception as e:
        print(f"Failed to download {filename} from Node {node_id}: {e}")
    print(f"Downloaded {filename} from Node {node_id}")

def plot_ycsb_profile(filename):
    # download the file from the remote node
    download_ycsb_from_remote(0, filename)
    
    # We'll store the throughput (ops/sec) and percentile latencies for READ and UPDATE.
    overall_throughput = None
    read_latencies = {}
    update_latencies = {}

    # Define the percentiles we are interested in (in order)
    percentiles = [
        "10thPercentileLatency(us)",
        "25thPercentileLatency(us)",
        "50thPercentileLatency(us)",
        "75thPercentileLatency(us)",
        "90thPercentileLatency(us)",
        "95thPercentileLatency(us)",
        "99thPercentileLatency(us)",
        "99.9PercentileLatency(us)"
    ]
    
    # Open and parse the file.
    with open(filename, 'r') as f:
        for line in f:
            # Remove extra spaces and newline.
            line = line.strip()
            if not line:
                continue

            parts = [p.strip() for p in line.split(",")]
            if parts[0] == "[OVERALL]":
                # Look for the throughput line.
                if len(parts) >= 3 and "Throughput(ops/sec)" in parts[1]:
                    try:
                        overall_throughput = float(parts[2])
                    except ValueError:
                        pass

            elif parts[0] == "[READ]":
                # Check if this line contains one of the percentile latencies.
                if len(parts) >= 3:
                    key = parts[1]
                    if key in percentiles:
                        try:
                            read_latencies[key] = float(parts[2])
                        except ValueError:
                            pass

            elif parts[0] == "[UPDATE]":
                if len(parts) >= 3:
                    key = parts[1]
                    if key in percentiles:
                        try:
                            update_latencies[key] = float(parts[2])
                        except ValueError:
                            pass

    # Sort percentiles in the order defined above.
    read_vals = [read_latencies.get(p, None) for p in percentiles]
    update_vals = [update_latencies.get(p, None) for p in percentiles]

    # Create x-axis labels (simplified, e.g. 10, 25, 50, etc.)
    x_labels = [p.split("th")[0] for p in percentiles]

    # Create a figure with 1 row and 2 columns of subplots.
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    # Plot READ percentiles as a bar chart.
    ax1.plot(x_labels, read_vals, color='skyblue')
    ax1.set_title("READ Tail Latency (μs)")
    # ax1.set_xlabel("Percentile")
    ax1.set_ylabel("Latency (μs)")
    # Annotate each bar with its value.
    for i, v in enumerate(read_vals):
        if v is not None:
            ax1.text(i, v + max(read_vals)*0.01, f"{v:.0f}", ha='center', va='bottom')

    # Plot UPDATE percentiles as a bar chart.
    ax2.plot(x_labels, update_vals, color='salmon')
    ax2.set_title("UPDATE Tail Latency (μs)")
    ax2.set_xlabel("Percentile")
    # Annotate each bar with its value.
    for i, v in enumerate(update_vals):
        if v is not None:
            ax2.text(i, v + max(update_vals)*0.01, f"{v:.0f}", ha='center', va='bottom')

    # Add an overall title or annotation with the overall throughput.
    if overall_throughput is not None:
        fig.suptitle(f"YCSB Profile: Overall Throughput = {overall_throughput:.2f} ops/sec", fontsize=14)
    else:
        fig.suptitle("YCSB Profile", fontsize=14)

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    # plt.show()
    plt.savefig("{0}_ycsb.png".format(filename))

# Example usage:
if __name__ == "__main__":
    import sys
    load_connections("nodes.yaml")
    if len(sys.argv) != 2:
        print("Usage: python ycsb_analysis.py <output_file>")
        sys.exit(1)
    plot_ycsb_profile(sys.argv[1])
