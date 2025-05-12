#include "node.h"
#include <sstream>
#include <cstring>

thread_local int Node::tls_worker_id = -1;

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
      port(config.clientPort),                                  // 10
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
    //   latency_threshold(1000.0), // Set your desired latency threshold
      majority_count((config.peerIPs.size() + 1) / 2), // Calculate majority count
      safety_margin_lower_bound(config.safetyMarginLowerBound),
      safety_margin_step_size(config.safetyMarginStepSize), 
      worker_threads_count(config.workerThreadsCount), 
      sender_threads_count(config.senderThreadsCount),
      client_port(config.clientPort),
      internal_base_port(config.internalBasePort), 
      replica_id(replicaId), 
      eligible_leaders(config.eligibleLeaders), 
      initial_eligible_leaders(config.initialEligibleLeaders),
      check_overhead(config.checkOverhead), 
      spinCheckCount(config.spinCheckCount),
      spinCheckInterval(config.spinCheckInterval), 
      tcp_monitor_freq(config.tcpMonitorFrequency), 
      latency_threshold(config.latency_threshold)
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

    for (const auto& peer : peerIPs) {
        peer_addresses.emplace_back(peer, internal_base_port + replicaId);

        if (peer != self_ip) {
            inflight_[peer].store(false, std::memory_order_relaxed);        
        }
    }

    // for (std::size_t id = 0; id < peerIPs.size(); ++id) {
    //     peer_addresses.emplace_back(peerIPs[id], internal_base_port + id);
    // }

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


    // need to constructy the sockets here. 
    // client sokcet. 
    clientSock_ = makeBoundUDPSocket(self_ip, client_port);
    clientCtx_.fd = clientSock_;
    clientCtx_.loop = ev_loop_new(EVFLAG_AUTO);

    LOG(INFO) << "Client socket created with fd: " << clientSock_ << ", port: " << client_port;

    // then we could contruc one socket per peer, including ourselves for simpler addressing:
    for (int id = 0; id < peerIPs.size(); id++) {
        int port = internal_base_port + id;
        int fd = makeBoundUDPSocket(self_ip, port);
        peerCtx_[id] = {fd, {}, ev_loop_new(EVFLAG_AUTO)};
        LOG(INFO) << "Peer socket created with fd: " << fd << ", port: " << port;
    }

    if (failure_leader) {
        LOG(INFO) << "Failure leader mode enabled. Leader will fail after " << max_heartbeats << " heartbeats.";
    }

    network_interface = config.interfaces[replicaId];
    LOG(INFO) << "Network interface for the node is: " << network_interface << " according to the provided config.";

    // change the fd mode:
    if (config.fdMode == "raft") {
        election_timeout_bound = raft;
    } else if (config.fdMode == "Jacobson") {
        election_timeout_bound = Jacobson;
    } else if (config.fdMode == "CI") {
        election_timeout_bound = CI;
    } else {
        LOG(FATAL) << "Invalid fd mode: " << config.fdMode; 
    }

    LOG(INFO) << "Eligible Leaders replica IDs: ";
    for (const auto& id : eligible_leaders) {
        LOG(INFO) << id;
    }

}

void Node::send_with_delay_and_loss(const std::string& message, const sockaddr_in& recipient_addr) {
    LOG(INFO) << "Inside send_with_delay_and_loss function";
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
    if (tcp_monitor) {
        LOG(INFO) << "Starting TCP monitoring";
        tcp_stat_manager.startMonitoring();
    }

    receiverThreads.emplace_back([ctx=&clientCtx_, this] { runRecvLoopClient(ctx, -1); });

    for (auto& [id, ctx] : peerCtx_) {
        // capture `this`, the pointer-to-ctx, and the peer id all by value:
        receiverThreads.emplace_back([this, ctx = &ctx, id]() {
            runRecvLoop(ctx, id);
        });
    }

    int numReceivers = receiverThreads.size();
    recvQueues.reserve(numReceivers);
    for (int i = 0; i < numReceivers; ++i) {
        recvQueues.emplace_back();
    }

    outQueues_.reserve(worker_threads_count);
    for (int i = 0; i < worker_threads_count; ++i) {
        outQueues_.emplace_back(std::make_unique<SendQueue>());
    }

    for (int i = 0; i < sender_threads_count; ++i) {
        senderThreads_.emplace_back(&Node::senderThreadFunc, this);
    }


    // before starting the election timeout, let us first init the async watcher for worker threads:
    ev_async_init(&election_async_watcher, Node::election_async_cb);
    election_async_watcher.data = this;
    // register this async wather with the main event loop:
    ev_async_start(loop, &election_async_watcher);

    // Start election timeout
    start_election_timeout();

    ev_timer_init(&shutdown_timer, shutdown_cb, runtime_seconds, 0);
    shutdown_timer.data = this;
    ev_timer_start(loop, &shutdown_timer);


    if (tcp_monitor) {
        start_penalty_timer();
    }

    // start running the worker threads. 
    startWorkerThreads(worker_threads_count);

    // Start the event loop
    ev_run(loop, 0);

    // After event loop stops, dump the raft log.
    std::string filename = "raftlog_dump_" + self_ip + "_" + std::to_string(port) + ".log";
    dumpRaftLogToFile(filename);
    LOG(INFO) << "Node shutting down. Raft log dumped to " << filename;
}


void Node::runRecvLoop(UDPSocketCtx* ctx, int peerId) {
    ev_io_init(&ctx->watcher, recv_cb, ctx->fd, EV_READ);
    ctx->watcher.data = new std::pair<Node*, int>(this, peerId);
    ev_io_start(ctx->loop, &ctx->watcher);
    ev_run(ctx->loop, 0);
}

void Node::runRecvLoopClient(UDPSocketCtx* ctx, int peerId) {
    ev_io_init(&ctx->watcher, recv_client_cb, ctx->fd, EV_READ);
    ctx->watcher.data = this;
    ev_io_start(ctx->loop, &ctx->watcher);
    ev_run(ctx->loop, 0);
}

int Node::createBoundSocket() {
    int s = socket(AF_INET, SOCK_DGRAM, 0);
    if (s < 0) {
        LOG(ERROR) << "Failed to create socket";
        return -1;
    }

    int optval = 1;
    if (setsockopt(s, SOL_SOCKET, SO_REUSEPORT, &optval, sizeof(optval)) < 0) {
        LOG(ERROR) << "Failed to setsockopt SO_REUSEPORT";
        close(s);
        return -1;
    }

    // set the socket mode to non-blocking. 
    int flags = fcntl(s, F_GETFL, 0);
    if (flags == -1) flags = 0;
    if (fcntl(s, F_SETFL, flags | O_NONBLOCK) < 0) {
        perror("fcntl non-blocking");
        close(s);
        return -1;
    }

    // bind the socket to the port and to the specified address. 
    sockaddr_in addr;
    addr.sin_family = AF_INET;
    addr.sin_port = htons(port);
    addr.sin_addr.s_addr = INADDR_ANY;

    // change the ip address to the legitimate one. 
    if (inet_pton(AF_INET, self_ip.c_str(), &addr.sin_addr) <= 0) {
        LOG(FATAL) << "Invalid IP address: " << self_ip;
    }

    // actually bind the sock to the address and port. 
    if (bind(s, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) < 0) {
        char ip_str[INET_ADDRSTRLEN];
        inet_ntop(AF_INET, &addr.sin_addr, ip_str, INET_ADDRSTRLEN);
        LOG(INFO) << "Binding to IP: " << ip_str << ", port: " << ntohs(addr.sin_port);
        LOG(FATAL) << "Failed to bind socket to port " << port;

        close(s);
        return -1;
    } 

    LOG(INFO) << "Receiver Thread: Bound to the socket " << s;

    // return the socket fd number. 
    return s;
}

