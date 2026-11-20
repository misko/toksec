// Trusted, closed-loop benchmark client for persistent plaintext gateway workloads.
// Python supplies the exact HTTP request and expected payload used by the reference worker.
#include <algorithm>
#include <array>
#include <cerrno>
#include <charconv>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

#include <arpa/inet.h>
#include <netinet/tcp.h>
#include <sys/epoll.h>
#include <sys/resource.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

using Time = int64_t;
constexpr Time ms = 1000000;
constexpr Time second = 1000 * ms;
constexpr size_t max_header = 65536;
constexpr size_t bins = 20002;

Time clock_ns(clockid_t clock) {
    timespec value{};
    if (clock_gettime(clock, &value) != 0) throw std::runtime_error("clock_gettime");
    return Time(value.tv_sec) * second + value.tv_nsec;
}

enum class Phase { retry, connect, write, response, done };

struct Client {
    int fd = -1;
    Phase phase = Phase::retry;
    Time started = 0;
    Time retry_at = 0;
    size_t sent = 0;
    size_t body_seen = 0;
    bool received_header = false;
    bool close = false;
    bool writing = true;
    std::string header_fragment;
};

struct Metrics {
    int64_t attempts = 0, successes = 0, completed = 0, failures = 0, timeouts = 0;
    int64_t bytes = 0, all_successes = 0, active = 0, peak = 0;
    Time worst_lag = 0;
    int64_t lag_samples = 0, lag_over_20ms = 0;
    std::array<int64_t, bins> histogram{};
    std::map<std::string, int64_t> failure_classes;

    void report(int clients, Time cpu, Time elapsed) const {
        rusage usage{};
        if (getrusage(RUSAGE_SELF, &usage) != 0) throw std::runtime_error("getrusage");
        std::cout << "{\"attempts\":" << attempts << ",\"successes\":" << successes
                  << ",\"completed_in_window\":" << completed << ",\"failures\":" << failures
                  << ",\"timeouts\":" << timeouts << ",\"payload_bytes\":" << bytes
                  << ",\"all_successes\":" << all_successes << ",\"peak_inflight\":" << peak
                  << ",\"clients_started\":" << clients << ",\"lag_samples\":" << lag_samples
                  << ",\"lag_over_20ms\":" << lag_over_20ms << ",\"lag_max_ms\":" << double(worst_lag) / ms
                  << ",\"elapsed_seconds\":" << double(elapsed) / second
                  << ",\"cpu_seconds\":" << double(cpu) / second << ",\"rss_kib\":" << usage.ru_maxrss
                  << ",\"failure_classes\":{";
        bool first = true;
        for (const auto &[name, count] : failure_classes) {
            std::cout << (first ? "" : ",") << '"' << name << "\":" << count;
            first = false;
        }
        std::cout << "},\"histogram\":[";
        for (size_t i = 0; i < bins; ++i) std::cout << (i ? "," : "") << histogram[i];
        std::cout << "]}\n";
    }
};

bool equal_header(std::string_view a, std::string_view lower) {
    return a.size() == lower.size() && std::equal(a.begin(), a.end(), lower.begin(),
        [](unsigned char c, unsigned char d) { return (c >= 'A' && c <= 'Z' ? c + ('a' - 'A') : c) == d; });
}

bool decimal(std::string_view value, int &out) {
    auto result = std::from_chars(value.data(), value.data() + value.size(), out);
    return result.ec == std::errc{} && result.ptr == value.data() + value.size();
}

std::string check_headers(std::string_view lines, size_t size, bool &close) {
    auto sep = lines.find("\r\n");
    auto status_line = lines.substr(0, sep);
    auto space = status_line.find(' ');
    int status = 0;
    if (space == std::string_view::npos) return "protocol";
    auto code = status_line.substr(space + 1);
    if (!decimal(code.substr(0, code.find(' ')), status) || status < 100 || status >= 600) return "protocol";
    if (status != 200) return "http_" + std::to_string(status);
    bool length_seen = false;
    while (sep != std::string_view::npos) {
        lines.remove_prefix(sep + 2);
        sep = lines.find("\r\n");
        auto field = lines.substr(0, sep);
        auto colon = field.find(':');
        if (colon == std::string_view::npos) return "protocol";
        auto name = field.substr(0, colon);
        auto value = field.substr(colon + 1);
        while (!value.empty() && (value.front() == ' ' || value.front() == '\t')) value.remove_prefix(1);
        while (!value.empty() && (value.back() == ' ' || value.back() == '\t')) value.remove_suffix(1);
        if (equal_header(name, "transfer-encoding")) return "protocol";
        if (equal_header(name, "content-length")) {
            int count = -1;
            if (length_seen || !decimal(value, count) || count < 0) return "protocol";
            if (static_cast<size_t>(count) != size) return "body_mismatch";
            length_seen = true;
        }
        if (equal_header(name, "connection")) close = equal_header(value, "close");
    }
    return length_seen ? "" : "protocol";
}

