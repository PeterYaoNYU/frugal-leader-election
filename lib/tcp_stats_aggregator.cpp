#include <fstream>
#include <iostream>
#include <map>
#include <string>
#include <chrono>
#include <thread>
#include <sstream>
#include <regex>
#include <cstdlib>

#define BYTES_ACKS_THRESHOLD 100
#define BYTES_RECV_THRESHOLD 200

// this time threshold is in milliseconds
#define LAST_SEND_TIME_THRESHOLD 500
#define LAST_RECV_TIME_THRESHOLD 500


// Structure to hold TCP connection statistics
struct TcpConnectionStats {
    uint64_t totalRtt;   // Total RTT in microseconds
    uint64_t retransmissions;
    uint64_t count;      // Count of connections

    double averageRtt() const {
        return count == 0 ? 0.0 : static_cast<double>(totalRtt) / count;
    }
    double averageRetransmissions() const {
        return count == 0 ? 0.0 : static_cast<double>(retransmissions) / count;
    }
};

// Function to aggregate TCP statistics
void aggregateTcpStats(std::map<std::pair<std::string, std::string>, TcpConnectionStats>& statsMap,
                       const std::string& src_ip, const std::string& dst_ip,
                       uint64_t rtt, uint64_t retransmissions) {
    std::pair<std::string, std::string> key = {src_ip, dst_ip};
    if (statsMap.find(key) == statsMap.end()) {
        statsMap[key] = {rtt, retransmissions, 1};
    } else {
        statsMap[key].totalRtt += rtt;
        statsMap[key].retransmissions += retransmissions;
        statsMap[key].count++;
    }
}

// Function to read and process TCP statistics
void readTcpStats() {
    std::ifstream tcpFile("/proc/net/tcp");
    if (!tcpFile.is_open()) {
        std::cerr << "Failed to open /proc/net/tcp" << std::endl;
        return;
    }

    std::string line;
    std::getline(tcpFile, line); // Skip the header line

    std::map<std::pair<std::string, std::string>, TcpConnectionStats> connectionStats;

    while (std::getline(tcpFile, line)) {
        std::istringstream iss(line);
        std::string sl, localAddress, remAddress, state;
        uint32_t txQueue, rxQueue, tr, tm_when, retrnsmt, uid, timeout, inode;

        iss >> sl >> localAddress >> remAddress >> state >> std::hex >> txQueue >> rxQueue >> std::dec
            >> tr >> tm_when >> retrnsmt >> uid >> timeout >> inode;

        // Extract source and destination IP addresses considering endianness
        auto hexToIp = [](const std::string& hexStr) -> std::string {
            std::string ip;
            for (int i = 0; i < 8; i += 2) {
                uint8_t octet = static_cast<uint8_t>(std::stoul(hexStr.substr(6 - i, 2), nullptr, 16));
                ip += std::to_string(octet);
                if (i < 6) ip += ".";
            }
            return ip;
        };

        std::string src_ip = hexToIp(localAddress.substr(0, 8));
        std::string dst_ip = hexToIp(remAddress.substr(0, 8));

        // Apply the filter to keep only entries with destination or origin of 10.0.*.2
        if (!std::regex_match(src_ip, std::regex("^10\\.0\\..*\\.2$")) &&
            !std::regex_match(dst_ip, std::regex("^10\\.0\\..*\\.2$"))) {
            continue;
        }

        // Use `ss` command to get detailed information for the socket
        std::string command = "ss -ti src " + src_ip + " dst " + dst_ip;
        FILE* pipe = popen(command.c_str(), "r");
        if (!pipe) {
            std::cerr << "Failed to run ss command" << std::endl;
            continue;
        }

        char buffer[256];
        uint64_t srtt = 0;
        uint64_t bytes_acked = 0;
        uint64_t bytes_received = 0;
        uint64_t lastsnd = 0;
        uint64_t lastrcv = 0;
        bool data_received = false;
        bool recent_activity = false;

        // Read and parse the output of the ss command
        while (fgets(buffer, sizeof(buffer), pipe) != nullptr) {
            std::string output(buffer);

            // Parse RTT
            std::size_t rtt_pos = output.find("rtt:");
            if (rtt_pos != std::string::npos) {
                std::istringstream rttStream(output.substr(rtt_pos + 4));
                std::string rttValue;
                rttStream >> rttValue;
                // Convert RTT to microseconds
                srtt = static_cast<uint64_t>(std::stod(rttValue) * 1000);
            }

            // Parse bytes_acked and bytes_received
            std::size_t bytes_acked_pos = output.find("bytes_acked:");
            if (bytes_acked_pos != std::string::npos) {
                std::istringstream ackStream(output.substr(bytes_acked_pos + 12));
                ackStream >> bytes_acked;
            }

            std::size_t bytes_received_pos = output.find("bytes_received:");
            if (bytes_received_pos != std::string::npos) {
                std::istringstream recvStream(output.substr(bytes_received_pos + 15));
                recvStream >> bytes_received;
            }

            // Parse lastsnd and lastrcv
            std::size_t lastsnd_pos = output.find("lastsnd:");
            if (lastsnd_pos != std::string::npos) {
                std::istringstream sndStream(output.substr(lastsnd_pos + 9));
                sndStream >> lastsnd;
            }

            std::size_t lastrcv_pos = output.find("lastrcv:");
            if (lastrcv_pos != std::string::npos) {
                std::istringstream rcvStream(output.substr(lastrcv_pos + 9));
                rcvStream >> lastrcv;
            }
        }
        pclose(pipe);

        // Check if data has been received recently, set a certain threshold
        data_received = (bytes_acked > BYTES_ACKS_THRESHOLD || bytes_received > BYTES_RECV_THRESHOLD);

        // Check for recent activity (within last sevaral hundred ms)
        recent_activity = (lastsnd < LAST_SEND_TIME_THRESHOLD || lastrcv < LAST_RECV_TIME_THRESHOLD);

        // Only aggregate if both conditions are met
        if (data_received && recent_activity) {
            uint64_t retransmissions = retrnsmt;
            aggregateTcpStats(connectionStats, src_ip, dst_ip, srtt, retransmissions);
        }
    }

    tcpFile.close();

    // Print aggregated stats
    std::cout << "TCP Statistics (by Connection Pair):\n";
    for (const auto& [connection, stats] : connectionStats) {
        std::cout << "Connection: " << connection.first << " -> " << connection.second
                  << ", Average RTT: " << stats.averageRtt() << " us"
                  << ", Average Retransmissions: " << stats.averageRetransmissions()
                  << "\n";
    }
}

int main() {
    std::cout << "Starting TCP statistics aggregation...\n";
    while (true) {
        readTcpStats();
        std::this_thread::sleep_for(std::chrono::seconds(5)); // Adjust the sleep duration as needed
    }
    return 0;
}
