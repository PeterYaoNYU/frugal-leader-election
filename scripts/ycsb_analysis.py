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
    
    
def plot_combined_ycsb_profiles(filenames):
    """
    Takes a list of YCSB output filenames and generates a combined plot with:
      - Two line charts for tail latency percentiles (READ and WRITE).
      - Three bar charts for mean READ latency, mean WRITE latency, and overall throughput.
      
    Different experiments (filenames) are represented with different colors.
    The resulting figure is saved as 'combined_ycsb.png'.
    """
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec

    # Define the percentiles we care about and their simplified x-axis labels.
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
    x_labels = ["10", "25", "50", "75", "90", "95", "99", "99.9"]

    # Container to store data for each experiment/file.
    experiments = []
    for fname in filenames:
        exp_data = {
            'filename': fname,
            'read_percentiles': {},
            'update_percentiles': {},
            'read_avg': None,
            'update_avg': None,
            'throughput': None,
        }
        with open(fname, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = [p.strip() for p in line.split(",")]
                if len(parts) < 3:
                    continue

                if parts[0] == "[OVERALL]":
                    if "Throughput(ops/sec)" in parts[1]:
                        try:
                            exp_data['throughput'] = float(parts[2])
                        except ValueError:
                            pass
                elif parts[0] == "[READ]":
                    if "AverageLatency(us)" in parts[1]:
                        try:
                            exp_data['read_avg'] = float(parts[2])
                        except ValueError:
                            pass
                    elif parts[1] in percentiles:
                        try:
                            exp_data['read_percentiles'][parts[1]] = float(parts[2])
                        except ValueError:
                            pass
                elif parts[0] == "[UPDATE]":
                    if "AverageLatency(us)" in parts[1]:
                        try:
                            exp_data['update_avg'] = float(parts[2])
                        except ValueError:
                            pass
                    elif parts[1] in percentiles:
                        try:
                            exp_data['update_percentiles'][parts[1]] = float(parts[2])
                        except ValueError:
                            pass
        experiments.append(exp_data)

    # Create the figure.
    fig = plt.figure(figsize=(18, 10))
    # Use an outer GridSpec with 2 rows:
    # - The top row will have 2 subplots (line charts).
    # - The bottom row will have 3 subplots (bar charts).
    outer = gridspec.GridSpec(2, 1, height_ratios=[1, 1])

    # Top row: two subplots for line charts.
    gs_top = gridspec.GridSpecFromSubplotSpec(1, 2, subplot_spec=outer[0])
    ax_read_line = fig.add_subplot(gs_top[0])
    ax_write_line = fig.add_subplot(gs_top[1])

    # Bottom row: three subplots for bar charts.
    gs_bottom = gridspec.GridSpecFromSubplotSpec(1, 3, subplot_spec=outer[1])
    ax_read_bar = fig.add_subplot(gs_bottom[0])
    ax_write_bar = fig.add_subplot(gs_bottom[1])
    ax_thr_bar = fig.add_subplot(gs_bottom[2])

    # Define a unified set of colors (one per experiment).
    num_experiments = len(experiments)
    cmap = plt.get_cmap("tab10")
    colors = [cmap(i) for i in range(num_experiments)]

    # Plot line charts for tail latencies.
    for i, exp in enumerate(experiments):
        # Extract percentile values in order.
        read_vals = [exp['read_percentiles'].get(p, None) for p in percentiles]
        write_vals = [exp['update_percentiles'].get(p, None) for p in percentiles]
        label = exp['filename']
        ax_read_line.plot(x_labels, read_vals, marker='o', color=colors[i], label=label)
        ax_write_line.plot(x_labels, write_vals, marker='o', color=colors[i], label=label)

    ax_read_line.set_title("READ Tail Latency (μs)")
    ax_read_line.set_xlabel("Percentile")
    ax_read_line.set_ylabel("Latency (μs)")
    ax_read_line.legend()

    ax_write_line.set_title("WRITE (UPDATE) Tail Latency (μs)")
    ax_write_line.set_xlabel("Percentile")
    ax_write_line.set_ylabel("Latency (μs)")
    ax_write_line.legend()

    # Prepare data for bar charts.
    exp_labels = [exp['filename'] for exp in experiments]
    indices = range(num_experiments)
    read_avgs = [exp['read_avg'] for exp in experiments]
    update_avgs = [exp['update_avg'] for exp in experiments]
    throughputs = [exp['throughput'] for exp in experiments]

    # Bar chart for mean READ latency.
    ax_read_bar.bar(indices, read_avgs, color=colors)
    ax_read_bar.set_title("Mean READ Latency (μs)")
    ax_read_bar.set_xticks(indices)
    ax_read_bar.set_xticklabels(exp_labels, rotation=45, ha='right')

    # Bar chart for mean WRITE latency.
    ax_write_bar.bar(indices, update_avgs, color=colors)
    ax_write_bar.set_title("Mean WRITE Latency (μs)")
    ax_write_bar.set_xticks(indices)
    ax_write_bar.set_xticklabels(exp_labels, rotation=45, ha='right')

    # Bar chart for overall throughput.
    ax_thr_bar.bar(indices, throughputs, color=colors)
    ax_thr_bar.set_title("Overall Throughput (ops/sec)")
    ax_thr_bar.set_xticks(indices)
    ax_thr_bar.set_xticklabels(exp_labels, rotation=45, ha='right')

    # Add an overall title and adjust layout.
    fig.suptitle("Combined YCSB Profiles", fontsize=16)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig("combined_ycsb.png")
    # Uncomment the following line if you want to display the plot interactively:
    # plt.show()


def plot_ycsb_profile(filename):
    # download the file from the remote node
    # download_ycsb_from_remote(0, filename)
    
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
        "99.5PercentileLatency(us)"
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
    # if len(sys.argv) != 2:
    #     print("Usage: python ycsb_analysis.py <output_file>")
    #     sys.exit(1)
    # plot_ycsb_profile(sys.argv[1])
    # files = ["zk_client_4_to_server.txt", "zk_client_0_to_server.txt", "zk_client_1_to_server.txt", "zk_client_3_to_server.txt", "zk_client_2_to_server.txt"]
    files = ["zk_different_rack_lat_1ms.txt", "zk_different_rack_lat_2ms.txt", "zk_different_rack_lat_4ms.txt", "zk_different_rack_lat_6ms.txt", "zk_different_rack_lat_8ms.txt"]
    plot_combined_ycsb_profiles(files)