#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>
#include <fcntl.h>
#include <ev.h>
#include <glog/logging.h>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <sstream>
#include <string>
#include "proto/raft_client.pb.h"
#include "proto/raft_leader_election.pb.h"
#include <iomanip>
#include <thread>


// Sending modes
enum SendMode {
    FIXED_RATE = 1,
    MAX_IN_FLIGHT = 2
};

class Client {
public:
    Client(const std::string& server_ip, int server_port, SendMode mode,
           double fixed_interval_sec, int maxInFlight, int client_id, std::string bind_ip);

    ~Client();

    // Run the event loop.
    void run();

private:
    int sock_fd_;
    struct ev_loop* loop_;
    ev_io recv_watcher_;
    ev_timer send_timer_;

    std::string server_ip_;
    std::string bind_ip_;
    int server_port_;
    sockaddr_in server_addr_;

    SendMode mode_;
    double fixed_interval_; // used in fixed-rate mode
    int max_in_flight_;     // used in max-in-flight mode
    int in_flight_;         // current count of in-flight requests

    int client_id_;
    int request_id_;

    std::unordered_map<int, std::chrono::steady_clock::time_point> request_times_;

    bool known_leader_ = true; // Flag to indicate if we know the leader

    ev_timer timeout_timer_;

    double timeout_interval_;

    // Send a client request (one UDP message).
    void send_request();

    // Timer callback for sending requests.
    static void send_timer_cb(struct ev_loop* loop, ev_timer* w, int revents);

    // I/O callback for receiving responses.
    static void recv_cb(struct ev_loop* loop, ev_io* w, int revents);

    static void timeout_cb(struct ev_loop* loop, ev_timer* w, int revents);

    // Handle an incoming ClientResponse.
    void handle_response(const std::string& response_data, sockaddr_in& from_addr);
};


