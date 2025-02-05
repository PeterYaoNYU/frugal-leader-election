#!/usr/bin/env python3
"""
sender.py

This program sends UDP packets at a fixed rate (in Mbps) for a set duration
and uses a separate thread to receive replies and compute RTT for each packet.
Each packet is 1400 bytes in size and contains a 4-byte packet ID. The echo server
(which trims the reply to just the packet ID) is assumed to be running on port 9999.
"""

import socket
import time
import struct
import threading

import argparse

# Global shared data structures.
send_times = {}  # Dictionary mapping packet ID (int) to send timestamp.
send_lock = threading.Lock()  # Lock to protect access to send_times.
rtts = []        # List to store measured RTTs.
rtt_lock = threading.Lock()

def sending_thread(sock, rate_mbps, duration, server_addr, packet_size=1400):
    """
    Sends UDP packets at a fixed rate for the specified duration.
    
    Each packet contains a 4-byte packet ID (big-endian unsigned integer). Before sending,
    the send timestamp is recorded in a shared dictionary.
    """
    start_time = time.time()
    seq = 0
    # Calculate the number of packets per second.
    # (rate in bits/sec) = rate_mbps * 1e6, and each packet is packet_size * 8 bits.
    packets_per_sec = (rate_mbps * 1e6) / (packet_size * 8)
    delay_between = 1.0 / packets_per_sec
    next_send_time = start_time

    while time.time() - start_time < duration:
        now = time.time()
        # Record the send time for this sequence number.
        with send_lock:
            send_times[seq] = now

        # Build the packet: first 4 bytes = packet ID, padded to packet_size.
        packet = struct.pack("!I", seq) + b'\x00' * (packet_size - 4)
        try:
            sock.sendto(packet, server_addr)
        except Exception as e:
            print(f"Error sending packet {seq}: {e}")

        seq += 1
        next_send_time += delay_between
        sleep_time = next_send_time - time.time()
        if sleep_time > 0:
            time.sleep(sleep_time)

    print(f"Sending thread finished. Sent {seq} packets.")

def receiving_thread(sock):
    """
    Receives UDP replies from the echo server. Each reply contains a 4-byte packet ID.
    It then computes the RTT (current time - stored send time) and appends it to a list.
    """
    sock.settimeout(1)  # Use a short timeout so we can exit when done.
    while True:
        try:
            data, addr = sock.recvfrom(1024)
        except socket.timeout:
            # No data for 1 second; assume sending is done.
            break
        except Exception as e:
            print("Receiving error:", e)
            break

        if len(data) < 4:
            continue
        # Unpack the packet ID.
        packet_id, = struct.unpack("!I", data[:4])
        recv_time = time.time()
        with send_lock:
            send_time = send_times.pop(packet_id, None)
        if send_time is not None:
            rtt = recv_time - send_time
            with rtt_lock:
                rtts.append(rtt)
            print(f"Packet {packet_id} RTT: {rtt*1000:.2f} ms")
        else:
            print(f"Received reply for packet {packet_id} (no send time recorded)")
    print("Receiving thread finished.")

def main():
    parser = argparse.ArgumentParser(description="UDP Echo Sender")
    parser.add_argument("ip", type=str,
                        help="IP address of the echo server")
    parser.add_argument("port", type=int, nargs="?", default=9999,
                        help="Port on which the echo server listens (default: 9999)")
    parser.add_argument("rate", type=float, default=0.6,
                        help="Sending rate in Mbps (default: 0.6)")
    args = parser.parse_args()
    
    # Test parameters.
    rate_mbps = args.rate         # Sending rate in Mbps.
    duration = 120         # Test duration in seconds (2 minutes).
    packet_size = 1400     # Packet size in bytes.
    server_addr = (args.ip, args.port)  # Echo server address.

    # Create a UDP socket and bind it (so that replies come back to the same port).
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('', 0))  # Let OS assign an ephemeral port.
    local_addr = sock.getsockname()
    print(f"Sender socket bound to {local_addr}")

    # Start the sending and receiving threads.
    sender = threading.Thread(target=sending_thread, args=(sock, rate_mbps, duration, server_addr, packet_size))
    receiver = threading.Thread(target=receiving_thread, args=(sock,))
    sender.start()
    receiver.start()

    # Wait for the sender to finish.
    sender.join()
    # Allow some extra time for late replies.
    time.sleep(5)
    # Close the socket to force the receiver thread to exit.
    sock.close()
    receiver.join()

    # Print summary statistics.
    with rtt_lock:
        if rtts:
            avg_rtt = sum(rtts) / len(rtts)
            min_rtt = min(rtts)
            max_rtt = max(rtts)
            print("\nTest completed.")
            print(f"Packets received: {len(rtts)}")
            print(f"RTT (ms): Average = {avg_rtt*1000:.2f}, Min = {min_rtt*1000:.2f}, Max = {max_rtt*1000:.2f}")
        else:
            print("No RTT data available.")

if __name__ == "__main__":
    main()
