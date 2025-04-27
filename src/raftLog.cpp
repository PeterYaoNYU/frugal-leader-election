#include "raftLog.h"

RaftLog::RaftLog() : commitIndex(0), lastApplied(0) {}

RaftLog::~RaftLog() {}

void RaftLog::appendEntry(const LogEntry& entry) {
    std::unique_lock lock(log_mutex);
    log.push_back(entry);
}

void RaftLog::appendEntry(int term, const std::string& command, int client_id, int request_id) {
    std::unique_lock lock(log_mutex);
    log.push_back({term, command, client_id, request_id});
}

// index starts at 1
int RaftLog::getLastLogIndex() {
    std::shared_lock lock(log_mutex);
    return log.empty() ? 0 : log.size();
} 

int RaftLog::getLastLogTerm() {
    std::shared_lock lock(log_mutex);
    return log.empty() ? 0 : log.back().term;
}

bool RaftLog::getEntry(int index, LogEntry& entry) {
    std::shared_lock lock(log_mutex);
    if (index <= 0 || index > static_cast<int>(log.size())) {
        return false;
    }

    entry = log[index - 1];
    return true;
}


bool RaftLog::getEntry(int index, LogEntry& entry, bool set_response_sent) {
    std::shared_lock lock(log_mutex);
    if (index <= 0 || index > static_cast<int>(log.size())) {
        return false;
    }

    entry = log[index - 1];
    bool response_sent = entry.response_sent;
    entry.response_sent = set_response_sent;

    return response_sent;
}

bool RaftLog::containsEntry(int index, int term) {
    std::shared_lock lock(log_mutex);
    if (index == 0) {
        return true;
    }
    if (index < 0 || index > static_cast<int>(log.size())) {
        return false;
    }

    return log[index - 1].term == term;
}


void RaftLog::deleteEntriesStartingFrom(int index) {
    std::unique_lock lock(log_mutex);
    if (index <= 0 || index > static_cast<int>(log.size())) {
        return;
    }

    log.erase(log.begin() + index - 1, log.end());
}