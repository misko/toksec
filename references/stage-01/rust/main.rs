//! Linux, standard-library-only Stage 1 HTTP file server.
use std::collections::{BTreeSet, HashMap};
use std::ffi::{c_int, c_void, CString};
use std::fs::{File, OpenOptions};
use std::io::{self, Read};
use std::net::{SocketAddr, TcpListener};
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd, RawFd};
use std::os::unix::fs::OpenOptionsExt;
use std::path::Path;
use std::sync::Arc;
use std::time::{Duration, Instant};

const O_NONBLOCK: c_int = 0x800;
const O_DIRECTORY: c_int = 0x10000;
const O_NOFOLLOW: c_int = 0x20000;
const O_CLOEXEC: c_int = 0x80000;
const O_PATH: c_int = 0x200000;
const EPOLLIN: u32 = 1;
const EPOLLOUT: u32 = 4;
const EPOLLERR: u32 = 8;
const EPOLLHUP: u32 = 16;
const MSG_NOSIGNAL: c_int = 0x4000;
const LISTENER: u64 = u64::MAX;
const CACHE_BYTES: usize = 16 * 1024 * 1024;
const CACHE_ENTRIES: usize = 256;
const CACHE_FILE_LIMIT: u64 = 64 * 1024;

// Linux epoll_event is packed on x86-64; all fields are copied, never referenced.
#[repr(C, packed)]
#[derive(Clone, Copy)]
struct Event {
    events: u32,
    data: u64,
}

unsafe extern "C" {
    fn epoll_create1(flags: c_int) -> c_int;
    fn epoll_ctl(epfd: c_int, op: c_int, fd: c_int, event: *const Event) -> c_int;
    fn epoll_wait(epfd: c_int, events: *mut Event, count: c_int, timeout: c_int) -> c_int;
    fn accept4(fd: c_int, address: *mut c_void, length: *mut u32, flags: c_int) -> c_int;
    fn listen(fd: c_int, backlog: c_int) -> c_int;
    fn recv(fd: c_int, buffer: *mut c_void, len: usize, flags: c_int) -> isize;
    fn send(fd: c_int, buffer: *const c_void, len: usize, flags: c_int) -> isize;
    fn sendfile(out_fd: c_int, in_fd: c_int, offset: *mut i64, len: usize) -> isize;
    fn shutdown(fd: c_int, how: c_int) -> c_int;
    fn openat(dirfd: c_int, name: *const i8, flags: c_int, ...) -> c_int;
    fn signal(number: c_int, handler: usize) -> usize;
}

struct Config {
    address: SocketAddr,
    root: File,
    max_connections: usize,
    header_bytes: usize,
    header_timeout: Duration,
    write_timeout: Duration,
}

impl Config {
    fn read() -> Result<Self, String> {
        let args: Vec<_> = std::env::args_os().collect();
        if args.len() != 3 || args[1] != "--config" {
            return Err("usage: server --config /absolute/config".into());
        }
        let text = std::fs::read_to_string(&args[2]).map_err(|e| e.to_string())?;
        let keys = ["listen", "root", "max_connections", "header_bytes", "header_timeout_ms",
                    "idle_timeout_ms", "write_timeout_ms", "max_requests", "pipeline_depth"];
        let mut values = HashMap::new();
        for line in text.lines() {
            let line = line.trim();
            if line.is_empty() || line.starts_with('#') {
                continue;
            }
            let (key, value) = line.split_once('=').ok_or("expected key=value")?;
            let key = key.trim();
            let value = value.trim();
            if !keys.contains(&key) || values.insert(key, value).is_some() {
                return Err("unknown or duplicate configuration key".into());
            }
        }
        if values.len() != keys.len() {
            return Err("missing configuration key".into());
        }
        let number = |key| -> Result<u64, String> {
            let value = values[key];
            if value.is_empty() || !value.bytes().all(|b| b.is_ascii_digit()) {
                return Err(format!("invalid {key}"));
            }
            value.parse::<u64>().ok().filter(|n| *n > 0).ok_or_else(|| format!("invalid {key}"))
        };
        let duration = |key| -> Result<Duration, String> {
            let duration = Duration::from_millis(number(key)?);
            Instant::now().checked_add(duration).ok_or_else(|| format!("invalid {key}"))?;
            Ok(duration)
        };
        let address: SocketAddr = values["listen"].parse().map_err(|_| "invalid listen address")?;
        // SocketAddr requires a numeric port; the shared interface also forbids zero.
        if address.port() == 0 {
            return Err("listen port must be positive".into());
        }
        let root_path = Path::new(values["root"]);
        if !root_path.is_absolute() || !std::fs::metadata(root_path).map_err(|e| e.to_string())?.is_dir() {
            return Err("root must be an existing absolute directory".into());
        }
        let root = OpenOptions::new().read(true).custom_flags(O_DIRECTORY | O_NONBLOCK | O_CLOEXEC)
            .open(root_path).map_err(|e| e.to_string())?;
        let max_connections = usize::try_from(number("max_connections")?).map_err(|_| "invalid connection limit")?;
        let header_bytes = usize::try_from(number("header_bytes")?).map_err(|_| "invalid header limit")?;
        let header_timeout = duration("header_timeout_ms")?;
        let write_timeout = duration("write_timeout_ms")?;
        duration("idle_timeout_ms")?;
        number("max_requests")?;
        number("pipeline_depth")?;
        Ok(Self { address, root, max_connections, header_bytes, header_timeout, write_timeout })
    }
}

