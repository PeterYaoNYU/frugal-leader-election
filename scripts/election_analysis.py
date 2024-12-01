import os
import argparse
import re
from collections import defaultdict
import matplotlib.pyplot as plt

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
    print(f"Largest folder: {largest_folder}")
    return largest_folder

def annotate_bars(ax, rects, counts):
    """
    Annotates each bar with its count value.

    Args:
        ax (matplotlib.axes.Axes): The axes to annotate.
        rects (list): The bar containers.
        counts (list): The counts corresponding to each bar.
    """
    for rect, count in zip(rects, counts):
        height = rect.get_height()
        ax.text(rect.get_x() + rect.get_width() / 2, height, f'{count}', 
                ha='center', va='bottom', fontsize=9, fontweight='bold')

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Process log files to calculate metrics.')
    parser.add_argument('--base_dir', default='./downloaded_logs/', help='Base directory containing log folders.')
    args = parser.parse_args()

    base_dir = args.base_dir

    # Find the largest folder in the base_dir
    largest_folder = find_largest_folder(base_dir)
    if not largest_folder:
        print(f"No subfolders found in '{base_dir}'. Exiting.")
        return

    print(f"Largest folder found: {largest_folder}")

    # Get the list of files in the largest folder
    try:
        file_list = os.listdir(largest_folder)
    except FileNotFoundError:
        print(f"Error: Folder '{largest_folder}' not found.")
        return

    # Filter the files to process (node_1.log to node_5.log)
    files_to_process = [f for f in file_list if f.startswith('node_') and f.endswith('.log')]

    if not files_to_process:
        print(f"No log files found in folder '{largest_folder}'.")
        return

    # Initialize counters
    rank0_counts = defaultdict(int)      # For counting rank=0 per IP
    term_leaders = dict()                # For tracking leader per term

    # Regular expressions for parsing
    rank_pattern = re.compile(r'The rank of (\S+) is: (\d+)')
    leader_pattern = re.compile(r'Received AppendEntries from (\S+) for term (\d+) with id (\d+)')

    # Process each file
    for filename in files_to_process:
        filepath = os.path.join(largest_folder, filename)
        print(f"Processing file: {filepath}")

        try:
            with open(filepath, 'r') as f:
                # Skip the first 1800 lines (warmup phase)
                for _ in range(1800):
                    next(f)
                # Process the rest of the lines
                for line in f:
                    # Check for rank information
                    rank_match = rank_pattern.search(line)
                    if rank_match:
                        ip_port = rank_match.group(1)
                        rank = int(rank_match.group(2))
                        if rank == 0:
                            rank0_counts[ip_port] += 1

                    # Check for leader information
                    leader_match = leader_pattern.search(line)
                    if leader_match:
                        leader_ip = leader_match.group(1)
                        term = int(leader_match.group(2))
                        # Avoid duplicate entries for the same term
                        if term not in term_leaders:
                            term_leaders[term] = leader_ip

        except StopIteration:
            print(f"File '{filename}' has less than 1800 lines. Skipping.")
            continue
        except Exception as e:
            print(f"Error processing file '{filename}': {e}")
            continue

    # --- Metric 1: Counts of rank 0 for each IP ---
    if not rank0_counts:
        print("No rank 0 data found in the logs.")
    else:
        # Prepare data for plotting
        ips_rank0 = list(rank0_counts.keys())
        counts_rank0 = [rank0_counts[ip] for ip in ips_rank0]
        total_counts_rank0 = sum(counts_rank0)
        proportions_rank0 = [count / total_counts_rank0 * 100 for count in counts_rank0]

        # Print counts
        print("\nCounts of rank 0 for each IP:")
        for ip_port, count in rank0_counts.items():
            print(f"{ip_port}: {count}")

        # Plot bar chart with annotations for rank=0
        plt.figure(figsize=(10,6))
        bars = plt.bar(ips_rank0, counts_rank0, color='skyblue')
        plt.xlabel('IP Address')
        plt.ylabel('Number of times ranked 0')
        plt.title('Number of Times Each IP Was Ranked 0')
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()

        # Annotate bars with counts
        ax = plt.gca()
        annotate_bars(ax, bars, counts_rank0)

        # Save bar chart
        bar_chart_path = os.path.join(largest_folder, 'rank0_bar_chart.png')
        plt.savefig(bar_chart_path)
        print(f"Bar chart for rank=0 saved as '{bar_chart_path}'.")

        # Clear the current figure
        plt.clf()

        # Plot pie chart for rank=0
        plt.figure(figsize=(8,8))
        plt.pie(counts_rank0, labels=ips_rank0, autopct='%1.1f%%', startangle=140, colors=plt.cm.Paired.colors)
        plt.title('Proportion of Times Each IP Was Ranked 0')
        plt.tight_layout()

        # Save pie chart
        pie_chart_path = os.path.join(largest_folder, 'rank0_pie_chart.png')
        plt.savefig(pie_chart_path)
        print(f"Pie chart for rank=0 saved as '{pie_chart_path}'.")

    # --- Metric 2: Leader Terms for 10.10.4.2:7912 ---
    if not term_leaders:
        print("No leader term data found in the logs.")
    else:
        # Calculate number of terms where 10.10.4.2:7912 was the leader
        target_leader = '10.0.4.2:7912'
        leader_count = sum(1 for leader in term_leaders.values() if leader == target_leader)
        total_terms = len(term_leaders)
        proportion_leader = (leader_count / total_terms) * 100 if total_terms > 0 else 0

        print(f"\nLeader Term Analysis for {target_leader}:")
        print(f"Number of terms led by {target_leader}: {leader_count}")
        print(f"Total number of terms: {total_terms}")
        print(f"Proportion of terms led by {target_leader}: {proportion_leader:.2f}%")

        # Prepare data for plotting
        leader_counts = [leader_count, total_terms - leader_count]
        labels = [target_leader, 'Others']
        colors = ['lightcoral', 'lightskyblue']

        # Plot bar chart for leader terms
        plt.figure(figsize=(8,6))
        bars = plt.bar(labels, leader_counts, color=colors)
        plt.xlabel('Leader')
        plt.ylabel('Number of Terms')
        plt.title(f'Number of Terms {target_leader} Was Leader')
        plt.tight_layout()

        # Annotate bars with counts
        ax = plt.gca()
        annotate_bars(ax, bars, leader_counts)

        # Save bar chart
        leader_bar_chart_path = os.path.join(largest_folder, 'leader_terms_bar_chart.png')
        plt.savefig(leader_bar_chart_path)
        print(f"Bar chart for leader terms saved as '{leader_bar_chart_path}'.")

        # Clear the current figure
        plt.clf()

        # Plot pie chart for leader terms
        plt.figure(figsize=(8,8))
        plt.pie(leader_counts, labels=labels, autopct='%1.1f%%', startangle=140, colors=colors)
        plt.title(f'Proportion of Terms Led by {target_leader}')
        plt.tight_layout()

        # Save pie chart
        leader_pie_chart_path = os.path.join(largest_folder, 'leader_terms_pie_chart.png')
        plt.savefig(leader_pie_chart_path)
        print(f"Pie chart for leader terms saved as '{leader_pie_chart_path}'.")

if __name__ == '__main__':
    main()