void Node::election_async_cb(EV_P_ ev_async* w, int revents) {
    Node* self = static_cast<Node*>(w->data);
    self->process_election_async_task();
}

void Node::process_election_async_task() {
    std::function<void()> task;
    while (true) {
        {
            std::lock_guard<std::mutex> lock(election_async_mutex);
            if (election_async_tasks.empty())
                break;
            task = std::move(election_async_tasks.front());
            election_async_tasks.pop();
        }
        // Execute the task in the event loop thread.
        task();
    }
}


void Node::shutdown_cb(EV_P_ ev_timer* w, int revents) {
    Node* self = static_cast<Node*>(w->data);
    LOG(WARNING) << "Runtime exceeded (" << self->runtime_seconds << " seconds). Shutting down node.";

    if (self->tcp_monitor) {
        self->tcp_stat_manager.stopMonitoring();
        self->tcp_stat_manager.stopPeriodicStatsPrinting();
    }

    self->shutdownWorkers.store(true);
    // join all worker threads:
    // Note of implementation: we need auto& to work with references of threads, not copies
    for (auto& thread : self->workerThreads) {
        if (thread.joinable()) {
            thread.join();
        }
    }

    for (auto& t : self->senderThreads_)
    {
        if (t.joinable()) t.join();
    }

    // Stop the event loop
    ev_break(EV_A_ EVBREAK_ALL);
    LOG(WARNING) << "Dumping raft log before shutdown.";
    std::string filename = "raftlog_dump_" + self->self_ip  + ".log";
    self->dumpRaftLogToFile(filename);
    LOG(INFO) << "Node shutting down. Raft log dumped to " << filename;

    // TODO: Fix with libev async!!!

    for (auto& [id, ctx] : self->peerCtx_) {
        ev_break(ctx.loop, EVBREAK_ALL);
    }
    ev_break(self->clientCtx_.loop, EVBREAK_ALL);   // client socket loop

    // we should also join the receiver threads. 
    for (auto& thread : self->receiverThreads) {
        if (thread.joinable()) {
            thread.join();
        }
    }

    LOG(INFO) << "Node shutdown complete.";
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
                LOG(WARNING) << "My rank is: " << i;
                // break;
                my_rank = i;
            }
            LOG(WARNING) << "The rank of " << penalty_scores_sorted[i].first << " is: " << i << " with penalty score: " << penalty_scores_sorted[i].second;
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
                        timeout = (stats.jacobsonEst() + heartbeat_interval_margin + delay_ms) / 1000;
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
        LOG(INFO) << "Using Raft estimation for election timeout: " << timeout*1000 << " Milliseconds";
    }

    ev_timer_init(&election_timer, election_timeout_cb, timeout, 0);
    ev_timer_start(loop, &election_timer);
    LOG(INFO) << "Election timeout started: " << timeout << " seconds";
}


void Node::reset_election_timeout(bool double_time, bool force_raft) {
    ev_timer_stop(loop, &election_timer);

    // LOG(INFO) << "resetting election timeout... the current term heartbeat count is " << heartbeat_current_term;
    if (double_time) {
        start_election_timeout(true, force_raft);
    } else {
        start_election_timeout(false, force_raft);
    }

    LOG(INFO) << "Election timeout restarted. the current term heartbeat count is " << heartbeat_current_term;
}

void Node::election_timeout_cb(EV_P_ ev_timer* w, int revents) {
    // LOG(INFO) << "Inside election timeout callback";
    Node* self = static_cast<Node*>(w->data);
    std::lock_guard<std::mutex> lock(self->state_mutex);

    if (self->check_false_positive) {
        // In "check false positive rate mode", do not initiate leader election
        self->suspected_leader_failures++;
        LOG(WARNING) << "Election timeout occurred. Suspected leader failure count: " << self->suspected_leader_failures;
    }

    LOG(WARNING) << "Election timeout occurred. Starting leader election and voting for myself. View number: " << self->current_term << " Current term hb count " <<self->heartbeat_current_term; 
    LOG(INFO) << "The dead leader is " << self->current_leader_ip << ":" << self->current_leader_port;


    // if initial election
    if (self->current_term == 0 && self->current_leader_ip.empty()) {
        LOG(INFO) << "Initial election. Current term: " << self->current_term;
        auto it = std::find(self->initial_eligible_leaders.begin(), self->initial_eligible_leaders.end(), self->replica_id);
        if (it == self->initial_eligible_leaders.end()) {
            LOG(INFO) << "Current node is not an eligible initial leader. Skipping leader election.";
            return;
        }
    }

    if (self->eligible_leaders.size() > 0) {
        // Check if the current node is an eligible leader
        auto it = std::find(self->eligible_leaders.begin(), self->eligible_leaders.end(), self->replica_id);
        if (it == self->eligible_leaders.end()) {
            LOG(INFO) << "Current node is not an eligible leader. Skipping leader election.";
            return;
        }
    }

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
    request.set_last_log_index(raftLog.getLastLogIndex());
    request.set_last_log_term(raftLog.getLastLogTerm());

    raft::leader_election::MessageWrapper wrapper;
    wrapper.set_type(raft::leader_election::MessageWrapper::REQUEST_VOTE);
    wrapper.set_payload(request.SerializeAsString());

    std::string serialized_message = wrapper.SerializeAsString();

    for (const auto& [ip, peer_port] : peer_addresses) {
        int id  = peerIdFromIp(ip);                 // ←  peer‑id
        sockaddr_in dst{};
        dst.sin_family = AF_INET;
        dst.sin_port   = htons(peer_port);
        inet_pton(AF_INET, ip.c_str(), &dst.sin_addr);

        // sendToPeer(id, std::move(wrapper), dst);
        sendSerialized(id, serialized_message, dst);
        LOG(INFO) << "Sent RequestVote to " << ip << ":" << peer_port;
    }
}

