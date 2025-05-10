#!/usr/bin/env python3
"""
remote_count_timeouts.py

Count "Election timeout occurred. Starting leader election" events
in a Raft log, **excluding the first N seconds** (default 30).

Usage (on the remote host)
--------------------------
    python3 remote_count_timeouts.py  path/to/node.log \
           --skip 30 --out timeout_count.txt
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
    ap.add_argument("logfile")
    ap.add_argument("--skip", type=int, default=30,
                    help="seconds to skip from start (default 30)")
    ap.add_argument("--out", default="timeout_count.txt",
                    help="output file (default timeout_count.txt)")
    args = ap.parse_args()

    with open(args.logfile, "r", encoding="utf-8") as f:
        lines = f.readlines()

    if not lines:
        sys.exit("Empty log.")

    first_ts = None
    count = 0

    for ln in lines:
        ts = parse_ts(ln)
        if ts and first_ts is None:
            first_ts = ts

        # only evaluate after we know first_ts
        if first_ts is None:
            continue

        # skip first N seconds
        if ts and ts - first_ts < timedelta(seconds=args.skip):
            continue

        if PATTERN.search(ln):
            count += 1

    with open(args.out, "w") as f:
        f.write(f"{count}\n")

    print(f"✓ {count} timeouts (≥{args.skip}s) → {args.out}")

if __name__ == "__main__":
    main()
