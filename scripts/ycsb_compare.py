#!/usr/bin/env python3
import os
import re
import glob
import matplotlib.pyplot as plt
from statistics import mean, stdev
import matplotlib.cm as cm
import matplotlib.patches as mpatches

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

def group_experiment_results():
    """
    Look for files matching:
      zk_leader_node{node_id}_{lat}ms_{thd_cnt}threads_base_delay_{base_delay}_ms_run{j}.txt
    Group results by (node_id, latency, thd_cnt) and for each group, collect
    throughput and update_avg values.
    """
    file_pattern = "zk_leader_node*.txt"
    files = glob.glob(file_pattern)
    
    regex = re.compile(
        r"zk_leader_node(?P<node_id>\d+)_(?P<latency>\d+(?:\.\d+)?)ms_(?P<thd_cnt>\d+)threads_base_delay_(?P<base_delay>\d+)_ms_run(?P<run>\d+)\.txt"
    )
    
    groups = {}
    for fname in files:
        m = regex.match(os.path.basename(fname))
        if m:
            node_id = int(m.group("node_id"))
            latency = float(m.group("latency"))
            thd_cnt = int(m.group("thd_cnt"))
            throughput, update_avg = parse_ycsb_file(fname)
            if throughput is None or update_avg is None:
                print(f"Warning: Could not parse {fname} properly.")
                continue
            key = (node_id, latency, thd_cnt)
            groups.setdefault(key, []).append((throughput, update_avg))
        else:
            print(f"File {fname} does not match the expected pattern.")
    return groups

def plot_bar_charts(groups, output_file="ycsb_bar_charts_with_delta.png"):
    """
    For each group (node_id, latency, thd_cnt) compute the mean and std dev
    for throughput and update latency. Then plot three bar charts:
      1. Throughput (with error bars)
      2. Average update latency (with error bars)
      3. Delta update latency, which is the difference between each group's update
         latency and the minimum update latency among all groups (converted to milliseconds).
         Each delta bar is annotated with its numeric value in milliseconds.
         
    A vertical dotted line is drawn between experiment settings (i.e. where latency and thread count change).
    Each node is assigned a unique color, and a legend is added to each chart.
    """
    labels = []  # x-axis labels
    throughput_means = []
    throughput_stds = []
    update_means = []
    update_stds = []
    
    # Sort groups by (latency, node_id, thread_count)
    sorted_keys = sorted(groups.keys(), key=lambda k: (k[1], k[0], k[2]))
    
    # Map each node_id to a unique color using a colormap (tab10)
    unique_node_ids = sorted(set(key[0] for key in sorted_keys))
    cmap = cm.get_cmap('tab10', len(unique_node_ids))
    node_color = {nid: cmap(i) for i, nid in enumerate(unique_node_ids)}
    
    # Build a list of colors for each group based on node id
    group_colors = []
    
    for key in sorted_keys:
        node_id, latency, thd_cnt = key
        data = groups[key]  # list of (throughput, update_avg)
        throughputs = [d[0] for d in data]
        updates = [d[1] for d in data]
        thr_mean = mean(throughputs)
        upd_mean = mean(updates)
        thr_std = stdev(throughputs) if len(throughputs) > 1 else 0
        upd_std = stdev(updates) if len(updates) > 1 else 0

        throughput_means.append(thr_mean)
        throughput_stds.append(thr_std)
        update_means.append(upd_mean)
        update_stds.append(upd_std)
        labels.append(f"Node {node_id}\n{latency}ms\n{thd_cnt}thr")
        group_colors.append(node_color[node_id])
    
    x = range(len(labels))
    
    # Determine the minimum update latency (in microseconds) across all groups.
    min_update = min(update_means)
    # Compute the delta (difference) for each group, and convert to milliseconds.
    update_deltas = [ (um - min_update) / 1000.0 for um in update_means ]
    
    # Create legend handles for each node id.
    legend_handles = [mpatches.Patch(color=node_color[nid], label=f"Node {nid}") for nid in unique_node_ids]
    
    # Create a figure with three subplots.
    fig, (ax_thr, ax_upd, ax_delta) = plt.subplots(3, 1, figsize=(24, 14), sharex=True)
    
    # --- Plot Throughput Bar Chart ---
    bars_thr = ax_thr.bar(x, throughput_means, yerr=throughput_stds, capsize=5, color=group_colors)
    ax_thr.set_title("Overall Throughput (ops/sec)")
    ax_thr.set_ylabel("Throughput (ops/sec)")
    ax_thr.set_xticks(x)
    ax_thr.set_xticklabels(labels, rotation=45, ha='right')
    for i, bar in enumerate(bars_thr):
        height = bar.get_height()
        ax_thr.text(bar.get_x() + bar.get_width()/2, height,
                    f"{throughput_means[i]:.1f}\n±{throughput_stds[i]:.1f}",
                    ha='center', va='bottom', fontsize=9)
    ax_thr.legend(handles=legend_handles, title="Node ID")
    
    # --- Plot Update Latency Bar Chart ---
    bars_upd = ax_upd.bar(x, update_means, yerr=update_stds, capsize=5, color=group_colors)
    ax_upd.set_title("Average Update Latency (μs)")
    ax_upd.set_ylabel("Latency (μs)")
    ax_upd.set_xticks(x)
    ax_upd.set_xticklabels(labels, rotation=45, ha='right')
    for i, bar in enumerate(bars_upd):
        height = bar.get_height()
        ax_upd.text(bar.get_x() + bar.get_width()/2, height,
                    f"{update_means[i]:.1f}\n±{update_stds[i]:.1f}",
                    ha='center', va='bottom', fontsize=9)
    ax_upd.legend(handles=legend_handles, title="Node ID")
    
    # --- Plot Delta Update Latency Bar Chart ---
    bars_delta = ax_delta.bar(x, update_deltas, capsize=5, color=group_colors)
    ax_delta.set_title("Delta Update Latency (ms)")
    ax_delta.set_ylabel("Delta Latency (ms)")
    ax_delta.set_xlabel("Experiment (Node, Link Delay, Thread Count)")
    ax_delta.set_xticks(x)
    ax_delta.set_xticklabels(labels, rotation=45, ha='right')
    for i, bar in enumerate(bars_delta):
        height = bar.get_height()
        ax_delta.text(bar.get_x() + bar.get_width()/2, height,
                      f"{update_deltas[i]:.2f}ms", ha='center', va='bottom', fontsize=9)
    ax_delta.legend(handles=legend_handles, title="Node ID")
    
    # --- Add Vertical Dotted Lines to Separate Experiment Settings ---
    # We define an experiment setting by (latency, thd_cnt).
    # We'll add a line before the first index of a new setting.
    prev_setting = None
    for i, key in enumerate(sorted_keys):
        # key structure is (node_id, latency, thd_cnt)
        current_setting = (key[1], key[2])
        if prev_setting is not None and current_setting != prev_setting:
            # Draw a vertical dotted line at x position i - 0.5.
            for ax in (ax_thr, ax_upd, ax_delta):
                ax.axvline(x=i - 0.5, color='black', linestyle='dotted')
        prev_setting = current_setting
    
    fig.tight_layout()
    plt.savefig(output_file)
    plt.show()
    print(f"Saved bar charts as {output_file}")

def main():
    groups = group_experiment_results()
    if not groups:
        print("No valid experiment files found.")
        return
    plot_bar_charts(groups)

if __name__ == "__main__":
    main()
