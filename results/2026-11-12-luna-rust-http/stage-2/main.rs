use std::collections::HashMap;
use std::env;
use std::fs::{self, File};
use std::io::{self, Read, Write};
use std::net::{TcpListener, TcpStream, SocketAddr};
use std::path::{Path, PathBuf};
use std::sync::{Arc, atomic::{AtomicUsize, Ordering}};
use std::thread;
use std::time::{Duration, Instant};

#[derive(Clone)] struct Config { listen: SocketAddr, root: PathBuf, max_conn: usize, header_bytes: usize, header_ms:u64, idle_ms:u64, write_ms:u64, max_req:usize, pipeline:usize }
fn parse_num(m:&HashMap<String,String>, k:&str, zero:bool)->Result<u64,String>{ let s=m.get(k).ok_or(format!("missing {k}"))?; if s.is_empty() || !s.bytes().all(|b|b.is_ascii_digit()){return Err(format!("bad {k}"));} let n=s.parse::<u64>().map_err(|_|format!("bad {k}"))?; if !zero && n==0{return Err(format!("bad {k}"));} Ok(n) }
fn config()->Result<Config,String>{
 let a:Vec<String>=env::args().collect(); let i=a.iter().position(|x|x=="--config").ok_or("missing --config".to_string())?; if i+1>=a.len(){return Err("missing config path".into());}
 let text=fs::read_to_string(&a[i+1]).map_err(|e|e.to_string())?; let keys=["listen","root","max_connections","header_bytes","header_timeout_ms","idle_timeout_ms","write_timeout_ms","max_requests","pipeline_depth"];
 let mut m=HashMap::new(); for (ln,line) in text.lines().enumerate(){let line=line.trim(); if line.is_empty()||line.starts_with('#'){continue;} let (k,v)=line.split_once('=').ok_or(format!("line {} malformed",ln+1))?; let k=k.trim();let v=v.trim(); if !keys.contains(&k){return Err(format!("unknown key {k}"));} if v.is_empty()||m.insert(k.to_string(),v.to_string()).is_some(){return Err(format!("duplicate/empty {k}"));}}
 if m.len()!=keys.len(){return Err("missing config key".into());}
 let addr=m["listen"].parse::<SocketAddr>().map_err(|_|"invalid listen".to_string())?;
 let rp=PathBuf::from(&m["root"]); if !rp.is_absolute()||!rp.is_dir(){return Err("invalid root".into());} let root=fs::canonicalize(rp).map_err(|e|e.to_string())?;
 Ok(Config{listen:addr,root,max_conn:parse_num(&m,"max_connections",false)? as usize,header_bytes:parse_num(&m,"header_bytes",false)? as usize,header_ms:parse_num(&m,"header_timeout_ms",false)?,idle_ms:parse_num(&m,"idle_timeout_ms",false)?,write_ms:parse_num(&m,"write_timeout_ms",false)?,max_req:parse_num(&m,"max_requests",false)? as usize,pipeline:parse_num(&m,"pipeline_depth",false)? as usize})
}
fn token(b:u8)->bool { b.is_ascii_alphanumeric() || b"!#$%&'*+-.^_`|~".contains(&b) }
struct Req { method:String, target:String, close:bool }
fn parse_req(raw:&[u8])->Result<Req,u16>{
 if raw.iter().any(|&b|b==0)||!raw.ends_with(b"\r\n\r\n"){return Err(400)}
 let s=std::str::from_utf8(raw).map_err(|_|400u16)?; let mut lines=s[..s.len()-4].split("\r\n"); let line=lines.next().ok_or(400u16)?;
 let p:Vec<&str>=line.split(' ').collect(); if p.len()!=3||p.iter().any(|x|x.is_empty())||p[0].bytes().any(|b|!token(b)){return Err(400)}
 let v11=match p[2]{"HTTP/1.1"=>true,"HTTP/1.0"=>false,_=>return Err(400)};
 let mut cl=0; let mut conn_close=false; let mut conn_keep=false;
 for l in lines { if l.is_empty()||l.starts_with(' ')||l.starts_with('\t'){return Err(400)} let (n,v)=l.split_once(':').ok_or(400u16)?; if n.is_empty()||!n.bytes().all(token){return Err(400)} if v.bytes().any(|b|(b<32&&b!=9)||b==127){return Err(400)} let name=n.to_ascii_lowercase(); let val=v.trim_matches([' ','\t']);
   if name=="transfer-encoding" {return Err(400)} if name=="content-length" {cl+=1;if cl>1||!val.bytes().all(|b|b.is_ascii_digit())||val.is_empty()||val.parse::<u64>().unwrap_or(1)!=0{return Err(400)}}
   if name=="connection" {for t in val.split(','){if t.trim().eq_ignore_ascii_case("close"){conn_close=true} if t.trim().eq_ignore_ascii_case("keep-alive"){conn_keep=true}}}
 }
 let close=conn_close||(!v11&&!conn_keep); Ok(Req{method:p[0].to_string(),target:p[1].to_string(),close})
}
fn status_text(s:u16)->&'static str{match s{200=>"OK",400=>"Bad Request",403=>"Forbidden",404=>"Not Found",405=>"Method Not Allowed",408=>"Request Timeout",431=>"Request Header Fields Too Large",_=>"Error"}}
fn send_error(stream:&mut TcpStream,s:u16,_head:bool)->io::Result<()>{ write!(stream,"HTTP/1.1 {} {}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n",s,status_text(s))?; stream.flush() }
fn decode_path(target:&str)->Result<(String,bool),u16>{
 if !target.starts_with('/')||target.starts_with("//")||target.contains('#'){return Err(400)}
 let raw=target.split('?').next().unwrap_or(""); let mut bytes=Vec::new(); let b=raw.as_bytes(); let mut i=0;
 while i<b.len(){if b[i]==b'%'{if i+2>=b.len(){return Err(400)} let h=(b[i+1] as char).to_digit(16).ok_or(400u16)?;let l=(b[i+2] as char).to_digit(16).ok_or(400u16)?;bytes.push(((h<<4)|l) as u8);i+=3;}else{bytes.push(b[i]);i+=1;}}
 let decoded=String::from_utf8(bytes).map_err(|_|400u16)?; if decoded.contains('\0')||decoded.contains('\\'){return Err(400)}
 for c in decoded.split('/'){if c==".."{return Err(403)}} Ok((decoded,raw.ends_with('/')))
}
fn resolve(root:&Path,path:&str,trailing:bool)->Result<File,u16>{
 let mut cur=root.to_path_buf(); let components:Vec<&str>=path.split('/').filter(|x|!x.is_empty()).collect();
 if components.is_empty(){return Err(403)}
 for (i,c) in components.iter().enumerate(){if *c=="."{continue} cur.push(c);
   let md=match fs::symlink_metadata(&cur){Ok(m)=>m,Err(e)=>return Err(if e.kind()==io::ErrorKind::NotFound{404}else{403})};
   if md.file_type().is_symlink(){return Err(403)}
   if i+1<components.len() && !md.is_dir(){return Err(404)}
   if i+1==components.len(){if trailing||!md.is_file(){return Err(403)} }
 }
 let real=fs::canonicalize(&cur).map_err(|_|403u16)?; if !real.starts_with(root){return Err(403)}
 File::open(real).map_err(|e|if e.kind()==io::ErrorKind::NotFound{404}else{403})
}
fn serve_one(st:&mut TcpStream, cfg:&Config, req:Req, count:usize)->io::Result<bool>{
 let head=req.method=="HEAD";
 if req.method!="GET"&&!head {send_error(st,405,false)?;return Ok(false)}
 let (path,trailing)=match decode_path(&req.target){Ok(x)=>x,Err(code)=>{send_error(st,code,head)?;return Ok(false)}};
 let mut file=match resolve(&cfg.root,&path,trailing){Ok(f)=>f,Err(code)=>{send_error(st,code,head)?;return Ok(false)}};
 let size=file.metadata()?.len();
 let keep=!req.close&&count<cfg.max_req;
 write!(st,"HTTP/1.1 200 OK\r\nContent-Length: {}\r\nContent-Type: application/octet-stream\r\nConnection: {}\r\n\r\n",size,if keep{"keep-alive"}else{"close"})?;
 if !head { let mut left=size; let mut buf=[0u8;65536]; while left>0 {let take=std::cmp::min(buf.len(),left as usize);let n=file.read(&mut buf[..take])?;if n==0{break} st.write_all(&buf[..n])?;left-=n as u64;} }
 st.flush()?; Ok(keep)
}
fn handle(mut stream:TcpStream,cfg:Arc<Config>){
 let _=stream.set_nodelay(true);let mut buf=Vec::<u8>::with_capacity(cfg.header_bytes+4096);let mut requests=0usize;let mut pending_started:Option<Instant>=None;
 loop {
   if requests>=cfg.max_req{break;}
   let end=buf.windows(4).position(|w|w==b"\r\n\r\n").map(|x|x+4);
   if let Some(n)=end {
      if n>cfg.header_bytes {let _=send_error(&mut stream,431,false);break;}
      let raw:Vec<u8>=buf.drain(..n).collect();pending_started=if buf.is_empty(){None}else{Some(Instant::now())};
      let req=match parse_req(&raw){Ok(r)=>r,Err(code)=>{let _=send_error(&mut stream,code,false);break}};
      requests+=1; let _=stream.set_write_timeout(Some(Duration::from_millis(cfg.write_ms)));
      match serve_one(&mut stream,&cfg,req,requests){Ok(true)=>{},_=>break}
      continue
   }
   if buf.iter().enumerate().any(|(i,&b)|b==b'\n'&&(i==0||buf[i-1]!=b'\r')) || buf.iter().enumerate().any(|(i,&b)|b==b'\r'&&i+1<buf.len()&&buf[i+1]!=b'\n') {let _=send_error(&mut stream,400,false);break;}
   if buf.len()>cfg.header_bytes {let _=send_error(&mut stream,431,false);break;}
   let deadline=if let Some(t)=pending_started {t+Duration::from_millis(cfg.header_ms)} else if buf.is_empty(){Instant::now()+Duration::from_millis(cfg.idle_ms)} else {let t=Instant::now();pending_started=Some(t);t+Duration::from_millis(cfg.header_ms)};
   let now=Instant::now(); if now>=deadline {if !buf.is_empty(){let _=send_error(&mut stream,408,false);}break;}
   let rem=deadline-now; let _=stream.set_read_timeout(Some(rem));
   let maxread=(cfg.header_bytes+4096).saturating_sub(buf.len()).min(4096).max(1); let mut tmp=[0u8;4096];
   match stream.read(&mut tmp[..maxread]) {Ok(0)=>break,Ok(n)=>{if buf.is_empty(){pending_started=Some(Instant::now())} buf.extend_from_slice(&tmp[..n]);},Err(e) if e.kind()==io::ErrorKind::Interrupted=>continue,Err(e) if e.kind()==io::ErrorKind::WouldBlock||e.kind()==io::ErrorKind::TimedOut=>{if !buf.is_empty()&&Instant::now()>=deadline{let _=send_error(&mut stream,408,false);}break},Err(_)=>break}
 }
}
fn main(){
 let cfg=match config(){Ok(c)=>c,Err(e)=>{eprintln!("configuration: {e}");std::process::exit(2)}};
 let listener=match TcpListener::bind(cfg.listen){Ok(l)=>l,Err(e)=>{eprintln!("listen: {e}");std::process::exit(2)}};
 let cfg=Arc::new(cfg);let active=Arc::new(AtomicUsize::new(0));
 for incoming in listener.incoming(){match incoming{Ok(s)=>{let n=active.fetch_add(1,Ordering::AcqRel);if n>=cfg.max_conn{active.fetch_sub(1,Ordering::AcqRel);drop(s);continue}let c=cfg.clone();let a=active.clone();let result=thread::Builder::new().stack_size(128*1024).spawn(move||{handle(s,c);a.fetch_sub(1,Ordering::AcqRel);});if result.is_err(){active.fetch_sub(1,Ordering::AcqRel);}},Err(e)=>{eprintln!("accept: {e}");}}}
}