class Worker {
public:
    Worker(int count, int port, Time start, Time warmup, Time duration, Time timeout,
           std::string request, std::string expected)
        : clients(count), start(start), measure(start + warmup), end(measure + duration), timeout(timeout),
          request(std::move(request)), expected(std::move(expected)), unfinished(count) {
        epoll = epoll_create1(EPOLL_CLOEXEC);
        if (epoll < 0) throw std::runtime_error("epoll_create1");
        address.sin_family = AF_INET;
        address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
        address.sin_port = htons(port);
    }

    void run() {
        Time cpu_start = clock_ns(CLOCK_PROCESS_CPUTIME_ID);
        timespec at{start / second, start % second};
        while (clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &at, nullptr) == EINTR) {}
        Time lag_sample = clock_ns(CLOCK_MONOTONIC) + 10 * ms;
        std::array<epoll_event, 256> events;
        while (unfinished) {
            Time now = clock_ns(CLOCK_MONOTONIC);
            if (now >= lag_sample && lag_sample - 10 * ms < end) {
                if (now >= measure) {
                    Time lag = now - lag_sample;
                    metrics.lag_samples++;
                    metrics.lag_over_20ms += lag > 20 * ms;
                    metrics.worst_lag = std::max(lag, metrics.worst_lag);
                }
                lag_sample = now + 10 * ms;
            }
            Time wake = now < end ? std::min(end, lag_sample) : now + timeout;
            for (auto &client : clients) {
                if (client.phase == Phase::retry && now >= client.retry_at) begin(client);
                if (client.phase == Phase::retry) {
                    wake = std::min(wake, client.retry_at);
                } else if (client.phase != Phase::done) {
                    if (now >= client.started + timeout) {
                        fail(client, timeout_reason(client), now);
                        wake = std::min(wake, client.retry_at);
                    } else {
                        wake = std::min(wake, client.started + timeout);
                    }
                }
            }
            if (!unfinished) break;
            int wait_ms = int(std::max<Time>(0, wake - clock_ns(CLOCK_MONOTONIC) + ms - 1) / ms);
            int n = epoll_wait(epoll, events.data(), int(events.size()), wait_ms);
            if (n < 0 && errno != EINTR) throw std::runtime_error("epoll_wait");
            for (int i = 0; i < n; ++i) {
                Client &c = clients.at(events[i].data.u32);
                now = clock_ns(CLOCK_MONOTONIC);
                if (c.phase == Phase::retry || c.phase == Phase::done) continue;
                if (now >= c.started + timeout) { fail(c, timeout_reason(c), now); continue; }
                if (c.phase == Phase::connect) {
                    int error = 0;
                    socklen_t len = sizeof(error);
                    if (getsockopt(c.fd, SOL_SOCKET, SO_ERROR, &error, &len) < 0 || error) {
                        fail(c, "connection_connect", now);
                        continue;
                    }
                    c.phase = Phase::write;
                }
                if (c.phase == Phase::write) write_request(c);
                else if (c.phase == Phase::response) read_response(c);
            }
        }
        metrics.report(int(clients.size()), clock_ns(CLOCK_PROCESS_CPUTIME_ID) - cpu_start,
                       clock_ns(CLOCK_MONOTONIC) - start);
    }

