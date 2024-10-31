#include "node.h"
#include <arpa/inet.h>
#include <sys/socket.h>
#include <sstream>
#include <cstring>

Node::Node(const ProcessConfig& config, int replicaId)
    : loop(ev_default_loop(0)),                    // 1
      election_timer(),                            // 2
      heartbeat_timer(),                           // 3
      failure_timer(),                             // 4
      recv_watcher(),                              // 5
      sock_fd(-1),                                 // 6
      self_ip(""),                                 // 7 (set later if needed)
      runtime_seconds(0),                          // 8 (set later if needed)
      shutdown_timer(),                            // 9
      port(config.port),                                  // 10
      peer_addresses(),                            // 11 (initialized in the body)
      rng(std::random_device{}()),                 // 12
      dist(150, 300),                              // 13
      failure_leader(false),                       // 14
      current_leader_ip(""),                       // 15
      current_leader_port(-1),                     // 16
      view_number(0),                              // 17
      current_term(0),                             // 18
      voted_for(""),                               // 19
      votes_received(0),                           // 20
      max_heartbeats(0),                           // 21 (set later if needed)
      heartbeat_count(0),                          // 22
      use_simulated_links(config.useSimulatedLinks),                  // 23 (set later if needed)
      loss_dist(0.0, 1.0),                         // 24
      delay_dist(config.delayLowerBound, config.delayUpperBound),                     // 25
      role(Role::FOLLOWER),                         // 26
      link_loss_rate(config.linkLossRate),          // 27
      tcp_stat_manager(config.peerIPs[replicaId]),
      confidence_level(config.confidenceLevel),
      heartbeat_interval_margin(config.heartbeatIntervalMargin),
      heartbeat_current_term(0)
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

    LOG(INFO) << "Peer addresses size is: " << peer_addresses.size() << "and replica id is: " << replicaId;


    // init the self_ip by the replicaId
    self_ip = config.peerIPs[replicaId];
    LOG(INFO) << "Node initialized with IP: " << self_ip << ", port: " << port;

    runtime_seconds = config.runtimeSeconds;

    check_false_positive = config.checkFalsePositive;

    tcp_monitor = config.tcp_monitor;


}

void Node::send_with_delay_and_loss(const std::string& message, const sockaddr_in& recipient_addr) {
    if (loss_dist(rng) < link_loss_rate) { // Simulate 5% packet loss by default
        LOG(INFO) << "Simulated packet loss to " << inet_ntoa(recipient_addr.sin_addr)
                  << ":" << ntohs(recipient_addr.sin_port);
        return;
    }

    double delay_ms = delay_dist(rng);
    LOG(INFO) << "Simulating delay of " << delay_ms << "ms for message to "
              << inet_ntoa(recipient_addr.sin_addr) << ":" << ntohs(recipient_addr.sin_port);

    ev_timer* delay_timer = new ev_timer;

    // Create DelayData instance
    DelayData* data = new DelayData{this, message, recipient_addr};
    delay_timer->data = data;

    ev_timer_init(delay_timer, delay_cb, delay_ms / 1000.0, 0);
    ev_timer_start(loop, delay_timer);
}


void Node::delay_cb(EV_P_ ev_timer* w, int revents) {
    // Retrieve DelayData
    DelayData* data = static_cast<DelayData*>(w->data);
    Node* self = data->self;
    std::string message = data->message;
    sockaddr_in recipient_addr = data->recipient_addr;
    delete data;

    ssize_t nsend = sendto(self->sock_fd, message.c_str(), message.size(), 0,
                           (sockaddr*)&recipient_addr, sizeof(recipient_addr));
    if (nsend == -1) {
        LOG(ERROR) << "Failed to send delayed message to "
                   << inet_ntoa(recipient_addr.sin_addr) << ":" << ntohs(recipient_addr.sin_port);
    } else {
        LOG(INFO) << "Sent delayed message to "
                  << inet_ntoa(recipient_addr.sin_addr) << ":" << ntohs(recipient_addr.sin_port);
    }

    ev_timer_stop(self->loop, w);
    delete w;
}



void Node::run() {
    // Setup UDP socket
    LOG(INFO) << "Start running node on port " << port;
    sock_fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock_fd < 0) {
        LOG(FATAL) << "Failed to create socket.";
    }

    if (tcp_monitor) {
        LOG(INFO) << "Starting TCP monitoring";
        tcp_stat_manager.startMonitoring();
    }

    // Set socket to non-blocking
    fcntl(sock_fd, F_SETFL, O_NONBLOCK);

    // Bind socket to the specified port
    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(port);
    // we cannot use INADDR_ANY here, because we need to know the ip address of the current node
    addr.sin_addr.s_addr = INADDR_ANY;

    // bind to the ip address of the current node
    // Convert self_ip (string) to in_addr
    if (inet_pton(AF_INET, self_ip.c_str(), &addr.sin_addr) <= 0) {
        LOG(FATAL) << "Invalid IP address: " << self_ip;
    }

    if (bind(sock_fd, (sockaddr*)&addr, sizeof(addr)) < 0) {
        char ip_str[INET_ADDRSTRLEN];
        inet_ntop(AF_INET, &addr.sin_addr, ip_str, INET_ADDRSTRLEN);
        LOG(INFO) << "Binding to IP: " << ip_str << ", port: " << ntohs(addr.sin_port);
        LOG(FATAL) << "Failed to bind socket to port " << port;
    }

    // Initialize receive watcher
    ev_io_init(&recv_watcher, recv_cb, sock_fd, EV_READ);

    ev_set_priority(&recv_watcher, -2);

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

    if (self->tcp_monitor) {
        self->tcp_stat_manager.stopMonitoring();
        self->tcp_stat_manager.stopPeriodicStatsPrinting();
    }
    // Stop the event loop
    ev_break(EV_A_ EVBREAK_ALL);
}

