import sys
import re
from statistics import mean

def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <logfile>")
        sys.exit(1)
    logfile = sys.argv[1]
    # Regex to capture sender IP and queue time
    pattern = re.compile(r"Received message from (\d+\.\d+\.\d+\.\d+).*Queue time: (\d+) microseconds")
    
    # Dictionary to accumulate queue times per sender
    times = {}
    
    with open(logfile, 'r') as f:
        for line in f:
            m = pattern.search(line)
            if m:
                ip = m.group(1)
                t = int(m.group(2))
                times.setdefault(ip, []).append(t)
    
    # Print results
    print(f"{'Sender IP':<15} {'Count':>6} {'Average (µs)':>14}")
    print("-" * 37)
    for ip in sorted(times.keys()):
        lst = times[ip]
        avg = mean(lst)
        print(f"{ip:<15} {len(lst):>6} {avg:>14.2f}")

if __name__ == "__main__":
    main()
