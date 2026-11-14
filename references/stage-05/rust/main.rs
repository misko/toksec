use std::collections::{HashMap, HashSet, VecDeque};
use std::ffi::CString;
use std::fs::{self, File};
use std::io::{self, Read, Write};
use std::net::{Shutdown, SocketAddr, TcpListener, TcpStream};
use std::os::fd::{AsRawFd, FromRawFd, RawFd};
use std::os::unix::fs::MetadataExt;
use std::sync::{Arc, atomic::{AtomicBool, Ordering}};
use std::time::{Duration, Instant};

const IN: u32 = 1;
const OUT: u32 = 4;
const ERR: u32 = 8;
const HUP: u32 = 16;
const RDHUP: u32 = 8192;
const CLOEXEC: i32 = 524288;
const NONBLOCK: i32 = 2048;
const NOFOLLOW: i32 = 131072;
const DIRECTORY: i32 = 65536;
// Bound establishment bursts and share persistent connections across downstreams.
const UPSTREAM_EXCHANGES: usize = 64;
#[repr(C, packed)]
#[derive(Clone, Copy)]
struct Event { events: u32, data: u64 }
#[repr(C)]
struct Sock4 { family: u16, port: u16, addr: [u8; 4], zero: [u8; 8] }
#[repr(C)]
struct Sock6 { family: u16, port: u16, flow: u32, addr: [u8; 16], scope: u32 }
extern "C" {
    fn epoll_create1(flags: i32) -> i32;
    fn epoll_ctl(epfd: i32, op: i32, fd: i32, event: *mut Event) -> i32;
    fn epoll_wait(epfd: i32, events: *mut Event, n: i32, timeout: i32) -> i32;
    fn openat(dir: i32, path: *const i8, flags: i32, ...) -> i32;
    fn sendfile(out: i32, input: i32, offset: *mut i64, count: usize) -> isize;
    fn socket(domain: i32, kind: i32, protocol: i32) -> i32;
    fn connect(fd: i32, addr: *const u8, len: u32) -> i32;
    fn listen(fd: i32, backlog: i32) -> i32;
    fn signal(sig: i32, handler: usize) -> usize;
    fn close(fd: i32) -> i32;
}
static RELOAD: AtomicBool = AtomicBool::new(false);
static STOP: AtomicBool = AtomicBool::new(false);
extern "C" fn on_signal(sig: i32) {
    if sig == 1 { RELOAD.store(true, Ordering::Relaxed); }
    if sig == 15 { STOP.store(true, Ordering::Relaxed); }
}
fn ms(n: u64) -> Duration { Duration::from_millis(n) }
fn set_backlog(listener:&TcpListener,connections:usize)->io::Result<()> {
    let backlog=connections.max(128).min(i32::MAX as usize) as i32;
    if unsafe {listen(listener.as_raw_fd(),backlog)}<0 {Err(io::Error::last_os_error())}else{Ok(())}
}
fn number(s: &str) -> Result<u64, String> {
    if s.is_empty() || !s.bytes().all(|b| b.is_ascii_digit()) { return Err("expected decimal integer".into()); }
    s.parse().map_err(|_| "integer overflow".into())
}
fn authority(s: &str) -> Result<(String, String), String> {
    let (name, port) = match s.split_once(':') { Some((h,p)) => (h,Some(p)), None => (s,None) };
    if name.is_empty() || !name.is_ascii() || name.split('.').any(|p| p.is_empty() || p.starts_with('-') || p.ends_with('-') || !p.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'-')) {
        return Err("invalid host".into());
    }
    if let Some(p) = port { if number(p)? > 65535 { return Err("invalid host port".into()); } }
    Ok((name.to_ascii_lowercase(), s.to_ascii_lowercase()))
}
fn address(s: &str) -> Result<SocketAddr, String> {
    let p = s.rsplit_once(':').ok_or("missing port")?.1;
    if number(p)? == 0 { return Err("zero port".into()); }
    s.parse::<SocketAddr>().map_err(|_| "invalid socket address".into())
}
fn root_file(s: &str) -> Result<Arc<File>, String> {
    if !s.starts_with('/') || s.as_bytes().contains(&0) { return Err("root must be absolute".into()); }
    let path = CString::new(s).map_err(|_| "invalid root")?;
    let fd = unsafe { openat(-100, path.as_ptr(), DIRECTORY | NONBLOCK | CLOEXEC | NOFOLLOW) };
    if fd < 0 { return Err(format!("invalid directory: {s}")); }
    Ok(Arc::new(unsafe { File::from_raw_fd(fd) }))
}
struct Config {
    listen: SocketAddr, root: Arc<File>, root_name: String,
    host: String, other_host: String, other_root: Arc<File>, other_name: String,
    alias: String, alias_root: Arc<File>, alias_name: String,
    redirect: String, location: String, index: String, proxy: String,
    upstreams: Vec<SocketAddr>,
    max_connections: usize, header_bytes: usize, header_timeout: Duration,
    idle_timeout: Duration, write_timeout: Duration, max_requests: usize,
    _pipeline_depth: usize, upstream_timeout: Duration, body_bytes: usize,
    cache_ttl: Duration, cache_bytes: usize, rate: f64, burst: f64, drain: Duration,
}
impl Config {
    fn load(path: &str) -> Result<Self, String> {
        let data = fs::read_to_string(path).map_err(|e| e.to_string())?;
        let mut v = HashMap::new();
        let keys = ["listen","root","max_connections","header_bytes","header_timeout_ms","idle_timeout_ms","write_timeout_ms","max_requests","pipeline_depth","default_host","host_root","alias","redirect","index","proxy_prefix","upstreams","upstream_timeout_ms","body_bytes","cache_ttl_ms","cache_bytes","rate_per_second","rate_burst","drain_timeout_ms"];
        for line in data.lines() {
            let line = line.trim();
            if line.is_empty() || line.starts_with('#') { continue; }
            let (k,x) = line.split_once('=').ok_or("invalid configuration line")?;
            let (k,x) = (k.trim(), x.trim());
            if !keys.contains(&k) || v.insert(k.to_string(),x.to_string()).is_some() { return Err("unknown or duplicate setting".into()); }
        }
        if v.len() != keys.len() { return Err("missing setting".into()); }
        let get = |k: &str| -> &str { &v[k] };
        let n = |k: &str| -> Result<u64,String> { let x=number(get(k))?; if x==0 && k!="rate_per_second" { Err("zero limit".into()) } else { Ok(x) } };
        let us = |k: &str| -> Result<usize,String> { usize::try_from(n(k)?).map_err(|_| "limit overflow".into()) };
        let (host,_) = authority(get("default_host"))?;
        if host != get("default_host").to_ascii_lowercase() { return Err("default host port".into()); }
        let (oh,op) = get("host_root").split_once(':').ok_or("invalid host_root")?;
        let (other_host,_) = authority(oh)?;
        if other_host == host || oh.contains(':') { return Err("invalid host mapping".into()); }
        let (alias,ap) = get("alias").split_once(':').ok_or("invalid alias")?;
        let (redirect,location) = get("redirect").split_once(':').ok_or("invalid redirect")?;
        for p in [alias, redirect, location, get("proxy_prefix")] {
            if !p.starts_with('/') || p.bytes().any(|b| b < 33 || b==127 || b==b'\\' || b==b'#') { return Err("invalid routing path".into()); }
        }
        if !alias.ends_with('/') || !get("proxy_prefix").ends_with('/') { return Err("prefix needs trailing slash".into()); }
        let index=get("index");
        if index.is_empty() || index=="." || index==".." || index.contains(['/', '\\']) || index.as_bytes().contains(&0) { return Err("invalid index".into()); }
        let upstreams=get("upstreams").split(',').map(address).collect::<Result<Vec<_>,_>>()?;
        if upstreams.is_empty() { return Err("no upstreams".into()); }
        Ok(Self {
            listen: address(get("listen"))?, root:root_file(get("root"))?, root_name:get("root").into(),
            host, other_host, other_root:root_file(op)?, other_name:op.into(),
            alias:alias.into(), alias_root:root_file(ap)?, alias_name:ap.into(),
            redirect:redirect.into(), location:location.into(), index:index.into(), proxy:get("proxy_prefix").into(), upstreams,
            max_connections:us("max_connections")?, header_bytes:us("header_bytes")?, header_timeout:ms(n("header_timeout_ms")?), idle_timeout:ms(n("idle_timeout_ms")?),
            write_timeout:ms(n("write_timeout_ms")?), max_requests:us("max_requests")?, _pipeline_depth:us("pipeline_depth")?, upstream_timeout:ms(n("upstream_timeout_ms")?),
            body_bytes:us("body_bytes")?, cache_ttl:ms(n("cache_ttl_ms")?), cache_bytes:us("cache_bytes")?, rate:n("rate_per_second")? as f64,
            burst:n("rate_burst")? as f64, drain:ms(n("drain_timeout_ms")?),
        })
    }
}
type Headers = Vec<(Vec<u8>, Vec<u8>)>;
fn token(s: &[u8]) -> bool { !s.is_empty() && s.iter().all(|b| b.is_ascii_alphanumeric() || b"!#$%&'*+-.^_`|~".contains(b)) }
fn trim(mut x: &[u8]) -> &[u8] {
    while matches!(x.first(),Some(b' ' | b'\t')) { x=&x[1..]; }
    while matches!(x.last(),Some(b' ' | b'\t')) { x=&x[..x.len()-1]; }
    x
}
fn header_line(line: &[u8]) -> Result<(Vec<u8>,Vec<u8>), u16> {
    let pos=line.iter().position(|b| *b==b':').ok_or(400u16)?;
    if !token(&line[..pos]) { return Err(400); }
    let val=trim(&line[pos+1..]);
    if val.iter().any(|b| (*b<32 && *b!=b'\t') || *b==127) { return Err(400); }
    Ok((line[..pos].to_ascii_lowercase(),val.to_vec()))
}
fn vals<'a>(h: &'a Headers, name: &'a [u8]) -> impl Iterator<Item=&'a [u8]> { h.iter().filter(move |(k,_)| k==name).map(|(_,v)| v.as_slice()) }
fn val<'a>(h: &'a Headers, name: &'a [u8]) -> Option<&'a [u8]> { vals(h,name).next() }
fn tokens(h: &Headers, name: &[u8]) -> HashSet<Vec<u8>> {
    vals(h,name).flat_map(|v| v.split(|b| *b==b',').map(|s| trim(s).to_ascii_lowercase())).collect()
}
fn decimal(s: &[u8]) -> Result<usize,u16> {
    if s.is_empty() || !s.iter().all(|b| b.is_ascii_digit()) { return Err(400); }
    s.iter().try_fold(0usize, |n,b| n.checked_mul(10).and_then(|n| n.checked_add((b-b'0') as usize)).ok_or(400))
}
fn head_end(buf: &[u8], limit: usize) -> Result<Option<usize>,u16> {
    for (i,b) in buf.iter().enumerate() {
        if *b==0 || (*b==b'\n' && (i==0 || buf[i-1]!=b'\r')) || (i>0 && buf[i-1]==b'\r' && *b!=b'\n') { return Err(400); }
        if i>=3 && &buf[i-3..=i]==b"\r\n\r\n" { return if i+1>limit {Err(431)} else {Ok(Some(i+1))}; }
        if i+1>limit { return Err(431); }
    }
    if buf.len()>=limit { Err(431) } else { Ok(None) }
}
fn parse_headers(raw: &[u8]) -> Result<(Vec<u8>,Headers),u16> {
    let mut lines=raw[..raw.len()-2].split(|b| *b==b'\n');
    let first=lines.next().ok_or(400u16)?;
    let first=first.strip_suffix(b"\r").ok_or(400u16)?.to_vec();
    let mut h=Vec::new();
    for line in lines {
        if line.is_empty() { continue; }
        let line=line.strip_suffix(b"\r").ok_or(400u16)?;
        if line.is_empty() { continue; }
        h.push(header_line(line)?);
    }
    Ok((first,h))
}
fn decode_path(raw: &str) -> Result<String,u16> {
    if !raw.starts_with('/') || raw.contains(['#','\\']) { return Err(400); }
    let mut result=Vec::with_capacity(raw.len()); let bytes=raw.as_bytes(); let mut i=0;
    while i<bytes.len() {
        if bytes[i]<32 || bytes[i]==127 {return Err(400)}
        let b=if bytes[i]==b'%' {
            if i+2>=bytes.len() { return Err(400); }
            let a=(bytes[i+1] as char).to_digit(16).ok_or(400u16)?;
            let b=(bytes[i+2] as char).to_digit(16).ok_or(400u16)?;
            i+=2; ((a<<4)|b) as u8
        } else { bytes[i] };
        if b==0 || b==b'\\' { return Err(400); }
        result.push(b); i+=1;
    }
    let s=String::from_utf8(result).map_err(|_|400u16)?;
    if s.split('/').any(|c| c=="..") { return Err(403); }
    Ok(s)
}
enum ChunkState { Size, Data(usize), EndData, Trailers, Done }
struct Chunks { state:ChunkState, trailer_bytes:usize }
impl Chunks {
    fn new() -> Self { Self {state:ChunkState::Size,trailer_bytes:0} }
    fn consume(&mut self, input:&mut Vec<u8>, body:&mut Vec<u8>, limit:usize, header_limit:usize) -> Result<bool,u16> {
        loop {
            match self.state {
                ChunkState::Size | ChunkState::Trailers => {
                    let end=match input.windows(2).position(|p| p==b"\r\n") {
                        Some(n)=>n, None=> {
                            if input.len()>header_limit || input.iter().enumerate().any(|(i,b)| *b==0 || (*b==b'\n' && (i==0 || input[i-1]!=b'\r'))) {return Err(400)}
                            return Ok(false);
                        }
                    };
                    let line=&input[..end];
                    if matches!(self.state,ChunkState::Trailers) {
                        self.trailer_bytes=self.trailer_bytes.checked_add(end+2).ok_or(400u16)?;
                        if self.trailer_bytes>header_limit {return Err(400)}
                        if line.is_empty() { self.state=ChunkState::Done; }
                        else { let (k,_)=header_line(line)?; if k==b"content-length" || k==b"transfer-encoding" || k==b"host" {return Err(400)} }
                    } else {
                        if end>header_limit {return Err(400)}
                        let mut pieces=line.splitn(2,|b| *b==b';');
                        let digits=pieces.next().unwrap();
                        if digits.is_empty() || !digits.iter().all(|b| b.is_ascii_hexdigit()) {return Err(400)}
                        if let Some(ext)=pieces.next() {if ext.is_empty() || ext.iter().any(|b| *b<32 || *b==127) {return Err(400)}}
                        let n=digits.iter().try_fold(0usize,|n,b| n.checked_mul(16).and_then(|n| n.checked_add((*b as char).to_digit(16).unwrap() as usize))).ok_or(400u16)?;
                        if n>limit.saturating_sub(body.len()) {return Err(413)}
                        self.state=if n==0 {ChunkState::Trailers} else {ChunkState::Data(n)};
                    }
                    input.drain(..end+2);
                }
                ChunkState::Data(n) => {
                    let take=n.min(input.len());
                    body.extend_from_slice(&input[..take]); input.drain(..take);
                    if take<n {self.state=ChunkState::Data(n-take);return Ok(false)}
                    self.state=ChunkState::EndData;
                }
                ChunkState::EndData => {
                    if input.first().is_some_and(|b| *b!=b'\r') || input.get(1).is_some_and(|b| *b!=b'\n') {return Err(400)}
                    if input.len()<2 {return Ok(false)}
                    input.drain(..2); self.state=ChunkState::Size;
                }
                ChunkState::Done => return Ok(true),
            }
        }
    }
}
enum Framing { Length(usize), Chunked(Chunks) }
struct Request {
    method:String, path:String, raw_path:String, query:String, host:String, authority:String,
    headers:Headers, close:bool, framing:Framing, body:Vec<u8>, cfg:Arc<Config>,
}
impl Request {
    fn parse(raw:&[u8],cfg:Arc<Config>) -> Result<Self,u16> {
        let (line,headers)=parse_headers(raw)?;
        let p=line.split(|b| *b==b' ').collect::<Vec<_>>();
        if p.len()!=3 || !token(p[0]) || p[1].is_empty() || !matches!(p[2],b"HTTP/1.0"|b"HTTP/1.1") {return Err(400)}
        let method=String::from_utf8(p[0].to_vec()).map_err(|_|400u16)?;
        let target=std::str::from_utf8(p[1]).map_err(|_|400u16)?;
        if target.contains('#') {return Err(400)}
        let (raw_path,query)=match target.split_once('?') {Some((p,q))=>(p,format!("?{q}")),None=>(target,String::new())};
        let path=decode_path(raw_path)?;
        let hosts=vals(&headers,b"host").collect::<Vec<_>>();
        let (host,auth)=if hosts.is_empty() && p[2]==b"HTTP/1.0" {(cfg.host.clone(),cfg.host.clone())}
            else if hosts.len()==1 { authority(std::str::from_utf8(hosts[0]).map_err(|_|400u16)?).map_err(|_|400u16)? }
            else {return Err(400)};
        if host!=cfg.host && host!=cfg.other_host {return Err(400)}
        let cls=vals(&headers,b"content-length").collect::<Vec<_>>();
        let tes=vals(&headers,b"transfer-encoding").collect::<Vec<_>>();
        if cls.len()>1 || tes.len()>1 || (!cls.is_empty() && !tes.is_empty()) {return Err(400)}
        let proxy=path.starts_with(&cfg.proxy);
        let framing=if let Some(te)=tes.first() {
            if !proxy || !te.eq_ignore_ascii_case(b"chunked") {return Err(400)}
            Framing::Chunked(Chunks::new())
        } else {
            let n=match cls.first() {Some(s)=>decimal(s)?,None=>0};
            if !proxy && n!=0 {return Err(400)}
            if proxy && n>cfg.body_bytes {return Err(413)}
            Framing::Length(n)
        };
        let close=p[2]==b"HTTP/1.0" || tokens(&headers,b"connection").contains(b"close".as_slice());
        Ok(Self {method,path,raw_path:raw_path.into(),query,host,authority:auth,headers,close,framing,body:Vec::new(),cfg})
    }
    fn consume(&mut self,buf:&mut Vec<u8>) -> Result<bool,u16> {
        match &mut self.framing {
            Framing::Length(n)=> {let take=(*n-self.body.len()).min(buf.len()); self.body.extend_from_slice(&buf[..take]);buf.drain(..take);Ok(self.body.len()==*n)}
            Framing::Chunked(c)=>c.consume(buf,&mut self.body,self.cfg.body_bytes,self.cfg.header_bytes),
        }
    }
    fn head(&self)->bool {self.method=="HEAD"}
    fn cache_key(&self)->String {format!("http://{}{}{}",self.authority,self.raw_path,self.query)}
    fn encoding(&self)->Vec<u8> { vals(&self.headers,b"accept-encoding").enumerate().fold(Vec::new(),|mut v,(i,x)|{if i>0 {v.push(b',')}v.extend_from_slice(x);v}) }
}
struct Representation {file:File,size:u64,etag:String,mime:&'static str}
enum Body { None, Memory(Arc<Vec<u8>>), File(Arc<Representation>,i64,u64) }
struct Output {header:Vec<u8>,pos:usize,body:Body,body_pos:usize,close:bool,last:Instant,timeout:Duration}
fn reason(s:u16)->&'static str {match s {200=>"OK",206=>"Partial Content",301=>"Moved Permanently",302=>"Found",304=>"Not Modified",400=>"Bad Request",403=>"Forbidden",404=>"Not Found",405=>"Method Not Allowed",408=>"Request Timeout",413=>"Content Too Large",416=>"Range Not Satisfiable",429=>"Too Many Requests",431=>"Request Header Fields Too Large",502=>"Bad Gateway",504=>"Gateway Timeout",_=>"Response"}}
fn output(status:u16,headers:&Headers,len:u64,body:Body,close:bool,timeout:Duration)->Output {
    let mut h=format!("HTTP/1.1 {} {}\r\nContent-Length: {}\r\nConnection: {}\r\n",status,reason(status),len,if close {"close"} else {"keep-alive"}).into_bytes();
    for (k,v) in headers { h.extend_from_slice(k);h.extend_from_slice(b": ");h.extend_from_slice(v);h.extend_from_slice(b"\r\n"); }
    h.extend_from_slice(b"\r\n");
    Output {header:h,pos:0,body,body_pos:0,close,last:Instant::now(),timeout}
}
fn extra(k:&str,v:String)->(Vec<u8>,Vec<u8>) {(k.as_bytes().to_vec(),v.into_bytes())}
fn hop_headers(h:&Headers)->HashSet<Vec<u8>> {
    let mut hops=tokens(h,b"connection");
    for k in ["connection","keep-alive","proxy-connection","transfer-encoding","te","trailer","upgrade","proxy-authenticate","proxy-authorization"] {hops.insert(k.as_bytes().to_vec());}
    hops
}
fn connect_nonblocking(addr:SocketAddr)->io::Result<TcpStream> {
    let fd=unsafe {socket(if addr.is_ipv4(){2}else{10},1|NONBLOCK|CLOEXEC,0)};
    if fd<0 {return Err(io::Error::last_os_error())}
    let stream=unsafe {TcpStream::from_raw_fd(fd)};
    let r=match addr {
        SocketAddr::V4(a)=> {let s=Sock4 {family:2,port:a.port().to_be(),addr:a.ip().octets(),zero:[0;8]};unsafe {connect(fd,&s as *const _ as *const u8,16)}}
        SocketAddr::V6(a)=> {let s=Sock6 {family:10,port:a.port().to_be(),flow:a.flowinfo(),addr:a.ip().octets(),scope:a.scope_id()};unsafe {connect(fd,&s as *const _ as *const u8,28)}}
    };
    if r<0 && io::Error::last_os_error().raw_os_error()!=Some(115) {return Err(io::Error::last_os_error())}
    let _=stream.set_nodelay(true); Ok(stream)
}
struct UpHead {status:u16,headers:Headers,framing:Framing,length:usize,keep:bool}
struct Proxy {
    request:Request, index:usize, attempt:usize, socket:TcpStream,
    send:Vec<u8>,sent:usize,raw:Vec<u8>,head:Option<UpHead>,body:Vec<u8>,deadline:Instant,
}
impl Proxy {
    fn create(request:Request,index:usize,attempt:usize,socket:TcpStream)->Self {
        let target=if request.raw_path.starts_with(&request.cfg.proxy) {format!("/{}{}",&request.raw_path[request.cfg.proxy.len()..],request.query)}
            else {format!("/{}{}",&request.path[request.cfg.proxy.len()..],request.query)};
        let mut send=format!("{} {} HTTP/1.1\r\nHost: {}\r\nContent-Length: {}\r\nConnection: keep-alive\r\n",request.method,target,request.cfg.upstreams[index],request.body.len()).into_bytes();
        let hops=hop_headers(&request.headers);
        for (k,v) in &request.headers {if !hops.contains(k) && k!=b"host" && k!=b"content-length" {send.extend_from_slice(k);send.extend_from_slice(b": ");send.extend_from_slice(v);send.extend_from_slice(b"\r\n");}}
        // Keep upload bytes in Request instead of duplicating them in the header buffer.
        send.extend_from_slice(b"\r\n");
        let deadline=Instant::now()+request.cfg.upstream_timeout;
        Self {request,index,attempt,socket,send,sent:0,raw:Vec::new(),head:None,body:Vec::new(),deadline}
    }
    fn send_len(&self)->usize {self.send.len()+self.request.body.len()}
    fn parse_head(&self,raw:&[u8])->Result<UpHead,u16> {
        let (line,headers)=parse_headers(raw).map_err(|_|502u16)?;
        let p=line.splitn(3,|b| *b==b' ').collect::<Vec<_>>();
        if p.len()<2 || !matches!(p[0],b"HTTP/1.0"|b"HTTP/1.1") || p[1].len()!=3 {return Err(502)}
        let status=decimal(p[1]).map_err(|_|502u16)? as u16;
        if !(100..=599).contains(&status) || p.get(2).is_some_and(|p|p.iter().any(|b|*b<32||*b==127)) {return Err(502)}
        let cls=vals(&headers,b"content-length").collect::<Vec<_>>();let tes=vals(&headers,b"transfer-encoding").collect::<Vec<_>>();
        if cls.len()>1 || tes.len()>1 || (!cls.is_empty() && !tes.is_empty()) {return Err(502)}
        let length=match cls.first(){Some(v)=>decimal(v).map_err(|_|502u16)?,None=>0};
        let nobody=self.request.head() || status==204 || status==304 || status<200;
        if !nobody && length>self.request.cfg.body_bytes {return Err(502)}
        let framing=if let Some(t)=tes.first() {
            if !t.eq_ignore_ascii_case(b"chunked") {return Err(502)}
            if nobody {Framing::Length(0)} else {Framing::Chunked(Chunks::new())}
        } else if nobody {Framing::Length(0)} else if cls.len()==1 {Framing::Length(length)} else {return Err(502)};
        let keep=p[0]==b"HTTP/1.1" && !tokens(&headers,b"connection").contains(b"close".as_slice());
        Ok(UpHead {status,headers,framing,length,keep})
    }
    fn consume(&mut self)->Result<bool,u16> {
        if self.head.is_none() {
            loop {
                let end=match head_end(&self.raw,self.request.cfg.header_bytes).map_err(|_|502u16)? {Some(n)=>n,None=>return Ok(false)};
                let h=self.parse_head(&self.raw[..end])?;self.raw.drain(..end);
                if h.status<200 {if h.status==101{return Err(502)}continue}
                // A partial first body read must not trigger geometric growth to almost
                // twice a declared 64KiB body, especially across 4096 active clients.
                if let Framing::Length(n)=h.framing {self.body.reserve_exact(n);}
                self.head=Some(h); break;
            }
        }
        let h=self.head.as_mut().unwrap();
        let complete=match &mut h.framing {
            Framing::Length(n)=>{let take=(*n-self.body.len()).min(self.raw.len());self.body.extend_from_slice(&self.raw[..take]);self.raw.drain(..take);self.body.len()==*n}
            Framing::Chunked(c)=>c.consume(&mut self.raw,&mut self.body,self.request.cfg.body_bytes,self.request.cfg.header_bytes).map_err(|_|502u16)?,
        };
        if complete && !self.raw.is_empty() {return Err(502)}
        Ok(complete)
    }
}
struct Cached {status:u16,headers:Headers,body:Arc<Vec<u8>>,expires:Instant,vary:bool}
struct Cache {map:HashMap<Vec<u8>,Cached>,order:VecDeque<Vec<u8>>,bytes:usize}
impl Cache {
    fn new()->Self {Self {map:HashMap::new(),order:VecDeque::new(),bytes:0}}
    fn key(base:&str,ae:Option<&[u8]>)->Vec<u8> {let mut k=base.as_bytes().to_vec();k.push(0);if let Some(a)=ae {k.extend_from_slice(a)}k}
    fn get(&mut self,r:&Request)->Option<(u16,Headers,Arc<Vec<u8>>)> {
        if val(&r.headers,b"authorization").is_some() {return None}
        let base=r.cache_key();let ae=r.encoding();let plain=Self::key(&base,None);let variant=Self::key(&base,Some(&ae));
        for key in [&plain,&variant] {
            if let Some(c)=self.map.get(key) {
                if Instant::now()<c.expires && (!c.vary || *key==variant) {return Some((c.status,c.headers.clone(),c.body.clone()))}
            }
            if self.map.get(key).is_some_and(|c|Instant::now()>=c.expires) {self.remove(key);}
        }
        None
    }
    fn remove(&mut self,key:&[u8]) {if let Some(c)=self.map.remove(key) {self.bytes-=c.body.len();}self.order.retain(|k|k!=key);}
    fn insert(&mut self,r:&Request,status:u16,headers:&Headers,body:Arc<Vec<u8>>) {
        if r.method!="GET" || status!=200 || val(&r.headers,b"authorization").is_some() || val(headers,b"set-cookie").is_some() {return}
        let cc=tokens(headers,b"cache-control");
        if !cc.contains(b"public".as_slice()) || cc.iter().any(|v| v==b"private" || v.starts_with(b"private=") || v==b"no-store") {return}
        let ages=cc.iter().filter_map(|v| v.strip_prefix(b"max-age=")).collect::<Vec<_>>();
        if ages.len()!=1 {return}
        let age=match decimal(ages[0]) {Ok(n)=>n as u64,Err(_)=>return};
        let ttl=Duration::from_secs(age).min(r.cfg.cache_ttl);if ttl.is_zero() || body.len()>r.cfg.cache_bytes {return}
        let vary=tokens(headers,b"vary");
        if vary.iter().any(|v|v!=b"accept-encoding") {return}
        let varying=!vary.is_empty();let ae=r.encoding();let key=Self::key(&r.cache_key(),if varying {Some(&ae)}else{None});
        self.remove(&key);
        // The body-byte budget also needs a separate bound for empty entries and metadata.
        let entries=r.cfg.cache_bytes.clamp(1,1024);
        while self.bytes.saturating_add(body.len())>r.cfg.cache_bytes || self.map.len()>=entries {
            if let Some(k)=self.order.pop_front(){if let Some(c)=self.map.remove(&k){self.bytes-=c.body.len();}}else{break}
        }
        self.bytes+=body.len();self.order.push_back(key.clone());
        self.map.insert(key,Cached {status,headers:headers.clone(),body,expires:Instant::now()+ttl,vary:varying});
    }
}
struct Queued {request:Request,index:usize,attempt:usize}
enum State {Reading, Writing(Output), Queued(Queued), Proxy(Proxy), Dead}
struct Connection {socket:TcpStream,input:Vec<u8>,pending:Option<Request>,state:State,count:usize,last:Instant,first:Option<Instant>,read_timeout:Duration}
struct PoolSocket {socket:TcpStream,at:Instant}
struct Server {
    ep:RawFd,listener:Option<TcpListener>,cfg:Arc<Config>,path:String,
    connections:HashMap<RawFd,Connection>,up_owners:HashMap<RawFd,RawFd>,pools:Vec<Vec<PoolSocket>>,
    up_active:HashMap<SocketAddr,usize>,queued:HashMap<SocketAddr,VecDeque<RawFd>>,wake_needed:bool,
    cache:Cache,files:HashMap<String,Arc<Representation>>,rr:usize,tokens:f64,refill:Instant,drain:Option<Instant>,
}
impl Server {
    fn interest(&self,fd:RawFd,events:u32) {let mut e=Event {events:if events==0 {0}else{events|RDHUP},data:fd as u64};unsafe {if epoll_ctl(self.ep,3,fd,&mut e)<0 {epoll_ctl(self.ep,1,fd,&mut e);}}}
    fn unregister(&self,fd:RawFd) {unsafe {epoll_ctl(self.ep,2,fd,std::ptr::null_mut());}}
    fn rate_allow(&mut self)->bool {
        if self.cfg.rate==0.0{return true}
        let now=Instant::now();self.tokens=(self.tokens+now.duration_since(self.refill).as_secs_f64()*self.cfg.rate).min(self.cfg.burst);self.refill=now;
        if self.tokens>=1.0 {self.tokens-=1.0;true}else{false}
    }
    fn error(&self,c:&mut Connection,status:u16,close:bool,headers:Headers) {c.state=State::Writing(output(status,&headers,0,Body::None,close,self.cfg.write_timeout));c.pending=None;c.first=None;}
    fn open_rep(&mut self,root:&Arc<File>,root_name:&str,path:&str,index:&str)->Result<Result<Arc<Representation>,bool>,u16> {
        let key=format!("{root_name}\0{path}\0{index}");
        if let Some(r)=self.files.get(&key){return Ok(Ok(r.clone()))}
        let parts=path.split('/').filter(|p|!p.is_empty() && *p!=".").collect::<Vec<_>>();
        let mut current=root.try_clone().map_err(|_|403u16)?;
        for p in parts {
            let name=CString::new(p).map_err(|_|400u16)?;
            let fd=unsafe {openat(current.as_raw_fd(),name.as_ptr(),NOFOLLOW|NONBLOCK|CLOEXEC)};
            if fd<0 {return Err(match io::Error::last_os_error().raw_os_error(){Some(2|20)=>404,_=>403})}
            current=unsafe {File::from_raw_fd(fd)};
            let m=current.metadata().map_err(|_|403u16)?;
            if !m.is_file() && !m.is_dir(){return Err(403)}
        }
        let mut m=current.metadata().map_err(|_|403u16)?;
        if m.is_dir() {
            if !path.ends_with('/') {return Ok(Err(true))}
            let name=CString::new(index).map_err(|_|400u16)?;
            let fd=unsafe {openat(current.as_raw_fd(),name.as_ptr(),NOFOLLOW|NONBLOCK|CLOEXEC)};
            if fd<0 {return Err(403)}current=unsafe {File::from_raw_fd(fd)};m=current.metadata().map_err(|_|403u16)?;
        } else if path.ends_with('/') {return Err(403)}
        if !m.is_file(){return Err(403)}
        let name=if path.ends_with('/') {index} else {path};
        let mime=if name.ends_with(".html"){"text/html"}else if name.ends_with(".txt"){"text/plain"}else{"application/octet-stream"};
        let etag=format!("\"{:x}-{:x}-{:x}-{:x}-{:x}\"",m.dev(),m.ino(),m.len(),m.mtime(),m.mtime_nsec());
        let rep=Arc::new(Representation {file:current,size:m.len(),etag,mime});
        if self.files.len()>=256 {if let Some(k)=self.files.keys().next().cloned(){self.files.remove(&k);}}
        self.files.insert(key,rep.clone());Ok(Ok(rep))
    }
    fn local(&mut self,c:&mut Connection,r:Request) {
        let close=r.close || c.count+1>=r.cfg.max_requests || self.drain.is_some();
        let timeout=r.cfg.write_timeout;
        if r.path==r.cfg.redirect {c.state=State::Writing(output(302,&vec![extra("Location",r.cfg.location.clone())],0,Body::None,close,timeout));return}
        let (root,name,path)=if r.path.starts_with(&r.cfg.alias) {(r.cfg.alias_root.clone(),r.cfg.alias_name.clone(),format!("/{}",&r.path[r.cfg.alias.len()..]))}
            else if r.host==r.cfg.other_host {(r.cfg.other_root.clone(),r.cfg.other_name.clone(),r.path.clone())}
            else {(r.cfg.root.clone(),r.cfg.root_name.clone(),r.path.clone())};
        let rep=match self.open_rep(&root,&name,&path,&r.cfg.index) {
            Ok(Ok(rep))=>rep,
            Ok(Err(_))=>{c.state=State::Writing(output(301,&vec![extra("Location",format!("{}/{}",r.raw_path,r.query))],0,Body::None,close,timeout));return}
            Err(e)=>{self.error(c,e,close,Vec::new());return}
        };
        let mut headers=vec![extra("Content-Type",rep.mime.into()),extra("ETag",rep.etag.clone())];
        let matched=vals(&r.headers,b"if-none-match").any(|v|v.split(|b|*b==b',').any(|v| {let t=trim(v);t==b"*" || t==rep.etag.as_bytes() || t.strip_prefix(b"W/")==Some(rep.etag.as_bytes())}));
        if matched {c.state=State::Writing(output(304,&headers,0,Body::None,close,timeout));return}
        let ranges=vals(&r.headers,b"range").collect::<Vec<_>>();
        let (status,start,len)=if !ranges.is_empty() {
            if ranges.len()!=1 {self.error(c,400,true,Vec::new());return}
            let range=match range(ranges[0],rep.size){Ok(v)=>v,Err(e)=>{self.error(c,e,true,Vec::new());return}};
            match range {
                Some((a,b))=>{headers.push(extra("Content-Range",format!("bytes {a}-{b}/{}",rep.size)));(206,a,b-a+1)}
                None=>{headers.push(extra("Content-Range",format!("bytes */{}",rep.size)));c.state=State::Writing(output(416,&headers,0,Body::None,close,timeout));return}
            }
        } else {(200,0,rep.size)};
        let body=if r.head() || len==0 {Body::None}else{Body::File(rep,start as i64,len)};
        c.state=State::Writing(output(status,&headers,len,body,close,timeout));
    }
    fn take_up(&mut self,index:usize,cfg:&Config)->io::Result<TcpStream> {
        if cfg.upstreams==self.cfg.upstreams {
            while let Some(p)=self.pools[index].pop(){if p.at.elapsed()<cfg.idle_timeout{return Ok(p.socket)}}
        }
        connect_nonblocking(cfg.upstreams[index])
    }
    fn cached_response(&mut self,c:&mut Connection,r:&Request)->bool {
        if !Arc::ptr_eq(&r.cfg,&self.cfg) || !matches!(r.method.as_str(),"GET"|"HEAD") {return false}
        if let Some((status,headers,body))=self.cache.get(r) {
            let len=body.len() as u64;let b=if r.head(){Body::None}else{Body::Memory(body)};
            c.state=State::Writing(output(status,&headers,len,b,r.close||c.count+1>=r.cfg.max_requests||self.drain.is_some(),r.cfg.write_timeout));true
        }else{false}
    }
    fn start_proxy(&mut self,c:&mut Connection,r:Request,index:usize,attempt:usize) {
        let endpoint=r.cfg.upstreams[index];
        // All new requests and retries join the same FIFO. Only the dispatcher
        // may claim an exchange slot, including slots freed in this event batch.
        self.queued.entry(endpoint).or_default().push_back(c.socket.as_raw_fd());
        c.state=State::Queued(Queued {request:r,index,attempt});self.wake_needed=true;
    }
    fn begin_proxy(&mut self,c:&mut Connection,r:Request,index:usize,attempt:usize) {
        let endpoint=r.cfg.upstreams[index];
        match self.take_up(index,&r.cfg) {
            Ok(s)=>{let u=Proxy::create(r,index,attempt,s);let fd=u.socket.as_raw_fd();*self.up_active.entry(endpoint).or_default()+=1;self.up_owners.insert(fd,c.socket.as_raw_fd());self.interest(fd,OUT);c.state=State::Proxy(u);}
            Err(_)=>{if attempt==0 && r.method!="POST" {let next=(index+1)%r.cfg.upstreams.len();self.start_proxy(c,r,next,1)}else{let close=r.close||c.count+1>=r.cfg.max_requests;self.error(c,502,close,Vec::new())}}
        }
    }
    fn release_upstream(&mut self,u:&Proxy) {
        let fd=u.socket.as_raw_fd();self.unregister(fd);self.up_owners.remove(&fd);
        let endpoint=u.request.cfg.upstreams[u.index];
        if let Some(n)=self.up_active.get_mut(&endpoint) {*n=n.saturating_sub(1);if *n==0 {self.up_active.remove(&endpoint);}}
        self.wake_needed=true;
    }
    fn wake_queued(&mut self) {
        if !self.wake_needed {return}
        self.wake_needed=false;
        let endpoints=self.queued.keys().copied().collect::<Vec<_>>();
        for endpoint in endpoints {
            while self.up_active.get(&endpoint).copied().unwrap_or(0)<UPSTREAM_EXCHANGES {
                let fd=match self.queued.get_mut(&endpoint).and_then(VecDeque::pop_front){Some(fd)=>fd,None=>break};
                let mut c=match self.connections.remove(&fd){Some(c)=>c,None=>continue};
                let state=std::mem::replace(&mut c.state,State::Dead);
                match state {
                    State::Queued(q) if q.request.cfg.upstreams[q.index]==endpoint=>{
                        // Another exchange may have filled a cache entry while this one waited.
                        if !self.cached_response(&mut c,&q.request){self.begin_proxy(&mut c,q.request,q.index,q.attempt);}
                    }
                    other=>{c.state=other;}
                }
                if matches!(c.state,State::Writing(_)){self.write_client(&mut c)}
                if matches!(c.state,State::Dead){self.remove(c)}else{self.sync(&c);self.connections.insert(fd,c);}
            }
            if self.queued.get(&endpoint).is_some_and(VecDeque::is_empty){self.queued.remove(&endpoint);}
        }
    }
    fn dispatch(&mut self,c:&mut Connection,r:Request) {
        c.first=None;
        if !self.rate_allow(){self.error(c,429,true,vec![extra("Retry-After",((1.0/self.cfg.rate).ceil() as u64).max(1).to_string())]);return}
        let proxy=r.path.starts_with(&r.cfg.proxy);
        if !matches!(r.method.as_str(),"GET"|"HEAD") && !(proxy && r.method=="POST") {self.error(c,405,r.close || c.count+1>=r.cfg.max_requests,Vec::new());return}
        if proxy {
            if self.cached_response(c,&r){return}
            let index=self.rr%r.cfg.upstreams.len();self.rr=self.rr.wrapping_add(1);self.start_proxy(c,r,index,0);
        } else {self.local(c,r)}
    }
    fn input(&mut self,c:&mut Connection)->bool {
        if c.pending.is_none() {
            let end=match head_end(&c.input,self.cfg.header_bytes){Ok(Some(n))=>n,Ok(None)=>return false,Err(e)=>{self.error(c,e,true,Vec::new());return true}};
            let r=match Request::parse(&c.input[..end],self.cfg.clone()){Ok(r)=>r,Err(e)=>{self.error(c,e,true,Vec::new());return true}};
            c.input.drain(..end);c.pending=Some(r);
        }
        match c.pending.as_mut().unwrap().consume(&mut c.input) {
            Ok(false)=>false,
            Ok(true)=>{let r=c.pending.take().unwrap();self.dispatch(c,r);true}
            Err(e)=>{self.error(c,e,true,Vec::new());true}
        }
    }
    fn read_client(&mut self,c:&mut Connection) {
        let mut total=0;let mut buf=[0u8;16384];
        loop {
            if self.input(c) {return}
            let cap=if c.pending.is_none(){self.cfg.header_bytes.saturating_sub(c.input.len()).max(1).min(buf.len())}else{buf.len()};
            match c.socket.read(&mut buf[..cap]) {
                Ok(0)=>{c.state=State::Dead;return}
                Ok(n)=>{if c.first.is_none(){c.first=Some(Instant::now());c.read_timeout=self.cfg.header_timeout;}c.input.extend_from_slice(&buf[..n]);c.last=Instant::now();total+=n;}
                Err(e) if e.kind()==io::ErrorKind::WouldBlock=>return,
                Err(e) if e.kind()==io::ErrorKind::Interrupted=>continue,
                Err(_)=>{c.state=State::Dead;return}
            }
            if total>=262144 {self.input(c);return}
        }
    }
    fn write_client(&mut self,c:&mut Connection) {
        let mut done=false;let mut dead=false;
        if let State::Writing(o)=&mut c.state {
            let mut budget=262144usize;
            while budget>0 {
                let result=if o.pos<o.header.len() {c.socket.write(&o.header[o.pos..]).map(|n|{o.pos+=n;n})}
                    else {match &mut o.body {
                        Body::None=>{done=true;break}
                        Body::Memory(v)=>{if o.body_pos==v.len(){done=true;break}c.socket.write(&v[o.body_pos..(o.body_pos+budget).min(v.len())]).map(|n|{o.body_pos+=n;n})}
                        Body::File(rep,off,left)=>{
                            if *left==0{done=true;break}
                            let n=unsafe {sendfile(c.socket.as_raw_fd(),rep.file.as_raw_fd(),off,budget.min(*left as usize))};
                            if n<0 {Err(io::Error::last_os_error())}else{*left-=n as u64;Ok(n as usize)}
                        }
                    }};
                match result {Ok(0)=>{dead=true;break},Ok(n)=>{o.last=Instant::now();budget=budget.saturating_sub(n)},Err(e) if e.kind()==io::ErrorKind::WouldBlock=>break,Err(e) if e.kind()==io::ErrorKind::Interrupted=>continue,Err(_)=>{dead=true;break}}
            }
            if done && (o.close || self.drain.is_some()){dead=true}
        }
        if dead {
            if done {
                // Send FIN before discarding a pipeline after its final advertised response.
                // Drain bytes already queued by the peer so close does not replace FIN with RST.
                let _=c.socket.shutdown(Shutdown::Write);
                let mut discard=[0u8;16384];let mut left=1048576;
                while left>0 {match c.socket.read(&mut discard) {Ok(0)=>break,Ok(n)=>left-=n,Err(e) if e.kind()==io::ErrorKind::Interrupted=>continue,Err(_)=>break}}
            }
            c.state=State::Dead;return
        }
        if done {c.count+=1;c.state=State::Reading;c.last=Instant::now();c.first=if c.input.is_empty(){None}else{Some(Instant::now())};c.read_timeout=self.cfg.header_timeout;self.read_client(c);}
    }
    fn proxy_failure(&mut self,c:&mut Connection,status:u16) {
        let old=std::mem::replace(&mut c.state,State::Dead);
        if let State::Proxy(u)=old {
            self.release_upstream(&u);
            if u.attempt==0 && u.request.method!="POST" {let next=(u.index+1)%u.request.cfg.upstreams.len();drop(u.socket);self.start_proxy(c,u.request,next,1)}
            else {let close=u.request.close||c.count+1>=u.request.cfg.max_requests;self.error(c,status,close,Vec::new());}
        }
    }
    fn proxy_ready(&mut self,c:&mut Connection) {
        let old=std::mem::replace(&mut c.state,State::Dead);
        if let State::Proxy(mut u)=old {
            self.release_upstream(&u);
            let h=u.head.take().unwrap();let hops=hop_headers(&h.headers);
            let headers=h.headers.into_iter().filter(|(k,_)|!hops.contains(k) && k!=b"content-length").collect::<Headers>();
            let body=Arc::new(u.body);let len=if u.request.head(){h.length as u64}else{body.len() as u64};
            if Arc::ptr_eq(&u.request.cfg,&self.cfg){self.cache.insert(&u.request,h.status,&headers,body.clone());}
            let close=u.request.close||c.count+1>=u.request.cfg.max_requests||self.drain.is_some();
            let outbody=if u.request.head(){Body::None}else{Body::Memory(body)};
            c.state=State::Writing(output(h.status,&headers,len,outbody,close,u.request.cfg.write_timeout));
            if h.keep && self.pools.get(u.index).is_some() && u.request.cfg.upstreams==self.cfg.upstreams && self.pools.iter().map(Vec::len).sum::<usize>()<self.cfg.max_connections.min(256) {
                self.pools[u.index].push(PoolSocket {socket:u.socket,at:Instant::now()});
            }
        }
    }
    fn upstream_io(&mut self,c:&mut Connection,events:u32) {
        let mut failed=None;let mut complete=false;
        if let State::Proxy(u)=&mut c.state {
            if events&OUT!=0 && u.sent<u.send_len() {
                if u.socket.take_error().ok().flatten().is_some(){failed=Some(502)}
                let mut budget=262144usize;
                while failed.is_none() && u.sent<u.send_len() && budget>0 {
                    let data=if u.sent<u.send.len(){&u.send[u.sent..]}else{&u.request.body[u.sent-u.send.len()..]};
                    match u.socket.write(data) {Ok(0)=>{failed=Some(502);break},Ok(n)=>{u.sent+=n;budget=budget.saturating_sub(n)},Err(e) if e.kind()==io::ErrorKind::WouldBlock=>break,Err(e) if e.kind()==io::ErrorKind::Interrupted=>continue,Err(_)=>{failed=Some(502);break}}
                }
            }
            if failed.is_none() && u.sent==u.send_len() {
                let mut buf=[0u8;16384];let mut budget=262144usize;
                loop {
                    match u.consume() {Ok(true)=>{complete=true;break},Ok(false)=>{},Err(e)=>{failed=Some(e);break}}
                    if budget==0{break}
                    match u.socket.read(&mut buf) {Ok(0)=>{failed=Some(502);break},Ok(n)=>{u.raw.extend_from_slice(&buf[..n]);budget=budget.saturating_sub(n)},Err(e) if e.kind()==io::ErrorKind::WouldBlock=>break,Err(e) if e.kind()==io::ErrorKind::Interrupted=>continue,Err(_)=>{failed=Some(502);break}}
                }
            }
        }
        if complete {self.proxy_ready(c)}else if let Some(status)=failed {self.proxy_failure(c,status)}
    }
    fn sync(&mut self,c:&Connection) {
        let fd=c.socket.as_raw_fd();
        match &c.state {
            State::Reading=>self.interest(fd,IN),
            State::Writing(_)=>self.interest(fd,OUT),
            State::Queued(_)=>self.interest(fd,0),
            State::Proxy(u)=>{self.interest(fd,0);self.interest(u.socket.as_raw_fd(),if u.sent<u.send_len(){OUT}else{IN});}
            State::Dead=>{},
        }
    }
    fn remove(&mut self,c:Connection) {
        self.unregister(c.socket.as_raw_fd());
        if let State::Proxy(u)=c.state {self.release_upstream(&u);}
    }
    fn abandon(&mut self,c:&mut Connection) {
        if let State::Proxy(u)=&c.state {self.release_upstream(u);}
        if let State::Queued(q)=&c.state {
            let endpoint=q.request.cfg.upstreams[q.index];let fd=c.socket.as_raw_fd();
            if let Some(queue)=self.queued.get_mut(&endpoint){queue.retain(|queued|*queued!=fd);}
            if self.queued.get(&endpoint).is_some_and(VecDeque::is_empty){self.queued.remove(&endpoint);}
        }
        c.state=State::Dead;
    }
    fn accept(&mut self) {
        loop {
            let r=match self.listener.as_ref(){Some(l)=>l.accept(),None=>return};
            match r {
                Ok((socket,_))=>{
                    if self.connections.len()>=self.cfg.max_connections {drop(socket);continue}
                    if socket.set_nonblocking(true).is_err(){continue}let _=socket.set_nodelay(true);
                    let fd=socket.as_raw_fd();let now=Instant::now();
                    self.connections.insert(fd,Connection {socket,input:Vec::new(),pending:None,state:State::Reading,count:0,last:now,first:None,read_timeout:self.cfg.header_timeout});self.interest(fd,IN);
                }
                Err(e) if e.kind()==io::ErrorKind::WouldBlock=>return,
                Err(e) if e.kind()==io::ErrorKind::Interrupted=>continue,
                Err(_)=>return,
            }
        }
    }
    fn maintenance(&mut self) {
        if RELOAD.swap(false,Ordering::Relaxed) && self.drain.is_none() {
            if let Ok(cfg)=Config::load(&self.path) {if cfg.listen==self.cfg.listen && self.listener.as_ref().is_none_or(|l|set_backlog(l,cfg.max_connections).is_ok()) {
                self.tokens=cfg.burst;self.refill=Instant::now();self.cache=Cache::new();self.files.clear();self.pools=(0..cfg.upstreams.len()).map(|_|Vec::new()).collect();self.rr=0;self.cfg=Arc::new(cfg);
            }}
        }
        if STOP.load(Ordering::Relaxed) && self.drain.is_none() {
            if let Some(l)=self.listener.take(){self.unregister(l.as_raw_fd());drop(l);}
            self.drain=Some(Instant::now()+self.cfg.drain);
        }
        let now=Instant::now();let fds=self.connections.iter().filter_map(|(fd,c)| {
            let due=match &c.state {
                State::Reading=>self.drain.is_some() || if c.pending.is_some(){now.duration_since(c.last)>=self.cfg.idle_timeout}else{c.first.map_or_else(||now.duration_since(c.last)>=self.cfg.idle_timeout,|t|now.duration_since(t)>=c.read_timeout)},
                State::Writing(o)=>now.duration_since(o.last)>=o.timeout,
                State::Queued(_)=>false,
                State::Proxy(u)=>now>=u.deadline,
                State::Dead=>true,
            };if due {Some(*fd)}else{None}
        }).collect::<Vec<_>>();
        for fd in fds {
            let mut c=match self.connections.remove(&fd){Some(c)=>c,None=>continue};
            match &c.state {
                State::Reading=>{
                    if self.drain.is_some(){c.state=State::Dead}
                    else if c.pending.is_some() {if now.duration_since(c.last)>=self.cfg.idle_timeout {self.error(&mut c,408,true,Vec::new())}}
                    else if c.first.is_some_and(|t|now.duration_since(t)>=c.read_timeout){self.error(&mut c,408,true,Vec::new())}
                    else if c.first.is_none() && now.duration_since(c.last)>=self.cfg.idle_timeout {c.state=State::Dead}
                }
                State::Writing(o)=>{if now.duration_since(o.last)>=o.timeout{c.state=State::Dead}}
                State::Proxy(u)=>{if now>=u.deadline{self.proxy_failure(&mut c,504)}}
                State::Queued(_)=>{},
                State::Dead=>{},
            }
            if matches!(c.state,State::Dead){self.remove(c)}else{self.sync(&c);self.connections.insert(fd,c);}
        }
        for pool in &mut self.pools {pool.retain(|p|now.duration_since(p.at)<self.cfg.idle_timeout);}
        self.wake_queued();
    }
    fn run(&mut self) {
        let mut events=[Event {events:0,data:0};1024];let mut last=Instant::now();
        loop {
            if last.elapsed()>=ms(10) || RELOAD.load(Ordering::Relaxed) || STOP.load(Ordering::Relaxed) {self.maintenance();last=Instant::now();}
            if self.drain.is_some_and(|d|Instant::now()>=d) || (self.drain.is_some() && self.connections.is_empty()){break}
            let n=unsafe {epoll_wait(self.ep,events.as_mut_ptr(),events.len() as i32,10)};
            if n<0 {continue}
            for event in &events[..n as usize] {
                let fd=event.data as i32;let flags=event.events;
                if self.listener.as_ref().is_some_and(|l|l.as_raw_fd()==fd){self.accept();continue}
                let owner=self.up_owners.get(&fd).copied();let key=owner.unwrap_or(fd);
                let mut c=match self.connections.remove(&key){Some(c)=>c,None=>continue};
                if owner.is_some(){self.upstream_io(&mut c,flags)}else {
                    match c.state {
                        State::Reading=>self.read_client(&mut c),
                        State::Writing(_)=>self.write_client(&mut c),
                        State::Proxy(_)|State::Queued(_)=>{if flags&(ERR|HUP)!=0{self.abandon(&mut c)}},
                        State::Dead=>{},
                    }
                }
                // Attempt new output immediately; readiness notification handles partial writes.
                if matches!(c.state,State::Writing(_)){self.write_client(&mut c)}
                if matches!(c.state,State::Dead){self.remove(c)}else{self.sync(&c);self.connections.insert(key,c);}
                self.wake_queued();
            }
        }
    }
}
fn range(raw:&[u8],size:u64)->Result<Option<(u64,u64)>,u16> {
    let s=raw.strip_prefix(b"bytes=").ok_or(400u16)?;
    if s.contains(&b','){return Err(400)}
    let dash=s.iter().position(|b|*b==b'-').ok_or(400u16)?;
    let (a,b)=(&s[..dash],&s[dash+1..]);
    if a.is_empty() {let n=decimal(b)? as u64;if n==0||size==0{return Ok(None)}Ok(Some((size.saturating_sub(n),size-1)))}
    else {let start=decimal(a)? as u64;let end=if b.is_empty(){size.saturating_sub(1)}else{decimal(b)? as u64};if start>=size||start>end{return Ok(None)}Ok(Some((start,end.min(size-1))))}
}
fn main() {
    let args=std::env::args().collect::<Vec<_>>();
    if args.len()!=3 || args[1]!="--config" {std::process::exit(1)}
    let cfg=match Config::load(&args[2]){Ok(c)=>Arc::new(c),Err(e)=>{eprintln!("configuration: {e}");std::process::exit(1)}};
    let listener=match TcpListener::bind(cfg.listen){Ok(l)=>l,Err(e)=>{eprintln!("listen: {e}");std::process::exit(1)}};
    if let Err(e)=set_backlog(&listener,cfg.max_connections){eprintln!("listen backlog: {e}");std::process::exit(1)}
    if listener.set_nonblocking(true).is_err(){std::process::exit(1)}
    unsafe {signal(13,1);signal(1,on_signal as *const () as usize);signal(15,on_signal as *const () as usize);}
    let ep=unsafe {epoll_create1(CLOEXEC)};if ep<0{std::process::exit(1)}
    let mut server=Server {ep,listener:Some(listener),cfg:cfg.clone(),path:args[2].clone(),connections:HashMap::new(),up_owners:HashMap::new(),pools:(0..cfg.upstreams.len()).map(|_|Vec::new()).collect(),up_active:HashMap::new(),queued:HashMap::new(),wake_needed:false,cache:Cache::new(),files:HashMap::new(),rr:0,tokens:cfg.burst,refill:Instant::now(),drain:None};
    server.interest(server.listener.as_ref().unwrap().as_raw_fd(),IN);server.run();
    unsafe {close(ep);}
}