void Node::send_request_vote(bool is_petition) {
    raft::leader_election::RequestVote request;
    request.set_term(current_term);
    request.set_candidate_id(self_ip + ":" + std::to_string(port));
    request.set_last_log_index(raftLog.getLastLogIndex());
    request.set_last_log_term(raftLog.getLastLogTerm());

    if (is_petition) {
        request.set_is_petition(true);
    } else {
        request.set_is_petition(false);
    }

    raft::leader_election::MessageWrapper wrapper;
    wrapper.set_type(raft::leader_election::MessageWrapper::REQUEST_VOTE);
    wrapper.set_payload(request.SerializeAsString());

    std::string serialized_message = wrapper.SerializeAsString();
    if (request.is_petition()) {
        // only send to the leader node:
        int id  = peerIdFromIp(current_leader_ip);                 // ←  peer‑id
        sockaddr_in dst{};
        dst.sin_family = AF_INET;
        dst.sin_port   = htons(current_leader_port);
        inet_pton(AF_INET, current_leader_ip.c_str(), &dst.sin_addr);

        sendSerialized(id, serialized_message, dst);
        LOG(INFO) << "Sent Peitition RequestVote to " << current_leader_ip << ":" << current_leader_port;
        return;
    } else {
        for (const auto& [ip, peer_port] : peer_addresses) {
            int id  = peerIdFromIp(ip);                 // ←  peer‑id
            sockaddr_in dst{};
            dst.sin_family = AF_INET;
            dst.sin_port   = htons(peer_port);
            inet_pton(AF_INET, ip.c_str(), &dst.sin_addr);
    
            // sendToPeer(id, std::move(wrapper), dst);
            sendSerialized(id, serialized_message, dst);
            LOG(INFO) << "Sent RequestVote to " << ip << ":" << peer_port;
        }
    }
}

void Node::heartbeat_cb(EV_P_ ev_timer* w, int revents) {
    // LOG(INFO) << "Heartbeat callback";
    Node* self = static_cast<Node*>(w->data);
    self->send_heartbeat();
}

void Node::recv_cb(EV_P_ ev_io* w, int revents) {
    auto [self, peerId] = *static_cast<std::pair<Node*,int>*>(w->data);
    char buf[4096]; sockaddr_in from{}; socklen_t alen = sizeof from;
    ssize_t n = recvfrom(w->fd, buf, sizeof buf, 0,
                         reinterpret_cast<sockaddr*>(&from), &alen);
    if (n <= 0) return;

    /* wrap & dispatch exactly like you did before */
    ReceivedMessage m;
    m.raw_message.assign(buf, n);
    m.sender = from;
    // if (self->check_overhead) {
    //     m.enqueue_time = std::chrono::steady_clock::now();
    // }
    // m.channel = peerId;          // ←  so workers know the source socket
    // LOG(INFO) << "Received message from " << inet_ntoa(from.sin_addr) << ":" << ntohs(from.sin_port) << " on channel " << peerId;
    self->recvQueues[peerId + 1].enqueue(std::move(m));
}


void Node::recv_client_cb(EV_P_ ev_io* w, int)
{
    auto* self = static_cast<Node*>(w->data);
    char buf[4096]; sockaddr_in from{}; socklen_t alen = sizeof from;
    ssize_t n = recvfrom(w->fd, buf, sizeof buf, 0,
                         reinterpret_cast<sockaddr*>(&from), &alen);
    if (n <= 0) return;

    ReceivedMessage m;
    m.raw_message.assign(buf, n);
    m.sender  = from;
    m.channel = -1;                                // special value for client
    // if (self->check_overhead) {
    //     m.enqueue_time = std::chrono::steady_clock::now();
    // }
    // LOG(INFO) << "Received message from client at " << inet_ntoa(from.sin_addr) << ":" << ntohs(from.sin_port);
    // client receiver at queue #0
    self->recvQueues[0].enqueue(std::move(m));
}

void Node::sendSerialized(int peerId, const std::string& bytes, const sockaddr_in& dst)
{
    auto* m      = new OutgoingMsg;
    m->bytes     = bytes;          // copy or std::move, caller’s choice
    m->use_wrapper = false;
    m->dst       = dst;
    m->fd        = ctxForPeer(peerId).fd;

    std::size_t q = (tls_worker_id >= 0) ? tls_worker_id : 0;
    // while (!outQueues_[q]->push(m)) std::this_thread::yield();
    outQueues_[q]->enqueue(m);
}

void Node::sendToPeer(int peerId, raft::leader_election::MessageWrapper&& wrapper, const sockaddr_in& dst)
{
    OutgoingMsg* m = new OutgoingMsg;
    m->wrapper = std::move(wrapper);
    m->use_wrapper = true;
    m->dst = dst;
    m->fd = ctxForPeer(peerId).fd;
    // outQueue_.enqueue(std::move(m));

    std::size_t qIdx = (tls_worker_id >= 0) ? tls_worker_id : 0;
    outQueues_[qIdx]->enqueue(m);
    // while (!outQueues_[qIdx]->push(std::move(m))) {
    //     std::this_thread::yield(); 
    // }

    // int fd = ctxForPeer(peerId).fd;
    // sendto(fd, payload.data(), payload.size(), 0,
    //     reinterpret_cast<const sockaddr*>(&dst), sizeof dst);
    // if (check_overhead) {
    //     LOG(WARNING) << "Msg Size: " << payload.size() << " bytes";
    // }
    // LOG(INFO) << "Sent message to peer " << peerId << " at " << inet_ntoa(dst.sin_addr) << ":" << ntohs(dst.sin_port) << " from FD: " << fd;
}

void Node::sendToClient(const std::string& payload, const sockaddr_in& dst)
{
    OutgoingMsg* m = new OutgoingMsg;
    m->bytes = std::move(payload);
    m->use_wrapper = false;
    m->dst = dst;
    m->fd = clientSock_;

    std::size_t qIdx = (tls_worker_id >= 0) ? tls_worker_id : 0;

    // while (!outQueues_[qIdx]->push(std::move(m))) {
    //     std::this_thread::yield(); 
    // }
    outQueues_[qIdx]->enqueue(m);
    // sendto(clientSock_, payload.data(), payload.size(), 0,
    //     reinterpret_cast<const sockaddr*>(&dst), sizeof dst);

    // if (check_overhead) {
    //     LOG(WARNING) << "Msg Size: " << payload.size() << " bytes";
    // }
    // LOG(INFO) << "Sent message to client at " << inet_ntoa(dst.sin_addr) << ":" << ntohs(dst.sin_port) << " from FD: " << clientSock_;
}

