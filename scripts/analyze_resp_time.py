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
    Format:  IYYYYMMDD HH:MM:SS.microseconds
              I20250422 13:17:15.987910
    """
    m = re.match(r"I(\d{8}) (\d{2}:\d{2}:\d{2}\.\d+)", line)
    if m:
        return datetime.strptime(
            f"{m.group(1)} {m.group(2)}", "%Y%m%d %H:%M:%S.%f"
        )
    return None


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <log_file>")
        sys.exit(1)

    filename = sys.argv[1]

    # ──────────────────────────────────────────────────────────────────────────
    # Regex for the new unified “Received ClientResponse” line
    # Captures: latency, success flag, leader‑IP, request‑id
    # Example line:
    # … Received ClientResponse: latency= 6.782, success=1, from=127.0.0.4,
    #     response="Command committed successfully.", … request_id=13 …
    # ──────────────────────────────────────────────────────────────────────────
    rcv_re = re.compile(
        r"Received ClientResponse:\s*latency=\s*([\d.]+),\s*success=(\d),\s*"
        r"from=([\d.]+).*request_id=(\d+)"
    )

    # Optional explicit text still present in the line – used to count commits
    committed_text = "Command committed successfully."

    # Leadership‑section markers (unchanged)
    begin_leader_re = re.compile(r"Begin of Leadership under: ([\d.]+)")
    end_leader_re = re.compile(r"End of Leadership under: ([\d.]+)")

    # ──────────────────────────────────────────────────────────────────────────
    # Accumulators
    # ──────────────────────────────────────────────────────────────────────────
    overall_latencies = []               # all successful latencies
    per_leader_latencies = {}            # {leader_ip: [latencies]}
    successful_commits = 0               # total committed requests

    leader_throughput = {}               # {leader_ip: {"commits": c, "duration": s}}
    active_leader = None                 # current leader ip in section
    section_start = None                 # datetime when section began
    section_commits = 0                  # commits in current section

    begin_ts = end_ts = None

    # ──────────────────────────────────────────────────────────────────────────
    # Parse file
    # ──────────────────────────────────────────────────────────────────────────
    try:
        with open(filename, "r") as f:
            for line in f:
                ts = parse_timestamp(line)
                if ts:
                    if begin_ts is None:
                        begin_ts = ts
                    end_ts = ts

                # Start of a leadership section
                m = begin_leader_re.search(line)
                if m and ts:
                    # close any previous section first
                    if active_leader is not None:
                        dur = (ts - section_start).total_seconds()
                        leader_throughput.setdefault(active_leader,
                                                     {"commits": 0, "duration": 0.0})
                        leader_throughput[active_leader]["commits"] += section_commits
                        leader_throughput[active_leader]["duration"] += dur
                    active_leader = m.group(1)
                    section_start = ts
                    section_commits = 0
                    continue

                # End of a leadership section
                m = end_leader_re.search(line)
                if m and active_leader and ts:
                    dur = (ts - section_start).total_seconds()
                    leader_throughput.setdefault(active_leader,
                                                 {"commits": 0, "duration": 0.0})
                    leader_throughput[active_leader]["commits"] += section_commits
                    leader_throughput[active_leader]["duration"] += dur
                    active_leader = section_start = None
                    section_commits = 0
                    continue

                # Parse the “Received ClientResponse” line
                m = rcv_re.search(line)
                if not m:
                    continue

                latency_ms = float(m.group(1))
                success_flag = m.group(2) == "1"
                leader_ip = m.group(3)
                # request_id = int(m.group(4))   # not used, but captured if needed

                # Consider only successful commits
                if success_flag:
                    successful_commits += 1
                    overall_latencies.append(latency_ms)
                    per_leader_latencies.setdefault(leader_ip, []).append(latency_ms)

                    if active_leader is not None:
                        section_commits += 1

    except Exception as e:
        print(f"Error reading {filename}: {e}")
        sys.exit(1)

    # ──────────────────────────────────────────────────────────────────────────
    # Report
    # ──────────────────────────────────────────────────────────────────────────
    if not overall_latencies:
        print("No successful commits with latency data found.")
        sys.exit(0)

    avg, std = compute_stats(overall_latencies)
    print("Overall Response‑Time Statistics:")
    print(f"  Average latency : {avg:.3f} ms")
    print(f"  Std deviation   : {std:.3f} ms")

    total_runtime = (end_ts - begin_ts).total_seconds() if begin_ts and end_ts else 0
    print(f"\nOverall Duration           : {total_runtime:.6f} seconds")
    print(f"Overall Committed Requests : {successful_commits}")
    if total_runtime > 0:
        print(f"Overall Throughput         : "
              f"{successful_commits / total_runtime:.3f} req/s")

    # Close last leadership section if file ended without explicit “End…”
    if active_leader and section_start and end_ts:
        dur = (end_ts - section_start).total_seconds()
        leader_throughput.setdefault(active_leader,
                                     {"commits": 0, "duration": 0.0})
        leader_throughput[active_leader]["commits"] += section_commits
        leader_throughput[active_leader]["duration"] += dur

    print("\nPer‑Leader Throughput:")
    for leader, stat in leader_throughput.items():
        c, d = stat["commits"], stat["duration"]
        thr = c / d if d > 0 else float("inf")
        print(f"  {leader:15}  commits={c:<6}  duration={d:.3f}s  thr={thr:.3f} req/s")

    print("\nPer‑Leader Latency Stats:")
    for leader, lats in per_leader_latencies.items():
        a, s = compute_stats(lats)
        print(f"  {leader:15}  samples={len(lats):<5}  avg={a:.3f} ms  std={s:.3f} ms")


if __name__ == "__main__":
    main()
