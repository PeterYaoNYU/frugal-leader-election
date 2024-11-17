#include "net_latency_controller.h"
#include <iostream>
#include <sstream>
#include <cstdlib>

bool NetLatencyController::setFixedDelay(const std::string& interface, int delay_ms) {
    if (delay_ms < 0) {
        std::cerr << "Delay must be non-negative." << std::endl;
        return false;
    }

    clearDelay(interface);

    std::ostringstream cmd;
    cmd << "tc qdisc add dev " << interface << " root netem delay " << delay_ms << "ms";

    return executeCommand(cmd.str());
}

bool NetLatencyController::setNormalDelay(const std::string& interface, int mean_ms, int stddev_ms) {
    if (mean_ms < 0 || stddev_ms < 0) {
        std::cerr << "Mean and standard deviation must be non-negative." << std::endl;
        return false;
    }

    clearDelay(interface);

    std::ostringstream cmd;
    cmd << "tc qdisc add dev " << interface << " root netem delay " << mean_ms
        << "ms " << stddev_ms << "ms distribution normal";

    return executeCommand(cmd.str());
}

bool NetLatencyController::clearDelay(const std::string& interface) {
    std::ostringstream cmd;
    cmd << "tc qdisc del dev " << interface << " root";

    return executeCommand(cmd.str());
}

bool NetLatencyController::executeCommand(const std::string& command) {
    // Log the command for debugging purposes (optional)
    // std::cout << "Executing command: " << command << std::endl;

    int result = system(command.c_str());
    if (result != 0) {
        std::cerr << "Command failed with exit code " << result << ": " << command << std::endl;
        return false;
    }
    return true;
}
