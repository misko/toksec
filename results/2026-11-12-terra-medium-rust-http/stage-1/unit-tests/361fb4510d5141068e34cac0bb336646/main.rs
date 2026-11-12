use std::sync::{Arc,atomic::{AtomicBool,Ordering}};
use std::thread;
use std::time::Duration;
#[test] fn bounded_thread_creation_and_recovery() {
 let done=Arc::new(AtomicBool::new(false)); let mut handles=Vec::new(); let mut failure=None;
 for i in 0..4096 {let stop=done.clone();match thread::Builder::new().stack_size(131072).spawn(move||{while !stop.load(Ordering::Relaxed){thread::sleep(Duration::from_millis(5));}}){Ok(h)=>handles.push(h),Err(e)=>{failure=Some((i,e.to_string()));break}}}
 eprintln!("started={} failure={:?}",handles.len(),failure); assert!(!handles.is_empty());done.store(true,Ordering::Relaxed);for h in handles{h.join().unwrap()}
 let h=thread::Builder::new().stack_size(131072).spawn(|| 42).unwrap();assert_eq!(h.join().unwrap(),42);
}
