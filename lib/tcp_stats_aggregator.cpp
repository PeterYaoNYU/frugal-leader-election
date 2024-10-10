#include <fstream>
#include <iostream>
#include <map>
#include <string>
#include <chrono>
#include <thread>
#include <sstream>
#include <regex>

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

void aggregateTcpStats(std::map<std::string, TcpConnectionStats>& statsMap, const std::string& key, uint32_t rtt, uint32_t retransmissions) {
    if (statsMap.find(key) == statsMap.end()) {
        statsMap[key] = {rtt, retransmissions, 1};
    } else {
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

    std::map<std::string, TcpConnectionStats> originStats, destStats;

    std::regex filterRegex("^0A0000[0-9A-F]{2}$"); // Matches IPs of the form 10.0.*.2 in hex

    while (std::getline(tcpFile, line)) {
        std::istringstream iss(line);
        std::string sl, localAddress, remAddress, state;
        uint32_t txQueue, rxQueue, tr, tm_when, retrnsmt, uid, timeout, inode;

        iss >> sl >> localAddress >> remAddress >> state >> txQueue >> rxQueue >> tr >> tm_when >> retrnsmt >> uid >> timeout >> inode;

        // Extract source and destination IP addresses
        std::string src_ip = localAddress.substr(0, localAddress.find(':'));
        std::string dst_ip = remAddress.substr(0, remAddress.find(':'));

        // Apply the filter to keep only entries with destination or origin of 10.0.*.2
        if (!std::regex_match(src_ip, filterRegex) && !std::regex_match(dst_ip, filterRegex)) {
            continue;
        }

        // For simplicity, using retransmissions as RTT value (inaccurate, but for demonstration)
        uint32_t rtt = retrnsmt;
        uint32_t retransmissions = retrnsmt;

        aggregateTcpStats(originStats, src_ip, rtt, retransmissions);
        aggregateTcpStats(destStats, dst_ip, rtt, retransmissions);
    }
    
    // Print aggregated stats
    std::cout << "TCP Statistics (by Origin):\n";
    for (const auto& [origin, stats] : originStats) {
        std::cout << "Origin IP: " << origin 
                  << ", Average RTT: " << stats.averageRtt() 
                  << ", Average Retransmissions: " << stats.averageRetransmissions() 
                  << "\n";
    }

    std::cout << "TCP Statistics (by Destination):\n";
    for (const auto& [dest, stats] : destStats) {
        std::cout << "Destination IP: " << dest 
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