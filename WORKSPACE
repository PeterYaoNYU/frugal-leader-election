workspace(name = "leader_election_workspace")

load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_archive")
load("@bazel_tools//tools/build_defs/repo:git.bzl", "git_repository", "new_git_repository")

http_archive(
    name = "rules_proto",
    sha256 = "e017528fd1c91c5a33f15493e3a398181a9e821a804eb7ff5acdd1d2d6c2b18d",
    strip_prefix = "rules_proto-4.0.0-3.20.0",
    urls = [
        "https://github.com/bazelbuild/rules_proto/archive/refs/tags/4.0.0-3.20.0.tar.gz",
    ],
)
load("@rules_proto//proto:repositories.bzl", "rules_proto_dependencies", "rules_proto_toolchains")
rules_proto_dependencies()
rules_proto_toolchains()

http_archive(
    name = "rules_foreign_cc",
    sha256 = "2a8000ce03dd9bb324bc9bb7f1f5d01debac406611f4d9fedd385192718804f0",
    strip_prefix = "rules_foreign_cc-60813d57a0e99be1a009c1a0e9627cdbe81fcd19",
    url = "https://github.com/bazelbuild/rules_foreign_cc/archive/60813d57a0e99be1a009c1a0e9627cdbe81fcd19.tar.gz",
)
load("@rules_foreign_cc//foreign_cc:repositories.bzl", "rules_foreign_cc_dependencies")
rules_foreign_cc_dependencies()

http_archive(
    name = "com_github_gflags_gflags",
    sha256 = "34af2f15cf7367513b352bdcd2493ab14ce43692d2dcd9dfc499492966c64dcf",
    strip_prefix = "gflags-2.2.2",
    urls = ["https://github.com/gflags/gflags/archive/v2.2.2.tar.gz"],
)

http_archive(
    name = "com_github_google_glog",
    sha256 = "c17d85c03ad9630006ef32c7be7c65656aba2e7e2fbfc82226b7e680c771fc88",
    strip_prefix = "glog-0.7.1",
    urls = ["https://github.com/google/glog/archive/v0.7.1.zip"],
)

new_git_repository(
    name = "com_github_enki_libev",
    commit = "93823e6ca699df195a6c7b8bfa6006ec40ee0003",
    shallow_since = "1463172876 -0700",
    build_file = "//third_party/libev:BUILD.bazel",
    remote = "https://github.com/enki/libev.git",
)

git_repository(
    name = "com_github_jbeder_yaml_cpp",
    commit = "fcbb8193b94921e058be7b563aea053531e5b2d9",  # 19-Aug-2023
    remote = "https://github.com/jbeder/yaml-cpp.git",
    shallow_since = "1692473776 -0400",
)

# Google protobuf.
git_repository(
    name = "com_google_protobuf",
    commit = "21027a27c4c2ec1000859ccbcfff46d83b16e1ed",  # 21-Apr-2022, v3.20.1
    remote = "https://github.com/protocolbuffers/protobuf",
    shallow_since = "1650589240 +0000",
)

# concurrent queue
new_git_repository(
    name = "com_github_cameron314_concurrentqueue",
    build_file = "//third_party/concurrentqueue:BUILD.bazel",
    commit = "6dd38b8a1dbaa7863aa907045f32308a56a6ff5d",
    shallow_since = "1686439287 -0400",
    remote = "https://github.com/cameron314/concurrentqueue.git",
)