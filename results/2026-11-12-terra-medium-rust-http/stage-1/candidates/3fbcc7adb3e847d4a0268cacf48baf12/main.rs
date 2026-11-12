use std::collections::HashMap;
use std::env;
use std::fs::{self,File};
use std::io::{self,Read,Write};
use std::net::{TcpListener,TcpStream,SocketAddr};
use std::os::fd::{AsRawFd,FromRawFd};
use std::path::Path;
use std::sync::{Arc,atomic::{AtomicUsize,Ordering}};
use std::time::{Duration,Instant};
use std::ffi::CString;
use std::os::raw::{c_char,c_int};
extern "C" { fn openat(dirfd:c_int, pathname:*const c_char, flags:c_int, ...) -> c_int; fn mallopt(param:c_int,value:c_int)->c_int; }
const O_CLOEXEC:i32=0x80000; const O_NOFOLLOW:i32=0x20000; const O_NONBLOCK:i32=0x800; const O_PATH:i32=0x200000;
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
 let mut lines=buf[..buf.len()-4].split(|&b|b==b'\n');
 let line=lines.next().ok_or(400u16)?; let line=line.strip_suffix(b"\r").ok_or(400u16)?;
 let parts:Vec<&[u8]>=line.split(|&b|b==b' ').collect(); if parts.len()!=3||parts[0].is_empty()||!parts[0].iter().copied().all(token)||parts[1].is_empty()||!(parts[2]==b"HTTP/1.0"||parts[2]==b"HTTP/1.1"){return Err(400)}
 let target=parts[1]; if target[0]!=b'/' || target.iter().any(|&b|b==b'#'||b==0||b==b'\\'||b<=32||b==127){return Err(400)}
 let mut seen=false;
 for line in lines { let line=line.strip_suffix(b"\r").unwrap_or(line); if line.is_empty(){return Err(400)} let i=line.iter().position(|&c|c==b':').ok_or(400u16)?; if i==0||!line[..i].iter().copied().all(token){return Err(400)} let name=&line[..i];let value=&line[i+1..]; if value.iter().any(|&b|(b<32&&b!=b'\t')||b==127){return Err(400)}
 if name.eq_ignore_ascii_case(b"transfer-encoding"){return Err(400)} if name.eq_ignore_ascii_case(b"content-length"){if seen{return Err(400)}seen=true;let v=value.trim_ascii();if v.is_empty()||!v.iter().all(|&c|c==b'0'){return Err(400)}} }
 let p=target.split(|&b|b==b'?').next().unwrap(); let mut out=Vec::with_capacity(p.len());let mut i=0;while i<p.len(){let c=if p[i]==b'%' {if i+2>=p.len(){return Err(400)}let h=hex(p[i+1]).ok_or(400u16)?;let l=hex(p[i+2]).ok_or(400u16)?;i+=3;h*16+l}else{let c=p[i];i+=1;c};if c==0||c==b'\\'{return Err(400)}out.push(c)}if std::str::from_utf8(&out).is_err(){return Err(400)}
 if parts[0]!=b"GET"{return Err(405)} if out.split(|&c|c==b'/').any(|c|c==b".."){return Err(403)} Ok(out)
}
fn open_path(root:&File,path:&[u8])->Result<File,u16>{
 if path.ends_with(b"/") {return Err(403)}
 let parts:Vec<&[u8]>=path.split(|&c|c==b'/').filter(|s|!s.is_empty()&&*s!=b".").collect();if parts.is_empty(){return Err(403)}
 let mut cur:Option<File>=None;for (i,part) in parts.iter().enumerate(){let c=CString::new(*part).map_err(|_|400u16)?;let fd=unsafe{openat(cur.as_ref().unwrap_or(root).as_raw_fd(),c.as_ptr(),O_CLOEXEC|O_NOFOLLOW|if i+1==parts.len(){O_NONBLOCK}else{O_PATH})};if fd<0{let e=io::Error::last_os_error().raw_os_error().unwrap_or(0);return Err(if e==2{404}else{403})}let f=unsafe{File::from_raw_fd(fd)};let m=f.metadata().map_err(|_|403u16)?;if i+1==parts.len(){if !m.is_file(){return Err(403)}return Ok(f)}else{if m.file_type().is_symlink()||!m.is_dir(){return Err(403)}cur=Some(f)}} Err(404)
}
fn reply(s:&mut TcpStream,code:u16,file:Option<File>){let phrase=match code{200=>"OK",400=>"Bad Request",403=>"Forbidden",404=>"Not Found",405=>"Method Not Allowed",431=>"Request Header Fields Too Large",_=>"Error"};let len=file.as_ref().and_then(|f|f.metadata().ok()).map(|m|m.len()).unwrap_or(0);let h=format!("HTTP/1.1 {code} {phrase}\r\nContent-Length: {len}\r\nConnection: close\r\nContent-Type: application/octet-stream\r\n\r\n");if s.write_all(h.as_bytes()).is_ok(){if let Some(f)=file{let _=io::copy(&mut f.take(len),s);}}}
fn serve(mut s:TcpStream,c:&Config,accepted:Instant){let _=s.set_write_timeout(Some(c.write));let mut buf=Vec::new();let mut temp=[0u8;4096];loop{let rem=match c.timeout.checked_sub(accepted.elapsed()){Some(r) if !r.is_zero()=>r,_=>return};let _=s.set_read_timeout(Some(rem));let available=c.header.saturating_add(1).saturating_sub(buf.len());if available==0{reply(&mut s,431,None);return}let n=match s.read(&mut temp[..available.min(4096)]){Ok(0)=>return,Ok(n)=>n,Err(_)=>return};let start=buf.len();buf.extend_from_slice(&temp[..n]);for j in start.saturating_sub(1)..buf.len(){if buf[j]==0 || (buf[j]==b'\n' && (j==0||buf[j-1]!=b'\r')) || (buf[j]==b'\r'&&j+1<buf.len()&&buf[j+1]!=b'\n'){reply(&mut s,400,None);return}if j>=3&&buf[j-3..=j]==*b"\r\n\r\n"{let size=j+1;if size>c.header{reply(&mut s,431,None);return}match parse(&buf[..size]){Err(e)=>reply(&mut s,e,None),Ok(path)=>match open_path(&c.root,&path){Ok(f)=>reply(&mut s,200,Some(f)),Err(e)=>reply(&mut s,e,None)}}return}}
 if buf.len()>c.header{reply(&mut s,431,None);return}}
}
fn main(){unsafe { mallopt(-8,1); } let c=match config(){Ok(c)=>Arc::new(c),Err(e)=>{eprintln!("config: {e}");std::process::exit(1)}};let listener=match TcpListener::bind(c.addr){Ok(x)=>x,Err(e)=>{eprintln!("bind: {e}");std::process::exit(1)}};let active=Arc::new(AtomicUsize::new(0));for stream in listener.incoming(){if let Ok(s)=stream{let now=Instant::now();if active.fetch_add(1,Ordering::Relaxed)>=c.max{active.fetch_sub(1,Ordering::Relaxed);continue}let c=c.clone();let a=active.clone();if std::thread::Builder::new().stack_size(131072).spawn(move||{serve(s,&c,now);a.fetch_sub(1,Ordering::Relaxed);}).is_err(){active.fetch_sub(1,Ordering::Relaxed);}}}}
