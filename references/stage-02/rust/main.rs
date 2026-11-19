//! Stage 2 static HTTP server. Linux epoll, writev, openat and sendfile use libc FFI.
use std::collections::HashMap;
use std::ffi::CString;
use std::fs::File;
use std::io::{self, Read};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::os::fd::{AsRawFd, FromRawFd};
use std::sync::Arc;
use std::time::Instant;

const EPOLLIN: u32 = 1;
const EPOLLOUT: u32 = 4;
const EPOLLERR: u32 = 8;
const EPOLLHUP: u32 = 16;
const EAGAIN: i32 = 11;
const EINTR: i32 = 4;
const O_NONBLOCK: i32 = 0x800;
const O_CLOEXEC: i32 = 0x80000;
const O_NOFOLLOW: i32 = 0x20000;
#[repr(C, packed)]
#[derive(Clone, Copy)]
struct Event { events: u32, data: u64 }
#[repr(C)]
struct IoVec { base: *const u8, len: usize }
extern "C" {
    fn epoll_create1(flags: i32) -> i32;
    fn epoll_ctl(epfd: i32, op: i32, fd: i32, event: *mut Event) -> i32;
    fn epoll_wait(epfd: i32, events: *mut Event, max: i32, timeout: i32) -> i32;
    fn recv(fd: i32, buf: *mut u8, len: usize, flags: i32) -> isize;
    fn writev(fd: i32, vectors: *const IoVec, count: i32) -> isize;
    fn sendfile(out_fd: i32, in_fd: i32, offset: *mut i64, count: usize) -> isize;
    fn openat(dir_fd: i32, name: *const i8, flags: i32, ...) -> i32;
    fn signal(sig: i32, handler: usize) -> usize;
    fn listen(fd: i32, backlog: i32) -> i32;
}
fn errno() -> i32 { io::Error::last_os_error().raw_os_error().unwrap_or(0) }
fn now(start: Instant) -> u64 { start.elapsed().as_millis().min(u64::MAX as u128) as u64 }
fn elapsed(t: u64, duration: u64, current: u64) -> bool { current.saturating_sub(t) >= duration }

struct Config {
    listen: SocketAddr, root: String, max_connections: usize, header_bytes: usize,
    header_timeout: u64, idle_timeout: u64, write_timeout: u64, max_requests: usize,
    _pipeline_depth: usize,
}
impl Config {
    fn read(path: &str) -> Result<Self, String> {
        let text = std::fs::read_to_string(path).map_err(|e| e.to_string())?;
        let expected = ["listen", "root", "max_connections", "header_bytes", "header_timeout_ms",
            "idle_timeout_ms", "write_timeout_ms", "max_requests", "pipeline_depth"];
        let mut items = HashMap::new();
        for line in text.lines() {
            let line = line.trim();
            if line.is_empty() || line.starts_with('#') { continue; }
            let (key, value) = line.split_once('=').ok_or("configuration requires key=value")?;
            let (key, value) = (key.trim(), value.trim());
            if !expected.contains(&key) || items.insert(key, value).is_some() { return Err("unknown or duplicate setting".into()); }
        }
        if items.len() != expected.len() { return Err("missing setting".into()); }
        let number = |key| -> Result<u64, String> {
            let raw = items[key];
            if raw.is_empty() || !raw.bytes().all(|b| b.is_ascii_digit()) { return Err(format!("invalid {key}")); }
            raw.parse::<u64>().ok().filter(|&x| x > 0).ok_or_else(|| format!("invalid {key}"))
        };
        let count = |key| -> Result<usize, String> {
            usize::try_from(number(key)?).map_err(|_| format!("invalid {key}"))
        };
        let listen_text = items["listen"];
        let (_, port) = listen_text.rsplit_once(':').ok_or("invalid listen address")?;
        if port.is_empty() || !port.bytes().all(|b| b.is_ascii_digit()) || port.parse::<u16>().ok().filter(|&p| p > 0).is_none() {
            return Err("invalid listen port".into());
        }
        let listen = listen_text.parse::<SocketAddr>().map_err(|_| "invalid listen address")?;
        let root = items["root"].to_string();
        if !std::path::Path::new(&root).is_absolute() || !std::fs::metadata(&root).map(|m| m.is_dir()).unwrap_or(false) {
            return Err("root must be an existing absolute directory".into());
        }
        Ok(Self { listen, root, max_connections: count("max_connections")?, header_bytes: count("header_bytes")?,
            header_timeout: number("header_timeout_ms")?, idle_timeout: number("idle_timeout_ms")?,
            write_timeout: number("write_timeout_ms")?, max_requests: count("max_requests")?, _pipeline_depth: count("pipeline_depth")? })
    }
}

