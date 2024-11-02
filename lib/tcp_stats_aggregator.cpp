#include <fstream>
#include <iostream>
#include <map>
#include <string>
#include <chrono>
#include <thread>
#include <sstream>
#include <regex>
#include <cstdlib>

struct TcpConnectionStats {
    uint32_t totalRtt;   // Total RTT in microseconds
    uint32_t retransmissions;
    uint32_t count;      // Count of connections

    double averageRtt() const {
        return count == 0 ? 0.0 : static_cast<double>(totalRtt) / count;
    }
    double averageRetransmissions() const {
        return count == 0 ? 0.0 : static_cast<double>(retransmissions) / count;
    }
};

void aggregateTcpStats(std::map<std::pair<std::string, std::string>, TcpConnectionStats>& statsMap, const std::string& src_ip, const std::string& dst_ip, uint32_t rtt, uint32_t retransmissions) {
    std::pair<std::string, std::string> key = {src_ip, dst_ip};
    if (statsMap.find(key) == statsMap.end()) {
        statsMap[key] = {rtt, retransmissions, 1};
    } else {
        // std::cout << "Aggregating stats for connection: " << key.first << " -> " << key.second << "\n";
        statsMap[key].totalRtt += rtt;
        statsMap[key].retransmissions += retransmissions;
        statsMap[key].count++;
    }
}

void readTcpStats() {
    std::ifstream tcpFile("/proc/net/tcp");
    if (!tcpFile.is_open()) {
        std::cerr << "Failed to open /proc/net/tcp" << std::endl;
        return;
    }

    std::string line;
    std::getline(tcpFile, line); // Skip the header line

    std::map<std::pair<std::string, std::string>, TcpConnectionStats> connectionStats;

    std::regex filterRegex("^0A0000[0-9A-F]{2}$"); // Matches IPs of the form 10.0.*.2 in hex

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

        // Aggregate stats based on source and destination pair
        aggregateTcpStats(connectionStats, src_ip, dst_ip, srtt, retransmissions);
    }
    
    // Print aggregated stats
    std::cout << "TCP Statistics (by Connection Pair):\n";
    for (const auto& [connection, stats] : connectionStats) {
        std::cout << "Connection: " << connection.first << " -> " << connection.second
                  << ", Average RTT: " << stats.averageRtt() 
                  << ", Average Retransmissions: " << stats.averageRetransmissions() 
                  << "\n";
    }

    tcpFile.close();
}

int main() {
    std::cout << "Starting TCP statistics aggregation...\n";
    while (true) {
        readTcpStats();
        std::this_thread::sleep_for(std::chrono::seconds(5)); // Adjust the sleep duration for periodic reads
    }

    return 0;
}