import socket
import threading
import time
import sys

# Store active socket connections
active_sockets = []
active_sockets_lock = threading.Lock()

def start_tcp_connection(local_ip, target_ip, target_port, duration=120, message_size=128, interval=0.10):
    start_time = time.time()
    message = b"A" * message_size
    while time.time() - start_time < duration:
        try:
            # Create a TCP socket
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            
            # Enable TCP Keep-Alive
            s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            
            # Platform-specific settings
            if sys.platform.startswith('linux'):
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 30)
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 20)
            elif sys.platform == 'darwin':  # macOS
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPALIVE, 60)
            
            s.bind((local_ip, 0))
            
            s.connect((target_ip, target_port))
            with active_sockets_lock:
                active_sockets.append(s)
            print(f"Connected to {target_ip}:{target_port}")
            
            while time.time() - start_time < duration:
                try:
                    s.sendall(message)
                except Exception as e:
                    print(f"Error sending data to {target_ip}:{target_port} - {e}")
                    break
                time.sleep(interval)  # Wait for some time before sending the next message
        except Exception as e:
            print(f"Failed to connect to {target_ip}:{target_port} - {e}")
        finally:
            with active_sockets_lock:
                if s in active_sockets:
                    active_sockets.remove(s)
            s.close()
            print(f"Connection to {target_ip}:{target_port} closed. Reconnecting in 5 seconds...")
            time.sleep(5)  # Wait before attempting to reconnect

def handle_client_connection(conn, addr):
    try:
        while True:
            data = conn.recv(4096)
            if not data:
                # No data means the client has closed the connection
                print(f"Connection closed by {addr}")
                break
    except Exception as e:
        print(f"Error handling client {addr}: {e}")
    finally:
        conn.close()
        with active_sockets_lock:
            if conn in active_sockets:
                active_sockets.remove(conn)

def listen_for_connections(listen_ip, listen_port):
    try:
        # Create a TCP socket to listen for incoming connections
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.bind((listen_ip, listen_port))
        server_socket.listen(10)
        print(f"Listening on {listen_ip}:{listen_port}")
        while True:
            conn, addr = server_socket.accept()
            print(f"Accepted connection from {addr}")
            with active_sockets_lock:
                active_sockets.append(conn)
            # Start a new thread to handle the incoming connection
            threading.Thread(target=handle_client_connection, args=(conn, addr)).start()
    except Exception as e:
        print(f"Failed to listen on {listen_ip}:{listen_port} - {e}")

def close_all_connections():
    print("Closing all active connections...")
    with active_sockets_lock:
        for s in active_sockets:
            try:
                s.close()
                print(f"Closed connection: {s}")
            except Exception as e:
                print(f"Failed to close connection: {s} - {e}")
        active_sockets.clear()

def start_node(node_id, central_port, duration):
    # Local IP range: 127.0.0.2 - 127.0.0.6
    node_ip_format = "127.0.0.{}"
    listen_ip = node_ip_format.format(node_id + 1)  # 127.0.0.2 corresponds to node_id 1

    # Start listening for incoming connections
    listen_thread = threading.Thread(target=listen_for_connections, args=(listen_ip, central_port,))
    listen_thread.start()

    # Allow some time for the listener to start
    time.sleep(5)

    # Start continuous TCP connections to each of the other nodes
    threads = []
    for target_id in range(1, 6):
        if target_id == node_id:
            continue  # Skip connecting to itself

        target_ip = node_ip_format.format(target_id + 1)
        thread = threading.Thread(target=start_tcp_connection, args=(listen_ip, target_ip, central_port, duration, 256, 0.1))
        thread.start()
        threads.append(thread)
        time.sleep(0.1)  # Small delay to avoid overwhelming the target

    # Wait for all threads to finish
    for thread in threads:
        thread.join()

    # Wait for the listen thread to finish
    listen_thread.join()

def main(central_port, duration):
    # Start the 5 nodes
    threads = []
    for node_id in range(1, 6):
        thread = threading.Thread(target=start_node, args=(node_id, central_port, duration))
        thread.start()
        threads.append(thread)

    # Wait for all nodes to finish
    for thread in threads:
        thread.join()

    # Close all connections
    close_all_connections()

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python tcp_sim.py <port> <duration>")
        sys.exit(1)

    try:
        central_port = int(sys.argv[1])
        duration = int(sys.argv[2])
    except ValueError:
        print("Port and duration must be integers.")
        sys.exit(1)

    main(central_port, duration)
