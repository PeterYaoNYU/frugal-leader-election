#ifndef NETLATENCYCONTROLLER_H
#define NETLATENCYCONTROLLER_H

#include <string>

class NetLatencyController {
public:
    // Sets a fixed delay on the specified network interface
    bool setFixedDelay(const std::string& interface, int delay_ms);

    // Sets a normal distribution delay on the specified network interface
    bool setNormalDelay(const std::string& interface, int mean_ms, int stddev_ms);

    // Clears any delay settings on the specified network interface
    bool clearDelay(const std::string& interface);

private:
    // Helper function to execute system commands safely
    bool executeCommand(const std::string& command);
};

#endif // NETLATENCYCONTROLLER_H
