import os
import re
from datetime import datetime

def process_log_file(log_file):
    # Regular expressions to match the required log lines
    election_timeout_pattern = r'I(\d{8} \d{2}:\d{2}:\d{2}\.\d+).*Election timeout occurred\. Suspected leader failure count: \d+'
    stale_append_entries_pattern = r'I(\d{8} \d{2}:\d{2}:\d{2}\.\d+).*Received Stale AppendEntries from .*'

    time_diffs = []
    last_election_timeout_time = None

    with open(log_file, 'r') as f:
        for line in f:
            # Check for election timeout occurrence
            election_match = re.search(election_timeout_pattern, line)
            if election_match:
                timestamp_str = election_match.group(1)
                last_election_timeout_time = datetime.strptime(timestamp_str, '%Y%m%d %H:%M:%S.%f')
                continue

            # Check for stale append entries
            stale_match = re.search(stale_append_entries_pattern, line)
            if stale_match and last_election_timeout_time:
                timestamp_str = stale_match.group(1)
                stale_time = datetime.strptime(timestamp_str, '%Y%m%d %H:%M:%S.%f')
                time_diff = (stale_time - last_election_timeout_time).total_seconds() * 1000.0  # Convert to milliseconds
                time_diffs.append(time_diff)
                last_election_timeout_time = None  # Reset to only consider the closest previous event

    return time_diffs

def analyze_logs_in_folder(folder_path):
    all_time_diffs = []
    for root, dirs, files in os.walk(folder_path):
        for filename in files:
            if filename.endswith('.log'):  # Adjust the extension if necessary
                log_file_path = os.path.join(root, filename)
                print(f'Processing {log_file_path}')
                time_diffs = process_log_file(log_file_path)
                all_time_diffs.extend(time_diffs)

    if all_time_diffs:
        min_diff = min(all_time_diffs)
        max_diff = max(all_time_diffs)
        avg_diff = sum(all_time_diffs) / len(all_time_diffs)
        print(f'\nProcessed {len(all_time_diffs)} time differences across all log files.')
        print(f'Min difference: {min_diff:.3f} ms')
        print(f'Max difference: {max_diff:.3f} ms')
        print(f'Average difference: {avg_diff:.3f} ms')
        print(sorted(all_time_diffs))
        print(len(all_time_diffs))
    else:
        print('No time differences found.')

if __name__ == '__main__':
    import sys
    if len(sys.argv) != 2:
        print('Usage: python analyze_logs.py /path/to/log/folder')
    else:
        folder_path = sys.argv[1]
        analyze_logs_in_folder(folder_path)
