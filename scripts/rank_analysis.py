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

    largest_folder = "./downloaded_logs/20241203_223802"

    print(f"Largest folder found: {largest_folder}")
    
    # Get the list of files in the largest folder
    try:
        file_list = os.listdir(largest_folder)
    except FileNotFoundError:
        print(f"Error: Folder '{largest_folder}' not found.")
        return

    # Filter the files to process (e.g., node_0.log to node_4.log)
    files_to_process = [f for f in file_list if f.startswith('node_') and f.endswith('.log')]

    if not files_to_process:
        print(f"No log files found in folder '{largest_folder}'.")
        return

    counts = defaultdict(int)

    # Define the mapping from node indices to IPs
    node_ip_list = ["10.10.4.2", "10.10.2.1", "10.10.2.2", "10.10.3.2", "10.10.5.2"]
    ip_to_node = {ip: f'node_{idx}' for idx, ip in enumerate(node_ip_list)}

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
                            # Extract IP part (remove port if present)
                            ip = ip_port.split(':')[0]
                            rank = int(match.group(2))
                            if rank == 0:
                                # Map IP to node name
                                node_name = ip_to_node.get(ip, ip)
                                counts[node_name] += 1
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
    node_names = list(counts.keys())
    counts_list = [counts[node_name] for node_name in node_names]
    total_counts = sum(counts_list)
    proportions = [count / total_counts * 100 for count in counts_list]

    # Print counts
    print("\nCounts of rank 0 for each node:")
    for node_name, count in counts.items():
        print(f"{node_name}: {count}")

    # Plot pie chart
    plt.figure(figsize=(8,8))
    plt.pie(
        counts_list, 
        labels=node_names, 
        autopct='%1.1f%%', 
        startangle=140, 
        colors=plt.cm.Paired.colors
    )
    plt.title('Proportion of Times Each Node Was Ranked 0')
    plt.tight_layout()
    
    # Save pie chart
    pie_chart_path = os.path.join(largest_folder, 'rank0_pie_chart.png')
    plt.savefig(pie_chart_path)
    print(f"Pie chart saved as '{pie_chart_path}'.")

if __name__ == '__main__':
    main()



