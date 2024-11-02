#!/usr/bin/env python3

import re
import sys
import matplotlib.pyplot as plt
from datetime import datetime, timedelta  # Added timedelta for cutoff

def parse_log_file(log_file_path):
    # Regular expressions to match log lines
    timestamp_pattern = r'([IE]\d{8} \d{2}:\d{2}:\d{2}\.\d{6})'
    follower_pattern = r'Received append entries message\.'
    leader_pattern = r'\[LEADER\] Sent heartbeat'
    heartbeat_pattern = r'(Sent|Received) heartbeat'

    views = []
    current_view = None
    heartbeat_count = 0
    initial_timestamp = None  # Added initial_timestamp
    cutoff_time = None         # Added cutoff_time

    with open(log_file_path, 'r') as log_file:
        for line in log_file:
            # Extract timestamp
            timestamp_match = re.search(timestamp_pattern, line)
            if timestamp_match:
                timestamp_str = timestamp_match.group(1)[1:]  # Remove leading 'I' or 'E'
                try:
                    timestamp = datetime.strptime(timestamp_str, '%Y%m%d %H:%M:%S.%f')
                except ValueError:
                    continue  # Skip lines with invalid timestamp format
            else:
                continue  # Skip lines without a timestamp

            # Initialize initial_timestamp and cutoff_time
            if initial_timestamp is None:
                initial_timestamp = timestamp
                cutoff_time = initial_timestamp + timedelta(seconds=30)
                continue  # Skip lines within the first 30 seconds

            # Skip lines before cutoff_time
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
        current_view['end_time'] = timestamp
        current_view['duration'] = (current_view['end_time'] - current_view['start_time']).total_seconds()
        current_view['heartbeat_count'] = heartbeat_count
        views.append(current_view)

    return views

def plot_views(views):
    durations = [view['duration'] for view in views]
    heartbeat_counts = [view['heartbeat_count'] for view in views]
    roles = [view['role'] for view in views]

    # Create scatter plot
    plt.figure(figsize=(10,6))
    colors = {'follower': 'blue', 'leader': 'red'}
    labels = {'follower': 'Follower', 'leader': 'Leader'}
    
    # To avoid duplicate labels in the legend
    plotted_roles = set()
    
    for i in range(len(views)):
        role = roles[i]
        label = labels.get(role, 'Unknown')
        if role not in plotted_roles:
            plt.scatter(heartbeat_counts[i], durations[i], color=colors.get(role, 'grey'), label=label)
            plotted_roles.add(role)
        else:
            plt.scatter(heartbeat_counts[i], durations[i], color=colors.get(role, 'grey'))
    
    plt.xlabel('Number of Heartbeats')
    plt.ylabel('Duration of View (seconds)')
    plt.title('Duration of Each View vs. Number of Heartbeats')
    plt.legend()
    plt.grid(True)
    
    # Add timestamp to filename
    current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    plt.savefig(f"heartbeat_duration_{current_time}.png")  # Changed filename to include timestamp

def main():
    if len(sys.argv) == 2:
        node_id = sys.argv[1]
        # log_file_path = f"logs/node_{node_id}.log"
        log_file_path = f"downloaded_logs/20241027_194240/node_1.log"
        print(f"Using log file: {log_file_path}")
    else:
        print("Usage: python script_name.py <node_id>")
        sys.exit(1)

    views = parse_log_file(log_file_path)
    plot_views(views)

if __name__ == '__main__':
    main()
