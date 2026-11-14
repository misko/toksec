#include <algorithm>
#include <array>
#include <cerrno>
#include <chrono>
#include <climits>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <limits>
#include <memory>
#include <string>
#include <string_view>
#include <unordered_map>
#include <vector>
#include <arpa/inet.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <signal.h>
#include <sys/epoll.h>
#include <sys/resource.h>
#include <sys/sendfile.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

namespace {
uint64_t milliseconds() {
    timespec t{};
    clock_gettime(CLOCK_MONOTONIC, &t);
    return uint64_t(t.tv_sec) * 1000 + uint64_t(t.tv_nsec) / 1000000;
}
uint64_t after(uint64_t now, uint64_t delay) {
    return delay > UINT64_MAX - now ? UINT64_MAX : now + delay;
}
bool utf8(std::string_view s) {
    size_t i = 0;
    while (i < s.size()) {
        unsigned char c = s[i++];
        if (c < 0x80) continue;
        unsigned n; uint32_t cp;
        if (c >= 0xc2 && c <= 0xdf) { n = 1; cp = c & 31; }
        else if (c >= 0xe0 && c <= 0xef) { n = 2; cp = c & 15; }
        else if (c >= 0xf0 && c <= 0xf4) { n = 3; cp = c & 7; }
        else return false;
        if (i + n > s.size()) return false;
        for (unsigned j = 0; j < n; ++j) {
            unsigned char b = s[i++];
            if ((b & 0xc0) != 0x80) return false;
            cp = (cp << 6) | (b & 63);
        }
        if ((n == 1 && cp < 0x80) || (n == 2 && cp < 0x800) ||
            (n == 3 && cp < 0x10000) || cp > 0x10ffff || (cp >= 0xd800 && cp <= 0xdfff)) return false;
    }
    return true;
}
std::string_view trim(std::string_view s) {
    while (!s.empty() && (s.front() == ' ' || s.front() == '\t')) s.remove_prefix(1);
    while (!s.empty() && (s.back() == ' ' || s.back() == '\t')) s.remove_suffix(1);
    return s;
}
bool decimal(std::string_view s, uint64_t& out) {
    if (s.empty()) return false;
    out = 0;
    for (unsigned char c : s) {
        if (c < '0' || c > '9' || out > (UINT64_MAX - (c - '0')) / 10) return false;
        out = out * 10 + c - '0';
    }
    return true;
}
struct Config {
    sockaddr_storage address{};
    socklen_t address_size = 0;
    std::string root;
    uint64_t max_connections = 0, header_bytes = 0, header_timeout = 0, write_timeout = 0;
};
bool configuration(const char* filename, Config& cfg) {
    std::ifstream input(filename, std::ios::binary);
    if (!input) return false;
    std::string all((std::istreambuf_iterator<char>(input)), {});
    if (!utf8(all) || all.find('\0') != std::string::npos) return false;
    std::unordered_map<std::string, std::string> fields;
    size_t begin = 0;
    while (begin < all.size()) {
        size_t end = all.find('\n', begin);
        if (end == std::string::npos) end = all.size();
        std::string_view line(all.data() + begin, end - begin);
        if (!line.empty() && line.back() == '\r') line.remove_suffix(1);
        line = trim(line);
        if (!line.empty() && line.front() != '#') {
            size_t equal = line.find('=');
            if (equal == std::string_view::npos) return false;
            auto key = trim(line.substr(0, equal));
            auto value = trim(line.substr(equal + 1));
            if (key.empty() || value.empty() || value.find('\r') != std::string_view::npos ||
                !fields.emplace(std::string(key), std::string(value)).second) return false;
        }
        begin = end + 1;
    }
    const char* names[] = {"listen", "root", "max_connections", "header_bytes", "header_timeout_ms",
                           "idle_timeout_ms", "write_timeout_ms", "max_requests", "pipeline_depth"};
    if (fields.size() != std::size(names)) return false;
    for (auto name : names) if (!fields.contains(name)) return false;
    cfg.root = fields["root"];
    if (cfg.root.front() != '/') return false;
    struct stat st{};
    if (stat(cfg.root.c_str(), &st) || !S_ISDIR(st.st_mode)) return false;
    for (size_t i = 2; i < std::size(names); ++i) {
        uint64_t value;
        if (!decimal(fields[names[i]], value) || value == 0) return false;
        if (i == 2) cfg.max_connections = value;
        if (i == 3) cfg.header_bytes = value;
        if (i == 4) cfg.header_timeout = value;
        if (i == 6) cfg.write_timeout = value;
    }
    std::string_view listen = fields["listen"], host, port;
    if (!listen.empty() && listen.front() == '[') {
        size_t close = listen.find(']');
        if (close == std::string_view::npos || close + 1 >= listen.size() || listen[close + 1] != ':') return false;
        host = listen.substr(1, close - 1); port = listen.substr(close + 2);
    } else {
        size_t colon = listen.find(':');
        if (colon == std::string_view::npos || listen.find(':', colon + 1) != std::string_view::npos) return false;
        host = listen.substr(0, colon); port = listen.substr(colon + 1);
    }
    uint64_t number;
    if (!decimal(port, number) || !number || number > 65535) return false;
    std::string host_string(host);
    auto* v4 = reinterpret_cast<sockaddr_in*>(&cfg.address);
    auto* v6 = reinterpret_cast<sockaddr_in6*>(&cfg.address);
    if (inet_pton(AF_INET, host_string.c_str(), &v4->sin_addr) == 1) {
        v4->sin_family = AF_INET; v4->sin_port = htons(number); cfg.address_size = sizeof(*v4);
    } else if (inet_pton(AF_INET6, host_string.c_str(), &v6->sin6_addr) == 1) {
        v6->sin6_family = AF_INET6; v6->sin6_port = htons(number); cfg.address_size = sizeof(*v6);
    } else return false;
    return true;
}
bool token(unsigned char c) {
    return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') ||
           std::string_view("!#$%&'*+-.^_`|~").find(char(c)) != std::string_view::npos;
}
bool iequal(std::string_view a, std::string_view b) {
    if (a.size() != b.size()) return false;
    for (size_t i = 0; i < a.size(); ++i) {
        unsigned char c = a[i];
        if (c >= 'A' && c <= 'Z') c += 'a' - 'A';
        if (c != b[i]) return false;
    }
    return true;
}
int hex(unsigned char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}
int parse(std::string_view raw, std::string& path) {
    size_t end = raw.find("\r\n");
    if (end == std::string_view::npos) return 400;
    auto line = raw.substr(0, end);
    size_t a = line.find(' '), b = a == std::string_view::npos ? a : line.find(' ', a + 1);
    if (a == 0 || a == std::string_view::npos || b == std::string_view::npos || b == a + 1 ||
        line.find(' ', b + 1) != std::string_view::npos) return 400;
    auto method = line.substr(0, a), target = line.substr(a + 1, b - a - 1), version = line.substr(b + 1);
    for (unsigned char c : method) if (!token(c)) return 400;
    if (version != "HTTP/1.0" && version != "HTTP/1.1") return 400;
    bool content_length = false;
    for (size_t pos = end + 2; pos < raw.size() - 2;) {
        size_t next = raw.find("\r\n", pos);
        if (next == std::string_view::npos || next == pos) return 400;
        auto field = raw.substr(pos, next - pos);
        size_t colon = field.find(':');
        if (!colon || colon == std::string_view::npos) return 400;
        auto name = field.substr(0, colon), value = field.substr(colon + 1);
        for (unsigned char c : name) if (!token(c)) return 400;
        for (unsigned char c : value) if ((c < 32 && c != '\t') || c == 127) return 400;
        if (iequal(name, "transfer-encoding")) return 400;
        if (iequal(name, "content-length")) {
            if (content_length) return 400;
            content_length = true;
            value = trim(value);
            if (value.empty()) return 400;
            // Any number of decimal zeroes is a valid zero, without integer overflow.
            for (unsigned char c : value) if (c != '0') return 400;
        }
        pos = next + 2;
    }
    if (target.empty() || target.front() != '/' || target.find('#') != std::string_view::npos) return 400;
    for (unsigned char c : target) if (c <= 32 || c == 127) return 400;
    target = target.substr(0, target.find('?'));
    path.clear(); path.reserve(target.size());
    for (size_t i = 0; i < target.size(); ++i) {
        unsigned char c = target[i];
        if (c == '%') {
            if (i + 2 >= target.size()) return 400;
            int hi = hex(target[i + 1]), lo = hex(target[i + 2]);
            if (hi < 0 || lo < 0) return 400;
            c = static_cast<unsigned char>((hi << 4) | lo); i += 2;
        }
        if (c == 0 || c == '\\') return 400;
        path.push_back(c);
    }
    if (!utf8(path)) return 400;
    size_t pos = 1;
    while (pos <= path.size()) {
        size_t slash = path.find('/', pos);
        if (slash == std::string::npos) slash = path.size();
        if (std::string_view(path).substr(pos, slash - pos) == "..") return 403;
        pos = slash + 1;
    }
    if (method != "GET") return 405;
    return 200;
}
std::string response_header(int status, uint64_t size) {
    const char* reason = "Internal Server Error";
    switch (status) {
        case 200: reason = "OK"; break;
        case 400: reason = "Bad Request"; break;
        case 403: reason = "Forbidden"; break;
        case 404: reason = "Not Found"; break;
        case 405: reason = "Method Not Allowed"; break;
        case 408: reason = "Request Timeout"; break;
        case 431: reason = "Request Header Fields Too Large"; break;
    }
    return "HTTP/1.1 " + std::to_string(status) + " " + reason +
           "\r\nContent-Length: " + std::to_string(size) +
           "\r\nContent-Type: application/octet-stream\r\nConnection: close\r\n\r\n";
}
struct File {
    int fd = -1;
    uint64_t length = 0;
    bool buffered = false;
    std::string wire;
    ~File() { if (fd >= 0) close(fd); }
};
class Files {
    int root;
    size_t cached_bytes = 0;
    std::unordered_map<std::string, std::shared_ptr<File>> cache;
    static int failure(int dir, const char* name, int error) {
        if (error == ELOOP || error == EACCES || error == EPERM) return 403;
        struct stat st{};
        if (!fstatat(dir, name, &st, AT_SYMLINK_NOFOLLOW) && (S_ISLNK(st.st_mode) || !S_ISREG(st.st_mode))) return 403;
        if (error == ENOENT || error == ENOTDIR || error == ENAMETOOLONG) return 404;
        return 500;
    }
public:
    explicit Files(int root_fd) : root(root_fd) {}
    std::shared_ptr<File> get(const std::string& path, int& status) {
        auto found = cache.find(path);
        if (found != cache.end()) return found->second;
        int dir = root, fd = -1;
        size_t pos = 1;
        while (pos < path.size()) {
            size_t slash = path.find('/', pos);
            if (slash == std::string::npos) slash = path.size();
            std::string name = path.substr(pos, slash - pos);
            pos = slash + 1;
            if (name.empty() || name == ".") continue;
            bool final = slash == path.size();
            int flags = O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK;
            if (!final) flags |= O_DIRECTORY;
            int next = openat(dir, name.c_str(), flags);
            if (next < 0) {
                status = failure(dir, name.c_str(), errno);
                if (dir != root) close(dir);
                return {};
            }
            if (dir != root) close(dir);
            if (final) { fd = next; break; }
            dir = next;
        }
        if (fd < 0) {
            if (dir != root) close(dir);
            status = 403; return {};
        }
        struct stat st{};
        if (fstat(fd, &st) || !S_ISREG(st.st_mode) || st.st_size < 0) {
            close(fd); status = 403; return {};
        }
        auto file = std::make_shared<File>();
        file->fd = fd; file->length = uint64_t(st.st_size);
        file->wire = response_header(200, file->length);
        bool cacheable = cache.size() < 128;
        if (cacheable && file->length <= 131072 && cached_bytes + file->length + file->wire.size() <= 8 * 1024 * 1024) {
            size_t header = file->wire.size();
            file->wire.resize(header + size_t(file->length));
            size_t offset = 0;
            while (offset < file->length) {
                ssize_t n = pread(fd, file->wire.data() + header + offset, file->length - offset, off_t(offset));
                if (n < 0 && errno == EINTR) continue;
                if (n <= 0) { status = 500; return {}; }
                offset += size_t(n);
            }
            file->buffered = true;
            close(file->fd); file->fd = -1;
            cached_bytes += file->wire.size();
        }
        if (cacheable) cache.emplace(path, file);
        return file;
    }
};
struct Connection {
    bool active = false, writing = false, registered = false;
    uint32_t generation = 0;
    size_t scanned = 0, sent = 0;
    int heap = -1;
    uint64_t deadline = 0;
    off_t offset = 0;
    std::string input, error;
    std::shared_ptr<File> file;
};
class Server {
    Config cfg;
    int listener = -1, epoll = -1, root = -1;
    uint64_t count = 0;
    bool listening = true;
    std::vector<Connection> connections;
    std::vector<int> timers;
    std::unique_ptr<Files> files;
    static constexpr uint64_t listener_tag = UINT64_MAX;
    bool earlier(int a, int b) { return connections[a].deadline < connections[b].deadline; }
    void swap_timer(size_t a, size_t b) {
        std::swap(timers[a], timers[b]);
        connections[timers[a]].heap = int(a); connections[timers[b]].heap = int(b);
    }
    void rise(size_t p) {
        while (p && earlier(timers[p], timers[(p - 1) / 2])) { swap_timer(p, (p - 1) / 2); p = (p - 1) / 2; }
    }
    void sink(size_t p) {
        for (;;) {
            size_t c = p * 2 + 1;
            if (c >= timers.size()) return;
            if (c + 1 < timers.size() && earlier(timers[c + 1], timers[c])) ++c;
            if (!earlier(timers[c], timers[p])) return;
            swap_timer(p, c); p = c;
        }
    }
    void untime(int fd) {
        int p = connections[fd].heap;
        if (p < 0) return;
        swap_timer(size_t(p), timers.size() - 1);
        timers.pop_back(); connections[fd].heap = -1;
        if (size_t(p) < timers.size()) {
            int moved = timers[p]; rise(size_t(p)); sink(size_t(connections[moved].heap));
        }
    }
    void time(int fd, uint64_t deadline) {
        auto& c = connections[fd];
        uint64_t previous = c.deadline; c.deadline = deadline;
        if (c.heap < 0) { c.heap = int(timers.size()); timers.push_back(fd); rise(size_t(c.heap)); }
        else if (deadline < previous) rise(size_t(c.heap)); else sink(size_t(c.heap));
    }
    void watch(int fd) {
        auto& c = connections[fd];
        epoll_event e{};
        // RDHUP is useful while reading; subscribing during a blocked write
        // would repeatedly wake for a client that half-closed its request.
        e.events = c.writing ? EPOLLOUT : (EPOLLIN | EPOLLRDHUP);
        e.data.u64 = (uint64_t(c.generation) << 32) | uint32_t(fd);
        int operation = c.registered ? EPOLL_CTL_MOD : EPOLL_CTL_ADD;
        if (epoll_ctl(epoll, operation, fd, &e)) { finish(fd); return; }
        c.registered = true;
    }
    void finish(int fd) {
        auto& c = connections[fd];
        if (!c.active) return;
        untime(fd);
        if (c.registered) epoll_ctl(epoll, EPOLL_CTL_DEL, fd, nullptr);
        close(fd);
        c.active = false; c.registered = false; c.file.reset(); c.input.clear(); c.error.clear(); --count;
        if (!listening && count < cfg.max_connections) {
            epoll_event e{}; e.events = EPOLLIN; e.data.u64 = listener_tag;
            if (!epoll_ctl(epoll, EPOLL_CTL_ADD, listener, &e)) listening = true;
        }
    }
    void write(int fd) {
        auto& c = connections[fd];
        const std::string& wire = c.file ? c.file->wire : c.error;
        bool progress = false;
        while (c.sent < wire.size()) {
            int flags = MSG_NOSIGNAL;
            if (c.file && !c.file->buffered && c.file->length) flags |= MSG_MORE;
            ssize_t n = send(fd, wire.data() + c.sent, wire.size() - c.sent, flags);
            if (n > 0) { c.sent += size_t(n); progress = true; continue; }
            if (n < 0 && errno == EINTR) continue;
            if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
                if (progress) time(fd, after(milliseconds(), cfg.write_timeout));
                return;
            }
            finish(fd); return;
        }
        if (c.file && !c.file->buffered) {
            while (uint64_t(c.offset) < c.file->length) {
                size_t length = size_t(std::min<uint64_t>(c.file->length - uint64_t(c.offset), 1024 * 1024));
                ssize_t n = sendfile(fd, c.file->fd, &c.offset, length);
                if (n > 0) { progress = true; continue; }
                if (n < 0 && errno == EINTR) continue;
                if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
                    if (progress) time(fd, after(milliseconds(), cfg.write_timeout));
                    return;
                }
                finish(fd); return;
            }
        }
        finish(fd);
    }
    void respond(int fd, int status, const std::string* path = nullptr) {
        auto& c = connections[fd];
        if (status == 200) c.file = files->get(*path, status);
        if (!c.file) c.error = response_header(status, 0);
        c.writing = true; c.sent = 0; c.offset = 0;
        time(fd, after(milliseconds(), cfg.write_timeout));
        write(fd);
        if (c.active && c.registered) watch(fd);
    }
    void read(int fd) {
        auto& c = connections[fd];
        std::array<char, 16384> buffer;
        for (;;) {
            uint64_t remaining = cfg.header_bytes >= c.input.size() ? cfg.header_bytes - c.input.size() : 0;
            size_t capacity = size_t(std::min<uint64_t>(remaining, buffer.size() - 1)) + 1;
            ssize_t n = recv(fd, buffer.data(), capacity, 0);
            if (n > 0) {
                c.input.append(buffer.data(), size_t(n));
                for (size_t i = c.scanned; i < c.input.size(); ++i) {
                    char ch = c.input[i];
                    if (!ch || (ch == '\n' && (!i || c.input[i - 1] != '\r')) ||
                        (i && c.input[i - 1] == '\r' && ch != '\n')) { respond(fd, 400); return; }
                    if (i >= 3 && ch == '\n' && c.input[i - 1] == '\r' && c.input[i - 2] == '\n' && c.input[i - 3] == '\r') {
                        if (i + 1 > cfg.header_bytes) { respond(fd, 431); return; }
                        if (milliseconds() >= c.deadline) { finish(fd); return; }
                        std::string path;
                        int status = parse(std::string_view(c.input.data(), i + 1), path);
                        respond(fd, status, &path); return;
                    }
                }
                c.scanned = c.input.size();
                if (c.input.size() > cfg.header_bytes) { respond(fd, 431); return; }
                continue;
            }
            if (n < 0 && errno == EINTR) continue;
            if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) return;
            finish(fd); return;
        }
    }
    void accept() {
        for (unsigned accepted = 0; accepted < 256 && count < cfg.max_connections; ++accepted) {
            int fd = accept4(listener, nullptr, nullptr, SOCK_NONBLOCK | SOCK_CLOEXEC);
            if (fd < 0) {
                if (errno == EINTR) { --accepted; continue; }
                return;
            }
            if (size_t(fd) >= connections.size()) connections.resize(size_t(fd) + 1024);
            auto& c = connections[fd];
            c.active = true; c.writing = false; c.registered = false; ++c.generation;
            c.scanned = c.sent = 0; c.offset = 0; ++count;
            time(fd, after(milliseconds(), cfg.header_timeout));
            int one = 1; setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof(one));
            read(fd);
            if (c.active) watch(fd);
        }
        if (count >= cfg.max_connections && listening) {
            epoll_ctl(epoll, EPOLL_CTL_DEL, listener, nullptr); listening = false;
        }
    }
