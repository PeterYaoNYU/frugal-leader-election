#!/usr/bin/env python3
"""
sender.py

This program sends UDP packets concurrently to five remote servers at a fixed rate
(for each server) and uses separate threads (each with its own socket) to receive
replies and compute RTT for each packet. Each packet is 1400 bytes in size and
contains a 4-byte packet ID. The echo server running on each remote host is assumed
to trim the reply to only the packet ID. At the end, the program reports separate
average RTT statistics for each server.

The five servers have IP addresses ranging from 10.0.1.2 to 10.0.5.2 on a specified port.
"""

import socket
import time
import struct
import threading
import argparse

# List of server IP addresses (without port)
server_ips = [
    "10.0.4.2",
    "10.0.5.2",
    "10.0.1.2",
    "10.0.2.2",
    "10.0.3.2",
]

### CHANGED:
# We no longer use global dictionaries shared across all threads.
# Each server test will have its own local send_times and RTT list.

def run_server_test(server_addr, rate_mbps, duration, packet_size=1400):
    """
    Runs the send/receive test for one server.
    
    This function creates its own UDP socket, local dictionaries, and spawns
    separate sending and receiving threads that share the same socket.
    
    Returns the list of measured RTTs for this server.
    """
    server_ip, server_port = server_addr
    # Create a dedicated UDP socket for this server.
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('', 0))  # Let the OS choose an ephemeral port.
    local_addr = sock.getsockname()
    print(f"[{server_ip}] Socket bound to {local_addr}")

    # Local dictionaries and lock for this server.
    local_send_times = {}   # mapping seq -> send timestamp
    local_rtts = []         # list of RTTs for this server
    lock = threading.Lock()

    def send_thread():
        seq = 0
        start_time = time.time()
        packets_per_sec = (rate_mbps * 1e6) / (packet_size * 8)
        delay_between = 1.0 / packets_per_sec
        next_send_time = start_time

        while time.time() - start_time < duration:
            now = time.time()
            with lock:
                local_send_times[seq] = now
            # Build packet: first 4 bytes are packet ID, padded to packet_size.
            packet = struct.pack("!I", seq) + b'\x00' * (packet_size - 4)
            try:
                sock.sendto(packet, server_addr)
            except Exception as e:
                print(f"[{server_ip}] Error sending packet {seq}: {e}")
            seq += 1
            next_send_time += delay_between
            sleep_time = next_send_time - time.time()
            if sleep_time > 0:
                time.sleep(sleep_time)
        print(f"[{server_ip}] Sending thread finished. Sent {seq} packets.")

    def recv_thread():
        sock.settimeout(1)
        while True:
            try:
                data, addr = sock.recvfrom(1024)
            except socket.timeout:
                # No data for 1 second; assume sending is done.
                break
            except Exception as e:
                print(f"[{server_ip}] Receiving error: {e}")
                break

            if len(data) < 4:
                continue
            packet_id, = struct.unpack("!I", data[:4])
            recv_time = time.time()
            with lock:
                send_time = local_send_times.pop(packet_id, None)
            if send_time is not None:
                rtt = recv_time - send_time
                with lock:
                    local_rtts.append(rtt)
                print(f"[{server_ip}] Packet {packet_id} RTT: {rtt*1000:.2f} ms")
            else:
                print(f"[{server_ip}] Received reply for packet {packet_id} (no send time recorded)")
        print(f"[{server_ip}] Receiving thread finished.")

    # Create threads for sending and receiving.
    t_send = threading.Thread(target=send_thread)
    t_recv = threading.Thread(target=recv_thread)
    t_send.start()
    t_recv.start()
    t_send.join()
    # Allow extra time for late replies.
    time.sleep(5)
    sock.close()
    t_recv.join()
    return local_rtts

def main():
    parser = argparse.ArgumentParser(description="UDP Sender for Multiple Echo Servers (Separate Sockets per Server)")
    parser.add_argument("port", type=int, nargs="?", default=9999,
                        help="Port on which the echo servers listen (default: 9999)")
    parser.add_argument("rate", type=float, nargs="?", default=0.12,
                        help="Sending rate in Mbps for each server (default: 0.12)")
    args = parser.parse_args()

    # Build server list using the provided port.
    server_list = [(ip, args.port) for ip in server_ips]

    # Test parameters.
    duration = 60      # Test duration in seconds (2 minutes)
    packet_size = 1400  # Packet size in bytes

    # For each server, start the test concurrently in a separate thread.
    results = {}   # Map server IP -> list of RTTs
    threads = []

    def test_for_server(server_addr):
        ip = server_addr[0]
        rtts = run_server_test(server_addr, args.rate, duration, packet_size)
        results[ip] = rtts

    for server_addr in server_list:
        t = threading.Thread(target=test_for_server, args=(server_addr,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    # Report per-server RTT statistics.
    print("\nTest completed. RTT summary per server:")
    for server_ip in sorted(results.keys()):
        server_rtts = results[server_ip]
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
