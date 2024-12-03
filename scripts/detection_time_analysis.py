import os
import re
import argparse
import numpy as np
import csv
from collections import defaultdict
from pathlib import Path

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

def parse_election_timeouts(log_dir):
    """
    Parses all log files in the given directory to extract election timeouts.

    Args:
        log_dir (str): Directory containing log files.

    Returns:
        dict: A dictionary mapping filenames to lists of election timeout values in milliseconds.
    """
    election_timeouts = defaultdict(list)

    # Define the regex pattern to match the election timeout lines
    pattern = r"Using Jacobson estimation for election timeout: ([\d\.]+) Milliseconds, additional delay: (\d+) Milliseconds"

    # Get all files in the directory
    for filename in os.listdir(log_dir):
        filepath = os.path.join(log_dir, filename)
        if os.path.isfile(filepath):
            with open(filepath, 'r') as f:
                for line in f:
                    match = re.search(pattern, line)
                    if match:
                        election_timeout_value = float(match.group(1))
                        additional_delay = int(match.group(2))
                        # Convert election_timeout_value to milliseconds
                        election_timeout_ms = election_timeout_value * 1000
                        # Total election timeout
                        total_election_timeout_ms = election_timeout_ms + additional_delay
                        election_timeouts[filename].append(total_election_timeout_ms)

    return election_timeouts

def process_election_timeouts(base_dir):
    # Find the largest folder in the base_dir
    largest_folder = find_largest_folder(base_dir)
    if not largest_folder:
        print(f"No subfolders found in '{base_dir}'. Exiting.")
        return

    print(f"Largest folder found: {largest_folder}")

    # Parse the election timeouts from the logs in the largest folder
    election_timeouts = parse_election_timeouts(largest_folder)

    # Collect all election timeout values
    all_timeouts = []
    for timeouts in election_timeouts.values():
        all_timeouts.extend(timeouts)

    if not all_timeouts:
        print("No election timeouts found in the logs.")
        return

    # Calculate statistics
    mean_timeout = np.mean(all_timeouts)
    std_timeout = np.std(all_timeouts)
    min_timeout = np.min(all_timeouts)
    max_timeout = np.max(all_timeouts)

    print(f"Mean election timeout: {mean_timeout:.2f} ms")
    print(f"Standard deviation: {std_timeout:.2f} ms")
    print(f"Minimum election timeout: {min_timeout:.2f} ms")
    print(f"Maximum election timeout: {max_timeout:.2f} ms")

    # Persist the election timeouts in a CSV file
    output_file = os.path.join(largest_folder, 'election_timeouts.csv')
    with open(output_file, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Filename', 'ElectionTimeout(ms)'])
        for filename, timeouts in election_timeouts.items():
            for timeout in timeouts:
                writer.writerow([filename, timeout])

    print(f"Election timeouts saved to {output_file}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Process log files to extract election timeouts.')
    parser.add_argument('--base_dir', default='./downloaded_logs/', help='Base directory containing log folders.')
    args = parser.parse_args()

    base_dir = args.base_dir
    process_election_timeouts(base_dir)
