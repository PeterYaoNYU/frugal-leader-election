#!/usr/bin/env python3
"""
merge_thp_summaries.py

Merge per‑second throughput CSVs from several nodes, add them,
and plot the combined throughput curve.

  Usage (on your workstation)
  ---------------------------
      python merge_thp_summaries.py  node*.csv \
             --plot combined_throughput.png    \
             --csv  combined_throughput.csv

• Any number of summary files may be given as positional arguments.
• The x‑axis is *relative seconds* since the earliest epoch_second
  appearing in any file.
"""

import argparse
import csv
import sys
from collections import defaultdict, OrderedDict

import matplotlib.pyplot as plt


def read_summary(path):
    """Return {epoch_second:int → throughput:int} from one CSV."""
    d = {}
    with open(path, newline="") as f:
        rdr = csv.DictReader(f)
        for row in rdr:
            d[int(row["epoch_second"])] = int(row["throughput"])
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
        for sec, thp in data.items():
            merged[sec] += thp

    if not merged:
        sys.exit("No data to merge.")

    merged = OrderedDict(sorted(merged.items()))
    first_sec = next(iter(merged))
    rel_times = [sec - first_sec for sec in merged]
    thp_vals  = list(merged.values())

    # Plot
    fig, ax = plt.subplots()
    ax.plot(rel_times, thp_vals, linewidth=1.5)
    ax.set_title("Combined Throughput (all nodes)")
    ax.set_xlabel("Time since earliest sample (s)")
    ax.set_ylabel("Requests / second (sum)")
    ax.grid(True, linestyle="--", alpha=0.3)
    fig.tight_layout()
    fig.savefig(args.plot)
    print(f"✓ Plot saved to {args.plot}")

    # Optional merged CSV
    if args.csv:
        with open(args.csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["relative_second", "throughput"])
            w.writerows(zip(rel_times, thp_vals))
        print(f"✓ Merged CSV saved to {args.csv}")


if __name__ == "__main__":
    main()