private:
    std::vector<Client> clients;
    const Time start, measure, end, timeout;
    const std::string request, expected;
    size_t unfinished;
    int epoll;
    sockaddr_in address{};
    Metrics metrics;

    static const char *timeout_reason(const Client &c) {
        if (c.phase == Phase::connect) return "timeout_connect";
        if (c.phase == Phase::write) return "timeout_write";
        return "timeout_response";
    }

    void watch(Client &c, bool write, int op = EPOLL_CTL_MOD) {
        if (op == EPOLL_CTL_MOD && c.writing == write) return;
        epoll_event e{};
        e.events = write ? EPOLLOUT : EPOLLIN;
        e.data.u32 = static_cast<uint32_t>(&c - clients.data());
        if (epoll_ctl(epoll, op, c.fd, &e) < 0) throw std::runtime_error("epoll_ctl");
        c.writing = write;
    }

    static void disconnect(Client &c) {
        if (c.fd >= 0) ::close(c.fd);
        c.fd = -1;
    }

    void begin(Client &c) {
        c.started = clock_ns(CLOCK_MONOTONIC);
        if (c.started >= end) {
            disconnect(c);
            c.phase = Phase::done;
            unfinished--;
            return;
        }
        if (c.started >= measure) {
            metrics.attempts++;
            metrics.peak = std::max(metrics.peak, ++metrics.active);
        }
        c.sent = c.body_seen = 0;
        c.received_header = c.close = false;
        c.header_fragment.clear();
        if (c.fd >= 0) {
            c.phase = Phase::write;
            write_request(c);
            return;
        }
        c.phase = Phase::connect;
        c.fd = socket(AF_INET, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
        int one = 1;
        if (c.fd < 0 || setsockopt(c.fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof(one)) < 0 ||
            (connect(c.fd, reinterpret_cast<const sockaddr*>(&address), sizeof(address)) < 0 && errno != EINPROGRESS)) {
            fail(c, "connection_connect", c.started);
            return;
        }
        watch(c, true, EPOLL_CTL_ADD);
    }

    void fail(Client &c, const std::string &reason, Time now) {
        if (c.started >= measure) {
            metrics.active--;
            metrics.failures++;
            metrics.failure_classes[reason]++;
            if (reason.rfind("timeout_", 0) == 0) metrics.timeouts++;
        }
        disconnect(c);
        c.phase = Phase::retry;
        c.retry_at = now + ms;
    }

    void write_request(Client &c) {
        while (c.sent < request.size()) {
            ssize_t n = send(c.fd, request.data() + c.sent, request.size() - c.sent, MSG_NOSIGNAL);
            if (n < 0 && errno == EINTR) continue;
            if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) { watch(c, true); return; }
            if (n <= 0) { fail(c, "connection_write", clock_ns(CLOCK_MONOTONIC)); return; }
            c.sent += n;
        }
        c.phase = Phase::response;
        watch(c, false);
    }

    std::string consume(Client &c, std::string_view data) {
        if (!c.received_header) {
            if (!c.header_fragment.empty()) {
                c.header_fragment.append(data);
                data = c.header_fragment;
            }
            auto sep = data.find("\r\n\r\n");
            if (sep == std::string_view::npos) {
                if (data.size() >= max_header) return "protocol";
                if (c.header_fragment.empty()) c.header_fragment.assign(data);
                return "";
            }
            if (sep + 4 > max_header) return "protocol";
            auto error = check_headers(data.substr(0, sep), expected.size(), c.close);
            if (!error.empty()) return error;
            data.remove_prefix(sep + 4);
            c.received_header = true;
        }
        if (data.size() > expected.size() - c.body_seen ||
            std::memcmp(data.data(), expected.data() + c.body_seen, data.size()) != 0) return "body_mismatch";
        c.body_seen += data.size();
        return "";
    }

    void read_response(Client &c) {
        char buf[64 * 1024];
        for (;;) {
            ssize_t n = recv(c.fd, buf, sizeof(buf), 0);
            if (n < 0 && errno == EINTR) continue;
            if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) return;
            if (n <= 0) { fail(c, "connection_response", clock_ns(CLOCK_MONOTONIC)); return; }
            auto reason = consume(c, std::string_view(buf, n));
            Time now = clock_ns(CLOCK_MONOTONIC);
            if (now >= c.started + timeout) { fail(c, "timeout_response", now); return; }
            if (!reason.empty()) { fail(c, reason, now); return; }
            if (!c.received_header || c.body_seen != expected.size()) continue;
            metrics.all_successes++;
            if (c.started >= measure) {
                metrics.successes++;
                metrics.active--;
                size_t bin = static_cast<size_t>((now - c.started + 99999) / 100000);
                metrics.histogram[std::min(bin, bins - 1)]++;
                if (now <= end) { metrics.completed++; metrics.bytes += expected.size(); }
            }
            if (c.close) disconnect(c);
            begin(c);
            return;
        }
    }
};

int main(int argc, char **argv) {
    try {
        if (argc != 7) throw std::runtime_error("expected clients, port, start, warmup, measure, timeout (nanoseconds)");
        int clients = std::stoi(argv[1]), port = std::stoi(argv[2]);
        Time start = std::stoll(argv[3]), warmup = std::stoll(argv[4]);
        Time duration = std::stoll(argv[5]), timeout = std::stoll(argv[6]);
        if (clients < 1 || clients > 1024 || port < 1 || port > 65535 || warmup < 0 || duration <= 0 || timeout <= 0)
            throw std::runtime_error("invalid worker configuration");
        size_t req_size, body_size;
        if (!(std::cin >> req_size >> body_size) || std::cin.get() != '\n' || req_size > 131072 || body_size > 65536)
            throw std::runtime_error("invalid request or payload size");
        std::string raw(req_size, '\0'), expected(body_size, '\0');
        if (!std::cin.read(raw.data(), raw.size()) || !std::cin.read(expected.data(), expected.size()))
            throw std::runtime_error("truncated worker input");
        Worker(clients, port, start, warmup, duration, timeout, std::move(raw), std::move(expected)).run();
        return 0;
    } catch (const std::exception &e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
