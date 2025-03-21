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
      dist(config.timeoutLowerBound, config.timeoutUpperBound),                              // 13
      election_dist(500, 900),
      failure_leader(config.failureLeader),                       // 14
      current_leader_ip(""),                       // 15
      current_leader_port(-1),                     // 16
      view_number(0),                              // 17
      current_term(0),                             // 18
      voted_for(""),                               // 19
      votes_received(0),                           // 20
      max_heartbeats(config.maxHeartbeats),                           // 21 (set later if needed)
      heartbeat_count(0),                          // 22
      use_simulated_links(config.useSimulatedLinks),                  // 23 (set later if needed)
      loss_dist(0.0, 1.0),                         // 24
      delay_dist(config.delayLowerBound, config.delayUpperBound),                     // 25
      role(Role::FOLLOWER),                         // 26
      link_loss_rate(config.linkLossRate),          // 27
      tcp_stat_manager(config.peerIPs[replicaId]),
      confidence_level(config.confidenceLevel),
      heartbeat_interval_margin(config.heartbeatIntervalMargin),
      heartbeat_current_term(0),
      self_id(replicaId),
      penalty_scores(),  // Initialize the penalty_scores map
      petition_count(),  // Initialize the petition_count map
      latency_threshold(1000.0), // Set your desired latency threshold
      majority_count((config.peerIPs.size() + 1) / 2 + 1), // Calculate majority count
      safety_margin_lower_bound(config.safetyMarginLowerBound),
      safety_margin_step_size(config.safetyMarginStepSize)
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

    for (int i = 0; i < config.peerIPs.size(); ++i) {
        ip_to_id[config.peerIPs[i]] = i;
    }

    LOG(INFO) << "Node initialized with ID: " << self_id << ", IP: " << self_ip << ", port: " << port;

    if (failure_leader) {
        LOG(INFO) << "Failure leader mode enabled. Leader will fail after " << max_heartbeats << " heartbeats.";
    }

    network_interface = config.interfaces[replicaId];
    LOG(INFO) << "Network interface for the node is: " << network_interface << " according to the provided config.";

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

    start_penalty_timer();

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

