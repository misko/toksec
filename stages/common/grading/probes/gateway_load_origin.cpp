// Parent-only ordinary-traffic fixture for the Stage 14 and 16 load matrix.
#include <arpa/inet.h>
#include <sys/epoll.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <cerrno>
#include <charconv>
#include <cstring>
#include <fstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <unordered_map>
using std::string;
using std::string_view;

namespace {
constexpr size_t header_limit = 8192;
constexpr size_t body_limit = 1 << 20;
struct Client {
    string input, output;
    size_t sent = 0;
    bool control = false, close_after = false;
};

void require(bool ok) {
    if (!ok) throw std::runtime_error(std::strerror(errno));
}
int listener(int family, const sockaddr* address, socklen_t length) {
    int fd = socket(family, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
    require(fd >= 0);
    int on = 1;
    if (family == AF_INET) require(!setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &on, sizeof(on)));
    require(!bind(fd, address, length) && !listen(fd, 8192));
    return fd;
}
void watch(int ep, int fd, int operation, uint32_t events) {
    epoll_event ev{}; ev.data.fd = fd; ev.events = events;
    require(epoll_ctl(ep, operation, fd, &ev) == 0);
}
string body(size_t size) {
    string bytes(size, 0);
    for (size_t i = 0; i < size; ++i) bytes[i] = static_cast<char>(i % 256);
    return bytes;
}
string response(string_view bytes, bool cacheable) {
    string value = "HTTP/1.1 200 Fixture\r\nContent-Length: " + std::to_string(bytes.size()) + "\r\n";
    if (cacheable) value += "Cache-Control: public,max-age=60\r\n";
    return value + "\r\n" + string(bytes);
}
constexpr string_view malformed = "HTTP/1.1 400 Fixture\r\nContent-Length: 0\r\nConnection: close\r\n\r\n";

bool equal_name(string_view left, string_view right) {
    if (left.size() != right.size()) return false;
    for (size_t i = 0; i < left.size(); ++i) {
        char c = left[i];
        if (c >= 'A' && c <= 'Z') c += 'a' - 'A';
        if (c != right[i]) return false;
    }
    return true;
}

void prepare(Client& c, size_t& requests, bool probe) {
    if (c.control) {
        if (c.input.find('\n') == string::npos) return;
        c.output = "{\"auth\":0,\"origin\":" + std::to_string(requests) + "}\n";
        c.close_after = true;
        return;
    }
    const string_view data(c.input);
    const size_t end = data.find("\r\n\r\n");
    auto reject = [&]() { c.output = malformed; c.close_after = true; };
    if (end == string::npos) { if (data.size() > header_limit) reject(); return; }
    if (end > header_limit) { reject(); return; }
    const size_t first = data.find("\r\n");
    const auto line = data.substr(0, first);
    size_t content_length = 0;
    bool length_seen = false;
    for (size_t pos = first + 2; pos < end; ) {
        const size_t next = data.find("\r\n", pos);
        const auto field = data.substr(pos, next - pos);
        const size_t colon = field.find(':');
        if (colon == string::npos) { reject(); return; }
        auto value = field.substr(colon + 1);
        while (!value.empty() && (value.front() == ' ' || value.front() == '\t')) value.remove_prefix(1);
        if (equal_name(field.substr(0, colon), "content-length")) {
            const auto parsed = std::from_chars(value.data(), value.data() + value.size(), content_length);
            if (length_seen || parsed.ec != std::errc() || parsed.ptr != value.data() + value.size() || content_length > body_limit) {
                reject(); return;
            }
            length_seen = true;
        }
        if (equal_name(field.substr(0, colon), "connection") && equal_name(value, "close")) c.close_after = true;
        pos = next + 2;
    }
    size_t length = end + 4 + content_length;
    if (data.size() < length) return;
    const size_t space = line.find(' '), tail = line.rfind(' ');
    if (space == string::npos || tail <= space) { reject(); return; }
    auto path = line.substr(space + 1, tail - space - 1);
    if (probe && path.starts_with("/gateway/")) path.remove_prefix(8);
    ++requests;
    if (line.starts_with("POST ") && path == "/upload") c.output = response(data.substr(end + 4, content_length), false);
    else if (line.starts_with("GET ") && (path == "/data/4096" || path == "/data/65536")) {
        static const string small = response(body(4096), true), large = response(body(65536), true);
        c.output = path == "/data/4096" ? small : large;
    } else {
        c.output = "HTTP/1.1 404 Fixture\r\nContent-Length: 0\r\n\r\n";
    }
    c.input.erase(0, length);
}
}