public:
    explicit Server(Config c) : cfg(std::move(c)), connections(16384) {}
    bool initialize() {
        root = open(cfg.root.c_str(), O_RDONLY | O_DIRECTORY | O_CLOEXEC);
        if (root < 0) return false;
        files = std::make_unique<Files>(root);
        listener = socket(cfg.address.ss_family, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
        if (listener < 0) return false;
        int one = 1; setsockopt(listener, SOL_SOCKET, SO_REUSEADDR, &one, sizeof(one));
        if (bind(listener, reinterpret_cast<sockaddr*>(&cfg.address), cfg.address_size) || listen(listener, SOMAXCONN)) return false;
        epoll = epoll_create1(EPOLL_CLOEXEC);
        if (epoll < 0) return false;
        epoll_event e{}; e.events = EPOLLIN; e.data.u64 = listener_tag;
        return epoll_ctl(epoll, EPOLL_CTL_ADD, listener, &e) == 0;
    }
    int run() {
        std::array<epoll_event, 1024> events;
        for (;;) {
            uint64_t now = milliseconds();
            while (!timers.empty() && connections[timers.front()].deadline <= now) finish(timers.front());
            int delay = -1;
            if (!timers.empty()) delay = int(std::min<uint64_t>(connections[timers.front()].deadline - now, INT_MAX));
            int n = epoll_wait(epoll, events.data(), int(events.size()), delay);
            if (n < 0) { if (errno == EINTR) continue; return 1; }
            for (int i = 0; i < n; ++i) {
                uint64_t tag = events[i].data.u64;
                if (tag == listener_tag) { accept(); continue; }
                int fd = int(uint32_t(tag));
                auto& c = connections[fd];
                if (!c.active || c.generation != uint32_t(tag >> 32)) continue;
                if (c.deadline <= milliseconds()) { finish(fd); continue; }
                if (events[i].events & EPOLLERR) { finish(fd); continue; }
                if (c.writing) write(fd); else read(fd);
            }
        }
    }
};
}
int main(int argc, char** argv) {
    if (argc != 3 || std::strcmp(argv[1], "--config")) return 1;
    signal(SIGPIPE, SIG_IGN);
    try {
        Config cfg;
        if (!configuration(argv[2], cfg)) { std::fprintf(stderr, "invalid configuration\n"); return 1; }
        Server server(std::move(cfg));
        if (!server.initialize()) { std::perror("server initialization"); return 1; }
        return server.run();
    } catch (const std::exception& e) { std::fprintf(stderr, "server error: %s\n", e.what()); return 1; }
}
