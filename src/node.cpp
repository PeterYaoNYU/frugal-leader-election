#include "node.h"
#include <arpa/inet.h>
#include <sys/socket.h>
#include <sstream>
#include <cstring>

// this constructor should probably be removed
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

    LOG(INFO) << "Peer addresses size is: " << peer_addresses.size();
}

Node::Node(const ProcessConfig& config, int replicaId)
    : loop(ev_default_loop(0)),
      port(config.port),
      rng(std::random_device{}()),
      dist(config.timeoutLowerBound, config.timeoutUpperBound),
      sock_fd(-1),
      runtime_seconds(config.runtimeSeconds),
      failure_leader(config.failureLeader)
{
    election_timer.data = this;
    heartbeat_timer.data = this;
    recv_watcher.data = this;

    current_leader_ip = "";
    current_leader_port = -1;
    role = Role::FOLLOWER;
    current_term = 0;
    voted_for = "";
    votes_received = 0;
    
    std::vector<std::string> peerIPs = config.peerIPs;
    int port_for_service = config.port;

    // Parse peer addresses from config.peerIPs
    for (const auto& peer : peerIPs) {
        peer_addresses.emplace_back(peer, port_for_service);
    }

    LOG(INFO) << "Peer addresses size is: " << peer_addresses.size();


    // init the self_ip by the replicaId
    self_ip = config.peerIPs[replicaId];
    runtime_seconds = config.runtimeSeconds;
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

    ev_timer_init(&shutdown_timer, shutdown_cb, runtime_seconds, 0);
    shutdown_timer.data = this;
    ev_timer_start(loop, &shutdown_timer);

    // Start the event loop
    ev_run(loop, 0);
}


void Node::shutdown_cb(EV_P_ ev_timer* w, int revents) {
    Node* self = static_cast<Node*>(w->data);
    LOG(INFO) << "Runtime exceeded (" << self->runtime_seconds << " seconds). Shutting down node.";
    // Stop the event loop
    ev_break(EV_A_ EVBREAK_ALL);
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

    self->current_term++;
    self->role = Role::CANDIDATE;
    self->current_leader_ip = "";  
    self->current_leader_port = -1;
    self->voted_for = self->self_ip + ":" + std::to_string(self->port);
    self->votes_received = 1; // Vote for self


    LOG(INFO) << "Election timeout occurred. Starting leader election and voting for myself. View number: " << self->current_term; 
    // self->become_leader();

    self->start_election_timeout();
    self->send_request_vote();
}

void Node::send_request_vote() {
    raft::leader_election::RequestVote request;
    request.set_term(current_term);
    request.set_candidate_id(self_ip + ":" + std::to_string(port));

    raft::leader_election::MessageWrapper wrapper;
    wrapper.set_type(raft::leader_election::MessageWrapper::REQUEST_VOTE);
    wrapper.set_payload(request.SerializeAsString());

    std::string serialized_message = wrapper.SerializeAsString();

    for (const auto& [ip, peer_port] : peer_addresses) {
        sockaddr_in peer_addr{};
        peer_addr.sin_family = AF_INET;
        peer_addr.sin_port = htons(peer_port);
        inet_pton(AF_INET, ip.c_str(), &peer_addr.sin_addr);

        ssize_t nsend = sendto(sock_fd, serialized_message.c_str(), serialized_message.size(), 0,
                               (sockaddr*)&peer_addr, sizeof(peer_addr));

        if (nsend == -1) {
            LOG(ERROR) << "Failed to send request vote to " << ip << ":" << peer_port;
        } else {
            LOG(INFO) << "Sent request vote to " << ip << ":" << peer_port;
        }
    }
}

void Node::heartbeat_cb(EV_P_ ev_timer* w, int revents) {
    Node* self = static_cast<Node*>(w->data);
    self->send_heartbeat();
}