void Node::senderThreadFunc()
{
    const int kSpin  = spinCheckCount;                      // spins before sleeping
    const auto kNap  = std::chrono::microseconds{spinCheckInterval};

    OutgoingMsg* m = nullptr;
    int idle = 0;
    const std::size_t numQs = outQueues_.size();
    std::size_t nextQ = 0;

    while (!shutdownWorkers.load(std::memory_order_acquire))
    {
        bool got = false;

        // one full round‑robin pass
        for (std::size_t i = 0; i < numQs; ++i)
        {
            auto& q = *outQueues_[nextQ];
            if (q.try_dequeue(m)) {
                got    = true;
                nextQ  = (nextQ + 1) % numQs;
                break;
            }
            nextQ = (nextQ + 1) % numQs;
        }

        if (got) {
            idle = 0;
            std::string bytes;
            if (m->use_wrapper) {
                bytes = m->wrapper.SerializeAsString();
            } else {
                bytes = std::move(m->bytes);
            }
                
            // LOG(INFO) << "Sending msg to peer " << inet_ntoa(m->dst.sin_addr) << ":" << ntohs(m->dst.sin_port) << " from FD: " << m->fd;
            ::sendto(m->fd,
                     bytes.data(), bytes.size(),
                     0,
                     reinterpret_cast<const sockaddr*>(&m->dst),
                     sizeof m->dst);
            delete m;
            // LOG(WARNING) << bytes.size() << " bytes";
            continue;
        }

        // back‑off
        if (++idle < kSpin) std::this_thread::yield();
        else { std::this_thread::sleep_for(kNap); idle = 0; }
    }
}


void Node::workerThreadFunc(int wid) {
    size_t numQs = recvQueues.size();
    size_t nextQ = 0;

    tls_worker_id = wid;

    const int kSpin  = spinCheckCount;                      // spins before sleeping
    const auto kNap  = std::chrono::microseconds{spinCheckInterval};

    int idle = 0;
    
    while (!shutdownWorkers.load(std::memory_order_acquire))
    {
        ReceivedMessage rm;
        bool got = false;

        // ---------- ONE FULL ROUND‑ROBIN PASS --------------------------------
        for (size_t i = 0; i < numQs; ++i)
        {
            auto& q = recvQueues[nextQ];
            if (q.try_dequeue(rm)) {
                got    = true;
                nextQ  = (nextQ + 1) % numQs;
                break;                                  // leave the for‑loop
            }
            nextQ = (nextQ + 1) % numQs;
        }
        // --------------------------------------------------------------------

        if (got) {
            idle = 0;                                   // reset back‑off
            handleReceived(std::move(rm));
            continue;
        }

        // ---------- nothing found → back‑off ---------------------------------
        if (++idle < kSpin) {
            std::this_thread::yield();                  // short spin
        } else {
            std::this_thread::sleep_for(kNap);          // take a nap
            idle = 0;                                   // restart spin budget
        }
    }
}


void Node::handleReceived(ReceivedMessage&& rm)
{
    if (check_overhead){
        auto dequeue_time = std::chrono::steady_clock::now();
        auto queue_ms = std::chrono::duration_cast<std::chrono::microseconds>(dequeue_time - rm.enqueue_time).count();
        auto sender = rm.sender;
        LOG(WARNING) << "Received message from " << inet_ntoa(sender.sin_addr) << " Queue time: " << queue_ms << " microseconds";
    }

    raft::leader_election::MessageWrapper wrapper;
    if (!wrapper.ParseFromString(rm.raw_message)) {
        LOG(ERROR) << "Failed to parse message from sender: " << inet_ntoa(rm.sender.sin_addr) << ":" << ntohs(rm.sender.sin_port);
        return;
    }   

    switch (wrapper.type()) {
        case raft::leader_election::MessageWrapper::REQUEST_VOTE: {
            raft::leader_election::RequestVote request;
            if (!request.ParseFromString(wrapper.payload())) {
                LOG(ERROR) << "Failed to parse request vote.";
                return;
            }
            LOG(WARNING) << "Received request vote from " << request.candidate_id() << " for term " << request.term();
            handle_request_vote(request, rm.sender);
            break;
        }
        case raft::leader_election::MessageWrapper::VOTE_RESPONSE: {
            raft::leader_election::VoteResponse response;
            if (!response.ParseFromString(wrapper.payload())) {
                LOG(ERROR) << "Failed to parse vote response.";
                return;
            }
            handle_vote_response(response, rm.sender);
            break;
        }
        case raft::leader_election::MessageWrapper::APPEND_ENTRIES: {
            raft::leader_election::AppendEntries append_entries;
            if (!append_entries.ParseFromString(wrapper.payload())) {
                LOG(ERROR) << "Failed to parse append entries.";
                return;
            }
            handle_append_entries(append_entries, rm.sender);
            // LOG(INFO) << "Received append entries message.";
            break;
        }
        case raft::leader_election::MessageWrapper::PENALTY_SCORE: {
            raft::leader_election::PenaltyScore penalty_msg;
            if (!penalty_msg.ParseFromString(wrapper.payload())) {
                LOG(ERROR) << "Failed to parse PenaltyScore message.";
                return;
            }
            handle_penalty_score(penalty_msg, rm.sender);
            break;
        }
        case raft::leader_election::MessageWrapper::PETITION: {
            raft::leader_election::Petition petition_msg;
            if (!petition_msg.ParseFromString(wrapper.payload())) {
                LOG(ERROR) << "Failed to parse Petition message.";
                return;
            }
            handle_petition(petition_msg, rm.sender);
            break;
        }
        case raft::leader_election::MessageWrapper::APPEND_ENTRIES_RESPONSE: {
            raft::leader_election::AppendEntriesResponse response;
            if (!response.ParseFromString(wrapper.payload())) {
                LOG(ERROR) << "Failed to parse AppendEntriesResponse message.";
                return;
            }
            handle_append_entries_response(response, rm.sender);
            break;
        }
        case raft::leader_election::MessageWrapper::CLIENT_REQUEST: {
            raft::client::ClientRequest client_request;
            if (!client_request.ParseFromString(wrapper.payload())) {
                LOG(ERROR) << "Failed to parse ClientRequest message.";
                return;
            }
            handle_client_request(client_request, rm.sender);
            break;
        }
        default:
            LOG(ERROR) << "Unknown message type.";
    }
}

void Node::startWorkerThreads(int numWorkers) {
    for (int i = 0; i < numWorkers; i++) {
        workerThreads.emplace_back(&Node::workerThreadFunc, this, i);
    }
}

