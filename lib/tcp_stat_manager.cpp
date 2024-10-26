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

double getZScore(double confidenceLevel) {
    if (confidenceLevel == 0.90) return 1.645;
    if (confidenceLevel == 0.95) return 1.96;
    if (confidenceLevel == 0.99) return 2.576;
    if (confidenceLevel == 0.999) return 3.291;
    if (confidenceLevel == 0.995) return 2.807;
    // Default to 95% confidence
    return 1.96;
}


std::pair<double, double> TcpConnectionStats::rttConfidenceInterval(double confidenceLevel) const {
    if (rttSamples.size() < 2) return {meanRtt(), meanRtt()};
    double mean = meanRtt();
    double variance = rttVariance();
    double stddev = std::sqrt(variance);
    // For large sample sizes, use Z-score
    double z = getZScore(confidenceLevel);
    double marginOfError = z * stddev / std::sqrt(rttSamples.size());

    LOG(INFO) << "Calculating the confidence interval: Mean: " << mean << ", Variance: " << variance << ", StdDev: " << stddev << ", Margin of Error: " << marginOfError;
    return {mean - marginOfError, mean + marginOfError};
}



TcpStatManager::TcpStatManager() : running(false) {}

TcpStatManager::~TcpStatManager() {
    stopMonitoring();
    stopPeriodicStatsPrinting();
}

//double TcpConnectionStats::averageRtt() const {
//    return count == 0 ? 0.0 : static_cast<double>(totalRtt) / count;
//}
//
//double TcpConnectionStats::averageRetransmissions() const {
//    return count == 0 ? 0.0 : static_cast<double>(retransmissions) / count;
//}

