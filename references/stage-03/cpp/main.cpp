#include <algorithm>
#include <array>
#include <cerrno>
#include <charconv>
#include <chrono>
#include <climits>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <list>
#include <memory>
#include <optional>
#include <string>
#include <string_view>
#include <unordered_map>
#include <utility>
#include <vector>
#include <arpa/inet.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <signal.h>
#include <sys/epoll.h>
#include <sys/sendfile.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <unistd.h>

using std::string;
using std::string_view;
using Clock = std::chrono::steady_clock;
static uint64_t now_ms() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now().time_since_epoch()).count();
}
static string_view trim(string_view v) {
    while (!v.empty() && (v.front() == ' ' || v.front() == '\t')) v.remove_prefix(1);
    while (!v.empty() && (v.back() == ' ' || v.back() == '\t')) v.remove_suffix(1);
    return v;
}
static string lower(string_view v) {
    string s(v);
    for (char& c : s) if (c >= 'A' && c <= 'Z') c += 'a' - 'A';
    return s;
}
static bool decimal(string_view v, uint64_t& n, bool saturate = false) {
    if (v.empty()) return false;
    n = 0;
    for (char c : v) {
        if (c < '0' || c > '9') return false;
        unsigned d = c - '0';
        if (n > (UINT64_MAX - d) / 10) {
            if (!saturate) return false;
            n = UINT64_MAX;
        } else n = n * 10 + d;
    }
    return true;
}
static bool token_char(unsigned char c) {
    return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
           (c >= '0' && c <= '9') || string_view("!#$%&'*+-.^_`|~").find(c) != string_view::npos;
}
static bool utf8(string_view s) {
    for (size_t i = 0; i < s.size();) {
        unsigned char a = s[i++];
        if (a < 128) continue;
        unsigned n, value, minimum;
        if (a >= 0xc2 && a <= 0xdf) { n = 1; value = a & 31; minimum = 0x80; }
        else if (a >= 0xe0 && a <= 0xef) { n = 2; value = a & 15; minimum = 0x800; }
        else if (a >= 0xf0 && a <= 0xf4) { n = 3; value = a & 7; minimum = 0x10000; }
        else return false;
        if (s.size() - i < n) return false;
        while (n--) {
            unsigned char b = s[i++];
            if ((b & 0xc0) != 0x80) return false;
            value = (value << 6) | (b & 63);
        }
        if (value < minimum || value > 0x10ffff || (value >= 0xd800 && value <= 0xdfff)) return false;
    }
    return true;
}
static bool hostname(string_view s) {
    if (s.empty() || s.size() > 253) return false;
    if (s.back() == '.') s.remove_suffix(1);
    if (s.empty()) return false;
    while (!s.empty()) {
        size_t end = s.find('.');
        string_view label = s.substr(0, end);
        if (label.empty() || label.size() > 63 || label.front() == '-' || label.back() == '-') return false;
        for (unsigned char c : label)
            if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
                  (c >= '0' && c <= '9') || c == '-')) return false;
        if (end == string_view::npos) break;
        s.remove_prefix(end + 1);
        if (s.empty()) return false;
    }
    return true;
}
static bool host_value(string_view value, string& name) {
    size_t colon = value.find(':');
    string_view h = value.substr(0, colon);
    if (!hostname(h)) return false;
    if (colon != string_view::npos) {
        string_view port = value.substr(colon + 1);
        if (port.empty()) return false;
        for (char ch : port) if (ch < '0' || ch > '9') return false;
    }
    name = lower(h);
    return true;
}
struct Directory {
    int fd = -1;
    ~Directory() { if (fd >= 0) close(fd); }
};
struct Config {
    sockaddr_storage address{};
    socklen_t address_len = 0;
    uint64_t max_connections, header_bytes, header_timeout, idle_timeout, write_timeout, max_requests, pipeline_depth;
    string default_host, second_host, alias_prefix, redirect_path, redirect_location, index;
    Directory root, host_root, alias_root;
};
static bool open_directory(string_view path, Directory& out) {
    if (path.empty() || path.front() != '/' || path.find('\0') != string_view::npos) return false;
    string p(path);
    out.fd = open(p.c_str(), O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NONBLOCK);
    return out.fd >= 0;
}
static bool load_config(const char* path, Config& c) {
    std::ifstream in(path);
    if (!in) return false;
    std::unordered_map<string, string> values;
    string line;
    const std::array<string_view, 14> keys = {"listen", "root", "max_connections", "header_bytes", "header_timeout_ms",
        "idle_timeout_ms", "write_timeout_ms", "max_requests", "pipeline_depth", "default_host", "host_root", "alias", "redirect", "index"};
    while (std::getline(in, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (!utf8(line) || line.find('\0') != string::npos) return false;
        string_view v = trim(line);
        if (v.empty() || v.front() == '#') continue;
        size_t equal = v.find('=');
        if (equal == string_view::npos) return false;
        string key(trim(v.substr(0, equal))), value(trim(v.substr(equal + 1)));
        if (std::find(keys.begin(), keys.end(), key) == keys.end() || value.empty() || values.contains(key)) return false;
        values.emplace(std::move(key), std::move(value));
    }
    if (!in.eof() || values.size() != 14) return false;
    auto number = [&](const char* key, uint64_t& n) {
        return decimal(values.at(key), n) && n > 0;
    };
    if (!number("max_connections", c.max_connections) || !number("header_bytes", c.header_bytes) ||
        !number("header_timeout_ms", c.header_timeout) || !number("idle_timeout_ms", c.idle_timeout) ||
        !number("write_timeout_ms", c.write_timeout) || !number("max_requests", c.max_requests) ||
        !number("pipeline_depth", c.pipeline_depth)) return false;
    string_view listen = values.at("listen");
    string address;
    string_view port_text;
    bool ipv6 = listen.front() == '[';
    if (ipv6) {
        size_t bracket = listen.find(']');
        if (bracket == string_view::npos || bracket + 1 >= listen.size() || listen[bracket + 1] != ':') return false;
        address = listen.substr(1, bracket - 1);
        port_text = listen.substr(bracket + 2);
    } else {
        size_t colon = listen.find(':');
        if (colon == string_view::npos) return false;
        address = listen.substr(0, colon);
        port_text = listen.substr(colon + 1);
    }
    uint64_t port;
    if (!decimal(port_text, port) || port == 0 || port > 65535) return false;
    if (ipv6) {
        auto* a = reinterpret_cast<sockaddr_in6*>(&c.address);
        a->sin6_family = AF_INET6; a->sin6_port = htons(port);
        if (inet_pton(AF_INET6, address.c_str(), &a->sin6_addr) != 1) return false;
        c.address_len = sizeof(*a);
    } else {
        auto* a = reinterpret_cast<sockaddr_in*>(&c.address);
        a->sin_family = AF_INET; a->sin_port = htons(port);
        if (inet_pton(AF_INET, address.c_str(), &a->sin_addr) != 1) return false;
        c.address_len = sizeof(*a);
    }
    c.default_host = lower(values.at("default_host"));
    if (!hostname(c.default_host)) return false;
    string_view mapping = values.at("host_root");
    size_t sep = mapping.find(':');
    if (sep == string_view::npos || !hostname(mapping.substr(0, sep))) return false;
    c.second_host = lower(mapping.substr(0, sep));
    if (c.second_host == c.default_host || !open_directory(mapping.substr(sep + 1), c.host_root)) return false;
    mapping = values.at("alias"); sep = mapping.find(':');
    if (sep == string_view::npos || mapping.front() != '/' || sep == 0 || !open_directory(mapping.substr(sep + 1), c.alias_root)) return false;
    c.alias_prefix = mapping.substr(0, sep);
    mapping = values.at("redirect"); sep = mapping.find(':');
    if (sep == string_view::npos || mapping.front() != '/' || sep == 0 || sep + 1 == mapping.size()) return false;
    c.redirect_path = mapping.substr(0, sep); c.redirect_location = mapping.substr(sep + 1);
    for (unsigned char ch : c.redirect_location) if (ch < 32 || ch == 127) return false;
    c.index = values.at("index");
    if (c.index == "." || c.index == ".." || c.index.find('/') != string::npos || c.index.find('\\') != string::npos) return false;
    for (unsigned char ch : c.alias_prefix) if (ch < 32 || ch == 127 || ch == '\\' || ch == '?' || ch == '#') return false;
    for (unsigned char ch : c.redirect_path) if (ch < 32 || ch == 127 || ch == '\\' || ch == '?' || ch == '#') return false;
    return open_directory(values.at("root"), c.root);
}
struct Request {
    bool head = false, close = false;
    string method, target, host, if_none_match, range;
};
static int parse_request(string_view data, const Config& c, Request& r) {
    size_t end = data.find("\r\n");
    if (end == string_view::npos) return 400;
    string_view first = data.substr(0, end);
    size_t a = first.find(' '), b = a == string_view::npos ? a : first.find(' ', a + 1);
    if (a == string_view::npos || b == string_view::npos || a == 0 || b == a + 1 || first.find(' ', b + 1) != string_view::npos) return 400;
    string_view method = first.substr(0, a), target = first.substr(a + 1, b - a - 1), version = first.substr(b + 1);
    for (unsigned char ch : method) if (!token_char(ch)) return 400;
    for (unsigned char ch : target) if (ch <= 32 || ch == 127) return 400;
    if (version != "HTTP/1.1" && version != "HTTP/1.0") return 400;
    r.method = method; r.target = target; r.head = method == "HEAD";
    r.close = version == "HTTP/1.0";
    bool got_host = false, got_length = false, got_range = false;
    for (size_t pos = end + 2; pos + 2 <= data.size();) {
        end = data.find("\r\n", pos);
        if (end == string_view::npos) return 400;
        string_view field = data.substr(pos, end - pos);
        pos = end + 2;
        if (field.empty()) break;
        size_t colon = field.find(':');
        if (colon == string_view::npos || colon == 0) return 400;
        for (unsigned char ch : field.substr(0, colon)) if (!token_char(ch)) return 400;
        string name = lower(field.substr(0, colon));
        string_view value = trim(field.substr(colon + 1));
        if (name == "host") {
            if (got_host || !host_value(value, r.host)) return 400;
            got_host = true;
        } else if (name == "content-length") {
            if (got_length || value.empty()) return 400;
            for (char ch : value) if (ch != '0') return 400;
            got_length = true;
        } else if (name == "transfer-encoding") return 400;
        else if (name == "connection") {
            while (!value.empty()) {
                size_t comma = value.find(',');
                if (lower(trim(value.substr(0, comma))) == "close") r.close = true;
                if (comma == string_view::npos) break;
                value.remove_prefix(comma + 1);
            }
        } else if (name == "if-none-match") {
            if (!r.if_none_match.empty()) r.if_none_match += ',';
            r.if_none_match += value;
        } else if (name == "range") {
            if (got_range) return 400;
            got_range = true; r.range = value;
            if (r.range.empty()) return 400;
        }
    }
    if (!got_host) {
        if (version == "HTTP/1.1") return 400;
        r.host = c.default_host;
    }
    if (r.host != c.default_host && r.host != c.second_host) return 400;
    return method == "GET" || method == "HEAD" ? 0 : 405;
}
static int decode_target(string_view target, string& path, string& original, string& query) {
    if (target.empty() || target.front() != '/' || target.find('#') != string_view::npos) return 400;
    size_t question = target.find('?');
    original = target.substr(0, question);
    if (question != string_view::npos) query = target.substr(question);
    target = target.substr(0, question);
    path.reserve(target.size());
    auto hex = [](char ch) -> int {
        if (ch >= '0' && ch <= '9') return ch - '0';
        if (ch >= 'a' && ch <= 'f') return ch - 'a' + 10;
        if (ch >= 'A' && ch <= 'F') return ch - 'A' + 10;
        return -1;
    };
    for (size_t i = 0; i < target.size(); ++i) {
        unsigned char ch = target[i];
        if (ch == '%') {
            if (i + 2 >= target.size()) return 400;
            int high = hex(target[i + 1]), low = hex(target[i + 2]);
            if (high < 0 || low < 0) return 400;
            ch = high * 16 + low; i += 2;
        }
        if (ch == 0 || ch == '\\') return 400;
        path += static_cast<char>(ch);
    }
    if (!utf8(path)) return 400;
    for (size_t pos = 0; pos < path.size();) {
        size_t slash = path.find('/', pos);
        if (path.substr(pos, slash == string::npos ? string::npos : slash - pos) == "..") return 403;
        if (slash == string::npos) break;
        pos = slash + 1;
    }
    return 0;
}
struct File {
    int fd;
    uint64_t size;
    string etag, mime;
    File(int f, const struct stat& st, string_view name) : fd(f), size(st.st_size) {
        char tag[192];
        std::snprintf(tag, sizeof(tag), "\"%llx-%llx-%llx-%llx-%llx\"",
            static_cast<unsigned long long>(st.st_dev), static_cast<unsigned long long>(st.st_ino),
            static_cast<unsigned long long>(st.st_size), static_cast<unsigned long long>(st.st_mtim.tv_sec),
            static_cast<unsigned long long>(st.st_mtim.tv_nsec));
        etag = tag;
        if (name.ends_with(".html")) mime = "text/html";
        else if (name.ends_with(".txt")) mime = "text/plain";
        else mime = "application/octet-stream";
    }
    ~File() { close(fd); }
};
struct Lookup { int status = 0; std::shared_ptr<File> file; };
class FileStore {
    struct Entry { std::shared_ptr<File> file; std::list<string>::iterator position; };
    std::unordered_map<string, Entry> cache;
    std::list<string> lru;
    static int error_status(int fd, const string& name, int error) {
        struct stat s;
        if (fstatat(fd, name.c_str(), &s, AT_SYMLINK_NOFOLLOW) == 0 &&
            (S_ISLNK(s.st_mode) || (!S_ISREG(s.st_mode) && !S_ISDIR(s.st_mode)))) return 403;
        return error == ENOENT || error == ENOTDIR ? 404 : 403;
    }
public:
    Lookup lookup(int root, string_view relative, bool trailing, const string& index) {
        string key = std::to_string(root) + ":" + string(relative) + (trailing ? "/" : "");
        auto hit = cache.find(key);
        if (hit != cache.end()) {
            lru.splice(lru.begin(), lru, hit->second.position);
            return {200, hit->second.file};
        }
        int current = root;
        bool owned = false;
        string name;
        struct stat st{};
        for (size_t pos = 0; pos < relative.size();) {
            size_t slash = relative.find('/', pos);
            string_view part = relative.substr(pos, slash == string_view::npos ? string_view::npos : slash - pos);
            if (!part.empty() && part != ".") {
                name = part;
                int next = openat(current, name.c_str(), O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC);
                if (next < 0) {
                    int status = error_status(current, name, errno);
                    if (owned) close(current);
                    return {status, {}};
                }
                if (owned) close(current);
                current = next; owned = true;
                if (fstat(current, &st) < 0) { close(current); return {403, {}}; }
                if (!S_ISREG(st.st_mode) && !S_ISDIR(st.st_mode)) { close(current); return {403, {}}; }
                if (slash != string_view::npos && !S_ISDIR(st.st_mode)) { close(current); return {404, {}}; }
            }
            if (slash == string_view::npos) break;
            pos = slash + 1;
        }
        if (!owned && fstat(current, &st) < 0) return {403, {}};
        if (S_ISDIR(st.st_mode)) {
            if (!trailing) { if (owned) close(current); return {301, {}}; }
            int next = openat(current, index.c_str(), O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC);
            if (owned) close(current);
            if (next < 0) return {403, {}};
            current = next; owned = true; name = index;
            if (fstat(current, &st) < 0 || !S_ISREG(st.st_mode)) { close(current); return {403, {}}; }
        } else if (trailing) { if (owned) close(current); return {404, {}}; }
        if (!S_ISREG(st.st_mode) || st.st_size < 0) { if (owned) close(current); return {403, {}}; }
        auto file = std::make_shared<File>(current, st, name);
        lru.push_front(key);
        cache.emplace(key, Entry{file, lru.begin()});
        while (cache.size() > 256) { cache.erase(lru.back()); lru.pop_back(); }
        return {200, std::move(file)};
    }
};
static bool conditional_match(string_view value, const string& tag) {
    value = trim(value);
    if (value == "*") return true;
    while (!value.empty()) {
        value = trim(value);
        if (value.starts_with("W/")) value.remove_prefix(2);
        if (value.empty() || value.front() != '"') return false;
        size_t quote = value.find('"', 1);
        if (quote == string_view::npos) return false;
        bool match = value.substr(0, quote + 1) == tag;
        value = trim(value.substr(quote + 1));
        if (!value.empty() && value.front() != ',') return false;
        if (match) return true;
        if (!value.empty()) value.remove_prefix(1);
    }
    return false;
}
static int byte_range(string_view value, uint64_t size, uint64_t& start, uint64_t& length) {
    if (value.size() < 6 || lower(value.substr(0, 6)) != "bytes=") return 400;
    value.remove_prefix(6);
    size_t dash = value.find('-');
    if (dash == string_view::npos) return 400;
    string_view left = value.substr(0, dash), right = value.substr(dash + 1);
    uint64_t a = 0, b = 0;
    if (left.empty()) {
        if (!decimal(right, b, true)) return 400;
        if (size == 0 || b == 0) return 416;
        length = std::min(b, size); start = size - length;
    } else {
        if (!decimal(left, a, true) || (!right.empty() && !decimal(right, b, true))) return 400;
        if (size == 0 || a >= size || (!right.empty() && b < a)) return 416;
        start = a;
        uint64_t last = right.empty() ? size - 1 : std::min(b, size - 1);
        length = last - a + 1;
    }
    return 206;
}
struct Response {
    string header;
    size_t header_sent = 0;
    std::shared_ptr<File> file;
    off_t offset = 0;
    uint64_t remaining = 0;
    bool close = false;
};
static string_view reason(int status) {
    switch (status) {
    case 200: return "OK"; case 206: return "Partial Content"; case 301: return "Moved Permanently";
    case 302: return "Found"; case 304: return "Not Modified"; case 400: return "Bad Request";
    case 403: return "Forbidden"; case 404: return "Not Found"; case 405: return "Method Not Allowed";
    case 408: return "Request Timeout"; case 416: return "Range Not Satisfiable";
    case 431: return "Request Header Fields Too Large"; default: return "Internal Server Error";
    }
}
static Response make_response(Request& r, const Config& c, FileStore& store, uint64_t count, int error = 0) {
    Response out;
    int status = error;
    string extra;
    uint64_t length = 0, start = 0;
    bool malformed = error == 400 || error == 431;
    if (status == 405) {
        string path, original, query;
        int decoded = decode_target(r.target, path, original, query);
        if (decoded == 400) { status = 400; malformed = true; }
    }
    if (!status) {
        string path, original, query;
        status = decode_target(r.target, path, original, query);
        if (status == 400) malformed = true;
        if (!status && path == c.redirect_path) {
            status = 302; extra = "Location: " + c.redirect_location + "\r\n";
        } else if (!status) {
            int root = r.host == c.second_host ? c.host_root.fd : c.root.fd;
            string_view relative(path);
            if (relative.starts_with(c.alias_prefix)) {
                relative.remove_prefix(c.alias_prefix.size()); root = c.alias_root.fd;
            }
            Lookup found = store.lookup(root, relative, path.ends_with('/'), c.index);
            status = found.status; out.file = std::move(found.file);
            if (status == 301) extra = "Location: " + original + "/" + query + "\r\n";
            if (out.file) {
                length = out.file->size;
                extra = "Content-Type: " + out.file->mime + "\r\nETag: " + out.file->etag + "\r\n";
                if (!r.if_none_match.empty() && conditional_match(r.if_none_match, out.file->etag)) {
                    status = 304; length = 0;
                } else if (!r.range.empty()) {
                    status = byte_range(r.range, out.file->size, start, length);
                    if (status == 206) extra += "Content-Range: bytes " + std::to_string(start) + "-" +
                        std::to_string(start + length - 1) + "/" + std::to_string(out.file->size) + "\r\n";
                    else {
                        length = 0;
                        if (status == 416) extra += "Content-Range: bytes */" + std::to_string(out.file->size) + "\r\n";
                        if (status == 400) malformed = true;
                    }
                }
            }
        }
    }
    out.close = r.close || malformed || count >= c.max_requests;
    out.header = "HTTP/1.1 " + std::to_string(status) + " " + string(reason(status)) + "\r\nContent-Length: " +
        std::to_string(length) + "\r\nConnection: " + (out.close ? "close\r\n" : "keep-alive\r\n") + extra + "\r\n";
    out.offset = static_cast<off_t>(start);
    if (!r.head && (status == 200 || status == 206)) out.remaining = length;
    if (out.remaining == 0) out.file.reset();
    return out;
}
struct Connection {
    int fd;
    uint64_t id, requests = 0, idle_since, header_since = 0, written_since = 0;
    string input;
    std::optional<Response> output;
    bool peer_eof = false, closing = false;
    uint32_t interest = EPOLLIN;
    Connection(int f, uint64_t identity, uint64_t now) : fd(f), id(identity), idle_since(now) {}
    ~Connection() { close(fd); }
};
class Server {
    Config& c;
    FileStore store;
    int listen_fd = -1, epoll_fd = -1;
    uint64_t serial = 1, active = 0;
    std::vector<std::unique_ptr<Connection>> slots;
    void remove(int fd) {
        epoll_ctl(epoll_fd, EPOLL_CTL_DEL, fd, nullptr);
        slots[fd].reset(); --active;
    }
    bool interest(Connection& con) {
        uint32_t desired = con.output ? EPOLLOUT : EPOLLIN;
        if (desired == con.interest) return true;
        epoll_event event{}; event.events = desired;
        event.data.u64 = con.id;
        if (epoll_ctl(epoll_fd, EPOLL_CTL_MOD, con.fd, &event) < 0) return false;
        con.interest = desired;
        return true;
    }
    bool prepare(Connection& con, uint64_t now) {
        size_t end = con.input.find("\r\n\r\n");
        size_t inspected = end == string::npos ? con.input.size() : end + 4;
        int error = 0;
        for (size_t i = 0; i < inspected; ++i) {
            char ch = con.input[i];
            if (ch == '\0' || (ch == '\n' && (i == 0 || con.input[i - 1] != '\r')) ||
                (ch == '\r' && i + 1 < inspected && con.input[i + 1] != '\n')) { error = 400; break; }
        }
        if (!error && (inspected > c.header_bytes || (end == string::npos && con.input.size() >= c.header_bytes))) error = 431;
        if (!error && end == string::npos) return true;
        Request request;
        if (!error) error = parse_request(string_view(con.input).substr(0, end + 4), c, request);
        if (error == 400 || error == 431) request.close = true;
        con.output = make_response(request, c, store, ++con.requests, error);
        con.written_since = now;
        if (end != string::npos && !request.close) con.input.erase(0, end + 4);
        else con.input.clear();
        if (con.input.empty()) con.header_since = 0;
        return true;
    }
    bool read(Connection& con, uint64_t now) {
        char buffer[16384];
        if (con.closing) {
            // A FIN lets the peer observe the final complete response. Keep
            // draining briefly so an unread pipeline cannot turn close into RST.
            size_t budget = 256 * 1024;
            while (budget) {
                ssize_t n = recv(con.fd, buffer, std::min(budget, sizeof(buffer)), 0);
                if (n > 0) budget -= n;
                else if (n < 0 && errno == EINTR) continue;
                else if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) return true;
                else return false;
            }
            return true;
        }
        if (!con.input.empty() && con.input.find("\r\n\r\n") == string::npos &&
            now - con.header_since >= c.header_timeout) return false;
        while (!con.output) {
            uint64_t room = c.header_bytes - std::min<uint64_t>(c.header_bytes, con.input.size());
            size_t cap = room >= sizeof(buffer) ? sizeof(buffer) : static_cast<size_t>(room) + 1;
            ssize_t n = recv(con.fd, buffer, cap, 0);
            if (n > 0) {
                if (con.input.empty()) con.header_since = now;
                con.input.append(buffer, n);
                prepare(con, now);
                if (con.output) break;
            } else if (n == 0) { con.peer_eof = true; break; }
            else if (errno == EINTR) continue;
            else if (errno == EAGAIN || errno == EWOULDBLOCK) break;
            else return false;
        }
        return con.output.has_value() || !con.peer_eof;
    }
    bool write(Connection& con, uint64_t now) {
        size_t budget = 256 * 1024;
        unsigned responses = 0;
        while (con.output) {
            Response& out = *con.output;
            while (out.header_sent < out.header.size()) {
                int flags = MSG_NOSIGNAL | (out.remaining ? MSG_MORE : 0);
                ssize_t n = send(con.fd, out.header.data() + out.header_sent, out.header.size() - out.header_sent, flags);
                if (n > 0) { out.header_sent += n; con.written_since = now; }
                else if (n < 0 && errno == EINTR) continue;
                else if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) return true;
                else return false;
            }
            while (out.remaining) {
                size_t bytes = std::min<uint64_t>(out.remaining, budget);
                ssize_t n = sendfile(con.fd, out.file->fd, &out.offset, bytes);
                if (n > 0) {
                    out.remaining -= n; budget -= n; con.written_since = now;
                    if (!budget && out.remaining) return true;
                } else if (n < 0 && errno == EINTR) continue;
                else if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) return true;
                else return false;
            }
            if (out.close) {
                if (shutdown(con.fd, SHUT_WR) < 0) return false;
                con.output.reset(); con.input.clear(); con.header_since = 0;
                con.closing = true; con.idle_since = now;
                return read(con, now);
            }
            con.output.reset(); con.idle_since = now;
            if (!con.input.empty()) prepare(con, now);
            else if (con.peer_eof) return false;
            if (++responses >= 16 || !budget) break;
        }
        return true;
    }
    void accept_connections(uint64_t now) {
        for (unsigned i = 0; i < 256; ++i) {
            int fd = accept4(listen_fd, nullptr, nullptr, SOCK_NONBLOCK | SOCK_CLOEXEC);
            if (fd < 0) { if (errno == EINTR) continue; break; }
            if (active >= c.max_connections) { close(fd); continue; }
            int yes = 1;
            setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &yes, sizeof(yes));
            if (static_cast<size_t>(fd) >= slots.size()) slots.resize(fd + 1024);
            uint64_t id = (++serial << 32) | static_cast<uint32_t>(fd);
            auto con = std::make_unique<Connection>(fd, id, now);
            epoll_event event{}; event.events = EPOLLIN; event.data.u64 = id;
            if (epoll_ctl(epoll_fd, EPOLL_CTL_ADD, fd, &event) < 0) continue;
            slots[fd] = std::move(con); ++active;
        }
    }
    void sweep(uint64_t now) {
        for (auto& ptr : slots) if (ptr) {
            Connection& con = *ptr;
            bool expired = con.closing ? now - con.idle_since >= std::min<uint64_t>(250, c.idle_timeout) :
                con.output ? now - con.written_since >= c.write_timeout :
                !con.input.empty() ? now - con.header_since >= c.header_timeout : now - con.idle_since >= c.idle_timeout;
            if (!con.closing && !con.input.empty() && con.input.find("\r\n\r\n") == string::npos &&
                now - con.header_since >= c.header_timeout) expired = true;
            if (expired) remove(con.fd);
        }
    }
