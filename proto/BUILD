# proto/BUILD
load("@rules_proto//proto:defs.bzl", "proto_library")


proto_library(
    name = "raft_leader_election_proto",
    srcs = ["raft_leader_election.proto"],
    visibility = ["//visibility:public"],
)

cc_proto_library(
    name = "raft_leader_election_cc_proto",
    deps = [":raft_leader_election_proto"],
    visibility = ["//visibility:public"],
)

proto_library(
    name = "raft_client_proto",
    srcs = ["raft_client.proto"],
    visibility = ["//visibility:public"],
)

cc_proto_library(
    name = "raft_client_cc_proto",
    deps = [":raft_client_proto"],
    visibility = ["//visibility:public"],
)
