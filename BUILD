cc_library(
    name = "node_lib",
    srcs = [
        "src/node.cpp",
        "src/raftLog.cpp",
    ],
    hdrs = [
        "src/node.h",   
        "src/process_config.h",
        "src/raftLog.h",
        "src/threadPool.h",
    ],
    includes = [
        "src",  # Include the "src" directory so node.h can be found.
    ],
    deps = [
        "@com_github_google_glog//:glog",
        "@com_github_enki_libev//:libev",
        "@com_github_jbeder_yaml_cpp//:yaml-cpp",
        "@com_github_cameron314_concurrentqueue//:concurrentqueue",
        "@com_github_cameron314_concurrentqueue//:blockingconcurrentqueue",
        "//proto:raft_leader_election_cc_proto",
        "//proto:raft_client_cc_proto",
        "//lib:utils",  
        "//lib:tcp_stat_manager",
        "//lib:net_latency_controller",
    ],
    visibility = ["//visibility:public"],  # Make this library available to other rules.
    copts = ["-std=c++17"], 
)

cc_binary(
    name = "leader_election",
    srcs = [
        "src/main.cpp",
    ],
    deps = [
        ":node_lib",  # Depend on the node_lib library.
    ],
    linkopts = [
        "-pthread",
    ],
    copts = ["-std=c++17"],  
)

cc_library(
    name = "client_lib",
    srcs = [
        "src/client.cpp",
    ],
    hdrs = [
        "src/client.h",
    ],
    deps = [
        "@com_github_google_glog//:glog",
        "@com_github_enki_libev//:libev",
        "@com_github_jbeder_yaml_cpp//:yaml-cpp",
        "@com_github_cameron314_concurrentqueue//:concurrentqueue",
        "//proto:raft_client_cc_proto",
        "//proto:raft_leader_election_cc_proto",
        "//lib:utils",  
    ],
    copts = ["-std=c++17"],
)

cc_binary(
    name = "client",
    srcs = [
        "src/client_main.cpp",
    ],
    deps = [
        ":client_lib",
    ],
    linkopts = [
        "-pthread",
    ],
    copts = ["-std=c++17"],
)