fn token_char(b: u8) -> bool {
    b.is_ascii_alphanumeric() || b"!#$%&'*+-.^_`|~".contains(&b)
}

fn trim_ows(mut bytes: &[u8]) -> &[u8] {
    while matches!(bytes.first(), Some(b' ' | b'\t')) { bytes = &bytes[1..]; }
    while matches!(bytes.last(), Some(b' ' | b'\t')) { bytes = &bytes[..bytes.len()-1]; }
    bytes
}

fn hex(b: u8) -> Option<u8> {
    match b {
        b'0'..=b'9' => Some(b - b'0'),
        b'a'..=b'f' => Some(b - b'a' + 10),
        b'A'..=b'F' => Some(b - b'A' + 10),
        _ => None,
    }
}

fn decode_path(target: &[u8]) -> Result<String, u16> {
    if target.first() != Some(&b'/') || target.contains(&b'#') ||
        target.iter().any(|b| *b <= 32 || *b == 127) {
        return Err(400);
    }
    let path = target.split(|b| *b == b'?').next().unwrap();
    let mut output = Vec::with_capacity(path.len());
    let mut index = 0;
    while index < path.len() {
        let b = if path[index] == b'%' {
            if index + 2 >= path.len() { return Err(400); }
            let b = (hex(path[index + 1]).ok_or(400u16)? << 4) | hex(path[index + 2]).ok_or(400u16)?;
            index += 3;
            b
        } else {
            let b = path[index];
            index += 1;
            b
        };
        if b == 0 || b == b'\\' { return Err(400); }
        output.push(b);
    }
    let output = String::from_utf8(output).map_err(|_| 400u16)?;
    if output.split('/').any(|component| component == "..") { return Err(403); }
    Ok(output)
}

fn parse_request(bytes: &[u8]) -> Result<String, u16> {
    let first_end = bytes.windows(2).position(|w| w == b"\r\n").ok_or(400u16)?;
    let mut parts = bytes[..first_end].split(|b| *b == b' ');
    let method = parts.next().ok_or(400u16)?;
    let target = parts.next().ok_or(400u16)?;
    let version = parts.next().ok_or(400u16)?;
    if method.is_empty() || !method.iter().copied().all(token_char) || target.is_empty() ||
        parts.next().is_some() || (version != b"HTTP/1.1" && version != b"HTTP/1.0") {
        return Err(400);
    }
    let mut position = first_end + 2;
    let mut length_seen = false;
    while position + 2 < bytes.len() {
        let end = position + bytes[position..].windows(2).position(|w| w == b"\r\n").ok_or(400u16)?;
        let line = &bytes[position..end];
        let colon = line.iter().position(|b| *b == b':').ok_or(400u16)?;
        let name = &line[..colon];
        let value = &line[colon + 1..];
        if name.is_empty() || !name.iter().copied().all(token_char) ||
            value.iter().any(|b| (*b < 32 && *b != b'\t') || *b == 127) {
            return Err(400);
        }
        if name.eq_ignore_ascii_case(b"transfer-encoding") { return Err(400); }
        if name.eq_ignore_ascii_case(b"content-length") {
            let value = trim_ows(value);
            if length_seen || value.is_empty() || !value.iter().all(|b| *b == b'0') {
                return Err(400);
            }
            length_seen = true;
        }
        position = end + 2;
    }
    let path = decode_path(target)?;
    if method != b"GET" { return Err(405); }
    Ok(path)
}

