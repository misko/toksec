use std::io::{self,Write};use std::net::{TcpListener,TcpStream,Shutdown};use std::os::fd::AsRawFd;
#[repr(C,packed)] #[derive(Clone,Copy)] struct E{ev:u32,data:u64}
unsafe extern "C"{fn epoll_create1(flags:i32)->i32;fn epoll_ctl(ep:i32,op:i32,fd:i32,e:*mut E)->i32;fn epoll_wait(ep:i32,e:*mut E,n:i32,ms:i32)->i32;fn close(fd:i32)->i32;}
#[test] fn write_mode_half_close(){
 let l=TcpListener::bind("127.0.0.1:0").unwrap();let client=TcpStream::connect(l.local_addr().unwrap()).unwrap();let(mut server,_)=l.accept().unwrap();server.set_nonblocking(true).unwrap();client.shutdown(Shutdown::Write).unwrap();
 let block=[0u8;65536];let mut total=0;loop{match server.write(&block){Ok(0)=>panic!("EOF"),Ok(n)=>{total+=n;assert!(total<64*1024*1024)},Err(e) if e.kind()==io::ErrorKind::WouldBlock=>break,Err(e)=>panic!("{e}")}}
 let ep=unsafe{epoll_create1(0)};assert!(ep>=0);let fd=server.as_raw_fd();let mut e=E{ev:4|0x2000,data:1};assert_eq!(unsafe{epoll_ctl(ep,1,fd,&mut e)},0);let mut got=[E{ev:0,data:0};1];for _ in 0..3{assert_eq!(unsafe{epoll_wait(ep,got.as_mut_ptr(),1,100)},1);let f=got[0].ev;assert_ne!(f&0x2000,0);}
 e.ev=4;assert_eq!(unsafe{epoll_ctl(ep,3,fd,&mut e)},0);let result=unsafe{epoll_wait(ep,got.as_mut_ptr(),1,20)};unsafe{close(ep)};assert_eq!(result,0,"socket unexpectedly writable after filling");
}