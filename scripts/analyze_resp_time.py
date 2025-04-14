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
    # Pattern for lines like: "Response time for request id 109 is 1.874 ms."
    response_pattern = re.compile(r"Response time for request id \d+ is ([\d\.]+) ms\.")
    committed_text = "Command committed successfully."
    times = []
    successful_requests = 0
    first_timestamp = None
    last_timestamp = None

    try:
        with open(filename, "r") as f:
            for line in f:
                # Parse the timestamp if present
                current_timestamp = parse_timestamp(line)
                if current_timestamp:
                    if first_timestamp is None:
                        first_timestamp = current_timestamp
                    last_timestamp = current_timestamp

                # Extract response times
                match = response_pattern.search(line)
                if match:
                    times.append(float(match.group(1)))

                # Count a successful command if the specific text is in the line
                if committed_text in line:
                    successful_requests += 1

    except Exception as e:
        print(f"Error reading file {filename}: {e}")
        sys.exit(1)

    if not times:
        print("No response times found in file.")
        sys.exit(1)

    avg, std_dev = compute_stats(times)
    print("Average response time: {:.3f} ms".format(avg))
    print("Standard deviation:    {:.3f} ms".format(std_dev))

    # Compute throughput if timestamps were found
    if first_timestamp and last_timestamp:
        duration = (last_timestamp - first_timestamp).total_seconds()
        throughput = successful_requests / duration if duration > 0 else float('inf')
        print("Total successful requests: {}".format(successful_requests))
        print("Total duration: {:.6f} seconds".format(duration))
        print("Throughput: {:.3f} requests/second".format(throughput))
    else:
        print("Timestamps not found in file to compute throughput.")

if __name__ == "__main__":
    main()
