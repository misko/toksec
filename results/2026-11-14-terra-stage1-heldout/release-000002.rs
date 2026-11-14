use std::collections::HashMap;
use std::env;
use std::ffi::CString;
use std::fs::{self,File,OpenOptions};
use std::io::{self,Read,Write};
use std::net::{SocketAddr,TcpListener,TcpStream};
use std::os::fd::{AsRawFd,FromRawFd};
use std::os::unix::fs::OpenOptionsExt;
use std::time::{Duration,Instant};

unsafe extern "C" {
 fn epoll_create1(flags:i32)->i32;
 fn epoll_ctl(epfd:i32,op:i32,fd:i32,event:*mut Event)->i32;
 fn epoll_wait(epfd:i32,events:*mut Event,maxevents:i32,timeout:i32)->i32;
 fn openat(dirfd:i32,path:*const i8,flags:i32,...)->i32;
 fn sendfile(out:i32,input:i32,offset:*mut i64,count:usize)->isize;
 fn listen(fd:i32,backlog:i32)->i32;
}
#[repr(C,packed)]
#[derive(Clone,Copy)]
struct Event { events:u32, data:u64 }
const IN:u32=1; const OUT:u32=4; const ERR:u32=8; const HUP:u32=16; const RDHUP:u32=0x2000;
const ADD:i32=1; const MOD:i32=3; const DEL:i32=2;
const O_NONBLOCK:i32=0x800; const O_DIRECTORY:i32=0x10000; const O_NOFOLLOW:i32=0x20000; const O_CLOEXEC:i32=0x80000; const O_PATH:i32=0x200000;
struct Config { listen:SocketAddr, root:File, max:usize, headers:usize, header_timeout:Duration, write_timeout:Duration }
fn config()->Result<Config,String>{
 let mut args=env::args(); args.next(); if args.next().as_deref()!=Some("--config") {return Err("expected --config".into())} let path=args.next().ok_or("missing config")?; if args.next().is_some(){return Err("extra arguments".into())}
 let text=fs::read_to_string(path).map_err(|e|e.to_string())?;
 let names=["listen","root","max_connections","header_bytes","header_timeout_ms","idle_timeout_ms","write_timeout_ms","max_requests","pipeline_depth"];
 let mut m=HashMap::new(); for line in text.lines(){let l=line.trim(); if l.is_empty()||l.starts_with('#'){continue} let (k,v)=l.split_once('=').ok_or("bad config")?; let k=k.trim(); let v=v.trim(); if !names.contains(&k)||v.is_empty()||m.insert(k,v).is_some(){return Err("bad config key".into())}}
 if m.len()!=names.len(){return Err("missing key".into())}
 let listen:SocketAddr=m["listen"].parse().map_err(|_|"bad listen")?;
 let rootpath=std::path::Path::new(m["root"]); if !rootpath.is_absolute(){return Err("root not absolute".into())}
 let root=OpenOptions::new().read(true).custom_flags(O_DIRECTORY|O_CLOEXEC).open(rootpath).map_err(|e|e.to_string())?;
 if !root.metadata().map_err(|e|e.to_string())?.is_dir(){return Err("not directory".into())}
 let number=|k:&str|->Result<usize,String>{let v=m[k]; if !v.bytes().all(|b|b.is_ascii_digit()){return Err("bad number".into())} let n=v.parse::<usize>().map_err(|_|"bad number")?; if n==0{return Err("zero".into())} Ok(n)};
 let max=number("max_connections")?; let headers=number("header_bytes")?;
 let ht=number("header_timeout_ms")?; let wt=number("write_timeout_ms")?; number("idle_timeout_ms")?; number("max_requests")?; number("pipeline_depth")?;
 Ok(Config{listen,root,max,headers,header_timeout:Duration::from_millis(ht as u64),write_timeout:Duration::from_millis(wt as u64)})
}
fn token(b:u8)->bool { b.is_ascii_alphanumeric() || b"!#$%&'*+-.^_`|~".contains(&b) }
fn hex(c:u8)->Option<u8>{match c {b'0'..=b'9'=>Some(c-b'0'),b'a'..=b'f'=>Some(c-b'a'+10),b'A'..=b'F'=>Some(c-b'A'+10),_=>None}}
fn parse_request(req:&[u8])->Result<Vec<u8>,u16>{
 if req.iter().any(|&b|b==0) {return Err(400)}
 let lines:Vec<&[u8]>=req[..req.len()-4].split(|&b|b==b'\n').collect();
 if lines.is_empty(){return Err(400)}
 let first=if lines.len()>1 {lines[0].strip_suffix(b"\r").ok_or(400u16)?} else {lines[0]};
 let p:Vec<&[u8]>=first.split(|&b|b==b' ').collect();
 if p.len()!=3 || p[0].is_empty() || !p[0].iter().copied().all(token) || p[1].is_empty() || !(p[2]==b"HTTP/1.0"||p[2]==b"HTTP/1.1") {return Err(400)}
 let mut cl=false;
 for (i,line0) in lines.iter().enumerate().skip(1){
  let line=if i+1<lines.len(){line0.strip_suffix(b"\r").ok_or(400u16)?}else{*line0};
  let pos=line.iter().position(|&b|b==b':').ok_or(400u16)?;
  if pos==0||!line[..pos].iter().copied().all(token){return Err(400)}
  let v=&line[pos+1..]; if v.iter().any(|&b| (b<32&&b!=b'\t')||b==127){return Err(400)}
  if line[..pos].eq_ignore_ascii_case(b"transfer-encoding"){return Err(400)}
  if line[..pos].eq_ignore_ascii_case(b"content-length") {if cl{return Err(400)} cl=true; let v=trim_ows(v); if v.is_empty()||!v.iter().all(|&b|b==b'0'){return Err(400)}}
 }
 let target=p[1]; if target[0]!=b'/' || target.iter().any(|&b|b==b'#'||b<33||b==127) {return Err(400)}
 let raw=target.split(|&b|b==b'?').next().unwrap(); let mut path=Vec::with_capacity(raw.len()); let mut i=0;
 while i<raw.len(){let b=if raw[i]==b'%' {if i+2>=raw.len(){return Err(400)} let v=hex(raw[i+1]).ok_or(400u16)?*16+hex(raw[i+2]).ok_or(400u16)?; i+=3; v} else {let v=raw[i];i+=1;v}; if b==0||b==b'\\'{return Err(400)} path.push(b)}
 if std::str::from_utf8(&path).is_err(){return Err(400)}
 if path.split(|&b|b==b'/').any(|c|c==b".."){return Err(403)}
 if p[0]!=b"GET"{return Err(405)}
 Ok(path)
}
fn trim_ows(mut b:&[u8])->&[u8]{while b.first().map_or(false,|x|*x==b' '||*x==b'\t'){b=&b[1..]} while b.last().map_or(false,|x|*x==b' '||*x==b'\t'){b=&b[..b.len()-1]} b}
fn find_file(root:&File,path:&[u8])->Result<(File,u64),u16>{
 let trailing=path.ends_with(b"/");
 let parts:Vec<&[u8]>=path.split(|&x|x==b'/').filter(|p|!p.is_empty()).collect();
 if parts.is_empty(){return Err(403)}
 let mut dir:Option<File>=None;
 for (i,part) in parts.iter().enumerate(){
  let final_part=i+1==parts.len(); let name=CString::new(*part).map_err(|_|400u16)?;
  let parent=dir.as_ref().unwrap_or(root).as_raw_fd();
  let flags=O_CLOEXEC|O_NOFOLLOW|O_NONBLOCK|if final_part {0} else {O_DIRECTORY};
  let fd=unsafe{openat(parent,name.as_ptr(),flags)};
  if fd<0 {let e=io::Error::last_os_error().raw_os_error().unwrap_or(0); if e==2{return Err(404)}
   if final_part {let probe=unsafe{openat(parent,name.as_ptr(),O_PATH|O_NOFOLLOW|O_CLOEXEC)}; if probe>=0 {let f=unsafe{File::from_raw_fd(probe)}; if let Ok(m)=f.metadata(){if !m.is_file(){return Err(403)}}}}
   return Err(match e {20|40|13|1=>403,_=>404})}
  let f=unsafe{File::from_raw_fd(fd)}; let meta=f.metadata().map_err(|_|403u16)?;
  if final_part {if trailing||!meta.is_file(){return Err(403)} return Ok((f,meta.len()))} else {if !meta.is_dir(){return Err(403)} dir=Some(f)}
 }
 Err(404)
}
struct Conn { sock:TcpStream, accepted:Instant, started:Option<Instant>, input:Vec<u8>, output:Vec<u8>, sent:usize, file:Option<File>, left:u64, offset:i64 }
impl Conn {fn new(sock:TcpStream)->Self{Self{sock,accepted:Instant::now(),started:None,input:Vec::with_capacity(1024),output:Vec::new(),sent:0,file:None,left:0,offset:0}}
 fn response(&mut self,status:u16,file:Option<(File,u64)>){let len=file.as_ref().map_or(0,|x|x.1); let reason=match status {200=>"OK",400=>"Bad Request",403=>"Forbidden",404=>"Not Found",405=>"Method Not Allowed",431=>"Request Header Fields Too Large",_=>"Error"}; self.output=format!("HTTP/1.1 {} {}\r\nContent-Length: {}\r\nConnection: close\r\n{}\r\n",status,reason,len,if status==405{"Allow: GET\r\n"}else{""}).into_bytes(); if let Some((f,n))=file {self.file=Some(f);self.left=n} self.started=Some(Instant::now());}
 fn read_request(&mut self,c:&Config)->bool {let mut buf=[0u8;8192]; loop {match self.sock.read(&mut buf){Ok(0)=>return false,Ok(n)=>{self.input.extend_from_slice(&buf[..n]); if let Some(end)=self.input.windows(4).position(|w|w==b"\r\n\r\n").map(|x|x+4){ if end>c.headers {self.response(431,None)}else{match parse_request(&self.input[..end]){Ok(path)=>match find_file(&c.root,&path){Ok(f)=>self.response(200,Some(f)),Err(e)=>self.response(e,None)},Err(e)=>self.response(e,None)}} return true} if self.input.len()>c.headers {self.response(431,None);return true} if self.input.iter().enumerate().any(|(i,&b)|b==0||(b==b'\n'&&(i==0||self.input[i-1]!=b'\r'))||(b==b'\r'&&i+1<self.input.len()&&self.input[i+1]!=b'\n')){self.response(400,None);return true}},Err(e) if e.kind()==io::ErrorKind::WouldBlock=>return true,Err(e) if e.kind()==io::ErrorKind::Interrupted=>continue,Err(_)=>return false}}}
 fn write_response(&mut self)->bool {while self.sent<self.output.len(){match self.sock.write(&self.output[self.sent..]){Ok(0)=>return false,Ok(n)=>self.sent+=n,Err(e) if e.kind()==io::ErrorKind::WouldBlock=>return true,Err(e) if e.kind()==io::ErrorKind::Interrupted=>continue,Err(_)=>return false}} while self.left>0 {let n=unsafe{sendfile(self.sock.as_raw_fd(),self.file.as_ref().unwrap().as_raw_fd(),&mut self.offset,self.left.min(1<<20) as usize)}; if n>0 {self.left-=n as u64} else if n==0{return false} else {let e=io::Error::last_os_error(); if e.kind()==io::ErrorKind::WouldBlock{return true} if e.kind()==io::ErrorKind::Interrupted{continue} return false}} false}
}
fn ctl(ep:i32,op:i32,fd:i32,events:u32){let mut ev=Event{events,data:fd as u64}; unsafe{epoll_ctl(ep,op,fd,&mut ev)};}
fn run(c:Config)->io::Result<()> {let listener=TcpListener::bind(c.listen)?; listener.set_nonblocking(true)?; unsafe{listen(listener.as_raw_fd(),8192)}; let ep=unsafe{epoll_create1(O_CLOEXEC)}; if ep<0{return Err(io::Error::last_os_error())} let lfd=listener.as_raw_fd();ctl(ep,ADD,lfd,IN);
 let mut conns:HashMap<i32,Conn>=HashMap::new(); let mut events=vec![Event{events:0,data:0};1024]; let mut sweep=Instant::now();
 loop {let n=unsafe{epoll_wait(ep,events.as_mut_ptr(),events.len() as i32,25)}; if n<0 {if io::Error::last_os_error().kind()==io::ErrorKind::Interrupted{continue} return Err(io::Error::last_os_error())}
 for ev in &events[..n as usize] {let fd=ev.data as i32; let flags=ev.events; if fd==lfd {loop {match listener.accept(){Ok((sock,_))=>{if conns.len()>=c.max {drop(sock);continue} if sock.set_nonblocking(true).is_err(){continue} let _=sock.set_nodelay(true); let fd=sock.as_raw_fd();ctl(ep,ADD,fd,IN|RDHUP);conns.insert(fd,Conn::new(sock));},Err(e) if e.kind()==io::ErrorKind::Interrupted=>continue,Err(_)=>break}}} else if let Some(mut conn)=conns.remove(&fd) {let mut alive=true; if conn.started.is_none(){if conn.accepted.elapsed()>=c.header_timeout {alive=false} else if flags&(IN|RDHUP|HUP|ERR)!=0 {alive=conn.read_request(&c)}} if alive&&conn.started.is_some(){if conn.started.unwrap().elapsed()>=c.write_timeout {alive=false} else {alive=conn.write_response(); if alive{ctl(ep,MOD,fd,OUT|RDHUP)}}} if alive {conns.insert(fd,conn);} else {ctl(ep,DEL,fd,0);}}
 }
 if sweep.elapsed()>=Duration::from_millis(25){let now=Instant::now(); conns.retain(|fd,conn|{let keep=match conn.started{Some(t)=>now.duration_since(t)<c.write_timeout,None=>now.duration_since(conn.accepted)<c.header_timeout}; if !keep{ctl(ep,DEL,*fd,0)} keep});sweep=now;}
 }
}
fn main(){match config().and_then(|c|run(c).map_err(|e|e.to_string())){Ok(())=>(),Err(e)=>{eprintln!("{}",e);std::process::exit(1)}}}
