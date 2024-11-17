#include "net_latency_controller.h"

#include <iostream>

int main() {
    NetLatencyController controller;
    std::string interface = "enp0s3"; // Replace with your network interface name

    // Set a fixed delay of 100ms
    if (controller.setFixedDelay(interface, 100)) {
        std::cout << "Fixed delay set successfully." << std::endl;
    } else {
        std::cerr << "Failed to set fixed delay." << std::endl;
    }

    // // Set a normal distribution delay with mean 200ms and stddev 50ms
    if (controller.setNormalDelay(interface, 200, 50)) {
        std::cout << "Normal delay set successfully." << std::endl;
    } else {
        std::cerr << "Failed to set normal delay." << std::endl;
    }

    // // Clear any delay settings
    if (controller.clearDelay(interface)) {
        std::cout << "Delay settings cleared." << std::endl;
    } else {
        std::cerr << "Failed to clear delay settings." << std::endl;
    }

    return 0;
}
