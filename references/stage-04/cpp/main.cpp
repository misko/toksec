#include <algorithm>
#include <array>
#include <cerrno>
#include <charconv>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <deque>
#include <fcntl.h>
#include <fstream>
#include <iostream>
#include <limits>
#include <memory>
#include <netdb.h>
#include <netinet/tcp.h>
#include <optional>
#include <queue>
#include <set>
#include <signal.h>
#include <string>
#include <string_view>
#include <sys/epoll.h>
#include <sys/sendfile.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <unistd.h>
#include <unordered_map>
#include <vector>

using namespace std;
using Clock = chrono::steady_clock;
static int64_t nowms() {
    return chrono::duration_cast<chrono::milliseconds>(Clock::now().time_since_epoch()).count();
}
static string lower(string_view s) {
    string r(s);
    for (char &c : r)
        if (c >= 'A' && c <= 'Z')
            c += 32;
    return r;
}
static string trim(string_view s) {
    while (!s.empty() && (s.front() == ' ' || s.front() == '\t'))
        s.remove_prefix(1);
    while (!s.empty() && (s.back() == ' ' || s.back() == '\t' || s.back() == '\r'))
        s.remove_suffix(1);
    return string(s);
}
static bool number(string_view s, uint64_t &v, int base = 10) {
    if (s.empty())
        return false;
    v = 0;
    for (unsigned char c : s) {
        unsigned d =
            c >= '0' && c <= '9'
                ? c - '0'
                : c >= 'a' && c <= 'f' ? c - 'a' + 10 : c >= 'A' && c <= 'F' ? c - 'A' + 10 : 99;
        if (d >= unsigned(base) || v > (UINT64_MAX - d) / base)
            return false;
        v = v * base + d;
    }
    return true;
}
static bool token(string_view s) {
    if (s.empty())
        return false;
    for (unsigned char c : s)
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') ||
              string_view("!#$%&'*+-.^_`|~").find(c) != string_view::npos))
            return false;
    return true;
}
static vector<string> tokens(string_view s) {
    vector<string> r;
    while (true) {
        auto p = s.find(',');
        r.push_back(lower(trim(s.substr(0, p))));
        if (p == s.npos)
            break;
        s.remove_prefix(p + 1);
    }
    return r;
}
static bool utf8(string_view s) {
    size_t i = 0;
    while (i < s.size()) {
        unsigned c = (unsigned char)s[i++];
        if (c < 128)
            continue;
        unsigned n = 0, cp = 0, min = 0;
        if (c >= 0xc2 && c <= 0xdf) {
            n = 1;
            cp = c & 31;
            min = 128;
        } else if (c >= 0xe0 && c <= 0xef) {
            n = 2;
            cp = c & 15;
            min = 2048;
        } else if (c >= 0xf0 && c <= 0xf4) {
            n = 3;
            cp = c & 7;
            min = 65536;
        } else
            return false;
        if (i + n > s.size())
            return false;
        while (n--) {
            unsigned d = (unsigned char)s[i++];
            if ((d & 192) != 128)
                return false;
            cp = cp * 64 + (d & 63);
        }
        if (cp < min || cp > 0x10ffff || (cp >= 0xd800 && cp <= 0xdfff))
            return false;
    }
    return true;
}
struct Endpoint {
    sockaddr_storage address{};
    socklen_t length = 0;
    string authority;
};
static bool endpoint(const string &s, Endpoint &e) {
    auto p = s.rfind(':');
    if (p == string::npos)
        return false;
    string host = s.substr(0, p), port = s.substr(p + 1);
    if (host.size() > 2 && host.front() == '[' && host.back() == ']')
        host = host.substr(1, host.size() - 2);
    uint64_t v;
    if (!number(port, v) || v == 0 || v > 65535)
        return false;
    addrinfo hints{}, *res = nullptr;
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_flags = AI_NUMERICSERV;
    if (getaddrinfo(host.c_str(), port.c_str(), &hints, &res))
        return false;
    bool ok = res && res->ai_addrlen <= sizeof(e.address);
    if (ok) {
        memcpy(&e.address, res->ai_addr, res->ai_addrlen);
        e.length = res->ai_addrlen;
        e.authority = s;
    }
    if (res)
        freeaddrinfo(res);
    return ok;
}
static bool hostname(string_view s) {
    if (s.empty() || s.size() > 253)
        return false;
    for (unsigned char c : s)
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') ||
              c == '-' || c == '.'))
            return false;
    return s.front() != '.' && s.back() != '.' && s.find("..") == s.npos;
}
static optional<string> hostvalue(string_view s) {
    if (s.find_first_of(" \t\r\n") != s.npos)
        return {};
    auto p = s.find(':');
    if (p != s.npos) {
        uint64_t v;
        if (!number(s.substr(p + 1), v) || v > 65535 || v == 0)
            return {};
        s = s.substr(0, p);
    }
    if (!hostname(s))
        return {};
    return lower(s);
}
// Configuration is fully validated before the listener is created.
struct Config {
    Endpoint listen;
    string root, hostroot, defhost, otherhost, alias, aliasroot, redirect, location, index, prefix;
    vector<Endpoint> upstreams;
    uint64_t maxconn = 0, headers = 0, headertime = 0, idletime = 0, writetime = 0, maxrequests = 0,
             pipeline = 0, uptime = 0, bodylimit = 0;
    int rootfd = -1, hostfd = -1, aliasfd = -1;
} cfg;
static bool directory(const string &s, int &fd) {
    if (s.empty() || s[0] != '/' || !utf8(s) || s.find('\0') != string::npos)
        return false;
    fd = open(s.c_str(), O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    return fd >= 0;
}
static bool config(const string &path) {
    ifstream f(path);
    if (!f)
        return false;
    unordered_map<string, string> m;
    string line;
    while (getline(f, line)) {
        line = trim(line);
        if (line.empty() || line[0] == '#')
            continue;
        auto p = line.find('=');
        if (p == string::npos)
            return false;
        string k = trim(string_view(line).substr(0, p)), v = trim(string_view(line).substr(p + 1));
        if (!utf8(v) || v.find('\0') != string::npos || !m.emplace(k, v).second)
            return false;
    }
    const vector<string> keys = {"listen",
                                 "root",
                                 "max_connections",
                                 "header_bytes",
                                 "header_timeout_ms",
                                 "idle_timeout_ms",
                                 "write_timeout_ms",
                                 "max_requests",
                                 "pipeline_depth",
                                 "default_host",
                                 "host_root",
                                 "alias",
                                 "redirect",
                                 "index",
                                 "proxy_prefix",
                                 "upstreams",
                                 "upstream_timeout_ms",
                                 "body_bytes"};
    if (m.size() != keys.size())
        return false;
    for (auto &k : keys)
        if (!m.count(k))
            return false;
    auto num = [&](const char *k, uint64_t &v) {
        return number(m[k], v) && v > 0 && v <= INT64_MAX / 4;
    };
    if (!num("max_connections", cfg.maxconn) || !num("header_bytes", cfg.headers) ||
        !num("header_timeout_ms", cfg.headertime) || !num("idle_timeout_ms", cfg.idletime) ||
        !num("write_timeout_ms", cfg.writetime) || !num("max_requests", cfg.maxrequests) ||
        !num("pipeline_depth", cfg.pipeline) || !num("upstream_timeout_ms", cfg.uptime) ||
        !num("body_bytes", cfg.bodylimit))
        return false;
    if (!endpoint(m["listen"], cfg.listen))
        return false;
    cfg.root = m["root"];
    cfg.defhost = lower(m["default_host"]);
    if (!hostname(cfg.defhost))
        return false;
    auto p = m["host_root"].find(':');
    if (p == string::npos)
        return false;
    cfg.otherhost = lower(m["host_root"].substr(0, p));
    cfg.hostroot = m["host_root"].substr(p + 1);
    if (!hostname(cfg.otherhost) || cfg.otherhost == cfg.defhost)
        return false;
    p = m["alias"].find(':');
    if (p == string::npos)
        return false;
    cfg.alias = m["alias"].substr(0, p);
    cfg.aliasroot = m["alias"].substr(p + 1);
    p = m["redirect"].find(':');
    if (p == string::npos)
        return false;
    cfg.redirect = m["redirect"].substr(0, p);
    cfg.location = m["redirect"].substr(p + 1);
    cfg.index = m["index"];
    cfg.prefix = m["proxy_prefix"];
    for (auto &s : {cfg.alias, cfg.redirect, cfg.location, cfg.prefix})
        if (s.empty() || s[0] != '/' || s.find_first_of("\r\n\0") != string::npos)
            return false;
    if (cfg.alias.back() != '/' || cfg.prefix.back() != '/' || cfg.index.empty() ||
        cfg.index == "." || cfg.index == ".." || cfg.index.find_first_of("/\\\r\n") != string::npos)
        return false;
    string_view all = m["upstreams"];
    while (true) {
        auto x = all.find(',');
        Endpoint e;
        if (!endpoint(trim(all.substr(0, x)), e))
            return false;
        cfg.upstreams.push_back(e);
        if (x == all.npos)
            break;
        all.remove_prefix(x + 1);
    }
    return directory(cfg.root, cfg.rootfd) && directory(cfg.hostroot, cfg.hostfd) &&
           directory(cfg.aliasroot, cfg.aliasfd);
}
struct Header {
    string name, value;
};
struct Message {
    string method, target, version, path, query, host, proxyTarget;
    vector<Header> headers;
    set<string> hop;
    bool head = false, close = false, proxy = false, chunked = false;
    uint64_t length = 0;
};
static bool headerlines(string_view s, vector<Header> &h) {
    while (!s.empty()) {
        auto p = s.find("\r\n");
        if (p == s.npos)
            return false;
        auto l = s.substr(0, p);
        s.remove_prefix(p + 2);
        if (l.empty())
            return s.empty();
        auto c = l.find(':');
        if (c == l.npos || !token(l.substr(0, c)))
            return false;
        auto value = l.substr(c + 1);
        for (unsigned char a : value)
            if (a == 0 || a == 127 || (a < 32 && a != '\t'))
                return false;
        h.push_back({lower(l.substr(0, c)), trim(value)});
    }
    return true;
}
static int parse(Message &r, string_view raw) {
    auto p = raw.find("\r\n");
    if (p == raw.npos)
        return 400;
    auto line = raw.substr(0, p);
    auto x = line.find(' '), y = x == line.npos ? line.npos : line.find(' ', x + 1);
    if (x == line.npos || y == line.npos || line.find(' ', y + 1) != line.npos ||
        !token(line.substr(0, x)) || y == x + 1)
        return 400;
    r.method = string(line.substr(0, x));
    r.target = string(line.substr(x + 1, y - x - 1));
    r.version = string(line.substr(y + 1));
    r.head = r.method == "HEAD";
    if (r.version != "HTTP/1.1" && r.version != "HTTP/1.0")
        return 400;
    if (!headerlines(raw.substr(p + 2), r.headers))
        return 400;
    int hosts = 0, lengths = 0, tes = 0;
    string host, te;
    for (auto &h : r.headers) {
        if (h.name == "host") {
            ++hosts;
            host = h.value;
        } else if (h.name == "content-length") {
            ++lengths;
            if (!number(h.value, r.length))
                return 400;
        } else if (h.name == "transfer-encoding") {
            ++tes;
            te = lower(h.value);
        } else if (h.name == "connection") {
            for (auto &t : tokens(h.value)) {
                if (!token(t))
                    return 400;
                r.hop.insert(t);
            }
        }
    }
    if (lengths > 1 || tes > 1 || (lengths && tes))
        return 400;
    if (hosts > 1 || (!hosts && r.version == "HTTP/1.1"))
        return 400;
    if (hosts) {
        auto h = hostvalue(host);
        if (!h)
            return 400;
        r.host = *h;
    } else
        r.host = cfg.defhost;
    if (r.host != cfg.defhost && r.host != cfg.otherhost)
        return 400;
    r.close = r.version == "HTTP/1.0" || r.hop.count("close");
    if (r.target.empty() || r.target[0] != '/' || r.target.find('#') != string::npos)
        return 400;
    auto q = r.target.find('?');
    r.query = q == string::npos ? "" : r.target.substr(q);
    string_view encoded(r.target.data(), q == string::npos ? r.target.size() : q);
    r.path.reserve(encoded.size());
    for (size_t i = 0; i < encoded.size(); ++i) {
        unsigned char c = encoded[i];
        if (c == '%') {
            if (i + 2 >= encoded.size())
                return 400;
            uint64_t v;
            if (!number(encoded.substr(i + 1, 2), v, 16))
                return 400;
            c = v;
            i += 2;
        }
        if (c == 0 || c == '\\' || c < 32 || c == 127)
            return 400;
        r.path += char(c);
        if (r.path.size() == cfg.prefix.size() && r.path == cfg.prefix)
            r.proxyTarget = "/" + string(encoded.substr(i + 1));
    }
    if (!utf8(r.path))
        return 400;
    size_t b = 0;
    while (b < r.path.size()) {
        auto e = r.path.find('/', b);
        if (e == string::npos)
            e = r.path.size();
        if (r.path.substr(b, e - b) == "..")
            return 403;
        b = e + 1;
    }
    r.proxy = r.path.starts_with(cfg.prefix);
    if (tes) {
        if (!r.proxy || te != "chunked")
            return 400;
        r.chunked = true;
    }
    if (!r.proxy && r.length)
        return 400;
    if (r.proxy && r.length > cfg.bodylimit)
        return 413;
    if (r.method != "GET" && r.method != "HEAD" && !(r.proxy && r.method == "POST"))
        return 405;
    return 0;
}
static string field(const vector<Header> &h, string_view name) {
    string r;
    for (auto &x : h)
        if (x.name == name) {
            if (!r.empty())
                r += ",";
            r += x.value;
        }
    return r;
}
static bool badlines(string_view b) {
    for (size_t i = 0; i < b.size(); ++i)
        if (b[i] == 0 || (b[i] == '\n' && (i == 0 || b[i - 1] != '\r')) ||
            (b[i] == '\r' && i + 1 < b.size() && b[i + 1] != '\n'))
            return true;
    return false;
}
static bool extensions(string_view s) {
    while (!s.empty()) {
        if (s.front() != ';')
            return false;
        s.remove_prefix(1);
        while (!s.empty() && (s.front() == ' ' || s.front() == '\t'))
            s.remove_prefix(1);
        size_t n = 0;
        while (n < s.size() && token(s.substr(n, 1)))
            ++n;
        if (!n)
            return false;
        s.remove_prefix(n);
        while (!s.empty() && (s.front() == ' ' || s.front() == '\t'))
            s.remove_prefix(1);
        if (!s.empty() && s.front() == '=') {
            s.remove_prefix(1);
            while (!s.empty() && (s.front() == ' ' || s.front() == '\t'))
                s.remove_prefix(1);
            if (s.empty())
                return false;
            if (s.front() == '"') {
                s.remove_prefix(1);
                bool ended = false;
                while (!s.empty()) {
                    unsigned char c = s.front();
                    s.remove_prefix(1);
                    if (c == '"') {
                        ended = true;
                        break;
                    }
                    if (c == '\\') {
                        if (s.empty())
                            return false;
                        c = s.front();
                        s.remove_prefix(1);
                    }
                    if ((c < 32 && c != '\t') || c == 127)
                        return false;
                }
                if (!ended)
                    return false;
            } else {
                n = 0;
                while (n < s.size() && token(s.substr(n, 1)))
                    ++n;
                if (!n)
                    return false;
                s.remove_prefix(n);
            }
            while (!s.empty() && (s.front() == ' ' || s.front() == '\t'))
                s.remove_prefix(1);
        }
    }
    return true;
}
struct Chunk {
    int state = 0;
    uint64_t remaining = 0;
    size_t trailers = 0;
};
// 0 incomplete, 1 complete, 400 malformed, 413 limit exceeded.
static int chunks(Chunk &c, string &in, string &out, uint64_t limit) {
    while (true) {
        if (c.state == 0) {
            auto e = in.find("\r\n");
            if (e == string::npos) {
                if (in.size() > 8192 || badlines(in))
                    return 400;
                return 0;
            }
            auto line = string_view(in).substr(0, e);
            auto sem = line.find(';');
            uint64_t n;
            if (!number(line.substr(0, sem), n, 16))
                return 400;
            if (sem != line.npos && !extensions(line.substr(sem)))
                return 400;
            if (n > limit - out.size())
                return 413;
            in.erase(0, e + 2);
            c.remaining = n;
            c.state = n ? 1 : 3;
        } else if (c.state == 1) {
            size_t n = min<uint64_t>(in.size(), c.remaining);
            out.append(in, 0, n);
            in.erase(0, n);
            c.remaining -= n;
            if (c.remaining)
                return 0;
            c.state = 2;
        } else if (c.state == 2) {
            if (in.size() < 2) {
                if (!in.empty() && in[0] != '\r')
                    return 400;
                return 0;
            }
            if (in.compare(0, 2, "\r\n"))
                return 400;
            in.erase(0, 2);
            c.state = 0;
        } else {
            auto e = in.find("\r\n");
            if (e == string::npos) {
                if (in.size() + c.trailers > cfg.headers || badlines(in))
                    return 400;
                return 0;
            }
            c.trailers += e + 2;
            if (c.trailers > cfg.headers)
                return 400;
            if (e == 0) {
                in.erase(0, 2);
                return 1;
            }
            vector<Header> h;
            if (!headerlines(string_view(in).substr(0, e + 2), h) || h.empty())
                return 400;
            for (auto &v : h)
                if (v.name == "content-length" || v.name == "transfer-encoding" || v.name == "host")
                    return 400;
            in.erase(0, e + 2);
        }
    }
}
struct File {
    int fd = -1;
    uint64_t size = 0;
    string etag, mime;
    ~File() {
        if (fd >= 0)
            ::close(fd);
    }
};
static unordered_map<string, shared_ptr<File>> files;
// Walk each component through directory descriptors. O_NOFOLLOW rejects symlinks,
// and O_NONBLOCK prevents a FIFO from blocking before fstat rejects it.
static shared_ptr<File> getfile(const Message &r, int &status, string &location) {
    int root = r.host == cfg.otherhost ? cfg.hostfd : cfg.rootfd;
    string rel = r.path.substr(1);
    if (r.path.starts_with(cfg.alias)) {
        root = cfg.aliasfd;
        rel = r.path.substr(cfg.alias.size());
    }
    string key = to_string(root) + ":" + rel;
    auto cached = files.find(key);
    if (cached != files.end())
        return cached->second;
    vector<string> parts;
    size_t p = 0;
    while (p < rel.size()) {
        auto e = rel.find('/', p);
        if (e == string::npos)
            e = rel.size();
        auto s = rel.substr(p, e - p);
        if (!s.empty() && s != ".")
            parts.push_back(s);
        p = e + 1;
    }
    int fd = dup(root);
    if (fd < 0) {
        status = 500;
        return {};
    }
    for (auto &s : parts) {
        int next = openat(fd, s.c_str(), O_RDONLY | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK);
        int er = errno;
        ::close(fd);
        if (next < 0) {
            status = er == ENOENT || er == ENOTDIR ? 404 : 403;
            return {};
        }
        fd = next;
        struct stat st {};
        if (fstat(fd, &st) || (!S_ISDIR(st.st_mode) && &s != &parts.back())) {
            ::close(fd);
            status = 403;
            return {};
        }
    }
    struct stat st {};
    if (fstat(fd, &st)) {
        ::close(fd);
        status = 403;
        return {};
    }
    string name = rel;
    if (S_ISDIR(st.st_mode)) {
        if (r.path.back() != '/') {
            ::close(fd);
            status = 301;
            location = r.path + "/" + r.query;
            return {};
        }
        int next = openat(fd, cfg.index.c_str(), O_RDONLY | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK);
        ::close(fd);
        if (next < 0) {
            status = 403;
            return {};
        }
        fd = next;
        if (fstat(fd, &st)) {
            ::close(fd);
            status = 403;
            return {};
        }
        name = cfg.index;
    } else if (r.path.back() == '/') {
        ::close(fd);
        status = 403;
        return {};
    }
    if (!S_ISREG(st.st_mode)) {
        ::close(fd);
        status = 403;
        return {};
    }
    auto f = make_shared<File>();
    f->fd = fd;
    f->size = st.st_size;
    f->etag = "\"" + to_string(uint64_t(st.st_ino)) + "-" + to_string(f->size) + "-" +
              to_string(st.st_mtim.tv_sec) + "-" + to_string(st.st_mtim.tv_nsec) + "\"";
    f->mime = name.ends_with(".html")
                  ? "text/html"
                  : name.ends_with(".txt") ? "text/plain" : "application/octet-stream";
    if (files.size() >= 512)
        files.clear();
    files.emplace(key, f);
    return f;
}
enum class CState { Header, Body, Slot, Upstream, Write, Drain };
struct Conn {
    int fd = -1;
    uint32_t gen = 0;
    CState state = CState::Header;
    string in, upload, out, body;
    size_t sent = 0, bsent = 0;
    Message req;
    Chunk chunk;
    uint64_t responses = 0, remaining = 0;
    off_t offset = 0;
    shared_ptr<File> file;
    bool close = false, hasSlot = false, peerEOF = false;
    int upstream = -1, attempt = 0;
    size_t selected = 0;
    int64_t deadline = 0;
    uint64_t timer = 0;
};
struct Up {
    int fd = -1, owner = -1;
    uint32_t gen = 0;
    size_t selected = 0;
    bool connecting = false, headers = false, chunked = false, reuse = true, eofbody = false;
    int status = 0;
    string in, out, body;
    size_t sent = 0;
    uint64_t length = 0;
    vector<Header> fields;
    set<string> hop;
    Chunk chunk;
    int64_t deadline = 0;
    uint64_t timer = 0;
};
static int ep = -1, listener = -1;
static uint32_t serial = 0;
static unordered_map<int, unique_ptr<Conn>> clients;
static unordered_map<int, unique_ptr<Up>> ups;
// An fd alone is not an identity: an expired socket's descriptor can be reused
// for a socket connected to a different authority before its old idle entry is
// visited. Keep the registration generation with every pool entry.
static vector<vector<pair<int, uint32_t>>> idle;
static deque<pair<int, uint32_t>> waiters;
static size_t rr = 0,
              slots =
                  0; // Keep proxy upload, upstream response, and stalled downstream buffers bounded
// independently of the number of accepted clients. A slot survives until the
// downstream response is completely sent.
static constexpr size_t SLOT_LIMIT = 64;
// Generation and timer IDs reject stale events after descriptors are reused.
struct Timer {
    int64_t at;
    int fd;
    uint32_t gen;
    uint64_t id;
    bool upstream;
    bool operator<(const Timer &t) const { return at > t.at; }
};
static priority_queue<Timer> timers;
static void watch(int fd, uint32_t gen, uint32_t events, bool add = false) {
    epoll_event e{};
    e.events = events;
    auto ci = clients.find(fd);
    if (ci == clients.end() || !ci->second->peerEOF)
        e.events |= EPOLLRDHUP;
    e.data.u64 = (uint64_t(gen) << 32) | uint32_t(fd);
    epoll_ctl(ep, add ? EPOLL_CTL_ADD : EPOLL_CTL_MOD, fd, &e);
}
static void deadline(Conn &c, int64_t at) {
    c.deadline = at;
    ++c.timer;
    timers.push({at, c.fd, c.gen, c.timer, false});
}
static void deadline(Up &u, int64_t at) {
    u.deadline = at;
    ++u.timer;
    timers.push({at, u.fd, u.gen, u.timer, true});
}
static void closeup(int fd) {
    auto it = ups.find(fd);
    if (it == ups.end())
        return;
    epoll_ctl(ep, EPOLL_CTL_DEL, fd, nullptr);
    ::close(fd);
    ups.erase(it);
}
static void closeclient(int fd) {
    auto it = clients.find(fd);
    if (it == clients.end())
        return;
    auto &c = *it->second;
    if (c.upstream >= 0)
        closeup(c.upstream);
    if (c.hasSlot) {
        --slots;
        c.hasSlot = false;
    }
    epoll_ctl(ep, EPOLL_CTL_DEL, fd, nullptr);
    ::close(fd);
    clients.erase(it);
}
static string response(int status, uint64_t len, bool close, const string &extra = "") {
    return "HTTP/1.1 " + to_string(status) + " Response\r\nContent-Length: " + to_string(len) +
           "\r\nConnection: " + (close ? "close" : "keep-alive") + "\r\n" + extra + "\r\n";
}
static void writeclient(int fd);
static void readclient(int fd);
static void progress(int fd);
static void beginproxy(int fd, bool retry = false);
static void finishresponse(Conn &c, int status, uint64_t len, const string &extra = "",
                           bool forceclose = false) {
    c.state = CState::Write;
    c.close = forceclose || c.req.close || c.responses + 1 >= cfg.maxrequests ||
              (c.peerEOF && c.in.empty());
    c.out = response(status, len, c.close, extra);
    c.sent = c.bsent = 0;
    deadline(c, nowms() + cfg.writetime);
    watch(c.fd, c.gen, EPOLLOUT);
}
static void errorresponse(Conn &c, int status, bool close = true) {
    c.file.reset();
    c.body.clear();
    finishresponse(c, status, 0, "", close);
}
static void local(Conn &c) {
    if (c.req.path == cfg.redirect) {
        finishresponse(c, 302, 0, "Location: " + cfg.location + "\r\n");
        return;
    }
    int status = 200;
    string loc;
    auto f = getfile(c.req, status, loc);
    if (!f) {
        finishresponse(c, status, 0, loc.empty() ? "" : "Location: " + loc + "\r\n");
        return;
    }
    string extra = "ETag: " + f->etag + "\r\nContent-Type: " + f->mime + "\r\n";
    auto cond = field(c.req.headers, "if-none-match");
    bool match = false;
    for (auto &tag : tokens(cond)) {
        if (tag == "*" || tag == lower(f->etag) || tag == "w/" + lower(f->etag))
            match = true;
    }
    if (match) {
        finishresponse(c, 304, 0, "ETag: " + f->etag + "\r\n");
        return;
    }
    uint64_t start = 0, len = f->size;
    string range = field(c.req.headers, "range");
    bool hasrange = any_of(c.req.headers.begin(), c.req.headers.end(),
                           [](auto &h) { return h.name == "range"; });
    if (hasrange) {
        if (!range.starts_with("bytes=") || range.find(',') != string::npos) {
            errorresponse(c, 400);
            return;
        }
        string_view v(range);
        v.remove_prefix(6);
        auto dash = v.find('-');
        uint64_t a = 0, b = 0;
        if (dash == v.npos || v.find('-', dash + 1) != v.npos || (dash == 0 && v.size() == 1) ||
            (dash && !number(v.substr(0, dash), a)) ||
            (dash + 1 < v.size() && !number(v.substr(dash + 1), b))) {
            errorresponse(c, 400);
            return;
        }
        bool unsat = false;
        if (dash == 0) {
            if (!b || !f->size)
                unsat = true;
            else {
                len = min(b, f->size);
                start = f->size - len;
            }
        } else {
            start = a;
            if (start >= f->size)
                unsat = true;
            else if (dash + 1 == v.size())
                len = f->size - start;
            else if (b < a)
                unsat = true;
            else
                len = min(b, f->size - 1) - start + 1;
        }
        if (unsat) {
            finishresponse(c, 416, 0, "Content-Range: bytes */" + to_string(f->size) + "\r\n");
            return;
        }
        status = 206;
        extra += "Content-Range: bytes " + to_string(start) + "-" + to_string(start + len - 1) +
                 "/" + to_string(f->size) + "\r\n";
    }
    if (!c.req.head) {
        c.file = f;
        c.offset = start;
        c.remaining = len;
    }
    finishresponse(c, status, len, extra);
}
static bool hop(string_view name, const set<string> &extra) {
    static const set<string> fixed = {
        "connection", "keep-alive", "proxy-connection",   "transfer-encoding",  "te",
        "trailer",    "upgrade",    "proxy-authenticate", "proxy-authorization"};
    return fixed.count(string(name)) || extra.count(string(name));
}
static void proxyfailure(int fd, bool timeout) {
    auto ci = clients.find(fd);
    if (ci == clients.end())
        return;
    auto &c = *ci->second;
    if (c.upstream >= 0) {
        closeup(c.upstream);
        c.upstream = -1;
    }
    if (c.attempt == 0 && (c.req.method == "GET" || c.req.method == "HEAD")) {
        ++c.attempt;
        beginproxy(fd, true);
        return;
    }
    if (c.hasSlot) {
        --slots;
        c.hasSlot = false;
    }
    errorresponse(c, timeout ? 504 : 502);
    writeclient(fd);
}
static void completeup(int upfd) {
    auto ui = ups.find(upfd);
    if (ui == ups.end())
        return;
    auto &u = *ui->second;
    auto ci = clients.find(u.owner);
    if (ci == clients.end()) {
        closeup(upfd);
        return;
    }
    auto &c = *ci->second;
    c.upstream = -1;
    string extra;
    for (auto &h : u.fields)
        if (h.name != "content-length" && !hop(h.name, u.hop))
            extra += h.name + ": " + h.value + "\r\n";
    uint64_t len = c.req.head ? u.length : u.body.size();
    if (u.status == 204 || u.status == 304)
        len = 0;
    if (!c.req.head)
        c.body = move(u.body);
    int status = u.status;
    bool reuse = u.reuse && !u.eofbody && u.in.empty();
    if (reuse) {
        u.owner = -1;
        u.out.clear();
        u.in.clear();
        u.fields.clear();
        u.body.clear();
        ++u.timer;
        idle[u.selected].emplace_back(upfd, u.gen);
        watch(upfd, u.gen, EPOLLIN);
        deadline(u, nowms() + cfg.idletime);
    } else
        closeup(upfd);
    finishresponse(c, status, len, extra);
    writeclient(c.fd);
}
static void readup(int fd) {
    auto it = ups.find(fd);
    if (it == ups.end())
        return;
    auto &u = *it->second;
    if (u.owner < 0) {
        char b;
        ssize_t n = recv(fd, &b, 1, MSG_PEEK);
        if (n != -1 || (errno != EAGAIN && errno != EWOULDBLOCK))
            closeup(fd);
        return;
    }
    int owner = u.owner;
    auto ci = clients.find(owner);
    if (ci == clients.end()) {
        closeup(fd);
        return;
    }
    bool eof = false;
    char buf[65536];
    size_t total = 0;
    while (total < 262144) {
        ssize_t n = recv(fd, buf, sizeof(buf), 0);
        bool fresh = n > 0;
        if (n > 0) {
            u.in.append(buf, n);
            total += n;
        } else if (n == 0) {
            eof = true;
            if (u.in.empty())
                break;
        } else if (errno == EAGAIN || errno == EWOULDBLOCK) {
            if (u.in.empty())
                break;
        } else if (errno != EINTR) {
            proxyfailure(owner, false);
            return;
        }
        if (!u.headers) {
            auto p = u.in.find("\r\n\r\n");
            if (p == string::npos) {
                if (u.in.size() > cfg.headers || badlines(u.in)) {
                    proxyfailure(owner, false);
                    return;
                }
                if (!fresh)
                    break;
                continue;
            }
            if (p + 4 > cfg.headers || badlines(string_view(u.in).substr(0, p + 4))) {
                proxyfailure(owner, false);
                return;
            }
            auto lineend = u.in.find("\r\n");
            auto line = string_view(u.in).substr(0, lineend);
            if (!(line.starts_with("HTTP/1.1 ") || line.starts_with("HTTP/1.0 ")) ||
                line.size() < 13 || line[12] != ' ') {
                proxyfailure(owner, false);
                return;
            }
            uint64_t status;
            if (!number(line.substr(9, 3), status) || status < 100 || status > 599 ||
                !headerlines(string_view(u.in).substr(lineend + 2, p + 4 - lineend - 2),
                             u.fields)) {
                proxyfailure(owner, false);
                return;
            }
            u.status = status;
            u.reuse = line.starts_with("HTTP/1.1");
            int cls = 0, tes = 0;
            string te;
            for (auto &h : u.fields) {
                if (h.name == "content-length") {
                    ++cls;
                    if (!number(h.value, u.length)) {
                        proxyfailure(owner, false);
                        return;
                    }
                } else if (h.name == "transfer-encoding") {
                    ++tes;
                    te = lower(h.value);
                } else if (h.name == "connection") {
                    for (auto &t : tokens(h.value)) {
                        if (!token(t)) {
                            proxyfailure(owner, false);
                            return;
                        }
                        u.hop.insert(t);
                    }
                }
            }
            if (cls > 1 || tes > 1 || (cls && tes) || (tes && te != "chunked") ||
                (u.length > cfg.bodylimit && !ci->second->req.head && status != 204 &&
                 status != 304)) {
                proxyfailure(owner, false);
                return;
            }
            if (u.hop.count("close"))
                u.reuse = false;
            u.chunked = tes;
            u.eofbody = !cls && !tes;
            u.in.erase(0, p + 4);
            u.headers = true;
            if (status >= 100 && status < 200) {
                if (status == 101) {
                    proxyfailure(owner, false);
                    return;
                }
                u.headers = false;
                u.fields.clear();
                u.hop.clear();
                u.length = 0;
                continue;
            }
            if (ci->second->req.head || status == 204 || status == 304) {
                if (!u.in.empty()) {
                    proxyfailure(owner, false);
                    return;
                }
                completeup(fd);
                return;
            }
        }
        if (u.headers) {
            if (u.chunked) {
                int result = chunks(u.chunk, u.in, u.body, cfg.bodylimit);
                if (result >= 400) {
                    proxyfailure(owner, false);
                    return;
                }
                if (result == 1) {
                    if (!u.in.empty()) {
                        proxyfailure(owner, false);
                        return;
                    }
                    u.length = u.body.size();
                    completeup(fd);
                    return;
                }
                if (!fresh)
                    break;
            } else if (u.eofbody) {
                if (u.in.size() > cfg.bodylimit - u.body.size()) {
                    proxyfailure(owner, false);
                    return;
                }
                u.body += u.in;
                u.in.clear();
            } else {
                if (u.in.size() > u.length - u.body.size()) {
                    proxyfailure(owner, false);
                    return;
                }
                u.body += u.in;
                u.in.clear();
                if (u.body.size() == u.length) {
                    completeup(fd);
                    return;
                }
            }
        }
        if (eof)
            break;
    }
    if (eof) {
        if (u.headers && u.eofbody) {
            u.reuse = false;
            u.length = u.body.size();
            completeup(fd);
        } else
            proxyfailure(owner, false);
    }
}
static void writeup(int fd) {
    auto it = ups.find(fd);
    if (it == ups.end())
        return;
    auto &u = *it->second;
    int owner = u.owner;
    if (u.connecting) {
        int er = 0;
        socklen_t n = sizeof(er);
        if (getsockopt(fd, SOL_SOCKET, SO_ERROR, &er, &n) || er) {
            proxyfailure(owner, false);
            return;
        }
        u.connecting = false;
    }
    while (u.sent < u.out.size()) {
        auto n = send(fd, u.out.data() + u.sent, u.out.size() - u.sent, MSG_NOSIGNAL);
        if (n > 0)
            u.sent += n;
        else if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
            watch(fd, u.gen, EPOLLOUT);
            return;
        } else if (n < 0 && errno == EINTR)
            continue;
        else {
            proxyfailure(owner, false);
            return;
        }
    }
    if (u.out.capacity() > 65536)
        string().swap(u.out);
    else
        u.out.clear();
    watch(fd, u.gen, EPOLLIN);
    readup(fd);
}
static void beginproxy(int fd, bool retry) {
    auto it = clients.find(fd);
    if (it == clients.end())
        return;
    auto &c = *it->second;
    size_t selected = retry ? (c.selected + 1) % cfg.upstreams.size() : rr++ % cfg.upstreams.size();
    c.selected = selected;
    int upfd = -1;
    while (!idle[selected].empty()) {
        auto [v, gen] = idle[selected].back();
        idle[selected].pop_back();
        auto u = ups.find(v);
        if (u != ups.end() && u->second->gen == gen &&
            u->second->selected == selected && u->second->owner < 0) {
            upfd = v;
            break;
        }
    }
    if (upfd < 0) {
        if (ups.size() >= 256) {
            vector<int> remove;
            for (auto &[v, p] : ups)
                if (p->owner < 0)
                    remove.push_back(v);
            for (int v : remove) {
                closeup(v);
                if (ups.size() < 192)
                    break;
            }
        }
        auto &e = cfg.upstreams[selected];
        upfd = socket(e.address.ss_family, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
        if (upfd < 0) {
            proxyfailure(fd, false);
            return;
        }
        int one = 1;
        setsockopt(upfd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof(one));
        auto u = make_unique<Up>();
        u->fd = upfd;
        u->gen = ++serial;
        u->selected = selected;
        u->connecting = true;
        ups.emplace(upfd, move(u));
        watch(upfd, ups[upfd]->gen, EPOLLOUT, true);
        if (connect(upfd, reinterpret_cast<sockaddr *>(&e.address), e.length) < 0 &&
            errno != EINPROGRESS) {
            c.upstream = upfd;
            proxyfailure(fd, false);
            return;
        }
    }
    auto &u = *ups[upfd];
    c.upstream = upfd;
    c.state = CState::Upstream;
    ++c.timer;
    u.owner = fd;
    u.headers = false;
    u.chunked = false;
    u.reuse = true;
    u.eofbody = false;
    u.status = 0;
    u.in.clear();
    u.body.clear();
    u.fields.clear();
    u.hop.clear();
    u.chunk = Chunk{};
    u.length = 0;
    u.sent = 0;
    u.out = c.req.method + " " + c.req.proxyTarget + c.req.query +
            " HTTP/1.1\r\nHost: " + cfg.upstreams[selected].authority + "\r\n";
    for (auto &h : c.req.headers)
        if (h.name != "host" && h.name != "content-length" && !hop(h.name, c.req.hop))
            u.out += h.name + ": " + h.value + "\r\n";
    if (c.req.method == "POST" || !c.upload.empty())
        u.out += "Content-Length: " + to_string(c.upload.size()) + "\r\n";
    u.out += "Connection: keep-alive\r\n\r\n";
    u.out += c.upload;
    watch(fd, c.gen, 0);
    deadline(u, nowms() + cfg.uptime);
    writeup(upfd);
}
static bool slot(Conn &c) {
    if (c.hasSlot)
        return true;
    // Preserve admission order even when a completed response released a slot
    // earlier in the current epoll batch. Otherwise a busy client's next request
    // can take that slot before wakewaiters() visits older queued requests.
    if (slots >= SLOT_LIMIT || !waiters.empty()) {
        c.state = CState::Slot;
        waiters.emplace_back(c.fd, c.gen);
        watch(c.fd, c.gen, 0);
        ++c.timer;
        return false;
    }
    ++slots;
    c.hasSlot = true;
    return true;
}
static void progress(int fd) {
    auto it = clients.find(fd);
    if (it == clients.end())
        return;
    auto &c = *it->second;
    if (c.state == CState::Header) {
        auto p = c.in.find("\r\n\r\n");
        if (p == string::npos) {
            if (badlines(c.in)) {
                errorresponse(c, 400);
                return;
            }
            if (c.in.size() >= cfg.headers) {
                errorresponse(c, 431);
                return;
            }
            return;
        }
        if (p + 4 > cfg.headers) {
            errorresponse(c, 431);
            return;
        }
        if (badlines(string_view(c.in).substr(0, p + 4))) {
            errorresponse(c, 400);
            return;
        }
        c.req = Message{};
        int status = parse(c.req, string_view(c.in).substr(0, p + 4));
        c.in.erase(0, p + 4);
        if (status) {
            errorresponse(c, status);
            return;
        }
        if (!c.req.proxy) {
            local(c);
            return;
        }
        if (!slot(c))
            return;
        c.state = CState::Body;
        c.upload.clear();
        c.chunk = Chunk{};
        deadline(c, nowms() + cfg.headertime);
    }
    if (c.state == CState::Body) {
        if (c.req.chunked) {
            int result = chunks(c.chunk, c.in, c.upload, cfg.bodylimit);
            if (result >= 400) {
                if (c.hasSlot) {
                    --slots;
                    c.hasSlot = false;
                }
                errorresponse(c, result);
                return;
            }
            if (result == 0)
                return;
        } else {
            size_t n = min<uint64_t>(c.in.size(), c.req.length - c.upload.size());
            c.upload.append(c.in, 0, n);
            c.in.erase(0, n);
            if (c.upload.size() < c.req.length)
                return;
        }
        c.attempt = 0;
        beginproxy(fd);
    }
}
// A FIN followed by bounded input draining preserves completed responses when
// extra pipelined input remains; closing immediately could send TCP RST.
static void drainclient(int fd) {
    auto it = clients.find(fd);
    if (it == clients.end())
        return;
    auto &c = *it->second;
    c.state = CState::Drain;
    c.in.clear();
    shutdown(fd, SHUT_WR);
    char b[16384];
    for (size_t work = 0; work < 262144;) {
        ssize_t n = recv(fd, b, sizeof(b), 0);
        if (n > 0)
            work += n;
        else if (n == 0) {
            closeclient(fd);
            return;
        } else if (errno == EINTR)
            continue;
        else if (errno == EAGAIN || errno == EWOULDBLOCK)
            break;
        else {
            closeclient(fd);
            return;
        }
    }
    watch(fd, c.gen, EPOLLIN);
    deadline(c, nowms() + min<uint64_t>(cfg.idletime, 1000));
}
static void readclient(int fd) {
    auto it = clients.find(fd);
    if (it == clients.end())
        return;
    auto &c = *it->second;
    if (c.state == CState::Drain) {
        drainclient(fd);
        return;
    }
    char b[16384];
    size_t total = 0;
    while (c.state == CState::Header || c.state == CState::Body) {
        size_t room = c.state == CState::Header
                          ? (cfg.headers >= c.in.size()
                                 ? min<uint64_t>(sizeof(b), cfg.headers - c.in.size() + 1)
                                 : 1)
                          : sizeof(b);
        ssize_t n = recv(fd, b, room, 0);
        if (n > 0) {
            if (c.state == CState::Header && c.in.empty())
                deadline(c, nowms() + cfg.headertime);
            c.in.append(b, n);
            total += n;
            progress(fd);
            if (!clients.count(fd))
                return;
            if (total >= 131072)
                break;
        } else if (n == 0) {
            c.peerEOF = true;
            if (c.state == CState::Header && c.in.empty()) {
                closeclient(fd);
                return;
            }
            errorresponse(c, 400);
            break;
        } else if (errno == EAGAIN || errno == EWOULDBLOCK)
            break;
        else if (errno != EINTR) {
            closeclient(fd);
            return;
        }
    }
    if (clients.count(fd) && c.state == CState::Write)
        writeclient(fd);
}
static void writeclient(int fd) {
    size_t work = 0;
    for (int count = 0; count < 16; ++count) {
        auto it = clients.find(fd);
        if (it == clients.end())
            return;
        auto &c = *it->second;
        if (c.state != CState::Write)
            return;
        while (c.sent < c.out.size()) {
            ssize_t n = send(fd, c.out.data() + c.sent, c.out.size() - c.sent, MSG_NOSIGNAL);
            if (n > 0) {
                c.sent += n;
                work += n;
                deadline(c, nowms() + cfg.writetime);
            } else if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK))
                return;
            else if (n < 0 && errno == EINTR)
                continue;
            else {
                closeclient(fd);
                return;
            }
        }
        while (c.file && c.remaining) {
            ssize_t n = sendfile(fd, c.file->fd, &c.offset, min<uint64_t>(c.remaining, 1048576));
            if (n > 0) {
                c.remaining -= n;
                work += n;
                deadline(c, nowms() + cfg.writetime);
                if (work >= 1048576)
                    return;
            } else if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK))
                return;
            else if (n < 0 && errno == EINTR)
                continue;
            else {
                closeclient(fd);
                return;
            }
        }
        while (c.bsent < c.body.size()) {
            ssize_t n = send(fd, c.body.data() + c.bsent, c.body.size() - c.bsent, MSG_NOSIGNAL);
            if (n > 0) {
                c.bsent += n;
                work += n;
                deadline(c, nowms() + cfg.writetime);
                if (work >= 1048576)
                    return;
            } else if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK))
                return;
            else if (n < 0 && errno == EINTR)
                continue;
            else {
                closeclient(fd);
                return;
            }
        }
        ++c.responses;
        if (c.hasSlot) {
            --slots;
            c.hasSlot = false;
        }
        c.file.reset();
        c.remaining = 0;
        c.out.clear();
        string().swap(c.body);
        string().swap(c.upload);
        if (c.close) {
            drainclient(fd);
            return;
        }
        c.state = CState::Header;
        c.req = Message{};
        deadline(c, nowms() + (c.in.empty() ? cfg.idletime : cfg.headertime));
        watch(fd, c.gen, EPOLLIN);
        if (c.in.empty())
            return;
        progress(fd);
        if (!clients.count(fd))
            return;
        if (c.state != CState::Write) {
            if (c.state == CState::Header || c.state == CState::Body)
                readclient(fd);
            return;
        }
    }
}
// Retired timers are periodically discarded so long configured deadlines do
// not make request throughput turn into unbounded retained timer storage.
static void compacttimers() {
    if (waiters.size() > 2 * clients.size() + 4096) {
        deque<pair<int, uint32_t>> live;
        for (auto [fd, gen] : waiters) {
            auto it = clients.find(fd);
            if (it != clients.end() && it->second->gen == gen &&
                it->second->state == CState::Slot)
                live.emplace_back(fd, gen);
        }
        waiters.swap(live);
    }
    if (timers.size() < 8 * (clients.size() + ups.size()) + 4096)
        return;
    priority_queue<Timer> fresh;
    for (auto &[fd, p] : clients)
        if (p->state != CState::Upstream && p->state != CState::Slot)
            fresh.push({p->deadline, fd, p->gen, p->timer, false});
    for (auto &[fd, p] : ups)
        fresh.push({p->deadline, fd, p->gen, p->timer, true});
    timers.swap(fresh);
}
static void wakewaiters() {
    size_t n = waiters.size();
    while (slots < SLOT_LIMIT && n-- && !waiters.empty()) {
        auto [fd, gen] = waiters.front();
        waiters.pop_front();
        auto it = clients.find(fd);
        if (it == clients.end() || it->second->gen != gen || it->second->state != CState::Slot)
            continue;
        auto &c = *it->second;
        ++slots;
        c.hasSlot = true;
        c.state = CState::Body;
        c.chunk = Chunk{};
        c.upload.clear();
        deadline(c, nowms() + cfg.headertime);
        watch(fd, c.gen, EPOLLIN);
        progress(fd);
        if (clients.count(fd) && (c.state == CState::Header || c.state == CState::Body))
            readclient(fd);
    }
}
int main(int argc, char **argv) {
    signal(SIGPIPE, SIG_IGN);
    if (argc != 3 || string(argv[1]) != "--config" || !config(argv[2]))
        return 1;
    idle.resize(cfg.upstreams.size());
    ep = epoll_create1(EPOLL_CLOEXEC);
    listener = socket(cfg.listen.address.ss_family, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
    if (ep < 0 || listener < 0)
        return 1;
    int one = 1;
    setsockopt(listener, SOL_SOCKET, SO_REUSEADDR, &one, sizeof(one));
    if (bind(listener, reinterpret_cast<sockaddr *>(&cfg.listen.address), cfg.listen.length) ||
        listen(listener, 16384))
        return 1;
    watch(listener, 0, EPOLLIN, true);
    array<epoll_event, 512> events;
    while (true) {
        int64_t now = nowms();
        while (!timers.empty() && timers.top().at <= now) {
            auto t = timers.top();
            timers.pop();
            if (t.upstream) {
                auto it = ups.find(t.fd);
                if (it == ups.end() || it->second->gen != t.gen || it->second->timer != t.id)
                    continue;
                if (it->second->owner < 0)
                    closeup(t.fd);
                else
                    proxyfailure(it->second->owner, true);
            } else {
                auto it = clients.find(t.fd);
                if (it != clients.end() && it->second->gen == t.gen && it->second->timer == t.id)
                    closeclient(t.fd);
            }
        }
        wakewaiters();
        compacttimers();
        int timeout =
            timers.empty() ? 1000 : int(clamp<int64_t>(timers.top().at - nowms(), 0, 1000));
        int n = epoll_wait(ep, events.data(), events.size(), timeout);
        if (n < 0) {
            if (errno == EINTR)
                continue;
            return 1;
        }
        for (int i = 0; i < n; ++i) {
            int fd = uint32_t(events[i].data.u64);
            uint32_t gen = events[i].data.u64 >> 32;
            auto ev = events[i].events;
            if (fd == listener && gen == 0) {
                for (int k = 0; k < 256; ++k) {
                    int cfd = accept4(listener, nullptr, nullptr, SOCK_NONBLOCK | SOCK_CLOEXEC);
                    if (cfd < 0)
                        break;
                    if (clients.size() >= cfg.maxconn) {
                        ::close(cfd);
                        continue;
                    }
                    setsockopt(cfd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof(one));
                    auto c = make_unique<Conn>();
                    c->fd = cfd;
                    c->gen = ++serial;
                    auto &ref = *c;
                    clients.emplace(cfd, move(c));
                    watch(cfd, ref.gen, EPOLLIN, true);
                    deadline(ref, nowms() + cfg.idletime);
                }
                continue;
            }
            auto ci = clients.find(fd);
            if (ci != clients.end() && ci->second->gen == gen) {
                if (ev & EPOLLERR) {
                    closeclient(fd);
                    continue;
                }
                if ((ev & EPOLLIN) &&
                    (ci->second->state == CState::Header || ci->second->state == CState::Body ||
                     ci->second->state == CState::Drain))
                    readclient(fd);
                ci = clients.find(fd);
                if (ci != clients.end() && ci->second->gen == gen && (ev & EPOLLOUT))
                    writeclient(fd);
                ci = clients.find(fd);
                if (ci != clients.end() && ci->second->gen == gen &&
                    (ev & (EPOLLHUP | EPOLLRDHUP))) {
                    auto &c = *ci->second;
                    c.peerEOF = true;
                    if (c.state == CState::Header || c.state == CState::Body ||
                        c.state == CState::Drain)
                        readclient(fd);
                    else
                        watch(fd, c.gen, c.state == CState::Write ? uint32_t(EPOLLOUT) : 0u);
                }
                continue;
            }
            auto ui = ups.find(fd);
            if (ui != ups.end() && ui->second->gen == gen) {
                if (ev & EPOLLERR) {
                    if (ui->second->owner < 0)
                        closeup(fd);
                    else
                        proxyfailure(ui->second->owner, false);
                    continue;
                }
                if (ev & EPOLLOUT)
                    writeup(fd);
                ui = ups.find(fd);
                if (ui != ups.end() && ui->second->gen == gen &&
                    (ev & (EPOLLIN | EPOLLRDHUP | EPOLLHUP)))
                    readup(fd);
            }
        }
    }
}
