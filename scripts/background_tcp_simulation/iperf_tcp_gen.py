#!/usr/bin/env python3

# ****************************************************
# ****************************************************
# Note: This file is not correct, still need debugging
# ****************************************************
# ****************************************************

import os
import subprocess
import sys
from invoke import task
from fabric import Connection

# Number of TCP connections per pair (adjustable)
NUM_CONNECTIONS = 4  # Adjusted to 4 servers per node

# Total number of spoke nodes
TOTAL_NODES = 5

# Function to install iperf3 if not installed
def install_iperf3():
    try:
        subprocess.run(['iperf3', '--version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("iperf3 is already installed.")
    except FileNotFoundError:
        print("iperf3 not found. Installing iperf3...")
        subprocess.run(['sudo', 'apt-get', 'update'], check=True)
        subprocess.run(['sudo', 'apt-get', 'install', '-y', 'iperf3'], check=True)
        print("iperf3 installation completed.")

# Function to start iperf3 servers on multiple ports
def start_iperf3_servers(node_num):
    server_ip = f"10.0.{node_num}.2"
    for k in range(1, TOTAL_NODES + 1):
        port = 5000 + k
        cmd = ['iperf3', '-s', '-p', str(port), '-B', server_ip, '-D']
        print(f"Starting iperf3 server on {server_ip}:{port}")
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# Function to start iperf3 clients to other nodes
def start_iperf3_clients(node_num):
    for target_node in range(1, TOTAL_NODES + 1):
        if target_node == node_num:
            continue
        remote_host = f'10.0.{target_node}.2'
        port = 5000 + node_num  # Each node connects to a unique port on the remote node
        cmd = [
            'iperf3', '-c', remote_host, '-p', str(port),
            '-t', '0',  # Run indefinitely
            '-P', '1',   # Number of parallel client streams
            '-b', '10K',  # Limit bandwidth to 0.2 Mbps
            '-l', '0.5K'
        ]
        print(f"Starting iperf3 client to {remote_host} on port {port} with bandwidth limit of 0.2 Mbps")
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def main():
    if len(sys.argv) != 3:
        print("Usage: ./iperf_tcp_gen.py <node_id> <mode>")
        print("Mode should be either 'server' or 'client'")
        sys.exit(1)

    try:
        node_num = int(sys.argv[1])
        if node_num < 1 or node_num > TOTAL_NODES:
            raise ValueError("Node ID must be between 1 and 5.")
    except ValueError as e:
        print(e)
        sys.exit(1)

    mode = sys.argv[2].lower()
    # install_iperf3()

    if mode == 'server':
        start_iperf3_servers(node_num)
        print("iperf3 servers have been started.")
    elif mode == 'client':
        start_iperf3_clients(node_num)
        print("iperf3 clients have been started.")
    else:
        print("Invalid mode. Use 'server' or 'client'.")
        sys.exit(1)

if __name__ == '__main__':
    main()