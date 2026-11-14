use std::collections::{HashMap, HashSet, VecDeque};
use std::ffi::{c_void, CString};
use std::fs::{self, File};
use std::io::{self, Read, Write};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::fs::MetadataExt;
use std::path::PathBuf;
use std::sync::Arc;
use std::time::{Duration, Instant};

// Linux OS primitives only; all protocol parsing remains in this file.
#[repr(C, packed)]
#[derive(Clone, Copy)]
struct Event {
    events: u32,
    data: u64,
}
#[repr(C)]
struct SockAddrIn {
    family: u16,
    port: u16,
    address: u32,
    zero: [u8; 8],
}
#[repr(C)]
struct SockAddrIn6 {
    family: u16,
    port: u16,
    flowinfo: u32,
    address: [u8; 16],
    scope_id: u32,
}
unsafe extern "C" {
    fn epoll_create1(flags: i32) -> i32;
    fn epoll_ctl(ep: i32, op: i32, fd: i32, ev: *mut Event) -> i32;
    fn epoll_wait(ep: i32, events: *mut Event, count: i32, timeout: i32) -> i32;
    fn sendfile(out_fd: i32, in_fd: i32, offset: *mut i64, count: usize) -> isize;
    fn socket(domain: i32, kind: i32, protocol: i32) -> i32;
    fn connect(fd: i32, addr: *const c_void, len: u32) -> i32;
    fn listen(fd: i32, backlog: i32) -> i32;
    fn openat(fd: i32, path: *const i8, flags: i32, ...) -> i32;
    fn signal(sig: i32, handler: usize) -> usize;
    fn setsockopt(fd: i32, level: i32, name: i32, value: *const c_void, len: u32) -> i32;
}
const IN: u32 = 1;
const OUT: u32 = 4;
const RDHUP: u32 = 0x2000;
const UP: u64 = 1 << 63;
fn trim(mut b: &[u8]) -> &[u8] {
    while matches!(b.first(), Some(b' ' | b'\t')) {
        b = &b[1..];
    }
    while matches!(b.last(), Some(b' ' | b'\t')) {
        b = &b[..b.len() - 1];
    }
    b
}
fn token(b: &[u8]) -> bool {
    !b.is_empty()
        && b.iter()
            .all(|c| c.is_ascii_alphanumeric() || b"!#$%&'*+-.^_`|~".contains(c))
}
fn decimal(b: &[u8]) -> Option<usize> {
    if b.is_empty() || !b.iter().all(u8::is_ascii_digit) {
        return None;
    }
    b.iter().try_fold(0usize, |n, c| {
        n.checked_mul(10)?.checked_add((c - b'0') as usize)
    })
}
fn host(b: &[u8]) -> Option<String> {
    let s = std::str::from_utf8(trim(b)).ok()?;
    let mut it = s.split(':');
    let h = it.next()?;
    if h.is_empty()
        || !h
            .bytes()
            .all(|c| c.is_ascii_alphanumeric() || c == b'.' || c == b'-')
    {
        return None;
    }
    if let Some(p) = it.next() {
        if decimal(p.as_bytes())? > 65535 {
            return None;
        }
    }
    if it.next().is_some() {
        return None;
    }
    Some(h.to_ascii_lowercase())
}
fn dir(s: &str) -> Result<PathBuf, String> {
    let p = PathBuf::from(s);
    if !p.is_absolute() || !fs::metadata(&p).map_err(|e| e.to_string())?.is_dir() {
        return Err("invalid directory".into());
    }
    Ok(p)
}
struct Config {
    listen: SocketAddr,
    root: File,
    beta: File,
    alias: File,
    beta_host: String,
    default_host: String,
    alias_prefix: String,
    redir_path: String,
    redir_to: String,
    index: String,
    proxy_prefix: String,
    upstreams: Vec<SocketAddr>,
    max_connections: usize,
    header_bytes: usize,
    header_timeout: Duration,
    idle_timeout: Duration,
    write_timeout: Duration,
    max_requests: usize,
    pipeline_depth: usize,
    upstream_timeout: Duration,
    body_bytes: usize,
}
impl Config {
    fn load(path: &str) -> Result<Self, String> {
        let allowed = [
            "listen",
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
            "body_bytes",
        ];
        let text = fs::read_to_string(path).map_err(|e| e.to_string())?;
        let mut m = HashMap::new();
        for l in text.lines() {
            let l = l.trim();
            if l.is_empty() || l.starts_with('#') {
                continue;
            }
            let (k, v) = l.split_once('=').ok_or("config line")?;
            let k = k.trim();
            let v = v.trim();
            if !allowed.contains(&k) || m.insert(k.to_string(), v.to_string()).is_some() {
                return Err("config key".into());
            }
        }
        if m.len() != allowed.len() {
            return Err("missing key".into());
        }
        let get = |k: &str| m.get(k).unwrap().as_str();
        let num = |k: &str| -> Result<usize, String> {
            let n = decimal(get(k).as_bytes()).ok_or("invalid number")?;
            if n == 0 || n > isize::MAX as usize {
                Err("invalid limit".into())
            } else {
                Ok(n)
            }
        };
        let timeout = |k: &str| -> Result<Duration, String> {
            Ok(Duration::from_millis(
                u64::try_from(num(k)?).map_err(|_| "timeout")?,
            ))
        };
        let listen = get("listen").parse::<SocketAddr>().map_err(|_| "listen")?;
        if listen.port() == 0 {
            return Err("listen".into());
        }
        let root = File::open(dir(get("root"))?).map_err(|e| e.to_string())?;
        let (bh, bp) = get("host_root").split_once(':').ok_or("host_root")?;
        let beta_host = host(bh.as_bytes()).ok_or("host_root host")?;
        let beta = File::open(dir(bp)?).map_err(|e| e.to_string())?;
        let default_host = host(get("default_host").as_bytes()).ok_or("default_host")?;
        if beta_host == default_host {
            return Err("duplicate hosts".into());
        }
        let (ap, ad) = get("alias").split_once(':').ok_or("alias")?;
        if !ap.starts_with('/') || !ap.ends_with('/') || ap.contains(['?', '#', '\\', '\0']) {
            return Err("alias".into());
        }
        let alias = File::open(dir(ad)?).map_err(|e| e.to_string())?;
        let (rp, rt) = get("redirect").split_once(':').ok_or("redirect")?;
        if !rp.starts_with('/')
            || rt.is_empty()
            || rp.contains(['?', '#', '\r', '\n', '\0'])
            || rt.contains(['\r', '\n', '\0'])
        {
            return Err("redirect".into());
        }
        let index = get("index");
        if index.is_empty() || index == "." || index == ".." || index.contains(['/', '\\', '\0']) {
            return Err("index".into());
        }
        let prefix = get("proxy_prefix");
        if !prefix.starts_with('/')
            || !prefix.ends_with('/')
            || prefix.contains(['?', '#', '\\', '\0'])
        {
            return Err("proxy_prefix".into());
        }
        let mut upstreams = Vec::new();
        for s in get("upstreams").split(',') {
            let a = s.parse::<SocketAddr>().map_err(|_| "upstreams")?;
            if a.port() == 0 {
                return Err("upstream address".into());
            }
            upstreams.push(a);
        }
        if upstreams.is_empty() {
            return Err("upstreams".into());
        }
        Ok(Self {
            listen,
            root,
            beta,
            alias,
            beta_host,
            default_host,
            alias_prefix: ap.into(),
            redir_path: rp.into(),
            redir_to: rt.into(),
            index: index.into(),
            proxy_prefix: prefix.into(),
            upstreams,
            max_connections: num("max_connections")?,
            header_bytes: num("header_bytes")?,
            header_timeout: timeout("header_timeout_ms")?,
            idle_timeout: timeout("idle_timeout_ms")?,
            write_timeout: timeout("write_timeout_ms")?,
            max_requests: num("max_requests")?,
            pipeline_depth: num("pipeline_depth")?,
            upstream_timeout: timeout("upstream_timeout_ms")?,
            body_bytes: num("body_bytes")?,
        })
    }
}
#[derive(Clone)]
struct Header {
    name: String,
    value: Vec<u8>,
}
fn fields(raw: &[u8]) -> Result<Vec<Header>, u16> {
    let mut hs = Vec::new();
    for line in raw.split_inclusive(|b| *b == b'\n') {
        let line = line.strip_suffix(b"\r\n").ok_or(400u16)?;
        if line.is_empty() {
            return Err(400);
        }
        let colon = line.iter().position(|b| *b == b':').ok_or(400u16)?;
        if !token(&line[..colon]) {
            return Err(400);
        }
        let val = trim(&line[colon + 1..]);
        if val.iter().any(|c| (*c < 32 && *c != b'\t') || *c == 127) {
            return Err(400);
        }
        hs.push(Header {
            name: String::from_utf8(line[..colon].to_ascii_lowercase()).unwrap(),
            value: val.to_vec(),
        });
    }
    Ok(hs)
}
fn values<'a>(hs: &'a [Header], n: &'a str) -> impl Iterator<Item = &'a [u8]> {
    hs.iter()
        .filter(move |h| h.name == n)
        .map(|h| h.value.as_slice())
}
fn connection_tokens(hs: &[Header]) -> HashSet<String> {
    values(hs, "connection")
        .flat_map(|v| v.split(|c| *c == b','))
        .filter_map(|v| {
            std::str::from_utf8(trim(v))
                .ok()
                .map(str::to_ascii_lowercase)
        })
        .collect()
}
fn blocked(name: &str, tokens: &HashSet<String>) -> bool {
    matches!(
        name,
        "connection"
            | "keep-alive"
            | "proxy-connection"
            | "transfer-encoding"
            | "te"
            | "trailer"
            | "upgrade"
            | "proxy-authenticate"
            | "proxy-authorization"
    ) || tokens.contains(name)
}
fn end_headers(b: &[u8]) -> Option<usize> {
    b.windows(4).position(|w| w == b"\r\n\r\n").map(|p| p + 4)
}
fn invalid_lines(b: &[u8]) -> bool {
    b.iter().enumerate().any(|(i, c)| {
        *c == 0
            || (*c == b'\n' && (i == 0 || b[i - 1] != b'\r'))
            || (*c == b'\r' && i + 1 < b.len() && b[i + 1] != b'\n')
    })
}
fn path_decode(raw: &[u8]) -> Result<(String, String), u16> {
    if !raw.starts_with(b"/") || raw.contains(&b'#') || raw.iter().any(|b| *b <= 32 || *b == 127) {
        return Err(400);
    }
    let p = raw.iter().position(|b| *b == b'?').unwrap_or(raw.len());
    let mut out = Vec::new();
    let mut i = 0;
    while i < p {
        if raw[i] == b'%' {
            if i + 2 >= p {
                return Err(400);
            }
            let a = (raw[i + 1] as char).to_digit(16).ok_or(400u16)?;
            let b = (raw[i + 2] as char).to_digit(16).ok_or(400u16)?;
            out.push((a * 16 + b) as u8);
            i += 3;
        } else {
            out.push(raw[i]);
            i += 1;
        }
    }
    if out
        .iter()
        .any(|b| *b == 0 || *b == b'\\' || *b < 32 || *b == 127)
    {
        return Err(400);
    }
    let path = String::from_utf8(out).map_err(|_| 400u16)?;
    if path.split('/').any(|p| p == "..") {
        return Err(403);
    }
    let query = String::from_utf8(raw[p..].to_vec()).map_err(|_| 400u16)?;
    Ok((path, query))
}
#[derive(Clone)]
struct Request {
    method: String,
    path: String,
    query: String,
    headers: Vec<Header>,
    close: bool,
    beta: bool,
    proxy: bool,
    frame: Frame,
}
#[derive(Clone, Copy)]
enum Frame {
    Length(usize),
    Chunked,
}
fn request(raw: &[u8], cfg: &Config) -> Result<Request, u16> {
    if invalid_lines(raw) {
        return Err(400);
    }
    let p = raw.windows(2).position(|w| w == b"\r\n").ok_or(400u16)?;
    let parts: Vec<_> = raw[..p].split(|b| *b == b' ').collect();
    if parts.len() != 3 || !token(parts[0]) || parts[1].is_empty() {
        return Err(400);
    }
    let version11 = match parts[2] {
        b"HTTP/1.1" => true,
        b"HTTP/1.0" => false,
        _ => return Err(400),
    };
    let headers = if p + 4 == raw.len() {
        Vec::new()
    } else {
        fields(&raw[p + 2..raw.len() - 2])?
    };
    let hosts: Vec<_> = values(&headers, "host").collect();
    if hosts.len() > 1 || (version11 && hosts.len() != 1) {
        return Err(400);
    }
    let h = if let Some(h) = hosts.first() {
        host(h).ok_or(400u16)?
    } else {
        cfg.default_host.clone()
    };
    let beta = h == cfg.beta_host;
    if h != cfg.default_host && !beta {
        return Err(400);
    }
    let (path, query) = path_decode(parts[1])?;
    let proxy = path.starts_with(&cfg.proxy_prefix);
    let cls: Vec<_> = values(&headers, "content-length").collect();
    let tes: Vec<_> = values(&headers, "transfer-encoding").collect();
    if cls.len() > 1 || tes.len() > 1 || (!cls.is_empty() && !tes.is_empty()) {
        return Err(400);
    }
    let frame = if let Some(v) = cls.first() {
        Frame::Length(decimal(v).ok_or(400u16)?)
    } else if let Some(v) = tes.first() {
        if !v.eq_ignore_ascii_case(b"chunked") {
            return Err(400);
        }
        Frame::Chunked
    } else {
        Frame::Length(0)
    };
    if !proxy && !matches!(frame, Frame::Length(0)) {
        return Err(400);
    }
    if proxy && matches!(frame,Frame::Length(n) if n>cfg.body_bytes) {
        return Err(413);
    }
    let method = String::from_utf8(parts[0].to_vec()).map_err(|_| 400u16)?;
    if !(method == "GET" || method == "HEAD" || (proxy && method == "POST")) {
        return Err(405);
    }
    let close = !version11 || connection_tokens(&headers).contains("close");
    Ok(Request {
        method,
        path,
        query,
        headers,
        close,
        beta,
        proxy,
        frame,
    })
}
// Chunk extensions use tokens or quoted strings; payload bytes are never syntax-checked.
fn chunk_size(line: &[u8]) -> Result<usize, u16> {
    let mut i = 0;
    while i < line.len() && line[i].is_ascii_hexdigit() {
        i += 1;
    }
    if i == 0 {
        return Err(400);
    }
    let size = line[..i]
        .iter()
        .try_fold(0usize, |n, c| {
            n.checked_mul(16)?
                .checked_add((*c as char).to_digit(16)? as usize)
        })
        .ok_or(413u16)?;
    while i < line.len() {
        while i < line.len() && matches!(line[i], b' ' | b'\t') {
            i += 1;
        }
        if i == line.len() || line[i] != b';' {
            return Err(400);
        }
        i += 1;
        while i < line.len() && matches!(line[i], b' ' | b'\t') {
            i += 1;
        }
        let start = i;
        while i < line.len() && token(&line[i..i + 1]) {
            i += 1;
        }
        if start == i {
            return Err(400);
        }
        while i < line.len() && matches!(line[i], b' ' | b'\t') {
            i += 1;
        }
        if i < line.len() && line[i] == b'=' {
            i += 1;
            while i < line.len() && matches!(line[i], b' ' | b'\t') {
                i += 1;
            }
            if i < line.len() && line[i] == b'"' {
                i += 1;
                let mut closed = false;
                while i < line.len() {
                    let c = line[i];
                    i += 1;
                    if c == b'"' {
                        closed = true;
                        break;
                    }
                    if c == b'\\' {
                        if i == line.len() {
                            return Err(400);
                        }
                        let escaped = line[i];
                        if escaped < 32 && escaped != b'\t' || escaped == 127 {
                            return Err(400);
                        }
                        i += 1;
                    } else if c < 32 && c != b'\t' || c == 127 {
                        return Err(400);
                    }
                }
                if !closed {
                    return Err(400);
                }
            } else {
                let start = i;
                while i < line.len() && token(&line[i..i + 1]) {
                    i += 1;
                }
                if i == start {
                    return Err(400);
                }
            }
            while i < line.len() && matches!(line[i], b' ' | b'\t') {
                i += 1;
            }
        }
        if i < line.len() && line[i] != b';' {
            return Err(400);
        }
    }
    Ok(size)
}
struct Decoder {
    state: ChunkState,
    body: Vec<u8>,
    trailers: usize,
}
enum ChunkState {
    Size,
    Data(usize),
    DataEnd,
    Trailers,
    Done,
}
impl Decoder {
    fn new() -> Self {
        Self {
            state: ChunkState::Size,
            body: Vec::new(),
            trailers: 0,
        }
    }
    // Consumes only decoded framing, leaving the next pipeline message untouched.
    fn feed(
        &mut self,
        input: &mut Vec<u8>,
        limit: usize,
        header_limit: usize,
    ) -> Result<bool, u16> {
        let mut used = 0;
        loop {
            match self.state {
                ChunkState::Size => {
                    let b = &input[used..];
                    let Some(p) = b.windows(2).position(|w| w == b"\r\n") else {
                        if b.len() > header_limit || invalid_lines(b) {
                            return Err(400);
                        }
                        break;
                    };
                    if invalid_lines(&b[..p + 2]) {
                        return Err(400);
                    }
                    if p > header_limit {
                        return Err(400);
                    }
                    let size = chunk_size(&b[..p])?;
                    if size > limit - self.body.len() {
                        return Err(413);
                    }
                    used += p + 2;
                    self.state = if size == 0 {
                        ChunkState::Trailers
                    } else {
                        ChunkState::Data(size)
                    };
                }
                ChunkState::Data(n) => {
                    let take = n.min(input.len() - used);
                    self.body.extend_from_slice(&input[used..used + take]);
                    used += take;
                    if take < n {
                        self.state = ChunkState::Data(n - take);
                        break;
                    }
                    self.state = ChunkState::DataEnd;
                }
                ChunkState::DataEnd => {
                    let b = &input[used..];
                    if b.first().is_some_and(|c| *c != b'\r') || (b.len() > 1 && b[1] != b'\n') {
                        return Err(400);
                    }
                    if b.len() < 2 {
                        break;
                    }
                    used += 2;
                    self.state = ChunkState::Size;
                }
                ChunkState::Trailers => {
                    let b = &input[used..];
                    let Some(p) = b.windows(2).position(|w| w == b"\r\n") else {
                        if self.trailers + b.len() > header_limit || invalid_lines(b) {
                            return Err(400);
                        }
                        break;
                    };
                    if invalid_lines(&b[..p + 2]) {
                        return Err(400);
                    }
                    self.trailers += p + 2;
                    if self.trailers > header_limit {
                        return Err(400);
                    }
                    used += p + 2;
                    if p == 0 {
                        self.state = ChunkState::Done;
                    } else {
                        let mut line = b[..p + 2].to_vec(); // use the same header syntax, and disallow framing trailers
                        let hs = fields(&line)?;
                        if hs.iter().any(|h| {
                            matches!(
                                h.name.as_str(),
                                "content-length" | "transfer-encoding" | "host"
                            )
                        }) {
                            return Err(400);
                        }
                        line.clear();
                    }
                }
                ChunkState::Done => break,
            }
        }
        if used > 0 {
            input.drain(..used);
        }
        Ok(matches!(self.state, ChunkState::Done))
    }
}
struct Local {
    file: File,
    len: u64,
    etag: String,
    mime: &'static str,
}
enum Body {
    Empty,
    Bytes(Vec<u8>, usize),
    File(Arc<Local>, i64, u64),
}
struct Output {
    header: Vec<u8>,
    pos: usize,
    body: Body,
    close: bool,
    deadline: Instant,
}
fn reason(s: u16) -> &'static str {
    match s {
        200 => "OK",
        206 => "Partial Content",
        301 => "Moved Permanently",
        302 => "Found",
        304 => "Not Modified",
        400 => "Bad Request",
        403 => "Forbidden",
        404 => "Not Found",
        405 => "Method Not Allowed",
        408 => "Request Timeout",
        413 => "Content Too Large",
        416 => "Range Not Satisfiable",
        431 => "Request Header Fields Too Large",
        502 => "Bad Gateway",
        504 => "Gateway Timeout",
        _ => "Response",
    }
}
fn output(
    status: u16,
    headers: Vec<Header>,
    length: u64,
    body: Body,
    close: bool,
    cfg: &Config,
) -> Output {
    let mut head = format!(
        "HTTP/1.1 {} {}\r\nContent-Length: {}\r\nConnection: {}\r\n",
        status,
        reason(status),
        length,
        if close { "close" } else { "keep-alive" }
    )
    .into_bytes();
    for h in headers {
        head.extend_from_slice(h.name.as_bytes());
        head.extend_from_slice(b": ");
        head.extend_from_slice(&h.value);
        head.extend_from_slice(b"\r\n");
    }
    head.extend_from_slice(b"\r\n");
    Output {
        header: head,
        pos: 0,
        body,
        close,
        deadline: Instant::now() + cfg.write_timeout,
    }
}
fn hdr(n: &str, v: impl Into<Vec<u8>>) -> Header {
    Header {
        name: n.into(),
        value: v.into(),
    }
}
fn error_output(status: u16, close: bool, cfg: &Config) -> Output {
    output(status, Vec::new(), 0, Body::Empty, close, cfg)
}
fn open_child(base: &File, parts: &[&str]) -> Result<File, u16> {
    let mut parent: Option<File> = None;
    for (i, p) in parts.iter().enumerate() {
        let cs = CString::new(*p).map_err(|_| 400u16)?;
        let fd = unsafe {
            openat(
                parent.as_ref().unwrap_or(base).as_raw_fd(),
                cs.as_ptr(),
                0x80000 | 0x20000 | 0x800 | if i + 1 < parts.len() { 0x10000 } else { 0 },
            )
        };
        if fd < 0 {
            let e = io::Error::last_os_error();
            return Err(match e.raw_os_error() {
                Some(2) => 404,
                _ => 403,
            });
        }
        parent = Some(unsafe { File::from_raw_fd(fd) });
    }
    if let Some(f) = parent {
        Ok(f)
    } else {
        base.try_clone().map_err(|_| 403)
    }
}
fn mime(path: &str) -> &'static str {
    if path.ends_with(".html") {
        "text/html"
    } else if path.ends_with(".txt") {
        "text/plain"
    } else {
        "application/octet-stream"
    }
}
fn range(raw: &[u8], size: u64) -> Result<Option<(u64, u64)>, u16> {
    let b = raw.strip_prefix(b"bytes=").ok_or(400u16)?;
    if b.contains(&b',') {
        return Err(400);
    }
    let i = b.iter().position(|c| *c == b'-').ok_or(400u16)?;
    let (a, z) = (&b[..i], &b[i + 1..]);
    if a.is_empty() {
        let n = decimal(z).ok_or(400u16)? as u64;
        if n == 0 || size == 0 {
            return Ok(None);
        }
        return Ok(Some((size.saturating_sub(n), size - 1)));
    }
    let start = decimal(a).ok_or(400u16)? as u64;
    let end = if z.is_empty() {
        size.saturating_sub(1)
    } else {
        decimal(z).ok_or(400u16)? as u64
    };
    if end < start || start >= size || size == 0 {
        Ok(None)
    } else {
        Ok(Some((start, end.min(size - 1))))
    }
}
fn local(
    req: &Request,
    close: bool,
    cfg: &Config,
    cache: &mut HashMap<String, Arc<Local>>,
) -> Output {
    if req.path == cfg.redir_path {
        return output(
            302,
            vec![hdr("Location", cfg.redir_to.clone())],
            0,
            Body::Empty,
            close,
            cfg,
        );
    }
    let (base, rest, key) = if req.path.starts_with(&cfg.alias_prefix) {
        (
            &cfg.alias,
            &req.path[cfg.alias_prefix.len()..],
            format!("a:{}", req.path),
        )
    } else {
        (
            if req.beta { &cfg.beta } else { &cfg.root },
            req.path.trim_start_matches('/'),
            format!("{}:{}", req.beta, req.path),
        )
    };
    let rep = if let Some(l) = cache.get(&key) {
        l.clone()
    } else {
        let mut parts: Vec<_> = rest
            .split('/')
            .filter(|p| !p.is_empty() && *p != ".")
            .collect();
        let mut file = match open_child(base, &parts) {
            Ok(f) => f,
            Err(s) => return error_output(s, close, cfg),
        };
        let mut md = match file.metadata() {
            Ok(m) => m,
            Err(_) => return error_output(403, close, cfg),
        };
        let mut selected = req.path.clone();
        if md.is_dir() {
            if !req.path.ends_with('/') {
                return output(
                    301,
                    vec![hdr("Location", format!("{}/{}", req.path, req.query))],
                    0,
                    Body::Empty,
                    close,
                    cfg,
                );
            }
            parts.push(&cfg.index);
            file = match open_child(base, &parts) {
                Ok(f) => f,
                Err(s) => return error_output(if s == 404 { 403 } else { s }, close, cfg),
            };
            md = match file.metadata() {
                Ok(m) => m,
                Err(_) => return error_output(403, close, cfg),
            };
            selected.push_str(&cfg.index);
        } else if req.path.ends_with('/') {
            return error_output(403, close, cfg);
        }
        if !md.is_file() {
            return error_output(403, close, cfg);
        }
        let rep = Arc::new(Local {
            file,
            len: md.len(),
            etag: format!(
                "\"{:x}-{:x}-{:x}-{:x}\"",
                md.dev(),
                md.ino(),
                md.len(),
                md.mtime_nsec() as u64 ^ md.mtime() as u64
            ),
            mime: mime(&selected),
        });
        if cache.len() < 512 {
            cache.insert(key, rep.clone());
        }
        rep
    };
    let headers = vec![hdr("Content-Type", rep.mime), hdr("ETag", rep.etag.clone())];
    if values(&req.headers, "if-none-match").any(|v| {
        v.split(|c| *c == b',').any(|t| {
            let t = trim(t);
            t == b"*"
                || t == rep.etag.as_bytes()
                || t.strip_prefix(b"W/")
                    .is_some_and(|x| x == rep.etag.as_bytes())
        })
    }) {
        return output(304, headers, 0, Body::Empty, close, cfg);
    }
    let ranges: Vec<_> = values(&req.headers, "range").collect();
    if ranges.len() > 1 {
        return error_output(400, true, cfg);
    }
    let (status, start, length, headers) = if let Some(v) = ranges.first() {
        match range(v, rep.len) {
            Err(s) => return error_output(s, true, cfg),
            Ok(None) => {
                return output(
                    416,
                    vec![hdr("Content-Range", format!("bytes */{}", rep.len))],
                    0,
                    Body::Empty,
                    close,
                    cfg,
                )
            }
            Ok(Some((a, b))) => {
                let mut h = headers;
                h.push(hdr(
                    "Content-Range",
                    format!("bytes {}-{}/{}", a, b, rep.len),
                ));
                (206, a, b - a + 1, h)
            }
        }
    } else {
        (200, 0, rep.len, headers)
    };
    let body = if req.method == "HEAD" || length == 0 {
        Body::Empty
    } else {
        Body::File(rep, start as i64, length)
    };
    output(status, headers, length, body, close, cfg)
}
#[derive(Clone, Copy)]
enum ResponseFrame {
    Length(usize),
    Chunked,
    Eof,
}
struct UpHead {
    status: u16,
    headers: Vec<Header>,
    frame: ResponseFrame,
    keep: bool,
    length: usize,
    no_body: bool,
}
fn upstream_head(raw: &[u8], head_request: bool, cfg: &Config) -> Result<UpHead, u16> {
    if invalid_lines(raw) {
        return Err(502);
    }
    let p = raw.windows(2).position(|w| w == b"\r\n").ok_or(502u16)?;
    let line = &raw[..p];
    if line.len() < 12
        || !(line.starts_with(b"HTTP/1.1 ") || line.starts_with(b"HTTP/1.0 "))
        || !line[9..12].iter().all(u8::is_ascii_digit)
        || (line.len() > 12 && line[12] != b' ')
        || line.iter().any(|c| (*c < 32 && *c != b'\t') || *c == 127)
    {
        return Err(502);
    }
    let status = decimal(&line[9..12]).ok_or(502u16)? as u16;
    if !(100..=599).contains(&status) || status == 101 {
        return Err(502);
    }
    let headers = if p + 4 == raw.len() {
        Vec::new()
    } else {
        fields(&raw[p + 2..raw.len() - 2]).map_err(|_| 502u16)?
    };
    let cls: Vec<_> = values(&headers, "content-length").collect();
    let tes: Vec<_> = values(&headers, "transfer-encoding").collect();
    if cls.len() > 1 || tes.len() > 1 || (!cls.is_empty() && !tes.is_empty()) {
        return Err(502);
    }
    let frame = if let Some(c) = cls.first() {
        ResponseFrame::Length(decimal(c).ok_or(502u16)?)
    } else if let Some(t) = tes.first() {
        if !t.eq_ignore_ascii_case(b"chunked") {
            return Err(502);
        }
        ResponseFrame::Chunked
    } else {
        ResponseFrame::Eof
    };
    let no_body = head_request || (100..200).contains(&status) || status == 204 || status == 304;
    let length = match frame {
        ResponseFrame::Length(n) => n,
        _ => 0,
    };
    if !no_body && length > cfg.body_bytes {
        return Err(502);
    }
    let keep = line.starts_with(b"HTTP/1.1 ")
        && !connection_tokens(&headers).contains("close")
        && (no_body || !matches!(frame, ResponseFrame::Eof));
    Ok(UpHead {
        status,
        headers,
        frame,
        keep,
        length,
        no_body,
    })
}
fn encode_uri(p: &str) -> String {
    let mut s = String::new();
    for c in p.bytes() {
        if c.is_ascii_alphanumeric() || b"-._~/:@!$&'()*+,;=".contains(&c) {
            s.push(c as char);
        } else {
            s.push_str(&format!("%{:02X}", c));
        }
    }
    s
}
struct Upload {
    req: Request,
    body: Vec<u8>,
    decoder: Option<Decoder>,
    deadline: Instant,
}
struct Proxy {
    stream: TcpStream,
    which: usize,
    attempt: u8,
    deadline: Instant,
    send: Vec<u8>,
    sent: usize,
    input: Vec<u8>,
    head: Option<UpHead>,
    body: Vec<u8>,
    decoder: Option<Decoder>,
    req: Request,
    upload: Vec<u8>,
}
struct QueuedProxy {
    fd: i32,
    ticket: u64,
    req: Request,
    upload: Vec<u8>,
    which: usize,
    attempt: u8,
}
enum Phase {
    Reading,
    Upload(Upload),
    Proxy(Proxy),
    Queued { ticket: u64, deadline: Instant },
    Writing(Output),
    Closing(Instant),
}
struct Client {
    stream: TcpStream,
    input: Vec<u8>,
    phase: Phase,
    first: Option<Instant>,
    idle: Instant,
    count: usize,
}
struct Server {
    cfg: Config,
    listener: TcpListener,
    ep: i32,
    clients: HashMap<i32, Client>,
    owners: HashMap<i32, i32>,
    pool: Vec<Vec<TcpStream>>,
    active: Vec<usize>,
    pending: VecDeque<QueuedProxy>,
    ticket: u64,
    round: usize,
    cache: HashMap<String, Arc<Local>>,
}
fn ep_set(ep: i32, op: i32, fd: i32, events: u32, data: u64) {
    let mut event = Event { events, data };
    unsafe {
        epoll_ctl(ep, op, fd, &mut event);
    }
}
fn nonblocking_connect(addr: SocketAddr) -> io::Result<TcpStream> {
    let fd = unsafe { socket(if addr.is_ipv4() { 2 } else { 10 }, 1 | 0x800 | 0x80000, 0) };
    if fd < 0 {
        return Err(io::Error::last_os_error());
    }
    let stream = unsafe { TcpStream::from_raw_fd(fd) };
    let result = match addr {
        SocketAddr::V4(a) => {
            let raw = SockAddrIn {
                family: 2,
                port: a.port().to_be(),
                address: u32::from_ne_bytes(a.ip().octets()),
                zero: [0; 8],
            };
            unsafe { connect(fd, &raw as *const _ as *const c_void, 16) }
        }
        SocketAddr::V6(a) => {
            let raw = SockAddrIn6 {
                family: 10,
                port: a.port().to_be(),
                flowinfo: a.flowinfo(),
                address: a.ip().octets(),
                scope_id: a.scope_id(),
            };
            unsafe { connect(fd, &raw as *const _ as *const c_void, 28) }
        }
    };
    if result < 0 && io::Error::last_os_error().raw_os_error() != Some(115) {
        return Err(io::Error::last_os_error());
    }
    let _ = stream.set_nodelay(true);
    Ok(stream)
}

