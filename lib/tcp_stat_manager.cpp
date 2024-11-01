// TcpStatManager.cpp
#include "tcp_stat_manager.h"
#include <sstream>
#include <cstdlib>
#include <chrono>


double TcpConnectionStats::meanRtt() const {
    if (rttSamples.empty()) return 0.0;
    double sum = std::accumulate(rttSamples.begin(), rttSamples.end(), 0.0);
    return sum / rttSamples.size();
}


double TcpConnectionStats::rttVariance() const {
    if (rttSamples.size() < 2) return 0.0;
    double mean = meanRtt();
    double accum = 0.0;
    for (double rtt : rttSamples) {
        accum += (rtt - mean) * (rtt - mean);
    }
    return accum / (rttSamples.size() - 1);
}

double TcpConnectionStats::meanRttVar() const {
    if (rttVarSamples.empty()) return 0.0;
    double sum = std::accumulate(rttVarSamples.begin(), rttVarSamples.end(), 0.0);
    return sum / rttVarSamples.size();
}


double getZScore(double confidenceLevel) {
    if (confidenceLevel == 0.90) return 1.645;
    if (confidenceLevel == 0.95) return 1.96;
    if (confidenceLevel == 0.99) return 2.576;
    // Default to 95% confidence
    if (confidenceLevel == 0.999) return 3.291;
    if (confidenceLevel == 0.995) return 2.807;
    return 1.96;
}


std::pair<double, double> TcpConnectionStats::rttConfidenceInterval(double confidenceLevel) const {
    if (rttSamples.size() < 2) return {meanRtt(), meanRtt()};
    double mean = meanRtt();
    double variance = meanRttVar();
    double stddev = std::sqrt(variance);
    // For large sample sizes, use Z-score
    double z = getZScore(confidenceLevel);


    double marginOfError = z * stddev;

    LOG(INFO) << "Calculating the confidence interval: Mean: " << mean << ", Variance: " << variance << ", StdDev: " << stddev << ", Margin of Error: " << marginOfError;
    return {mean - marginOfError, mean + marginOfError};
}

double TcpConnectionStats::jacobsonEst() const {
    if (rttSamples.empty()) return 0.0;  // No RTT samples available

    // Initialize SRTT and RTTVAR if they don't exist
    double srtt = meanRtt();   // Initial SRTT
    double rttvar = meanRttVar(); // Initial RTTVAR

    LOG(INFO) << "SRTT: " << srtt << ", RTTVAR: " << rttvar;

    // Calculate Retransmission Timeout (RTO) using SRTT and RTTVAR
    double rto = srtt + 4 * rttvar;

    // Ensure RTO is at least a minimum threshold, in our case 300ms
    const double max_RTO = 300;
    return std::min(rto, max_RTO);
}



TcpStatManager::TcpStatManager(const std::string& self_ip) : stopThreadPool(false), running(false)  {
    this->self_ip = self_ip;
    LOG(INFO) << "TCP manager initialized with IP: " << self_ip;
    initializeThreadPool(std::thread::hardware_concurrency());  // Initialize thread pool
    LOG(INFO) << "Initialized TCP statistics manager, concurrency: " << std::thread::hardware_concurrency();
    startPeriodicStatsPrinting(15);
}

TcpStatManager::~TcpStatManager() {
    stopMonitoring();
    shutdownThreadPool();
    stopPeriodicStatsPrinting();
}

// CHANGED: Initialize thread pool
void TcpStatManager::initializeThreadPool(size_t numThreads) {
    for (size_t i = 0; i < numThreads; ++i) {
        threadPool.emplace_back([this]() {
            while (true) {
                std::function<void()> task;

                {
                    std::unique_lock<std::mutex> lock(queueMutex);
                    condition.wait(lock, [this]() { return stopThreadPool || !taskQueue.empty(); });
                    if (stopThreadPool && taskQueue.empty())
                        return;
                    task = std::move(taskQueue.front());
                    taskQueue.pop();
                }

                task();
            }
        });
    }
}

// CHANGED: Shutdown thread pool
void TcpStatManager::shutdownThreadPool() {
    {
        std::unique_lock<std::mutex> lock(queueMutex);
        stopThreadPool = true;
    }
    condition.notify_all();
    for (std::thread &worker : threadPool) {
        if (worker.joinable())
            worker.join();
    }
}

//double TcpConnectionStats::averageRtt() const {
//    return count == 0 ? 0.0 : static_cast<double>(totalRtt) / count;
//}
//
//double TcpConnectionStats::averageRetransmissions() const {
//    return count == 0 ? 0.0 : static_cast<double>(retransmissions) / count;
//}

