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
    parser = argparse.ArgumentParser(description='Process log files to calculate rank 0 proportions.')
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

    counts = defaultdict(int)

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
                    if 'The rank of' in line and 'is:' in line:
                        # Use regex to extract IP and rank
                        pattern = r'The rank of (\S+) is: (\d+)'
                        match = re.search(pattern, line)
                        if match:
                            ip_port = match.group(1)
                            rank = int(match.group(2))
                            if rank == 0:
                                counts[ip_port] += 1
        except StopIteration:
            print(f"File '{filename}' has less than 1800 lines. Skipping.")
            continue
        except Exception as e:
            print(f"Error processing file '{filename}': {e}")
            continue

    # Check if counts is empty
    if not counts:
        print("No rank 0 data found in the logs.")
        return

    # Prepare data for plotting
    ips = list(counts.keys())
    counts_list = [counts[ip] for ip in ips]
    total_counts = sum(counts_list)
    proportions = [count / total_counts * 100 for count in counts_list]

    # Print counts
    print("\nCounts of rank 0 for each IP:")
    for ip_port, count in counts.items():
        print(f"{ip_port}: {count}")

    # Plot bar chart with annotations
    plt.figure(figsize=(10,6))
    bars = plt.bar(ips, counts_list, color='skyblue')
    plt.xlabel('IP Address')
    plt.ylabel('Number of times ranked 0')
    plt.title('Number of Times Each IP Was Ranked 0')
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()

    # Annotate bars with counts
    ax = plt.gca()
    annotate_bars(ax, bars, counts_list)

    # Save bar chart
    bar_chart_path = os.path.join(largest_folder, 'rank0_bar_chart.png')
    plt.savefig(bar_chart_path)
    print(f"Bar chart saved as '{bar_chart_path}'.")

    # Clear the current figure
    plt.clf()

    # Plot pie chart
    plt.figure(figsize=(8,8))
    plt.pie(counts_list, labels=ips, autopct='%1.1f%%', startangle=140, colors=plt.cm.Paired.colors)
    plt.title('Proportion of Times Each IP Was Ranked 0')
    plt.tight_layout()
    
    # Save pie chart
    pie_chart_path = os.path.join(largest_folder, 'rank0_pie_chart.png')
    plt.savefig(pie_chart_path)
    print(f"Pie chart saved as '{pie_chart_path}'.")

if __name__ == '__main__':
    main()