impl Server {
    fn new(cfg: Config) -> io::Result<Self> {
        let listener = TcpListener::bind(cfg.listen)?;
        // std uses a small fixed accept backlog; expose the configured connection capacity
        // to the kernel so a burst need not wait for a TCP retransmission to be accepted.
        if unsafe {
            listen(
                listener.as_raw_fd(),
                cfg.max_connections.clamp(128, i32::MAX as usize) as i32,
            )
        } < 0
        {
            return Err(io::Error::last_os_error());
        }
        listener.set_nonblocking(true)?;
        let ep = unsafe { epoll_create1(0x80000) };
        if ep < 0 {
            return Err(io::Error::last_os_error());
        }
        ep_set(ep, 1, listener.as_raw_fd(), IN, listener.as_raw_fd() as u64);
        let pool = cfg.upstreams.iter().map(|_| Vec::new()).collect();
        let active = vec![0; cfg.upstreams.len()];
        Ok(Self {
            cfg,
            listener,
            ep,
            clients: HashMap::new(),
            owners: HashMap::new(),
            pool,
            active,
            pending: VecDeque::new(),
            ticket: 0,
            round: 0,
            cache: HashMap::new(),
        })
    }
    fn accept(&mut self) {
        for _ in 0..256 {
            match self.listener.accept() {
                Ok((stream, _)) => {
                    if self.clients.len() >= self.cfg.max_connections {
                        drop(stream);
                        continue;
                    }
                    let _ = stream.set_nonblocking(true);
                    let _ = stream.set_nodelay(true);
                    // Restrict kernel output buffering so a stalled reader cannot occupy a slot indefinitely.
                    let size: i32 = 65536;
                    unsafe {
                        setsockopt(
                            stream.as_raw_fd(),
                            1,
                            7,
                            &size as *const _ as *const c_void,
                            4,
                        );
                    }
                    let fd = stream.as_raw_fd();
                    ep_set(self.ep, 1, fd, IN | RDHUP, fd as u64);
                    self.clients.insert(
                        fd,
                        Client {
                            stream,
                            input: Vec::new(),
                            phase: Phase::Reading,
                            first: None,
                            idle: Instant::now() + self.cfg.idle_timeout,
                            count: 0,
                        },
                    );
                }
                Err(e) if e.kind() == io::ErrorKind::WouldBlock => break,
                Err(_) => break,
            }
        }
    }
    fn dispose(&mut self, fd: i32, c: Client) {
        ep_set(self.ep, 2, fd, 0, 0);
        if let Phase::Proxy(p) = c.phase {
            let up = p.stream.as_raw_fd();
            ep_set(self.ep, 2, up, 0, 0);
            self.owners.remove(&up);
            self.active[p.which] -= 1;
        }
    }
    fn register_down(&self, c: &Client) {
        let fd = c.stream.as_raw_fd();
        let events = match c.phase {
            Phase::Reading | Phase::Upload(_) => IN | RDHUP,
            Phase::Writing(_) => OUT | RDHUP,
            Phase::Proxy(_) | Phase::Queued { .. } => 0,
            Phase::Closing(_) => IN | RDHUP,
        };
        ep_set(self.ep, 3, fd, events, fd as u64);
    }
    fn start_proxy(
        &mut self,
        fd: i32,
        req: Request,
        upload: Vec<u8>,
        which: usize,
        attempt: u8,
    ) -> Result<Proxy, u16> {
        let mut stream = None;
        while let Some(s) = self.pool[which].pop() {
            let mut b = [0; 1];
            match s.peek(&mut b) {
                Err(e) if e.kind() == io::ErrorKind::WouldBlock => {
                    stream = Some(s);
                    break;
                }
                _ => {}
            }
        }
        let stream = match stream {
            Some(s) => s,
            None => nonblocking_connect(self.cfg.upstreams[which]).map_err(|_| 502u16)?,
        };
        let target = format!(
            "/{}{}",
            encode_uri(&req.path[self.cfg.proxy_prefix.len()..]),
            req.query
        );
        let mut send = format!(
            "{} {} HTTP/1.1\r\nHost: {}\r\nContent-Length: {}\r\nConnection: keep-alive\r\n",
            req.method,
            target,
            self.cfg.upstreams[which],
            upload.len()
        )
        .into_bytes();
        let tokens = connection_tokens(&req.headers);
        for h in &req.headers {
            if h.name == "host"
                || h.name == "content-length"
                || h.name == "expect"
                || blocked(&h.name, &tokens)
            {
                continue;
            }
            send.extend_from_slice(h.name.as_bytes());
            send.extend_from_slice(b": ");
            send.extend_from_slice(&h.value);
            send.extend_from_slice(b"\r\n");
        }
        send.extend_from_slice(b"\r\n");
        send.extend_from_slice(&upload);
        let up = stream.as_raw_fd();
        ep_set(self.ep, 1, up, IN | OUT | RDHUP, UP | up as u64);
        self.owners.insert(up, fd);
        self.active[which] += 1;
        Ok(Proxy {
            stream,
            which,
            attempt,
            deadline: Instant::now() + self.cfg.upstream_timeout,
            send,
            sent: 0,
            input: Vec::new(),
            head: None,
            body: Vec::new(),
            decoder: None,
            req,
            upload,
        })
    }
    // Every admission, including a retry, joins the queue. Only the dispatcher
    // can claim capacity, so a request arriving later in an epoll batch cannot
    // overtake an older waiter after a completion frees an upstream slot.
    fn enqueue_proxy(
        &mut self,
        fd: i32,
        req: Request,
        upload: Vec<u8>,
        which: usize,
        attempt: u8,
    ) -> Phase {
        self.ticket = self.ticket.wrapping_add(1);
        let ticket = self.ticket;
        self.pending.push_back(QueuedProxy {
            fd,
            ticket,
            req,
            upload,
            which,
            attempt,
        });
        Phase::Queued {
            ticket,
            deadline: Instant::now() + self.cfg.idle_timeout,
        }
    }
    fn dispatch_pending(&mut self) {
        // Keep the old batch separate from retries created during this pass.
        // Otherwise rotating an old blocked entry after a newly enqueued retry
        // could move that retry ahead of requests which were already waiting.
        let batch = std::mem::take(&mut self.pending);
        let mut waiting = VecDeque::new();
        for q in batch {
            if !self
                .clients
                .get(&q.fd)
                .is_some_and(|c| matches!(c.phase,Phase::Queued{ticket,..} if ticket==q.ticket))
            {
                continue;
            }
            if self.active[q.which] >= self.cfg.max_connections.min(64) {
                waiting.push_back(q);
                continue;
            }
            let mut c = self.clients.remove(&q.fd).unwrap();
            // A popped entry owns this turn; starting it directly avoids moving
            // the oldest waiter behind the newer entries still in the queue.
            c.phase =
                match self.start_proxy(q.fd, q.req.clone(), q.upload.clone(), q.which, q.attempt) {
                    Ok(p) => Phase::Proxy(p),
                    Err(_) if q.attempt == 0 && q.req.method != "POST" => self.enqueue_proxy(
                        q.fd,
                        q.req,
                        q.upload,
                        (q.which + 1) % self.cfg.upstreams.len(),
                        1,
                    ),
                    Err(e) => Phase::Writing(error_output(e, true, &self.cfg)),
                };
            self.register_down(&c);
            self.clients.insert(q.fd, c);
        }
        waiting.append(&mut self.pending);
        self.pending = waiting;
    }
    fn initiate(&mut self, fd: i32, c: &mut Client, req: Request, body: Vec<u8>) {
        if req.proxy {
            let which = self.round % self.cfg.upstreams.len();
            self.round = self.round.wrapping_add(1);
            c.phase = self.enqueue_proxy(fd, req, body, which, 0);
        } else {
            let close = req.close || c.count + 1 >= self.cfg.max_requests;
            c.phase = Phase::Writing(local(&req, close, &self.cfg, &mut self.cache));
        }
    }
    fn consume(&mut self, fd: i32, c: &mut Client) -> Result<bool, ()> {
        let phase = std::mem::replace(&mut c.phase, Phase::Reading);
        match phase {
            Phase::Reading => {
                if c.input.is_empty() {
                    return Ok(false);
                }
                if c.first.is_none() {
                    c.first = Some(Instant::now());
                }
                let end = end_headers(&c.input);
                let n = end.unwrap_or(c.input.len());
                if n > self.cfg.header_bytes {
                    c.phase = Phase::Writing(error_output(431, true, &self.cfg));
                    return Ok(true);
                }
                if invalid_lines(&c.input[..n]) {
                    c.phase = Phase::Writing(error_output(400, true, &self.cfg));
                    return Ok(true);
                }
                let Some(end) = end else {
                    return Ok(false);
                };
                let req = match request(&c.input[..end], &self.cfg) {
                    Ok(r) => r,
                    Err(e) => {
                        c.phase = Phase::Writing(error_output(e, true, &self.cfg));
                        return Ok(true);
                    }
                };
                c.input.drain(..end);
                if c.input.is_empty() {
                    c.first = None;
                }
                match req.frame {
                    Frame::Length(0) => self.initiate(fd, c, req, Vec::new()),
                    Frame::Length(_) => {
                        c.phase = Phase::Upload(Upload {
                            req,
                            body: Vec::new(),
                            decoder: None,
                            deadline: Instant::now() + self.cfg.idle_timeout,
                        })
                    }
                    Frame::Chunked => {
                        c.phase = Phase::Upload(Upload {
                            req,
                            body: Vec::new(),
                            decoder: Some(Decoder::new()),
                            deadline: Instant::now() + self.cfg.idle_timeout,
                        })
                    }
                }
                Ok(true)
            }
            Phase::Upload(mut u) => {
                let done = if let Some(d) = &mut u.decoder {
                    match d.feed(&mut c.input, self.cfg.body_bytes, self.cfg.header_bytes) {
                        Ok(done) => done,
                        Err(e) => {
                            c.phase = Phase::Writing(error_output(e, true, &self.cfg));
                            return Ok(true);
                        }
                    }
                } else {
                    let Frame::Length(n) = u.req.frame else {
                        unreachable!()
                    };
                    let take = (n - u.body.len()).min(c.input.len());
                    u.body.extend_from_slice(&c.input[..take]);
                    c.input.drain(..take);
                    u.body.len() == n
                };
                if c.input.is_empty() {
                    c.first = None;
                }
                if done {
                    let body = if let Some(d) = u.decoder {
                        d.body
                    } else {
                        u.body
                    };
                    self.initiate(fd, c, u.req, body);
                    Ok(true)
                } else {
                    c.phase = Phase::Upload(u);
                    Ok(false)
                }
            }
            other => {
                c.phase = other;
                Ok(false)
            }
        }
    }
    fn write_output(&self, c: &mut Client) -> Result<bool, ()> {
        let Phase::Writing(o) = &mut c.phase else {
            return Ok(false);
        };
        let mut budget: usize = 256 * 1024;
        while o.pos < o.header.len() {
            match c.stream.write(&o.header[o.pos..]) {
                Ok(0) => return Err(()),
                Ok(n) => {
                    o.pos += n;
                    o.deadline = Instant::now() + self.cfg.write_timeout;
                }
                Err(e) if e.kind() == io::ErrorKind::WouldBlock => return Ok(false),
                Err(e) if e.kind() == io::ErrorKind::Interrupted => continue,
                Err(_) => return Err(()),
            }
        }
        loop {
            match &mut o.body {
                Body::Empty => return Ok(true),
                Body::Bytes(b, pos) => {
                    if *pos == b.len() {
                        return Ok(true);
                    }
                    match c.stream.write(&b[*pos..(*pos + budget).min(b.len())]) {
                        Ok(0) => return Err(()),
                        Ok(n) => {
                            *pos += n;
                            budget -= n;
                            o.deadline = Instant::now() + self.cfg.write_timeout;
                        }
                        Err(e) if e.kind() == io::ErrorKind::WouldBlock => return Ok(false),
                        Err(e) if e.kind() == io::ErrorKind::Interrupted => continue,
                        Err(_) => return Err(()),
                    }
                }
                Body::File(f, offset, left) => {
                    if *left == 0 {
                        return Ok(true);
                    }
                    let n = unsafe {
                        sendfile(
                            c.stream.as_raw_fd(),
                            f.file.as_raw_fd(),
                            offset,
                            (*left as usize).min(budget),
                        )
                    };
                    if n > 0 {
                        *left -= n as u64;
                        budget -= n as usize;
                        o.deadline = Instant::now() + self.cfg.write_timeout;
                    } else if n == 0 {
                        return Err(());
                    } else {
                        let e = io::Error::last_os_error();
                        if e.kind() == io::ErrorKind::WouldBlock {
                            return Ok(false);
                        }
                        if e.kind() != io::ErrorKind::Interrupted {
                            return Err(());
                        }
                    }
                }
            }
            if budget == 0 {
                return Ok(false);
            }
        }
    }
    fn downstream(&mut self, fd: i32) {
        let Some(mut c) = self.clients.remove(&fd) else {
            return;
        };
        // Pending exchanges have no read interest, but epoll still reports socket
        // errors. Release reset clients promptly without treating a valid FIN
        // (a request-side half close) as cancellation.
        if matches!(c.phase, Phase::Proxy(_) | Phase::Queued { .. })
            && !matches!(c.stream.take_error(), Ok(None))
        {
            self.dispose(fd, c);
            return;
        }
        let mut alive = true;
        let mut budget: usize = 256 * 1024;
        for _ in 0..(self.cfg.pipeline_depth.min(64) + 2) {
            if matches!(c.phase, Phase::Reading | Phase::Upload(_)) {
                match self.consume(fd, &mut c) {
                    Err(_) => {
                        alive = false;
                        break;
                    }
                    Ok(true) => continue,
                    _ => {}
                }
                if budget == 0 {
                    break;
                }
                let mut b = [0u8; 16384];
                // Header buffering never reads arbitrary future pipelines or upload bodies into memory.
                let cap = if matches!(c.phase, Phase::Reading) {
                    (self.cfg.header_bytes + 1)
                        .saturating_sub(c.input.len())
                        .min(b.len())
                } else {
                    b.len()
                };
                if cap == 0 {
                    c.phase = Phase::Writing(error_output(431, true, &self.cfg));
                    continue;
                }
                match c.stream.read(&mut b[..cap]) {
                    Ok(0) => {
                        alive = false;
                        break;
                    }
                    Ok(n) => {
                        if c.input.is_empty() && c.first.is_none() {
                            c.first = Some(Instant::now());
                        }
                        c.input.extend_from_slice(&b[..n]);
                        if let Phase::Upload(u) = &mut c.phase {
                            u.deadline = Instant::now() + self.cfg.idle_timeout;
                        }
                        budget = budget.saturating_sub(n);
                        continue;
                    }
                    Err(e) if e.kind() == io::ErrorKind::WouldBlock => break,
                    Err(e) if e.kind() == io::ErrorKind::Interrupted => continue,
                    Err(_) => {
                        alive = false;
                        break;
                    }
                }
            } else if matches!(c.phase, Phase::Writing(_)) {
                match self.write_output(&mut c) {
                    Err(_) => {
                        alive = false;
                        break;
                    }
                    Ok(false) => break,
                    Ok(true) => {
                        let Phase::Writing(o) = std::mem::replace(&mut c.phase, Phase::Reading)
                        else {
                            unreachable!()
                        };
                        c.count += 1;
                        if o.close {
                            let _ = c.stream.shutdown(std::net::Shutdown::Write);
                            c.input.clear();
                            c.phase = Phase::Closing(Instant::now() + Duration::from_millis(100));
                            continue;
                        }
                        c.idle = Instant::now() + self.cfg.idle_timeout;
                        c.first = if c.input.is_empty() {
                            None
                        } else {
                            c.first.or(Some(Instant::now()))
                        };
                        continue;
                    }
                }
            } else if matches!(c.phase, Phase::Closing(_)) {
                if budget == 0 {
                    break;
                }
                let mut discard = [0u8; 16384];
                match c.stream.read(&mut discard) {
                    Ok(0) => {
                        alive = false;
                        break;
                    }
                    Ok(n) => {
                        budget = budget.saturating_sub(n);
                    }
                    Err(e) if e.kind() == io::ErrorKind::WouldBlock => break,
                    Err(e) if e.kind() == io::ErrorKind::Interrupted => continue,
                    Err(_) => {
                        alive = false;
                        break;
                    }
                }
            } else {
                break;
            }
        }
        if alive {
            self.register_down(&c);
            self.clients.insert(fd, c);
        } else {
            self.dispose(fd, c);
        }
    }
    fn proxy_io(&mut self, p: &mut Proxy) -> Result<Option<(UpHead, Vec<u8>)>, u16> {
        if Instant::now() >= p.deadline {
            return Err(504);
        }
        if let Some(e) = p.stream.take_error().map_err(|_| 502u16)? {
            let _ = e;
            return Err(502);
        }
        let mut budget: usize = 256 * 1024;
        while p.sent < p.send.len() {
            match p.stream.write(&p.send[p.sent..]) {
                Ok(0) => return Err(502),
                Ok(n) => {
                    p.sent += n;
                    budget = budget.saturating_sub(n);
                    if budget == 0 {
                        return Ok(None);
                    }
                }
                Err(e) if e.kind() == io::ErrorKind::WouldBlock => return Ok(None),
                Err(e) if e.kind() == io::ErrorKind::Interrupted => continue,
                Err(_) => return Err(502),
            }
        }
        if !p.send.is_empty() {
            p.send.clear();
            p.send.shrink_to_fit();
            p.upload.shrink_to_fit();
        }
        loop {
            if p.head.is_none() {
                if let Some(end) = end_headers(&p.input) {
                    if end > self.cfg.header_bytes {
                        return Err(502);
                    }
                    let h = upstream_head(&p.input[..end], p.req.method == "HEAD", &self.cfg)?;
                    p.input.drain(..end);
                    if (100..200).contains(&h.status) {
                        continue;
                    }
                    if matches!(h.frame, ResponseFrame::Chunked) {
                        p.decoder = Some(Decoder::new());
                    } else if !h.no_body {
                        if let ResponseFrame::Length(n) = h.frame {
                            p.body.try_reserve_exact(n).map_err(|_| 502u16)?;
                        }
                    }
                    p.head = Some(h);
                } else if p.input.len() > self.cfg.header_bytes || invalid_lines(&p.input) {
                    return Err(502);
                }
            }
            if let Some(h) = &p.head {
                let done = if h.no_body {
                    if !p.input.is_empty() {
                        return Err(502);
                    }
                    true
                } else {
                    match h.frame {
                        ResponseFrame::Length(n) => {
                            let take = (n - p.body.len()).min(p.input.len());
                            p.body.extend_from_slice(&p.input[..take]);
                            p.input.drain(..take);
                            if p.body.len() == n {
                                if !p.input.is_empty() {
                                    return Err(502);
                                }
                                true
                            } else {
                                false
                            }
                        }
                        ResponseFrame::Chunked => {
                            let done = p
                                .decoder
                                .as_mut()
                                .unwrap()
                                .feed(&mut p.input, self.cfg.body_bytes, self.cfg.header_bytes)
                                .map_err(|_| 502u16)?;
                            if done && !p.input.is_empty() {
                                return Err(502);
                            }
                            done
                        }
                        ResponseFrame::Eof => {
                            if p.body.len() + p.input.len() > self.cfg.body_bytes {
                                return Err(502);
                            }
                            p.body.append(&mut p.input);
                            false
                        }
                    }
                };
                if done {
                    let h = p.head.take().unwrap();
                    let body = if let Some(d) = p.decoder.take() {
                        d.body
                    } else {
                        std::mem::take(&mut p.body)
                    };
                    return Ok(Some((h, body)));
                }
            }
            if budget == 0 {
                return Ok(None);
            }
            let mut b = [0u8; 16384];
            match p.stream.read(&mut b) {
                Ok(0) => {
                    if let Some(h) = p.head.take() {
                        if !h.no_body && matches!(h.frame, ResponseFrame::Eof) {
                            return Ok(Some((h, std::mem::take(&mut p.body))));
                        }
                    }
                    return Err(502);
                }
                Ok(n) => {
                    p.input.extend_from_slice(&b[..n]);
                    budget = budget.saturating_sub(n);
                }
                Err(e) if e.kind() == io::ErrorKind::WouldBlock => return Ok(None),
                Err(e) if e.kind() == io::ErrorKind::Interrupted => continue,
                Err(_) => return Err(502),
            }
        }
    }
    fn upstream(&mut self, up: i32) {
        let Some(&fd) = self.owners.get(&up) else {
            return;
        };
        let Some(mut c) = self.clients.remove(&fd) else {
            return;
        };
        let Phase::Proxy(mut p) = std::mem::replace(&mut c.phase, Phase::Reading) else {
            return;
        };
        match self.proxy_io(&mut p) {
            Ok(None) => {
                let events = if p.sent < p.send.len() {
                    IN | OUT | RDHUP
                } else {
                    IN | RDHUP
                };
                ep_set(self.ep, 3, up, events, UP | up as u64);
                c.phase = Phase::Proxy(p);
                self.clients.insert(fd, c);
            }
            Ok(Some((h, body))) => {
                ep_set(self.ep, 2, up, 0, 0);
                self.owners.remove(&up);
                self.active[p.which] -= 1;
                let close = p.req.close || c.count + 1 >= self.cfg.max_requests;
                let tokens = connection_tokens(&h.headers);
                let headers = h
                    .headers
                    .into_iter()
                    .filter(|h| h.name != "content-length" && !blocked(&h.name, &tokens))
                    .collect();
                let length = if h.no_body {
                    if p.req.method == "HEAD" {
                        h.length
                    } else {
                        0
                    }
                } else {
                    body.len()
                };
                let output_body = if p.req.method == "HEAD" || body.is_empty() {
                    Body::Empty
                } else {
                    Body::Bytes(body, 0)
                };
                c.phase = Phase::Writing(output(
                    h.status,
                    headers,
                    length as u64,
                    output_body,
                    close,
                    &self.cfg,
                ));
                if h.keep
                    && self.pool[p.which].len() < 128
                    && self.pool.iter().map(Vec::len).sum::<usize>() < 256
                {
                    self.pool[p.which].push(p.stream);
                }
                self.register_down(&c);
                self.clients.insert(fd, c);
                self.downstream(fd);
            }
            Err(e) => {
                ep_set(self.ep, 2, up, 0, 0);
                self.owners.remove(&up);
                self.active[p.which] -= 1;
                let retry = p.attempt == 0 && p.req.method != "POST";
                let next = (p.which + 1) % self.cfg.upstreams.len();
                if retry {
                    c.phase = self.enqueue_proxy(fd, p.req, p.upload, next, 1);
                    self.clients.insert(fd, c);
                    return;
                }
                c.phase = Phase::Writing(error_output(e, true, &self.cfg));
                self.register_down(&c);
                self.clients.insert(fd, c);
                self.downstream(fd);
            }
        }
    }
    fn deadlines(&mut self) {
        let now = Instant::now();
        let expired: Vec<i32> = self
            .clients
            .iter()
            .filter_map(|(fd, c)| {
                let expired = match &c.phase {
                    Phase::Reading => c.first.map_or(now >= c.idle, |first| {
                        now.duration_since(first) >= self.cfg.header_timeout
                    }),
                    Phase::Upload(u) => now >= u.deadline,
                    Phase::Proxy(p) => now >= p.deadline,
                    Phase::Queued { deadline, .. } => now >= *deadline,
                    Phase::Writing(o) => now >= o.deadline,
                    Phase::Closing(d) => now >= *d,
                };
                if expired {
                    Some(*fd)
                } else {
                    None
                }
            })
            .collect();
        for fd in expired {
            let Some(mut c) = self.clients.remove(&fd) else {
                continue;
            };
            match &c.phase {
                Phase::Proxy(p) => {
                    let up = p.stream.as_raw_fd();
                    self.clients.insert(fd, c);
                    self.upstream(up);
                }
                Phase::Reading if c.first.is_some() => {
                    c.phase = Phase::Writing(error_output(408, true, &self.cfg));
                    self.register_down(&c);
                    self.clients.insert(fd, c);
                    self.downstream(fd);
                }
                Phase::Queued { .. } => {
                    c.phase = Phase::Writing(error_output(504, true, &self.cfg));
                    self.register_down(&c);
                    self.clients.insert(fd, c);
                    self.downstream(fd);
                }
                Phase::Upload(_) => {
                    c.phase = Phase::Writing(error_output(408, true, &self.cfg));
                    self.register_down(&c);
                    self.clients.insert(fd, c);
                    self.downstream(fd);
                }
                _ => self.dispose(fd, c),
            }
        }
    }
    fn run(&mut self) {
        let mut events = [Event { events: 0, data: 0 }; 512];
        let mut tick = Instant::now();
        loop {
            let n = unsafe { epoll_wait(self.ep, events.as_mut_ptr(), events.len() as i32, 10) };
            if n < 0 {
                if io::Error::last_os_error().kind() == io::ErrorKind::Interrupted {
                    continue;
                }
                break;
            }
            for ev in events.iter().take(n as usize) {
                let data = ev.data;
                if data & UP != 0 {
                    self.upstream((data & !UP) as i32);
                } else if data as i32 == self.listener.as_raw_fd() {
                    self.accept();
                } else {
                    self.downstream(data as i32);
                }
            }
            // Buffered requests count as runnable work even if the kernel receive queue is empty.
            let buffered: Vec<_> = self
                .clients
                .iter()
                .filter_map(|(fd, c)| {
                    if matches!(c.phase, Phase::Reading) && end_headers(&c.input).is_some() {
                        Some(*fd)
                    } else {
                        None
                    }
                })
                .collect();
            for fd in buffered {
                self.downstream(fd);
            }
            if tick.elapsed() >= Duration::from_millis(10) {
                self.deadlines();
                tick = Instant::now();
            }
            self.dispatch_pending();
        }
    }
}
fn main() {
    unsafe {
        signal(13, 1);
    }
    let args: Vec<String> = std::env::args().collect();
    if args.len() != 3 || args[1] != "--config" {
        std::process::exit(1);
    }
    let cfg = match Config::load(&args[2]) {
        Ok(c) => c,
        Err(e) => {
            eprintln!("configuration: {}", e);
            std::process::exit(1);
        }
    };
    match Server::new(cfg) {
        Ok(mut s) => s.run(),
        Err(e) => {
            eprintln!("server: {}", e);
            std::process::exit(1);
        }
    }
}