// void TcpStatManager::startMonitoring() {
//     running = true;
//     monitoringThread = std::thread([this]() {
//         while (running) {
//             readTcpStats();
//             // std::this_thread::sleep_for(std::chrono::seconds(1));
//             // change the frequency of the monitoring
//             std::this_thread::sleep_for(std::chrono::milliseconds(100));
//         }
//     });
// }


void TcpStatManager::startMonitoring() {
    running = true;
    monitoringThread = std::thread([this]() {
        while (running) {
            {
                std::unique_lock<std::mutex> lock(queueMutex);
                // taskQueue.emplace([this]() {
                //     readTcpStats();  // CHANGED: Task added to thread pool
                // });

                // Enqueue task to monitor by source IP
                taskQueue.emplace([this]() {
                    readTcpStats(self_ip, true);  // Filter by source IP
                });
                // Enqueue task to monitor by destination IP
                taskQueue.emplace([this]() {
                    readTcpStats(self_ip, false);  // Filter by destination IP
                });
            }
            // condition.notify_one();
            condition.notify_all();
            // Adjust sleep interval as needed
            std::this_thread::sleep_for(std::chrono::milliseconds(4000));
        }
    });
}


void TcpStatManager::stopMonitoring() {
    running = false;
    if (monitoringThread.joinable()) {
        monitoringThread.join();
    }
}

void TcpStatManager::printStats() {
    std::lock_guard<std::mutex> lock(statsMutex);
    LOG(INFO) << "TCP Statistics (by Connection Pair):\n";
    for (const auto& [connection, stats] : connectionStats) {
        auto [lowerBound, upperBound] = stats.rttConfidenceInterval(0.99);
        LOG(INFO) << "Connection: " << connection.first << " -> " << connection.second
                  << ", Mean RTT: " << stats.meanRtt() << " ms"
                  << ", RTT 95% Confidence Interval: [" << lowerBound << ", " << upperBound << "] ms"
                  << ", Retransmissions: " << stats.retransmissions;
    }
}

void TcpStatManager::readTcpStats() {
    // LOG(INFO) << "Reading TCP stats using Netlink socket";
    int sock = socket(AF_NETLINK, SOCK_RAW, NETLINK_INET_DIAG);
    if (sock < 0) {
        perror("socket");
        return;
    }

    // Set socket to non-blocking mode
    int flags = fcntl(sock, F_GETFL, 0);
    if (flags == -1) {
        perror("fcntl F_GETFL");
        close(sock);
        return;
    }
    if (fcntl(sock, F_SETFL, flags | O_NONBLOCK) == -1) {
        perror("fcntl F_SETFL");
        close(sock);
        return;
    }

    // Prepare Netlink message
    struct {
        struct nlmsghdr nlh;
        struct inet_diag_req_v2 req;
    } request;

    memset(&request, 0, sizeof(request));
    request.nlh.nlmsg_len = NLMSG_LENGTH(sizeof(struct inet_diag_req_v2));
    request.nlh.nlmsg_type = SOCK_DIAG_BY_FAMILY;
    request.nlh.nlmsg_flags = NLM_F_REQUEST | NLM_F_DUMP;

    request.req.sdiag_family = AF_INET;
    request.req.sdiag_protocol = IPPROTO_TCP;
    request.req.idiag_states = (1 << TCP_ESTABLISHED);  // Corrected state filter
    request.req.idiag_ext = (1 << (INET_DIAG_INFO - 1));  // Request INET_DIAG_INFO

    // Send Netlink message
    if (send(sock, &request, request.nlh.nlmsg_len, 0) < 0) {
        perror("send");
        close(sock);
        return;
    }

    // Receive and process responses
    char buffer[8192];
    int len;
    while (true) {
        len = recv(sock, buffer, sizeof(buffer), 0);
        if (len > 0) {
            // Process the Netlink response in a separate task
            {
                // LOG(INFO) << "Netlink info received, len=" << len;
                std::unique_lock<std::mutex> lock(queueMutex);
                taskQueue.emplace([this, bufferCopy = std::string(buffer, len)]() {
                    processNetlinkResponse(bufferCopy.c_str(), bufferCopy.size());
                });
            }
            condition.notify_one();
        } else if (len == 0) {
            LOG(INFO) << "recv() returned 0, no more data to read";
            break;
        } else {
            if (errno == EAGAIN || errno == EWOULDBLOCK) {
                LOG(INFO) << "recv() would block, no data available";
                break;
            } else {
                perror("recv");
                break;
            }
        }
    }

    close(sock);
}

