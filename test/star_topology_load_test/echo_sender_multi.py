#!/usr/bin/env python3
"""
sender.py

This program sends UDP packets concurrently to five remote servers at a fixed rate
(for each server) and uses a separate thread to receive replies and compute RTT
for each packet. Each packet is 1400 bytes in size and contains a 4-byte packet ID.
The echo server running on each remote host is assumed to trim the reply to only the
packet ID. At the end, the program reports separate average RTT statistics for each server.

The five servers have IP addresses ranging from 10.0.1.2 to 10.0.5.2 on port 9999.
"""

import socket
import time
import struct
import threading

import argparse

# List of target servers as tuples: (IP, port)
server_ips = [
    "10.0.4.2",
    "10.0.5.2",
    "10.0.1.2",
    "10.0.2.2",
    "10.0.3.2",
]

# A lock to protect access to the shared dictionaries.
global_lock = threading.Lock()

def sending_thread(sock, rate_mbps, duration, server_addr, packet_size=1400):
    """
    Sends UDP packets at a fixed rate for a specified duration to a given server.
    
    Each packet contains a 4-byte packet ID (big-endian unsigned integer). Before sending,
    the send timestamp is recorded in a global dictionary under the server's IP.
    
    Parameters:
      sock       - a UDP socket (shared among threads)
      rate_mbps  - desired sending rate in Mbps (for this destination)
      duration   - test duration in seconds
      server_addr- tuple (IP, port) of the target server
      packet_size- total packet size in bytes (default: 1400)
    """
    server_ip, server_port = server_addr
    start_time = time.time()
    seq = 0
    # Calculate the number of packets per second for this server.
    # (rate in bits/sec) = rate_mbps * 1e6, and each packet is packet_size * 8 bits.
    packets_per_sec = (rate_mbps * 1e6) / (packet_size * 8)
    delay_between = 1.0 / packets_per_sec
    next_send_time = start_time

    while time.time() - start_time < duration:
        now = time.time()
        # Record the send time for this sequence number for the given server.
        with global_lock:
            send_times[server_ip][seq] = now

        # Build the packet: first 4 bytes = packet ID, padded to packet_size.
        packet = struct.pack("!I", seq) + b'\x00' * (packet_size - 4)
        try:
            sock.sendto(packet, server_addr)
        except Exception as e:
            print(f"Error sending packet {seq} to {server_ip}:{server_port}: {e}")

        seq += 1
        next_send_time += delay_between
        sleep_time = next_send_time - time.time()
        if sleep_time > 0:
            time.sleep(sleep_time)

    print(f"Sending thread for {server_ip} finished. Sent {seq} packets.")

def receiving_thread(sock):
    """
    Receives UDP replies from any of the echo servers.
    
    Each reply contains a 4-byte packet ID. Using the source address from the reply,
    the thread retrieves the corresponding send timestamp from the global dictionary,
    computes the RTT, and appends it to the corresponding RTT list.
    """
    sock.settimeout(1)  # Use a short timeout so we can eventually exit.
    while True:
        try:
            data, addr = sock.recvfrom(1024)
        except socket.timeout:
            # No data for 1 second; assume sending is done and exit.
            break
        except Exception as e:
            print("Receiving error:", e)
            break

        if len(data) < 4:
            continue

        # Unpack the 4-byte packet ID.
        packet_id, = struct.unpack("!I", data[:4])
        recv_time = time.time()
        server_ip = addr[0]

        with global_lock:
            # Look up and remove the send time for this packet from the dictionary.
            send_time = send_times.get(server_ip, {}).pop(packet_id, None)
        if send_time is not None:
            rtt = recv_time - send_time
            with global_lock:
                rtts[server_ip].append(rtt)
            print(f"Server {server_ip}: Packet {packet_id} RTT: {rtt*1000:.2f} ms")
        else:
            print(f"Server {server_ip}: Received reply for packet {packet_id} (no send time recorded)")
    print("Receiving thread finished.")

def main():
    parser = argparse.ArgumentParser(description="UDP Sender for Multiple Echo Servers")
    parser.add_argument("port", type=int, nargs="?", default=9999,
                        help="Port on which the echo servers listen (default: 9999)")
    
    parser.add_argument("rate", type=float, default=0.12,
                        help="Sending rate in Mbps (default: 0.12)")
    args = parser.parse_args()

    # Build the server list using the provided port.
    server_list = [(ip, args.port) for ip in server_ips]

    # Initialize the global dictionaries based on the server IPs.
    global send_times, rtts
    send_times = {ip: {} for ip in server_ips}
    rtts = {ip: [] for ip in server_ips}
    
    
    # Test parameters.
    rate_mbps = args.rate         # Sending rate in Mbps for each server.
    duration = 120         # Test duration in seconds (2 minutes).
    packet_size = 1400     # Packet size in bytes.

    # Create a UDP socket and bind it so that replies come back to the same port.
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('', 0))  # Let the OS assign an ephemeral port.
    local_addr = sock.getsockname()
    print(f"Sender socket bound to {local_addr}")

    # Create a sending thread for each server.
    send_threads = []
    for server_addr in server_list:
        t = threading.Thread(target=sending_thread, args=(sock, rate_mbps, duration, server_addr, packet_size))
        send_threads.append(t)

    # Create the receiving thread.
    recv_thread = threading.Thread(target=receiving_thread, args=(sock,))

    # Start all sending threads.
    for t in send_threads:
        t.start()
    # Start the receiving thread.
    recv_thread.start()

    # Wait for all sending threads to finish.
    for t in send_threads:
        t.join()

    # Allow some extra time for late replies.
    time.sleep(5)
    # Close the socket to force the receiver thread to exit.
    sock.close()
    recv_thread.join()

    # Report per-server RTT statistics.
    print("\nTest completed. RTT summary per server:")
    with global_lock:
        for server_ip in sorted(rtts.keys()):
            server_rtts = rtts[server_ip]
            if server_rtts:
                avg_rtt = sum(server_rtts) / len(server_rtts)
                min_rtt = min(server_rtts)
                max_rtt = max(server_rtts)
                print(f"Server {server_ip}: Packets received: {len(server_rtts)} | "
                      f"Avg RTT = {avg_rtt*1000:.2f} ms, Min RTT = {min_rtt*1000:.2f} ms, Max RTT = {max_rtt*1000:.2f} ms")
            else:
                print(f"Server {server_ip}: No RTT data available.")

if __name__ == "__main__":
    main()
