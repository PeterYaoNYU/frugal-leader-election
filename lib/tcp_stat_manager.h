// TcpStatManager.h
#ifndef TCP_STAT_MANAGER_H
#define TCP_STAT_MANAGER_H

#include <fstream>
#include <iostream>
#include <map>
#include <string>
#include <thread>
#include <regex>
#include <mutex>

#include <glog/logging.h>

struct TcpConnectionStats {
    uint32_t totalRtt;   // Total RTT in microseconds
    uint32_t retransmissions;
    uint32_t count;      // Count of connections

    double averageRtt() const;
    double averageRetransmissions() const;
};

class TcpStatManager {
public:
    TcpStatManager();
    ~TcpStatManager();
    void startMonitoring();
    void stopMonitoring();
    void printStats();

    std::map<std::pair<std::string, std::string>, TcpConnectionStats> connectionStats;
    std::mutex statsMutex;

private:
    void readTcpStats();
    void aggregateTcpStats(const std::string& src_ip, const std::string& dst_ip, uint32_t rtt, uint32_t retransmissions);

    std::thread monitoringThread;
    bool running;
};

#endif // TCP_STAT_MANAGER_H