fn token(b: u8) -> bool {
    b.is_ascii_alphanumeric() || b"!#$%&'*+-.^_`|~".contains(&b)
}
fn trim(mut b: &[u8]) -> &[u8] {
    while b.first().is_some_and(|x| *x == b' ' || *x == b'\t') { b = &b[1..]; }
    while b.last().is_some_and(|x| *x == b' ' || *x == b'\t') { b = &b[..b.len()-1]; }
    b
}
fn hex(b: u8) -> Option<u8> {
    match b { b'0'..=b'9' => Some(b-b'0'), b'a'..=b'f' => Some(b-b'a'+10), b'A'..=b'F' => Some(b-b'A'+10), _ => None }
}
struct Request { head: bool, close: bool, path: String, method_supported: bool }
fn parse(raw: &[u8]) -> Result<Request, u16> {
    if raw.len() < 4 || !raw.ends_with(b"\r\n\r\n") { return Err(400); }
    let line_end = raw.windows(2).position(|w| w == b"\r\n").ok_or(400u16)?;
    let line = &raw[..line_end];
    let mut parts = line.split(|b| *b == b' ');
    let method = parts.next().ok_or(400u16)?;
    let target = parts.next().ok_or(400u16)?;
    let version = parts.next().ok_or(400u16)?;
    if parts.next().is_some() || method.is_empty() || !method.iter().copied().all(token) || target.is_empty()
        || target.iter().any(|&b| b <= b' ' || b == 127) || ![b"HTTP/1.0".as_slice(), b"HTTP/1.1".as_slice()].contains(&version) { return Err(400); }
    let mut close = version == b"HTTP/1.0";
    let mut length_seen = false;
    let mut pos = line_end + 2;
    while pos < raw.len()-2 {
        let size = raw[pos..].windows(2).position(|w| w == b"\r\n").ok_or(400u16)?;
        let field = &raw[pos..pos+size];
        if field.is_empty() || field[0] == b' ' || field[0] == b'\t' { return Err(400); }
        let colon = field.iter().position(|b| *b == b':').ok_or(400u16)?;
        if colon == 0 || !field[..colon].iter().copied().all(token) { return Err(400); }
        let name = &field[..colon];
        let value = trim(&field[colon+1..]);
        if name.eq_ignore_ascii_case(b"transfer-encoding") { return Err(400); }
        if name.eq_ignore_ascii_case(b"content-length") {
            if length_seen || value.is_empty() || !value.iter().all(|&b| b == b'0') { return Err(400); }
            length_seen = true;
        }
        if name.eq_ignore_ascii_case(b"connection") && value.split(|b| *b == b',').any(|t| trim(t).eq_ignore_ascii_case(b"close")) { close = true; }
        pos += size + 2;
    }
    if !target.starts_with(b"/") || target.contains(&b'#') { return Err(400); }
    let path = target.split(|b| *b == b'?').next().unwrap();
    let mut decoded = Vec::with_capacity(path.len());
    let mut i = 0;
    while i < path.len() {
        let b = if path[i] == b'%' {
            if i+2 >= path.len() { return Err(400); }
            let b = (hex(path[i+1]).ok_or(400u16)? << 4) | hex(path[i+2]).ok_or(400u16)?;
            i += 3; b
        } else { let b=path[i]; i+=1; b };
        if b == 0 || b == b'\\' { return Err(400); }
        decoded.push(b);
    }
    let path = String::from_utf8(decoded).map_err(|_| 400u16)?;
    Ok(Request { head: method == b"HEAD", close, path, method_supported: method == b"HEAD" || method == b"GET" })
}

