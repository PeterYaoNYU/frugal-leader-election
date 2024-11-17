#ifndef PROCESS_CONFIG_H
#define PROCESS_CONFIG_H

#include <stdint.h>
#include <string>
#include <vector>
#include <yaml-cpp/yaml.h>
#include "process_config.h"

class ConfigParseException : public std::runtime_error {
public:
    ConfigParseException(const std::string &msg)
        : std::runtime_error(msg)
    {
    }

    static ConfigParseException missing(const std::string &field)
    {
        return ConfigParseException("Config missing field " + field);
    }
};


struct ProcessConfig {
    std::vector<std::string> peerIPs;
    std::vector<std::string> interfaces;
    int port;
    // after this many seconds, stop running the process
    int runtimeSeconds;
    int timeoutLowerBound;
    int timeoutUpperBound;
    // when this is set, the leader fails automatically
    // useful for testing purposes
    bool failureLeader;
    int maxHeartbeats;
    int delayLowerBound;
    int delayUpperBound;
    double linkLossRate;

    // simulation
    bool useSimulatedLinks;

    // a bool which tells us if we are in a check CI false positive mode. 
    bool checkFalsePositive;

    bool tcp_monitor;
    double confidenceLevel;
    int heartbeatIntervalMargin;



    template <class T> T parseField(const YAML::Node &parent, const std::string &key)
    {
        if (!parent[key]) {
            throw ConfigParseException("'" + key + "' not found, required");
        }

        try {
            return parent[key].as<T>();
        } catch (const YAML::BadConversion &e) {
            throw ConfigParseException("'" + key + "': " + e.msg + ".");
        }
    }

    template <class T> T parseField(const YAML::Node &parent, const std::string &key, const T &default_value)
    {
        if (!parent[key]) {
            return default_value;
        }

        try {
            return parent[key].as<T>();
        } catch (const YAML::BadConversion &e) {
            throw ConfigParseException("'" + key + "': " + e.msg + ".");
        }
    }

    void parseStringVector(std::vector<std::string> &list, const YAML::Node &parent, const std::string &key)
    {
        if (!parent[key]) {
            throw ConfigParseException("'" + key + "' not found");
        }

        try {
            for (uint32_t i = 0; i < parent[key].size(); i++) {
                list.push_back(parent[key][i].as<std::string>());
            }
        } catch (const YAML::BadConversion &e) {
            throw ConfigParseException("'" + key + "': " + e.msg + ".");
        }
    }

    void parseReplicaConfig(const YAML::Node &root)
    {
        const YAML::Node &replicaNode = root["replica"];
        std::string key;

        try {
            parseStringVector(peerIPs, replicaNode, "ips");
            parseStringVector(interfaces, replicaNode, "interfaces");
            port = parseField<int>(replicaNode, "port");
            runtimeSeconds = parseField<int>(replicaNode, "runtimeSeconds");

            timeoutLowerBound = parseField<int>(replicaNode, "timeoutLowerBound");
            timeoutUpperBound = parseField<int>(replicaNode, "timeoutUpperBound");
            failureLeader = parseField<bool>(replicaNode, "failureLeader");
            maxHeartbeats = parseField<int>(replicaNode, "maxHeartbeats");
            useSimulatedLinks = parseField<bool>(replicaNode, "useSimulatedLinks");
            delayLowerBound = parseField<int>(replicaNode, "delayLowerBound");
            delayUpperBound = parseField<int>(replicaNode, "delayUpperBound");
            linkLossRate = parseField<double>(replicaNode, "linkLossRate");
            checkFalsePositive = parseField<bool>(replicaNode, "checkFalsePositiveRate");
            tcp_monitor = parseField<bool>(replicaNode, "tcp_monitor");

            confidenceLevel = parseField<double>(replicaNode, "confidenceLevel");
            heartbeatIntervalMargin = parseField<int>(replicaNode, "heartbeatIntervalMargin");

        } catch (const ConfigParseException &e) {
            throw ConfigParseException("Error parsing replica " + std::string(e.what()));
        }
    }

    void parseConfig(const std::string &configFilename)
    {
        YAML::Node config;

        try {
            config = YAML::LoadFile(configFilename);
        } catch (const YAML::BadFile &e) {
            throw ConfigParseException("Error loading config file:" + e.msg + ".");
        }

        parseReplicaConfig(config);

        LOG(INFO) << "Config parsed successfully";
    }
};

#endif