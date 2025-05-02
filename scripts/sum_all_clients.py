#!/usr/bin/env python3
import sys
import re

def parse_file(path):
    """
    Returns (throughput, avg_latency) parsed from the given file,
    or (None, None) if parsing fails.
    """
    content = open(path, 'r').read()
    tp_m = re.search(r"Overall Throughput\s*:\s*([0-9.]+)\s*req/s", content)
    lat_m = re.search(r"Average latency\s*:\s*([0-9.]+)\s*ms", content)
    if not tp_m or not lat_m:
        return None, None
    return float(tp_m.group(1)), float(lat_m.group(1))

def main():
    # if len(sys.argv) != 6:
    #     print(f"Usage: {sys.argv[0]} <file1> <file2> <file3> <file4> <file5>")
    #     sys.exit(1)

    total_tp = 0.0
    weighted_lat_sum = 0.0
    
    files = ["client_remote_0.log", "client_remote_1.log", "client_remote_2.log", "client_remote_3.log", "client_remote_4.log"]

    for path in files:
        tp, lat = parse_file(path)
        if tp is None:
            print(f"Warning: could not parse '{path}'")
            continue
        total_tp += tp
        weighted_lat_sum += lat * tp

    if total_tp <= 0:
        print("No valid throughput data found.")
    else:
        weighted_avg_lat = weighted_lat_sum / total_tp
        print(f"Total throughput:          {total_tp:.3f} req/s")
        print(f"Weighted average latency: {weighted_avg_lat:.3f} ms")

if __name__ == "__main__":
    main()