void Node::recv_cb(EV_P_ ev_io* w, int revents) {
    Node* self = static_cast<Node*>(w->data);
    char buffer[4096];
    sockaddr_in sender_addr{};
    socklen_t sender_len = sizeof(sender_addr);
    ssize_t nread = recvfrom(w->fd, buffer, sizeof(buffer), 0,
                             (sockaddr*)&sender_addr, &sender_len);
    if (nread > 0) {
        // buffer[nread] = '\0';
        std::string message(buffer, nread);
        // LOG(INFO) << "Received message: " << message;

        raft::leader_election::MessageWrapper wrapper;
        if (!wrapper.ParseFromString(message)) {
            LOG(ERROR) << "Failed to parse message.";
            return;
        }   

        switch (wrapper.type()) {
            case raft::leader_election::MessageWrapper::REQUEST_VOTE: {
                raft::leader_election::RequestVote request;
                if (!request.ParseFromString(wrapper.payload())) {
                    LOG(ERROR) << "Failed to parse request vote.";
                    return;
                }
                self->handle_request_vote(request, sender_addr);
                break;
            }
            case raft::leader_election::MessageWrapper::VOTE_RESPONSE: {
                raft::leader_election::VoteResponse response;
                if (!response.ParseFromString(wrapper.payload())) {
                    LOG(ERROR) << "Failed to parse vote response.";
                    return;
                }
                self->handle_vote_response(response);
                break;
            }
            case raft::leader_election::MessageWrapper::APPEND_ENTRIES: {
                raft::leader_election::AppendEntries append_entries;
                if (!append_entries.ParseFromString(wrapper.payload())) {
                    LOG(ERROR) << "Failed to parse append entries.";
                    return;
                }
                self->handle_append_entries(append_entries, sender_addr);
                LOG(INFO) << "Received append entries message.";
                break;
            }
            default:
                LOG(ERROR) << "Unknown message type.";
        }

    }
}

void Node::handle_request_vote(const raft::leader_election::RequestVote& request, const sockaddr_in& send_addr) {
    int received_term = request.term();
    // this is not an id, but the candidate IP and port combination. 
    std::string candidate_id = request.candidate_id();

    if (received_term < current_term) {
        raft::leader_election::VoteResponse response;
        response.set_term(current_term);
        response.set_vote_granted(false);

        send_vote_response(response, send_addr);
        return;
    }

    if (received_term > current_term) {
        current_term = received_term;
        role = Role::FOLLOWER;
        voted_for = ""; 
    }

    // this is important, ensure that a node only votes once per term. 
    bool vote_granted = false;
    if (voted_for.empty() || voted_for == candidate_id) {
        vote_granted = true;
        voted_for = candidate_id;
        reset_election_timeout();
    }

    raft::leader_election::VoteResponse response;
    response.set_term(current_term);
    response.set_vote_granted(vote_granted);

    send_vote_response(response, send_addr);

    LOG(INFO) << "Received request vote from " << candidate_id <<  " for term: " << received_term  << ". Vote granted: " << vote_granted;
}

void Node::send_vote_response(const raft::leader_election::VoteResponse& response, const sockaddr_in& recepient_addr) {
    raft::leader_election::MessageWrapper wrapper;
    wrapper.set_type(raft::leader_election::MessageWrapper::VOTE_RESPONSE);
    wrapper.set_payload(response.SerializeAsString());

    std::string serialized_message = wrapper.SerializeAsString();

    ssize_t nsend = sendto(sock_fd, serialized_message.c_str(), serialized_message.size(), 0,
                           (sockaddr*)&recepient_addr, sizeof(recepient_addr));
    if (nsend == -1) {
        LOG(ERROR) << "Failed to send vote response.";
    } else {
        LOG(INFO) << "Sent VoteResponse to "
                  << inet_ntoa(recepient_addr.sin_addr) << ":" << ntohs(recepient_addr.sin_port);
    }
}

void Node::handle_vote_response(const raft::leader_election::VoteResponse& response) {
    if (role != Role::CANDIDATE) {
        return;
    }

    // if the response has a bigger term number, indicating that out term has already expired. 
    // revert back to the follower. 
    if (response.term() > current_term) {
        current_term = response.term();
        role = Role::FOLLOWER;
        voted_for = "";
        return;
    }

    if (response.vote_granted()) {
        votes_received++;

        // if bigger than f+1 in a 2f+1 setting
        if (votes_received >= peer_addresses.size() / 2 + 1) {
            role = Role::LEADER;
            become_leader();
        }
    }
}

