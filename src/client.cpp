#include "client.h"

Client::Client(const std::string& server_ip, int server_port, SendMode mode,
        double fixed_interval_sec, int maxInFlight, int client_id, std::string bind_ip)
    : server_ip_(server_ip),
        server_port_(server_port),
        mode_(mode),
        fixed_interval_(fixed_interval_sec),
        max_in_flight_(maxInFlight),
        in_flight_(0),
        client_id_(client_id),
        request_id_(1), 
        timeout_interval_(3.0), 
        bind_ip_(bind_ip) 
{
    // Create the default event loop.
    loop_ = ev_default_loop(0);
    // Create UDP socket.
    sock_fd_ = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock_fd_ < 0) {
        LOG(FATAL) << "Failed to create UDP socket.";
    }
    // Set non-blocking.
    int flags = fcntl(sock_fd_, F_GETFL, 0);
    fcntl(sock_fd_, F_SETFL, flags | O_NONBLOCK);

    // Set up the server address.
    memset(&server_addr_, 0, sizeof(server_addr_));
    server_addr_.sin_family = AF_INET;
    server_addr_.sin_port = htons(server_port_);
    if (inet_pton(AF_INET, server_ip_.c_str(), &server_addr_.sin_addr) <= 0) {
        LOG(FATAL) << "Invalid server IP: " << server_ip_;
    }

    sockaddr_in local_addr{};
    local_addr.sin_family = AF_INET;
    local_addr.sin_port = htons(0); // let the OS choose a free port
    if (inet_pton(AF_INET, bind_ip_.c_str(), &local_addr.sin_addr) <= 0) {
        LOG(FATAL) << "Invalid local IP address: " << server_ip_;
    }
    if (bind(sock_fd_, (sockaddr*)&local_addr, sizeof(local_addr)) < 0) {
        LOG(FATAL) << "Failed to bind local socket to " << server_ip_;
    }

    // Initialize the libev watchers.
    ev_io_init(&recv_watcher_, recv_cb, sock_fd_, EV_READ);
    recv_watcher_.data = this;
    ev_io_start(loop_, &recv_watcher_);

    // In FIXED_RATE mode, set up a timer.
    if (mode_ == FIXED_RATE) {
        ev_timer_init(&send_timer_, send_timer_cb, fixed_interval_, fixed_interval_);
        send_timer_.data = this;
        ev_timer_start(loop_, &send_timer_);
    }
    
    // for MAX_IN_FLIGHT mode, we don't start the timer here. Send off the initial batch immediately.  
    
    // else if (mode_ == MAX_IN_FLIGHT) {
    //     // In MAX_IN_FLIGHT mode, we use a very short timer to try sending new requests.
    //     ev_timer_init(&send_timer_, send_timer_cb, 0.0, 0.002); // every 10ms
    //     send_timer_.data = this;
    //     ev_timer_start(loop_, &send_timer_);
    // }

    if (mode_ == MAX_IN_FLIGHT) {
        // You may choose a short periodic interval (e.g., check every second) or use the timeout interval.
        ev_timer_init(&timeout_timer_, timeout_cb , timeout_interval_, timeout_interval_);
        timeout_timer_.data = this;
        ev_timer_start(loop_, &timeout_timer_);
    }
}

Client::~Client() {
    close(sock_fd_);
}

void Client::run() {
    LOG(INFO) << "Client starting event loop.";

    send_request();
    sleep(1);

    // send of the initial batch of requests altogether. 
    if (mode_ == MAX_IN_FLIGHT) {
        for (int i = 0; i < max_in_flight_ - 1; i++) {
            send_request();
            // in_flight_++;
        }
    }

    ev_run(loop_, 0);
    LOG(INFO) << "Client event loop stopped.";
}

void Client::send_request() {
    // Construct the ClientRequest message.
    raft::client::ClientRequest request;
    request.set_command(std::to_string(request_id_) + " " + std::to_string(client_id_));
    request.set_client_id(client_id_);
    request.set_request_id(request_id_++);

    std::string serialized_request;
    if (!request.SerializeToString(&serialized_request)) {
        LOG(ERROR) << "Failed to serialize ClientRequest.";
        return;
    }

    raft::leader_election::MessageWrapper wrapper;
    wrapper.set_type(raft::leader_election::MessageWrapper::CLIENT_REQUEST);
    wrapper.set_payload(serialized_request);

    serialized_request = wrapper.SerializeAsString();

    request_times_[request.request_id()] = std::chrono::steady_clock::now();

    ssize_t sent = sendto(sock_fd_, serialized_request.c_str(), serialized_request.size(), 0,
                            (sockaddr*)&server_addr_, sizeof(server_addr_));
    if (sent < 0) {
        LOG(ERROR) << "sendto() failed while sending request id " << request.request_id() << "to IP: " << server_ip_ << ":" << server_port_;
    } else {
        LOG(INFO) << "Sent ClientRequest id " << request.request_id() - 1
                    << " to " << server_ip_ << ":" << server_port_ 
                    << " (in-flight: " << in_flight_ + 1 << ")";
        if (mode_ == MAX_IN_FLIGHT) {
            in_flight_++;
        }

        // cancel the previous timeout timer, and start a new one.
        if (mode_ == MAX_IN_FLIGHT) {
            ev_timer_stop(loop_, &timeout_timer_);
            ev_timer_init(&timeout_timer_, timeout_cb, timeout_interval_, timeout_interval_);
            ev_timer_start(loop_, &timeout_timer_);
        }
    }
}