bool convertIpToInAddr(const std::string& ipStr, struct in_addr& addr) {
    return inet_pton(AF_INET, ipStr.c_str(), &addr) == 1;
}


// void TcpStatManager::readTcpStats(const std::string& filterIp, bool filterBySource) {
//     int sock = socket(AF_NETLINK, SOCK_RAW, NETLINK_INET_DIAG);
//     if (sock < 0) {
//         perror("socket");
//         return;
//     }

//     // Prepare Netlink message buffer
//     char nlmsgbuf[8192];
//     memset(nlmsgbuf, 0, sizeof(nlmsgbuf));

//     struct nlmsghdr *nlh = (struct nlmsghdr *)nlmsgbuf;
//     nlh->nlmsg_len = NLMSG_LENGTH(sizeof(struct inet_diag_req_v2));
//     nlh->nlmsg_type = SOCK_DIAG_BY_FAMILY;
//     nlh->nlmsg_flags = NLM_F_REQUEST | NLM_F_DUMP;

//     struct inet_diag_req_v2 *req = (struct inet_diag_req_v2 *)NLMSG_DATA(nlh);
//     memset(req, 0, sizeof(struct inet_diag_req_v2));
//     req->sdiag_family = AF_INET;
//     req->sdiag_protocol = IPPROTO_TCP;
//     req->idiag_states = (1 << TCP_ESTABLISHED);
//     req->idiag_ext = 0;

//     // Build the bytecode filter
//     char bytecode[256];
//     int bytecode_len = 0;

//     // Convert filter IP to binary
//     struct in_addr ipAddr;
//     if (!inet_pton(AF_INET, filterIp.c_str(), &ipAddr)) {
//         LOG(ERROR) << "Invalid IP address format: " << filterIp;
//         close(sock);
//         return;
//     }

//     // Set up the filter operation
//     struct inet_diag_bc_op op;
//     memset(&op, 0, sizeof(op));
//     op.code = filterBySource ? INET_DIAG_BC_S_EQ : INET_DIAG_BC_D_EQ;
//     op.yes = sizeof(op) + sizeof(struct inet_diag_hostcond) + sizeof(ipAddr.s_addr);
//     op.no = 0;

//     // Build the host condition
//     struct inet_diag_hostcond hostcond;
//     memset(&hostcond, 0, sizeof(hostcond));
//     hostcond.family = AF_INET;
//     hostcond.prefix_len = 32; // Match full IP address
//     hostcond.port = -1;       // Ignore port

//     // Append operation, host condition, and IP address to bytecode
//     memcpy(bytecode + bytecode_len, &op, sizeof(op));
//     bytecode_len += sizeof(op);
//     memcpy(bytecode + bytecode_len, &hostcond, sizeof(hostcond));
//     bytecode_len += sizeof(hostcond);
//     memcpy(bytecode + bytecode_len, &ipAddr.s_addr, sizeof(ipAddr.s_addr));
//     bytecode_len += sizeof(ipAddr.s_addr);

//     // Add the bytecode as a Netlink attribute
//     // struct rtattr *rta = (struct rtattr *)NLMSG_TAIL(nlh);
//     struct rtattr *rta = (struct rtattr *)((char *)nlh + NLMSG_ALIGN(nlh->nlmsg_len));

//     rta->rta_type = INET_DIAG_REQ_BYTECODE;
//     rta->rta_len = RTA_LENGTH(bytecode_len);
//     memcpy(RTA_DATA(rta), bytecode, bytecode_len);

//     // Adjust the message length to include the attribute
//     nlh->nlmsg_len = NLMSG_ALIGN(nlh->nlmsg_len) + RTA_ALIGN(rta->rta_len);

//     // Send Netlink message
//     if (send(sock, nlmsgbuf, nlh->nlmsg_len, 0) < 0) {
//         perror("send");
//         close(sock);
//         return;
//     }

//     // Receive and process responses
//     char buffer[8192];
//     int len;
//     while (true) {
//         len = recv(sock, buffer, sizeof(buffer), 0);
//         if (len > 0) {
//             {
//                 std::unique_lock<std::mutex> lock(queueMutex);
//                 taskQueue.emplace([this, bufferCopy = std::string(buffer, len)]() {
//                     processNetlinkResponse(bufferCopy.c_str(), bufferCopy.size());
//                 });
//             }
//             condition.notify_one();
//         } else if (len == 0) {
//             break;
//         } else {
//             if (errno == EAGAIN || errno == EWOULDBLOCK) {
//                 break;
//             } else {
//                 perror("recv");
//                 break;
//             }
//         }
//     }

