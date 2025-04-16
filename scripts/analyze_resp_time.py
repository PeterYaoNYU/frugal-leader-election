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
    I20250416 05:59:30.959692
    """
    match = re.match(r"I(\d{8}) (\d{2}:\d{2}:\d{2}\.\d+)", line)
    if match:
        date_str = match.group(1)
        time_str = match.group(2)
        return datetime.strptime(f"{date_str} {time_str}", "%Y%m%d %H:%M:%S.%f")
    return None

def main():
    if len(sys.argv) < 2:
        print("Usage: {} <log_file>".format(sys.argv[0]))
        sys.exit(1)

    filename = sys.argv[1]
    
    # Pattern to extract response time and request id, e.g.
    # "Response time for request id 32873 is 12.940 ms."
    response_pattern = re.compile(r"Response time for request id (\d+) is ([\d\.]+) ms\.")
    
    # Pattern for "Received ClientResponse" lines.
    # Example:
    # "Received ClientResponse: success=1, from=10.0.0.3, response="Command committed successfully.", client_id=123, request_id=32873, leader_id="
    received_pattern = re.compile(r"Received ClientResponse: .* from=([\d\.]+).*request_id=(\d+)")
    
    # Patterns to detect leadership boundaries.
    begin_leader_pattern = re.compile(r"Begin of Leadership under: ([\d\.]+)")
    end_leader_pattern   = re.compile(r"End of Leadership under: ([\d\.]+)")
    
    committed_text = "Command committed successfully."
    
    # Overall response times for statistics.
    times = []              
    successful_requests = 0  # overall commit count
    
    # For throughput per leader using leadership section markers.
    # Structure: { leader_ip: { "commits": count, "duration": total_seconds } }
    leader_throughput = {}
    
    # For active leadership section tracking.
    active_section_leader = None  # leader IP
    active_section_start = None   # timestamp (datetime)
    active_section_commits = 0    # count in current section
    
    # For latency measurements per leader.
    # Structure: { leader_ip: [latency1, latency2, ...] }
    leader_latency = {}
    # Temporary storages, since response time and "from" lines may not be in order.
    req_latency = {}   # request_id -> latency (float)
    req_leader = {}    # request_id -> leader (string)
    
    try:
        with open(filename, "r") as f:
            for line in f:
                current_timestamp = parse_timestamp(line)
                
                # Check for beginning of a leadership section.
                begin_match = begin_leader_pattern.search(line)
                if begin_match and current_timestamp:
                    # Flush any active section first.
                    if active_section_leader is not None:
                        section_duration = (current_timestamp - active_section_start).total_seconds()
                        leader = active_section_leader
                        if leader not in leader_throughput:
                            leader_throughput[leader] = {"commits": 0, "duration": 0.0}
                        leader_throughput[leader]["commits"] += active_section_commits
                        leader_throughput[leader]["duration"] += section_duration
                        active_section_leader = None
                        active_section_start = None
                        active_section_commits = 0
                    active_section_leader = begin_match.group(1)
                    active_section_start = current_timestamp
                    active_section_commits = 0
                    continue

                # Check for end of a leadership section.
                end_match = end_leader_pattern.search(line)
                if end_match and active_section_leader and current_timestamp:
                    section_duration = (current_timestamp - active_section_start).total_seconds()
                    leader = active_section_leader
                    if leader not in leader_throughput:
                        leader_throughput[leader] = {"commits": 0, "duration": 0.0}
                    leader_throughput[leader]["commits"] += active_section_commits
                    leader_throughput[leader]["duration"] += section_duration
                    active_section_leader = None
                    active_section_start = None
                    active_section_commits = 0
                    continue

                # Count commit events.
                if committed_text in line:
                    successful_requests += 1
                    if active_section_leader is not None:
                        active_section_commits += 1

                # Capture response time lines.
                r_match = response_pattern.search(line)
                if r_match:
                    req_id = int(r_match.group(1))
                    latency = float(r_match.group(2))
                    times.append(latency)
                    req_latency[req_id] = latency
                    if req_id in req_leader:
                        leader = req_leader.pop(req_id)
                        if leader not in leader_latency:
                            leader_latency[leader] = []
                        leader_latency[leader].append(latency)
                        req_latency.pop(req_id)
                
                # Capture received response lines to get leader info.
                rcv_match = received_pattern.search(line)
                if rcv_match:
                    leader_ip = rcv_match.group(1)
                    req_id = int(rcv_match.group(2))
                    req_leader[req_id] = leader_ip
                    if req_id in req_latency:
                        latency = req_latency.pop(req_id)
                        if leader_ip not in leader_latency:
                            leader_latency[leader_ip] = []
                        leader_latency[leader_ip].append(latency)
                        req_leader.pop(req_id)
    except Exception as e:
        print(f"Error reading file {filename}: {e}")
        sys.exit(1)

    if not times:
        print("No response times found in file.")
        sys.exit(1)

    # Overall Response Time Statistics.
    avg, std_dev = compute_stats(times)
    print("Overall Response Time Statistics:")
    print("  Average response time: {:.3f} ms".format(avg))
    print("  Standard deviation:    {:.3f} ms".format(std_dev))
    
    overall_duration = 0

    # Per-leader throughput and total running time.
    print("\nPer-Leader Throughput:")
    for leader, stats in leader_throughput.items():
        commits = stats["commits"]
        duration = stats["duration"]
        throughput = commits / duration if duration > 0 else float('inf')
        print("  Leader {}: Total commits = {}, Total duration = {:.6f} seconds, Throughput = {:.3f} requests/second"
              .format(leader, commits, duration, throughput))
        overall_duration += duration
        
    print("\nOverall Duration: {:.6f} seconds".format(overall_duration))
    
    # Per-leader response latency statistics.
    print("\nPer-Leader Response Latency:")
    for leader, latencies in leader_latency.items():
        if latencies:
            avg_latency, std_latency = compute_stats(latencies)
            count = len(latencies)
            print("  Leader {}: {} responses, Average latency = {:.3f} ms, Std Dev = {:.3f} ms"
                  .format(leader, count, avg_latency, std_latency))
        else:
            print("  Leader {}: No latency data available.".format(leader))

if __name__ == "__main__":
    main()
