#!/usr/bin/env python3

import re
import sys
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

def extract_last_heartbeat_failure(log_file_path, cutoff_time):
    """
    Extracts the last occurrence of the heartbeat failure line after the cutoff_time
    and prints the number of leader failures out of the total number of heartbeats.
    """
    # Regex pattern to match the heartbeat failure line
    pattern = re.compile(
        r'I\d{8} \d{2}:\d{2}:\d{2}\.\d{6} \d+ node\.cpp:\d+\] '
        r'Heartbeat received from leader .*? False positive check mode is active, resetting election timeout\. '
        r'(\d+) failures out of (\d+)'
    )

    last_failures = None
    last_total = None

    # Read the log file line by line
    with open(log_file_path, 'r') as f:
        for line in f:
            # Extract timestamp
            timestamp_match = re.match(r'[IE](\d{8} \d{2}:\d{2}:\d{2}\.\d{6})', line)
            if not timestamp_match:
                continue  # Skip lines without a valid timestamp

            timestamp_str = timestamp_match.group(1)
            try:
                timestamp = datetime.strptime(timestamp_str, '%Y%m%d %H:%M:%S.%f')
            except ValueError:
                continue  # Skip lines with invalid timestamp format

            # Skip lines before the cutoff_time
            if timestamp < cutoff_time:
                continue

            match = pattern.search(line)
            if match:
                # Extract the number of failures and total heartbeats
                last_failures = int(match.group(1))
                last_total = int(match.group(2))

    if last_failures is not None and last_total is not None:
        print(f"Leader failures: {last_failures} out of {last_total} heartbeats")
    else:
        print("No matching heartbeat failure lines found in the log file after the cutoff time.")

def plot_failure_occurrences(log_file_path, cutoff_time):
    """
    Extracts the occurrence times of election timeouts after the cutoff_time and plots them
    to visualize when failures happen during execution.
    """
    # Regex pattern to match the election timeout line
    pattern = re.compile(
        r'I(\d{8} \d{2}:\d{2}:\d{2}\.\d{6}) \d+ node\.cpp:\d+\] '
        r'Heartbeat received from leader .*? False positive check mode is active, resetting election timeout\. (\d+) failures out of (\d+)'
    )

    timestamps = []
    failure_counts = []

    # Read the log file line by line
    with open(log_file_path, 'r') as f:
        for line in f:
            match = pattern.search(line)
            if match:
                timestamp_str = match.group(1)
                failures = int(match.group(2))
                total = int(match.group(3))
                try:
                    timestamp = datetime.strptime(timestamp_str, '%Y%m%d %H:%M:%S.%f')
                except ValueError:
                    continue  # Skip lines with invalid timestamp format

                # Skip lines before the cutoff_time
                if timestamp < cutoff_time:
                    continue

                timestamps.append(timestamp)
                failure_counts.append(failures)

    if timestamps:
        # Plot the failure occurrences over time
        plt.figure(figsize=(12, 6))
        plt.plot(timestamps, failure_counts, marker='o', linestyle='-', color='red')
        plt.xlabel('Time')
        plt.ylabel('Number of Leader Failures')
        plt.title('Leader Failure Occurrences Over Time')
        plt.grid(True)
        plt.tight_layout()
        
        # Create a timestamp for the filename
        plot_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        plot_filename = f"failure_occurrences_{plot_timestamp}.png"
        plt.savefig(plot_filename)
        print(f"Plot saved as {plot_filename}")
    else:
        print("No matching election timeout lines found in the log file after the cutoff time.")

