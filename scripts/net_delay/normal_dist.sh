sudo tc qdisc add dev vlan1140 root netem delay 100ms 100ms distribution normal
sudo tc qdisc add dev vlan1159 root netem delay 100ms 100ms distribution normal
sudo tc qdisc add dev vlan1191 root netem delay 100ms 100ms distribution normal
sudo tc qdisc add dev vlan1213 root netem delay 100ms 100ms distribution normal
sudo tc qdisc add dev vlan1221 root netem delay 100ms 100ms distribution normal




sudo tc qdisc add dev vlan1110 root netem delay 15ms 5ms distribution normal
sudo tc qdisc add dev vlan1150 root netem delay 15ms 5ms distribution normal
sudo tc qdisc add dev vlan1187 root netem delay 2ms 1ms distribution normal
sudo tc qdisc add dev vlan1195 root netem delay 15ms 5ms distribution normal
sudo tc qdisc add dev vlan1212 root netem delay 15ms 5ms distribution normal


sudo tc qdisc del dev vlan1140 root
sudo tc qdisc del dev vlan1159 root
sudo tc qdisc del dev vlan1191 root
sudo tc qdisc del dev vlan1213 root
sudo tc qdisc del dev vlan1221 root

# for testing petition mechanism in the network
sudo tc qdisc add dev vlan1110 root netem delay 120ms 5ms distribution normal
sudo tc qdisc add dev vlan1150 root netem delay 120ms 5ms distribution normal
sudo tc qdisc add dev vlan1187 root netem delay 120ms 1ms distribution normal
sudo tc qdisc add dev vlan1195 root netem delay 120ms 5ms distribution normal
sudo tc qdisc add dev vlan1212 root netem delay 120ms 5ms distribution normal

sudo tc qdisc add dev vlan1187 root netem delay 2ms 1ms distribution normal


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