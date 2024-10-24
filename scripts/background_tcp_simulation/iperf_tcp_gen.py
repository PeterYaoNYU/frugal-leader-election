#!/usr/bin/env python3

import os
import subprocess
import sys
from invoke import task

# Number of TCP connections per pair (adjustable)
NUM_CONNECTIONS = 2

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
    for k in range(NUM_CONNECTIONS):
        port = 5000 + k
        cmd = ['iperf3', '-s', '-p', str(port), '-B', server_ip, '-D']
        print(f"Starting iperf3 server on {server_ip}:{port}")
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# Function to start iperf3 clients to other nodes
def start_iperf3_clients(node_num):
    for target_node in range(node_num + 1, TOTAL_NODES + 1):
        remote_host = f'10.0.{target_node}.2'
        for k in range(NUM_CONNECTIONS):
            port = 5000 + k
            cmd = [
                'iperf3', '-c', remote_host, '-p', str(port),
                '-t', '0',  # Run indefinitely
                '-P', '1',   # Number of parallel client streams
                '-b', '1M'  # Limit bandwidth to 10 Mbps
            ]
            print(f"Starting iperf3 client to {remote_host} on port {port} with bandwidth limit of 1 Mbps")
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def main():
    if len(sys.argv) != 2:
        print("Usage: ./iperf_tcp_gen.py <node_id>")
        sys.exit(1)

    try:
        node_num = int(sys.argv[1])
        if node_num < 1 or node_num > TOTAL_NODES:
            raise ValueError("Node ID must be between 1 and 5.")
    except ValueError as e:
        print(e)
        sys.exit(1)

    install_iperf3()
    start_iperf3_servers(node_num)
    start_iperf3_clients(node_num)
    print("All iperf3 servers and clients have been started.")

if __name__ == '__main__':
    main()