int main(int argc, char** argv) {
    // The direct generator probe uses the standard candidate process interface.
    const bool probe = argc == 3 && string_view(argv[1]) == "--config";
    if (argc != 3) return 2;
    sockaddr_in endpoint{};
    endpoint.sin_family = AF_INET;
    endpoint.sin_port = htons(probe ? 8080 : 8081);
    endpoint.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    const int tcp = listener(AF_INET, reinterpret_cast<const sockaddr*>(&endpoint), sizeof(endpoint));
    int ctl = -1;
    if (!probe) {
        sockaddr_un addr{}; addr.sun_family = AF_UNIX;
        if (std::strlen(argv[2]) >= sizeof(addr.sun_path)) return 2;
        std::strcpy(addr.sun_path, argv[2]);
        ctl = listener(AF_UNIX, reinterpret_cast<const sockaddr*>(&addr), sizeof(addr));
    }
    const int ep = epoll_create1(EPOLL_CLOEXEC);
    require(ep >= 0);
    watch(ep, tcp, EPOLL_CTL_ADD, EPOLLIN);
    if (ctl >= 0) {
        watch(ep, ctl, EPOLL_CTL_ADD, EPOLLIN);
        std::ofstream ready(argv[1]); require(ready.good());
    }
    std::unordered_map<int, Client> clients;
    size_t requests = 0;
    epoll_event events[256];
    for (;;) {
        const int count = epoll_wait(ep, events, 256, -1);
        if (count < 0 && errno == EINTR) continue;
        require(count >= 0);
        for (int i = 0; i < count; ++i) {
            const int fd = events[i].data.fd;
            if (fd == tcp || fd == ctl) {
                for (;;) {
                    const int peer = accept4(fd, nullptr, nullptr, SOCK_NONBLOCK | SOCK_CLOEXEC);
                    if (peer < 0) break;
                    clients[peer].control = fd == ctl;
                    watch(ep, peer, EPOLL_CTL_ADD, EPOLLIN);
                }
                continue;
            }
            Client& c = clients.at(fd);
            bool closed = events[i].events & (EPOLLERR | EPOLLHUP);
            if (!closed && c.output.empty() && (events[i].events & EPOLLIN)) {
                char buf[32768];
                auto n = recv(fd, buf, sizeof(buf), 0);
                if (n > 0) c.input.append(buf, static_cast<size_t>(n));
                else if (!n || (errno != EAGAIN && errno != EINTR)) closed = true;
                if (c.input.size() > body_limit + header_limit + 4 || (c.control && c.input.size() > 1024)) closed = true;
                if (!closed) prepare(c, requests, probe);
            }
            if (!closed && !c.output.empty()) {
                auto n = send(fd, c.output.data() + c.sent, c.output.size() - c.sent, MSG_NOSIGNAL);
                if (n > 0) c.sent += static_cast<size_t>(n);
                else if (n < 0 && errno != EAGAIN && errno != EINTR) closed = true;
                if (c.sent == c.output.size()) {
                    c.sent = 0; c.output.clear(); closed |= c.close_after;
                    if (!closed && !c.input.empty()) prepare(c, requests, probe);
                }
            }
            if (closed) { clients.erase(fd); close(fd); }
            else watch(ep, fd, EPOLL_CTL_MOD, c.output.empty() ? EPOLLIN : EPOLLOUT);
        }
    }
}
