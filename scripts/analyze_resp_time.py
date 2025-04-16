#!/usr/bin/env python3
import sys
import re
import math
from datetime import datetime

def compute_stats(times):
    n = len(times)
    avg = sum(times) / n
    variance = sum((t - avg) ** 2 for t in times) / n
    std_dev = math.sqrt(variance)
    return avg, std_dev

def parse_timestamp(line):
    """
    Parse the timestamp from the beginning of a log line.
    Expected format: IYYYYMMDD HH:MM:SS.microseconds, for example:
    I20250413 22:52:12.450729
    """
    match = re.match(r"I(\d{8}) (\d{2}:\d{2}:\d{2}\.\d+)", line)
    if match:
        date_str = match.group(1)
        time_str = match.group(2)
        dt = datetime.strptime(f"{date_str} {time_str}", "%Y%m%d %H:%M:%S.%f")
        return dt
    return None

def main():
    if len(sys.argv) < 2:
        print("Usage: {} <log_file>".format(sys.argv[0]))
        sys.exit(1)

    filename = sys.argv[1]
    # Pattern to extract response time, e.g.
    # "Response time for request id 13876 is 19.094 ms."
    response_pattern = re.compile(r"Response time for request id \d+ is ([\d\.]+) ms\.")
    # Pattern to capture leader information from:
    # "Got a response from: 10.0.4.2:6555"
    leader_pattern = re.compile(r"Got a response from: ([\d\.]+:\d+)")
    committed_text = "Command committed successfully."
    
    times = []                 # Overall response times
    successful_requests = 0    # Overall count of successful requests
    leader_stats = {}          # Dictionary mapping leader -> list of response times
    last_leader = None         # Keep track of the last seen leader
    first_timestamp = None
    last_timestamp = None

    try:
        with open(filename, "r") as f:
            for line in f:
                # Capture the timestamp
                current_timestamp = parse_timestamp(line)
                if current_timestamp:
                    if first_timestamp is None:
                        first_timestamp = current_timestamp
                    last_timestamp = current_timestamp

                # Check for leader information.
                # When found, store it for the next response time.
                leader_match = leader_pattern.search(line)
                if leader_match:
                    last_leader = leader_match.group(1)

                # Extract response time and associate it with the current leader.
                response_match = response_pattern.search(line)
                if response_match:
                    response_time = float(response_match.group(1))
                    times.append(response_time)
                    # Associate with last seen leader if available, otherwise "unknown"
                    leader_id = last_leader if last_leader is not None else "unknown"
                    if leader_id not in leader_stats:
                        leader_stats[leader_id] = []
                    leader_stats[leader_id].append(response_time)
                    # Optionally, reset last_leader if you expect a new leader to be indicated each time.
                    # last_leader = None

                # Count successful requests (if the line indicates a committed command).
                if committed_text in line:
                    successful_requests += 1

    except Exception as e:
        print(f"Error reading file {filename}: {e}")
        sys.exit(1)

    if not times:
        print("No response times found in file.")
        sys.exit(1)

    # Overall statistics
    avg, std_dev = compute_stats(times)
    print("Overall Statistics:")
    print("  Average response time: {:.3f} ms".format(avg))
    print("  Standard deviation:    {:.3f} ms".format(std_dev))

    # Throughput calculations using overall timestamps.
    if first_timestamp and last_timestamp:
        duration = (last_timestamp - first_timestamp).total_seconds()
        throughput = successful_requests / duration if duration > 0 else float('inf')
        print("\nThroughput:")
        print("  Total successful requests: {}".format(successful_requests))
        print("  Total duration: {:.6f} seconds".format(duration))
        print("  Throughput: {:.3f} requests/second".format(throughput))
    else:
        print("Timestamps not found in file to compute throughput.")

    # Compute and print per-leader statistics.
    print("\nPer-Leader Response Times:")
    for leader, leader_times in leader_stats.items():
        count = len(leader_times)
        avg_leader, std_dev_leader = compute_stats(leader_times)
        print("  Leader {}: count = {}, Average = {:.3f} ms, Std Dev = {:.3f} ms"
              .format(leader, count, avg_leader, std_dev_leader))

if __name__ == "__main__":
    main()
