### How to build?
I use the Bazel build system. Any any location, call:
```bash
bazel build //:leader_election
```

### How to run?

> To reproduce, you should only run on the Wisconsin Cluster of CloudLab. Emulab has known issue to delay messages without conforming to the predetermined distribution, causing inferior performance. 

I use the ```invoke``` library for running the process. The script is in the subdirectory ```scripts```.
```bash
cd scripts
invoke start
```

To stop the processes from running, 
```bash
killall leader*
```

the command for the ebpf compilation is
```python
sudo python3 loader.py
```

A command for listing the specifics of a certain TCP connection that is both established
and has a certain address as the destination
```bash
ss -t -i state established dst 10.0.1.2
```

the command to generate a smooth tcp traffic:

```bash
iperf3 -c 10.0.1.2 -t 0 -b 100K -l 1K
```

Maybe the tcp traffic monitor should use weighted mean rtt instead of just RTT? So that it can adapt. 