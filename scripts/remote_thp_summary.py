#!/usr/bin/env python3
"""
remote_thp_summary.py   (revised)

Create a per‑second throughput CSV from a single client log.

  Usage (on the remote host)
  --------------------------
      python remote_thp_summary.py  client.log  --out thp_summary.csv

The CSV columns are:
    timestamp, throughput_req_per_sec

• Only success=1 lines are used.
• The first and last N seconds of traffic (default 10 s) are dropped
  to ignore warm‑up / cool‑down.
• “timestamp” is written exactly once per bucket in the same
  human‑readable format seen in the log (YYYY‑MM‑DD HH:MM:SS).
"""

import argparse
import re
import sys
from collections import defaultdict, OrderedDict
from datetime import datetime, timedelta

# ----------------------------------------------------------------------
RE_LINE = re.compile(
    r"""^I(\d{8})\s+(\d{2}:\d{2}:\d{2}\.\d{6})\s
        .*?Received\ ClientResponse:
        .*?\bsuccess=1\b
    """,
    re.VERBOSE,
)


def parse_success_timestamps(logpath):
    """Yield datetime objects for every success=1 response line."""
    with open(logpath, "r", encoding="utf-8") as f:
        for ln in f:
            m = RE_LINE.search(ln)
            if not m:
                continue
            date_part, time_part = m.groups()
            yield datetime.strptime(f"{date_part} {time_part}",
                                    "%Y%m%d %H:%M:%S.%f")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("logfile", help="client log file")
    ap.add_argument("--out", default="thp_summary.csv",
                    help="output CSV (default: thp_summary.csv)")
    ap.add_argument("--trim", type=int, default=10,
                    help="seconds to trim from start & end (default 10)")
    args = ap.parse_args()

    ts = sorted(parse_success_timestamps(args.logfile))
    if not ts:
        sys.exit("No successful responses found.")

    # Trim first/last N seconds
    start_ok = ts[0] + timedelta(seconds=args.trim)
    end_ok   = ts[-1] - timedelta(seconds=args.trim)
    ts = [t for t in ts if start_ok <= t <= end_ok]
    if not ts:
        sys.exit("All samples trimmed away.")

    per_sec = defaultdict(int)
    for t in ts:
        bucket = t.replace(microsecond=0)          # truncate to nearest second
        per_sec[bucket] += 1

    per_sec = OrderedDict(sorted(per_sec.items()))

    # Write CSV
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("timestamp,throughput\n")
        for dt, count in per_sec.items():
            f.write(f"{dt.strftime('%Y-%m-%d %H:%M:%S')},{count}\n")

    print(f"✓ Wrote {args.out} ({len(per_sec)} rows)")


if __name__ == "__main__":
    main()
