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

To check that zookeeper is running properly, on each node, check with the command. 
```bash
/users/PeterYao/apache-zookeeper-3.8.4-bin/bin/zkServer.sh status
```

To benchmark Zookeeper with YCSB:
First compile the ZK binding for YCSB. 
```bash
sudo apt update
sudo apt install maven

git clone http://github.com/brianfrankcooper/YCSB.git
# more details in the landing page for instructions on downloading YCSB(https://github.com/brianfrankcooper/YCSB#getting-started).
cd YCSB
mvn -pl site.ycsb:zookeeper-binding -am clean package -DskipTests
```

Then load the data into YCSB. To do that, you need to first create the benchmark znode in the ZK distirbuted system, and then load the data into the benchmark znode. 
```bash
# first connect the zookeeper with CLI, suppose that we are connecting to node 10.0.3.1
./bin/zkCli.sh -server 10.0.3.1:2181
# then we create the /benchmark node. 
create /benchmark "" 
# verify with the following in the client CLI interface. 
ls /
```

load the data:
```bash
# -p recordcount,the count of records/paths you want to insert
cd ~/YCSB
./bin/ycsb load zookeeper -s -P workloads/workloadb -p zookeeper.connectString=10.0.3.1:2181/benchmark -p recordcount=10000 > outputLoad.txt
```

Verify that the data entries have been inserted already. Should see that there are a lot of entries in that znode.  
```bash
./bin/zkCli.sh -server 10.0.3.1:2181
ls /benchmark
```

Test the performance with a write heavy situation:
```bash
cd ~/YCSB
./bin/ycsb run zookeeper -threads 1 -P workloads/workloadb \
  -p zookeeper.connectString=10.0.3.1:2181/benchmark \
  -p readproportion=0.1 -p updateproportion=0.9 \
  -p hdrhistogram.percentiles=10,25,50,75,90,95,99,99.9 \
  -p histogram.buckets=500 > outputHist7.txt
```

node 0 serves as the client, without adding additional delay. 
When node 2 is the leader, connecting to node 2 (fairly far from everyone else):
[OVERALL], Throughput(ops/sec), 100.54293183189222 
[UPDATE], Operations, 891
[UPDATE], AverageLatency(us), 10721.777777777777
[UPDATE], MinLatency(us), 4320
[UPDATE], MaxLatency(us), 85887
[UPDATE], 10thPercentileLatency(us), 5667
[UPDATE], 25thPercentileLatency(us), 5919
[UPDATE], 50thPercentileLatency(us), 9519
[UPDATE], 75thPercentileLatency(us), 16127
[UPDATE], 90thPercentileLatency(us), 18175
[UPDATE], 95thPercentileLatency(us), 18815
[UPDATE], 99thPercentileLatency(us), 21375
[UPDATE], 99.9PercentileLatency(us), 85887
[UPDATE], Return=OK, 891
Results stored in outputHist7.txt


node 0 serves as the client, connecting to node 1, node 1 is the leader, closer to everyone else. 
Output saved to outputHist0.txt and outputHist1.txt
[OVERALL], Throughput(ops/sec), 97.03085581214826
[UPDATE], Operations, 923
[UPDATE], AverageLatency(us), 10790.535211267606
[UPDATE], MinLatency(us), 4268
[UPDATE], MaxLatency(us), 82495
[UPDATE], 10thPercentileLatency(us), 5719
[UPDATE], 25thPercentileLatency(us), 5991
[UPDATE], 50thPercentileLatency(us), 9431
[UPDATE], 75thPercentileLatency(us), 15863
[UPDATE], 90thPercentileLatency(us), 17855
[UPDATE], 95thPercentileLatency(us), 18319
[UPDATE], 99thPercentileLatency(us), 21583
[UPDATE], 99.9PercentileLatency(us), 82495

