#include "raftLog.h"

RaftLog::RaftLog() : commitIndex(0), lastApplied(0) {}

RaftLog::~RaftLog() {}

void RaftLog::appendEntry(const LogEntry& entry) {
    std::lock_guard<std::mutex> lock(log_mutex);
    log.push_back(entry);
}

// index starts at 1
int RaftLog::getLastLogIndex() {
    std::lock_guard<std::mutex> lock(log_mutex);
    return log.empty() ? 0 : log.size();
} 

int RaftLog::getLastLogTerm() {
    std::lock_guard<std::mutex> lock(log_mutex);
    return log.empty() ? 0 : log.back().term;
}

bool RaftLog::getEntry(int index, LogEntry& entry) {
    std::lock_guard<std::mutex> lock(log_mutex);
    if (index <= 0 || index > static_cast<int>(log.size())) {
        return false;
    }

    entry = log[index - 1];
    return true;
}

bool RaftLog::containsEntry(int index, int term) {
    std::lock_guard<std::mutex> lock(log_mutex);
    if (index == 0) {
        return true;
    }
    if (index < 0 || index > static_cast<int>(log.size())) {
        return false;
    }

    return log[index - 1].term == term;
}


void RaftLog::deleteEntriesStartingFrom(int index) {
    std::lock_guard<std::mutex> lock(log_mutex);
    if (index <= 0 || index > static_cast<int>(log.size())) {
        return;
    }

    log.erase(log.begin() + index - 1, log.end());
}