def plot_view_durations(log_file_path, cutoff_time):
    """
    Parses the log file to identify view durations and number of heartbeats,
    then plots two separate graphs:
    1. Duration of each view (seconds) vs. view number.
    2. Number of heartbeats in each view vs. view number.
    """
    # Regular expressions to match log lines
    follower_pattern = r'Received append entries message\.'
    leader_pattern = r'\[LEADER\] Sent heartbeat'
    heartbeat_pattern = r'(Sent|Received) heartbeat'

    views = []
    current_view = None
    heartbeat_count = 0

    with open(log_file_path, 'r') as log_file:
        for line in log_file:
            # Extract timestamp
            timestamp_match = re.match(r'[IE](\d{8} \d{2}:\d{2}:\d{2}\.\d{6})', line)
            if not timestamp_match:
                continue  # Skip lines without a valid timestamp

            timestamp_str = timestamp_match.group(1)
            try:
                timestamp = datetime.strptime(timestamp_str, '%Y%m%d %H:%M:%S.%f')
            except ValueError:
                continue  # Skip lines with invalid timestamp format

            # Skip lines before the cutoff_time
            if timestamp < cutoff_time:
                continue

            # Check for role changes
            if re.search(follower_pattern, line):
                # Node is a follower
                if current_view is None or current_view['role'] != 'follower':
                    # Save the previous view
                    if current_view is not None:
                        current_view['end_time'] = timestamp
                        current_view['duration'] = (current_view['end_time'] - current_view['start_time']).total_seconds()
                        current_view['heartbeat_count'] = heartbeat_count
                        views.append(current_view)
                        heartbeat_count = 0  # Reset heartbeat count
                    # Start new follower view
                    current_view = {'role': 'follower', 'start_time': timestamp}
            elif re.search(leader_pattern, line):
                # Node is a leader
                if current_view is None or current_view['role'] != 'leader':
                    # Save the previous view
                    if current_view is not None:
                        current_view['end_time'] = timestamp
                        current_view['duration'] = (current_view['end_time'] - current_view['start_time']).total_seconds()
                        current_view['heartbeat_count'] = heartbeat_count
                        views.append(current_view)
                        heartbeat_count = 0  # Reset heartbeat count
                    # Start new leader view
                    current_view = {'role': 'leader', 'start_time': timestamp}

            # Count heartbeats within a view
            if current_view is not None:
                if re.search(heartbeat_pattern, line):
                    heartbeat_count += 1

    # Save the last view
    if current_view is not None:
        # Assuming the last timestamp in the log as the end_time
        current_view['end_time'] = timestamp
        current_view['duration'] = (current_view['end_time'] - current_view['start_time']).total_seconds()
        current_view['heartbeat_count'] = heartbeat_count
        views.append(current_view)

    if not views:
        print("No views found in the log file after the cutoff time.")
        return

    # Prepare data for plotting
    view_numbers = list(range(1, len(views) + 1))
    durations = [view['duration'] for view in views]
    heartbeat_counts = [view['heartbeat_count'] for view in views]
    roles = [view['role'] for view in views]

    # Colors and labels for roles
    colors = {'follower': 'blue', 'leader': 'green'}
    labels = {'follower': 'Follower', 'leader': 'Leader'}

    # First Plot: Duration vs. View Number
    plt.figure(figsize=(14, 7))
    for i in range(len(views)):
        plt.bar(view_numbers[i], durations[i], color=colors.get(roles[i], 'grey'), label=labels.get(roles[i], 'Unknown') if i == 0 or labels.get(roles[i], 'Unknown') not in plt.gca().get_legend_handles_labels()[1] else "")
    plt.xlabel('View Number')
    plt.ylabel('Duration of View (seconds)')
    plt.title('Duration of Each View')
    plt.legend()
    plt.grid(True)
    plt.xticks(view_numbers)
    plt.tight_layout()
    
    # Create a timestamp for the filename
    plot_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    duration_plot_filename = f"view_durations_{plot_timestamp}.png"
    plt.savefig(duration_plot_filename)
    print(f"Duration plot saved as {duration_plot_filename}")
    # plt.show()

    # Second Plot: Heartbeats vs. View Number
    plt.figure(figsize=(14, 7))
    for i in range(len(views)):
        plt.bar(view_numbers[i], heartbeat_counts[i], color=colors.get(roles[i], 'grey'), label=labels.get(roles[i], 'Unknown') if i == 0 or labels.get(roles[i], 'Unknown') not in plt.gca().get_legend_handles_labels()[1] else "")
    plt.xlabel('View Number')
    plt.ylabel('Number of Heartbeats')
    plt.title('Number of Heartbeats in Each View')
    plt.legend()
    plt.grid(True)
    plt.xticks(view_numbers)
    plt.tight_layout()
    
    heartbeat_plot_filename = f"heartbeat_counts_{plot_timestamp}.png"
    plt.savefig(heartbeat_plot_filename)
    print(f"Heartbeat plot saved as {heartbeat_plot_filename}")
    # plt.show()

def main():
    if len(sys.argv) == 2:
        id = sys.argv[1]
        log_file_path = f"logs/node_{id}.log"
        print(f"Using log file: {log_file_path}")
    else:
        print("Usage: python script_name.py <id>")
        sys.exit(1)

    # Define the cutoff time (first 30 seconds)
    # We'll determine the initial timestamp from the first log entry after the cutoff
    # To do this, we'll read the file once to get the first timestamp, then set the cutoff
    initial_timestamp = None
    with open(log_file_path, 'r') as f:
        for line in f:
            timestamp_match = re.match(r'[IE](\d{8} \d{2}:\d{2}:\d{2}\.\d{6})', line)
            if timestamp_match:
                timestamp_str = timestamp_match.group(1)
                try:
                    initial_timestamp = datetime.strptime(timestamp_str, '%Y%m%d %H:%M:%S.%f')
                    cutoff_time = initial_timestamp + timedelta(seconds=30)
                    break
                except ValueError:
                    continue  # Skip lines with invalid timestamp format

    if initial_timestamp is None:
        print("No valid timestamps found in the log file.")
        sys.exit(1)

    print(f"Initial timestamp: {initial_timestamp}")
    print(f"Cutoff time set to: {cutoff_time}")

    # Extract last heartbeat failure after cutoff_time
    extract_last_heartbeat_failure(log_file_path, cutoff_time)

    # Plot failure occurrences after cutoff_time
    plot_failure_occurrences(log_file_path, cutoff_time)

    # Optional: Plot view durations and heartbeats
    plot_view_durations(log_file_path, cutoff_time)

if __name__ == "__main__":
    main()
