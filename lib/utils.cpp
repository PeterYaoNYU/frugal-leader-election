#include "utils.h"

std::string get_current_time() {
    using namespace std::chrono;

    auto now = system_clock::now();
    std::time_t now_time_t = system_clock::to_time_t(now);
    auto now_ms = duration_cast<milliseconds>(now.time_since_epoch()) % 1000;

    std::tm now_tm;
    localtime_r(&now_time_t, &now_tm); // Thread-safe alternative to localtime

    std::ostringstream oss;
    oss << std::put_time(&now_tm, "%Y-%m-%d %H:%M:%S")
        << '.' << std::setfill('0') << std::setw(3) << now_ms.count();
    return oss.str();
}
