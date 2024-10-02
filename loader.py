from bcc import BPF
from time import sleep
import socket
import struct

# Load eBPF program
b = BPF(src_file="srtt.c")
b.attach_kprobe(event="tcp_rcv_established", fn_name="track_srtt")

srtt_map = b.get_table("srtt_map")

print("%-16s %-10s" % ("Destination IP", "SRTT(us)"))

try:
    while True:
        sleep(1)
        for k, v in srtt_map.items():
            ip_addr = socket.inet_ntoa(struct.pack('I', k.daddr))
            print("%-16s %-10d" % (ip_addr, v.srtt))
        srtt_map.clear()
        srtt_map = b.get_table("srtt_map")
        
except KeyboardInterrupt:
    pass

