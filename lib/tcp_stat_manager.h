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

#include <vector>              // CHANGED: For thread pool
#include <queue>               // CHANGED: For task queue
#include <condition_variable>  // CHANGED: For synchronization
#include <atomic>              // CHANGED: For thread-safe flags

#include <numeric>
#include <cmath>

#include <netinet/in.h>       // CHANGED: Include for Netlink sockets
#include <linux/netlink.h>    // CHANGED: Include for Netlink sockets
#include <linux/inet_diag.h>  // CHANGED: Include for Netlink sockets
// #include <linux/tcp.h>        // CHANGED: Include for TCP info
#include <sys/socket.h>       // CHANGED: Include for sockets
#include <unistd.h>           // CHANGED: Include for close()

#include <linux/sock_diag.h>
#include <linux/rtnetlink.h>
#include <cstring>            // For memset
#include <arpa/inet.h>        // For inet_ntop

#include <netinet/ip.h>
#include <netinet/tcp.h>

#include <fcntl.h>

#include <asm/byteorder.h>


#include <glog/logging.h>

const size_t MAX_SAMPLES = 1000;

struct TcpConnectionStats {
    std::vector<double> rttSamples;
    std::vector<double> rttVarSamples;
    uint32_t retransmissions;
    uint32_t count;      // Count of connections

    double meanRtt() const;
    double rttVariance() const;
    double meanRttVar() const;
    std::pair<double, double> rttConfidenceInterval(double confidenceLevel) const;
};

class TcpStatManager {
public:
    // TcpStatManager();
    TcpStatManager(const std::string& self_ip);
    ~TcpStatManager();
    void startMonitoring();
    void stopMonitoring();
    void printStats();

    void startPeriodicStatsPrinting(int intervalInSeconds);
    void stopPeriodicStatsPrinting();

    std::map<std::pair<std::string, std::string>, TcpConnectionStats> connectionStats;
    std::mutex statsMutex;

private:
    void readTcpStats();
    void readTcpStats(const std::string& filterIp, bool filterBySource);

    void processNetlinkResponse(const char* buffer, int len);
    void aggregateTcpStats(const std::string& src_ip, const std::string& dst_ip, double rtt,double rttVar, uint32_t  retransmissions);

    void initializeThreadPool(size_t numThreads);
    void shutdownThreadPool();

    std::vector<std::thread> threadPool;                       // CHANGED: Thread pool
    std::queue<std::function<void()>> taskQueue;               // CHANGED: Task queue
    std::mutex queueMutex;                                     // CHANGED: Mutex for task queue
    std::condition_variable condition;                         // CHANGED: Condition variable for synchronization
    bool stopThreadPool;                                       // CHANGED: Flag to stop thread pool

    std::thread monitoringThread;
//    bool running;
//    fot thread safety
    std::atomic<bool> running;


    std::thread statsPrintingThread;
    std::atomic<bool> stopPeriodicPrinting{false};

    std::string self_ip;
};

#endif // TCP_STAT_MANAGER_H