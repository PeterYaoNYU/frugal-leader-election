#ifndef NODE_H
#define NODE_H

#include <ev.h>
#include <glog/logging.h>
#include <netinet/in.h>
#include <unistd.h>
#include <fcntl.h>
#include <string>
#include <vector>

#include <arpa/inet.h>
#include <sys/socket.h>

#include <fstream>
#include <chrono>
#include <iomanip>

// using a thread pool to get the socket statistics. 
#include <queue>               // CHANGED: For task queue
#include <condition_variable>  // CHANGED: For synchronization
#include <atomic>              // CHANGED: For thread-safe flags

#include <random>
#include <unordered_map>

#include <thread>

#include "process_config.h"
#include "proto/raft_leader_election.pb.h"
#include "proto/raft_client.pb.h"
#include "lib/utils.h"

#include "lib/tcp_stat_manager.h"

#include "lib/net_latency_controller.h"

#include "raftLog.h"

#include "concurrentqueue.h"

// Helper: Convert our in-memory log entry to the proto LogEntry.
inline raft::leader_election::LogEntry convertToProto(const LogEntry& entry) {
    raft::leader_election::LogEntry protoEntry;
    protoEntry.set_term(entry.term);
    protoEntry.set_command(entry.command);
    return protoEntry;
}

// a simple struct to hold raw messages, and sender information. 
struct ReceivedMessage {
    // the raw messages have not been parsed by protobuf. 
    std::string raw_message;
    sockaddr_in sender;
};

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
    std::uniform_real_distribution<double> election_dist;

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

    // debugging
    int heartbeat_current_term = 0;

    // timeout variation
    int self_id;
    std::unordered_map<std::string, int> ip_to_id;

    enum bound_type {CI, Jacobson, raft} election_timeout_bound = raft;

    // New timer for penalty score exchange
    ev_timer penalty_timer;

    // Data structure to store penalty scores received from other nodes
    std::unordered_map<std::string, double> penalty_scores; // Key: node_id, Value: penalty_score

    // Data structures for petition handling
    int petition_count = 0; // Count of petitions received  
    // std::unordered_map<std::string, int> petition_count; // Key: proposed_leader_id, Value: count of petitions received
    // also for petition purposes   
    std::unordered_map<std::string, double> latency_to_leader; // Key: peer_id, Value: latency in millisecon`
    std::mutex petition_mutex; // To protect access to petition_count

    // Thresholds and configurations
    double latency_threshold = 75.0; // Threshold in milliseconds
    int majority_count; // Number of nodes required for majority

    std::string network_interface;

    NetLatencyController net_latency_controller;

    int safety_margin_lower_bound;
    int safety_margin_step_size;

    RaftLog raftLog;

    std::unordered_map<std::string, int> next_index;
    std::unordered_map<std::string, int> match_index;

    std::unordered_map<int, sockaddr_in> client_id_to_addr;

    moodycamel::ConcurrentQueue<ReceivedMessage> workerQueue;
    std::vector<std::thread> workerThreads;
    std::atomic<bool> shutdownWorkers {false};
    // for protecting Variables like current_term, voted_for, votes_received, role, heartbeat_count, heartbeat_current_term, current_leader_ip, and current_leader_port
    std::mutex state_mutex;
    // for protecting next_index and match_index
    std::mutex indices_mutex;
    // for protecting the map that stores client addresses. 
    std::mutex client_map_mutex;

    // for multithreading safety,init an async watcher that exclusively handles 
    // election related timeouts and potentially other timeouts.

    ev_async election_async_watcher;
    std::mutex election_async_mutex;
    // holds functions that return void and has no argument list.
    std::queue<std::function<void()>> election_async_tasks;

    // async signal callback function:
    static void election_async_cb(EV_P_ ev_async* w, int revents);

    void process_election_async_task();

    void start_election_timeout(bool double_time=false, bool force_raft=false);
    void reset_election_timeout(bool double_time=false, bool force_raft=false);
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

    // a set of penalty related functions. 
    void start_penalty_timer();
    static void penalty_timer_cb(EV_P_ ev_timer* w, int revents);
    void calculate_and_send_penalty_score();
    double compute_penalty_score();
    double get_latency_to_peer(const std::string& peer_id);
    void handle_penalty_score(const raft::leader_election::PenaltyScore& penalty_msg, const sockaddr_in& sender_addr);

    // Methods for petition handling
    void send_petition(const std::string& proposed_leader, double latency_to_leader);
    void handle_petition(const raft::leader_election::Petition& petition_msg, const sockaddr_in& sender_addr);
    void check_and_initiate_leader_election(const std::string& proposed_leader, double proposed_latency);


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

    // Only for the leader: handle the client requests, update the followers, 
    void handle_client_request(const raft::client::ClientRequest& request, const sockaddr_in& sender_addr);
    void handle_append_entries_response(const raft::leader_election::AppendEntriesResponse& response, const sockaddr_in& sender_addr);

    void send_client_response(const raft::client::ClientResponse& response, const sockaddr_in& recipient_addr);
    void send_proposals_to_followers(int current_term, int commit_index);

    // check quorum and forward commit idx, for the leader's use.
    void updated_commit_index();

    void dumpRaftLogToFile(const std::string& file_path);

    void startWorkerThreads(int numWorkers);

    void workerThreadFunc();
};



struct DelayData {
    Node* self;
    std::string message;
    sockaddr_in recipient_addr;
};

#endif // NODE_H
