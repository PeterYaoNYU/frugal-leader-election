#!/usr/bin/env python3
"""
Count how many times a node became leader in a log file.

Usage:
    ./count_leaders.py <logfile>

It looks for lines that contain the phrase
"Received enough votes to become leader" (case‑insensitive).
"""

import re
import sys

PATTERN = re.compile(r"Received enough votes to become leader", re.IGNORECASE)


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <logfile>")
        sys.exit(1)

    log_file = sys.argv[1]
    try:
        with open(log_file, "r") as f:
            count = sum(1 for line in f if PATTERN.search(line))
    except FileNotFoundError:
        print(f"Error: file '{log_file}' not found")
        sys.exit(1)

    print(f"Leader elections: {count}")


if __name__ == "__main__":
    main()
