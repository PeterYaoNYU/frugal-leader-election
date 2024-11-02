import re
import os
from pathlib import Path
from collections import defaultdict

def analyze_logs(folder_path):
    timeout_values = []
    additional_delay_values = []

    # Define the regular expression pattern to match the timeout and additional delay values
    pattern = re.compile(r'Using Jacobson estimation for election timeout: ([\d.]+) Milliseconds, additional delay: (\d+) Milliseconds')

    # Traverse all log files in the folder
    for log_file in Path(folder_path).glob("*.log"):
        print(f"Processing {log_file}...")
        with open(log_file, 'r') as f:
            for line in f:
                # print(line)
                match = pattern.search(line)
                if match:
                    # print(f"Matched line: {line.strip()}")
                    # Extract timeout and additional delay from the matched line
                    timeout = float(match.group(1)) * 1000
                    additional_delay = int(match.group(2))
                    timeout_values.append(timeout)
                    additional_delay_values.append(additional_delay)

    # Calculate mean timeout and mean additional delay
    mean_timeout = sum(timeout_values) / len(timeout_values) if timeout_values else 0
    mean_additional_delay = sum(additional_delay_values) / len(additional_delay_values) if additional_delay_values else 0

    # Calculate percentage breakdown of the additional delay in the timeout
    delay_percentage = (mean_additional_delay / mean_timeout * 100) if mean_timeout else 0
    timeout_percentage = 100 - delay_percentage

    # Display the results
    print("Analysis Results:")
    print(f"Mean Timeout: {mean_timeout:.3f} ms")
    print(f"Mean Additional Delay: {mean_additional_delay:.3f} ms")
    print(f"Percentage Breakdown:")
    print(f"  Timeout Component: {timeout_percentage:.2f}%")
    print(f"  Additional Delay Component: {delay_percentage:.2f}%")

# Example usage
folder_path = "./downloaded_logs/20241102_144713"  # Specify your folder path containing log files here
analyze_logs(folder_path)
