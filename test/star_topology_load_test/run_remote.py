#!/usr/bin/env python3
"""
deploy_run.py

This Fabric script performs the following steps on 5 remote hosts:

  1. Uploads the files: echo_sender.py, echo_sender_multi.py, and echo_server.py
     to a remote directory (here, /tmp).

  2. Runs a compile step on each file (using python3 -m py_compile) to verify they compile.

  3. Starts the echo server by executing:
       nohup python3 /tmp/echo_server.py > /tmp/echo_server.log 2>&1 &
     so that it runs in the background.

  4. Finally, initiates the multi‐sender by running:
       python3 /tmp/echo_sender_multi.py

Between each step, the script waits a few seconds so that the previous step has time to finish.

Example remote host string:
  PeterYao@c220g5-111004.wisc.cloudlab.us:32410

Usage:
  python3 deploy_run.py
"""

import time
from fabric import Group

# Define the remote hosts (with custom SSH ports) as host strings.
hosts = [
    "PeterYao@c220g5-111004.wisc.cloudlab.us:32410",
    "PeterYao@c220g5-111012.wisc.cloudlab.us:32410",
    "PeterYao@c220g5-111004.wisc.cloudlab.us:32411",
    "PeterYao@c220g5-111004.wisc.cloudlab.us:32412",
    "PeterYao@c220g5-111012.wisc.cloudlab.us:32411"
]

# Create a Fabric Group with the hosts.
group = Group(*hosts)

# Remote directory where files will be uploaded.
remote_dir = "~"

# List of files to upload.
# files_to_upload = ["./echo_sender.py", "echo_sender_multi.py", "echo_server.py"]

files_to_upload = ["./echo_sender_concurrent_multi.py"]

# -------------------------------
# Step 1: Upload the files.
# -------------------------------
print("Uploading files to remote hosts...")
for filename in files_to_upload:
    for conn in group:
        remote_path = f"{remote_dir}/{filename}"
        print(f"Uploading {filename} to {remote_path} on host {conn}...")
        conn.put(filename)

# Give extra time for all transfers to settle.
time.sleep(5)

print("Starting echo_server.py on remote hosts in background...")
server_cmd = f"nohup python3 {remote_dir}/echo_server.py 7788 > {remote_dir}/echo_server.log 2>&1 &"
for conn in group:
  conn.run(server_cmd)
# Allow a few seconds for the echo server to start.
time.sleep(5)

# -------------------------------
# Step 4: Start the multi-sender.
# -------------------------------
print("Starting echo_sender_multi.py on remote hosts...")
for conn in group[:1]:
  print(f"Starting echo_sender_multi.py on host {conn}...")
  conn.run(f"python3 {remote_dir}/echo_sender_concurrent_multi.py 7788 0.06 > {remote_dir}/echo_sender.log")

