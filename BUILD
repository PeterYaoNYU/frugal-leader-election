cc_library(
    name = "node_lib",
    srcs = [
        "src/node.cpp",
    ],
    hdrs = [
        "src/node.h",   
        "src/process_config.h"
    ],
    includes = [
        "src",  # Include the "src" directory so node.h can be found.
    ],
    deps = [
        "@com_github_google_glog//:glog",
        "@com_github_enki_libev//:libev",
        "@com_github_jbeder_yaml_cpp//:yaml-cpp",
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
