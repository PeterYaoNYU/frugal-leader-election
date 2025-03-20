#include <vector>
#include <mutex>
#include <algorithm>
#include <string>

struct LogEntry {
    int term;
    std::string command;
};

class RaftLog {
public:
    RaftLog();
    ~RaftLog();

    void appendEntry(const LogEntry& entry);
    void appendEntry(int term, const std::string& command);
    int getLastLogIndex();
    int getLastLogTerm();
    bool getEntry(int index, LogEntry& entry);
    // Check whether the log contains an entry at index with the specified term.
    bool containsEntry(int index, int term);
    // Delete all entries starting from index
    void deleteEntriesStartingFrom(int index);

    int getCommitIndex();
    int getLastApplied();
    // void setCommitIndex(int index);
    // void setLastApplied(int index);

    int commitIndex;
    int lastApplied;
    std::mutex log_mutex;

private:
    std::vector<LogEntry> log;
};