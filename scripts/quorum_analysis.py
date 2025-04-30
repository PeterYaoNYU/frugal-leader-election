#!/usr/bin/env python3
import sys
import re
from collections import Counter

def count_quorum_nodes(logfile_path):
    # Pattern to capture everything after "with quorum size: <n> "
    quorum_re = re.compile(r'with quorum size:\s*\d+\s+(.+)$')
    counts = Counter()

    with open(logfile_path, 'r') as f:
        for line in f:
            match = quorum_re.search(line)
            if not match:
                continue
            # split the remainder by whitespace to get the IPs
            nodes = match.group(1).split()
            counts.update(nodes)

    return counts

def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <log_file>")
        sys.exit(1)

    logfile = sys.argv[1]
    counts = count_quorum_nodes(logfile)

    print("Quorum membership counts:")
    for node, cnt in counts.most_common():
        print(f"{node}: {cnt}")

if __name__ == "__main__":
    main()