void Node::handle_request_vote(const raft::leader_election::RequestVote& request, const sockaddr_in& send_addr) {
    std::lock_guard<std::mutex> lock(state_mutex);
    int received_term = request.term();
    // this is not an id, but the candidate IP and port combination. 
    std::string candidate_id = request.candidate_id();

    if (received_term < current_term) {

        LOG(INFO) << "Received STALE request vote from " << candidate_id << " for term " << received_term << ". Current term: " << current_term;
        raft::leader_election::VoteResponse response;
        response.set_term(current_term);
        response.set_vote_granted(false);

        send_vote_response(response, send_addr);
        return;
    }

    // handle the petition version of request vote:
    if (request.is_petition()) {
        if (role == Role::LEADER) {
            LOG(INFO) << "Received petition request vote from " << candidate_id << " for term " << received_term;
    
            // Stop the heartbeat timer to simulate failure
            ev_timer_stop(loop, &heartbeat_timer);
        
            // Optionally, log the simulated failure
            LOG(INFO) << "[" << get_current_time() << "] Received petition success, Leader has stopped for term: "<< current_term ;
        
            // we also need to change the internal status to follower
            role = Role::FOLLOWER;
            current_leader_ip = "";
            current_leader_port = -1;
    
            return;
        } else {
            LOG(INFO) << "Received petition request vote from " << candidate_id << " for term " << received_term << ". But I am not leader. Current term: " << current_term;
            return;
        }
    }

    if (received_term > current_term) {
        current_term = received_term;
        if (role == Role::LEADER) {
            ev_timer_stop(loop, &heartbeat_timer);
            // isOldLeader = true;
        }
        latency_to_leader.clear();
        petition_count = 0;
        role = Role::FOLLOWER;
        voted_for = ""; 
        current_leader_ip = "";
        current_leader_port = -1;
        LOG(WARNING) << "Got newer request vote. Received request vote from " << candidate_id << " for term " << received_term << ". Current term updated to: " << current_term;
    }

    // section 5.4 of the raft paper enforces a trick that requies the leader to be up-to-date before being aboe to 
    // take the leadership role
    int last_log_index = raftLog.getLastLogIndex();
    int last_log_term = raftLog.getLastLogTerm();
    bool candidate_up_to_date = (request.last_log_term() > last_log_term) || 
                                 (request.last_log_term() == last_log_term && request.last_log_index() >= last_log_index);

    if (!candidate_up_to_date) {
        LOG(INFO) << "Candidate " << candidate_id << " is not up-to-date. Current term: " << current_term 
                  << ", Candidate last log term: " << request.last_log_term() 
                  << ", Candidate last log index: " << request.last_log_index() 
                  << ", My last log term: " << last_log_term 
                  << ", My last log index: " << last_log_index;
    }

    // a green way for petitions. Catch up later. 
    // if (request.is_petition()) {
    //     LOG(INFO) << "Received request vote petition from " << candidate_id << " for term " << received_term;
    //     candidate_up_to_date = true;
    // }

    // this is important, ensure that a node only votes once per term. 
    bool vote_granted = false;
    if ((voted_for.empty() || voted_for == candidate_id) && candidate_up_to_date) {
        vote_granted = true;
        voted_for = candidate_id;
        {
            std::lock_guard<std::mutex> lock(election_async_mutex);
            election_async_tasks.push([this]() {
                // This lambda will run in the event loop thread.
                // Cancel the old election timer and start a new one.
                reset_election_timeout(/*double_time=*/true, /*force_raft=*/false);
            });
        }
        // Notify the event loop thread:
        ev_async_send(loop, &election_async_watcher);
        // reset_election_timeout(true, false);
    }

    raft::leader_election::VoteResponse response;
    response.set_term(current_term);
    response.set_vote_granted(vote_granted);
    LOG(INFO) << "Received request vote from " << candidate_id <<  " for term: " << received_term  << ". Vote granted: " << vote_granted;
    send_vote_response(response, send_addr);
}