fn file_error(error: io::Error) -> u16 {
    match error.raw_os_error() {
        Some(2 | 20 | 36) => 404, // missing, non-directory component, excessive filename
        Some(13 | 1 | 40 | 6 | 19) => 403, // access denied, symlink, device/nonregular
        Some(23 | 24 | 12) => 503,
        _ => 403,
    }
}

fn open_file(root: RawFd, path: &str) -> Result<(File, u64), u16> {
    let mut components = path.split('/').filter(|part| !part.is_empty() && *part != ".").peekable();
    let mut parent: Option<File> = None;
    while let Some(component) = components.next() {
        let last = components.peek().is_none();
        let name = CString::new(component).map_err(|_| 400u16)?;
        let dirfd = parent.as_ref().map_or(root, AsRawFd::as_raw_fd);
        let flags = O_NOFOLLOW | O_CLOEXEC | if last { O_NONBLOCK } else { O_PATH };
        // The directory fd remains owned throughout this call, and the NUL-terminated
        // name is valid. O_NOFOLLOW forbids following the final component at each step.
        let fd = unsafe { openat(dirfd, name.as_ptr(), flags) };
        if fd < 0 { return Err(file_error(io::Error::last_os_error())); }
        let file = unsafe { File::from_raw_fd(fd) };
        let metadata = file.metadata().map_err(file_error)?;
        if metadata.file_type().is_symlink() { return Err(403); }
        if last {
            if !metadata.is_file() || path.ends_with('/') || path.ends_with("/.") { return Err(403); }
            return Ok((file, metadata.len()));
        }
        if !metadata.is_dir() { return Err(404); }
        parent = Some(file);
    }
    Err(403)
}

fn header(status: u16, size: u64) -> Vec<u8> {
    let reason = match status {
        200 => "OK", 400 => "Bad Request", 403 => "Forbidden", 404 => "Not Found",
        405 => "Method Not Allowed", 431 => "Request Header Fields Too Large",
        503 => "Service Unavailable", _ => "Error",
    };
    format!("HTTP/1.1 {status} {reason}\r\nContent-Length: {size}\r\nConnection: close\r\nContent-Type: application/octet-stream\r\n\r\n").into_bytes()
}

enum Output {
    Buffer { data: Arc<Vec<u8>>, position: usize },
    File { header: Vec<u8>, position: usize, file: File, offset: i64, remaining: u64 },
}

struct Cache {
    entries: HashMap<String, Arc<Vec<u8>>>,
    bytes: usize,
}

impl Cache {
    fn response(&mut self, config: &Config, request: &[u8]) -> (Output, bool) {
        let result = (|| {
            let path = parse_request(request)?;
            if let Some(data) = self.entries.get(&path) {
                return Ok(Output::Buffer { data: data.clone(), position: 0 });
            }
            let (mut file, size) = open_file(config.root.as_raw_fd(), &path)?;
            let mut bytes = header(200, size);
            let cost = size as usize + bytes.len() + path.len();
            if size <= CACHE_FILE_LIMIT && self.entries.len() < CACHE_ENTRIES &&
                cost <= CACHE_BYTES.saturating_sub(self.bytes) {
                let start = bytes.len();
                bytes.resize(start + size as usize, 0);
                file.read_exact(&mut bytes[start..]).map_err(|_| 403u16)?;
                let data = Arc::new(bytes);
                self.bytes += cost;
                self.entries.insert(path, data.clone());
                Ok(Output::Buffer { data, position: 0 })
            } else {
                Ok(Output::File { header: bytes, position: 0, file, offset: 0, remaining: size })
            }
        })();
        match result {
            Ok(output) => (output, false),
            Err(status) => (Output::Buffer { data: Arc::new(header(status, 0)), position: 0 }, true),
        }
    }
}

struct Connection {
    fd: OwnedFd,
    token: u64,
    deadline: Instant,
    input: Vec<u8>,
    output: Option<Output>,
    graceful_error: bool,
    draining: bool,
}

impl Connection {
    fn respond_error(&mut self, status: u16, config: &Config) {
        self.output = Some(Output::Buffer { data: Arc::new(header(status, 0)), position: 0 });
        self.input = Vec::new();
        self.graceful_error = true;
        self.deadline = Instant::now() + config.write_timeout;
    }

