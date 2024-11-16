sudo tc qdisc add dev eth1 root netem delay 10ms 5ms distribution normal
sudo tc qdisc add dev eth2 root netem delay 10ms 5ms distribution normal
sudo tc qdisc add dev eth3 root netem delay 10ms 5ms distribution normal
sudo tc qdisc add dev eth4 root netem delay 10ms 5ms distribution normal
sudo tc qdisc add dev eth5 root netem delay 10ms 5ms distribution normal




sudo tc qdisc add dev vlan1110 root netem delay 10ms 5ms distribution normal
sudo tc qdisc add dev vlan1150 root netem delay 10ms 5ms distribution normal
sudo tc qdisc add dev vlan1187 root netem delay 10ms 5ms distribution normal
sudo tc qdisc add dev vlan1195 root netem delay 10ms 5ms distribution normal
sudo tc qdisc add dev vlan1212 root netem delay 10ms 5ms distribution normal


sudo tc qdisc add dev vlan102 root netem delay 1ms 1ms distribution normal
sudo tc qdisc add dev vlan105 root netem delay 2ms 1ms distribution normal
sudo tc qdisc add dev vlan107 root netem delay 2ms 1ms distribution normal
sudo tc qdisc add dev vlan109 root netem delay 2ms 1ms distribution normal
sudo tc qdisc add dev vlan110 root netem delay 2ms 1ms distribution normal

sudo tc qdisc del dev vlan102 root
sudo tc qdisc del dev vlan105 root
sudo tc qdisc del dev vlan107 root
sudo tc qdisc del dev vlan109 root
sudo tc qdisc del dev vlan110 root