#[derive(Clone)]
enum Payload { Empty, Bytes(Arc<Vec<u8>>), Disk(Arc<File>, u64) }
impl Payload {
    fn len(&self) -> u64 { match self { Self::Empty => 0, Self::Bytes(b) => b.len() as u64, Self::Disk(_, n) => *n } }
}
struct Files { root: File, cache: HashMap<String, Payload> }
impl Files {
    fn get(&mut self, path: &str) -> Result<Payload, u16> {
        let mut components = Vec::new();
        for part in path.split('/') {
            if part == ".." { return Err(403); }
            if !part.is_empty() && part != "." { components.push(part); }
        }
        if components.is_empty() { return Err(403); }
        let normalized = components.join("/");
        if let Some(value) = self.cache.get(&normalized) {
            if path.ends_with('/') || path.ends_with("/.") { return Err(403); }
            return Ok(value.clone());
        }
        let mut directory: Option<File> = None;
        let mut result = None;
        for (index, part) in components.iter().enumerate() {
            let name = CString::new(*part).map_err(|_| 400u16)?;
            let parent = directory.as_ref().unwrap_or(&self.root).as_raw_fd();
            // O_NOFOLLOW makes confinement race-safe; O_NONBLOCK prevents FIFO opens from blocking.
            let fd = unsafe { openat(parent, name.as_ptr(), O_CLOEXEC|O_NOFOLLOW|O_NONBLOCK) };
            if fd < 0 { return Err(match errno() { 2 | 20 => 404, 40 | 13 => 403, _ => 403 }); }
            let file = unsafe { File::from_raw_fd(fd) };
            let meta = file.metadata().map_err(|_| 403u16)?;
            if index+1 < components.len() {
                if !meta.is_dir() { return Err(403); }
                directory = Some(file);
            } else {
                if !meta.is_file() || path.ends_with('/') || path.ends_with("/.") { return Err(403); }
                result = Some((file, meta.len()));
            }
        }
        let (mut file, length) = result.ok_or(403u16)?;
        let payload = if length <= 65536 {
            let mut bytes = Vec::with_capacity(length as usize);
            file.read_to_end(&mut bytes).map_err(|_| 403u16)?;
            if bytes.len() as u64 != length { return Err(403); }
            Payload::Bytes(Arc::new(bytes))
        } else { Payload::Disk(Arc::new(file), length) };
        if self.cache.len() >= 128 { self.cache.clear(); }
        self.cache.insert(normalized, payload.clone());
        Ok(payload)
    }
}