public:
    explicit Server(Config& config) : c(config), slots(16384) {}
    ~Server() { if (listen_fd >= 0) close(listen_fd); if (epoll_fd >= 0) close(epoll_fd); }
    bool run() {
        listen_fd = socket(c.address.ss_family, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
        if (listen_fd < 0) return false;
        int yes = 1;
        setsockopt(listen_fd, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes));
        if (bind(listen_fd, reinterpret_cast<sockaddr*>(&c.address), c.address_len) < 0 || listen(listen_fd, 8192) < 0) return false;
        epoll_fd = epoll_create1(EPOLL_CLOEXEC);
        if (epoll_fd < 0) return false;
        epoll_event listener{}; listener.events = EPOLLIN; listener.data.u64 = 0;
        if (epoll_ctl(epoll_fd, EPOLL_CTL_ADD, listen_fd, &listener) < 0) return false;
        std::array<epoll_event, 512> events;
        uint64_t next_sweep = now_ms() + 10;
        while (true) {
            int n = epoll_wait(epoll_fd, events.data(), events.size(), 10);
            if (n < 0) { if (errno == EINTR) continue; return false; }
            uint64_t now = now_ms();
            for (int i = 0; i < n; ++i) {
                auto event = events[i];
                if (event.data.u64 == 0) { accept_connections(now); continue; }
                int fd = static_cast<uint32_t>(event.data.u64);
                if (static_cast<size_t>(fd) >= slots.size() || !slots[fd] || slots[fd]->id != event.data.u64) continue;
                Connection& con = *slots[fd];
                bool ok = !(event.events & EPOLLERR);
                if (ok && !con.output && (event.events & (EPOLLIN | EPOLLRDHUP | EPOLLHUP))) ok = read(con, now);
                if (ok && con.output) ok = write(con, now);
                if (ok) ok = interest(con);
                if (!ok) remove(fd);
            }
            if (now >= next_sweep) { sweep(now); next_sweep = now + 10; }
        }
    }
};
int main(int argc, char** argv) {
    if (argc != 3 || std::strcmp(argv[1], "--config") != 0) return 1;
    signal(SIGPIPE, SIG_IGN);
    try {
        Config config;
        if (!load_config(argv[2], config)) { std::fputs("Invalid configuration\n", stderr); return 1; }
        Server server(config);
        return server.run() ? 0 : 1;
    } catch (...) { return 1; }
}
