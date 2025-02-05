#!/usr/bin/env python3
"""
echo_server.py

A UDP echo server that trims the reply to just the packet ID.
It listens on port 9999. When a packet is received, the first 4 bytes
(assumed to be the packet ID) are extracted and sent back to the sender.
"""

import socket
import argparse

def echo_server(port, listen_addr=("0.0.0.0", )):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((listen_addr[0], port))
    print(f"Echo server listening on {listen_addr[0]}:{port}")
    while True:
        try:
            data, addr = sock.recvfrom(2048)
            if len(data) >= 4:
                # Extract the first 4 bytes (the packet ID)
                packet_id = data[:4]
                # Send only the packet ID back as the reply
                sock.sendto(packet_id, addr)
            else:
                # If the packet is too short, ignore it.
                continue
        except KeyboardInterrupt:
            print("Echo server interrupted. Exiting.")
            break
        except Exception as e:
            print("Echo server error:", e)
            break
    sock.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="UDP Echo Server")
    parser.add_argument("port", type=int, nargs="?", default=9999,
                        help="Port on which to listen for echo requests (default: 9999)")
    args = parser.parse_args()

    echo_server(args.port)