void Node::start_election_timeout() {
    double timeout = dist(rng) / 1000.0; // Convert ms to seconds

    bool using_raft_timeout = true;

    // Check if there is an existing TCP connection with the leader or peers
    if (tcp_monitor)
    {
        std::lock_guard<std::mutex> lock(tcp_stat_manager.statsMutex);
        for (const auto& [connection, stats] : tcp_stat_manager.connectionStats) {
            if ((connection.first == self_ip && connection.second == current_leader_ip) ||
                (connection.second == self_ip && connection.first == current_leader_ip)) {
                double avgRttSec = stats.meanRtt() / 1000.0; // Convert microseconds to seconds
                if (avgRttSec > 0.0) {
//                    timeout = 2 * avgRttSec;
//                    get the 95 confidence interval and use the upperbound for the timeout
                    auto [lowerbound, upperbound] = stats.rttConfidenceInterval(confidence_level);
                    LOG(INFO) << "Using "<< confidence_level <<"% CI upperbound for RTT as election timueout: " << upperbound<< " MilliSeconds";
                    timeout = (upperbound / 2 + heartbeat_interval_margin) / 1000;
                    LOG(INFO) << "Using average RTT from TCP connection as election timeout: " << timeout << " MilliSeconds";
                    using_raft_timeout = false;
                }
                break;
            }
        }
    }
    if (using_raft_timeout) {
        LOG(INFO) << "Using Raft timeout for election timeout: " << timeout << " seconds";
    }

    ev_timer_init(&election_timer, election_timeout_cb, timeout, 0);
    ev_timer_start(loop, &election_timer);
    LOG(INFO) << "Election timeout started: " << timeout << " seconds";
}

void Node::reset_election_timeout() {
    ev_timer_stop(loop, &election_timer);

    LOG(INFO) << "resetting election timeout... the current term heartbeat count is " << heartbeat_current_term;
    start_election_timeout();

    LOG(INFO) << "Election timeout restarted. the current term heartbeat count is " << heartbeat_current_term;
}

