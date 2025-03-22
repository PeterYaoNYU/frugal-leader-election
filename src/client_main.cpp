#include <glog/logging.h>
#include "client.h"

int main(int argc, char* argv[]) {
    // Initialize Google's logging library.
    google::InitGoogleLogging(argv[0]);
    FLAGS_logtostderr = true;

    if (argc < 4) {
        std::cerr << "Usage: " << argv[0] << " <server_ip> <server_port> <mode> [<value>]" << std::endl;
        std::cerr << "  mode: fixed OR maxcap" << std::endl;
        std::cerr << "  For fixed mode, <value> is send interval in seconds." << std::endl;
        std::cerr << "  For maxcap mode, <value> is maximum in-flight requests (integer)." << std::endl;
        return 1;
    }

    std::string server_ip = argv[1];
    int server_port = std::stoi(argv[2]);
    std::string mode_str = argv[3];
    SendMode mode;
    double fixed_interval = 0.0;
    int max_in_flight = 0;

    if (mode_str == "fixed") {
        mode = FIXED_RATE;
        if (argc < 5) {
            std::cerr << "Fixed mode requires a send interval (in seconds)." << std::endl;
            return 1;
        }
        fixed_interval = std::stod(argv[4]);
    } else if (mode_str == "maxcap") {
        mode = MAX_IN_FLIGHT;
        if (argc < 5) {
            std::cerr << "Maxcap mode requires a maximum in-flight request cap." << std::endl;
            return 1;
        }
        max_in_flight = std::stoi(argv[4]);
    } else {
        std::cerr << "Unknown mode: " << mode_str << std::endl;
        return 1;
    }

    // Use a dummy client id (could be randomized or assigned)
    int client_id = 12367;

    Client client(server_ip, server_port, mode, fixed_interval, max_in_flight, client_id);
    client.run();

    google::ShutdownGoogleLogging();
    return 0;
}