void TcpStatManager::startMonitoring() {
    running = true;
    monitoringThread = std::thread([this]() {
        while (running) {
            readTcpStats();
            // std::this_thread::sleep_for(std::chrono::seconds(1));
            // change the frequency of the monitoring
            std::this_thread::sleep_for(std::chrono::milliseconds(50));
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
    std::cout << "TCP Statistics (by Connection Pair):\n";
    for (const auto& [connection, stats] : connectionStats) {
        auto [lowerBound, upperBound] = stats.rttConfidenceInterval(0.95);
        LOG(INFO) << "Connection: " << connection.first << " -> " << connection.second
                  << ", Mean RTT: " << stats.meanRtt() << " ms"
                  << ", RTT 95% Confidence Interval: [" << lowerBound << ", " << upperBound << "] ms"
                  << ", Retransmissions: " << stats.retransmissions;
    }
}

void TcpStatManager::readTcpStats() {
    std::ifstream tcpFile("/proc/net/tcp");
    if (!tcpFile.is_open()) {
        std::cerr << "Failed to open /proc/net/tcp" << std::endl;
        return;
    }

    std::string line;
    std::getline(tcpFile, line); // Skip the header line

    std::lock_guard<std::mutex> lock(statsMutex);

    while (std::getline(tcpFile, line)) {
        std::istringstream iss(line);
        std::string sl, localAddress, remAddress, state;
        uint32_t txQueue, rxQueue, tr, tm_when, retrnsmt, uid, timeout, inode;

        iss >> sl >> localAddress >> remAddress >> state >> txQueue >> rxQueue >> tr >> tm_when >> retrnsmt >> uid >> timeout >> inode;

        // Extract source and destination IP addresses considering endianess
        std::string src_ip = std::to_string((std::stoul(localAddress.substr(6, 2), nullptr, 16))) + "." +
                             std::to_string((std::stoul(localAddress.substr(4, 2), nullptr, 16))) + "." +
                             std::to_string((std::stoul(localAddress.substr(2, 2), nullptr, 16))) + "." +
                             std::to_string((std::stoul(localAddress.substr(0, 2), nullptr, 16)));

        std::string dst_ip = std::to_string((std::stoul(remAddress.substr(6, 2), nullptr, 16))) + "." +
                             std::to_string((std::stoul(remAddress.substr(4, 2), nullptr, 16))) + "." +
                             std::to_string((std::stoul(remAddress.substr(2, 2), nullptr, 16))) + "." +
                             std::to_string((std::stoul(remAddress.substr(0, 2), nullptr, 16)));

        // Apply the filter to keep only entries with destination or origin of 10.0.*.2
        if (!std::regex_match(src_ip, std::regex("^10\.0\..*\.2$")) && !std::regex_match(dst_ip, std::regex("^10\.0\..*\.2$"))) {
            continue;
        }

        // Use `ss` command to get SRTT for the socket
        std::string command = "ss -ti src " + src_ip + " dst " + dst_ip;
        FILE* pipe = popen(command.c_str(), "r");
        if (!pipe) {
            std::cerr << "Failed to run ss command" << std::endl;
            continue;
        }

        char buffer[512];
        double rtt = 0.0;
        double rttVar = 0.0;

        uint64_t bytes_acked = 0;
        uint64_t bytes_received = 0;
        uint64_t lastsnd = 0;
        uint64_t lastrcv = 0;


        while (fgets(buffer, sizeof(buffer), pipe) != nullptr) {
            std::string output(buffer);
            std::smatch match;
            // Match RTT and variance (e.g., rtt:100/50)
            if (std::regex_search(output, match, std::regex("rtt:([0-9]+(?:\\.[0-9]+)?)/([0-9]+(?:\\.[0-9]+)?)"))) {
                rtt = std::stod(match[1]);
                rttVar = std::stod(match[2]);
            }

            // ADDITION: Parse bytes_acked
            if (std::regex_search(output, match, std::regex("bytes_acked:([0-9]+)"))) {
                bytes_acked = std::stoull(match[1]);
            }

            // ADDITION: Parse bytes_received
            if (std::regex_search(output, match, std::regex("bytes_received:([0-9]+)"))) {
                bytes_received = std::stoull(match[1]);
            }

            // ADDITION: Parse lastsnd
            if (std::regex_search(output, match, std::regex("lastsnd:([0-9]+)"))) {
                lastsnd = std::stoull(match[1]);
            }

            // ADDITION: Parse lastrcv
            if (std::regex_search(output, match, std::regex("lastrcv:([0-9]+)"))) {
                lastrcv = std::stoull(match[1]);
            }
        }
        pclose(pipe);

        bool data_received = (bytes_acked >= BYTES_ACKS_THRESHOLD) || (bytes_received >= BYTES_RECV_THRESHOLD);
        bool recent_activity = (lastsnd <= LAST_SEND_TIME_THRESHOLD) || (lastrcv <= LAST_RECV_TIME_THRESHOLD);

        // Only aggregate if both conditions are met
        if (data_received && recent_activity) {
            uint32_t retransmissions = retrnsmt;
            aggregateTcpStats(src_ip, dst_ip, rtt, retransmissions);
            LOG(INFO) << "src IP: " << src_ip << " dst IP: " << dst_ip << " RTT: " << rtt << " ms, RTT Variance: " << rttVar << " ms. Bytes Acked: " << bytes_acked << ", Bytes Received: " << bytes_received << ", last send time: " << lastsnd << ", last recv time: " << lastrcv;
        } else {
            // Skip aggregation for this connection
            continue;
        }
    }

    tcpFile.close();
}

void TcpStatManager::aggregateTcpStats(const std::string& src_ip, const std::string& dst_ip, double rtt, uint32_t retransmissions) {
    auto key = std::make_pair(src_ip, dst_ip);
    
    if (connectionStats.find(key) == connectionStats.end()) {
        TcpConnectionStats stats;
        stats.rttSamples = {rtt};
        stats.retransmissions = retransmissions;
        stats.count = 1;
        connectionStats[key] = stats;
    } else {
        TcpConnectionStats& stats = connectionStats[key];
        if (stats.rttSamples.size() >= MAX_SAMPLES) {
            stats.rttSamples.erase(stats.rttSamples.begin());
        }
        stats.rttSamples.push_back(rtt);
        stats.retransmissions += retransmissions;
        stats.count++;
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