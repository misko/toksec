// Host-only supplemental plaintext HTTP load worker. Never a scored evaluator.
#include <arpa/inet.h>
#include <sys/epoll.h>
#include <sys/resource.h>
#include <sys/socket.h>
#include <unistd.h>
#include <sched.h>
#include <time.h>
#include <algorithm>
#include <array>
#include <cerrno>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

using ns = int64_t;
constexpr ns SECOND = 1000000000LL, TICK = 10000000LL;
constexpr size_t BINS = 20002;
static ns now(clockid_t clock = CLOCK_MONOTONIC) {
    timespec t{};
    if (clock_gettime(clock, &t)) throw std::runtime_error("clock_gettime");
    return ns(t.tv_sec) * SECOND + t.tv_nsec;
}
static std::string lower(std::string_view s) {
    std::string result(s);
    for (char &c : result) if (c >= 'A' && c <= 'Z') c += 'a' - 'A';
    return result;
}
static std::string_view trim(std::string_view s) {
    while (!s.empty() && (s.front() == ' ' || s.front() == '\t')) s.remove_prefix(1);
    while (!s.empty() && (s.back() == ' ' || s.back() == '\t')) s.remove_suffix(1);
    return s;
}
static bool token(unsigned char c) {
    return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
           (c >= '0' && c <= '9') || std::string_view("!#$%&'*+-.^_`|~").find(c) != std::string_view::npos;
}
static const std::array<unsigned char, 65536> EXPECTED = [] {
    std::array<unsigned char, 65536> bytes{};
    for (size_t i = 0; i < bytes.size(); ++i) bytes[i] = static_cast<unsigned char>(i);
    return bytes;
}();

// Fixed measurement deadlines are independent of dispatch time. A scheduling
// pause cannot erase deadlines by ending after the measurement window. Keep
// the v1 interior observation gate too, so changing denominators never relaxes
// its eligibility decision.
struct LagMonitor {
    ns measure, end, next_deadline, next_legacy, last_observation = -1;
    ns maximum = 0, legacy_maximum = 0;
    uint64_t samples = 0, over_20ms = 0, missed_deadlines = 0;
    uint64_t legacy_samples = 0, legacy_over_20ms = 0;
    explicit LagMonitor(ns start)
        : measure(start + SECOND), end(start + 4 * SECOND),
          next_deadline(measure), next_legacy(start + TICK) {}
    void observe(ns t) {
        if (t < last_observation) throw std::runtime_error("lag clock moved backward");
        last_observation = t;
        while (next_deadline < end && next_deadline <= t) {
            ns lag = t - next_deadline;
            maximum = std::max(maximum, lag);
            ++samples;
            over_20ms += lag > 20000000;
            missed_deadlines += lag > TICK;
            next_deadline += TICK;
        }
        if (t >= next_legacy) {
            if (t >= measure && t < end) {
                ns lag = t - next_legacy;
                legacy_maximum = std::max(legacy_maximum, lag);
                ++legacy_samples;
                legacy_over_20ms += lag > 20000000;
            }
            next_legacy = t + TICK;
        }
    }
    uint64_t expected() const { return (end - measure + TICK - 1) / TICK; }
    bool covered() const { return next_deadline >= end && samples == expected(); }
    void json(std::ostream &out) const {
        out << "\"lag_max_ms\":" << double(maximum) / 1000000
            << ",\"lag_samples\":" << samples << ",\"lag_over_20ms\":" << over_20ms
            << ",\"lag_missed_deadlines\":" << missed_deadlines
            << ",\"expected_lag_samples\":" << expected()
            << ",\"lag_coverage_valid\":" << (covered() ? "true" : "false")
            << ",\"legacy_lag_max_ms\":" << double(legacy_maximum) / 1000000
            << ",\"legacy_lag_samples\":" << legacy_samples
            << ",\"legacy_lag_over_20ms\":" << legacy_over_20ms;
    }
};

