use std::cell::Cell;
use std::collections::{HashMap, VecDeque};
use std::ffi::CString;
use std::fs::{self, File};
use std::io::{self, Read};
use std::net::{Shutdown, SocketAddr, TcpListener, TcpStream};
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::fs::MetadataExt;
use std::path::Path;
use std::rc::Rc;
use std::sync::Arc;
use std::time::{Duration, Instant};

const IN: u32 = 1;
const OUT: u32 = 4;
const ERR: u32 = 8;
const HUP: u32 = 16;
const RDHUP: u32 = 0x2000;
const NOFOLLOW: i32 = 0x20000;
const CLOEXEC: i32 = 0x80000;
const NONBLOCK: i32 = 0x800;
#[repr(C, packed)]
#[derive(Clone, Copy)]
struct Event { flags: u32, data: u64 }
#[repr(C)]
struct IoVec { base: *const u8, len: usize }
unsafe extern "C" {
    fn listen(fd: i32, backlog: i32) -> i32;
    fn epoll_create1(flags: i32) -> i32;
    fn epoll_ctl(ep: i32, op: i32, fd: i32, event: *const Event) -> i32;
    fn epoll_wait(ep: i32, events: *mut Event, n: i32, timeout: i32) -> i32;
    fn read(fd: i32, p: *mut std::ffi::c_void, count: usize) -> isize;
    fn writev(fd: i32, iov: *const IoVec, n: i32) -> isize;
    fn sendfile(out: i32, input: i32, offset: *mut i64, count: usize) -> isize;
    fn openat(fd: i32, path: *const i8, flags: i32, ...) -> i32;
}
fn errno() -> i32 { io::Error::last_os_error().raw_os_error().unwrap_or(0) }
fn trim(mut s: &[u8]) -> &[u8] {
    while matches!(s.first(), Some(b' ' | b'\t')) { s = &s[1..]; }
    while matches!(s.last(), Some(b' ' | b'\t')) { s = &s[..s.len()-1]; }
    s
}
fn number(s: &str) -> Result<usize, String> {
    if s.is_empty() || !s.bytes().all(|x| x.is_ascii_digit()) { return Err("invalid integer".into()); }
    let n = s.parse::<usize>().map_err(|_| "integer overflow")?;
    if n == 0 { Err("integer must be positive".into()) } else { Ok(n) }
}
fn host_name(s: &str) -> bool {
    !s.is_empty() && s.len() <= 253 && s.split('.').all(|label| !label.is_empty() && label.len() <= 63
        && label.bytes().all(|x| x.is_ascii_alphanumeric() || x == b'-')
        && !label.starts_with('-') && !label.ends_with('-'))
}
fn host_value(bytes: &[u8]) -> Option<String> {
    let s = std::str::from_utf8(trim(bytes)).ok()?;
    let host = if let Some((host, port)) = s.split_once(':') {
        if port.is_empty() || !port.bytes().all(|b| b.is_ascii_digit()) || port.parse::<u16>().is_err() { return None; }
        host
    } else { s };
    if !host_name(host) { return None; }
    Some(host.to_ascii_lowercase())
}
struct Config {
    listen: SocketAddr, roots: [File; 3], max_connections: usize, header_bytes: usize,
    header_timeout: Duration, idle_timeout: Duration, write_timeout: Duration,
    max_requests: usize, pipeline_depth: usize, default_host: String, other_host: String,
    alias: String, redirect_path: String, redirect_target: String, index: String,
}
impl Config {
    fn load(path: &str) -> Result<Self, String> {
        let contents = fs::read_to_string(path).map_err(|e| e.to_string())?;
        let names = ["listen", "root", "max_connections", "header_bytes", "header_timeout_ms", "idle_timeout_ms", "write_timeout_ms", "max_requests", "pipeline_depth", "default_host", "host_root", "alias", "redirect", "index"];
        let mut values = HashMap::new();
        for line in contents.lines() {
            let line = line.trim();
            if line.is_empty() || line.starts_with('#') { continue; }
            let (key, value) = line.split_once('=').ok_or("expected key=value")?;
            let (key, value) = (key.trim(), value.trim());
            if !names.contains(&key) || values.insert(key, value).is_some() { return Err("unknown or duplicate key".into()); }
        }
        if names.iter().any(|key| !values.contains_key(key)) { return Err("missing key".into()); }
        let root = |name: &str| -> Result<File, String> {
            if !Path::new(name).is_absolute() { return Err("root must be absolute".into()); }
            let meta = fs::metadata(name).map_err(|e| e.to_string())?;
            if !meta.is_dir() { return Err("root is not a directory".into()); }
            File::open(name).map_err(|e| e.to_string())
        };
        let default_host = values["default_host"].to_ascii_lowercase();
        let (other_host, host_root) = values["host_root"].split_once(':').ok_or("invalid host_root")?;
        if !host_name(&default_host) || !host_name(other_host) || default_host.eq_ignore_ascii_case(other_host) { return Err("invalid host names".into()); }
        let (alias, alias_root) = values["alias"].split_once(':').ok_or("invalid alias")?;
        let (redirect_path, redirect_target) = values["redirect"].split_once(':').ok_or("invalid redirect")?;
        let valid_route = |s: &str| s.starts_with('/') && !s.contains(['?', '#', '\\', '\r', '\n', '\0']) && !s.split('/').any(|c| c == "..");
        if !valid_route(alias) || !alias.ends_with('/') || !valid_route(redirect_path) || redirect_target.is_empty()
            || redirect_target.bytes().any(|x| x <= 32 || x == 127) { return Err("invalid route".into()); }
        let index = values["index"];
        if index.is_empty() || index == "." || index == ".." || index.contains(['/', '\\', '\0', '\r', '\n']) { return Err("invalid index".into()); }
        let listen = values["listen"].parse::<SocketAddr>().map_err(|_| "invalid listen address")?;
        if listen.port() == 0 { return Err("invalid listen port".into()); }
        let millis = |key: &str| -> Result<Duration, String> { Ok(Duration::from_millis(u64::try_from(number(values[key])?).map_err(|_| "duration overflow")?)) };
        Ok(Self { listen, roots: [root(values["root"] )?, root(host_root)?, root(alias_root)?],
            max_connections: number(values["max_connections"] )?, header_bytes: number(values["header_bytes"] )?,
            header_timeout: millis("header_timeout_ms")?, idle_timeout: millis("idle_timeout_ms")?, write_timeout: millis("write_timeout_ms")?,
            max_requests: number(values["max_requests"] )?, pipeline_depth: number(values["pipeline_depth"] )?,
            default_host, other_host: other_host.to_ascii_lowercase(), alias: alias.into(),
            redirect_path: redirect_path.into(), redirect_target: redirect_target.into(), index: index.into() })
    }
}
struct Request {
    head: bool, close: bool, target: String, host: usize,
    conditional: Vec<Vec<u8>>, range: Option<Vec<u8>>,
}
fn token(b: u8) -> bool { b.is_ascii_alphanumeric() || b"!#$%&'*+-.^_`|~".contains(&b) }
fn parse(raw: &[u8], cfg: &Config) -> Result<Request, u16> {
    if raw.contains(&0) { return Err(400); }
    let first_end = raw.windows(2).position(|s| s == b"\r\n").ok_or(400u16)?;
    let line = &raw[..first_end];
    let fields: Vec<&[u8]> = line.split(|&b| b == b' ').collect();
    if fields.len() != 3 || fields.iter().any(|s| s.is_empty()) || !fields[0].iter().all(|&b| token(b)) { return Err(400); }
    let http11 = match fields[2] { b"HTTP/1.1" => true, b"HTTP/1.0" => false, _ => return Err(400) };
    let target = std::str::from_utf8(fields[1]).map_err(|_| 400u16)?.to_string();
    if target.bytes().any(|x| x <= 32 || x == 127) { return Err(400); }
    let mut host = None;
    let mut close = !http11;
    let mut length_seen = false;
    let mut conditional = Vec::new();
    let mut range = None;
    let mut pos = first_end + 2;
    while pos + 2 < raw.len() {
        let end = raw[pos..].windows(2).position(|s| s == b"\r\n").ok_or(400u16)? + pos;
        if end == pos { break; }
        let line = &raw[pos..end];
        let colon = line.iter().position(|&b| b == b':').ok_or(400u16)?;
        if colon == 0 || !line[..colon].iter().all(|&b| token(b)) { return Err(400); }
        let value = trim(&line[colon+1..]);
        if value.iter().any(|&b| b == b'\r' || b == b'\n' || b == 127 || (b < 32 && b != b'\t')) { return Err(400); }
        let name = &line[..colon];
        if name.eq_ignore_ascii_case(b"host") {
            if host.is_some() { return Err(400); }
            host = Some(host_value(value).ok_or(400u16)?);
        } else if name.eq_ignore_ascii_case(b"connection") {
            if value.split(|&b| b == b',').any(|t| trim(t).eq_ignore_ascii_case(b"close")) { close = true; }
        } else if name.eq_ignore_ascii_case(b"content-length") {
            if length_seen || value.is_empty() || !value.iter().all(|b| b.is_ascii_digit()) || value.iter().any(|&b| b != b'0') { return Err(400); }
            length_seen = true;
        } else if name.eq_ignore_ascii_case(b"transfer-encoding") { return Err(400); }
        else if name.eq_ignore_ascii_case(b"if-none-match") { conditional.push(value.to_vec()); }
        else if name.eq_ignore_ascii_case(b"range") {
            if range.is_some() { return Err(400); }
            range = Some(value.to_vec());
        }
        pos = end + 2;
    }
    let host = match host.as_deref() {
        None if !http11 => 0,
        Some(h) if h == cfg.default_host => 0,
        Some(h) if h == cfg.other_host => 1,
        _ => return Err(400),
    };
    if fields[0] != b"GET" && fields[0] != b"HEAD" { return Err(405); }
    Ok(Request { head: fields[0] == b"HEAD", close, target, host, conditional, range })
}
fn decode_target(target: &str) -> Result<(String, &str, &str), u16> {
    if !target.starts_with('/') || target.contains('#') || target.contains('\\') { return Err(400); }
    let (raw_path, query) = target.split_once('?').map_or((target, ""), |(a,b)| (a, b));
    let mut path = Vec::with_capacity(raw_path.len());
    let bytes = raw_path.as_bytes();
    let hex = |b: u8| match b { b'0'..=b'9' => Some(b-b'0'), b'a'..=b'f' => Some(b-b'a'+10), b'A'..=b'F' => Some(b-b'A'+10), _ => None };
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%' {
            if i+2 >= bytes.len() { return Err(400); }
            path.push(hex(bytes[i+1]).ok_or(400u16)? * 16 + hex(bytes[i+2]).ok_or(400u16)?);
            i += 3;
        } else { path.push(bytes[i]); i += 1; }
    }
    if path.iter().any(|&b| b == 0 || b == b'\\') { return Err(400); }
    let path = String::from_utf8(path).map_err(|_| 400u16)?;
    if path.split('/').any(|s| s == "..") { return Err(403); }
    Ok((path, raw_path, query))
}
struct Resource { file: Option<File>, bytes: Option<Vec<u8>>, len: u64, etag: String, mime: &'static str, resident: Rc<Cell<usize>> }
impl Drop for Resource {
    fn drop(&mut self) { if let Some(bytes) = &self.bytes { self.resident.set(self.resident.get()-bytes.len()); } }
}
struct Cache { map: HashMap<(usize, String), Arc<Resource>>, order: VecDeque<(usize, String)>, memory: usize, resident: Rc<Cell<usize>> }
impl Cache {
    fn new() -> Self { Self { map: HashMap::new(), order: VecDeque::new(), memory: 0, resident: Rc::new(Cell::new(0)) } }
    fn insert(&mut self, key: (usize, String), resource: Arc<Resource>) {
        let len = resource.bytes.as_ref().map_or(0, |v| v.len());
        while self.map.len() >= 256 || self.memory + len > 16*1024*1024 {
            if let Some(old) = self.order.pop_front() { if let Some(r) = self.map.remove(&old) { self.memory -= r.bytes.as_ref().map_or(0, |v| v.len()); } }
            else { break; }
        }
        self.memory += len;
        self.order.push_back(key.clone());
        self.map.insert(key, resource);
    }
    fn lookup(&mut self, root: usize, path: &str, cfg: &Config) -> Result<Option<Arc<Resource>>, u16> {
        let key = (root, path.to_owned());
        if let Some(value) = self.map.get(&key) { return Ok(Some(value.clone())); }
        let mut parent: Option<File> = None;
        let mut components = path.split('/').filter(|c| !c.is_empty() && *c != ".").peekable();
        while let Some(part) = components.next() {
            let part = CString::new(part).map_err(|_| 400u16)?;
            let fd = unsafe { openat(parent.as_ref().map_or(cfg.roots[root].as_raw_fd(), |f| f.as_raw_fd()), part.as_ptr(), NOFOLLOW | CLOEXEC | NONBLOCK) };
            if fd < 0 { return Err(match errno() { 2 => 404, _ => 403 }); }
            let file = unsafe { File::from_raw_fd(fd) };
            let meta = file.metadata().map_err(|_| 403u16)?;
            if components.peek().is_some() {
                if !meta.is_dir() { return Err(403); }
                parent = Some(file);
            } else {
                if meta.is_dir() { return Ok(None); }
                if !meta.is_file() || path.ends_with('/') { return Err(403); }
                let etag = format!("\"{:x}-{:x}-{:x}-{:x}-{:x}\"", meta.dev(), meta.ino(), meta.len(), meta.mtime(), meta.mtime_nsec());
                let mime = if path.ends_with(".html") { "text/html" } else if path.ends_with(".txt") { "text/plain" } else { "application/octet-stream" };
                let (file, bytes) = if meta.len() <= 128*1024 && self.resident.get().saturating_add(meta.len() as usize) <= 16*1024*1024 {
                    let mut bytes = Vec::with_capacity(meta.len() as usize);
                    let mut file = file;
                    file.read_to_end(&mut bytes).map_err(|_| 403u16)?;
                    self.resident.set(self.resident.get()+bytes.len());
                    (None, Some(bytes))
                } else { (Some(file), None) };
                let resource = Arc::new(Resource { file, bytes, len: meta.len(), etag, mime, resident: self.resident.clone() });
                self.insert(key, resource.clone());
                return Ok(Some(resource));
            }
        }
        Ok(None)
    }
}
enum Body { Empty, Memory { resource: Arc<Resource>, position: usize, end: usize }, File { resource: Arc<Resource>, offset: i64, remaining: u64 } }
struct Response { header: Vec<u8>, written: usize, body: Body, close: bool }
fn response(status: u16, length: u64, extra: &str, body: Body, close: bool) -> Response {
    let reason = match status { 200 => "OK", 206 => "Partial Content", 301 => "Moved Permanently", 302 => "Found", 304 => "Not Modified", 400 => "Bad Request", 403 => "Forbidden", 404 => "Not Found", 405 => "Method Not Allowed", 408 => "Request Timeout", 416 => "Range Not Satisfiable", 431 => "Request Header Fields Too Large", _ => "Internal Server Error" };
    let header = format!("HTTP/1.1 {} {}\r\nContent-Length: {}\r\nConnection: {}\r\n{}\r\n", status, reason, length, if close {"close"} else {"keep-alive"}, extra).into_bytes();
    Response { header, written: 0, body, close }
}
fn empty(status: u16, close: bool) -> Response { response(status, 0, "", Body::Empty, close) }
fn range_number(bytes: &[u8]) -> Result<u64, u16> {
    if bytes.is_empty() || !bytes.iter().all(|b| b.is_ascii_digit()) { return Err(400); }
    // Arbitrarily long decimal positions are valid syntax and saturate beyond EOF.
    Ok(bytes.iter().fold(0u64, |n,b| n.saturating_mul(10).saturating_add((b-b'0') as u64)))
}
fn byte_range(value: &[u8], len: u64) -> Result<Option<(u64,u64)>,u16> {
    let value = trim(value);
    if !value.starts_with(b"bytes=") { return Err(400); }
    let value = &value[6..];
    if value.contains(&b',') { return Err(400); }
    let hyphen = value.iter().position(|&b| b == b'-').ok_or(400u16)?;
    let (a,b) = (&value[..hyphen], &value[hyphen+1..]);
    if a.is_empty() {
        let suffix = range_number(b)?;
        if suffix == 0 || len == 0 { return Ok(None); }
        return Ok(Some((len.saturating_sub(suffix),len-1)));
    }
    let start = range_number(a)?;
    let end = if b.is_empty() { len.saturating_sub(1) } else { range_number(b)? };
    if start >= len || end < start { return Ok(None); }
    Ok(Some((start,end.min(len-1))))
}
fn serve(req: &Request, cfg: &Config, cache: &mut Cache, close: bool) -> Response {
    let (path, raw_path, query) = match decode_target(&req.target) { Ok(v) => v, Err(e) => return empty(e, true) };
    if path == cfg.redirect_path { return response(302, 0, &format!("Location: {}\r\n",cfg.redirect_target), Body::Empty, close); }
    let (root, selected) = if path.starts_with(&cfg.alias) { (2, &path[cfg.alias.len()..]) } else { (req.host, path.as_str()) };
    let resource = match cache.lookup(root, selected, cfg) {
        Ok(Some(r)) => r,
        Err(e) => return empty(e, close),
        Ok(None) => {
            if !path.ends_with('/') {
                let location = format!("{}{}{}",raw_path.to_owned()+"/",if req.target.contains('?') {"?"} else {""},query);
                return response(301, 0, &format!("Location: {}\r\n",location), Body::Empty, close);
            }
            let index_path = format!("{}{}/{}", selected, if selected.ends_with('/') || selected.is_empty() {""} else {"/"}, cfg.index);
            match cache.lookup(root,&index_path,cfg) { Ok(Some(r)) => r, _ => return empty(403,close) }
        }
    };
    let mut extra = format!("Content-Type: {}\r\nETag: {}\r\n",resource.mime,resource.etag);
    let matches = req.conditional.iter().any(|v| v.split(|&b| b == b',').any(|part| {
        let part = trim(part);
        part == b"*" || part == resource.etag.as_bytes() || part.strip_prefix(b"W/").is_some_and(|v| v == resource.etag.as_bytes())
    }));
    if matches { return response(304,0,&extra,Body::Empty,close); }
    let mut start = 0;
    let mut length = resource.len;
    let mut status = 200;
    if let Some(range) = &req.range {
        match byte_range(range, resource.len) {
            Err(e) => return empty(e,true),
            Ok(None) => return response(416,0,&format!("Content-Range: bytes */{}\r\n",resource.len),Body::Empty,close),
            Ok(Some((a,b))) => { start = a; length = b-a+1; status = 206; extra.push_str(&format!("Content-Range: bytes {}-{}/{}\r\n",a,b,resource.len)); }
        }
    }
    let body = if req.head || length == 0 { Body::Empty }
        else if resource.bytes.is_some() { Body::Memory { resource, position: start as usize, end: (start+length) as usize } }
        else { Body::File { resource, offset: start as i64, remaining: length } };
    response(status,length,&extra,body,close)
}
struct Connection {
    stream: TcpStream, token: u64, input: Vec<u8>, response: Option<Response>, requests: usize,
    first_byte: Option<Instant>, idle_since: Instant, write_since: Instant, eof: bool, writing_interest: bool, closing: bool,
}
impl Connection {
    fn new(stream: TcpStream, token: u64, now: Instant) -> Self {
        Self { stream, token, input: Vec::with_capacity(1024), response: None, requests: 0,
            first_byte: None, idle_since: now, write_since: now, eof: false, writing_interest: false, closing: false }
    }
    fn make_response(&mut self, cfg: &Config, cache: &mut Cache, now: Instant) -> bool {
        let end = self.input.windows(4).position(|v| v == b"\r\n\r\n").map(|n| n+4);
        // Inspect only this request, never the bytes of the next pipelined header.
        let upto = end.unwrap_or(self.input.len());
        let bad = self.input[..upto].iter().enumerate().any(|(i,&b)| b == 0 || (b == b'\n' && (i == 0 || self.input[i-1] != b'\r')) || (b == b'\r' && i+1 < upto && self.input[i+1] != b'\n'));
        let error = if upto > cfg.header_bytes || (end.is_none() && upto >= cfg.header_bytes) { Some(431) } else if bad { Some(400) } else { None };
        if let Some(e) = error { self.response = Some(empty(e,true)); self.input.clear(); }
        else if let Some(end) = end {
            let parsed = parse(&self.input[..end], cfg);
            self.requests += 1;
            self.response = Some(match parsed { Ok(req) => serve(&req,cfg,cache,req.close || self.requests >= cfg.max_requests), Err(e) => empty(e,true) });
            self.input.drain(..end);
            self.first_byte = if self.input.is_empty() { None } else { Some(now) };
        } else { return false; }
        self.write_since = now;
        true
    }
    // Returns false on disconnect; limits each event's work for fairness.
    fn pump(&mut self, cfg: &Config, cache: &mut Cache, now: Instant) -> bool {
        let fd = self.stream.as_raw_fd();
        let mut budget = 1024*1024usize;
        let mut completed = 0usize;
        loop {
            if self.closing {
                // Send FIN before draining surplus input, preventing TCP reset from
                // discarding the final ordered response when the peer pipelined more.
                if budget == 0 { return true; }
                let mut discard = [0u8;8192];
                let n = unsafe { read(fd,discard.as_mut_ptr().cast(),discard.len()) };
                if n < 0 { match errno() { 4 => continue, 11 => return true, _ => return false } }
                if n == 0 { return false; }
                budget = budget.saturating_sub(n as usize);
                continue;
            }
            if let Some(res) = self.response.as_mut() {
                if budget == 0 { return true; }
                let header_left = &res.header[res.written..];
                let mut vectors = [IoVec { base: header_left.as_ptr(), len: header_left.len() }, IoVec { base: std::ptr::null(), len: 0 }];
                if let Body::Memory { resource, position, end } = &res.body {
                    vectors[1] = IoVec { base: unsafe { resource.bytes.as_ref().unwrap().as_ptr().add(*position) }, len: (*end-*position).min(budget) };
                }
                if vectors[0].len + vectors[1].len > 0 {
                    let wrote = unsafe { writev(fd,vectors.as_ptr(),if vectors[1].len > 0 {2} else {1}) };
                    if wrote < 0 { match errno() { 4 => continue, 11 => return true, _ => return false } }
                    if wrote == 0 { return false; }
                    let n = wrote as usize;
                    let header_bytes = n.min(res.header.len()-res.written);
                    res.written += header_bytes;
                    if let Body::Memory { position, .. } = &mut res.body { *position += n-header_bytes; }
                    budget = budget.saturating_sub(n);
                    self.write_since = now;
                    if res.written != res.header.len() { continue; }
                }
                if let Body::File { resource, offset, remaining } = &mut res.body {
                    if *remaining > 0 && budget > 0 {
                        let n = unsafe { sendfile(fd,resource.file.as_ref().unwrap().as_raw_fd(),offset,(*remaining).min(budget as u64) as usize) };
                        if n < 0 { match errno() { 4 => continue, 11 => return true, _ => return false } }
                        if n == 0 { return false; }
                        *remaining -= n as u64;
                        budget = budget.saturating_sub(n as usize);
                        self.write_since = now;
                    }
                }
                let done = match &res.body { Body::Empty => true, Body::Memory {position,end,..} => position == end, Body::File {remaining,..} => *remaining == 0 };
                if !done { continue; }
                if res.close {
                    let _ = self.stream.shutdown(Shutdown::Write);
                    self.response = None;
                    self.input.clear();
                    self.first_byte = None;
                    self.closing = true;
                    self.idle_since = now;
                    continue;
                }
                self.response = None;
                self.idle_since = now;
                completed += 1;
                if completed >= cfg.pipeline_depth.min(32) { return true; }
            }
            if self.make_response(cfg,cache,now) { continue; }
            if self.eof { return false; }
            let available = cfg.header_bytes.saturating_sub(self.input.len()).min(8192);
            if available == 0 { self.response = Some(empty(431,true)); self.write_since = now; continue; }
            let mut buffer = [0u8;8192];
            let n = unsafe { read(fd,buffer.as_mut_ptr().cast(),available) };
            if n < 0 { match errno() { 4 => continue, 11 => return true, _ => return false } }
            if n == 0 { self.eof = true; if self.input.is_empty() { return false; } return false; }
            if self.input.is_empty() { self.first_byte = Some(now); }
            self.input.extend_from_slice(&buffer[..n as usize]);
        }
    }
}
fn set_interest(ep: i32, op: i32, fd: i32, token: u64, writing: bool) -> bool {
    let event = Event { flags: (if writing { OUT } else { IN }) | RDHUP, data: token };
    unsafe { epoll_ctl(ep,op,fd,&event) == 0 }
}
fn run(cfg: Config) -> io::Result<()> {
    let listener = TcpListener::bind(cfg.listen)?;
    // std's bind uses a small fixed backlog. Size the completed-handshake queue
    // for the configured connection capacity; Linux applies its somaxconn cap.
    let backlog = cfg.max_connections.max(128).min(i32::MAX as usize) as i32;
    if unsafe { listen(listener.as_raw_fd(),backlog) } != 0 { return Err(io::Error::last_os_error()); }
    listener.set_nonblocking(true)?;
    let ep = unsafe { epoll_create1(CLOEXEC) };
    if ep < 0 { return Err(io::Error::last_os_error()); }
    let ep_handle = unsafe { File::from_raw_fd(ep) };
    let event = Event { flags: IN, data: 0 };
    if unsafe { epoll_ctl(ep,1,listener.as_raw_fd(),&event) } != 0 { return Err(io::Error::last_os_error()); }
    let mut connections: Vec<Option<Connection>> = Vec::new();
    let mut active = 0usize;
    let mut generation = 1u64;
    let mut events = [Event { flags: 0, data: 0 };256];
    let mut cache = Cache::new();
    let mut last_sweep = Instant::now();
    loop {
        // A ready buffered pipeline must run even without a new kernel read event.
        let count = unsafe { epoll_wait(ep,events.as_mut_ptr(),events.len() as i32,25) };
        if count < 0 { if errno() == 4 { continue; } return Err(io::Error::last_os_error()); }
        let now = Instant::now();
        for event in &events[..count as usize] {
            let token = event.data;
            if token == 0 {
                for _ in 0..128 {
                    match listener.accept() {
                        Ok((stream,_)) => {
                            if active >= cfg.max_connections { drop(stream); continue; }
                            stream.set_nonblocking(true)?;
                            stream.set_nodelay(true)?;
                            let fd = stream.as_raw_fd() as usize;
                            if fd >= connections.len() { connections.resize_with(fd+1,||None); }
                            generation = generation.wrapping_add(1).max(1);
                            let token = (generation << 32) | fd as u64;
                            if set_interest(ep,1,fd as i32,token,false) {
                                connections[fd] = Some(Connection::new(stream,token,now)); active += 1;
                            }
                        }
                        Err(e) if e.kind() == io::ErrorKind::WouldBlock => break,
                        Err(e) if e.kind() == io::ErrorKind::Interrupted => continue,
                        Err(_) => break,
                    }
                }
            } else {
                let fd = (token & 0xffff_ffff) as usize;
                if fd >= connections.len() || connections[fd].as_ref().is_none_or(|c| c.token != token) { continue; }
                let mut connection = connections[fd].take().unwrap();
                let flags = event.flags;
                let alive = flags & ERR == 0 && (flags & HUP == 0 || flags & IN != 0) && connection.pump(&cfg,&mut cache,now);
                // OUT also schedules already-buffered requests when an event budget ended.
                let writing = connection.response.is_some() || connection.input.windows(4).any(|w| w == b"\r\n\r\n");
                if alive && (writing == connection.writing_interest || set_interest(ep,3,fd as i32,token,writing)) { connection.writing_interest = writing; connections[fd] = Some(connection); }
                else { unsafe { epoll_ctl(ep,2,fd as i32,std::ptr::null()); } active -= 1; }
            }
        }
        if now.duration_since(last_sweep) >= Duration::from_millis(25) {
            last_sweep = now;
            for slot in &mut connections {
                if let Some(c) = slot.as_mut() {
                    let expired = if c.closing { now.duration_since(c.idle_since) >= cfg.idle_timeout.min(Duration::from_millis(250)) }
                        else if c.response.is_some() { now.duration_since(c.write_since) >= cfg.write_timeout }
                        else if let Some(first) = c.first_byte { now.duration_since(first) >= cfg.header_timeout }
                        else { now.duration_since(c.idle_since) >= cfg.idle_timeout };
                    if expired { unsafe { epoll_ctl(ep,2,c.stream.as_raw_fd(),std::ptr::null()); } *slot = None; active -= 1; }
                }
            }
        }
        let _ = &ep_handle;
    }
}
fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() != 3 || args[1] != "--config" { eprintln!("usage: server --config /path/server.conf"); std::process::exit(1); }
    match Config::load(&args[2]) { Ok(cfg) => if let Err(e) = run(cfg) { eprintln!("server: {e}"); std::process::exit(1); }, Err(e) => { eprintln!("config: {e}"); std::process::exit(1); } }
}
