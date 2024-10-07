import socket
import sys
import threading
import time

def start_tcp_connection(target_ip, target_port):
    try:
        # Create a TCP socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((target_ip, target_port))
        print(f"Connected to {target_ip}:{target_port}")
        # Sending a simple message to the target node
        s.sendall(b"Hello from node!")
        # Close the socket
        s.close()
    except Exception as e:
        print(f"Failed to connect to {target_ip}:{target_port} - {e}")

def listen_for_connections(listen_ip, listen_port):
    try:
        # Create a TCP socket to listen for incoming connections
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.bind((listen_ip, listen_port))
        server_socket.listen(5)
        print(f"Listening on {listen_ip}:{listen_port}")
        while True:
            conn, addr = server_socket.accept()
            print(f"Accepted connection from {addr}")
            data = conn.recv(1024)
            if data:
                print(f"Received message: {data.decode()}")
            conn.close()
    except Exception as e:
        print(f"Failed to listen on {listen_ip}:{listen_port} - {e}")

def main(node_id, central_port):
    node_ip_format = "10.0.{}.2"

    # Validate the node ID
    if node_id < 1 or node_id > 5:
        print("Node ID must be between 1 and 5.")
        sys.exit(1)

    # Start listening for incoming connections
    listen_ip = node_ip_format.format(node_id)
    listen_thread = threading.Thread(target=listen_for_connections, args=(listen_ip, central_port))
    listen_thread.start()
    
    wait_time = 5
    print(f"Waiting {wait_time} seconds for the listen thread to start...")
    time.sleep(wait_time)

    # Start 10 TCP connections to each of the other nodes
    threads = []
    for target_id in range(1, 6):
        if target_id == node_id:
            continue  # Skip connecting to itself

        target_ip = node_ip_format.format(target_id)
        for i in range(10):  # Start 10 TCP connections to the target node
            thread = threading.Thread(target=start_tcp_connection, args=(target_ip, central_port))
            thread.start()
            threads.append(thread)
            time.sleep(0.1)  # Small delay to avoid overwhelming the target

    # Wait for all threads to finish
    for thread in threads:
        thread.join()

    # Wait for the listen thread to finish (it runs indefinitely)
    listen_thread.join()

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python tcp_sim.py <node_id> <port>")
        sys.exit(1)

    try:
        node_id = int(sys.argv[1])
        central_port = int(sys.argv[2])
    except ValueError:
        print("Node ID and port must be integers.")
        sys.exit(1)

    main(node_id, central_port)