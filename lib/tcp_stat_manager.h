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

const size_t MAX_SAMPLES = 1000;

struct TcpConnectionStats {
    std::vector<double> rttSamples;
    // now keep a vector instead of an accumulation
    // uint32_t totalRtt;   // Total RTT in microseconds
    uint32_t retransmissions;
    uint32_t count;      // Count of connections

    double meanRtt() const;
    double rttVariance() const;
    std::pair<double, double> rttConfidenceInterval(double confidenceLevel) const;
    // double averageRetransmissions() const;
};


double TcpConnectionStats::meanRtt() const {
    if (rttSamples.empty()) return 0.0;
    double sum = std::accumulate(rttSamples.begin(), rttSamples.end(), 0.0);
    return sum / rttSamples.size();
}

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
//    bool running;
//    fot thread safety
    std::atomic<bool> running;
};

#endif // TCP_STAT_MANAGER_H