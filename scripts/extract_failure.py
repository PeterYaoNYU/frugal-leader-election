#!/usr/bin/env python3

import re
import sys
import matplotlib.pyplot as plt
from datetime import datetime

def extract_last_heartbeat_failure(log_file_path):
    """
    Extracts the last occurrence of the heartbeat failure line and prints
    the number of leader failures out of the total number of heartbeats.
    """
    # Regex pattern to match the heartbeat failure line
    pattern = re.compile(
        r'I\d{8} \d{2}:\d{2}:\d{2}\.\d{6} \d+ node\.cpp:\d+\]'
        r' Heartbeat received from leader .*? False positive check mode is active, resetting election timeout\.'
        r' (\d+) failures out of (\d+)'
    )

    last_failures = None
    last_total = None

    # Read the log file line by line
    with open(log_file_path, 'r') as f:
        for line in f:
            match = pattern.search(line)
            if match:
                # Extract the number of failures and total heartbeats
                last_failures = int(match.group(1))
                last_total = int(match.group(2))

    if last_failures is not None and last_total is not None:
        print(f"Leader failures: {last_failures} out of {last_total} heartbeats")
    else:
        print("No matching heartbeat failure lines found in the log file.")

def plot_failure_occurrences(log_file_path):
    """
    Extracts the occurrence times of election timeouts and plots them to
    visualize when failures happen during execution.
    """
    # Regex pattern to match the election timeout line
    pattern = re.compile(
        r'I(\d{8} \d{2}:\d{2}:\d{2}\.\d{6}) \d+ node\.cpp:\d+\]'
        r' Election timeout occurred\. Suspected leader failure count: (\d+)'
    )

    timestamps = []
    failure_counts = []

    # Read the log file line by line
    with open(log_file_path, 'r') as f:
        for line in f:
            match = pattern.search(line)
            if match:
                timestamp_str = match.group(1)
                failure_count = int(match.group(2))
                # Convert timestamp string to datetime object
                timestamp = datetime.strptime(timestamp_str, '%Y%m%d %H:%M:%S.%f')
                timestamps.append(timestamp)
                failure_counts.append(failure_count)

    if timestamps:
        # Plot the failure occurrences over time
        plt.figure(figsize=(10, 6))
        plt.plot(timestamps, failure_counts, marker='o', linestyle='-')
        plt.xlabel('Time')
        plt.ylabel('Suspected Leader Failure Count')
        plt.title('Leader Failure Occurrences Over Time')
        plt.grid(True)
        plt.tight_layout()
        # plt.show()
        plt.savefig("failure_occurrences.png")
    else:
        print("No matching election timeout lines found in the log file.")

def main():
    if len(sys.argv) == 2:
        # log_file_path = sys.argv[1]
        id = sys.argv[1]
        print("Using default log file: logs/node_1.log")
        log_file_path = "logs/node_{}.log".format(id)
    else:
        print("Usage: python script_name.py <id>")
        
    # Extract last heartbeat failure
    extract_last_heartbeat_failure(log_file_path)

    # Plot failure occurrences
    plot_failure_occurrences(log_file_path)

if __name__ == "__main__":
    main()