    // true means an incomplete operation remains; false closes the connection.
    fn receive(&mut self, config: &Config, cache: &mut Cache) -> bool {
        let mut buffer = [0u8; 8192];
        loop {
            if Instant::now() >= self.deadline { return false; }
            let room = config.header_bytes.saturating_sub(self.input.len());
            if room == 0 {
                self.respond_error(431, config);
                return self.transmit();
            }
            let received = unsafe { recv(self.fd.as_raw_fd(), buffer.as_mut_ptr().cast(), room.min(buffer.len()), 0) };
            if received == 0 { return false; }
            if received < 0 {
                return match io::Error::last_os_error().kind() {
                    io::ErrorKind::WouldBlock => true,
                    io::ErrorKind::Interrupted => continue,
                    _ => false,
                };
            }
            let old_length = self.input.len();
            self.input.extend_from_slice(&buffer[..received as usize]);
            let mut header_end = None;
            for index in old_length..self.input.len() {
                let byte = self.input[index];
                if byte == 0 || (byte == b'\n' && (index == 0 || self.input[index - 1] != b'\r')) ||
                    (index > 0 && self.input[index - 1] == b'\r' && byte != b'\n') {
                    self.respond_error(400, config);
                    return self.transmit();
                }
                if index >= 3 && self.input[index - 3..=index] == *b"\r\n\r\n" {
                    header_end = Some(index + 1);
                    break;
                }
            }
            if let Some(end) = header_end {
                let (output, error) = cache.response(config, &self.input[..end]);
                self.output = Some(output);
                self.graceful_error = error;
                self.input = Vec::new();
                self.deadline = Instant::now() + config.write_timeout;
                return self.transmit();
            }
        }
    }

    fn transmit(&mut self) -> bool {
        let fd = self.fd.as_raw_fd();
        let mut quota = 256 * 1024;
        loop {
            let result = match self.output.as_mut().unwrap() {
                Output::Buffer { data, position } => {
                    if *position == data.len() { return self.finish(); }
                    let result = unsafe { send(fd, data[*position..].as_ptr().cast(), (data.len() - *position).min(quota), MSG_NOSIGNAL) };
                    if result > 0 { *position += result as usize; }
                    result
                }
                Output::File { header, position, file, offset, remaining } => {
                    if *position != header.len() {
                        let result = unsafe { send(fd, header[*position..].as_ptr().cast(), header.len() - *position, MSG_NOSIGNAL) };
                        if result > 0 { *position += result as usize; }
                        result
                    } else {
                        if *remaining == 0 { return false; }
                        let result = unsafe { sendfile(fd, file.as_raw_fd(), offset, (*remaining).min(quota as u64) as usize) };
                        if result > 0 { *remaining -= result as u64; }
                        result
                    }
                }
            };
            if result <= 0 {
                if result == 0 { return false; }
                return match io::Error::last_os_error().kind() {
                    io::ErrorKind::WouldBlock => true,
                    io::ErrorKind::Interrupted => continue,
                    _ => false,
                };
            }
            quota = quota.saturating_sub(result as usize);
            if quota == 0 { return true; }
        }
    }

    fn finish(&mut self) -> bool {
        if !self.graceful_error { return false; }
        // An error may leave body/excess-header bytes unread. Send FIN first and
        // briefly drain incoming data so close does not replace the response with RST.
        unsafe { shutdown(self.fd.as_raw_fd(), 1); }
        self.draining = true;
        self.output = None;
        self.deadline = Instant::now() + Duration::from_millis(250);
        self.drain()
    }

    fn drain(&mut self) -> bool {
        let mut bytes = [0u8; 8192];
        for _ in 0..32 {
            let result = unsafe { recv(self.fd.as_raw_fd(), bytes.as_mut_ptr().cast(), bytes.len(), 0) };
            if result == 0 { return false; }
            if result < 0 {
                return match io::Error::last_os_error().kind() {
                    io::ErrorKind::WouldBlock => true,
                    io::ErrorKind::Interrupted => continue,
                    _ => false,
                };
            }
        }
        true
    }
}

fn control(epoll: RawFd, operation: c_int, fd: RawFd, flags: u32, token: u64) -> io::Result<()> {
    let event = Event { events: flags, data: token };
    if unsafe { epoll_ctl(epoll, operation, fd, &event) } < 0 {
        Err(io::Error::last_os_error())
    } else { Ok(()) }
}

