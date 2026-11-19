use std::collections::HashMap;
use std::env;
use std::fs::{self, File};
use std::io::{self, Read, Write};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::os::fd::{AsRawFd, FromRawFd, RawFd};
use std::path::Path;
use std::time::{Duration, Instant};
use std::ffi::CString;

#[repr(C, packed)]
#[derive(Copy, Clone)]
struct EpollEvent { events: u32, data: u64 }
unsafe extern "C" {
    fn epoll_create1(flags: i32) -> i32;
    fn epoll_ctl(epfd: i32, op: i32, fd: i32, event: *mut EpollEvent) -> i32;
    fn epoll_wait(epfd: i32, events: *mut EpollEvent, maxevents: i32, timeout: i32) -> i32;
    fn openat(dirfd: i32, path: *const i8, flags: i32, ...) -> i32;
    fn sendfile(out_fd: i32, in_fd: i32, offset: *mut i64, count: usize) -> isize;
    fn close(fd: i32) -> i32;
}
const IN: u32 = 1; const OUT: u32 = 4; const ERR: u32 = 8; const HUP: u32 = 16;
const ADD: i32 = 1; const MOD: i32 = 3;
const O_CLOEXEC: i32 = 0o2000000; const O_NOFOLLOW: i32 = 0o400000; const O_NONBLOCK: i32 = 0o4000;

