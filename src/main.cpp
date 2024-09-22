#include "node.h"
#include <gflags/gflags.h>
#include "process_config.h"

// Define flags
DEFINE_string(config, "configs/config.yaml", "The config file for the receiver");

DEFINE_uint32(replicaId, 0, "The replica id.");


int main(int argc, char* argv[]) {
    gflags::ParseCommandLineFlags(&argc, &argv, true);
    google::InitGoogleLogging(argv[0]);

    FLAGS_logtostderr = true;


    LOG(INFO) << "loading config from " << FLAGS_config;
    ProcessConfig config;
    config.parseConfig(FLAGS_config);

    Node node(config, FLAGS_replicaId);
    node.run();
    return 0;
}