void Node::election_timeout_cb(EV_P_ ev_timer* w, int revents) {
    Node* self = static_cast<Node*>(w->data);

    if (self->check_false_positive) {
        // In "check false positive rate mode", do not initiate leader election
        self->suspected_leader_failures++;
        LOG(INFO) << "Election timeout occurred. Suspected leader failure count: " << self->suspected_leader_failures;
    }

    LOG(INFO) << "Election timeout occurred. Starting leader election and voting for myself. View number: " << self->current_term << " Current term hb count " <<self->heartbeat_current_term; 
    LOG(INFO) << "The dead leader is " << self->current_leader_ip << ":" << self->current_leader_port;

    self->current_term++;
    self->role = Role::CANDIDATE;
    self->current_leader_ip = "";  
    self->current_leader_port = -1;
    self->voted_for = self->self_ip + ":" + std::to_string(self->port);
    self->votes_received = 0; // Vote for self later when it receives its own message

    self->heartbeat_current_term = 0;

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
    LOG(INFO) << "Heartbeat callback";
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
                self->handle_vote_response(response, sender_addr);
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
        if (role == Role::LEADER) {
            ev_timer_stop(loop, &heartbeat_timer);
        }
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
    LOG(INFO) << "Received request vote from " << candidate_id <<  " for term: " << received_term  << ". Vote granted: " << vote_granted;
    send_vote_response(response, send_addr);
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

// Utility function to convert sockaddr_in to string
std::string sockaddr_to_string(const sockaddr_in& addr) {
    char ip_str[INET_ADDRSTRLEN];
    memset(ip_str, 0, INET_ADDRSTRLEN);

    if (inet_ntop(AF_INET, &(addr.sin_addr), ip_str, INET_ADDRSTRLEN) == nullptr) {
        return "Invalid IP";
    }

    int port = ntohs(addr.sin_port);
    return std::string(ip_str) + ":" + std::to_string(port);
}

void Node::handle_vote_response(const raft::leader_election::VoteResponse& response, const sockaddr_in& sender_addr) {
    if (role != Role::CANDIDATE) {
        return;
    }

    // if the response has a bigger term number, indicating that out term has already expired. 
    // revert back to the follower. 
    if (response.term() > current_term) {
        LOG(INFO) << "[" << get_current_time() << "] Received vote response with a bigger term number: " << response.term() 
                  << ". Reverting back to follower.";
        current_term = response.term();
        role = Role::FOLLOWER;
        voted_for = "";
        return;
    }

    if (response.vote_granted()) {
        votes_received++;

        // Convert the sender's address to a readable string
        std::string sender = sockaddr_to_string(sender_addr);

        LOG(INFO) << "Received vote from: " << sender 
                  << " | Votes received: " << votes_received 
                  << " out of " << peer_addresses.size();

        // if bigger than f+1 in a 2f+1 setting
        if (votes_received >= peer_addresses.size() / 2 + 1) {
            LOG(INFO) << "Received enough votes to become leader. Term: " << current_term << ". Votes received: " << votes_received << " out of " << peer_addresses.size();
            // role = Role::LEADER;
            become_leader();
        }
    }
}

void Node::become_leader() {
    role = Role::LEADER;
    current_leader_ip = self_ip;
    current_leader_port = port;

    // reset the amount of heartbeats sent
    heartbeat_count = 0;
    votes_received = 0;

    // stop the election timeout
    ev_timer_stop(loop, &election_timer);

    LOG(INFO) << "[" << get_current_time() << "] Became leader. Starting to send heartbeats. Elected Term: " << current_term;

    // Initialize heartbeat timer
    ev_timer_init(&heartbeat_timer, heartbeat_cb, 0.0, 0.075); // 75 ms interval
    heartbeat_timer.data = this;
    ev_timer_start(loop, &heartbeat_timer);
}

void Node::send_heartbeat() {
    if (role != Role::LEADER) {
        LOG(INFO) << "Not a leader. Cannot send heartbeat.";
        if (role==Role::FOLLOWER) {
            LOG(INFO) << "Current leader is: " << current_leader_ip << ":" << current_leader_port;
            LOG(INFO) << "Current term is: " << current_term;
            LOG(INFO) << "I Am a follower";
        }
        if (role==Role::CANDIDATE) {
            LOG(INFO) << "Current leader is: " << current_leader_ip << ":" << current_leader_port;
            LOG(INFO) << "Current term is: " << current_term;
            LOG(INFO) << "I Am a candidate";
        }
        return;
    }

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

        if (use_simulated_links) {
            send_with_delay_and_loss(serialized_message, peer_addr);
        } else {
            ssize_t nsend = sendto(sock_fd, serialized_message.c_str(), serialized_message.size(), 0,
                                   (sockaddr*)&peer_addr, sizeof(peer_addr));
            if (nsend == -1) {
                LOG(ERROR) << "Failed to send heartbeat to " << ip << ":" << peer_port;
            } else {
                LOG(INFO) << "Sent heartbeat to " << ip << ":" << peer_port;
            }
        }
    }

    heartbeat_count++;
    LOG(INFO) << "[LEADER] Sent heartbeat " << heartbeat_count << " for term " << current_term;

    if (failure_leader) {
        LOG(INFO) << "Leader will simulate failure after " << max_heartbeats << " heartbeats.";
    }


    if (failure_leader && heartbeat_count >= max_heartbeats && role == Role::LEADER) {
        // Schedule failure within the heartbeat interval (75 ms)
        double random_delay = ((rand() % 75) + 1) / 1000.0; // Random delay between 1ms and 75ms
        ev_timer_init(&failure_timer, failure_cb, random_delay, 0);
        failure_timer.data = this;
        ev_timer_start(loop, &failure_timer);

        LOG(INFO) << "Leader will simulate failure after " << random_delay << " seconds.";
    }
}

void Node::failure_cb(EV_P_ ev_timer* w, int revents) {
    Node* self = static_cast<Node*>(w->data);

    // Stop the heartbeat timer to simulate failure
    ev_timer_stop(self->loop, &self->heartbeat_timer);

    // Optionally, log the simulated failure
    LOG(INFO) << "[" << get_current_time() << "] Leader has stopped for term: "<< self->current_term ;

    // Continue participating in other activities (e.g., receiving messages)
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

    if (received_term > current_term && ev_is_active(&heartbeat_timer)) {
        LOG(INFO) << "Got a heartbeat from another leader with bigger term, resetting current heartbeat count...";
        heartbeat_current_term = 0;
        ev_timer_stop(loop, &heartbeat_timer);
    }

    if (sender_addr.sin_addr.s_addr == inet_addr(self_ip.c_str())) {
        // Ignore messages from self
        return;
    }

    heartbeat_current_term++;

    if (check_false_positive) {
        recv_heartbeat_count++;
        LOG(INFO) << "Heartbeat received from leader " << leader_id << " for term " << received_term
                  << ". HB count for this term is: "<< heartbeat_current_term <<". False positive check mode is active, resetting election timeout. " << suspected_leader_failures << " failures out of " << recv_heartbeat_count; 
    }

    // If term is newer or equal, update current_term and leader info
    current_term = received_term;
    role = Role::FOLLOWER;
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
