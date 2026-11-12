use std::io::{self,Read,Write};
use std::net::{TcpListener,TcpStream,Shutdown};
use std::time::Duration;
fn retained_read(s:&mut TcpStream,buf:&mut Vec<u8>)->bool {
 let mut temp=[0u8;8192]; loop { let cap=8193usize.saturating_sub(buf.len()).min(temp.len()); if cap==0 {break} match s.read(&mut temp[..cap]) { Ok(0)=>{if buf.is_empty(){return false} break}, Ok(n)=>{buf.extend_from_slice(&temp[..n]);}, Err(e) if e.kind()==io::ErrorKind::WouldBlock=>break, Err(e) if e.kind()==io::ErrorKind::Interrupted=>continue, Err(_)=>return false } } true
}
fn fixed_read(s:&mut TcpStream,buf:&mut Vec<u8>)->bool {
 let mut temp=[0u8;8192]; loop { let cap=8193usize.saturating_sub(buf.len()).min(temp.len()); if cap==0 {break} match s.read(&mut temp[..cap]) { Ok(0)=>return false, Ok(n)=>{buf.extend_from_slice(&temp[..n]);}, Err(e) if e.kind()==io::ErrorKind::WouldBlock=>break, Err(e) if e.kind()==io::ErrorKind::Interrupted=>continue, Err(_)=>return false } } true
}
fn setup()->(TcpStream,TcpStream) { let l=TcpListener::bind("127.0.0.1:0").unwrap();let mut client=TcpStream::connect(l.local_addr().unwrap()).unwrap();let (server,_)=l.accept().unwrap();client.write_all(b"GET /incomplete").unwrap();client.shutdown(Shutdown::Write).unwrap();server.set_read_timeout(Some(Duration::from_secs(1))).unwrap(); (client,server) }
#[test] fn retained_eof_keeps_connection_alive() { let (_peer,mut s)=setup();let mut buf=vec![];assert!(retained_read(&mut s,&mut buf));assert_eq!(buf,b"GET /incomplete");assert!(retained_read(&mut s,&mut buf)); }
#[test] fn corrected_eof_closes_connection() { let (_peer,mut s)=setup();let mut buf=vec![];assert!(!fixed_read(&mut s,&mut buf));assert_eq!(buf,b"GET /incomplete"); }