// The same incremental parser is exercised by --validate and the real worker.
// Body bytes are compared directly, without retaining a response-sized buffer.
struct Response {
    size_t expected, received = 0;
    std::string header;
    bool headers_done = false, done = false, close = false;
    explicit Response(size_t size) : expected(size) { header.reserve(512); }
    void reset() { received = 0; header.clear(); headers_done = done = close = false; }
    void parse_headers() {
        std::string_view h(header);
        auto end = h.find("\r\n");
        auto first = h.substr(0, end);
        if (end == h.npos || first.size() < 13 ||
            (first.substr(0, 9) != "HTTP/1.1 " && first.substr(0, 9) != "HTTP/1.0 ") ||
            first.substr(9, 4) != "200 ") throw std::runtime_error("status");
        for (unsigned char c : first) if (c < 32 || c == 127) throw std::runtime_error("status");
        bool http10 = first.substr(0, 8) == "HTTP/1.0";
        bool seen_length = false, keep_alive = false;
        h.remove_prefix(end + 2);
        while (h != "\r\n") {
            end = h.find("\r\n");
            if (end == h.npos || end == 0) throw std::runtime_error("headers");
            auto line = h.substr(0, end);
            auto colon = line.find(':');
            if (colon == 0 || colon == line.npos) throw std::runtime_error("headers");
            for (unsigned char c : line.substr(0, colon)) if (!token(c)) throw std::runtime_error("headers");
            auto name = lower(line.substr(0, colon));
            auto value = trim(line.substr(colon + 1));
            for (unsigned char c : value) if ((c < 32 && c != '\t') || c == 127) throw std::runtime_error("headers");
            if (name == "transfer-encoding") throw std::runtime_error("transfer_encoding");
            if (name == "content-length") {
                if (seen_length || value.empty()) throw std::runtime_error("content_length");
                seen_length = true;
                size_t length = 0;
                for (unsigned char c : value) {
                    if (c < '0' || c > '9' || length > expected) throw std::runtime_error("content_length");
                    length = length * 10 + c - '0';
                }
                if (length != expected) throw std::runtime_error("content_length");
            }
            if (name == "content-encoding" && lower(value) != "identity") throw std::runtime_error("content_encoding");
            if (name == "connection") {
                while (!value.empty()) {
                    auto comma = value.find(',');
                    auto part = lower(trim(value.substr(0, comma)));
                    close |= part == "close";
                    keep_alive |= part == "keep-alive";
                    if (comma == value.npos) break;
                    value.remove_prefix(comma + 1);
                }
            }
            h.remove_prefix(end + 2);
        }
        if (!seen_length) throw std::runtime_error("content_length");
        close |= http10 && !keep_alive;
        headers_done = true;
    }
    void feed(const char *data, size_t length) {
        size_t offset = 0;
        if (done && length) throw std::runtime_error("trailing_bytes");
        if (!headers_done) {
            while (offset < length) {
                header += data[offset++];
                if (header.size() > 65536) throw std::runtime_error("header_too_large");
                if (header.size() >= 4 && header.compare(header.size() - 4, 4, "\r\n\r\n") == 0) {
                    parse_headers();
                    break;
                }
            }
        }
        if (headers_done) {
            if (length - offset > expected - received) throw std::runtime_error("trailing_bytes");
            if (std::memcmp(data + offset, EXPECTED.data() + received, length - offset)) throw std::runtime_error("payload");
            received += length - offset;
            done = received == expected;
        }
    }
};

enum Phase { Connecting, Sending, Reading, Backoff, Stopped };
struct Client {
    int fd = -1;
    Phase phase = Backoff;
    size_t sent = 0;
    ns started = 0, deadline = 0, retry = 0;
    bool measured = false;
    Response response;
    explicit Client(size_t size) : response(size) {}
};

