#!/usr/bin/env python3
import sys

def count_leader(filename):
    count = 0
    try:
        with open(filename, 'r') as file:
            for line in file:
                if "Became leader." in line:
                    count += 1
    except FileNotFoundError:
        print(f"Error: The file '{filename}' was not found.")
        sys.exit(1)
    except IOError as e:
        print(f"Error reading file '{filename}': {e}")
        sys.exit(1)
    return count

def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <log_filename>")
        sys.exit(1)

    filename = sys.argv[1]
    leader_count = count_leader(filename)
    print(f"Times node became leader: {leader_count}")

if __name__ == "__main__":
    main()
