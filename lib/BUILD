cc_library(
    name = "utils",
    srcs = ["utils.cpp"],
    hdrs = ["utils.h"],
    deps = [
        "@com_github_google_glog//:glog",
    ],
    visibility = ["//visibility:public"],
)

cc_library(
    name = "tcp_stat_manager",
    srcs = ["tcp_stat_manager.cpp"],
    hdrs = [
        "tcp_stat_manager.h",
    ],
    deps = [
        "@com_github_google_glog//:glog",
    ],
    copts = [
        "-std=c++17",
        # Add other compiler options here
    ],
    visibility = ["//visibility:public"],
)

cc_library(
    name = "net_latency_controller",
    srcs = ["net_latency_controller.cpp"],
    hdrs = [
        "net_latency_controller.h",
    ],
    deps = [
        "@com_github_google_glog//:glog",
    ],
    copts = [
        "-std=c++17",
        # Add other compiler options here
    ],
    visibility = ["//visibility:public"],
)