struct Worker {
    size_t count, size;
    int cpu, port, ep = -1;
    bool persistent;
    ns start, measure, end, next_tick, cpu_start, cpu_measure = -1, cpu_end = -1;
    LagMonitor lag;
    std::string request;
    std::vector<Client> clients;
    std::array<uint64_t, BINS> histogram{};
    uint64_t attempts = 0, successes = 0, completed = 0, failures = 0, timeouts = 0;
    uint64_t warmup_failures = 0, inflight = 0, peak = 0;
    std::map<std::string, uint64_t> errors;
    Worker(size_t n, size_t bytes, int core, int destination, bool reuse, ns begin, std::string raw)
        : count(n), size(bytes), cpu(core), port(destination), persistent(reuse),
          start(begin), measure(begin + SECOND), end(begin + 4 * SECOND), next_tick(begin + TICK),
          lag(begin), request(std::move(raw)) {
        clients.reserve(n);
        for (size_t i = 0; i < n; ++i) clients.emplace_back(size);
    }
    ~Worker() { for (auto &c : clients) if (c.fd >= 0) ::close(c.fd); if (ep >= 0) ::close(ep); }
    void disconnect(Client &c) {
        if (c.fd >= 0) { epoll_ctl(ep, EPOLL_CTL_DEL, c.fd, nullptr); ::close(c.fd); c.fd = -1; }
    }
    void interest(size_t index, bool add = false) {
        auto &c = clients[index];
        epoll_event event{};
        event.events = (c.phase == Reading ? EPOLLIN : EPOLLOUT) | EPOLLRDHUP;
        event.data.u32 = index;
        if (epoll_ctl(ep, add ? EPOLL_CTL_ADD : EPOLL_CTL_MOD, c.fd, &event))
            throw std::runtime_error("epoll_ctl");
    }
    void fail(size_t index, const std::string &error, ns t) {
        auto &c = clients[index];
        if (c.measured) { ++failures; --inflight; timeouts += error == "timeout"; ++errors[error]; }
        else ++warmup_failures;
        disconnect(c);
        c.phase = t >= end ? Stopped : Backoff;
        c.retry = t + 1000000;
    }
    void begin(size_t index, ns t) {
        auto &c = clients[index];
        if (t >= end) { disconnect(c); c.phase = Stopped; return; }
        c.started = t; c.deadline = t + 2 * SECOND; c.measured = t >= measure;
        c.sent = 0; c.response.reset();
        if (c.measured) { ++attempts; peak = std::max(peak, ++inflight); }
        if (c.fd < 0) {
            c.fd = socket(AF_INET, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
            if (c.fd < 0) { fail(index, "socket", t); return; }
            sockaddr_in address{};
            address.sin_family = AF_INET; address.sin_port = htons(port); address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
            int result = connect(c.fd, reinterpret_cast<sockaddr *>(&address), sizeof(address));
            if (result && errno != EINPROGRESS) { fail(index, "connect", t); return; }
            c.phase = result ? Connecting : Sending;
            interest(index, true);
        } else { c.phase = Sending; interest(index); }
    }
    void event(size_t index, uint32_t flags) {
        auto &c = clients[index];
        if (c.fd < 0 || c.phase == Stopped || c.phase == Backoff) return;
        ns t = now();
        if (t >= c.deadline) { fail(index, "timeout", t); return; }
        if (c.phase == Connecting) {
            int error = 0; socklen_t length = sizeof(error);
            if (getsockopt(c.fd, SOL_SOCKET, SO_ERROR, &error, &length) || error) { fail(index, "connect", t); return; }
            c.phase = Sending;
        }
        if (c.phase == Sending) {
            while (c.sent < request.size()) {
                ssize_t n = send(c.fd, request.data() + c.sent, request.size() - c.sent, MSG_NOSIGNAL);
                if (n > 0) c.sent += n;
                else if (n < 0 && errno == EINTR) continue;
                else if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) return;
                else { fail(index, "send", now()); return; }
            }
            c.phase = Reading; interest(index);
        }
        if (c.phase == Reading) {
            char buffer[65536];
            for (;;) {
                ssize_t n = recv(c.fd, buffer, sizeof(buffer), 0);
                if (n > 0) {
                    try { c.response.feed(buffer, n); }
                    catch (const std::exception &error) { fail(index, error.what(), now()); return; }
                    if (c.response.done) {
                        t = now();
                        if (t >= c.deadline) { fail(index, "timeout", t); return; }
                        // Reject unsolicited bytes already queued beyond Content-Length.
                        char extra;
                        ssize_t peek = recv(c.fd, &extra, 1, MSG_PEEK | MSG_DONTWAIT);
                        if (peek > 0) { fail(index, "trailing_bytes", t); return; }
                        if (c.measured) {
                            ++successes; --inflight;
                            size_t bin = std::min<size_t>(BINS - 1, (t - c.started + 99999) / 100000);
                            ++histogram[bin];
                            if (t <= end) ++completed;
                        }
                        if (!persistent || c.response.close || peek == 0 || (flags & (EPOLLRDHUP | EPOLLHUP))) disconnect(c);
                        begin(index, t);
                        return; // At most one completed request per readiness dispatch.
                    }
                } else if (n == 0) { fail(index, "truncated", now()); return; }
                else if (errno == EINTR) continue;
                else if (errno == EAGAIN || errno == EWOULDBLOCK) return;
                else { fail(index, "recv", now()); return; }
            }
        }
    }
    void run() {
        cpu_set_t set; CPU_ZERO(&set); CPU_SET(cpu, &set);
        if (sched_setaffinity(0, sizeof(set), &set)) throw std::runtime_error("sched_setaffinity");
        rlimit limit{}; getrlimit(RLIMIT_NOFILE, &limit);
        limit.rlim_cur = std::min<rlim_t>(limit.rlim_max, std::max<rlim_t>(limit.rlim_cur, 16384));
        if (limit.rlim_cur < 16384 || setrlimit(RLIMIT_NOFILE, &limit)) throw std::runtime_error("descriptor limit");
        ep = epoll_create1(EPOLL_CLOEXEC); if (ep < 0) throw std::runtime_error("epoll_create1");
        if (now() >= start) throw std::runtime_error("worker missed synchronized start");
        timespec target{start / SECOND, start % SECOND};
        while (clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &target, nullptr) == EINTR) {}
        cpu_start = now(CLOCK_PROCESS_CPUTIME_ID);
        for (size_t i = 0; i < count; ++i) begin(i, now());
        epoll_event events[256];
        while (true) {
            ns t = now();
            lag.observe(t);
            if (cpu_measure < 0 && t >= measure) cpu_measure = now(CLOCK_PROCESS_CPUTIME_ID);
            if (cpu_end < 0 && t >= end) cpu_end = now(CLOCK_PROCESS_CPUTIME_ID);
            if (t >= next_tick) {
                next_tick = t + TICK;
                bool active = false;
                for (size_t i = 0; i < count; ++i) {
                    auto &c = clients[i];
                    if (c.phase == Backoff && t >= c.retry) begin(i, t);
                    else if (c.phase != Stopped && c.phase != Backoff && t >= c.deadline) fail(i, "timeout", t);
                    active |= c.phase != Stopped;
                }
                if (t >= end && !active) break;
            }
            if (t > end + 2 * SECOND + SECOND) throw std::runtime_error("worker drain deadline");
            int n = epoll_wait(ep, events, 256, 1);
            if (n < 0) { if (errno == EINTR) continue; throw std::runtime_error("epoll_wait"); }
            for (int i = 0; i < n; ++i) event(events[i].data.u32, events[i].events);
        }
        ns finish = now();
        ns cpu_total = now(CLOCK_PROCESS_CPUTIME_ID) - cpu_start;
        rusage usage{}; getrusage(RUSAGE_SELF, &usage);
        double elapsed = double(finish - start) / SECOND;
        double measured_cpu = double(cpu_end - cpu_measure) / SECOND;
        std::cout << "{\"attempts\":" << attempts << ",\"successes\":" << successes
                  << ",\"completed_in_window\":" << completed << ",\"failures\":" << failures
                  << ",\"timeouts\":" << timeouts << ",\"warmup_failures\":" << warmup_failures
                  << ",\"payload_bytes\":" << completed * size << ",\"clients_started\":" << count
                  << ",\"peak_inflight\":" << peak << ",\"cpu_seconds\":" << double(cpu_total) / SECOND
                  << ",\"measurement_cpu_seconds\":" << measured_cpu
                  << ",\"measurement_cpu_utilization\":" << measured_cpu / 3
                  << ",\"elapsed_seconds\":" << elapsed << ",\"rss_kib\":" << usage.ru_maxrss << ',';
        lag.json(std::cout);
        std::cout << ",\"errors\":{";
        bool first = true;
        for (const auto &[key, value] : errors) { if (!first) std::cout << ','; first = false; std::cout << '"' << key << "\":" << value; }
        std::cout << "},\"histogram\":[";
        for (size_t i = 0; i < BINS; ++i) { if (i) std::cout << ','; std::cout << histogram[i]; }
        std::cout << "]}\n";
    }
};