void Client::send_timer_cb(struct ev_loop* loop, ev_timer* w, int revents) {
    Client* client = static_cast<Client*>(w->data);
    if (client->mode_ == FIXED_RATE) {
        // In fixed rate mode, send one request per timer callback.
        client->send_request();
    } else if (client->mode_ == MAX_IN_FLIGHT) {
        // In max-in-flight mode, send as many requests as possible (non-blocking)
        // until we hit the cap.
        while (client->in_flight_ < client->max_in_flight_) {
            client->send_request();
        }
    }
}

void Client::timeout_cb(struct ev_loop* loop, ev_timer* w, int revents) {
    Client* client = static_cast<Client*>(w->data);
    if (client->in_flight_ > 0) {
        LOG(INFO) << "Timeout occurred. In-flight requests: " << client->in_flight_;
        // clear the in-flight requests
        client->in_flight_ = 0;
        // send a new request
        for (int i = 0; i < client->max_in_flight_; i++) {
            client->send_request();
        }
    }
}

void Client::recv_cb(struct ev_loop* loop, ev_io* w, int revents) {
    Client* client = static_cast<Client*>(w->data);
    char buffer[4096];
    sockaddr_in from_addr{};
    socklen_t addr_len = sizeof(from_addr);
    ssize_t nread = recvfrom(client->sock_fd_, buffer, sizeof(buffer), 0,
                                (sockaddr*)&from_addr, &addr_len);
    if (nread < 0) {
        LOG(ERROR) << "recvfrom() error.";
        return;
    }
    // LOG(INFO) << "Got a response from: " << inet_ntoa(from_addr.sin_addr) << ":" << ntohs(from_addr.sin_port);
    std::string serialized_response(buffer, nread);
    client->handle_response(serialized_response, from_addr);
}

// Handle an incoming ClientResponse.
void Client::handle_response(const std::string& response_data,  sockaddr_in& from_addr) {
    raft::client::ClientResponse response;
    if (!response.ParseFromString(response_data)) {
        LOG(ERROR) << "Failed to parse ClientResponse.";
        return;
    }

    if (response.success()) {
        if (!known_leader_) {
            known_leader_ = true; // Set flag to indicate we know the leader
            LOG(INFO) << "Begin of Leadership under: " << server_ip_;
        }
    }

    if (!response.success()) {
        // if unsuccessful, change the leader to the one in the response
        std::string leader_id = response.leader_id();
        size_t colon_pos = leader_id.find(':');
        if (colon_pos != std::string::npos) {
            std::string leader_ip = leader_id.substr(0, colon_pos);
            if (leader_ip.empty()) {
                LOG(WARNING) << "Empty leader IP in leader_id: " << leader_id;
                if (mode_ == MAX_IN_FLIGHT) {
                    in_flight_ = 0;
                    LOG(INFO) << "In-flight requests reset to 0.";
                }
                std::this_thread::sleep_for(std::chrono::milliseconds(20));
                send_request();
                return;
            }

            if (inet_pton(AF_INET, leader_ip.c_str(), &server_addr_.sin_addr) <= 0) {
                LOG(ERROR) << "Invalid leader IP: " << leader_ip;
            } else {
                if (server_ip_ == leader_ip) {
                    LOG(INFO) << "Already connected to the leader: " << leader_ip;
                    return;
                } else {
                    LOG(INFO) << "Changing leader from " << server_ip_ << " to " << leader_ip;
                }
                known_leader_ = false; // Set flag to indicate we don't know the leader
                // If we are in MAX_IN_FLIGHT mode, we need to reset the in-flight count.
                if (mode_ == MAX_IN_FLIGHT) {
                    in_flight_ = 0;
                    LOG(INFO)   << "In-flight requests reset to 0.";
                }

                LOG(INFO) << "End of Leadership under: " << server_ip_;

                server_ip_ = leader_ip;
                int leader_port = std::stoi(leader_id.substr(colon_pos + 1));
                server_port_ = leader_port;
                // Update server address with new leader details.
                server_addr_.sin_family = AF_INET;
                server_addr_.sin_port = htons(leader_port);
                LOG(INFO) << "Updated leader to " << leader_ip << ":" << leader_port;

                if (mode_ == MAX_IN_FLIGHT) {
                    send_request();
                    sleep(1);
                    while (in_flight_ < max_in_flight_) {
                        send_request();
                        sleep(0.5);
                    }
                }

            }
        } else {
            LOG(ERROR) << "Invalid leader_id format: " << leader_id;
        }
    }

    // Compute response time if we have a recorded submission time.
    auto it = request_times_.find(response.request_id());
    std::ostringstream oss;
    if (it != request_times_.end()) {
        auto now = std::chrono::steady_clock::now();
        double duration_ms = std::chrono::duration_cast<std::chrono::duration<double, std::milli>>(now - it->second).count();
        oss << std::fixed << std::setprecision(3) << duration_ms;
        // LOG(INFO) << "Response time for request id " << response.request_id() << " is " << oss.str() << " ms.";        
        request_times_.erase(it);
    } else {
        LOG(WARNING) << "No recorded request time for request id " << response.request_id();
    }
    
    LOG(INFO) << "Received ClientResponse: latency= " << oss.str() << ", success=" << response.success()
                << ", from=" << inet_ntoa(from_addr.sin_addr)
                << ", response=\"" << response.response() << "\""
                << ", client_id=" << response.client_id()
                << ", request_id=" << response.request_id()
                << ", leader_id=" << response.leader_id();

    // In MAX_IN_FLIGHT mode, decrement the count on each response.
    if (mode_ == MAX_IN_FLIGHT) {
        // Decrement the counter since a response has been received.
        if (in_flight_ > 0)
            in_flight_--;
        LOG(INFO) << "In-flight requests decremented to " << in_flight_;
        // Immediately send a new request if we are below the limit.
        while (in_flight_ < max_in_flight_) {
            send_request();
        }
    }
}
