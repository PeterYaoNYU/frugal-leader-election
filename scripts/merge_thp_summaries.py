#!/usr/bin/env python3
"""
merge_thp_summaries.py   (revised)

Merge per‑second throughput CSVs from several nodes, add them,
and plot the combined throughput curve on an absolute time axis.

  Usage (on your workstation)
  ---------------------------
      python merge_thp_summaries.py  node*.csv \
             --plot combined_throughput.png    \
             --csv  combined_throughput.csv

• Any number of summary files may be given as positional arguments.
• The x‑axis is the true wall‑clock time (no relative shift).
"""

import argparse
import csv
import sys
from collections import defaultdict, OrderedDict
from datetime import datetime

import matplotlib.pyplot as plt
import matplotlib.dates as mdates


def read_summary(path):
    """Return {datetime → throughput:int} from one CSV."""
    d = {}
    with open(path, newline="") as f:
        rdr = csv.DictReader(f)
        for row in rdr:
            ts = datetime.fromisoformat(row["timestamp"])
            d[ts] = int(row["throughput"])
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_files", nargs="+", help="per‑node summary CSVs")
    ap.add_argument("--plot", default="combined_throughput.png",
                    help="output PNG plot (default: combined_throughput.png)")
    ap.add_argument("--csv", help="also write merged CSV (optional)")
    args = ap.parse_args()

    if len(args.csv_files) < 2:
        sys.exit("Need at least two CSV files to merge.")

    # Collect & sum
    merged = defaultdict(int)
    for path in args.csv_files:
        data = read_summary(path)
        for ts, thp in data.items():
            merged[ts] += thp

    if not merged:
        sys.exit("No data to merge.")

    merged = OrderedDict(sorted(merged.items()))
    times   = list(merged.keys())
    thp_vals = list(merged.values())

    # Plot
    fig, ax = plt.subplots()
    ax.plot(times, thp_vals, linewidth=1.5)
    ax.set_title("Combined Throughput (all nodes)")
    ax.set_xlabel("Time")
    ax.set_ylabel("Requests / second (sum)")
    ax.grid(True, linestyle="--", alpha=0.3)

    # nicer date formatting
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(args.plot)
    print(f"✓ Plot saved to {args.plot}")

    # Optional merged CSV
    if args.csv:
        with open(args.csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["timestamp", "throughput"])
            for ts, val in merged.items():
                w.writerow([ts.strftime('%Y-%m-%d %H:%M:%S'), val])
        print(f"✓ Merged CSV saved to {args.csv}")


if __name__ == "__main__":
    main()