int main(int argc, char **argv) {
    try {
        std::map<std::string, std::string> args;
        for (int i = 1; i < argc; i += 2) {
            if (i + 1 >= argc || !args.emplace(argv[i], argv[i + 1]).second) throw std::runtime_error("arguments");
        }
        size_t size = std::stoull(args.at("--size"));
        if (size != 4096 && size != 65536) throw std::runtime_error("size");
        if (args.count("--lag-probe")) {
            LagMonitor monitor(0);
            std::istringstream input(args.at("--lag-probe"));
            std::string value;
            while (std::getline(input, value, ',')) monitor.observe(std::stoll(value));
            std::cout << '{'; monitor.json(std::cout); std::cout << "}\n";
        } else if (args.count("--validate")) {
            Response parser(size);
            size_t chunk = std::stoull(args.at("--validate"));
            if (!chunk || chunk > 65536) throw std::runtime_error("chunk");
            std::vector<char> data(chunk);
            while (std::cin) { std::cin.read(data.data(), data.size()); parser.feed(data.data(), std::cin.gcount()); }
            if (!parser.done) throw std::runtime_error("truncated");
            std::cout << "{\"passed\":true,\"connection_close\":" << (parser.close ? "true" : "false") << "}\n";
        } else {
            std::ifstream input(args.at("--request"), std::ios::binary);
            if (!input) throw std::runtime_error("request file");
            std::string raw((std::istreambuf_iterator<char>(input)), {});
            if (raw.empty() || raw.size() > 65536) throw std::runtime_error("request size");
            size_t count = std::stoull(args.at("--clients"));
            int cpu = std::stoi(args.at("--cpu")), port = std::stoi(args.at("--port"));
            if ((count != 64 && count != 1024) || cpu < 0 || cpu >= CPU_SETSIZE || port < 1 || port > 65535) throw std::runtime_error("worker parameters");
            auto reuse = args.at("--persistent");
            if (reuse != "0" && reuse != "1") throw std::runtime_error("persistent");
            Worker(count, size, cpu, port, reuse == "1", std::stoll(args.at("--start-ns")), std::move(raw)).run();
        }
        return 0;
    } catch (const std::exception &error) { std::cerr << error.what() << '\n'; return 1; }
}