struct Connection {
    stream: TcpStream, generation: u32, input: Vec<u8>, header: Vec<u8>, header_sent: usize,
    body: Payload, body_sent: u64, writing: bool, close: bool, served: usize,
    header_started: Option<u64>, idle_since: u64, write_progress: u64, interest: u32,
}
impl Connection {
    fn new(stream: TcpStream, generation: u32, current: u64) -> Self {
        Self { stream, generation, input: Vec::with_capacity(256), header: Vec::with_capacity(128), header_sent: 0,
            body: Payload::Empty, body_sent: 0, writing: false, close: false, served: 0,
            header_started: None, idle_since: current, write_progress: current, interest: EPOLLIN }
    }
    fn response(&mut self, status: u16, payload: Payload, head: bool, mut close: bool, config: &Config, current: u64) {
        self.served += 1;
        if self.served >= config.max_requests { close = true; }
        let reason = match status { 200=>"OK", 400=>"Bad Request", 403=>"Forbidden", 404=>"Not Found", 405=>"Method Not Allowed", 431=>"Request Header Fields Too Large", _=>"Error" };
        self.header.clear();
        self.header.extend_from_slice(format!("HTTP/1.1 {status} {reason}\r\nContent-Length: {}\r\nContent-Type: application/octet-stream\r\nConnection: {}\r\n\r\n", payload.len(), if close {"close"} else {"keep-alive"}).as_bytes());
        self.header_sent = 0;
        self.body = if head { Payload::Empty } else { payload };
        self.body_sent = 0;
        self.writing = true;
        self.close = close;
        self.write_progress = current;
        self.input.clear();
        self.header_started = None;
    }
    fn bad(&mut self, status: u16, config: &Config, current: u64) { self.response(status, Payload::Empty, false, true, config, current); }
    // Peek through one header, then consume only its bytes. All later pipeline bytes remain in
    // the kernel while the one outstanding response is sent: the queue bound is always one.
    fn read_request(&mut self, config: &Config, files: &mut Files, current: u64) -> i32 {
        let fd = self.stream.as_raw_fd();
        let mut peek = [0u8; 8192];
        loop {
            let allowance = config.header_bytes.saturating_sub(self.input.len()).saturating_add(1).min(peek.len());
            let n = unsafe { recv(fd, peek.as_mut_ptr(), allowance, 2) };
            if n == 0 { return -1; }
            if n < 0 { return match errno() { EINTR => continue, EAGAIN => 0, _ => -1 }; }
            if self.header_started.is_none() { self.header_started=Some(current); }
            let n = n as usize;
            let old = self.input.len();
            let total = old+n;
            let byte = |p: usize| if p < old {self.input[p]} else {peek[p-old]};
            let mut end = None;
            if total >= 4 {
                for p in old.saturating_sub(3)..=total-4 {
                    if byte(p)==b'\r' && byte(p+1)==b'\n' && byte(p+2)==b'\r' && byte(p+3)==b'\n' { end=Some(p+4); break; }
                }
            }
            let through = end.unwrap_or(total);
            for p in old..through {
                let b=byte(p);
                if b==0 || (b==b'\n' && (p==0 || byte(p-1)!=b'\r'))
                    || (p>0 && byte(p-1)==b'\r' && b!=b'\n') {
                    self.bad(400,config,current); return 1;
                }
            }
            if through > config.header_bytes { self.bad(431, config, current); return 1; }
            let consume = through-old;
            self.input.resize(through,0);
            let got = unsafe { recv(fd,self.input[old..].as_mut_ptr(),consume,0) };
            if got<=0 {
                self.input.truncate(old);
                if got<0 && errno()==EINTR {continue;}
                if got<0 && errno()==EAGAIN {return 0;}
                return -1;
            }
            self.input.truncate(old+got as usize);
            if self.input.len()==through && end.is_some() {
                match parse(&self.input) {
                    Err(status)=>self.bad(status,config,current),
                    Ok(request)=> {
                        let (status,payload)=if !request.method_supported {(405,Payload::Empty)} else {
                            match files.get(&request.path) { Ok(p)=>(200,p), Err(s)=>(s,Payload::Empty) }
                        };
                        self.response(status,payload,request.head,request.close,config,current);
                    }
                }
                return 1;
            }
        }
    }
    fn write_response(&mut self, current: u64, budget: &mut usize) -> i32 {
        let fd=self.stream.as_raw_fd();
        while *budget>0 {
            let header_left=&self.header[self.header_sent..];
            let n=match &self.body {
                Payload::Bytes(bytes)=> {
                    let remaining=&bytes[self.body_sent as usize..];
                    let vectors=[IoVec{base:header_left.as_ptr(),len:header_left.len()},IoVec{base:remaining.as_ptr(),len:remaining.len().min(*budget)}];
                    unsafe {writev(fd,vectors.as_ptr(),2)}
                }
                _ if !header_left.is_empty()=> {
                    let vector=IoVec{base:header_left.as_ptr(),len:header_left.len()};
                    unsafe{writev(fd,&vector,1)}
                }
                Payload::Disk(file,length) if self.body_sent<*length => {
                    let mut offset=self.body_sent as i64;
                    unsafe{sendfile(fd,file.as_raw_fd(),&mut offset,(*length-self.body_sent).min(*budget as u64) as usize)}
                }
                _=>return 1,
            };
            if n<0 {match errno(){EINTR=>continue,EAGAIN=>return 0,_=>return -1}}
            if n==0 {
                return if self.header_sent==self.header.len() && self.body_sent==self.body.len(){1}else{-1};
            }
            let n=n as usize;
            let h=n.min(self.header.len()-self.header_sent);
            self.header_sent+=h;
            self.body_sent+=(n-h) as u64;
            self.write_progress=current;
            *budget=budget.saturating_sub(n);
            if self.header_sent==self.header.len() && self.body_sent==self.body.len(){return 1;}
        }
        0
    }
    fn drive(&mut self, config: &Config, files: &mut Files, current: u64) -> bool {
        let mut budget=256*1024;
        for _ in 0..32 {
            if !self.writing {
                match self.read_request(config,files,current){-1=>return false,0=>return true,_=>{}}
            }
            match self.write_response(current,&mut budget){
                -1=>return false,
                0=>return true,
                _=>{
                    if self.close{
                        // Finish the advertised response before discarding a bounded amount of
                        // already-pipelined input. An unread receive queue would otherwise cause
                        // close(2) to reset TCP instead of delivering an orderly end of stream.
                        let _=self.stream.shutdown(std::net::Shutdown::Write);
                        let mut discard=[0u8;4096];
                        for _ in 0..16 {
                            let n=unsafe{recv(self.stream.as_raw_fd(),discard.as_mut_ptr(),discard.len(),0)};
                            if n<=0{break;}
                        }
                        return false;
                    }
                    self.writing=false;
                    self.body=Payload::Empty;
                    self.idle_since=current;
                    if budget==0{return true;}
                }
            }
        }
        true
    }
    fn expired(&self,c:&Config,current:u64)->bool {
        if self.writing {elapsed(self.write_progress,c.write_timeout,current)}
        else if let Some(first)=self.header_started {elapsed(first,c.header_timeout,current)}
        else {elapsed(self.idle_since,c.idle_timeout,current)}
    }
}
fn interest(ep:i32,fd:i32,op:i32,events:u32,generation:u32)->bool {
    let mut event=Event{events,data:((generation as u64)<<32)|(fd as u32 as u64)};
    unsafe{epoll_ctl(ep,op,fd,&mut event)==0}
}
fn run(config:Config)->io::Result<()> {
    let root=File::open(&config.root)?;
    if !root.metadata()?.is_dir(){return Err(io::Error::new(io::ErrorKind::InvalidInput,"invalid root"));}
    let mut files=Files{root,cache:HashMap::new()};
    let listener=TcpListener::bind(config.listen)?;
    listener.set_nonblocking(true)?;
    // Give simultaneous fresh clients an accept backlog commensurate with capacity.
    if unsafe{listen(listener.as_raw_fd(),config.max_connections.clamp(128,16384) as i32)}<0{return Err(io::Error::last_os_error());}
    let ep=unsafe{epoll_create1(O_CLOEXEC)};
    if ep<0{return Err(io::Error::last_os_error());}
    let _ep=unsafe{File::from_raw_fd(ep)};
    let mut listener_event=Event{events:EPOLLIN,data:u64::MAX};
    if unsafe{epoll_ctl(ep,1,listener.as_raw_fd(),&mut listener_event)}<0{return Err(io::Error::last_os_error());}
    let mut connections:Vec<Option<Box<Connection>>>=Vec::new();
    let mut count=0usize;
    let mut generation=0u32;
    let mut events=[Event{events:0,data:0};1024];
    let clock=Instant::now();
    let sweep=config.header_timeout.min(config.idle_timeout).min(config.write_timeout).min(10).max(1);
    let mut next_sweep=0;
    loop {
        let current=now(clock);
        if current>=next_sweep {
            for slot in &mut connections {
                if slot.as_ref().is_some_and(|c|c.expired(&config,current)) {
                    if let Some(conn)=slot.take(){unsafe{epoll_ctl(ep,2,conn.stream.as_raw_fd(),std::ptr::null_mut());}count-=1;}
                }
            }
            next_sweep=current.saturating_add(sweep);
        }
        let n=unsafe{epoll_wait(ep,events.as_mut_ptr(),events.len() as i32,next_sweep.saturating_sub(current).min(i32::MAX as u64) as i32)};
        if n<0 {if errno()==EINTR{continue;}return Err(io::Error::last_os_error());}
        for event in &events[..n as usize] {
            let data=event.data;
            if data==u64::MAX {
                for _ in 0..128 {
                    match listener.accept() {
                        Ok((stream,_))=>{
                            if count>=config.max_connections{drop(stream);continue;}
                            if stream.set_nonblocking(true).is_err(){continue;}
                            let _=stream.set_nodelay(true);
                            let fd=stream.as_raw_fd() as usize;
                            if fd>=connections.len(){connections.resize_with(fd+1,||None);}
                            generation=generation.wrapping_add(1);
                            if !interest(ep,fd as i32,1,EPOLLIN,generation){continue;}
                            connections[fd]=Some(Box::new(Connection::new(stream,generation,now(clock))));
                            count+=1;
                        }
                        Err(e) if e.kind()==io::ErrorKind::Interrupted=>continue,
                        Err(_)=>break,
                    }
                }
            } else {
                let fd=data as u32 as usize;
                let expected=(data>>32) as u32;
                let Some(slot)=connections.get_mut(fd) else{continue;};
                let Some(conn)=slot.as_mut() else{continue;};
                if conn.generation!=expected{continue;}
                let flags=event.events;
                let mut keep=flags & EPOLLERR==0 && conn.drive(&config,&mut files,now(clock));
                // A half-close may still carry a complete request; drive it before deciding to close.
                if flags & EPOLLHUP!=0{keep=false;}
                if keep {
                    let wanted=if conn.writing{EPOLLOUT}else{EPOLLIN};
                    if wanted!=conn.interest {
                        keep=interest(ep,fd as i32,3,wanted,conn.generation);
                        conn.interest=wanted;
                    }
                }
                if !keep {
                    unsafe{epoll_ctl(ep,2,fd as i32,std::ptr::null_mut());}
                    *slot=None;count-=1;
                }
            }
        }
    }
}
fn main() {
    // sendfile/writev must report EPIPE rather than terminate the process.
    unsafe{signal(13,1);}
    let args:Vec<_>=std::env::args().collect();
    if args.len()!=3 || args[1]!="--config" {eprintln!("usage: server --config PATH");std::process::exit(1);}
    let result=Config::read(&args[2]).and_then(|c|run(c).map_err(|e|e.to_string()));
    if let Err(error)=result{eprintln!("{error}");std::process::exit(1);}
}
