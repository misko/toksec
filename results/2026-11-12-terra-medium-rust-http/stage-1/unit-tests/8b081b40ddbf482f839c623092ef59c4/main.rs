use std::sync::{Arc,atomic::{AtomicBool,Ordering}};
use std::thread;use std::time::Duration;
fn vmsize()->usize{let s=std::fs::read_to_string("/proc/self/status").unwrap();s.lines().find(|s|s.starts_with("VmSize:")).unwrap().split_whitespace().nth(1).unwrap().parse().unwrap()}
#[test] fn measure_stalled_threads() {
 let done=Arc::new(AtomicBool::new(false)); let mut handles=Vec::with_capacity(1024);let base=vmsize();let mut snap=0;let mut failure=String::new();
 for i in 0..1024{let stop=done.clone();match thread::Builder::new().stack_size(131072).spawn(move||{while !stop.load(Ordering::Relaxed){thread::sleep(Duration::from_millis(5));}}){Ok(h)=>handles.push(h),Err(e)=>{failure=format!("{} at {}",e,i);break}}if i==255 {snap=vmsize();}}
 let peak=vmsize();let n=handles.len();done.store(true,Ordering::Relaxed);for h in handles{h.join().unwrap()}
 assert!(n==usize::MAX,"observed threads={n} baseline_kib={base} at256_kib={snap} final_kib={peak} failure={failure}");
}
