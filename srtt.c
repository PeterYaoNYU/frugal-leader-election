// srtt_tracker.c
#include <uapi/linux/ptrace.h>
#include <net/sock.h>
#include <bcc/proto.h>

struct srtt_key_t {
    u32 daddr; // Destination IP address
};

struct srtt_val_t {
    u32 srtt;  // Smoothed RTT in microseconds
};

// Define an eBPF hash map that will store the srtt for each destination.
BPF_HASH(srtt_map, struct srtt_key_t, struct srtt_val_t);

int track_srtt(struct pt_regs *ctx, struct sock *sk) {
    u16 family = sk->__sk_common.skc_family;
    struct srtt_key_t key = {};
    struct srtt_val_t value = {};
    u32 srtt = 0;

    // Only process IPv4 family
    if (family == AF_INET) {
        key.daddr = sk->__sk_common.skc_daddr;

        // Manually read the srtt_us field using the known offset (1672 bytes)
        bpf_probe_read(&srtt, sizeof(srtt), ((char *)sk + 1672));

        // Convert from fixed-point (shifted by 3) to microseconds
        value.srtt = srtt >> 3;

        // Store the value in the map
        srtt_map.update(&key, &value);
    }

    return 0;
}
