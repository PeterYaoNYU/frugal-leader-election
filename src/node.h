#ifndef NODE_H
#define NODE_H

#include <ev.h>
#include <glog/logging.h>
#include <netinet/in.h>
#include <unistd.h>
#include <fcntl.h>
#include <string>
#include <vector>
#include <random>
#include <unordered_map>
#include "process_config.h"
class Node {
public:
    Node(int port, const std::string& peers);
    Node(const ProcessConfig& config, int replicaId);
    void run();

private:
    struct ev_loop* loop;
    ev_timer election_timer;
    ev_timer heartbeat_timer;
    ev_io recv_watcher;
    int sock_fd;

    std::string self_ip;

    int port;
    std::vector<std::pair<std::string, int>> peer_addresses;
    std::mt19937 rng;
    std::uniform_int_distribution<std::mt19937::result_type> dist;

    void start_election_timeout();
    void reset_election_timeout();
    static void election_timeout_cb(EV_P_ ev_timer* w, int revents);
    static void heartbeat_cb(EV_P_ ev_timer* w, int revents);

    static void recv_cb(EV_P_ ev_io* w, int revents);

    void become_leader();
    void send_heartbeat();
};

#endif // NODE_H
