#!/usr/bin/env python3
"""
remote_count_timeouts.py

Count "Election timeout occurred. Starting leader election" events
in a Raft log, excluding the first N seconds **and** the last M seconds.

Usage (on the remote host)
--------------------------
    python3 remote_count_timeouts.py  path/to/node.log \
           --skip-first 30 --skip-last 10 \
           --out timeout_count.txt
"""
import argparse
import re
import sys
from datetime import datetime, timedelta

PATTERN = re.compile(
    r"Election timeout occurred\. Starting leader election"
)
TS_RE = re.compile(r"^I(\d{8})\s+(\d{2}:\d{2}:\d{2}\.\d{6})")

def parse_ts(line):
    m = TS_RE.match(line)
    if not m:
        return None
    return datetime.strptime(
        f"{m.group(1)} {m.group(2)}", "%Y%m%d %H:%M:%S.%f"
    )

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("logfile",
                    help="path to the log file")
    ap.add_argument("--skip-first", type=int, default=30,
                    help="seconds to skip from start (default: 30)")
    ap.add_argument("--skip-last",  type=int, default=0,
                    help="seconds to skip before end (default: 0)")
    ap.add_argument("--out", default="timeout_count.txt",
                    help="output file (default: timeout_count.txt)")
    args = ap.parse_args()

    # Read all lines
    with open(args.logfile, "r", encoding="utf-8") as f:
        lines = f.readlines()

    if not lines:
        sys.exit("Empty log.")

    # First pass: find first_ts and last_ts
    first_ts = None
    last_ts  = None
    for ln in lines:
        ts = parse_ts(ln)
        if ts:
            if first_ts is None:
                first_ts = ts
            last_ts = ts

    if first_ts is None or last_ts is None:
        sys.exit("No valid timestamps found.")

    # Second pass: count after skip-first and before skip-last
    count = 0
    for ln in lines:
        ts = parse_ts(ln)
        if not ts:
            continue

        # skip from start
        if ts - first_ts < timedelta(seconds=args.skip_first):
            continue
        # skip before end
        if last_ts - ts   < timedelta(seconds=args.skip_last):
            continue

        if PATTERN.search(ln):
            count += 1

    # Write result
    with open(args.out, "w") as f:
        f.write(f"{count}\n")

    print(f"✓ {count} timeouts (skipped first {args.skip_first}s and last {args.skip_last}s) → {args.out}")


if __name__ == "__main__":
    main()
