### How to build?
I use the Bazel build system. Any any location, call:
```bash
bazel-7.5.0 build //:leader_election
bazel-7.5.0 build //:client
```

``bash
python3 overlay_thp_runs.py leader1_20250510_054902raft/ leader1_20250510_053331raft/ leader1_20250510_055658raft/ leader1_20250510_052535raft/ leader1_20250510_081550raft --trim-first 15 --trim-last 30


python3 overlay_thp_runs.py leader1_20250510_062437Jacobson/ leader1_20250510_064031Jacobson/ leader1_20250510_064842Jacobson/ leader1_20250510_065650Jacobson/ leader1_20250510_072122Jacobson/ --trim-first 15 --trim-last 30
```


```bash
invoke start-client --serverIp 127.0.0.4 --serverPort 10999 --value 5 --bindIp 127.0.0.18
invoke start-clients-remote --leaderId 0 --serverPort 10083 --value 5
invoke start-client-remote --remoteHostId 5 --serverIp 10.0.0.3 --serverPort 10083 --value 5 --bindIp 10.0.3.1
invoke start-client-remote --remoteHostId 5 --serverIp 10.0.0.3 --serverPort 10083 --value 0.001 --bindIp 10.0.3.1
```


BUG LOG: 

> [!WARNING] 
> Moodycamel implementation is problematic, and sometimes will not dequeue packets from a certain node if it has many user requests queued up. Separate into 2 queues, one for client requests, and the other for internal communication. 

Identified bug, before sleep. The cause is that there are synchronization error when sending messgaes, causing the messages to be not parsable. 

Proof:
the system is under small load when the succession of failed requests occurred. 
The cause of the catrastrophe is the node not parsing messages, and then sending an election timeout to everyone else incorrectly. 
Always, before the election timeout, the node says that it cannot parse incoming messages, no exceptions. 
The phenomenom is compunded by increasing the number of worker threads. 


Now I am pretty sure that, synchronization may not be the main cause of the problem. The problem is that the message cannot be parsed, and this is because of the fact that the message size exceeds MTU, causing truncation. 

potential solutions include (1) switching to TCP or nano message. (2) cutoff when the message size is big, but this introduces problems of when are we going to send additional leftover entries. 


identified bug: after batch commit, did not send acknowledgement for all previous messages, causing trouble in max in flight mode, the client will get stuck for not receiving any ack. 


too many worker threads actually degrade the performance. Weird.


Is the bottleneck at the single UDP socket responsible for both ingress and egress of all packets? A simple program to test the limit of a single socket might be interesting. 



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

## Zookeeper Benchmark

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
./bin/zkCli.sh -server 10.0.0.3:2181
# then we create the /benchmark node. 
create /benchmark "" 
# verify with the following in the client CLI interface. 
ls /
```

load the data:
```bash
# -p recordcount,the count of records/paths you want to insert
cd ~/YCSB
./bin/ycsb load zookeeper -s -P workloads/workloadb -p zookeeper.connectString=10.0.0.3:2181/benchmark -p recordcount=10000 > outputLoad.txt
```

Verify that the data entries have been inserted already. Should see that there are a lot of entries in that znode.  
```bash
./bin/zkCli.sh -server 10.0.0.3:2181
ls /benchmark
```

To remove the already loaded data in zookeeper and to load new data into it:
```
cd ~/{apache_directory}/bin
./zkCli.sh -server 10.0.3.1:2181
[zk: 10.0.3.1:2181(CONNECTED) 0] deleteall /benchmark
```

to localize the effect of latency performance to network latency and leader selection only, reduce the number of bytes in each field. 


```
cd ~/YCSB
./bin/ycsb load zookeeper -s -P workloads/workloadb \
  -p zookeeper.connectString=10.0.0.2:2181/benchmark \
  -p recordcount=5000 -p fieldlength=1
```

Test the performance with a write heavy situation:
```bash
cd ~/YCSB
./bin/ycsb run zookeeper -threads 1 -P workloads/workloadb \
  -p zookeeper.connectString=10.0.5.2:2181/benchmark \
  -p readproportion=0.1 -p updateproportion=0.9 \
  -p operationcoun=1000000 \
  -p hdrhistogram.percentiles=10,25,50,75,90,95,99,99.9 \
  -p histogram.buckets=500 > outputHist7.txt
```

to change the weight/latency of a specific link:
```bash
sudo tc qdisc del dev enp129s0f0 root
sudo tc qdisc add dev enp129s0f0 root netem delay 6ms 3ms distribution pareto
```
