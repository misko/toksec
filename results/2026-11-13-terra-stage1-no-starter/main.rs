use std::{collections::HashMap,env,fs::{self,File},io::{self,Read,Write},net::{TcpListener,TcpStream,SocketAddr},os::fd::{AsRawFd,FromRawFd},path::Path,sync::{Arc,atomic::{AtomicUsize,Ordering}},time::{Duration,Instant},ffi::CString,thread};
use std::os::unix::fs::{FileTypeExt,OpenOptionsExt};
unsafe extern "C" {fn openat(dirfd:i32,path:*const i8,flags:i32,...)->i32;}
const O_RDONLY:i32=0; const O_NONBLOCK:i32=0x800; const O_CLOEXEC:i32=0x80000; const O_NOFOLLOW:i32=0x20000; const O_PATH:i32=0x200000;
struct Config { addr:SocketAddr, root:File, max:usize, header:usize, htime:Duration, wtime:Duration }
fn config()->Result<Config,String>{
 let args:Vec<_>=env::args().collect(); if args.len()!=3 || args[1]!="--config" {return Err("args".into())}
 let text=fs::read_to_string(&args[2]).map_err(|e|e.to_string())?; let mut m=HashMap::new();
 for line in text.lines(){let l=line.trim();if l.is_empty()||l.starts_with('#'){continue} let (k,v)=l.split_once('=').ok_or("line")?;let k=k.trim();let v=v.trim();if !["listen","root","max_connections","header_bytes","header_timeout_ms","idle_timeout_ms","write_timeout_ms","max_requests","pipeline_depth"].contains(&k)||m.insert(k.to_owned(),v.to_owned()).is_some(){return Err("key".into())}}
 if m.len()!=9{return Err("missing".into())} let num=|key:&str|->Result<usize,String>{let s=&m[key];if s.is_empty()||!s.bytes().all(|c|c.is_ascii_digit()){return Err("number".into())}let n=s.parse::<usize>().map_err(|_|"number")?;if n==0{return Err("zero".into())}Ok(n)};
 let addr=m["listen"].parse::<SocketAddr>().map_err(|_|"addr")?; let rootpath=Path::new(&m["root"]);if !rootpath.is_absolute()||!rootpath.is_dir(){return Err("root".into())}let root=fs::OpenOptions::new().read(true).custom_flags(O_CLOEXEC).open(rootpath).map_err(|_|"root")?;
 let max=num("max_connections")?;let header=num("header_bytes")?;let ht=num("header_timeout_ms")?;let wt=num("write_timeout_ms")?;num("idle_timeout_ms")?;num("max_requests")?;num("pipeline_depth")?;
 if header>16*1024*1024 || max>1000000 || ht>u64::MAX as usize || wt>u64::MAX as usize{return Err("limit".into())}
 Ok(Config{addr,root,max,header,htime:Duration::from_millis(ht as u64),wtime:Duration::from_millis(wt as u64)})
}
fn token(c:u8)->bool{c.is_ascii_alphanumeric()||b"!#$%&'*+-.^_`|~".contains(&c)}
fn parse(raw:&[u8])->Result<Vec<u8>,u16>{
 let lines:Vec<&[u8]>=raw[..raw.len()-2].split(|&x|x==b'\n').collect();
 let line=lines.first().ok_or(400u16)?;let line=line.strip_suffix(b"\r").ok_or(400u16)?;
 let parts:Vec<&[u8]>=line.split(|&x|x==b' ').collect();if parts.len()!=3||parts.iter().any(|p|p.is_empty())||!parts[0].iter().copied().all(token){return Err(400)}
 if parts[2]!=b"HTTP/1.0"&&parts[2]!=b"HTTP/1.1"{return Err(400)}
 let target=parts[1]; if target.first()!=Some(&b'/') || target.contains(&b'#') || target.iter().any(|&c|c<=32||c==127){return Err(400)}
 let p=target.split(|&c|c==b'?').next().unwrap();let mut out=Vec::with_capacity(p.len());let mut i=0;while i<p.len(){let c=if p[i]==b'%' {if i+2>=p.len(){return Err(400)}let h=|b:u8|->Option<u8>{match b{b'0'..=b'9'=>Some(b-b'0'),b'a'..=b'f'=>Some(b-b'a'+10),b'A'..=b'F'=>Some(b-b'A'+10),_=>None}};let v=h(p[i+1]).ok_or(400u16)?*16+h(p[i+2]).ok_or(400u16)?;i+=3;v}else{let v=p[i];i+=1;v};if c==0||c==b'\\'{return Err(400)}out.push(c)}
 if std::str::from_utf8(&out).is_err(){return Err(400)}
 let mut length=false;for line in lines.iter().skip(1){if line.is_empty(){continue}let line=line.strip_suffix(b"\r").ok_or(400u16)?;if line.is_empty(){continue}let pos=line.iter().position(|&x|x==b':').ok_or(400u16)?;let (name,value)=line.split_at(pos);if name.is_empty()||!name.iter().copied().all(token)||value[1..].iter().any(|&c|(c<32&&c!=9)||c==127){return Err(400)}
 if name.eq_ignore_ascii_case(b"transfer-encoding"){return Err(400)} if name.eq_ignore_ascii_case(b"content-length"){if length{return Err(400)}length=true;let v=value[1..].trim_ascii();if v.is_empty()||!v.iter().all(|&x|x==b'0'){return Err(400)}}}
 if parts[0]!=b"GET"{return Err(405)} Ok(out)
}
fn lookup(root:&File,path:&[u8])->Result<File,u16>{
 let comps:Vec<&[u8]>=path.split(|&c|c==b'/').filter(|p|!p.is_empty()&&*p!=b".").collect();if comps.iter().any(|&p|p==b".."){return Err(403)} if comps.is_empty()||path.ends_with(b"/"){return Err(403)}
 let mut dir:Option<File>=None;
 for (idx,part) in comps.iter().enumerate(){let name=CString::new(*part).map_err(|_|400u16)?;let fd=unsafe{openat(dir.as_ref().unwrap_or(root).as_raw_fd(),name.as_ptr(),O_PATH|O_NOFOLLOW|O_CLOEXEC)};if fd<0 {let e=io::Error::last_os_error().raw_os_error().unwrap_or(0);return Err(if e==2||e==20{404}else{403})}let f=unsafe{File::from_raw_fd(fd)};let md=f.metadata().map_err(|_|403u16)?;if md.file_type().is_symlink(){return Err(403)}if idx+1<comps.len(){if !md.is_dir(){return Err(403)}dir=Some(f);continue} if !md.is_file()||md.file_type().is_fifo()||md.file_type().is_socket(){return Err(403)}
 let fd=unsafe{openat(dir.as_ref().unwrap_or(root).as_raw_fd(),name.as_ptr(),O_RDONLY|O_NONBLOCK|O_NOFOLLOW|O_CLOEXEC)};if fd<0{return Err(403)}let file=unsafe{File::from_raw_fd(fd)};if !file.metadata().map_err(|_|403u16)?.is_file(){return Err(403)}return Ok(file)
 }Err(403)
}
fn response(s:&mut TcpStream,status:u16,mut file:Option<File>){let reason=match status{200=>"OK",400=>"Bad Request",403=>"Forbidden",404=>"Not Found",405=>"Method Not Allowed",431=>"Request Header Fields Too Large",_=>"Error"};let len=file.as_ref().and_then(|f|f.metadata().ok()).map(|m|m.len()).unwrap_or(0);let h=format!("HTTP/1.1 {} {}\r\nContent-Length: {}\r\nConnection: close\r\nContent-Type: application/octet-stream\r\n\r\n",status,reason,len);if s.write_all(h.as_bytes()).is_ok(){if let Some(ref mut f)=file{let _=io::copy(f,s);}}}
fn serve(mut s:TcpStream,c:&Config,start:Instant){let _=s.set_write_timeout(Some(c.wtime));let mut data=Vec::with_capacity(c.header.min(8192)+1);let mut b=[0u8;4096];loop{let Some(left)=c.htime.checked_sub(start.elapsed()) else{return};if left.is_zero(){return}let _=s.set_read_timeout(Some(left));let n=match s.read(&mut b){Ok(0)=>return,Ok(n)=>n,Err(_)=>return};for &x in &b[..n]{data.push(x);let l=data.len();if x==0||(x==b'\n'&&(l<2||data[l-2]!=b'\r'))||(l>=2&&data[l-2]==b'\r'&&x!=b'\n'){response(&mut s,400,None);return}if l>=4&&data[l-4..]==*b"\r\n\r\n"{if l>c.header{response(&mut s,431,None);return}match parse(&data){Ok(p)=>match lookup(&c.root,&p){Ok(f)=>response(&mut s,200,Some(f)),Err(code)=>response(&mut s,code,None)},Err(code)=>response(&mut s,code,None)}return}if l>c.header{response(&mut s,431,None);return}}}}
fn main(){let c=match config(){Ok(c)=>Arc::new(c),Err(e)=>{eprintln!("config: {e}");std::process::exit(1)}};let listener=match TcpListener::bind(c.addr){Ok(x)=>x,Err(e)=>{eprintln!("bind: {e}");std::process::exit(1)}};let active=Arc::new(AtomicUsize::new(0));for con in listener.incoming(){if let Ok(s)=con{let start=Instant::now();if active.fetch_add(1,Ordering::Relaxed)>=c.max{active.fetch_sub(1,Ordering::Relaxed);continue}let (cc,aa)=(c.clone(),active.clone());if thread::Builder::new().stack_size(128*1024).spawn(move||{serve(s,&cc,start);aa.fetch_sub(1,Ordering::Relaxed);}).is_err(){active.fetch_sub(1,Ordering::Relaxed);}}}}
