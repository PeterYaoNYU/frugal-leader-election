sudo tc qdisc add dev eth1 root netem delay 2ms 2ms distribution normal
sudo tc qdisc add dev eth2 root netem delay 2ms 2ms distribution normal
sudo tc qdisc add dev eth3 root netem delay 2ms 2ms distribution normal
sudo tc qdisc add dev eth4 root netem delay 2ms 2ms distribution normal
sudo tc qdisc add dev eth5 root netem delay 2ms 2ms distribution normal