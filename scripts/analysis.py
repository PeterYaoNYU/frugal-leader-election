#!/usr/bin/env python3

import re
import sys
import csv
import matplotlib.pyplot as plt
from datetime import datetime

def parse_log_file(log_file_path):
    # Regular expressions to match log lines
    timestamp_pattern = r'([IE]\d{8} \d{2}:\d{2}:\d{2}\.\d{6})'
    leader_pattern = r'\[LEADER\] Sent heartbeat (\d+) for term (\d+)'
    follower_pattern = r'Received heartbeat \(AppendEntries\) from leader .* for term (\d+)'

    views = []
    current_view = None
    current_term = None
    current_role = None
    heartbeat_count = 0

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

            # Check for leader log lines
            leader_match = re.search(leader_pattern, line)
            if leader_match:
                heartbeat_id = int(leader_match.group(1))
                term = int(leader_match.group(2))

                # New term detected
                if current_term != term or current_role != 'leader':
                    # Save the previous view
                    if current_view is not None:
                        views.append(current_view)

                    # Start a new leader view
                    current_view = {'view_number': len(views) + 1, 'role': 'leader', 'term': term, 'heartbeat_count': 0}
                    current_term = term
                    current_role = 'leader'

                # Update the maximum heartbeat ID for the leader
                current_view['heartbeat_count'] = max(current_view['heartbeat_count'], heartbeat_id)

            # Check for follower log lines
            follower_match = re.search(follower_pattern, line)
            if follower_match:
                term = int(follower_match.group(1))

                # New term detected
                if current_term != term or current_role != 'follower':
                    # Save the previous view
                    if current_view is not None:
                        views.append(current_view)

                    # Start a new follower view
                    current_view = {'view_number': len(views) + 1, 'role': 'follower', 'term': term, 'heartbeat_count': 0}
                    current_term = term
                    current_role = 'follower'

                # Increment the heartbeat count for the follower
                current_view['heartbeat_count'] += 1

    # Save the last view
    if current_view is not None:
        views.append(current_view)

    return views

def generate_csv(views, output_csv_path):
    with open(output_csv_path, 'w', newline='') as csvfile:
        fieldnames = ['View Number', 'Role', 'Term', 'Heartbeat Count']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for view in views:
            writer.writerow({
                'View Number': view['view_number'],
                'Role': view['role'],
                'Term': view['term'],
                'Heartbeat Count': view['heartbeat_count']
            })

def plot_views(views):
    terms = [view['term'] for view in views]
    heartbeat_counts = [view['heartbeat_count'] for view in views]
    colors = ['red' if view['role'] == 'leader' else 'green' for view in views]

    # Create bar plot
    plt.figure(figsize=(10, 6))
    plt.bar(terms, heartbeat_counts, color=colors)
    plt.xlabel('Term')
    plt.ylabel('Heartbeat Count')
    plt.title('Heartbeat Counts per Term')
    plt.grid(axis='y')

    # Add timestamp to filename
    current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    plt.savefig(f"heartbeat_counts_{current_time}.png")

def main():
    if len(sys.argv) == 1:
        # node_id = sys.argv[1]
        log_file_path = f"downloaded_logs/20241027_190925/node_2.log"
        print(f"Using log file: {log_file_path}")
    else:
        print("Usage: python script_name.py <node_id>")
        sys.exit(1)

    views = parse_log_file(log_file_path)

    # Generate CSV
    csv_file_path = f"heartbeat_stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    generate_csv(views, csv_file_path)
    print(f"CSV file saved: {csv_file_path}")

    # Plot views
    plot_views(views)

if __name__ == '__main__':
    main()