fn serve(config: Config) -> io::Result<()> {
    // sendfile lacks MSG_NOSIGNAL; the process must survive disconnected peers.
    unsafe { signal(13, 1); }
    let listener = TcpListener::bind(config.address)?;
    listener.set_nonblocking(true)?;
    if unsafe { listen(listener.as_raw_fd(), config.max_connections.min(i32::MAX as usize) as c_int) } < 0 {
        return Err(io::Error::last_os_error());
    }
    let raw_epoll = unsafe { epoll_create1(O_CLOEXEC) };
    if raw_epoll < 0 { return Err(io::Error::last_os_error()); }
    let epoll = unsafe { OwnedFd::from_raw_fd(raw_epoll) };
    control(raw_epoll, 1, listener.as_raw_fd(), EPOLLIN, LISTENER)?;
    let mut connections: Vec<Option<Connection>> = Vec::new();
    let mut timers: BTreeSet<(Instant, u64)> = BTreeSet::new();
    let mut cache = Cache { entries: HashMap::new(), bytes: 0 };
    let mut active = 0usize;
    let mut generation = 0u32;
    let mut events = [Event { events: 0, data: 0 }; 1024];
    loop {
        let now = Instant::now();
        while let Some(&(deadline, token)) = timers.first() {
            if deadline > now { break; }
            timers.pop_first();
            let fd = token as u32 as usize;
            if connections.get(fd).and_then(Option::as_ref).is_some_and(|c| c.token == token) {
                connections[fd] = None;
                active -= 1;
            }
        }
        let timeout = timers.first().map_or(-1, |(deadline, _)| {
            let duration = deadline.saturating_duration_since(Instant::now());
            duration.as_millis().saturating_add(u128::from(duration.subsec_nanos() % 1_000_000 != 0))
                .min(i32::MAX as u128) as c_int
        });
        let count = unsafe { epoll_wait(epoll.as_raw_fd(), events.as_mut_ptr(), events.len() as c_int, timeout) };
        if count < 0 {
            if io::Error::last_os_error().kind() == io::ErrorKind::Interrupted { continue; }
            return Err(io::Error::last_os_error());
        }
        for event in &events[..count as usize] {
            let token = event.data;
            let flags = event.events;
            if token == LISTENER {
                for _ in 0..128 {
                    let fd = unsafe { accept4(listener.as_raw_fd(), std::ptr::null_mut(), std::ptr::null_mut(), O_NONBLOCK | O_CLOEXEC) };
                    if fd < 0 {
                        if io::Error::last_os_error().kind() == io::ErrorKind::Interrupted { continue; }
                        break;
                    }
                    let owned = unsafe { OwnedFd::from_raw_fd(fd) };
                    if active >= config.max_connections { continue; }
                    generation = generation.wrapping_add(1);
                    let token = ((generation as u64) << 32) | fd as u32 as u64;
                    let mut connection = Connection {
                        fd: owned, token, deadline: Instant::now() + config.header_timeout,
                        input: Vec::new(), output: None, graceful_error: false, draining: false,
                    };
                    if !connection.receive(&config, &mut cache) { continue; }
                    let interest = if connection.output.is_some() { EPOLLOUT } else { EPOLLIN };
                    if control(raw_epoll, 1, fd, interest, token).is_err() { continue; }
                    timers.insert((connection.deadline, token));
                    let index = fd as usize;
                    if index >= connections.len() { connections.resize_with(index + 1, || None); }
                    connections[index] = Some(connection);
                    active += 1;
                }
            } else {
                let index = token as u32 as usize;
                if !connections.get(index).and_then(Option::as_ref).is_some_and(|c| c.token == token) { continue; }
                let mut connection = connections[index].take().unwrap();
                timers.remove(&(connection.deadline, token));
                let was_writing = connection.output.is_some();
                let keep = if Instant::now() >= connection.deadline || flags & (EPOLLERR | EPOLLHUP) != 0 {
                    false
                } else if connection.draining { connection.drain() }
                else if was_writing { connection.transmit() } else { connection.receive(&config, &mut cache) };
                if keep {
                    let writing = connection.output.is_some();
                    if was_writing == writing || control(raw_epoll, 3, index as RawFd, if writing { EPOLLOUT } else { EPOLLIN }, token).is_ok() {
                        timers.insert((connection.deadline, token));
                        connections[index] = Some(connection);
                        continue;
                    }
                }
                active -= 1;
            }
        }
    }
}

fn main() {
    let result = Config::read().and_then(|config| serve(config).map_err(|error| error.to_string()));
    if let Err(error) = result {
        eprintln!("server: {error}");
        std::process::exit(1);
    }
}
