#!/usr/bin/env python3
import os
import re
import glob
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import yaml
from fabric import Connection

# --- Existing connection loading code ---
connections = {}

def load_connections(yaml_file):
    with open(yaml_file, 'r') as f:
        data = yaml.safe_load(f)
    
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

# --- Modified plotting function that accepts an output filename ---
def plot_combined_ycsb_profiles(filenames, output_file="combined_ycsb.png"):
    """
    Takes a list of YCSB output filenames and generates a combined plot with:
      - Two line charts for tail latency percentiles (READ and WRITE).
      - Three bar charts for mean READ latency, mean WRITE latency, and overall throughput.
      
    Each experiment (filename) is plotted in a different color.
    The resulting figure is saved as the provided output_file.
    """
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

    ax_read_bar.bar(indices, read_avgs, color=colors)
    ax_read_bar.set_title("Mean READ Latency (μs)")
    ax_read_bar.set_xticks(indices)
    ax_read_bar.set_xticklabels(exp_labels, rotation=45, ha='right')

    ax_write_bar.bar(indices, update_avgs, color=colors)
    ax_write_bar.set_title("Mean WRITE Latency (μs)")
    ax_write_bar.set_xticks(indices)
    ax_write_bar.set_xticklabels(exp_labels, rotation=45, ha='right')

    ax_thr_bar.bar(indices, throughputs, color=colors)
    ax_thr_bar.set_title("Overall Throughput (ops/sec)")
    ax_thr_bar.set_xticks(indices)
    ax_thr_bar.set_xticklabels(exp_labels, rotation=45, ha='right')

    fig.suptitle("Combined YCSB Profiles", fontsize=16)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(output_file)
    plt.close(fig)
    print(f"Saved combined plot as {output_file}")

# --- New function to automatically group files and generate plots ---
def automated_plot_experiments():
    """
    This function searches for files matching the pattern:
      zk_lat_leader_node{leader}_{mean}_{std}_pareto_read_{read}_write_{write}.txt
    It groups files by the common parameters (mean delay, std dev, read ratio, write ratio)
    regardless of the leader. For each group, it calls the plotting function to generate a
    combined plot that includes all leader cases.
    """
    # Find all matching files.
    file_pattern = "zk_lat_leader_node*.txt"
    files = glob.glob(file_pattern)
    if not files:
        print("No experiment files found matching", file_pattern)
        return

    # Pattern to extract parameters from the filename.
    regex = re.compile(
        r"zk_lat_leader_node(?P<leader>\d+)_"
        r"(?P<mean>\d+)_"
        r"(?P<std>\d+)_pareto_"
        r"read_(?P<read>[\d\.]+)_"
        r"write_(?P<write>[\d\.]+)\.txt"
    )
    
    # Group files by (mean, std, read, write)
    groups = {}
    for fname in files:
        m = regex.match(os.path.basename(fname))
        if m:
            mean = m.group("mean")
            std = m.group("std")
            read = m.group("read")
            write = m.group("write")
            key = (mean, std, read, write)
            groups.setdefault(key, []).append(fname)
        else:
            print(f"File {fname} does not match the expected pattern.")

    # For each group, sort the file list by leader and plot.
    for key, file_list in groups.items():
        mean, std, read, write = key
        # Sort by leader number (extracted from filename)
        file_list.sort(key=lambda f: int(regex.match(os.path.basename(f)).group("leader")))
        output_file = f"combined_zk_lat_{mean}_{std}_pareto_read_{read}_write_{write}.png"
        print(f"Generating plot for mean={mean}, std={std}, read={read}, write={write} using files:")
        for f in file_list:
            print("   ", f)
        plot_combined_ycsb_profiles(file_list, output_file=output_file)

# --- Example usage ---
if __name__ == "__main__":
    # load_connections("nodes.yaml")  # Uncomment if needed for remote downloading
    automated_plot_experiments()
