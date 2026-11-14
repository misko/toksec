#include <algorithm>
#include <array>
#include <cerrno>
#include <charconv>
#include <chrono>
#include <csignal>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <limits>
#include <memory>
#include <string>
#include <string_view>
#include <unordered_map>
#include <vector>
#include <arpa/inet.h>
#include <fcntl.h>
#include <netinet/tcp.h>
#include <sys/epoll.h>
#include <sys/sendfile.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/uio.h>
#include <unistd.h>

using Clock = std::chrono::steady_clock;
using Millis = std::chrono::milliseconds;
static uint64_t now_ms() {
    return std::chrono::duration_cast<Millis>(Clock::now().time_since_epoch()).count();
}
static std::string_view trim(std::string_view v) {
    while (!v.empty() && (v.front() == ' ' || v.front() == '\t' || v.front() == '\r')) v.remove_prefix(1);
    while (!v.empty() && (v.back() == ' ' || v.back() == '\t' || v.back() == '\r')) v.remove_suffix(1);
    return v;
}
static bool utf8(std::string_view s) {
    for (size_t i = 0; i < s.size();) {
        unsigned char a = s[i++];
        if (a < 0x80) continue;
        unsigned n, cp, low;
        if (a >= 0xc2 && a <= 0xdf) { n = 1; cp = a & 31; low = 0x80; }
        else if (a >= 0xe0 && a <= 0xef) { n = 2; cp = a & 15; low = 0x800; }
        else if (a >= 0xf0 && a <= 0xf4) { n = 3; cp = a & 7; low = 0x10000; }
        else return false;
        if (s.size() - i < n) return false;
        for (unsigned j = 0; j < n; ++j) {
            unsigned char b = s[i++];
            if ((b & 0xc0) != 0x80) return false;
            cp = (cp << 6) | (b & 63);
        }
        if (cp < low || cp > 0x10ffff || (cp >= 0xd800 && cp <= 0xdfff)) return false;
    }
    return true;
}
static bool decimal(std::string_view s, uint64_t& out) {
    if (s.empty()) return false;
    out = 0;
    for (unsigned char c : s) {
        if (c < '0' || c > '9' || out > (std::numeric_limits<uint64_t>::max() - (c - '0')) / 10) return false;
        out = out * 10 + c - '0';
    }
    return true;
}
static bool equal_ci(std::string_view a, std::string_view b) {
    if (a.size() != b.size()) return false;
    for (size_t i = 0; i < a.size(); ++i) {
        unsigned char c = a[i];
        if (c >= 'A' && c <= 'Z') c += 'a' - 'A';
        if (c != static_cast<unsigned char>(b[i])) return false;
    }
    return true;
}
static bool token_char(unsigned char c) {
    return (c >= '0' && c <= '9') || (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
        std::string_view("!#$%&'*+-.^_`|~").find(c) != std::string_view::npos;
}

struct Config {
    std::string root;
    sockaddr_storage address{};
    socklen_t address_length = 0;
    uint64_t max_connections = 0, header_bytes = 0, header_timeout_ms = 0;
    uint64_t idle_timeout_ms = 0, write_timeout_ms = 0, max_requests = 0, pipeline_depth = 0;
};
static bool configuration(const char* path, Config& c) {
    std::ifstream file(path, std::ios::binary);
    if (!file) return false;
    std::string all((std::istreambuf_iterator<char>(file)), {});
    if (!utf8(all) || all.find('\0') != std::string::npos) return false;
    std::unordered_map<std::string, std::string> values;
    size_t position = 0;
    while (position < all.size()) {
        size_t end = all.find('\n', position);
        if (end == std::string::npos) end = all.size();
        auto line = trim(std::string_view(all).substr(position, end - position));
        position = end + 1;
        if (line.empty() || line.front() == '#') continue;
        size_t equals = line.find('=');
        if (equals == std::string_view::npos) return false;
        auto key = trim(line.substr(0, equals));
        auto value = trim(line.substr(equals + 1));
        if (key.empty() || value.empty() || !values.emplace(std::string(key), std::string(value)).second) return false;
    }
    const std::array<std::string_view, 9> keys = {"listen", "root", "max_connections", "header_bytes", "header_timeout_ms",
        "idle_timeout_ms", "write_timeout_ms", "max_requests", "pipeline_depth"};
    if (values.size() != keys.size()) return false;
    for (auto key : keys) if (!values.count(std::string(key))) return false;
    c.root = values["root"];
    if (c.root.empty() || c.root[0] != '/') return false;
    std::array<uint64_t*, 7> limits = {&c.max_connections, &c.header_bytes, &c.header_timeout_ms,
        &c.idle_timeout_ms, &c.write_timeout_ms, &c.max_requests, &c.pipeline_depth};
    for (size_t i = 0; i < limits.size(); ++i) {
        if (!decimal(values[std::string(keys[i + 2])], *limits[i]) || !*limits[i] ||
            *limits[i] > static_cast<uint64_t>(std::numeric_limits<int64_t>::max()) / 4) return false;
    }
    std::string_view listen = values["listen"], host, port;
    int family;
    if (listen.front() == '[') {
        size_t bracket = listen.find(']');
        if (bracket == std::string_view::npos || bracket + 1 >= listen.size() || listen[bracket + 1] != ':') return false;
        family = AF_INET6; host = listen.substr(1, bracket - 1); port = listen.substr(bracket + 2);
    } else {
        size_t colon = listen.find(':');
        if (colon == std::string_view::npos) return false;
        family = AF_INET; host = listen.substr(0, colon); port = listen.substr(colon + 1);
    }
    uint64_t p;
    if (!decimal(port, p) || !p || p > 65535 || host.empty()) return false;
    if (family == AF_INET) {
        auto* address = reinterpret_cast<sockaddr_in*>(&c.address);
        address->sin_family = AF_INET; address->sin_port = htons(static_cast<uint16_t>(p));
        if (inet_pton(AF_INET, std::string(host).c_str(), &address->sin_addr) != 1) return false;
        c.address_length = sizeof(*address);
    } else {
        auto* address = reinterpret_cast<sockaddr_in6*>(&c.address);
        address->sin6_family = AF_INET6; address->sin6_port = htons(static_cast<uint16_t>(p));
        if (inet_pton(AF_INET6, std::string(host).c_str(), &address->sin6_addr) != 1) return false;
        c.address_length = sizeof(*address);
    }
    return true;
}

struct File {
    std::string path, bytes;
    uint64_t size = 0;
    int fd = -1;
    bool buffered = false;
    ~File() { if (fd >= 0) close(fd); }
};
struct Connection {
    int fd;
    std::string input, header;
    size_t header_sent = 0;
    uint64_t body_sent = 0, served = 0;
    uint64_t header_start = 0, idle_since = 0, write_progress = 0;
    std::shared_ptr<File> file;
    bool output = false, closing = false, head = false, draining = false;
    uint32_t events = EPOLLIN | EPOLLRDHUP;
    explicit Connection(int socket) : fd(socket), idle_since(now_ms()) {}
    ~Connection() { close(fd); }
};

class Server {
    Config config;
    int root = -1, listener = -1, epoll = -1;
    size_t active = 0;
    std::vector<std::unique_ptr<Connection>> connections;
    std::unordered_map<std::string, std::shared_ptr<File>> cache;
    uint64_t next_expiration = 0;

    static int file_error(int parent, const std::string& part, int error) {
        struct stat st{};
        if (fstatat(parent, part.c_str(), &st, AT_SYMLINK_NOFOLLOW) == 0 && S_ISLNK(st.st_mode)) return 403;
        if (error == ELOOP || error == EACCES || error == EPERM) return 403;
        if (error == ENOENT || error == ENOTDIR || error == ENAMETOOLONG) return 404;
        return 500;
    }
    // Every component is opened relative to a previously confined directory.
    int open_file(const std::string& path, int& status) {
        int directory = root;
        size_t at = 0;
        while (true) {
            size_t slash = path.find('/', at);
            bool final = slash == std::string::npos;
            std::string part = path.substr(at, final ? std::string::npos : slash - at);
            int flags = O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK;
            if (!final) flags |= O_DIRECTORY;
            int fd = openat(directory, part.c_str(), flags);
            int error = errno;
            if (fd < 0) {
                status = file_error(directory, part, error);
                if (directory != root) close(directory);
                return -1;
            }
            if (directory != root) close(directory);
            if (final) {
                struct stat st{};
                if (fstat(fd, &st) < 0) { close(fd); status = 500; return -1; }
                if (!S_ISREG(st.st_mode)) { close(fd); status = 403; return -1; }
                status = 200;
                return fd;
            }
            directory = fd; at = slash + 1;
        }
    }
    std::shared_ptr<File> lookup(const std::string& path, int& status) {
        auto it = cache.find(path);
        if (it != cache.end()) { status = 200; return it->second; }
        int fd = open_file(path, status);
        if (fd < 0) return {};
        struct stat st{};
        if (fstat(fd, &st) < 0 || st.st_size < 0) { close(fd); status = 500; return {}; }
        auto entry = std::make_shared<File>();
        entry->path = path; entry->fd = fd; entry->size = static_cast<uint64_t>(st.st_size);
        if (entry->size <= 65536) {
            entry->bytes.resize(entry->size);
            size_t n = 0;
            while (n < entry->bytes.size()) {
                ssize_t r = pread(fd, entry->bytes.data() + n, entry->bytes.size() - n, static_cast<off_t>(n));
                if (r < 0 && errno == EINTR) continue;
                if (r <= 0) { status = 500; return {}; }
                n += static_cast<size_t>(r);
            }
            entry->buffered = true;
            close(entry->fd); entry->fd = -1;
        }
        // Eviction also closes a descriptor referenced by a blocked response.
        // Such responses reopen securely for the duration of their next write.
        if (cache.size() >= 128) {
            auto victim = cache.begin();
            if (victim->second->fd >= 0) { close(victim->second->fd); victim->second->fd = -1; }
            victim->second->buffered = false;
            std::string().swap(victim->second->bytes);
            cache.erase(victim);
        }
        cache.emplace(path, entry);
        return entry;
    }
    static int decode_path(std::string_view target, std::string& path, bool& trailing) {
        if (target.empty() || target.front() != '/' || target.find('#') != std::string_view::npos) return 400;
        target = target.substr(0, target.find('?'));
        std::string decoded;
        decoded.reserve(target.size());
        auto hex = [](unsigned char c) -> int {
            if (c >= '0' && c <= '9') return c - '0';
            if (c >= 'A' && c <= 'F') return c - 'A' + 10;
            if (c >= 'a' && c <= 'f') return c - 'a' + 10;
            return -1;
        };
        for (size_t i = 0; i < target.size(); ++i) {
            unsigned char ch = target[i];
            if (ch == '%') {
                if (i + 2 >= target.size()) return 400;
                int a = hex(target[i + 1]), b = hex(target[i + 2]);
                if (a < 0 || b < 0) return 400;
                ch = static_cast<unsigned char>((a << 4) | b); i += 2;
            }
            if (!ch || ch == '\\') return 400;
            decoded.push_back(ch);
        }
        if (!utf8(decoded)) return 400;
        trailing = decoded.back() == '/';
        size_t at = 1;
        while (at <= decoded.size()) {
            size_t end = decoded.find('/', at);
            if (end == std::string::npos) end = decoded.size();
            auto part = std::string_view(decoded).substr(at, end - at);
            if (part == "..") return 403;
            if (!part.empty() && part != ".") {
                if (!path.empty()) path.push_back('/');
                path.append(part);
            }
            at = end + 1;
        }
        return path.empty() ? 403 : 200;
    }
    void response(Connection& c, int status, bool close_after, bool head, std::shared_ptr<File> file = {}) {
        const char* reason = status == 200 ? "OK" : status == 400 ? "Bad Request" : status == 403 ? "Forbidden" :
            status == 404 ? "Not Found" : status == 405 ? "Method Not Allowed" : status == 431 ? "Request Header Fields Too Large" : "Internal Server Error";
        c.file = std::move(file); c.head = head; c.closing = close_after || c.served + 1 >= config.max_requests;
        c.header = "HTTP/1.1 " + std::to_string(status) + " " + reason + "\r\nContent-Length: " +
            std::to_string(c.file ? c.file->size : 0) + "\r\nContent-Type: application/octet-stream\r\nConnection: " +
            (c.closing ? "close" : "keep-alive") + "\r\n\r\n";
        c.header_sent = 0; c.body_sent = 0; c.output = true; c.write_progress = now_ms();
        c.header_start = 0;
        c.input.clear();
    }
    void parse(Connection& c) {
        std::string_view raw = c.input;
        size_t line_end = raw.find("\r\n");
        auto line = raw.substr(0, line_end);
        size_t a = line.find(' '), b = a == std::string_view::npos ? a : line.find(' ', a + 1);
        if (a == std::string_view::npos || b == std::string_view::npos || !a || b == a + 1 ||
            line.find(' ', b + 1) != std::string_view::npos) { response(c, 400, true, false); return; }
        auto method = line.substr(0, a), target = line.substr(a + 1, b - a - 1), version = line.substr(b + 1);
        for (unsigned char ch : method) if (!token_char(ch)) { response(c, 400, true, false); return; }
        for (unsigned char ch : target) if (ch <= 32 || ch == 127) { response(c, 400, true, false); return; }
        if (version != "HTTP/1.0" && version != "HTTP/1.1") { response(c, 400, true, false); return; }
        bool close_after = version == "HTTP/1.0", head = method == "HEAD", length_seen = false;
        size_t at = line_end + 2;
        while (at + 2 < raw.size()) {
            size_t end = raw.find("\r\n", at);
            line = raw.substr(at, end - at); at = end + 2;
            if (line.empty()) break;
            size_t colon = line.find(':');
            if (colon == std::string_view::npos || colon == 0) { response(c, 400, true, head); return; }
            auto name = line.substr(0, colon), value = line.substr(colon + 1);
            for (unsigned char ch : name) if (!token_char(ch)) { response(c, 400, true, head); return; }
            if (equal_ci(name, "transfer-encoding")) { response(c, 400, true, head); return; }
            if (equal_ci(name, "content-length")) {
                value = trim(value);
                if (length_seen || value.empty()) { response(c, 400, true, head); return; }
                length_seen = true;
                for (unsigned char ch : value) if (ch != '0') { response(c, 400, true, head); return; }
            }
            if (equal_ci(name, "connection")) {
                while (true) {
                    size_t comma = value.find(',');
                    if (equal_ci(trim(value.substr(0, comma)), "close")) close_after = true;
                    if (comma == std::string_view::npos) break;
                    value.remove_prefix(comma + 1);
                }
            }
        }
        std::string path;
        bool trailing = false;
        int status = decode_path(target, path, trailing);
        if (status == 400) { response(c, 400, true, head); return; }
        if (method != "GET" && method != "HEAD") { response(c, 405, close_after, false); return; }
        std::shared_ptr<File> file;
        if (status == 200) {
            file = lookup(path, status);
            if (file && trailing) { file.reset(); status = 403; }
        }
        response(c, status, close_after || status == 400, head, std::move(file));
    }
    // Peek and consume exactly one header. Subsequent pipelined bytes stay in
    // the kernel while output is blocked, so no request/response queue grows.
    int read_header(Connection& c) {
        char bytes[16384];
        size_t available = config.header_bytes > c.input.size() ?
            static_cast<size_t>(std::min<uint64_t>(sizeof(bytes), config.header_bytes - c.input.size())) : 0;
        if (!available) { response(c, 431, true, false); return 1; }
        ssize_t got = recv(c.fd, bytes, available, MSG_PEEK);
        if (got < 0 && errno == EINTR) return 2;
        if (got < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) return 0;
        if (got <= 0) return -1;
        size_t consume = got;
        char previous = c.input.empty() ? 0 : c.input.back();
        unsigned suffix = 0;
        if (c.input.size() >= 3 && c.input.compare(c.input.size() - 3, 3, "\r\n\r") == 0) suffix = 3;
        else if (c.input.size() >= 2 && c.input.compare(c.input.size() - 2, 2, "\r\n") == 0) suffix = 2;
        else if (previous == '\r') suffix = 1;
        bool malformed = false;
        for (size_t i = 0; i < static_cast<size_t>(got); ++i) {
            char ch = bytes[i];
            if (!ch || (ch == '\n' && previous != '\r') || (previous == '\r' && ch != '\n')) {
                malformed = true; consume = i + 1; break;
            }
            if (ch == "\r\n\r\n"[suffix]) ++suffix;
            else suffix = ch == '\r' ? 1 : 0;
            previous = ch;
            if (suffix == 4) { consume = i + 1; break; }
        }
        ssize_t count = recv(c.fd, bytes, consume, 0);
        if (count < 0 && (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK)) return 2;
        if (count <= 0) return -1;
        if (!c.header_start) c.header_start = now_ms();
        c.input.append(bytes, static_cast<size_t>(count));
        if (now_ms() - c.header_start >= config.header_timeout_ms) return -1;
        if (static_cast<size_t>(count) != consume) return 2;
        if (malformed) { response(c, 400, true, false); return 1; }
        if (suffix == 4) { parse(c); return 1; }
        if (c.input.size() >= config.header_bytes) { response(c, 431, true, false); return 1; }
        return 2;
    }
    int write_response(Connection& c, size_t& budget) {
        ssize_t sent = 0;
        if (c.header_sent < c.header.size() || (c.file && c.file->buffered && !c.head && c.body_sent < c.file->size)) {
            iovec vectors[2]; int count = 0;
            if (c.header_sent < c.header.size()) vectors[count++] = {c.header.data() + c.header_sent, c.header.size() - c.header_sent};
            if (c.file && c.file->buffered && !c.head && c.body_sent < c.file->size)
                vectors[count++] = {c.file->bytes.data() + c.body_sent, static_cast<size_t>(c.file->size - c.body_sent)};
            msghdr message{}; message.msg_iov = vectors; message.msg_iovlen = count;
            sent = sendmsg(c.fd, &message, MSG_NOSIGNAL);
            if (sent > 0) {
                size_t header_bytes = std::min<size_t>(sent, c.header.size() - c.header_sent);
                c.header_sent += header_bytes;
                c.body_sent += static_cast<size_t>(sent) - header_bytes;
            }
        } else if (c.file && !c.head && c.body_sent < c.file->size) {
            int status = 200, fd = c.file->fd;
            bool temporary = fd < 0;
            if (temporary) fd = open_file(c.file->path, status);
            if (fd < 0) return -1;
            off_t offset = static_cast<off_t>(c.body_sent);
            sent = sendfile(c.fd, fd, &offset, std::min<uint64_t>(budget, c.file->size - c.body_sent));
            int error = errno;
            if (temporary) close(fd);
            errno = error;
            if (sent > 0) c.body_sent += static_cast<size_t>(sent);
        } else return 1;
        if (sent < 0 && errno == EINTR) return 2;
        if (sent < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) return 0;
        if (sent <= 0) return -1;
        c.write_progress = now_ms();
        budget -= std::min<size_t>(budget, sent);
        if (c.header_sent == c.header.size() && (!c.file || c.head || c.body_sent == c.file->size)) return 1;
        return 2;
    }
    bool drain_input(Connection& c) {
        char bytes[16384];
        for (unsigned i = 0; i < 16; ++i) {
            ssize_t n = recv(c.fd, bytes, sizeof(bytes), 0);
            if (n < 0 && errno == EINTR) { --i; continue; }
            // Closing a socket with queued request bytes sends TCP RST.
            // Discard the already received excess pipeline before close.
            if (n <= 0) return false;
        }
        return true;
    }
    bool timed_out(const Connection& c, uint64_t now) const {
        return c.draining ? now - c.idle_since >= config.write_timeout_ms :
            c.output ? now - c.write_progress >= config.write_timeout_ms :
            c.header_start ? now - c.header_start >= config.header_timeout_ms :
            now - c.idle_since >= config.idle_timeout_ms;
    }
    bool service(Connection& c) {
        if (timed_out(c, now_ms())) return false;
        if (c.draining) return drain_input(c);
        size_t budget = 256 * 1024;
        unsigned completed = 0, reads = 0;
        while (budget && completed < 32 && reads < 64) {
            if (timed_out(c, now_ms())) return false;
            if (!c.output) {
                ++reads;
                int read = read_header(c);
                if (read < 0) return false;
                if (read == 0) break;
                if (!c.output) continue;
            }
            int written = write_response(c, budget);
            if (written < 0) return false;
            if (!written) break;
            if (written == 1) {
                if (c.closing) {
                    shutdown(c.fd, SHUT_WR);
                    c.output = false; c.draining = true; c.file.reset();
                    c.idle_since = now_ms();
                    if (!drain_input(c)) return false;
                    break;
                }
                ++c.served; ++completed;
                c.output = false; c.file.reset(); c.header.clear();
                c.idle_since = now_ms();
            }
        }
        uint32_t interest = c.output ? EPOLLOUT : (EPOLLIN | EPOLLRDHUP);
        if (interest != c.events) {
            epoll_event event{}; event.events = interest; event.data.fd = c.fd;
            if (epoll_ctl(epoll, EPOLL_CTL_MOD, c.fd, &event) < 0) return false;
            c.events = interest;
        }
        return true;
    }
    void drop(int fd) {
        if (fd >= 0 && static_cast<size_t>(fd) < connections.size() && connections[fd]) {
            epoll_ctl(epoll, EPOLL_CTL_DEL, fd, nullptr);
            connections[fd].reset(); --active;
        }
    }
    void accept_clients() {
        for (unsigned i = 0; i < 128; ++i) {
            int fd = accept4(listener, nullptr, nullptr, SOCK_NONBLOCK | SOCK_CLOEXEC);
            if (fd < 0) { if (errno == EINTR) continue; return; }
            if (active >= config.max_connections) { close(fd); continue; }
            int yes = 1;
            setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &yes, sizeof(yes));
            if (static_cast<size_t>(fd) >= connections.size()) connections.resize(fd + 256);
            auto connection = std::make_unique<Connection>(fd);
            epoll_event event{}; event.events = connection->events; event.data.fd = fd;
            if (epoll_ctl(epoll, EPOLL_CTL_ADD, fd, &event) < 0) continue;
            connections[fd] = std::move(connection); ++active;
        }
    }
    void expire() {
        uint64_t now = now_ms();
        if (now < next_expiration) return;
        next_expiration = now + std::min<uint64_t>({10, config.header_timeout_ms, config.idle_timeout_ms, config.write_timeout_ms});
        for (size_t fd = 0; fd < connections.size(); ++fd) {
            if (!connections[fd]) continue;
            if (timed_out(*connections[fd], now)) drop(static_cast<int>(fd));
        }
    }
public:
    explicit Server(Config c) : config(std::move(c)) {}
    ~Server() { if (root >= 0) close(root); if (listener >= 0) close(listener); if (epoll >= 0) close(epoll); }
    bool start() {
        root = open(config.root.c_str(), O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NONBLOCK);
        if (root < 0) return false;
        listener = socket(config.address.ss_family, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
        if (listener < 0) return false;
        int yes = 1;
        setsockopt(listener, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes));
        if (bind(listener, reinterpret_cast<sockaddr*>(&config.address), config.address_length) < 0 || listen(listener, 8192) < 0) return false;
        epoll = epoll_create1(EPOLL_CLOEXEC);
        if (epoll < 0) return false;
        epoll_event event{}; event.events = EPOLLIN; event.data.fd = listener;
        return epoll_ctl(epoll, EPOLL_CTL_ADD, listener, &event) == 0;
    }
    void run() {
        epoll_event events[256];
        while (true) {
            expire();
            int n = epoll_wait(epoll, events, 256, static_cast<int>(std::min<uint64_t>(
                {10, config.header_timeout_ms, config.idle_timeout_ms, config.write_timeout_ms})));
            if (n < 0) { if (errno == EINTR) continue; return; }
            for (int i = 0; i < n; ++i) {
                int fd = events[i].data.fd;
                if (fd == listener) { accept_clients(); continue; }
                if (fd < 0 || static_cast<size_t>(fd) >= connections.size() || !connections[fd]) continue;
                if ((events[i].events & EPOLLERR) || !service(*connections[fd])) drop(fd);
            }
        }
    }
};

int main(int argc, char** argv) {
    std::signal(SIGPIPE, SIG_IGN);
    if (argc != 3 || std::string_view(argv[1]) != "--config") return 1;
    try {
        Config config;
        if (!configuration(argv[2], config)) { std::cerr << "Invalid configuration\n"; return 1; }
        Server server(std::move(config));
        if (!server.start()) { std::cerr << "Unable to start server\n"; return 1; }
        server.run();
    } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
    return 0;
}
