use std::collections::HashMap;
use std::env;
use std::fs::{self,File};
use std::io::{self,Read,Write};
use std::net::{TcpListener,TcpStream,SocketAddr};
use std::os::fd::{AsRawFd,FromRawFd};
use std::path::Path;
use std::time::{Duration,Instant};
use std::ffi::CString;
use std::os::raw::{c_char,c_int,c_void};
extern "C" { fn openat(dirfd:c_int, pathname:*const c_char, flags:c_int, ...) -> c_int; fn epoll_create1(flags:c_int)->c_int; fn epoll_ctl(epfd:c_int,op:c_int,fd:c_int,event:*mut Event)->c_int; fn epoll_wait(epfd:c_int,events:*mut Event,maxevents:c_int,timeout:c_int)->c_int; fn listen(fd:c_int,backlog:c_int)->c_int; fn sendfile(outfd:c_int,infd:c_int,offset:*mut i64,count:usize)->isize; }
const O_CLOEXEC:i32=0x80000; const O_NOFOLLOW:i32=0x20000; const O_NONBLOCK:i32=0x800; const O_PATH:i32=0x200000;
const EPOLLIN:u32=1; const EPOLLOUT:u32=4; const EPOLLERR:u32=8; const EPOLLHUP:u32=16;
#[repr(C,packed)] #[derive(Clone,Copy)] struct Event { events:u32, data:u64 }
struct Config { addr:SocketAddr, root:File, max:usize, header:usize, timeout:Duration, write:Duration }
fn config()->Result<Config,String>{
 let a:Vec<String>=env::args().collect(); if a.len()!=3 || a[1]!="--config" {return Err("usage".into())}
 let text=fs::read_to_string(&a[2]).map_err(|e|e.to_string())?; let mut m=HashMap::new();
 for line in text.lines(){let line=line.trim();if line.is_empty()||line.starts_with('#'){continue} let (k,v)=line.split_once('=').ok_or("line")?;let k=k.trim();let v=v.trim(); if !["listen","root","max_connections","header_bytes","header_timeout_ms","idle_timeout_ms","write_timeout_ms","max_requests","pipeline_depth"].contains(&k)||v.is_empty()||m.insert(k.to_string(),v.to_string()).is_some(){return Err("key".into())}}
 let get=|k:&str|m.get(k).map(|x|x.as_str()).ok_or_else(||format!("missing {k}"));
 let number=|k:&str|->Result<usize,String>{let s=get(k)?;if !s.bytes().all(|b|b.is_ascii_digit()){return Err("number".into())}let n=s.parse::<usize>().map_err(|_|"number")?;if n==0{return Err("zero".into())} Ok(n)};
 let addr:SocketAddr=get("listen")?.parse().map_err(|_|"address")?; let root=get("root")?;if !Path::new(root).is_absolute()||!fs::metadata(root).map_err(|_|"root")?.is_dir(){return Err("root".into())}let root=File::open(root).map_err(|_|"root")?;
 let max=number("max_connections")?;let header=number("header_bytes")?;let timeout=number("header_timeout_ms")?;let write=number("write_timeout_ms")?;number("idle_timeout_ms")?;number("max_requests")?;number("pipeline_depth")?;
 Ok(Config{addr,root,max,header,timeout:Duration::from_millis(timeout as u64),write:Duration::from_millis(write as u64)})
}
fn token(c:u8)->bool { c.is_ascii_alphanumeric()||b"!#$%&'*+-.^_`|~".contains(&c) }
fn hex(c:u8)->Option<u8>{match c {b'0'..=b'9'=>Some(c-b'0'),b'a'..=b'f'=>Some(c-b'a'+10),b'A'..=b'F'=>Some(c-b'A'+10),_=>None}}
fn parse(buf:&[u8])->Result<Vec<u8>,u16>{
 let mut lines=buf[..buf.len()-2].split(|&b|b==b'\n');
 let line=lines.next().ok_or(400u16)?; let line=line.strip_suffix(b"\r").ok_or(400u16)?;
 let parts:Vec<&[u8]>=line.split(|&b|b==b' ').collect(); if parts.len()!=3||parts[0].is_empty()||!parts[0].iter().copied().all(token)||parts[1].is_empty()||!(parts[2]==b"HTTP/1.0"||parts[2]==b"HTTP/1.1"){return Err(400)}
 let target=parts[1]; if target[0]!=b'/' || target.iter().any(|&b|b==b'#'||b==0||b==b'\\'||b<=32||b==127){return Err(400)}
 let mut seen=false;
 for line in lines {if line.is_empty(){break}let line=line.strip_suffix(b"\r").ok_or(400u16)?; if line.is_empty(){return Err(400)} let i=line.iter().position(|&c|c==b':').ok_or(400u16)?; if i==0||!line[..i].iter().copied().all(token){return Err(400)} let name=&line[..i];let value=&line[i+1..]; if value.iter().any(|&b|(b<32&&b!=b'\t')||b==127){return Err(400)}
 if name.eq_ignore_ascii_case(b"transfer-encoding"){return Err(400)} if name.eq_ignore_ascii_case(b"content-length"){if seen{return Err(400)}seen=true;let v=value.trim_ascii();if v.is_empty()||!v.iter().all(|&c|c==b'0'){return Err(400)}} }
 let p=target.split(|&b|b==b'?').next().unwrap(); let mut out=Vec::with_capacity(p.len());let mut i=0;while i<p.len(){let c=if p[i]==b'%' {if i+2>=p.len(){return Err(400)}let h=hex(p[i+1]).ok_or(400u16)?;let l=hex(p[i+2]).ok_or(400u16)?;i+=3;h*16+l}else{let c=p[i];i+=1;c};if c==0||c==b'\\'{return Err(400)}out.push(c)}if std::str::from_utf8(&out).is_err(){return Err(400)}
 if parts[0]!=b"GET"{return Err(405)} if out.split(|&c|c==b'/').any(|c|c==b".."){return Err(403)} Ok(out)
}
fn open_path(root:&File,path:&[u8])->Result<File,u16>{
 if path.ends_with(b"/") {return Err(403)}
 let parts:Vec<&[u8]>=path.split(|&c|c==b'/').filter(|s|!s.is_empty()&&*s!=b".").collect();if parts.is_empty(){return Err(403)}
 let mut cur:Option<File>=None;for (i,part) in parts.iter().enumerate(){let c=CString::new(*part).map_err(|_|400u16)?;let fd=unsafe{openat(cur.as_ref().unwrap_or(root).as_raw_fd(),c.as_ptr(),O_CLOEXEC|O_NOFOLLOW|if i+1==parts.len(){O_NONBLOCK}else{O_PATH})};if fd<0{let e=io::Error::last_os_error().raw_os_error().unwrap_or(0);return Err(if e==2{404}else{403})}let f=unsafe{File::from_raw_fd(fd)};let m=f.metadata().map_err(|_|403u16)?;if i+1==parts.len(){if !m.is_file(){return Err(403)}return Ok(f)}else{if m.file_type().is_symlink()||!m.is_dir(){return Err(403)}cur=Some(f)}} Err(404)
}
struct Conn { stream:TcpStream, started:Instant, buf:Vec<u8>, head:Vec<u8>, pos:usize, file:Option<File>, remaining:u64, writing:bool }
impl Conn {
 fn new(stream:TcpStream)->Self{Self{stream,started:Instant::now(),buf:Vec::new(),head:Vec::new(),pos:0,file:None,remaining:0,writing:false}}
 fn prepare(&mut self,code:u16,file:Option<File>){let phrase=match code{200=>"OK",400=>"Bad Request",403=>"Forbidden",404=>"Not Found",405=>"Method Not Allowed",431=>"Request Header Fields Too Large",_=>"Error"};let len=file.as_ref().and_then(|f|f.metadata().ok()).map(|m|m.len()).unwrap_or(0);self.head=format!("HTTP/1.1 {code} {phrase}\r\nContent-Length: {len}\r\nConnection: close\r\nContent-Type: application/octet-stream\r\n\r\n").into_bytes();self.file=file;self.remaining=len;self.writing=true;self.started=Instant::now();self.buf.clear();}
 fn read_request(&mut self,c:&Config)->bool {let mut temp=[0u8;4096];loop {let avail=c.header.saturating_add(1).saturating_sub(self.buf.len());if avail==0{self.prepare(431,None);return true}let n=match self.stream.read(&mut temp[..avail.min(4096)]) {Ok(0)=>return false,Ok(n)=>n,Err(e) if e.kind()==io::ErrorKind::WouldBlock=>return true,Err(e) if e.kind()==io::ErrorKind::Interrupted=>continue,Err(_)=>return false};let start=self.buf.len();self.buf.extend_from_slice(&temp[..n]);for j in start.saturating_sub(1)..self.buf.len(){if self.buf[j]==0||(self.buf[j]==b'\n'&&(j==0||self.buf[j-1]!=b'\r'))||(self.buf[j]==b'\r'&&j+1<self.buf.len()&&self.buf[j+1]!=b'\n'){self.prepare(400,None);return true}if j>=3&&self.buf[j-3..=j]==*b"\r\n\r\n"{let size=j+1;if size>c.header{self.prepare(431,None);return true}let result=parse(&self.buf[..size]).and_then(|path|open_path(&c.root,&path));match result{Ok(f)=>self.prepare(200,Some(f)),Err(code)=>self.prepare(code,None)}return true}}if self.buf.len()>c.header{self.prepare(431,None);return true}}}
 fn write_response(&mut self)->bool {while self.pos<self.head.len(){match self.stream.write(&self.head[self.pos..]){Ok(0)=>return false,Ok(n)=>self.pos+=n,Err(e) if e.kind()==io::ErrorKind::WouldBlock=>return true,Err(e) if e.kind()==io::ErrorKind::Interrupted=>continue,Err(_)=>return false}}
 while self.remaining>0 {let count=self.remaining.min(1024*1024) as usize;let n=unsafe{sendfile(self.stream.as_raw_fd(),self.file.as_ref().unwrap().as_raw_fd(),std::ptr::null_mut(),count)};if n>0{self.remaining-=n as u64}else if n==0{return false}else{let e=io::Error::last_os_error();if e.kind()==io::ErrorKind::WouldBlock{return true}if e.kind()==io::ErrorKind::Interrupted{continue}return false}}false }
}
fn ctl(ep:i32,op:i32,fd:i32,flags:u32,id:u64)->bool{let mut e=Event{events:flags,data:id};unsafe{epoll_ctl(ep,op,fd,&mut e)==0}}
fn run(c:Config)->io::Result<()> {let listener=TcpListener::bind(c.addr)?;listener.set_nonblocking(true)?;if unsafe{listen(listener.as_raw_fd(),4096)}<0{return Err(io::Error::last_os_error())}let ep=unsafe{epoll_create1(O_CLOEXEC)};if ep<0{return Err(io::Error::last_os_error())}let epfile=unsafe{File::from_raw_fd(ep)};if !ctl(ep,1,listener.as_raw_fd(),EPOLLIN,0){return Err(io::Error::last_os_error())}let mut map:HashMap<u64,Conn>=HashMap::new();let mut next=1u64;let mut events=[Event{events:0,data:0};1024];let mut sweep=Instant::now();
 loop {let n=unsafe{epoll_wait(ep,events.as_mut_ptr(),events.len() as i32,50)};if n<0{let e=io::Error::last_os_error();if e.kind()==io::ErrorKind::Interrupted{continue}return Err(e)}for e in &events[..n as usize]{let id=e.data;let flags=e.events;if id==0{for _ in 0..256{match listener.accept(){Ok((s,_))=>{if map.len()>=c.max{drop(s);continue}if s.set_nonblocking(true).is_err(){continue}let id=next;next=next.wrapping_add(1);if next==0{next=1}if ctl(ep,1,s.as_raw_fd(),EPOLLIN,id){map.insert(id,Conn::new(s));}},Err(e) if e.kind()==io::ErrorKind::WouldBlock=>break,Err(e) if e.kind()==io::ErrorKind::Interrupted=>continue,Err(_)=>break}}continue}if let Some(conn)=map.get_mut(&id){let alive=if flags&(EPOLLERR|EPOLLHUP)!=0{false}else if conn.writing{conn.write_response()}else{conn.read_request(&c)};if !alive{map.remove(&id);}else if conn.writing{if !ctl(ep,3,conn.stream.as_raw_fd(),EPOLLOUT,id){map.remove(&id);}}}}
 if sweep.elapsed()>=Duration::from_millis(25){map.retain(|_,conn|conn.started.elapsed()<if conn.writing{c.write}else{c.timeout});sweep=Instant::now();}let _=&epfile;
 }
}
fn main(){let c=match config(){Ok(c)=>c,Err(e)=>{eprintln!("config: {e}");std::process::exit(1)}};if let Err(e)=run(c){eprintln!("server: {e}");std::process::exit(1)}}