//     close(sock);
// }


void TcpStatManager::readTcpStats(const std::string& filterIp, bool filterBySource) {
    // LOG(INFO) << "Reading TCP stats using Netlink socket";
    int sock = socket(AF_NETLINK, SOCK_RAW, NETLINK_INET_DIAG);
    if (sock < 0) {
        perror("socket");
        return;
    }

    // Set socket to non-blocking mode
    int flags = fcntl(sock, F_GETFL, 0);
    if (flags == -1) {
        perror("fcntl F_GETFL");
        close(sock);
        return;
    }
    if (fcntl(sock, F_SETFL, flags | O_NONBLOCK) == -1) {
        perror("fcntl F_SETFL");
        close(sock);
        return;
    }

    struct {
        struct nlmsghdr nlh;
        struct inet_diag_req req;
    } request;

    memset(&request, 0, sizeof(request));
    request.nlh.nlmsg_len = NLMSG_LENGTH(sizeof(struct inet_diag_req));
    request.nlh.nlmsg_type = TCPDIAG_GETSOCK;  // Use TCPDIAG_GETSOCK for TCP sockets
    request.nlh.nlmsg_flags = NLM_F_REQUEST | NLM_F_DUMP;

    request.req.idiag_family = AF_INET;
    request.req.idiag_states = (1 << TCP_ESTABLISHED);  // Filter for established connections
    request.req.idiag_ext = (1 << (INET_DIAG_INFO - 1));  // Request INET_DIAG_INFO

    // Set up filter for specific IP
    struct in_addr ipAddr;
    if (!inet_pton(AF_INET, filterIp.c_str(), &ipAddr)) {
        LOG(ERROR) << "Invalid IP address format: " << filterIp;
        close(sock);
        return;
    }

    if (filterBySource) {
        // Filter by source IP
        request.req.idiag_src_len = 4;  // IPv4 address length
        request.req.id.idiag_src[0] = ipAddr.s_addr;
        request.req.idiag_dst_len = 0;  // Not filtering by destination
    } else {
        // Filter by destination IP
        request.req.idiag_dst_len = 4;  // IPv4 address length
        request.req.id.idiag_dst[0] = ipAddr.s_addr;
        request.req.idiag_src_len = 0;  // Not filtering by source
    }

    // Initialize the rest of id fields
    request.req.id.idiag_sport = 0;
    request.req.id.idiag_dport = 0;
    request.req.id.idiag_if = 0;
    request.req.id.idiag_cookie[0] = INET_DIAG_NOCOOKIE;
    request.req.id.idiag_cookie[1] = INET_DIAG_NOCOOKIE;

    // Send Netlink message
    if (send(sock, &request, request.nlh.nlmsg_len, 0) < 0) {
        perror("send");
        close(sock);
        return;
    }

    // Send Netlink message
    if (send(sock, &request, request.nlh.nlmsg_len, 0) < 0) {
        perror("send");
        close(sock);
        return;
    }

    // Receive and process responses
    char buffer[8192];
    int len;
    while (true) {
        len = recv(sock, buffer, sizeof(buffer), 0);
        if (len > 0) {
            // Process the Netlink response in a separate task
            {
                // LOG(INFO) << "Netlink info received, len=" << len;
                std::unique_lock<std::mutex> lock(queueMutex);
                taskQueue.emplace([this, bufferCopy = std::string(buffer, len)]() {
                    processNetlinkResponse(bufferCopy.c_str(), bufferCopy.size());
                });
            }
            condition.notify_one();
        } else if (len == 0) {
            LOG(INFO) << "recv() returned 0, no more data to read";
            break;
        } else {
            if (errno == EAGAIN || errno == EWOULDBLOCK) {
                LOG(INFO) << "recv() would block, no data available";
                break;
            } else {
                perror("recv");
                break;
            }
        }
    }

    close(sock);
}


