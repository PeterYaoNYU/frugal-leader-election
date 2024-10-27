#ifndef NODE_H
#define NODE_H

#include <ev.h>
#include <glog/logging.h>
#include <netinet/in.h>
#include <unistd.h>
#include <fcntl.h>
#include <string>
#include <vector>

// using a thread pool to get the socket statistics. 
#include <queue>               // CHANGED: For task queue
#include <condition_variable>  // CHANGED: For synchronization
#include <atomic>              // CHANGED: For thread-safe flags

#include <random>
#include <unordered_map>
#include "process_config.h"
#include "proto/raft_leader_election.pb.h"
#include "lib/utils.h"

#include "lib/tcp_stat_manager.h"
class Node {
public:
    // Node(int port, const std::string& peers);
    Node(const ProcessConfig& config, int replicaId);
    void run();

private:
    void send_with_delay_and_loss(const std::string& message, const sockaddr_in& recipient_addr);
    static void delay_cb(EV_P_ ev_timer* w, int revents);

    struct ev_loop* loop;
    ev_timer election_timer;
    ev_timer heartbeat_timer;
    ev_timer failure_timer;
    ev_io recv_watcher;
    int sock_fd;

    std::string self_ip;

    // the total amount of time the process should run
    int runtime_seconds;
    ev_timer shutdown_timer;

    int port;
    std::vector<std::pair<std::string, int>> peer_addresses;
    std::mt19937 rng;
    std::uniform_int_distribution<std::mt19937::result_type> dist;


    bool failure_leader = false;

    std::string current_leader_ip;
    int current_leader_port;
    int view_number = 0;
    int current_term;
    std::string voted_for; //  Candidate ID (IP:port) this node voted for in current term
    int votes_received; // Number of votes received in current term
    int max_heartbeats; // Number of heartbeats to send before stopping, if the leader will fail in experiments
    int heartbeat_count; // Number of heartbeats sent so far (for the leader only_)

    // network simulation
    bool use_simulated_links;
    // for now, we use uniform distribution, to be changed later to poisson. 
    std::uniform_real_distribution<double> loss_dist;
    std::uniform_real_distribution<double> delay_dist;
    enum Role {FOLLOWER, CANDIDATE, LEADER} role;    

    double link_loss_rate;

    // extract network layer information
    TcpStatManager tcp_stat_manager;

    // if we are in a check false positive mode or not
    bool check_false_positive;  

    // a number for check false positive mode
    int suspected_leader_failures = 0;
    int recv_heartbeat_count = 0;

    bool tcp_monitor;

    double confidence_level = 0.999;
    int heartbeat_interval_margin = 75; // 75 ms

    void start_election_timeout();
    void reset_election_timeout();
    static void election_timeout_cb(EV_P_ ev_timer* w, int revents);
    static void heartbeat_cb(EV_P_ ev_timer* w, int revents);

    static void shutdown_cb(EV_P_ ev_timer* w, int revents);

    static void recv_cb(EV_P_ ev_io* w, int revents);

    // for the leader, call back after it is time to fail. 
    static void failure_cb(EV_P_ ev_timer* w, int revents);

    void send_request_vote();
    void send_vote_response(const raft::leader_election::VoteResponse& response, const sockaddr_in& addr);
    void send_append_entries_response(const raft::leader_election::AppendEntriesResponse& response, const sockaddr_in& recipient_addr);

    void handle_request_vote(const raft::leader_election::RequestVote& request, const sockaddr_in& sender_addr);
    void handle_vote_response(const raft::leader_election::VoteResponse& response, const sockaddr_in& sender_addr);

    void handle_append_entries(const raft::leader_election::AppendEntries& append_entries, const sockaddr_in& sender_addr); 

    void become_leader();
    void send_heartbeat();

    void startMonitoringTraffic() {
        tcp_stat_manager.startMonitoring();
    }

    void stopMonitoringTraffic() {
        tcp_stat_manager.stopMonitoring();
    }

    void displayTrafficStats() {
        tcp_stat_manager.printStats();
    }
};



struct DelayData {
    Node* self;
    std::string message;
    sockaddr_in recipient_addr;
};

#endif // NODE_H
