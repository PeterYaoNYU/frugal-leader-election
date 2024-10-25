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
#include <vector>
#include <numeric>
#include <cmath>
#include <glog/logging.h>

#define BYTES_ACKS_THRESHOLD 100
#define BYTES_RECV_THRESHOLD 200

// Time thresholds in milliseconds
#define LAST_SEND_TIME_THRESHOLD 500
#define LAST_RECV_TIME_THRESHOLD 500

struct TcpConnectionStats {
    std::vector<double> rttSamples;
    uint32_t retransmissions;
    uint32_t count;

    double meanRtt() const;
    double rttVariance() const;
    std::pair<double, double> rttConfidenceInterval(double confidenceLevel) const;
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
    void aggregateTcpStats(const std::string& src_ip, const std::string& dst_ip, double rtt, uint32_t retransmissions);
    bool running;
    std::thread monitoringThread;
};

#endif // TCP_STAT_MANAGER_H
