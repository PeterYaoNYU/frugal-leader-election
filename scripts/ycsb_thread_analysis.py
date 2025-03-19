#!/usr/bin/env python3
import os
import re
import glob
import matplotlib.pyplot as plt

def parse_ycsb_file(fname):
    """
    Parse a YCSB output file to extract:
      - overall throughput (ops/sec) from the [OVERALL] line
      - average UPDATE latency (in microseconds) from the [UPDATE] line.
    """
    throughput = None
    update_avg = None
    with open(fname, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith("[OVERALL]") and "Throughput(ops/sec)" in line:
                parts = [p.strip() for p in line.split(",")]
                try:
                    throughput = float(parts[-1])
                except ValueError:
                    pass
            elif line.startswith("[UPDATE]") and "AverageLatency(us)" in line:
                parts = [p.strip() for p in line.split(",")]
                try:
                    update_avg = float(parts[-1])
                except ValueError:
                    pass
    return throughput, update_avg

def plot_combined_profiles(groups):
    # Create a figure with two subplots (line charts)
    fig, (ax_thr, ax_lat) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)

    # For each (leader, latency) combination, sort by thread count and plot.
    for (leader, latency), data in sorted(groups.items(), key=lambda x: (x[0][0], x[0][1])):
        # Sort by the number of threads.
        data.sort(key=lambda tup: tup[0])
        threads_list = [d[0] for d in data]
        throughput_list = [d[1] for d in data]
        update_lat_list = [d[2] for d in data]
        label = f"Leader {leader}, {latency}ms"
        ax_thr.plot(threads_list, throughput_list, marker='o', label=label)
        ax_lat.plot(threads_list, update_lat_list, marker='o', label=label)
    
    ax_thr.set_title("Throughput vs Number of Threads")
    ax_thr.set_ylabel("Throughput (ops/sec)")
    ax_thr.legend()
    ax_thr.grid(True)

    ax_lat.set_title("Avg Write Latency vs Number of Threads")
    ax_lat.set_xlabel("Number of Threads")
    ax_lat.set_ylabel("Average Write Latency (us)")
    ax_lat.legend()
    ax_lat.grid(True)
    
    fig.tight_layout()
    output_file = "combined_leader_latency.png"
    plt.savefig(output_file)
    plt.show()
    print(f"Saved combined plot as {output_file}")

def plot_gap_for_34_threads(groups):
    """
    For experiments with exactly 34 threads, compute and visualize the performance gap.
    For avg write latency, we compute: (measured_latency - min_latency).
    For throughput, we compute: (max_throughput - measured_throughput).
    These differences (gaps) are shown as bar charts with numeric labels on top.
    """
    results = []
    # Filter groups: for each (leader, latency) group, pick the experiment with 34 threads.
    for (leader, latency), data in groups.items():
        for d in data:
            if d[0] == 34:
                results.append(((leader, latency), d[1], d[2]))  # (throughput, update_avg)
                break

    if not results:
        print("No experiment files with 34 threads found.")
        return

    # Sort results by leader then latency.
    results.sort(key=lambda x: (x[0][0], x[0][1]))

    labels = [f"Leader {k[0]}, {k[1]}ms" for k, _, _ in results]
    throughputs = [th for _, th, _ in results]
    latencies = [lat for _, _, lat in results]

    # For throughput: higher is better, so gap = max_throughput - measured_throughput.
    max_thr = max(throughputs)
    throughput_gap = [max_thr - th for th in throughputs]

    # For latency: lower is better, so gap = measured_latency - min_latency.
    min_lat = min(latencies)
    latency_gap = [lat - min_lat for lat in latencies]

    # Create a new figure with two side-by-side bar charts.
    fig, (ax_gap_lat, ax_gap_thr) = plt.subplots(1, 2, figsize=(14, 6))
    
    # Plot latency gap bar chart.
    bars1 = ax_gap_lat.bar(labels, latency_gap, color="skyblue")
    ax_gap_lat.set_title("Delta Avg Write Latency (us) at 34 Threads")
    ax_gap_lat.set_xlabel("Experiment (Leader, Link Latency)")
    ax_gap_lat.set_ylabel("Latency Gap (us)")
    ax_gap_lat.tick_params(axis='x', rotation=45)
    # Annotate the bars with their numeric value.
    for bar in bars1:
        height = bar.get_height()
        ax_gap_lat.text(bar.get_x() + bar.get_width()/2, height, f"{height:.1f}",
                        ha='center', va='bottom')
    
    # Plot throughput gap bar chart.
    bars2 = ax_gap_thr.bar(labels, throughput_gap, color="salmon")
    ax_gap_thr.set_title("Delta Throughput (ops/sec) at 34 Threads")
    ax_gap_thr.set_xlabel("Experiment (Leader, Link Latency)")
    ax_gap_thr.set_ylabel("Throughput Gap (ops/sec)")
    ax_gap_thr.tick_params(axis='x', rotation=45)
    # Annotate the bars with their numeric value.
    for bar in bars2:
        height = bar.get_height()
        ax_gap_thr.text(bar.get_x() + bar.get_width()/2, height, f"{height:.1f}",
                        ha='center', va='bottom')

    fig.tight_layout()
    output_file = "gap_at_34_threads.png"
    plt.savefig(output_file)
    plt.show()
    print(f"Saved gap plot as {output_file}")

def main():
    # Look for all files matching the pattern.
    file_pattern = "zk_leader_node*.txt"
    files = glob.glob(file_pattern)
    
    # Regex pattern to extract leader, latency (in ms), and number of threads
    # from filenames of the form:
    #    zk_leader_node{leader}_{latency}ms_{threads}threads.txt
    regex = re.compile(
        r"zk_leader_node(?P<leader>\d+)_(?P<latency>\d+)ms_(?P<threads>\d+)threads\.txt"
    )
    
    # Group data by (leader, latency). Each entry is a list of tuples:
    # (threads, throughput, update_avg)
    groups = {}
    for fname in files:
        match = regex.match(os.path.basename(fname))
        if match:
            leader = int(match.group("leader"))
            latency = int(match.group("latency"))
            threads = int(match.group("threads"))
            throughput, update_avg = parse_ycsb_file(fname)
            if throughput is None or update_avg is None:
                print(f"Warning: Could not parse {fname} properly.")
                continue
            key = (leader, latency)
            groups.setdefault(key, []).append((threads, throughput, update_avg))
        else:
            print(f"File {fname} does not match the expected pattern.")
    
    if not groups:
        print("No valid experiment files found.")
        return

    # Plot the combined line charts over all thread counts.
    plot_combined_profiles(groups)

    # Plot additional gap bar charts for experiments with 34 threads.
    plot_gap_for_34_threads(groups)

if __name__ == "__main__":
    main()