struct Config { listen: SocketAddr, root: File, max_conn: usize, header: usize, header_ms: u64, idle_ms: u64, write_ms: u64, max_req: usize, pipeline: usize }
fn number(s: &str) -> Result<usize, String> {
    if s.is_empty() || !s.bytes().all(|c| c.is_ascii_digit()) { return Err("invalid integer".into()); }
    let n = s.parse::<usize>().map_err(|_| "invalid integer")?;
    if n == 0 { return Err("zero limit".into()); } Ok(n)
}
fn config() -> Result<Config, String> {
    let args: Vec<String> = env::args().collect();
    if args.len() != 3 || args[1] != "--config" { return Err("expected --config path".into()); }
    let text = fs::read_to_string(&args[2]).map_err(|e| e.to_string())?;
    let mut m = HashMap::new();
    let allowed = ["listen", "root", "max_connections", "header_bytes", "header_timeout_ms", "idle_timeout_ms", "write_timeout_ms", "max_requests", "pipeline_depth"];
    for line in text.lines() {
        let line = line.trim(); if line.is_empty() || line.starts_with('#') { continue; }
        let (k,v) = line.split_once('=').ok_or("invalid config line")?;
        let k=k.trim(); let v=v.trim();
        if !allowed.contains(&k) || m.insert(k, v).is_some() { return Err("unknown or duplicate key".into()); }
    }
    let get = |k: &str| m.get(k).copied().ok_or_else(|| format!("missing {k}"));
    let listen: SocketAddr = get("listen")?.parse().map_err(|_| "invalid listen")?;
    let root_path = Path::new(get("root")?);
    if !root_path.is_absolute() || !fs::metadata(root_path).map_err(|e|e.to_string())?.is_dir() { return Err("invalid root".into()); }
    let root = File::open(root_path).map_err(|e|e.to_string())?;
    let max_conn=number(get("max_connections")?)?;
    let header=number(get("header_bytes")?)?;
    let header_ms=number(get("header_timeout_ms")?)? as u64;
    let idle_ms=number(get("idle_timeout_ms")?)? as u64;
    let write_ms=number(get("write_timeout_ms")?)? as u64;
    let max_req=number(get("max_requests")?)?;
    let pipeline=number(get("pipeline_depth")?)?;
    Ok(Config {listen,root,max_conn,header,header_ms,idle_ms,write_ms,max_req,pipeline})
}
fn token(b:u8)->bool { b.is_ascii_alphanumeric() || matches!(b,b'!'|b'#'|b'$'|b'%'|b'&'|b'\''|b'*'|b'+'|b'-'|b'.'|b'^'|b'_'|b'`'|b'|'|b'~') }
fn trim(mut x:&[u8])->&[u8] { while x.first().is_some_and(|b| *b==b' '||*b==b'\t') {x=&x[1..];} while x.last().is_some_and(|b| *b==b' '||*b==b'\t') {x=&x[..x.len()-1];} x }
fn eq(x:&[u8], y:&[u8])->bool { x.eq_ignore_ascii_case(y) }
fn hex(b:u8)->Option<u8> { match b { b'0'..=b'9'=>Some(b-b'0'),b'a'..=b'f'=>Some(b-b'a'+10),b'A'..=b'F'=>Some(b-b'A'+10),_=>None } }
struct Request { head: bool, method_ok: bool, close: bool, v11: bool, path: String }
fn parse(data:&[u8])->Result<Request,u16> {
    let mut lines = data[..data.len()-2].split(|&b| b==b'\n');
    let line=lines.next().ok_or(400u16)?;
    if !line.ends_with(b"\r") { return Err(400); }
    let line=&line[..line.len()-1];
    let mut parts=line.split(|&b|b==b' ');
    let method=parts.next().ok_or(400u16)?; let target=parts.next().ok_or(400u16)?; let version=parts.next().ok_or(400u16)?;
    if parts.next().is_some() || method.is_empty() || !method.iter().copied().all(token) || target.is_empty() || target.iter().any(|&b|b<=32||b==127) {return Err(400);}
    let v11=match version { b"HTTP/1.1"=>true,b"HTTP/1.0"=>false,_=>return Err(400) };
    let mut close=!v11; let mut length_seen=false;
    for line in lines {
        if line.is_empty() { continue; }
        if !line.ends_with(b"\r") {return Err(400);}
        let line=&line[..line.len()-1];
        if line.is_empty() {continue;}
        let p=line.iter().position(|&b|b==b':').ok_or(400u16)?;
        let name=&line[..p]; let value=&line[p+1..];
        if name.is_empty() || !name.iter().copied().all(token) || value.iter().any(|&b| b==0 || b==b'\r' || b==b'\n' || (b<32 && b!=b'\t') || b==127) {return Err(400);}
        if eq(name,b"transfer-encoding") {return Err(400);}
        if eq(name,b"content-length") {
            if length_seen {return Err(400);} length_seen=true;
            let val=trim(value); if val.is_empty() || !val.iter().all(|&b|b==b'0') {return Err(400);}
        }
        if eq(name,b"connection") {
            for t in value.split(|&b|b==b',') { if eq(trim(t),b"close") {close=true;} }
        }
    }
    if target[0]!=b'/' || target.contains(&b'#') {return Err(400);}
    let path=target.split(|&b|b==b'?').next().unwrap();
    let mut decoded=Vec::with_capacity(path.len()); let mut i=0;
    while i<path.len() {
        let b=if path[i]==b'%' {if i+2>=path.len(){return Err(400);} let h=hex(path[i+1]).ok_or(400u16)?; let l=hex(path[i+2]).ok_or(400u16)?; i+=3; h*16+l} else {let b=path[i]; i+=1; b};
        if b==0 || b==b'\\' || b<32 || b==127 {return Err(400);} decoded.push(b);
    }
    let path=String::from_utf8(decoded).map_err(|_|400u16)?;
    Ok(Request {head:method==b"HEAD",method_ok:method==b"GET"||method==b"HEAD",close,v11,path})
}
fn file_for(root:RawFd,path:&str)->Result<File,u16> {
    let pieces: Vec<&str> = path.split('/').filter(|s|!s.is_empty() && *s!=".").collect();
    if path.split('/').any(|s|s=="..") {return Err(403);}
    if pieces.is_empty() {return Err(403);}
    let trailing=path.ends_with('/') || path.split('/').last()==Some(".");
    let mut parent: Option<File>=None;
    for (i,part) in pieces.iter().enumerate() {
        let name=CString::new(*part).map_err(|_|400u16)?;
        let base=parent.as_ref().map_or(root,|f|f.as_raw_fd());
        let fd=unsafe{openat(base,name.as_ptr(),O_CLOEXEC|O_NOFOLLOW|O_NONBLOCK)};
        if fd<0 {
            let code=io::Error::last_os_error().raw_os_error().unwrap_or(0);
            return Err(match code {2=>404,40=>403,20=>403,13=>403,_=>403});
        }
        let f=unsafe{File::from_raw_fd(fd)};
        let md=f.metadata().map_err(|_|403u16)?;
        if i+1==pieces.len() {
            if trailing || !md.is_file() {return Err(403);} return Ok(f);
        }
        if !md.is_dir(){return Err(403);} parent=Some(f);
    }
    Err(404)
}
struct Response { header: Vec<u8>, hpos: usize, file: Option<File>, remain: u64, close: bool }
struct Conn { stream:TcpStream, buf:Vec<u8>, started:Option<Instant>, last_read:Instant, idle:Instant, progress:Instant, response:Option<Response>, count:usize }
fn response(status:u16, size:u64, file:Option<File>, head:bool, close:bool, v11:bool)->Response {
    let reason=match status {200=>"OK",400=>"Bad Request",403=>"Forbidden",404=>"Not Found",405=>"Method Not Allowed",431=>"Request Header Fields Too Large",_=>"Internal Server Error"};
    let version=if v11 {"HTTP/1.1"}else{"HTTP/1.0"};
    let mut h=format!("{version} {status} {reason}\r\nContent-Length: {size}\r\nConnection: {}\r\n",if close {"close"} else {"keep-alive"});
    if status==200 {h.push_str("Content-Type: application/octet-stream\r\n");}
    if status==405 {h.push_str("Allow: GET, HEAD\r\n");}
    h.push_str("\r\n");
    Response{header:h.into_bytes(),hpos:0,file:if head {None}else{file},remain:if head {0}else{size},close}
}
fn error(c:&mut Conn,status:u16) { c.count+=1; c.response=Some(response(status,0,None,false,true,true)); c.progress=Instant::now(); c.started=None; c.buf.clear(); }
fn prepare(c:&mut Conn,cfg:&Config) {
    if c.response.is_some() {return;}
    let mut end=None;
    for i in 0..c.buf.len() {
        let b=c.buf[i];
        if b==0 || (b==b'\n' && (i==0 || c.buf[i-1]!=b'\r')) || (i>0 && c.buf[i-1]==b'\r' && b!=b'\n') {error(c,400); return;}
        if i>=3 && &c.buf[i-3..=i]==b"\r\n\r\n" {end=Some(i+1); break;}
    }
    let n=match end {Some(n)=>n,None=>{if c.buf.len()>=cfg.header {error(c,431);} return;}};
    if n>cfg.header {error(c,431);return;}
    let parsed=parse(&c.buf[..n]);
    c.buf.drain(..n);
    c.started=if c.buf.is_empty(){None}else{Some(c.last_read)};
    match parsed {
        Err(s)=>error(c,s),
        Ok(req)=>{
            c.count+=1;
            let close=req.close || c.count>=cfg.max_req;
            let (status,size,file)=if !req.method_ok {(405,0,None)} else {match file_for(cfg.root.as_raw_fd(),&req.path) {Ok(f)=>match f.metadata(){Ok(m)=>(200,m.len(),Some(f)),Err(_)=>(403,0,None)},Err(e)=>(e,0,None)}};
            c.response=Some(response(status,size,file,req.head,close,req.v11)); c.progress=Instant::now();
        }
    }
}
fn receive(c:&mut Conn,cfg:&Config)->bool {
    let mut tmp=[0u8;8192];
    loop {
        let room=cfg.header.saturating_add(1).saturating_sub(c.buf.len()).min(tmp.len());
        if room==0 {error(c,431);return true;}
        match c.stream.read(&mut tmp[..room]) {
            Ok(0)=>return false,
            Ok(n)=>{c.last_read=Instant::now();if c.started.is_none(){c.started=Some(c.last_read);} c.buf.extend_from_slice(&tmp[..n]); prepare(c,cfg); if c.response.is_some(){return true;}}
            Err(e) if e.kind()==io::ErrorKind::Interrupted=>continue,
            Err(e) if e.kind()==io::ErrorKind::WouldBlock=>return true,
            Err(_)=>return false,
        }
    }
}
fn flush(c:&mut Conn,cfg:&Config)->bool {
    let mut quota=256*1024usize;
    loop {
        if c.response.is_none() { prepare(c,cfg); if c.response.is_none(){return true;} }
        let r=c.response.as_mut().unwrap();
        while r.hpos<r.header.len() {
            match c.stream.write(&r.header[r.hpos..]) {
                Ok(0)=>return false,
                Ok(n)=>{r.hpos+=n;c.progress=Instant::now();},
                Err(e) if e.kind()==io::ErrorKind::Interrupted=>continue,
                Err(e) if e.kind()==io::ErrorKind::WouldBlock=>return true,
                Err(_)=>return false,
            }
        }
        while r.remain>0 {
            if quota==0{return true;}
            let count=(r.remain.min(quota as u64)) as usize;
            let n=unsafe{sendfile(c.stream.as_raw_fd(),r.file.as_ref().unwrap().as_raw_fd(),std::ptr::null_mut(),count)};
            if n>0 {r.remain-=n as u64;quota-=n as usize;c.progress=Instant::now();}
            else if n==0 {return false;}
            else {let e=io::Error::last_os_error();if e.kind()==io::ErrorKind::Interrupted{continue;} if e.kind()==io::ErrorKind::WouldBlock{return true;} return false;}
        }
        let close=r.close; c.response=None; c.idle=Instant::now();
        if close {return false;}
        if c.buf.is_empty(){c.started=None;return true;}
        if quota==0 {prepare(c,cfg);return true;}
    }
}
fn ctl(ep:RawFd,op:i32,fd:RawFd,events:u32,id:u64)->bool {let mut ev=EpollEvent{events,data:id}; unsafe{epoll_ctl(ep,op,fd,&mut ev)==0}}
fn run(cfg:Config)->io::Result<()> {
    let listener=TcpListener::bind(cfg.listen)?; listener.set_nonblocking(true)?;
    let ep=unsafe{epoll_create1(O_CLOEXEC)}; if ep<0{return Err(io::Error::last_os_error());}
    if !ctl(ep,ADD,listener.as_raw_fd(),IN,0){return Err(io::Error::last_os_error());}
    let mut clients:HashMap<u64,Conn>=HashMap::new(); let mut serial=0u64;
    let mut events=[EpollEvent{events:0,data:0};1024];
    let interval=cfg.header_ms.min(cfg.idle_ms).min(cfg.write_ms).min(25).max(1);
    let mut last_sweep=Instant::now(); let _pipeline=cfg.pipeline;
    loop {
        let timeout=if clients.is_empty(){1000}else{interval as i32};
        let n=unsafe{epoll_wait(ep,events.as_mut_ptr(),events.len() as i32,timeout)};
        if n<0 {if io::Error::last_os_error().kind()==io::ErrorKind::Interrupted {continue;} break;}
        for event in &events[..n as usize] {
            let id=event.data; let flags=event.events;
            if id==0 {
                loop {match listener.accept() {
                    Ok((s,_))=>{
                        if clients.len()>=cfg.max_conn {drop(s);continue;}
                        if s.set_nonblocking(true).is_err(){continue;}
                        let _=s.set_nodelay(true);
                        serial=serial.wrapping_add(1); if serial==0{serial=1;}
                        if !ctl(ep,ADD,s.as_raw_fd(),IN,serial){continue;}
                        let now=Instant::now();
                        clients.insert(serial,Conn{stream:s,buf:Vec::new(),started:None,last_read:now,idle:now,progress:now,response:None,count:0});
                    },
                    Err(e) if e.kind()==io::ErrorKind::Interrupted=>continue,
                    Err(e) if e.kind()==io::ErrorKind::WouldBlock=>break,
                    Err(_)=>break,
                }}
            } else if let Some(mut c)=clients.remove(&id) {
                let mut alive=true;
                if c.response.is_none() && flags & (IN|HUP|ERR)!=0 {alive=receive(&mut c,&cfg);}
                if alive && c.response.is_some() {alive=flush(&mut c,&cfg);}
                if alive {
                    let interest=if c.response.is_some(){OUT}else{IN};
                    if ctl(ep,MOD,c.stream.as_raw_fd(),interest,id){clients.insert(id,c);}
                }
            }
        }
        let now=Instant::now();
        if now.duration_since(last_sweep)>=Duration::from_millis(interval) {
            clients.retain(|_,c| {
                if c.response.is_some() {now.duration_since(c.progress)<Duration::from_millis(cfg.write_ms)}
                else if let Some(t)=c.started {now.duration_since(t)<Duration::from_millis(cfg.header_ms)}
                else {now.duration_since(c.idle)<Duration::from_millis(cfg.idle_ms)}
            });
            last_sweep=now;
        }
    }
    unsafe{close(ep)}; Ok(())
}
fn main(){match config().and_then(|c|run(c).map_err(|e|e.to_string())) {Ok(())=>{},Err(e)=>{eprintln!("{e}");std::process::exit(1);}}}