void Node::start_election_timeout(bool double_time, bool force_raft) {
    double timeout = dist(rng) / 1000.0; // Convert ms to seconds

    bool using_raft_timeout = true;

    // // Calculate additional delay based on node IDs
    // int dead_leader_id = -1;

    // if (!current_leader_ip.empty()) {
    //     auto it = ip_to_id.find(current_leader_ip);
    //     if (it != ip_to_id.end()) {
    //         dead_leader_id = it->second;
    //     }
    // }

    // int delay_ms = 0;
    // if (dead_leader_id >= 0) {
    //     delay_ms = (abs(self_id - dead_leader_id) - 1) * 20;
    // } else {
    //     delay_ms = self_id * 20;  // Use self_id if dead leader ID is unknown
    // }

    // int delay_ms = (rand() % 31);

    // std::uniform_int_distribution<int> delay_distribution(20, 40);
    // int delay_ms = delay_distribution(rng);

    // Check if there is an existing TCP connection with the leader
    if (tcp_monitor && election_timeout_bound != raft && !force_raft) {

// use the penalty score to calculate:
// 1. sort the unordered map:
        std::vector<std::pair<std::string, double>> penalty_scores_sorted(penalty_scores.begin(), penalty_scores.end());

        // sort the vec based oin the value: the order is ascending form small to big
        std::sort(penalty_scores_sorted.begin(), penalty_scores_sorted.end(), 
            [](const std::pair<std::string, double>& a, const std::pair<std::string, double>& b) {
                return a.second < b.second;
            });

        int my_rank;
        // find my rank:
        for (int i = 0; i < penalty_scores_sorted.size(); i++) {
            if (penalty_scores_sorted[i].first == self_ip+":"+std::to_string(port)) {
                LOG(INFO) << "My rank is: " << i;
                // break;
                my_rank = i;
            }
            LOG(INFO) << "The rank of " << penalty_scores_sorted[i].first << " is: " << i << " with penalty score: " << penalty_scores_sorted[i].second;
        }

        // find the number of all peers including myself in the membership group:
        int total_peers = peer_addresses.size();

        // make these numbers configurable later:
        int lower_bound = safety_margin_lower_bound + safety_margin_step_size * my_rank;
        int upper_bound = safety_margin_lower_bound + safety_margin_step_size * (my_rank + 1);

        std::uniform_int_distribution<int> delay_distribution(lower_bound, upper_bound);
        int delay_ms = delay_distribution(rng);

        LOG(INFO) << "The safety margin for the election timeout is: " << delay_ms << " Milliseconds, lowerbound: " << lower_bound << " upperbound: " << upper_bound;

        std::lock_guard<std::mutex> lock(tcp_stat_manager.statsMutex);
        auto key = std::make_pair(self_ip, current_leader_ip);
        
        auto it = tcp_stat_manager.connectionStats.find(key);
        if (it != tcp_stat_manager.connectionStats.end()) {
            const TcpConnectionStats& stats = it->second;
            double avgRttSec = stats.meanRtt() / 1000.0; // Convert microseconds to seconds
            if (avgRttSec > 0.0) {
                if (election_timeout_bound == CI) {
                    auto [lowerbound, upperbound] = stats.rttConfidenceInterval(confidence_level);
                    LOG(INFO) << "Using " << confidence_level << "% CI upperbound for RTT as election timeout: " 
                              << upperbound << " Milliseconds";
                    if (!double_time) {
                        timeout = (upperbound / 2 + heartbeat_interval_margin + delay_ms) / 1000;
                    } else {
                        timeout = (upperbound + heartbeat_interval_margin + delay_ms) / 1000;
                    }
                    LOG(INFO) << "Using average RTT from TCP connection as election timeout: " << timeout << " Milliseconds";
                    using_raft_timeout = false;
                } else if (election_timeout_bound == Jacobson) {
                    if (!double_time) {
                        timeout = (stats.jacobsonEst() / 2 + heartbeat_interval_margin + delay_ms) / 1000;
                    } else {
                        timeout = (stats.jacobsonEst() + heartbeat_interval_margin + delay_ms) / 1000;
                    }
                    LOG(INFO) << "Using Jacobson estimation for election timeout: " << timeout *1000 << " Milliseconds, additional delay: " << delay_ms << " Milliseconds " << " jacob: " << stats.jacobsonEst()/2 << " heartbeat: " << heartbeat_interval_margin;
                    using_raft_timeout = false;
                }
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


void Node::reset_election_timeout(bool double_time, bool force_raft) {
    ev_timer_stop(loop, &election_timer);

    LOG(INFO) << "resetting election timeout... the current term heartbeat count is " << heartbeat_current_term;
    if (double_time) {
        start_election_timeout(true, force_raft);
    } else {
        start_election_timeout(false, force_raft);
    }

    LOG(INFO) << "Election timeout restarted. the current term heartbeat count is " << heartbeat_current_term;
}

void Node::election_timeout_cb(EV_P_ ev_timer* w, int revents) {
    LOG(INFO) << "Inside election timeout callback";
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

    self->latency_to_leader.clear(); 

    self->petition_count = 0;

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
                // LOG(INFO) << "Received append entries message.";
                break;
            }
            case raft::leader_election::MessageWrapper::PENALTY_SCORE: {
                raft::leader_election::PenaltyScore penalty_msg;
                if (!penalty_msg.ParseFromString(wrapper.payload())) {
                    LOG(ERROR) << "Failed to parse PenaltyScore message.";
                    return;
                }
                self->handle_penalty_score(penalty_msg, sender_addr);
                break;
            }
            case raft::leader_election::MessageWrapper::PETITION: {
                raft::leader_election::Petition petition_msg;
                if (!petition_msg.ParseFromString(wrapper.payload())) {
                    LOG(ERROR) << "Failed to parse Petition message.";
                    return;
                }
                self->handle_petition(petition_msg, sender_addr);
                break;
            }
            case raft::leader_election::MessageWrapper::APPEND_ENTRIES_RESPONSE: {
                raft::leader_election::AppendEntriesResponse response;
                if (!response.ParseFromString(wrapper.payload())) {
                    LOG(ERROR) << "Failed to parse AppendEntriesResponse message.";
                    return;
                }
                self->handle_append_entries_response(response, sender_addr);
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
        latency_to_leader.clear();
        petition_count = 0;
        role = Role::FOLLOWER;
        voted_for = ""; 
    }

    // section 5.4 of the raft paper enforces a trick that requies the leader to be up-to-date before being aboe to 
    // take the leadership role
    int last_log_index = raftLog.getLastLogIndex();
    int last_log_term = raftLog.getLastLogTerm();
    bool candidate_up_to_date = (request.last_log_term() > last_log_term) || 
                                 (request.last_log_term() == last_log_term && request.last_log_index() >= last_log_index);

    // this is important, ensure that a node only votes once per term. 
    bool vote_granted = false;
    if ((voted_for.empty() || voted_for == candidate_id) && candidate_up_to_date) {
        vote_granted = true;
        voted_for = candidate_id;
        reset_election_timeout(true, false);
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
        latency_to_leader.clear();
        petition_count = 0;
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

    for (const auto& [ip, peer_port] : peer_addresses) {
        std::string id = ip + ":" + std::to_string(peer_port);
        if (id != self_ip + ":" + std::to_string(port)) {
            next_index[id] = raftLog.getLastLogIndex() + 1;
            match_index[id] = 0;
        }
    }

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
    append_entries.set_id(++heartbeat_count);

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

    // heartbeat_count++;
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

        LOG(INFO) << "[Scheduled Failure Pending] Leader will simulate failure after " << random_delay << " seconds.";
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
    int id = append_entries.id();   

    int match_index = 0;

    // the RPC has a smaller term number than the current one, reject on the spot. 
    if (received_term < current_term) {
        raft::leader_election::AppendEntriesResponse response;
        response.set_term(current_term);
        response.set_success(false);

        LOG(INFO) << "Received Stale AppendEntries from " << leader_id << " for term " << received_term << " with id " << id;

        send_append_entries_response(response, sender_addr);
        return;
    }
    
    // this part is intended just for metrics of how many hertbeats have been received from the (previous) leader
    // and maybe we should start couting afresh. 
    if (received_term > current_term && ev_is_active(&heartbeat_timer)) {
        LOG(INFO) << "Got a heartbeat from another leader with bigger term, resetting current heartbeat count...";
        heartbeat_current_term = 0;
        ev_timer_stop(loop, &heartbeat_timer);
    }

    // TODO: I think this check could be forwarded to the dispatching thread, but for now, let's keep it here.
    if (sender_addr.sin_addr.s_addr == inet_addr(self_ip.c_str())) {
        // Ignore messages from self
        return;
    }


    LOG(INFO) << "Received AppendEntries from " << leader_id << " for term " << received_term << " with id " << id;

    // if (id != heartbeat_current_term + 1) {
    //     LOG(INFO) << "Received out of order heartbeat. Expected id: " << heartbeat_current_term << ", received id: " << id;
    //     return;
    // }
    heartbeat_current_term++;

    if (check_false_positive) {
        recv_heartbeat_count++;
        LOG(INFO) << "Heartbeat received from leader " << leader_id << " for term " << received_term
                  << ". HB count for this term is: "<< heartbeat_current_term <<". False positive check mode is active, resetting election timeout. " << suspected_leader_failures << " failures out of " << recv_heartbeat_count; 
    }

    // If term is newer or equal, update current_term and leader info
    if (received_term > current_term) {
        current_term = received_term;
        // not part of the original raft specification
        latency_to_leader.clear();
        petition_count = 0;
    }

    // above we eliminate cases where the newly received term number is smaller than the current term number.
    // all below: we are in the case where the term number is the same or bigger than the current term number.
    // should convert to folloer and acknoledge the new leader in whaever cases.  
    current_term = received_term;
    role = Role::FOLLOWER;
    current_leader_ip = leader_id.substr(0, leader_id.find(':'));
    current_leader_port = std::stoi(leader_id.substr(leader_id.find(':') + 1));
    voted_for = ""; // Reset voted_for in the new term
    LOG(INFO) << "resetting election timeout... the current term is " << current_term << " and the current leader is " << current_leader_ip << ":" << current_leader_port;
    reset_election_timeout(); // Reset election timeout upon receiving heartbeat
    // Assuming logs are consistent for simplicity
    LOG(INFO) << "DONE resetting election timeout... the current term is " << current_term << " and the current leader is " << current_leader_ip << ":" << current_leader_port;


    // Begin processing for the potential new log entries. 
    // reply false if log does not contain an entry at prevLogIndex whose term matches prevLogTerm
    if (!raftLog.containsEntry(append_entries.prev_log_index(), append_entries.prev_log_term())) {
        raft::leader_election::AppendEntriesResponse response;
        response.set_term(current_term);
        response.set_success(false);
        response.set_match_index(match_index);

        // TODO: we can optionally include conflict information, omitted here for now
        send_append_entries_response(response, sender_addr);
        return;
    }

    // implementation in referecen to this: https://github.com/ongardie/raftscope/blob/master/raft.js
    int index = append_entries.prev_log_index();

    // If an existing entry conflicts with a new one (same index but different terms), delete the existing entry and all that follow it
    {
        std::lock_guard<std::mutex> lock(raftLog.log_mutex);
        // this is the index that we start insering, and wiping out all inconsistent entries.
        int insertion_index = append_entries.prev_log_index() + 1;
        for (int i = 0; i < append_entries.entries_size(); i++) {
            index++;
            const raft::leader_election::LogEntry& new_entry = append_entries.entries(i);
            LogEntry existingEntry;
            if (raftLog.getEntry(insertion_index, existingEntry)) {
                if (existingEntry.term != new_entry.term()) {
                    raftLog.deleteEntriesStartingFrom(insertion_index);
                    raftLog.appendEntry(new_entry.term(), new_entry.command());
                }
                // if matches, do nothing, and continue to the next one
            } else {
                // if the position is empty, just append the new entry
                raftLog.appendEntry(new_entry.term(), new_entry.command());
            }
            insertion_index++;
        }
    }

    match_index = index;

    // if leaderCommit > commitIndex, set commitIndex = min(leaderCommit, index of last new entry)
    if (append_entries.leader_commit() > raftLog.getCommitIndex()) {
        std::lock_guard<std::mutex> lock(raftLog.log_mutex);
        raftLog.commitIndex = std::min(append_entries.leader_commit(), raftLog.getLastLogIndex());
        // TODO: Implement the persistence
        // apply_committed_entries(); // persist the changes to the state machine
    }

    raft::leader_election::AppendEntriesResponse response;
    response.set_term(current_term);
    response.set_success(true);
    response.set_match_index(match_index);

    send_append_entries_response(response, sender_addr);

    // LOG(INFO) << "Received heartbeat (AppendEntries) from leader " << leader_id << " for term " << received_term;
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

void Node::start_penalty_timer() {
    double interval = 1.0; // Interval in seconds
    ev_timer_init(&penalty_timer, penalty_timer_cb, 0.0, interval);
    penalty_timer.data = this;
    ev_timer_start(loop, &penalty_timer);
}

void Node::penalty_timer_cb(EV_P_ ev_timer* w, int revents) {
    Node* self = static_cast<Node*>(w->data);
    self->calculate_and_send_penalty_score();
}


void Node::calculate_and_send_penalty_score() {
    // Calculate penalty score
    double penalty_score = compute_penalty_score();

    penalty_scores[self_ip + ":" + std::to_string(port)] = penalty_score;

    // Create PenaltyScore message
    raft::leader_election::PenaltyScore penalty_msg;
    penalty_msg.set_term(current_term);
    penalty_msg.set_node_id(self_ip + ":" + std::to_string(port));
    penalty_msg.set_penalty_score(penalty_score);

    // Wrap and serialize the message
    raft::leader_election::MessageWrapper wrapper;
    wrapper.set_type(raft::leader_election::MessageWrapper::PENALTY_SCORE);
    wrapper.set_payload(penalty_msg.SerializeAsString());

    std::string serialized_message = wrapper.SerializeAsString();

    // Send the message to all peers
    for (const auto& [ip, peer_port] : peer_addresses) {
        sockaddr_in peer_addr{};
        peer_addr.sin_family = AF_INET;
        peer_addr.sin_port = htons(peer_port);
        inet_pton(AF_INET, ip.c_str(), &peer_addr.sin_addr);

        ssize_t nsend = sendto(sock_fd, serialized_message.c_str(), serialized_message.size(), 0,
                               (sockaddr*)&peer_addr, sizeof(peer_addr));

        if (nsend == -1) {
            LOG(ERROR) << "Failed to send penalty score to " << ip << ":" << peer_port;
        } else {
            LOG(INFO) << "Sent penalty score to " << ip << ":" << peer_port;
        }
    }
}

double Node::compute_penalty_score() {
    // make these tunable parameters from the config later. 
    double w = 1.0;     // Weight factor
    double T = 100.0;   // Threshold in milliseconds
    int N = peer_addresses.size() + 1; // Total number of nodes including self

    double sum = 0.0;
    for (const auto& [ip, peer_port] : peer_addresses) {
        std::string peer_id = ip + ":" + std::to_string(peer_port);

        // Skip self
        if (peer_id == self_ip + ":" + std::to_string(port)) {
            continue;
        }

        // Get L_ij (latency to peer j)
        double L_ij = get_latency_to_peer(peer_id);

        LOG(INFO) << "Latency to " << peer_id << " is: " << L_ij;

        double penalty = L_ij + w * std::max(0.0, L_ij - T);
        sum += penalty;
    }

    double penalty_score = sum / (N - 1);
    LOG(INFO) << "Calculated penalty score for myself is: " << penalty_score;

    // Get latency to current leader
    double latency_to_leader = get_latency_to_peer(current_leader_ip + ":" + std::to_string(current_leader_port));

    LOG(INFO) << "Latency to leader " << current_leader_ip << ":" << current_leader_port << " is: " << latency_to_leader << " ms";

    // Check if latency exceeds threshold
    if (latency_to_leader > latency_threshold && role != Role::LEADER) {
        LOG(INFO) << "Latency to leader exceeds threshold. Initiating petition process.";

        // Find the node with the lowest penalty score (excluding the leader)
        std::string proposed_leader = "";
        double lowest_penalty = std::numeric_limits<double>::max();

        for (const auto& [node_id, penalty] : penalty_scores) {
            if (node_id != current_leader_ip + ":" + std::to_string(current_leader_port)) {
                if (penalty < lowest_penalty) {
                    lowest_penalty = penalty;
                    proposed_leader = node_id;
                }
            }
        }

        // Send a petition to the proposed leader
        if (!proposed_leader.empty() && proposed_leader != self_ip + ":" + std::to_string(port)) {
            send_petition(proposed_leader, latency_to_leader);
        }
    }

    return penalty_score;
}


void Node::send_petition(const std::string& proposed_leader, double latency_to_leader) {
    // Create Petition message
    raft::leader_election::Petition petition_msg;
    petition_msg.set_term(current_term);
    petition_msg.set_current_leader(current_leader_ip + ":" + std::to_string(current_leader_port));
    petition_msg.set_proposed_leader(proposed_leader);
    petition_msg.set_latency_to_leader(latency_to_leader);
    petition_msg.set_sender_id(self_ip + ":" + std::to_string(port));

    // Wrap and serialize the message
    raft::leader_election::MessageWrapper wrapper;
    wrapper.set_type(raft::leader_election::MessageWrapper::PETITION);
    wrapper.set_payload(petition_msg.SerializeAsString());

    std::string serialized_message = wrapper.SerializeAsString();

    // Send the petition to the proposed leader
    std::string proposed_leader_ip = proposed_leader.substr(0, proposed_leader.find(':'));
    int proposed_leader_port = std::stoi(proposed_leader.substr(proposed_leader.find(':') + 1));

    sockaddr_in peer_addr{};
    peer_addr.sin_family = AF_INET;
    peer_addr.sin_port = htons(proposed_leader_port);
    inet_pton(AF_INET, proposed_leader_ip.c_str(), &peer_addr.sin_addr);

    ssize_t nsend = sendto(sock_fd, serialized_message.c_str(), serialized_message.size(), 0,
                           (sockaddr*)&peer_addr, sizeof(peer_addr));

    if (nsend == -1) {
        LOG(ERROR) << "Failed to send petition to " << proposed_leader;
    } else {
        LOG(INFO) << "Sent petition to " << proposed_leader;
    }
}


void Node::handle_penalty_score(const raft::leader_election::PenaltyScore& penalty_msg, const sockaddr_in& sender_addr) {
    std::string node_id = penalty_msg.node_id();
    double penalty = penalty_msg.penalty_score();

    // Store the received penalty score
    penalty_scores[node_id] = penalty;

    LOG(INFO) << "Received penalty score from " << node_id << ": " << penalty;
}


double Node::get_latency_to_peer(const std::string& peer_id) {
    // Use tcp_stat_manager to get RTT to peer
    if (tcp_monitor) {
        std::lock_guard<std::mutex> lock(tcp_stat_manager.statsMutex);
        auto key = std::make_pair(self_ip, peer_id.substr(0, peer_id.find(':')));

        auto it = tcp_stat_manager.connectionStats.find(key);
        if (it != tcp_stat_manager.connectionStats.end()) {
            LOG(INFO) << "RTT data is available for " << peer_id;
            const TcpConnectionStats& stats = it->second;
            double avgRttMs = stats.meanRtt(); // In milliseconds
            return avgRttMs;
        } else {
            LOG(INFO) << "No RTT data available for " << peer_id;
        }
    }
    // If no data is available, return -1 to indicate non availability
    return -1;
}

void Node::handle_client_request(const raft::client::ClientRequest& request, const sockaddr_in& sender_addr) {
    if (role != Role::LEADER) {
        auto client_id = request.client_id();
        auto client_request_id = request.request_id();
        LOG(INFO) << "Not a leader. Cannot handle client request.";
        raft::client::ClientResponse response;  
        response.set_success(false);    
        response.set_response("Not a leader. Leader: " + current_leader_ip + ":" + std::to_string(current_leader_port));
        response.set_client_id(client_id);
        response.set_request_id(client_request_id);
        send_client_response(response, sender_addr);    
        return;
    }

    // append new command as a log entry
    int new_log_index = raftLog.getLastLogIndex() + 1;
    LogEntry new_entry { current_term, request.command() };
    {
        std::lock_guard<std::mutex> lock(raftLog.log_mutex);
        raftLog.appendEntry(new_entry);
    }

    // communicate with the other replicas in the system
    // first get the prev log term and prev log index, needede for append entries RPC. 
    int prev_index = new_log_index - 1;
    int prev_term = -1;
    if (prev_index > 0) {
        LogEntry prev_entry;
        raftLog.getEntry(prev_index, prev_entry);
        prev_term = prev_entry.term;
    }
    // TODO High Priority: Implement the request queue
    // TODO: Instead of sending off the request ASA it is received. 
    // poll from a request queue (concurrent) until it is empty

    // this function will either dispatch immeidiately, or wait for a batch to form, more flexibility. 
    send_proposals_to_followers(current_term, raftLog.commitIndex);
    // raft::leader_election::AppendEntries append_entries;
    // append_entries.set_term(current_term);  
    // append_entries.set_leader_id(self_ip + ":" + std::to_string(port));
    // append_entries.set_prev_log_index(prev_index);
    // append_entries.set_prev_log_term(prev_term);

    // *append_entries.add_entries() = convertToProto(new_entry);
    // append_entries.set_leader_commit(raftLog.commitIndex);

}

void Node::send_proposals_to_followers(int current_term, int commit_index) {
    // Iterate over each follower (skip self).
    for (const auto& [ip, peer_port] : peer_addresses) {
        std::string follower_id = ip + ":" + std::to_string(peer_port);
        if (follower_id == self_ip + ":" + std::to_string(port))
            continue;

        // Get the starting index for this follower.
        int start_index = next_index[follower_id];

        // Prepare an AppendEntries RPC containing log entries from start_index to the current last log index.
        raft::leader_election::AppendEntries append_entries;
        append_entries.set_term(current_term);
        append_entries.set_leader_id(self_ip + ":" + std::to_string(port));

        // The preceding log index/term.
        int prev_index = start_index - 1;
        int prev_term = 0;
        if (prev_index > 0) {
            LogEntry prevEntry;
            if (raftLog.getEntry(prev_index, prevEntry))
                prev_term = prevEntry.term;
        }
        append_entries.set_prev_log_index(prev_index);
        append_entries.set_prev_log_term(prev_term);

        // Add all entries from start_index onwards.
        for (int i = start_index; i <= raftLog.getLastLogIndex(); i++) {
            LogEntry entry;
            if (raftLog.getEntry(i, entry)) {
                *append_entries.add_entries() = convertToProto(entry);
            }
        }
        append_entries.set_leader_commit(commit_index);

        // Serialize and send this RPC to the follower.
        raft::leader_election::MessageWrapper wrapper;
        wrapper.set_type(raft::leader_election::MessageWrapper::APPEND_ENTRIES);
        wrapper.set_payload(append_entries.SerializeAsString());
        std::string serialized_message = wrapper.SerializeAsString();

        sockaddr_in peer_addr{};
        peer_addr.sin_family = AF_INET;
        peer_addr.sin_port = htons(peer_port);
        inet_pton(AF_INET, ip.c_str(), &peer_addr.sin_addr);

        ssize_t nsend = sendto(sock_fd, serialized_message.c_str(), serialized_message.size(), 0,
                               (sockaddr*)&peer_addr, sizeof(peer_addr));
        if (nsend == -1) {
            LOG(ERROR) << "Failed to send proposals to " << ip << ":" << peer_port;
        } else {
            LOG(INFO) << "Sent proposals to " << ip << ":" << peer_port;
        }
    }
}



void Node::send_client_response(const raft::client::ClientResponse& response, const sockaddr_in& recipient_addr) {
    std::string serialized_message = response.SerializeAsString();

    ssize_t nsend = sendto(sock_fd, serialized_message.c_str(), serialized_message.size(), 0,
                           (sockaddr*)&recipient_addr, sizeof(recipient_addr));
    if (nsend == -1) {
        LOG(ERROR) << "Failed to send client response.";
    } else {
        LOG(INFO) << "Sent client response to "
                  << inet_ntoa(recipient_addr.sin_addr) << ":" << ntohs(recipient_addr.sin_port);
    }
}


void Node::handle_petition(const raft::leader_election::Petition& petition_msg, const sockaddr_in& sender_addr) {
    std::string proposed_leader = petition_msg.proposed_leader();
    double reported_latency = petition_msg.latency_to_leader();
    std::string sender_id = petition_msg.sender_id();

    int received_term = petition_msg.term();
    std::string current_leader = petition_msg.current_leader();
    if (received_term != current_term) {
        LOG(INFO) << "Received stale petition for term " << received_term << " while current term is " << current_term;
        return;
    }

    if (current_leader != current_leader_ip + ":" + std::to_string(current_leader_port)) {
        LOG(INFO) << "Received petition from " << sockaddr_to_string(sender_addr) << " for stale leader " << current_leader;
        return;
    }

    if (proposed_leader != self_ip + ":" + std::to_string(port)) {
        LOG(INFO) << "Received petition for another node. Ignoring.";
        return;
    }

    latency_to_leader[sender_id] = reported_latency;

    LOG(INFO) << "Received petition from " << sockaddr_to_string(sender_addr)
              << " proposing leader " << proposed_leader
              << " due to high latency to current leader (" << reported_latency << " ms)";

    // Update petition count
    {
        std::lock_guard<std::mutex> lock(petition_mutex);
        petition_count++;
    }


    if (petition_count >= majority_count) {
        LOG(INFO) << "Received petitions from majority for proposed leader " << proposed_leader;
        bool petition_succeed = true;

        for (const auto& [sender_id, latency] : latency_to_leader) {
            LOG(INFO) << "Latency to leader " << sender_id << ": " << latency << " ms";
            auto my_latency = get_latency_to_peer(sender_id);
            LOG(INFO) << "My latency to peer " << sender_id << ": " << my_latency << " ms";

            // TODO: Remove the 20 ms margin
            // the 20 is for testing purposes, and should be removed later.
            if (my_latency > latency + 20) {
                petition_succeed = false;
                break;
            }
        }

        if (petition_succeed) {
            LOG(INFO) << "Petition succeeded. Changing leader to " << proposed_leader;

            current_term++;
            role = Role::CANDIDATE;
            current_leader_ip = "";  
            current_leader_port = -1;
            voted_for = self_ip + ":" + std::to_string(port);
            votes_received = 0; // Vote for self later when it receives its own message

            latency_to_leader.clear(); 

            petition_count = 0;

            heartbeat_current_term = 0;

            // start_election_timeout();
            reset_election_timeout();
            send_request_vote();
        //     current_term++;
        //     role = Role::CANDIDATE;
        //     voted_for = self_ip + ":" + std::to_string(port);
        //     votes_received = 0;

        //     // LOG(INFO) << "[petition] Petition Succeed!";

        //     start_election_timeout();
        //     send_request_vote();
        //     // Reset the petition count after handling
        //     {
        //         std::lock_guard<std::mutex> lock(petition_mutex);
        //         petition_count = 0;
        //         latency_to_leader.clear();
        //     }
        } else {
            LOG(INFO) << "Petition failed. Not changing leader.";
        }
    }
}

void Node::handle_append_entries_response(const raft::leader_election::AppendEntriesResponse& response, const sockaddr_in& sender_addr) {
    if (role != Role::LEADER) {
        return;
    }

    int received_term = response.term();
    if (received_term > current_term) {
        current_term = received_term;
        role = Role::FOLLOWER;
        voted_for = "";
        latency_to_leader.clear();
        petition_count = 0;
        return;
    }

    std::string sender_ip = inet_ntoa(sender_addr.sin_addr);
    int sender_port = ntohs(sender_addr.sin_port);
    std::string sender_id = sender_ip + ":" + std::to_string(sender_port);
    
    if (response.success()) {
        // according to the implementation specification at: https://github.com/ongardie/raftscope/blob/master/raft.js
        match_index[sender_id] = std::max(match_index[sender_id], response.match_index());
        next_index[sender_id] = response.match_index() + 1;
    } else {
        // // If conflict_index is provided, set next_index accordingly:
        // if (response.set_conflict_index()) {
        //     next_index[sender_id] = response.conflict_index();
        // } else {
            // Fallback: decrement by one (ensuring it stays at least 1)
            next_index[sender_id] = std::max(1, next_index[sender_id] - 1);
    }
}

void Node::updated_commit_index() {
    std::lock_guard<std::mutex> lock(raftLog.log_mutex);

    int new_commit_index = raftLog.commitIndex;
    int last_log_index = raftLog.getLastLogIndex();
    for (int i = raftLog.commitIndex + 1; i <= last_log_index; i++) {
        int count = 1; // Count self
        for (const auto& [ip, peer_port] : peer_addresses) {
            std::string id = ip + ":" + std::to_string(peer_port);
            if (match_index[id] >= i) {
                count++;
            }
        }
        if (count >= majority_count) {
            LogEntry entry;
            if (raftLog.getEntry(i, entry) && entry.term == current_term) {
                new_commit_index = i;
            }
        }
    }

    if (new_commit_index != raftLog.commitIndex) {
        raftLog.commitIndex = new_commit_index;
        LOG(INFO) << "Advanced commit index to: " << new_commit_index;
        // Optionally, trigger applying the newly committed entries to the state machine.
        // apply_committed_entries();
    }
}