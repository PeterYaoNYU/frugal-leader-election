import re
import matplotlib.pyplot as plt
from collections import defaultdict
from pathlib import Path
import numpy as np


import os
import argparse
import re

def find_largest_folder(base_dir):
    """
    Finds the largest subfolder within the base_dir based on the number of files.
    
    Args:
        base_dir (str): The base directory to search within.
    
    Returns:
        str: The path to the largest subfolder.
    """
    subfolders = [f.path for f in os.scandir(base_dir) if f.is_dir()]
    if not subfolders:
        return None
    
    print(subfolders)
    
    # Find the subfolder with the maximum number of files
    largest_folder = max(subfolders)
    return largest_folder


def plot_heartbeat_lengths(log_file, output_dir="plots"):
    """
    Parses the log file to determine the length of each term in heartbeats
    and plots it as a bar chart. Different bar colors indicate different leaders.
    Also prints and plots the average, variance, min, and max of the term length.

    Parameters:
        log_file (str): Path to the log file to parse.
        output_dir (str): Directory where the plot should be saved.
    """
    # Regular expressions to detect heartbeat patterns
    follower_pattern = r"Received AppendEntries from ([\d\.]+):\d+ for term (\d+) with id (\d+)"
    leader_pattern = r"\[LEADER\] Sent heartbeat (\d+) for term (\d+)"
    
    # Dictionary to store heartbeat counts for each term by leader
    heartbeat_counts = defaultdict(lambda: defaultdict(int))
    
    # Parse the log file for heartbeat information
    with open(log_file, 'r') as f:
        for line in f:
            # Match follower's received heartbeat
            follower_match = re.search(follower_pattern, line)
            if follower_match:
                leader_ip = follower_match.group(1)
                term = int(follower_match.group(2))
                heartbeat_counts[term][leader_ip] += 1
            
            # Match leader's sent heartbeat
            leader_match = re.search(leader_pattern, line)
            if leader_match:
                term = int(leader_match.group(2))
                heartbeat_count = int(leader_match.group(1))
                leader_ip = "self"  # Mark the node as leader for this term
                heartbeat_counts[term][leader_ip] = max(heartbeat_counts[term][leader_ip], heartbeat_count)

    # Prepare data for plotting
    terms = sorted(heartbeat_counts.keys())
    term_lengths = []
    leaders = []
    colors = []
    
    color_map = {}  # Map leader IP to color
    unique_leaders = set(leader for term in heartbeat_counts.values() for leader in term)
    color_palette = plt.cm.get_cmap("tab10", len(unique_leaders))
    
    # Assign a unique color for each leader
    for i, leader in enumerate(unique_leaders):
        color_map[leader] = color_palette(i)
    
    for term in terms:
        leader = max(heartbeat_counts[term], key=heartbeat_counts[term].get)  # Leader with max heartbeats
        term_length = heartbeat_counts[term][leader]
        term_lengths.append(term_length)
        leaders.append(leader)
        colors.append(color_map[leader])

    # Calculate statistics
    avg_length = np.mean(term_lengths)
    var_length = np.var(term_lengths)
    min_length = np.min(term_lengths)
    max_length = np.max(term_lengths)
    sum_length = np.sum(term_lengths)   

    print(f"Statistics for {Path(log_file).name}:")
    print(f"  Average Term Length: {avg_length}")
    print(f"  Variance of Term Length: {var_length}")
    print(f"  Min Term Length: {min_length}")
    print(f"  Max Term Length: {max_length}")
    print(f"  Total Heartbeats: {sum_length}")
    print(f"  Total number of terms: {len(terms)}")

    # Plot the bar chart
    plt.figure(figsize=(10, 6))
    plt.bar(range(len(terms)), term_lengths, color=colors, tick_label=terms)
    plt.xlabel("Term")
    plt.ylabel("Length (Number of Heartbeats)")
    plt.title(f"Heartbeat Lengths by Term\n(Average: {avg_length:.2f}, Variance: {var_length:.2f}, Min: {min_length}, Max: {max_length}, Total: {sum_length}, Terms: {len(terms)}, rate: {(len(terms) - 1)/sum_length:.4f})")
    plt.xticks(rotation=45, fontsize=8)  # Smaller font size for term labels
    plt.tight_layout()

    # Save the plot
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    plot_file = output_path / f"{Path(log_file).stem}_heartbeat_lengths.png"
    plt.savefig(plot_file)
    plt.close()


def bulk_process_logs(log_dir, start_idx, end_idx, output_dir="plots"):
    """
    Processes multiple log files for a range of indices and generates
    heartbeat length plots for each run.

    Parameters:
        log_dir (str): Directory containing log files.
        start_idx (int): Starting index for the log files to process.
        end_idx (int): Ending index for the log files to process.
        output_dir (str): Directory where the plots should be saved.
    """
    for idx in range(start_idx, end_idx + 1):
        # log_file = Path(log_dir) / f"node_1_run_{idx}.log"  # Adjust node and filename pattern as needed
        log_file = Path(log_dir) / f"node_{idx}.log"
        if log_file.exists():
            print(f"\nProcessing {log_file}")
            plot_heartbeat_lengths(log_file, output_dir=output_dir)
        else:
            print(f"Log file {log_file} not found. Skipping.")

# Example usage for a single file
# plot_heartbeat_lengths("./downloaded_logs/remote/node_5_run_1.log", output_dir="custom_plots")
parser = argparse.ArgumentParser(description='Process log files to calculate rank 0 proportions.')
parser.add_argument('--base_dir', default='./downloaded_logs/', help='Base directory containing log folders.')
args = parser.parse_args()

base_dir = args.base_dir

# Find the largest folder in the base_dir
largest_folder = find_largest_folder(base_dir)
if not largest_folder:
    print(f"No subfolders found in '{base_dir}'. Exiting.")

print(f"Largest folder found: {largest_folder}")
# Example usage for bulk processing
bulk_process_logs(largest_folder, start_idx=1, end_idx=1, output_dir="jacobson_variation_try13_300s_4rttvar+10-20random")
# plot_heartbeat_lengths("./downloaded_logs/20241102_130839/node_.log", output_dir="jacobson6_variation_try8_500s_4rttvar+random")