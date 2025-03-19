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
    int getLastLogIndex();
    int getLastLogTerm();
    bool getEntry(int index, LogEntry& entry);
    // Check whether the log contains an entry at index with the specified term.
    bool containsEntry(int index, int term);
    // Delete all entries starting from index
    void deleteEntriesStartingFrom(int index);

    int commitIndex;
    int lastApplied;

private:
    std::vector<LogEntry> log;
    // I choose not to expose the mutex to exernal classes
    std::mutex log_mutex;
};