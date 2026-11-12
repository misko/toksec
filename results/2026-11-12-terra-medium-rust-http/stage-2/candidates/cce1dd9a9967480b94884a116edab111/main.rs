use std::collections::HashMap;
use std::ffi::CString;
use std::fs::File;
use std::io::{self, Read, Write};
use std::net::{SocketAddrV4, TcpListener, TcpStream};
use std::os::fd::{AsRawFd, FromRawFd, RawFd};
use std::os::unix::fs::FileTypeExt;
use std::path::Path;
use std::time::{Duration, Instant};
unsafe extern "C" {
 fn epoll_create1(flags:i32)->i32;
 fn epoll_ctl(ep:i32, op:i32, fd:i32, ev:*mut EpEvent)->i32;
 fn epoll_wait(ep:i32, ev:*mut EpEvent, n:i32, timeout:i32)->i32;
 fn openat(fd:i32, name:*const i8, flags:i32, ...)->i32;
 fn sendfile(out:i32, input:i32, offset:*mut i64, count:usize)->isize;
 fn close(fd:i32)->i32;
}
#[repr(C, packed)] #[derive(Clone,Copy)] struct EpEvent { events:u32, data:u64 }
const IN:u32=1; const OUT:u32=4; const ERR:u32=8; const HUP:u32=16; const RDHUP:u32=0x2000;
const ADD:i32=1; const MOD:i32=3; const DEL:i32=2;
const O_NONBLOCK:i32=0x800; const O_DIRECTORY:i32=0x10000; const O_NOFOLLOW:i32=0x20000; const O_CLOEXEC:i32=0x80000;
fn ctl(ep:i32, op:i32, fd:i32, events:u32) { let mut e=EpEvent{events,data:fd as u64}; unsafe{epoll_ctl(ep,op,fd,&mut e);}}
struct Config { addr:SocketAddrV4, root:File, max_conn:usize, hbytes:usize, header:Duration, idle:Duration, write:Duration, max_req:usize, depth:usize }
fn decimal(s:&str)->Option<usize> { if s.is_empty() || !s.bytes().all(|c|c.is_ascii_digit()) {return None} s.parse::<usize>().ok().filter(|x|*x>0) }
fn config()->Result<Config,String> {
 let args:Vec<String>=std::env::args().collect(); if args.len()!=3 || args[1]!="--config" {return Err("arguments".into())}
 let text=std::fs::read_to_string(&args[2]).map_err(|e|e.to_string())?; let mut m=HashMap::new();
 for line in text.lines(){let line=line.trim(); if line.is_empty()||line.starts_with('#'){continue} let (k,v)=line.split_once('=').ok_or("line")?; let k=k.trim();let v=v.trim(); if !["listen","root","max_connections","header_bytes","header_timeout_ms","idle_timeout_ms","write_timeout_ms","max_requests","pipeline_depth"].contains(&k)||m.insert(k.to_string(),v.to_string()).is_some(){return Err("key".into())}}
 if m.len()!=9 {return Err("missing".into())} let addr:SocketAddrV4=m["listen"].parse().map_err(|_|"listen")?; if addr.port()==0{return Err("port".into())}
 let p=Path::new(&m["root"]); if !p.is_absolute()||!p.is_dir(){return Err("root".into())} let root=File::open(p).map_err(|e|e.to_string())?;
 let n=|k:&str| decimal(&m[k]).ok_or_else(||format!("invalid {}",k));
 let max_conn=n("max_connections")?; let hbytes=n("header_bytes")?; let header=Duration::from_millis(n("header_timeout_ms")? as u64);let idle=Duration::from_millis(n("idle_timeout_ms")? as u64);let write=Duration::from_millis(n("write_timeout_ms")? as u64); let max_req=n("max_requests")?; let depth=n("pipeline_depth")?;
 Ok(Config{addr,root,max_conn,hbytes,header,idle,write,max_req,depth})
}
fn token(c:u8)->bool { c.is_ascii_alphanumeric() || b"!#$%&'*+-.^_`|~".contains(&c) }
struct Req { path:String, head:bool, close:bool, method_ok:bool }
fn parse(raw:&[u8])->Result<Req,u16> {
 let s=std::str::from_utf8(raw).map_err(|_|400u16)?; let mut lines=s.split("\r\n"); let line=lines.next().ok_or(400u16)?; let mut parts=line.split(' '); let method=parts.next().ok_or(400u16)?;let target=parts.next().ok_or(400u16)?;let vers=parts.next().ok_or(400u16)?;
 if parts.next().is_some() || method.is_empty() || !method.bytes().all(token) || target.is_empty() || (vers!="HTTP/1.1" && vers!="HTTP/1.0") {return Err(400)}
 let mut closing=vers=="HTTP/1.0"; let mut cl=false;
 for l in lines { if l.is_empty(){continue} let (name,val)=l.split_once(':').ok_or(400u16)?; if name.is_empty()||!name.bytes().all(token)||val.bytes().any(|b| b==127 || (b<32 && b!=b'\t')) {return Err(400)}
 if name.eq_ignore_ascii_case("transfer-encoding"){return Err(400)}
 if name.eq_ignore_ascii_case("content-length"){if cl{return Err(400)} cl=true;let v=val.trim_matches(|c| c==' '||c=='\t');if v.is_empty()||!v.bytes().all(|b|b==b'0'){return Err(400)}}
 if name.eq_ignore_ascii_case("connection"){for t in val.split(','){if t.trim().eq_ignore_ascii_case("close"){closing=true}}}
 }
 if !target.starts_with('/') || target.contains('#') || target.bytes().any(|b|b<=32||b==127||b==b'\\') {return Err(400)}
 let p=target.split('?').next().unwrap(); let b=p.as_bytes(); let mut decoded=Vec::with_capacity(b.len()); let mut i=0;
 while i<b.len(){if b[i]==b'%' {if i+2>=b.len(){return Err(400)} let h=|x:u8|->Option<u8>{match x{b'0'..=b'9'=>Some(x-b'0'),b'a'..=b'f'=>Some(x-b'a'+10),b'A'..=b'F'=>Some(x-b'A'+10),_=>None}};let a=h(b[i+1]).ok_or(400u16)?;let c=h(b[i+2]).ok_or(400u16)?;decoded.push(a*16+c);i+=3;}else{decoded.push(b[i]);i+=1}}
 if decoded.iter().any(|b| *b==0||*b==b'\\') {return Err(400)} let path=String::from_utf8(decoded).map_err(|_|400u16)?;
 if path.split('/').any(|x|x=="..") {return Err(403)}
 Ok(Req{path,head:method=="HEAD",close:closing,method_ok:method=="GET"||method=="HEAD"})
}
fn open_file(root:&File, path:&str)->Result<File,u16> {
 if path.ends_with('/') {return Err(403)}
 let components:Vec<&str>=path.split('/').filter(|x|!x.is_empty()&&*x!=".").collect(); if components.is_empty(){return Err(403)}
 let mut holder:Option<File>=None;
 for (i,name) in components.iter().enumerate(){let c=CString::new(*name).map_err(|_|400u16)?; let parent=holder.as_ref().map_or(root.as_raw_fd(),|f|f.as_raw_fd());let flags=O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC|if i+1<components.len(){O_DIRECTORY}else{0};let fd=unsafe{openat(parent,c.as_ptr(),flags)};
 if fd<0 {let e=io::Error::last_os_error().raw_os_error().unwrap_or(0);return Err(match e{2=>404,40|20|13|1=>403,_=>404})} holder=Some(unsafe{File::from_raw_fd(fd)});
 }
 let f=holder.unwrap();let meta=f.metadata().map_err(|_|403u16)?;if !meta.is_file() || meta.file_type().is_symlink() || meta.file_type().is_fifo(){return Err(403)} Ok(f)
}
struct Conn { stream:TcpStream, buf:Vec<u8>, header_start:Option<Instant>, idle_start:Instant, out:Vec<u8>, sent:usize, file:Option<File>, offset:i64, left:u64, write_start:Instant, close_after:bool, count:usize, writing:bool }
impl Conn { fn new(stream:TcpStream, now:Instant)->Self{Self{stream,buf:Vec::new(),header_start:Some(now),idle_start:now,out:Vec::new(),sent:0,file:None,offset:0,left:0,write_start:now,close_after:false,count:0,writing:false}} }
fn response(c:&mut Conn,status:u16,file:Option<File>,head:bool,close_it:bool,now:Instant){let length=file.as_ref().and_then(|f|f.metadata().ok()).map_or(0,|m|m.len()); let reason=match status{200=>"OK",400=>"Bad Request",403=>"Forbidden",404=>"Not Found",405=>"Method Not Allowed",431=>"Request Header Fields Too Large",_=>"Error"}; c.out=format!("HTTP/1.1 {} {}\r\nContent-Length: {}\r\nContent-Type: application/octet-stream\r\nConnection: {}\r\n\r\n",status,reason,length,if close_it{"close"}else{"keep-alive"}).into_bytes(); c.sent=0; c.left=if head{0}else{length};c.file=if c.left>0{file}else{None};c.offset=0;c.close_after=close_it;c.write_start=now;c.writing=true;c.count+=1;}
fn process(c:&mut Conn,cfg:&Config,now:Instant)->bool {
 if c.writing {return true}
 let mut end=None; let b=&c.buf;
 for i in 0..b.len(){ if b[i]==0 || b[i]==b'\n'&&(i==0||b[i-1]!=b'\r') || b[i]==b'\r'&&i+1<b.len()&&b[i+1]!=b'\n' {response(c,400,None,false,true,now);return true} if i>=3&& &b[i-3..=i]==b"\r\n\r\n" {end=Some(i+1);break} }
 if let Some(n)=end { if n>cfg.hbytes {response(c,431,None,false,true,now);return true} let req=parse(&c.buf[..n]);c.buf.drain(..n);c.header_start=if c.buf.is_empty(){None}else{Some(now)};match req{Err(status)=>response(c,status,None,false,true,now),Ok(req)=>{let close_it=req.close||c.count+1>=cfg.max_req; if !req.method_ok {response(c,405,None,req.head,close_it,now)}else{match open_file(&cfg.root,&req.path){Ok(f)=>response(c,200,Some(f),req.head,close_it,now),Err(code)=>response(c,code,None,req.head,close_it,now)}}}}; }
 else if c.buf.len()>cfg.hbytes {response(c,431,None,false,true,now)}
 true
}
fn drive(c:&mut Conn,cfg:&Config,events:u32,now:Instant)->bool {
 if events & ERR!=0{return false}
 if !c.writing && events & (IN|HUP|RDHUP)!=0 {let mut temp=[0u8;8192]; loop {let cap=cfg.hbytes.saturating_add(1).saturating_sub(c.buf.len()).min(temp.len());if cap==0{break} match c.stream.read(&mut temp[..cap]){Ok(0)=>{if c.buf.is_empty(){return false} break},Ok(n)=>{if c.buf.is_empty(){c.header_start=Some(now)} c.buf.extend_from_slice(&temp[..n]);process(c,cfg,now);if c.writing{break}},Err(e) if e.kind()==io::ErrorKind::WouldBlock=>break,Err(e) if e.kind()==io::ErrorKind::Interrupted=>continue,Err(_)=>return false}}}
 if c.writing {loop {while c.sent<c.out.len(){match c.stream.write(&c.out[c.sent..]){Ok(0)=>return false,Ok(n)=>c.sent+=n,Err(e) if e.kind()==io::ErrorKind::WouldBlock=>return true,Err(e) if e.kind()==io::ErrorKind::Interrupted=>continue,Err(_)=>return false}}
 while c.left>0 {let n=unsafe{sendfile(c.stream.as_raw_fd(),c.file.as_ref().unwrap().as_raw_fd(),&mut c.offset,c.left.min(1024*1024) as usize)}; if n>0{c.left-=n as u64}else if n==0{return false}else{let e=io::Error::last_os_error();if e.kind()==io::ErrorKind::WouldBlock{return true} if e.kind()==io::ErrorKind::Interrupted{continue}return false}}
 c.file=None; if c.close_after{return false} c.writing=false;c.idle_start=now; if !c.buf.is_empty(){process(c,cfg,now);} if !c.writing {break}
 }} true
}
fn run()->Result<(),String>{let cfg=config()?;let listener=TcpListener::bind(cfg.addr).map_err(|e|e.to_string())?;listener.set_nonblocking(true).map_err(|e|e.to_string())?;let ep=unsafe{epoll_create1(O_CLOEXEC)};if ep<0{return Err("epoll".into())}let lfd=listener.as_raw_fd();ctl(ep,ADD,lfd,IN);let mut connections:HashMap<RawFd,Conn>=HashMap::new();let mut events=[EpEvent{events:0,data:0};1024];let mut sweep=Instant::now();let _depth=cfg.depth;
 loop {let n=unsafe{epoll_wait(ep,events.as_mut_ptr(),events.len() as i32,50)};if n<0{if io::Error::last_os_error().kind()==io::ErrorKind::Interrupted{continue}break}let now=Instant::now();for e in events.iter().take(n as usize){let fd=e.data as i32;let flags=e.events;if fd==lfd {loop{match listener.accept(){Ok((s,_))=>{if connections.len()>=cfg.max_conn{drop(s);continue} if s.set_nonblocking(true).is_err(){continue} let fd=s.as_raw_fd();ctl(ep,ADD,fd,IN|RDHUP);connections.insert(fd,Conn::new(s,now));},Err(e) if e.kind()==io::ErrorKind::WouldBlock=>break,Err(_)=>break}}}else if let Some(c)=connections.get_mut(&fd){let before=c.writing;let keep=drive(c,&cfg,flags,now);if !keep{ctl(ep,DEL,fd,0);connections.remove(&fd);}else if before!=c.writing{ctl(ep,MOD,fd,if c.writing{OUT}else{IN|RDHUP});}}}
 if now.duration_since(sweep)>=Duration::from_millis(50){sweep=now;connections.retain(|fd,c|{let expired=if c.writing {now.duration_since(c.write_start)>=cfg.write}else if let Some(start)=c.header_start{now.duration_since(start)>=cfg.header}else{now.duration_since(c.idle_start)>=cfg.idle};if expired{ctl(ep,DEL,*fd,0)} !expired});}
 }
 unsafe{close(ep)};Ok(()) }
fn main(){if let Err(e)=run(){eprintln!("{}",e);std::process::exit(1)}}
