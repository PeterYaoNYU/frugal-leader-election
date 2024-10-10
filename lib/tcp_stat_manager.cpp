// TcpStatManager.cpp
#include "tcp_stat_manager.h"
#include <sstream>
#include <cstdlib>
#include <chrono>

TcpStatManager::TcpStatManager() : running(false) {}

TcpStatManager::~TcpStatManager() {
    stopMonitoring();
}

double TcpConnectionStats::averageRtt() const {
    return count == 0 ? 0.0 : static_cast<double>(totalRtt) / count;
}

double TcpConnectionStats::averageRetransmissions() const {
    return count == 0 ? 0.0 : static_cast<double>(retransmissions) / count;
}

void TcpStatManager::startMonitoring() {
    running = true;
    monitoringThread = std::thread([this]() {
        while (running) {
            readTcpStats();
            std::this_thread::sleep_for(std::chrono::seconds(1));
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
        LOG(INFO) << "Connection: " << connection.first << " -> " << connection.second
                  << ", Average RTT: " << stats.averageRtt() 
                  << ", Average Retransmissions: " << stats.averageRetransmissions();
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

        char buffer[256];
        uint32_t srtt = 0;
        while (fgets(buffer, sizeof(buffer), pipe) != nullptr) {
            std::string output(buffer);
            std::size_t pos = output.find("rtt:");
            if (pos != std::string::npos) {
                std::istringstream rttStream(output.substr(pos + 4));
                rttStream >> srtt;
                break;
            }
        }
        pclose(pipe);

        uint32_t retransmissions = retrnsmt;
        aggregateTcpStats(src_ip, dst_ip, srtt, retransmissions);
    }

    tcpFile.close();
}

void TcpStatManager::aggregateTcpStats(const std::string& src_ip, const std::string& dst_ip, uint32_t rtt, uint32_t retransmissions) {
    std::pair<std::string, std::string> key = {src_ip, dst_ip};
    if (connectionStats.find(key) == connectionStats.end()) {
        connectionStats[key] = {rtt, retransmissions, 1};
    } else {
        connectionStats[key].totalRtt += rtt;
        connectionStats[key].retransmissions += retransmissions;
        connectionStats[key].count++;
    }
}