void Node::send_vote_response(const raft::leader_election::VoteResponse& response, const sockaddr_in& recipient) {
    raft::leader_election::MessageWrapper wrapper;
    wrapper.set_type(raft::leader_election::MessageWrapper::VOTE_RESPONSE);
    wrapper.set_payload(response.SerializeAsString());

    // std::string serialized_message = wrapper.SerializeAsString();

    std::string ip   = inet_ntoa(recipient.sin_addr);
    int         id   = peerIdFromIp(ip);

    sendToPeer(id, std::move(wrapper), recipient);    
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
    std::lock_guard<std::mutex> lock(state_mutex);
    
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
            LOG(WARNING) << "Received enough votes to become leader. Term: " << current_term << ". Votes received: " << votes_received << " out of " << peer_addresses.size();
            // role = Role::LEADER;
            // become_leader();
            // isOldLeader = false;

            // become leader directly stops the election timer in the worker thread, instead of the main thread. 
            // this can be fixed by async task 
            {
                std::lock_guard<std::mutex> lock(election_async_mutex);
                election_async_tasks.push([this]() {
                    become_leader();
                });
            }

            ev_async_send(loop, &election_async_watcher);
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

    latency_to_leader.clear();

    // stop the election timeout
    ev_timer_stop(loop, &election_timer);

    LOG(INFO) << "[" << get_current_time() << "] Became leader. Starting to send heartbeats. Elected Term: " << current_term;

    for (const auto& [ip, peer_port] : peer_addresses) {
        std::string id = ip;
        if (id != self_ip) {
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

    for (const auto& [ip, peer_port] : peer_addresses) {
        int start_index = next_index[ip];
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

        append_entries.set_leader_commit(raftLog.getCommitIndex());

        // wrap around:
        raft::leader_election::MessageWrapper wrapper;
        wrapper.set_type(raft::leader_election::MessageWrapper::APPEND_ENTRIES);
        wrapper.set_payload(append_entries.SerializeAsString());

        // std::string serialized_message = wrapper.SerializeAsString();   

        sockaddr_in peer_addr{};
        peer_addr.sin_family = AF_INET;
        peer_addr.sin_port = htons(peer_port);
        inet_pton(AF_INET, ip.c_str(), &peer_addr.sin_addr);

        // if (use_simulated_links) {
        //     send_with_delay_and_loss(serialized_message, peer_addr);
        // } else {
        sendToPeer(peerIdFromIp(ip), std::move(wrapper), peer_addr);
        // }
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

    std::lock_guard<std::mutex> lock(self->state_mutex);    

    // Stop the heartbeat timer to simulate failure
    ev_timer_stop(self->loop, &self->heartbeat_timer);

    // Optionally, log the simulated failure
    LOG(INFO) << "[" << get_current_time() << "] Leader has stopped for term: "<< self->current_term ;

    // we also need to change the internal status to follower
    self->role = Role::FOLLOWER;
    self->current_leader_ip = "";
    self->current_leader_port = -1;
    // Continue participating in other activities (e.g., receiving messages)
}

void Node::handle_append_entries(const raft::leader_election::AppendEntries& append_entries, const sockaddr_in& sender_addr) {
    int received_term = append_entries.term();
    std::string leader_id = append_entries.leader_id();
    int id = append_entries.id();   

    int match_index = 0;

    LOG(INFO) << "Received AppendEntries from " << leader_id << " for term " << received_term << " with id " << id;

    // the RPC has a smaller term number than the current one, reject on the spot. 
    if (received_term < current_term) {
        raft::leader_election::AppendEntriesResponse response;
        response.set_term(current_term);
        response.set_success(false);

        LOG(INFO) << "Received Stale AppendEntries from " << leader_id << " for term " << received_term << " while current term: " << current_term;

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
        // if (role == Role::LEADER) {
        //     LOG(INFO) << "Received heartbeat from a new leader with bigger term. Stopping heartbeat timer and resetting election timeout...";
        //     isOldLeader = true;
        // }
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
    // reset_election_timeout(); // Reset election timeout upon receiving heartbeat
    // for thread safety, should call async eventloop instead of directly resetting the 
    {
        std::lock_guard<std::mutex> lock(election_async_mutex);
        election_async_tasks.push([this]() {
            reset_election_timeout(false, false);
        });
        ev_async_send(loop, &election_async_watcher);
    }

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
        LOG(INFO) << "Prev entries do not match, sending AppendEntriesResponse with success=false";
        return;
    }

    LOG(INFO) << "Prev entries match, processing new log entries..." << append_entries.prev_log_index() << " " << append_entries.prev_log_term() << " Message Entries Count: " << append_entries.entries_size();

    // implementation in referecen to this: https://github.com/ongardie/raftscope/blob/master/raft.js
    int index = append_entries.prev_log_index();

    int prev_last_log_idx = raftLog.getLastLogIndex();

    LOG(INFO) << "Got proposal: " <<  append_entries.entries_size() << " entries, starting from index " << append_entries.prev_log_index() + 1 << " and the last log index is: " << prev_last_log_idx;

    // If an existing entry conflicts with a new one (same index but different terms), delete the existing entry and all that follow it
    {
        // std::lock_guard<std::mutex> lock(raftLog.log_mutex);
        // this is the index that we start insering, and wiping out all inconsistent entries.
        int insertion_index = append_entries.prev_log_index() + 1;
        for (int i = 0; i < append_entries.entries_size(); i++) {
            index++;
            const raft::leader_election::LogEntry& new_entry = append_entries.entries(i);
            LogEntry existingEntry;
            if (raftLog.getEntry(insertion_index, existingEntry)) {
                if (existingEntry.term != new_entry.term()) {
                    raftLog.deleteEntriesStartingFrom(insertion_index);

                    LOG(INFO) << "deleted entries from " << insertion_index << " to " << prev_last_log_idx << " due to term mismatch";
                    // raftLog.appendEntry(new_entry.term(), new_entry.command(), new_entry.client_id(), new_entry.request_id());
                    raftLog.appendEntry( makeLogEntry(new_entry.term(), new_entry.command(), new_entry.client_id(), new_entry.request_id()) );
                }
                // if matches, do nothing, and continue to the next one
            } else {
                // if the position is empty, just append the new entry
                // raftLog.appendEntry(new_entry.term(), new_entry.command(), new_entry.client_id(), new_entry.request_id());
                raftLog.appendEntry( makeLogEntry(new_entry.term(), new_entry.command(), new_entry.client_id(), new_entry.request_id()) );
            }
            // LOG(INFO) << "Appended entry at index " << index << " with term " << new_entry.term();
            insertion_index++;
        }
    }

    LOG(INFO) << "Appended entries from " << append_entries.prev_log_index() + 1 << " to " << index << ", Previous log ends at " << prev_last_log_idx
              << " and this message progressed by " << index - prev_last_log_idx << " entries";

    match_index = index;

    // if leaderCommit > commitIndex, set commitIndex = min(leaderCommit, index of last new entry)
    if (append_entries.leader_commit() > raftLog.getCommitIndex()) {
        // std::lock_guard<std::mutex> lock(raftLog.log_mutex);
        raftLog.advanceCommitIndex(std::min(append_entries.leader_commit(), raftLog.getLastLogIndex()));
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

void Node::send_append_entries_response(const raft::leader_election::AppendEntriesResponse& response, const sockaddr_in& recipient) {
    raft::leader_election::MessageWrapper wrapper;
    wrapper.set_type(raft::leader_election::MessageWrapper::APPEND_ENTRIES_RESPONSE);
    wrapper.set_payload(response.SerializeAsString());

    // std::string serialized_message = wrapper.SerializeAsString();

    sendToPeer(peerIdFromIp(inet_ntoa(recipient.sin_addr)), std::move(wrapper) , recipient);
}

void Node::start_penalty_timer() {
    LOG(WARNING) << "Starting penalty timer... tcp_monitor_freq: " << tcp_monitor_freq;
    double interval = 1.0 / tcp_monitor_freq;
    LOG(WARNING) << "Penalty timer started with interval: " << interval << " seconds";
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

    // LOG(WARNING) << "Rank Data Overhead: " << serialized_message.size() * 5 << " bytes";

    // Send the message to all peers
    for (const auto& [ip, peer_port] : peer_addresses) {
        sockaddr_in peer_addr{};
        peer_addr.sin_family = AF_INET;
        peer_addr.sin_port = htons(peer_port);
        inet_pton(AF_INET, ip.c_str(), &peer_addr.sin_addr);

        sendSerialized(peerIdFromIp(ip), serialized_message, peer_addr);
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

    sendSerialized(peerIdFromIp(proposed_leader_ip), serialized_message, peer_addr);
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
    LOG(INFO) << "Received client request: " << request.command() << " from " << inet_ntoa(sender_addr.sin_addr) << ":" << ntohs(sender_addr.sin_port);
    if (role != Role::LEADER) {
        auto client_id = request.client_id();
        auto client_request_id = request.request_id();
        raft::client::ClientResponse response;  
        response.set_success(false);    
        response.set_response("Not a leader. Leader: " + current_leader_ip + ":" + std::to_string(current_leader_port));
        response.set_client_id(client_id);
        response.set_request_id(client_request_id);
        response.set_leader_id(current_leader_ip + ":" + std::to_string(current_leader_port));
        LOG(INFO) << "Not a leader. Cannot handle client request. Telling the client that the leader is " << current_leader_ip << ":" << current_leader_port;
        send_client_response(response, sender_addr);    
        return;
    }

    if (client_id_to_addr.find(request.client_id()) == client_id_to_addr.end()) {
        client_id_to_addr[request.client_id()] = sender_addr;
        LOG(INFO) << "Added client " << request.client_id() << " to client_id_to_addr map.";
    }
        

    LOG(INFO) << "Am the leader, handling client request.";

    // append new command as a log entry
    int new_log_index = raftLog.getLastLogIndex() + 1;
    LOG(INFO) << "the new log index is " << new_log_index;
    // LogEntry new_entry { current_term, request.command(), request.client_id(), request.request_id() };
    // raftLog.appendEntry(new_entry);
    // LOG(INFO) << "Appended new entry to log-> Index: " << new_log_index << ", Term: " << new_entry.term << ", Client ID: " << new_entry.client_id << ", Command: " << new_entry.command;

    raftLog.appendEntry( makeLogEntry(current_term, request.command(), request.client_id(), request.request_id()) );
 
    // communicate with the other replicas in the system
    // first get the prev log term and prev log index, needede for append entries RPC. 
    int prev_index = new_log_index - 1;
    int prev_term = -1;
    if (prev_index > 0) {
        LogEntry prev_entry;
        raftLog.getEntry(prev_index, prev_entry);
        prev_term = prev_entry.term;
    }

    LOG(INFO) << "Prev index: " << prev_index << ", Prev term: " << prev_term;
    // TODO High Priority: Implement the request queue
    // TODO: Instead of sending off the request ASA it is received. 
    // poll from a request queue (concurrent) until it is empty

    // this function will either dispatch immeidiately, or wait for a batch to form, more flexibility. 
    // TODO: Duplication calculation of prev term and prev index. 
    LOG(INFO) << "Begin sending proposals to followers.";
    send_proposals_to_followers(current_term, raftLog.getCommitIndex());
    LOG(INFO) << "Done sending proposals to followers.";

    // raft::leader_election::AppendEntries append_entries;
    // append_entries.set_term(current_term);  
    // append_entries.set_leader_id(self_ip + ":" + std::to_string(port));
    // append_entries.set_prev_log_index(prev_index);
    // append_entries.set_prev_log_term(prev_term);

    // *append_entries.add_entries() = convertToProto(new_entry);
    // append_entries.set_leader_commit(raftLog.commitIndex);
    LOG(INFO) << "Received client request: " << request.command() << " from " << inet_ntoa(sender_addr.sin_addr) << ":" << ntohs(sender_addr.sin_port);
}

void Node::send_proposals_to_followers(int term, int commit_index)
{
    constexpr size_t kMtuBytes       = 1400;  // « real MTU minus UDP/IP/PROTO/your-own-headers
    constexpr size_t kHdrSlackBytes  = 64;    // « space for MessageWrapper + AppendEntries headers

    //--------------------------------------------------------------------
    // 1.  Snapshot the starting next_index for every follower
    //--------------------------------------------------------------------
    std::unordered_map<std::string,int> next;
    {
        std::lock_guard lk(indices_mutex);
        for (auto& [ip, port] : peer_addresses)
        {
            auto id = ip;
            if (id == self_ip) continue;   // skip self
            next[id] = next_index[id];
        }
    }

    const int last_log_idx = raftLog.getLastLogIndex();

    //--------------------------------------------------------------------
    // 2.  For every follower send log-entries in MTU-sized batches
    //--------------------------------------------------------------------
    for (auto& [follower_id, start_idx] : next)
    {
        // if (inflight_[follower_id].load(std::memory_order_acquire)) {
        //     continue;
        // }

        // --- parse follower ip / port ----------------------------------
        const std::string ip        = follower_id;
        const int         peer_port = internal_base_port + replica_id;
        if (ip == self_ip) continue;   // skip self

        // --- pre-serialize every *new* entry once ----------------------
        struct CachedEntry {
            std::string  bytes;
            int          index;
        };
        std::vector<CachedEntry> cached;
        // cached.reserve(last_log_idx - start_idx + 1);

        for (int idx = start_idx; idx <= last_log_idx && idx < 120; ++idx)
        {
            LogEntry le;
            if (!raftLog.getEntry(idx, le)) break;

            // raft::leader_election::LogEntry proto = convertToProto(le);
            CachedEntry ce;
            ce.index = idx;
            ce.bytes = le.encoded;
            cached.push_back(std::move(ce));
        }

        LOG(INFO) << "Cached " << cached.size() << " entries for follower " << follower_id
                  << " starting from index " << start_idx
                  << " to " << last_log_idx;
        //----------------------------------------------------------------
        // 3.  Stream out the cached entries respecting MTU
        //----------------------------------------------------------------

        int message_count = 0;
        size_t cursor = 0;
        while (cursor < cached.size())
        {
            if (inflight_[follower_id].load(std::memory_order_acquire)) {
                continue;
            }
            raft::leader_election::AppendEntries msg;
            msg.set_term(term);
            msg.set_leader_id(self_ip + ":" + std::to_string(this->port));
            msg.set_leader_commit(commit_index);

            // prevLogIndex / prevLogTerm are relative to *first* entry
            const int first_idx = cached[cursor].index;
            const int prev_idx  = first_idx - 1;
            int prev_term = 0;
            if (prev_idx > 0) {
                LogEntry prev;
                if (raftLog.getEntry(prev_idx, prev))
                    prev_term = prev.term;
            }
            msg.set_prev_log_index(prev_idx);
            msg.set_prev_log_term(prev_term);

            message_count++;

            // ---- fill message until adding another entry would overflow
            size_t payload_size = kHdrSlackBytes;   // message + wrapper hdrs
            LOG(INFO) << message_count << " proposals this round, msg to " << ip << " begins with " << cached[cursor].index;
            while (cursor < cached.size())
            {
                const auto& ce    = cached[cursor];
                const size_t need = ce.bytes.size();

                if (payload_size + need > kMtuBytes)       // would overflow
                    break;

                // add the pre-encoded bytes directly
                auto* e = msg.add_entries();
                e->ParseFromString(ce.bytes);              // no re-encode cost
                payload_size += need;
                ++cursor;
            }


            //----------------------------------------------------------------
            // 4.  Send this chunk
            //----------------------------------------------------------------
            raft::leader_election::MessageWrapper wrapper;
            wrapper.set_type(raft::leader_election::MessageWrapper::APPEND_ENTRIES);
            wrapper.set_payload(msg.SerializeAsString());

            sockaddr_in dst{};
            dst.sin_family = AF_INET;
            dst.sin_port   = htons(peer_port);
            inet_pton(AF_INET, ip.c_str(), &dst.sin_addr);

            // if (use_simulated_links)
            //     send_with_delay_and_loss(wrapper.SerializeAsString(), dst);
            // else
            sendToPeer(peerIdFromIp(ip), std::move(wrapper), dst);

            inflight_[follower_id].store(true, std::memory_order_release);
        }

        LOG(INFO) << "Replicated entries "
                  << start_idx << "-" << last_log_idx
                  << " to " << follower_id
                  << " in " << cached.size() << " total entries";
    }
}



void Node::send_client_response(const raft::client::ClientResponse& response, const sockaddr_in& recipient_addr) {
    std::string serialized_message = response.SerializeAsString();

    sendToClient(serialized_message, recipient_addr);
}


void Node::handle_petition(const raft::leader_election::Petition& petition_msg, const sockaddr_in& sender_addr) {
    std::string proposed_leader = petition_msg.proposed_leader();
    double reported_lat = petition_msg.latency_to_leader();
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

    //------------------------------------------------------------------
    //  Record petition only once per sender
    //------------------------------------------------------------------
    {
        std::lock_guard lg(petition_mutex);

        /*  latency_to_leader is our “who‑has‑petitioned” map.
            If we have NOT seen this sender before, record it and
            bump the unique‑petition counter.                        */
        auto [it, inserted] = latency_to_leader.emplace(sender_id, reported_lat);
        if (!inserted) {
            /* already had a petition from this sender – overwrite the
               stored latency but DO NOT double‑count the petition   */
            it->second = reported_lat;
            LOG(INFO) << "Duplicate petition from " << sender_id
                      << " ignored (latency updated).";
            return;
        }

        petition_count = static_cast<int>(latency_to_leader.size());   // unique senders
        LOG(INFO) << "Unique petitions so far: " << petition_count
                  << " (majority = "          << majority_count << ")";
    }


    if (petition_count >= majority_count-1) {
        LOG(INFO) << "Received petitions from majority for proposed leader " << proposed_leader;
        bool petition_succeed = true;

        for (const auto& [sender_id, latency] : latency_to_leader) {
            LOG(INFO) << "Latency to leader " << sender_id << ": " << latency << " ms";
            auto my_latency = get_latency_to_peer(sender_id);
            LOG(INFO) << "My latency to peer " << sender_id << ": " << my_latency << " ms";

            // TODO: Remove the 20 ms margin
            // the 20 is for testing purposes, and should be removed later.
            if (my_latency > latency) {
                petition_succeed = false;
                break;
            }
        }

        if (petition_succeed) {
            LOG(WARNING) << "Petition succeeded. Changing leader to " << proposed_leader;

            // current_term++;
            // role = Role::CANDIDATE;
            // current_leader_ip = "";  
            // current_leader_port = -1;
            // voted_for = self_ip + ":" + std::to_string(port);
            // votes_received = 0; // Vote for self later when it receives its own message

            // latency_to_leader.clear(); 

            // petition_count = 0;

            // heartbeat_current_term = 0;

            // start_election_timeout();
            // reset_election_timeout();
            send_request_vote(true);
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
        LOG(INFO) << "Received AppendEntriesResponse with a bigger term number: " << received_term << ". Reverting back to follower.";
        return;
    }

    std::string sender_ip = inet_ntoa(sender_addr.sin_addr);
    int sender_port = ntohs(sender_addr.sin_port);
    std::string sender_id = sender_ip;

    inflight_[sender_id].store(false, std::memory_order_release);   
    
    if (response.success()) {
        LOG(INFO) << "Hnadling AppendEntriesResponse from " << sender_id << " with success=true";

        std::lock_guard<std::mutex> lock(indices_mutex);

        // according to the implementation specification at: https://github.com/ongardie/raftscope/blob/master/raft.js
        int prev_next_index = next_index[sender_id];
        match_index[sender_id] = std::max(match_index[sender_id], response.match_index());
        next_index[sender_id] = match_index[sender_id] + 1;
        LOG(WARNING) << "Success AE response from " << sender_id << ". Match index: " << response.match_index() << ". Next index: " << next_index[sender_id] << " Prev next index: " << prev_next_index << " progresses by " << next_index[sender_id] - prev_next_index;
        updated_commit_index();
    } else {
        // // If conflict_index is provided, set next_index accordingly:
        // if (response.set_conflict_index()) {
        //     next_index[sender_id] = response.conflict_index();
        // } else {
            // Fallback: decrement by one (ensuring it stays at least 1)
            LOG(INFO) << "Handling AppendEntriesResponse from " << sender_id << " with success=false";

            std::lock_guard<std::mutex> lock(indices_mutex);
            next_index[sender_id] = std::max(1, next_index[sender_id] - 1);
            LOG(INFO) << "Failure AE response from " << sender_id << ". Decrementing next index to: " << next_index[sender_id];
    }
}

void Node::updated_commit_index() {
    // std::lock_guard<std::mutex> lock(raftLog.log_mutex);

    //  we should send response not just to the last committed entry, but to all the entries that are now recently committed.
    int old_commit_index = raftLog.getCommitIndex();
    int new_commit_index = raftLog.getCommitIndex();
    int last_log_index = raftLog.getLastLogIndex();
    LOG(INFO) << "Old commit index: " << old_commit_index << ", New commit index: " << new_commit_index;
    for (int i = raftLog.getCommitIndex() + 1; i <= last_log_index; i++) {
        int count = 1; // Count self

        // create a quorum vector to log the ones that agree to the commit:
        std::vector<std::string> quorum;
        quorum.push_back(self_ip);
        for (const auto& [ip, peer_port] : peer_addresses) {
            std::string id = ip;
            if (match_index[id] >= i) {
                count++;
                quorum.push_back(id);
            }
        }
        if (count >= majority_count) {
            LogEntry entry;
            if (raftLog.getEntry(i, entry) && entry.term == current_term) {
                new_commit_index = i;

                // get the time of this commit
                auto now = std::chrono::system_clock::now();
                auto in_time_t = std::chrono::system_clock::to_time_t(now);
                auto micros = std::chrono::duration_cast<std::chrono::microseconds>(
                    now.time_since_epoch()
                ) % 1000000;
    
                std::ostringstream ts;
                ts << std::put_time(std::localtime(&in_time_t), "%Y-%m-%d %H:%M:%S")
                   << "." << std::setfill('0') << std::setw(6) << micros.count();

                LOG(WARNING) << "Commit for: " << entry.command << " at " << ts.str() << " with quorum size: " << quorum.size() << " " << quorum[0] << " " << quorum[1] << " " << quorum[2] << " " ;
            }
        }
    }

    if (new_commit_index != raftLog.getCommitIndex()) {
        raftLog.advanceCommitIndex(new_commit_index);
        LOG(INFO) << "Advanced commit index to: " << new_commit_index;
        // Optionally, trigger applying the newly committed entries to the state machine.
        // apply_committed_entries();

        for (int idx = old_commit_index + 1; idx <= new_commit_index; idx++) 
        {
            LogEntry entry;
            if (raftLog.getEntry(idx, entry)) {
    
                auto client_address = client_id_to_addr.find(entry.client_id);
    
                if (client_address != client_id_to_addr.end()) {
                    raft::client::ClientResponse response;
                    response.set_success(true);
                    response.set_response("1");
                    response.set_client_id(entry.client_id);
                    response.set_request_id(entry.request_id);
                    send_client_response(response, client_address->second);
                }
            }
        }
    }
}

void Node::dumpRaftLogToFile(const std::string& file_path) {
    std::ofstream ofs(file_path, std::ios::out);
    if (!ofs.is_open()) {
        LOG(ERROR) << "Failed to open file " << file_path << " for writing raft log.";
        return;
    }
    
    // Write header information.
    ofs << "Raft Log Dump for Node " << self_ip << ":" << port << "\n";
    ofs << "Current term: " << current_term << "\n";
    int lastIndex = raftLog.getLastLogIndex();
    ofs << "Last log index: " << lastIndex << "\n";
    ofs << "----------------------------------------\n";

    // Iterate over the log entries (assuming log indices start at 1).
    for (int i = 1; i <= lastIndex; i++) {
        LogEntry entry;
        if (raftLog.getEntry(i, entry)) {
            ofs << "Index: " << i 
                << ", Term: " << entry.term
                << ", Command: " << entry.command
                << ", Client ID: " << entry.client_id
                << ", Request ID: " << entry.request_id << "\n";
        }
    }
    ofs.close();
    LOG(INFO) << "Raft log dumped to file: " << file_path;
}