#[cfg(test)]
mod tests {
    use super::*; use std::{os::unix::fs::symlink,thread};
    fn conn(port:u16)->TcpStream {let s=TcpStream::connect(("127.0.0.1",port)).unwrap();s.set_read_timeout(Some(Duration::from_secs(2))).unwrap();s.set_write_timeout(Some(Duration::from_secs(2))).unwrap();s}
    fn read_resp(s:&mut TcpStream,head:bool)->(u16,usize,Vec<u8>,String) {let mut h=Vec::new();loop {let mut b=[0];s.read_exact(&mut b).unwrap();h.push(b[0]);assert!(h.len()<2000);if h.ends_with(b"\r\n\r\n"){break;}}let h=String::from_utf8(h).unwrap();let status=h.split_whitespace().nth(1).unwrap().parse().unwrap();let len=h.lines().find_map(|l|l.strip_prefix("Content-Length: ")).unwrap().parse().unwrap();let mut body=vec![0;if head {0}else{len}];s.read_exact(&mut body).unwrap();(status,len,body,h)}
    fn one(port:u16,req:&[u8],st:u16) {let mut s=conn(port);s.write_all(req).unwrap();let r=read_resp(&mut s,false);assert_eq!(r.0,st,"{:?}: {}",req,r.3);}
    #[test] fn contract() {
        let dir=format!("/tmp/server-tests-{}",std::process::id()); fs::create_dir_all(format!("{dir}/sub")).unwrap();fs::write(format!("{dir}/file"),b"hello\0world\xff").unwrap();fs::write(format!("{dir}/empty"),b"").unwrap();fs::write(format!("{dir}/big"),vec![17u8;8*1024*1024]).unwrap();fs::write(format!("{dir}/chunk"),vec![7u8;65536]).unwrap();symlink("/etc/passwd",format!("{dir}/link")).unwrap();symlink("sub",format!("{dir}/sub-link")).unwrap();
        let port=TcpListener::bind("127.0.0.1:0").unwrap().local_addr().unwrap().port();
        let cfg=Config{listen:format!("127.0.0.1:{port}").parse().unwrap(),root:File::open(&dir).unwrap(),max_conn:32,header:256,header_ms:250,idle_ms:400,write_ms:250,max_req:50,pipeline:1};
        thread::spawn(move||{run(cfg).unwrap();}); let until=Instant::now()+Duration::from_secs(2);loop{if TcpStream::connect(("127.0.0.1",port)).is_ok(){break;}assert!(Instant::now()<until);thread::sleep(Duration::from_millis(5));}
        let mut c=conn(port);c.write_all(b"GET /file?q=1 HTTP/1.1\r\nX-raw: \xff\r\n\r\n").unwrap();let r=read_resp(&mut c,false);assert_eq!((r.0,r.1,r.2),(200,12,b"hello\0world\xff".to_vec()));assert!(r.3.contains("keep-alive"));c.write_all(b"HEAD /file HTTP/1.1\r\n\r\n").unwrap();let r=read_resp(&mut c,true);assert_eq!((r.0,r.1),(200,12));c.write_all(b"GET /empty HTTP/1.1\r\nConnection: cLoSe\r\n\r\n").unwrap();let r=read_resp(&mut c,false);assert_eq!((r.0,r.1),(200,0));assert!(r.3.contains("Connection: close"));let mut b=[0];assert_eq!(c.read(&mut b).unwrap(),0);
        for (p,st) in [("/missing",404),("/",403),("/sub",403),("/file/",403),("/file/.",403),("/link",403),("/sub-link/x",403),("/%2e%2e/file",403),("/%zz",400),("/file#foo",400),("/file%00",400),("/file%5c",400)] {one(port,format!("GET {p} HTTP/1.1\r\nConnection: close\r\n\r\n").as_bytes(),st);}
        one(port,b"POST /file HTTP/1.1\r\n\r\n",405);one(port,b"GET http://host/file HTTP/1.1\r\n\r\n",400);one(port,b"GET /file HTTP/2.0\r\n\r\n",400);
        for x in [&b"GET /file HTTP/1.1\n\n"[..],b"GET /file HTTP/1.1\r\n header: x\r\n\r\n",b"GET /file HTTP/1.1\r\nBad Name: x\r\n\r\n",b"GET /file HTTP/1.1\r\nX: \0\r\n\r\n",b"GET /file HTTP/1.1\r\nContent-Length: 0\r\nContent-Length: 0\r\n\r\n",b"GET /file HTTP/1.1\r\nTransfer-Encoding: identity\r\n\r\n",b"GET /file HTTP/1.1\r\nContent-Length: 1\r\n\r\n"] {one(port,x,400);}
        one(port,b"GET /file HTTP/1.1\r\nContent-Length: 00000\r\n\r\n",200);let mut long=b"GET /file HTTP/1.1\r\nX: ".to_vec();long.extend(vec![b'a';256]);long.extend_from_slice(b"\r\n\r\n");one(port,&long,431);
        let mut c=conn(port);let mut p=Vec::new();for _ in 0..30 {p.extend_from_slice(b"GET /file HTTP/1.1\r\n\r\n");}c.write_all(&p).unwrap();for _ in 0..30 {assert_eq!(read_resp(&mut c,false).0,200);}
        let mut c=conn(port);for i in 0..50 {c.write_all(b"GET /empty HTTP/1.1\r\n\r\n").unwrap();let r=read_resp(&mut c,false);if i==49 {assert!(r.3.contains("Connection: close"));}}assert_eq!(c.read(&mut b).unwrap(),0);
        let mut c=conn(port);for _ in 0..4 {c.write_all(b"GET /chunk HTTP/1.1\r\n\r\n").unwrap();}c.write_all(b"GET /empty HTTP/1.1\r\n\r\n").unwrap();for _ in 0..4 {let r=read_resp(&mut c,false);assert_eq!(r.2,vec![7u8;65536]);}assert_eq!(read_resp(&mut c,false).0,200);
        let mut slow=conn(port);slow.write_all(b"GET /file HTTP/1.1\r\nX:").unwrap();thread::sleep(Duration::from_millis(350));assert_eq!(slow.read(&mut b).unwrap(),0);let mut idle=conn(port);thread::sleep(Duration::from_millis(500));assert_eq!(idle.read(&mut b).unwrap(),0);
        let mut slowout=conn(port);slowout.write_all(b"GET /big HTTP/1.1\r\n\r\n").unwrap();thread::sleep(Duration::from_millis(400));one(port,b"GET /file HTTP/1.1\r\n\r\n",200);
    }
}
