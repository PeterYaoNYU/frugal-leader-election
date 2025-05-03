#include <vector>
#include <mutex>
#include <algorithm>
#include <string>
#include <glog/logging.h>
#include <shared_mutex>

struct LogEntry {
    int term;
    std::string command;
    int client_id;
    int request_id;
    // to avoid protobuf overhead, we use a string to store the encoded message.
    std::string encoded;
};

class RaftLog {
public:
    RaftLog();
    ~RaftLog();

    void appendEntry(const LogEntry& entry);
    void appendEntry(int term, const std::string& command, int client_id, int request_id);
    int getLastLogIndex();
    int getLastLogTerm();
    bool getEntry(int index, LogEntry& entry);
    // Check whether the log contains an entry at index with the specified term.
    bool containsEntry(int index, int term);
    // Delete all entries starting from index
    void deleteEntriesStartingFrom(int index);

    // int getCommitIndex();
    // int getLastApplied();
    // void setCommitIndex(int index);
    // void setLastApplied(int index);

    std::atomic<int>                        commitIndex{0};
    std::atomic<int>                        lastApplied{0};
    // std::mutex log_mutex;
    mutable std::shared_mutex log_mutex; // Use shared mutex for read/write access

    int  getCommitIndex()   { return commitIndex.load(std::memory_order_acquire); }
    int  getLastApplied()   { return lastApplied.load(std::memory_order_acquire); }

    /* writers for the atomics */
    void advanceCommitIndex(int idx) noexcept {
        commitIndex.store(idx, std::memory_order_release);
    }
    void advanceLastApplied(int idx) noexcept {
        lastApplied.store(idx, std::memory_order_release);
    }


private:
    std::vector<LogEntry> log;
};