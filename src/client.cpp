#include "client.h"

Client::Client(const std::string& server_ip, int server_port, SendMode mode,
        double fixed_interval_sec, int maxInFlight, int client_id)
    : server_ip_(server_ip),
        server_port_(server_port),
        mode_(mode),
        fixed_interval_(fixed_interval_sec),
        max_in_flight_(maxInFlight),
        in_flight_(0),
        client_id_(client_id),
        request_id_(1)
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

    // Optionally, bind to any local address.
    sockaddr_in local_addr{};
    local_addr.sin_family = AF_INET;
    local_addr.sin_port = htons(0); // let the OS choose a free port
    local_addr.sin_addr.s_addr = INADDR_ANY;
    if (bind(sock_fd_, (sockaddr*)&local_addr, sizeof(local_addr)) < 0) {
        LOG(FATAL) << "Failed to bind local socket.";
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
    } else if (mode_ == MAX_IN_FLIGHT) {
        // In MAX_IN_FLIGHT mode, we use a very short timer to try sending new requests.
        ev_timer_init(&send_timer_, send_timer_cb, 0.0, 0.002); // every 10ms
        send_timer_.data = this;
        ev_timer_start(loop_, &send_timer_);
    }
}

Client::~Client() {
    close(sock_fd_);
}

void Client::run() {
    LOG(INFO) << "Client starting event loop.";
    ev_run(loop_, 0);
    LOG(INFO) << "Client event loop stopped.";
}

void Client::send_request() {
    // Construct the ClientRequest message.
    raft::client::ClientRequest request;
    request.set_command(""); // command left empty for now
    request.set_client_id(client_id_);
    request.set_request_id(request_id_++);

    std::string serialized_request;
    if (!request.SerializeToString(&serialized_request)) {
        LOG(ERROR) << "Failed to serialize ClientRequest.";
        return;
    }

    ssize_t sent = sendto(sock_fd_, serialized_request.c_str(), serialized_request.size(), 0,
                            (sockaddr*)&server_addr_, sizeof(server_addr_));
    if (sent < 0) {
        LOG(ERROR) << "sendto() failed while sending request id " << request.request_id();
    } else {
        LOG(INFO) << "Sent ClientRequest id " << request.request_id() - 1
                    << " to " << server_ip_ << ":" << server_port_ 
                    << " (in-flight: " << in_flight_ + 1 << ")";
        if (mode_ == MAX_IN_FLIGHT) {
            in_flight_++;
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
    std::string serialized_response(buffer, nread);
    client->handle_response(serialized_response);
}

// Handle an incoming ClientResponse.
void Client::handle_response(const std::string& response_data) {
    raft::client::ClientResponse response;
    if (!response.ParseFromString(response_data)) {
        LOG(ERROR) << "Failed to parse ClientResponse.";
        return;
    }
    LOG(INFO) << "Received ClientResponse: success=" << response.success()
                << ", response=\"" << response.response() << "\""
                << ", client_id=" << response.client_id()
                << ", request_id=" << response.request_id();

    // In MAX_IN_FLIGHT mode, decrement the count on each response.
    if (mode_ == MAX_IN_FLIGHT && in_flight_ > 0) {
        in_flight_--;
        LOG(INFO) << "In-flight requests decremented to " << in_flight_;
    }
}
