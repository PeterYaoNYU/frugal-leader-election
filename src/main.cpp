#include "node.h"

int main(int argc, char* argv[]) {
    google::InitGoogleLogging(argv[0]);

    FLAGS_logtostderr = true;

    if (argc < 3) {
        LOG(ERROR) << "Usage: " << argv[0] << " [port] [peer1_ip:peer1_port,peer2_ip:peer2_port,...]";
        return -1;
    }

    int port = std::stoi(argv[1]);
    std::string peers = argv[2];

    Node node(port, peers);
    node.run();
    return 0;
}
