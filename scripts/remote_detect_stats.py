#!/usr/bin/env python3
"""
remote_detect_stats.py

Extract detection‑time values from a Raft log and compute basic stats,
skipping the first/last N seconds of the log.

Detection time is the *first* float (ms) that appears in a line like:
  Using Jacobson estimation for election timeout: 267.512 Milliseconds ...

Output (default detect_stats.txt) is a single line:
    count mean_ms std_ms
"""
import argparse
import re
import statistics as st
import sys
from datetime import datetime, timedelta

# Regexes
PAT_LINE = re.compile(
    r"Using Jacobson estimation for election timeout:\s+([0-9.]+)\s+Milliseconds",
)
TS_RE = re.compile(r"^I(\d{8})\s+(\d{2}:\d{2}:\d{2}\.\d{6})")

def parse_ts(line):
    m = TS_RE.match(line)
    if not m:
        return None
    return datetime.strptime(f"{m.group(1)} {m.group(2)}",
                             "%Y%m%d %H:%M:%S.%f")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("logfile")
    ap.add_argument("--skip-first", type=int, default=30,
                    help="seconds to skip from start (default 30)")
    ap.add_argument("--skip-last",  type=int, default=0,
                    help="seconds to skip from end (default 0)")
    ap.add_argument("--out", default="detect_stats.txt",
                    help="output file (default detect_stats.txt)")
    args = ap.parse_args()

    with open(args.logfile, encoding="utf-8") as f:
        lines = f.readlines()
    if not lines:
        sys.exit("Empty log.")

    # Determine first/last timestamps
    first_ts = last_ts = None
    for ln in lines:
        ts = parse_ts(ln)
        if ts:
            first_ts = ts if first_ts is None else first_ts
            last_ts  = ts

    if first_ts is None or last_ts is None:
        sys.exit("No timestamps found.")

    low_cut  = first_ts + timedelta(seconds=args.skip_first)
    high_cut = last_ts  - timedelta(seconds=args.skip_last)

    # Collect detection times (ms)
    samples = []
    for ln in lines:
        ts = parse_ts(ln)
        if not ts or not (low_cut <= ts <= high_cut):
            continue
        m = PAT_LINE.search(ln)
        if m:
            samples.append(float(m.group(1)))

    if samples:
        mean_ms = st.mean(samples)
        std_ms  = st.pstdev(samples) if len(samples) > 1 else 0.0
    else:
        mean_ms = std_ms = 0.0

    with open(args.out, "w") as f:
        f.write(f"{len(samples)} {mean_ms:.6f} {std_ms:.6f}\n")

    print(f"✓ wrote {len(samples)} samples → {args.out}")

if __name__ == "__main__":
    main()
