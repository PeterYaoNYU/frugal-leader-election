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

### Cloudlab Experiment Instructions

To compile and/or install the build system (Bazel 7), or to fetch the latest changes from Github, use the script, which probably has pretty bad naming:
```bash
cd scripts
python3 background_tcp_simulation/auto_run_leader_election.py 
```

To initiate background traffic, run the script:
```bash
python3 background_tcp_simulation/auto_sim.py
```
> The node sequence in auto_sim.py should really match the IP order in tcp_sim.py

To begin running remote experiments, use the command:
```bash
invoke start-remote-default
```
> Need to make sure that the ip order in remote.yaml matches the node ordering in tasks.py

To download the logs:
```bash
invoke download-logs-default
```