void TcpStatManager::processNetlinkResponse(const char* buffer, int len) {
    // LOG(INFO) << "Processing Netlink response";
    struct nlmsghdr *nlh = (struct nlmsghdr *)buffer;
    for (; NLMSG_OK(nlh, len); nlh = NLMSG_NEXT(nlh, len)) {
        // LOG(INFO) << "Netlink message type: " << nlh->nlmsg_type << ", length: " << nlh->nlmsg_len;
        if (nlh->nlmsg_type == NLMSG_DONE) {
            LOG(INFO) << "Netlink message done";
            break;
        }
        if (nlh->nlmsg_type == NLMSG_ERROR) {
            LOG(ERROR) << "Netlink message error";
            struct nlmsgerr *err = (struct nlmsgerr *)NLMSG_DATA(nlh);
            LOG(ERROR) << "Netlink error code: " << strerror(-err->error);
            break;
        }

        struct inet_diag_msg *diag_msg = (struct inet_diag_msg *)NLMSG_DATA(nlh);

        // Extract source and destination IPs and ports
        char src_ip[INET_ADDRSTRLEN], dst_ip[INET_ADDRSTRLEN];
        inet_ntop(AF_INET, &diag_msg->id.idiag_src, src_ip, sizeof(src_ip));
        inet_ntop(AF_INET, &diag_msg->id.idiag_dst, dst_ip, sizeof(dst_ip));

        // Extract RTT and RTT variance
        uint32_t rtt = 0, rtt_var = 0;
        uint32_t retrans = 0;
        uint32_t lastsnd = 0;

        struct rtattr *attr = (struct rtattr *)(diag_msg + 1);
        int rta_len = nlh->nlmsg_len - NLMSG_LENGTH(sizeof(*diag_msg));

        for (; RTA_OK(attr, rta_len); attr = RTA_NEXT(attr, rta_len)) {
            if (attr->rta_type == INET_DIAG_INFO) {
                struct tcp_info *tcpi = (struct tcp_info *)RTA_DATA(attr);
                rtt = tcpi->tcpi_rtt;           // Value in microseconds
                rtt_var = tcpi->tcpi_rttvar;    // Value in microseconds
                retrans = tcpi->tcpi_total_retrans;
                lastsnd = tcpi->tcpi_last_data_sent;

                // if (lastsnd > 100) {
                //     LOG(INFO) << "Last send time: " << lastsnd << " which is too far back into history, DISCARDING";
                //     continue;
                // }
            }
        }

        // LOG(INFO) << "Raw tcpi_rttvar: " << rtt_var;

        // Convert RTT and RTT variance to milliseconds
        double rtt_ms = rtt / 1000.0;
        double rtt_var_ms = rtt_var / 1000.0;

        // LOG(INFO) << "Netlink INFO: " << src_ip << " -> " << dst_ip
        //           << ", RTT: " << rtt_ms << " ms, RTT Variance: " << rtt_var_ms << " ms, Retransmissions: " << retrans;

        // Aggregate stats
        aggregateTcpStats(src_ip, dst_ip, rtt_ms, rtt_var_ms, retrans);
    }

    // LOG(INFO) << "DONE Processed Netlink response";
}

void TcpStatManager::aggregateTcpStats(const std::string& src_ip, const std::string& dst_ip, double rtt, double rttVar, uint32_t retransmissions) {
    std::lock_guard<std::mutex> lock(statsMutex); 
    
    auto key = std::make_pair(src_ip, dst_ip);
    
    if (connectionStats.find(key) == connectionStats.end()) {
        TcpConnectionStats stats;
        stats.rttSamples = {rtt};
        stats.rttVarSamples = {rttVar};
        stats.retransmissions = retransmissions;
        stats.count = 1;
        connectionStats[key] = stats;
        // LOG(INFO) << "Added stats for new connection: " << src_ip << " -> " << dst_ip
        //           << ", RTT: " << rtt << " ms, rttvat: " << rttVar;
    } else {
        TcpConnectionStats& stats = connectionStats[key];
        if (stats.rttSamples.size() >= MAX_SAMPLES) {
            stats.rttSamples.erase(stats.rttSamples.begin());
            stats.rttVarSamples.erase(stats.rttVarSamples.begin());
        }
        stats.rttSamples.push_back(rtt);
        stats.rttVarSamples.push_back(rttVar);
        stats.retransmissions += retransmissions;
        stats.count++;
        // LOG(INFO) << "Added stats for connection: " << src_ip << " -> " << dst_ip
        //           << ", RTT: " << rtt << " ms, rttvar: " << rttVar;
    }
}


void TcpStatManager::startPeriodicStatsPrinting(int intervalInSeconds) {
    stopPeriodicPrinting = false; // Reset the stop flag
    statsPrintingThread = std::thread([this, intervalInSeconds]() {
        while (!stopPeriodicPrinting) {
            printStats();
            std::this_thread::sleep_for(std::chrono::seconds(intervalInSeconds));
        }
    });
}

void TcpStatManager::stopPeriodicStatsPrinting() {
    stopPeriodicPrinting = true;
    if (statsPrintingThread.joinable()) {
        statsPrintingThread.join();
    }
}