void Node::become_leader() {
    role = Role::LEADER;
    current_leader_ip = self_ip;
    current_leader_port = port;

    // stop the election timeout
    ev_timer_stop(loop, &election_timer);

    LOG(INFO) << "Became leader. Starting to send heartbeats. Elected Term: " << current_term;
    

    // Initialize heartbeat timer
    ev_timer_init(&heartbeat_timer, heartbeat_cb, 0.0, 0.075); // 75 ms interval
    heartbeat_timer.data = this;
    ev_timer_start(loop, &heartbeat_timer);
}

void Node::send_heartbeat() {
    raft::leader_election::AppendEntries append_entries;
    append_entries.set_term(current_term);
    append_entries.set_leader_id(self_ip + ":" + std::to_string(port));

    // wrap around:
    raft::leader_election::MessageWrapper wrapper;
    wrapper.set_type(raft::leader_election::MessageWrapper::APPEND_ENTRIES);
    wrapper.set_payload(append_entries.SerializeAsString());

    std::string serialized_message = wrapper.SerializeAsString();   

    for (const auto& [ip, peer_port] : peer_addresses) {
        sockaddr_in peer_addr{};
        peer_addr.sin_family = AF_INET;
        peer_addr.sin_port = htons(peer_port);
        inet_pton(AF_INET, ip.c_str(), &peer_addr.sin_addr);

        ssize_t nsend = sendto(sock_fd, serialized_message.c_str(), serialized_message.size(), 0,
                               (sockaddr*)&peer_addr, sizeof(peer_addr));
        if (nsend == -1) {
            LOG(ERROR) << "Failed to send heartbeat to " << ip << ":" << peer_port;
        } else {
            LOG(INFO) << "Sent heartbeat to " << ip << ":" << peer_port;
        }
    }
}

void Node::handle_append_entries(const raft::leader_election::AppendEntries& append_entries, const sockaddr_in& sender_addr) {
    int received_term = append_entries.term();
    std::string leader_id = append_entries.leader_id();

    if (received_term < current_term) {
        raft::leader_election::AppendEntriesResponse response;
        response.set_term(current_term);
        response.set_success(false);

        send_append_entries_response(response, sender_addr);
        return;
    }

    // If term is newer or equal, update current_term and leader info
    current_term = received_term;
    role = FOLLOWER;
    current_leader_ip = leader_id.substr(0, leader_id.find(':'));
    current_leader_port = std::stoi(leader_id.substr(leader_id.find(':') + 1));
    voted_for = ""; // Reset voted_for in the new term

    reset_election_timeout(); // Reset election timeout upon receiving heartbeat

    // Assuming logs are consistent for simplicity

    raft::leader_election::AppendEntriesResponse response;
    response.set_term(current_term);
    response.set_success(true);

    send_append_entries_response(response, sender_addr);

    LOG(INFO) << "Received heartbeat (AppendEntries) from leader " << leader_id << " for term " << received_term;
}

void Node::send_append_entries_response(const raft::leader_election::AppendEntriesResponse& response, const sockaddr_in& recipient_addr) {
    raft::leader_election::MessageWrapper wrapper;
    wrapper.set_type(raft::leader_election::MessageWrapper::APPEND_ENTRIES_RESPONSE);
    wrapper.set_payload(response.SerializeAsString());

    std::string serialized_message = wrapper.SerializeAsString();

    ssize_t nsend = sendto(sock_fd, serialized_message.c_str(), serialized_message.size(), 0,
                           (sockaddr*)&recipient_addr, sizeof(recipient_addr));
    if (nsend == -1) {
        LOG(ERROR) << "Failed to send AppendEntriesResponse";
    } else {
        LOG(INFO) << "Sent AppendEntriesResponse to "
                  << inet_ntoa(recipient_addr.sin_addr) << ":" << ntohs(recipient_addr.sin_port);
    }
}
