#include "node.h"
#include <arpa/inet.h>
#include <sys/socket.h>
#include <sstream>
#include <cstring>

Node::Node(int port, const std::string& peers)
    : loop(ev_default_loop(0)),
      port(port),
      rng(std::random_device{}()),
      dist(150, 300), // Election timeout between 150-300 ms
      sock_fd(-1)
{
    election_timer.data = this;
    heartbeat_timer.data = this;
    recv_watcher.data = this;

    // Parse peer addresses
    std::stringstream ss(peers);
    std::string peer;
    while (std::getline(ss, peer, ',')) {
        auto pos = peer.find(':');
        if (pos != std::string::npos) {
            std::string ip = peer.substr(0, pos);
            int peer_port = std::stoi(peer.substr(pos + 1));
            LOG(INFO) << "Peer: " << ip << ":" << peer_port;
            peer_addresses.emplace_back(ip, peer_port);
        }
    }
}

Node::Node(const ProcessConfig& config, int replicaId)
    : loop(ev_default_loop(0)),
      port(config.port),
      rng(std::random_device{}()),
      dist(config.timeoutLowerBound, config.timeoutUpperBound),
      sock_fd(-1)
{
    election_timer.data = this;
    heartbeat_timer.data = this;
    recv_watcher.data = this;

    std::vector<std::string> peerIPs = config.peerIPs;
    int port_for_service = config.port;

    // Parse peer addresses from config.peerIPs
    for (const auto& peer : peerIPs) {
        peer_addresses.emplace_back(peer, port_for_service);
    }

    // init the self_ip by the replicaId
    self_ip = config.peerIPs[replicaId];
}


void Node::run() {
    // Setup UDP socket
    LOG(INFO) << "Start running node on port " << port;
    sock_fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock_fd < 0) {
        LOG(FATAL) << "Failed to create socket.";
    }

    // Set socket to non-blocking
    fcntl(sock_fd, F_SETFL, O_NONBLOCK);

    // Bind socket to the specified port
    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(port);
    // we cannot use INADDR_ANY here, because we need to know the ip address of the current node
    // addr.sin_addr.s_addr = INADDR_ANY;

    // bind to the ip address of the current node
    // Convert self_ip (string) to in_addr
    if (inet_pton(AF_INET, self_ip.c_str(), &addr.sin_addr) <= 0) {
        LOG(FATAL) << "Invalid IP address: " << self_ip;
    }

    if (bind(sock_fd, (sockaddr*)&addr, sizeof(addr)) < 0) {
        LOG(FATAL) << "Failed to bind socket to port " << port;
    }

    // Initialize receive watcher
    ev_io_init(&recv_watcher, recv_cb, sock_fd, EV_READ);
    ev_io_start(loop, &recv_watcher);

    // Start election timeout
    start_election_timeout();

    // Start the event loop
    ev_run(loop, 0);
}

void Node::start_election_timeout() {
    double timeout = dist(rng) / 1000.0; // Convert ms to seconds
    ev_timer_init(&election_timer, election_timeout_cb, timeout, 0);
    ev_timer_start(loop, &election_timer);
    LOG(INFO) << "Election timeout started: " << timeout << " seconds";
}

void Node::reset_election_timeout() {
    ev_timer_stop(loop, &election_timer);
    start_election_timeout();
}

void Node::election_timeout_cb(EV_P_ ev_timer* w, int revents) {
    Node* self = static_cast<Node*>(w->data);
    LOG(INFO) << "Election timeout occurred. Starting leader election.";
    self->become_leader();
}

void Node::heartbeat_cb(EV_P_ ev_timer* w, int revents) {
    Node* self = static_cast<Node*>(w->data);
    self->send_heartbeat();
}

void Node::recv_cb(EV_P_ ev_io* w, int revents) {
    Node* self = static_cast<Node*>(w->data);
    char buffer[1024];
    sockaddr_in sender_addr{};
    socklen_t sender_len = sizeof(sender_addr);
    ssize_t nread = recvfrom(w->fd, buffer, sizeof(buffer) - 1, 0,
                             (sockaddr*)&sender_addr, &sender_len);
    if (nread > 0) {
        buffer[nread] = '\0';
        std::string message(buffer);
        LOG(INFO) << "Received message: " << message;

        if (message == "heartbeat") {
            self->reset_election_timeout();
            LOG(INFO) << "Heartbeat received. Resetting election timeout.";
        }
    }
}

void Node::become_leader() {
    LOG(INFO) << "Became leader. Starting to send heartbeats.";

    // Initialize heartbeat timer
    ev_timer_init(&heartbeat_timer, heartbeat_cb, 0.0, 0.05); // 50 ms interval
    ev_timer_start(loop, &heartbeat_timer);
}

void Node::send_heartbeat() {
    for (const auto& [ip, peer_port] : peer_addresses) {
        sockaddr_in peer_addr{};
        peer_addr.sin_family = AF_INET;
        peer_addr.sin_port = htons(peer_port);
        inet_pton(AF_INET, ip.c_str(), &peer_addr.sin_addr);

        std::string message = "heartbeat";
        ssize_t nsend = sendto(sock_fd, message.c_str(), message.size(), 0,
                               (sockaddr*)&peer_addr, sizeof(peer_addr));
        if (nsend == -1) {
            LOG(ERROR) << "Failed to send heartbeat to " << ip << ":" << peer_port;
        } else {
            LOG(INFO) << "Sent heartbeat to " << ip << ":" << peer_port;
        }
    }
}
