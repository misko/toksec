use std::fs::{self,File}; use std::io::{self,Read}; use std::os::fd::{AsRawFd,FromRawFd}; use std::ffi::CString; use std::os::raw::{c_char,c_int};
extern "C" { fn openat(dirfd:c_int, pathname:*const c_char, flags:c_int, ...) -> c_int; fn mkfifo(path:*const c_char, mode:u32)->c_int; }
const O_CLOEXEC:i32=0x80000; const O_NOFOLLOW:i32=0x20000; const O_NONBLOCK:i32=0x800; const O_PATH:i32=0x200000;
fn open_path(root:&File,path:&[u8])->Result<File,u16>{
 if path.ends_with(b"/") {return Err(403)}
 let parts:Vec<&[u8]>=path.split(|&c|c==b'/').filter(|s|!s.is_empty()&&*s!=b".").collect();if parts.is_empty(){return Err(403)}
 let mut cur:Option<File>=None;for (i,part) in parts.iter().enumerate(){let c=CString::new(*part).map_err(|_|400u16)?;let fd=unsafe{openat(cur.as_ref().unwrap_or(root).as_raw_fd(),c.as_ptr(),O_CLOEXEC|O_NOFOLLOW|if i+1==parts.len(){O_NONBLOCK}else{O_PATH})};if fd<0{let e=io::Error::last_os_error().raw_os_error().unwrap_or(0);return Err(if e==2{404}else{403})}let f=unsafe{File::from_raw_fd(fd)};let m=f.metadata().map_err(|_|403u16)?;if i+1==parts.len(){if !m.is_file(){return Err(403)}return Ok(f)}else{if m.file_type().is_symlink()||!m.is_dir(){return Err(403)}cur=Some(f)}} Err(404)
}
#[test] fn confine_and_do_not_leak(){
 use std::os::unix::fs::symlink; use std::os::unix::ffi::OsStrExt;
 let base=std::env::temp_dir().join(format!("confine-{}",std::process::id()));let _=fs::remove_dir_all(&base);fs::create_dir_all(base.join("root/dir")).unwrap();fs::write(base.join("root/dir/good"),b"good").unwrap();fs::write(base.join("secret"),b"secret").unwrap();symlink("../secret",base.join("root/escape")).unwrap();symlink("dir",base.join("root/linkdir")).unwrap();symlink("../secret",base.join("root/dir/link")).unwrap();let fifo=CString::new(base.join("root/fifo").as_os_str().as_bytes()).unwrap();assert_eq!(unsafe{mkfifo(fifo.as_ptr(),0o600)},0);let root=File::open(base.join("root")).unwrap();let before=fs::read_dir("/proc/self/fd").unwrap().count();
 for _ in 0..1000 {let mut f=open_path(&root,b"/dir/good").unwrap();let mut b=Vec::new();f.read_to_end(&mut b).unwrap();assert_eq!(b,b"good");drop(f);for p in [&b"/escape"[..],b"/linkdir/good",b"/dir/link",b"/dir",b"/fifo",b"/dir/good/"]{assert_eq!(open_path(&root,p).err(),Some(403));}assert_eq!(open_path(&root,b"/dir/missing").err(),Some(404));assert_eq!(open_path(&root,b"/dir/x\0y").err(),Some(400));}
 let after=fs::read_dir("/proc/self/fd").unwrap().count();assert_eq!(after,before);drop(root);fs::remove_dir_all(base).unwrap();}
