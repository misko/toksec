// Deliberately limited bootstrap: blocking, one request per connection, GET only.
// Complete the published contract before optimizing. Not a production HTTP parser.
use std::{env,fs,io::{Read,Write},net::TcpListener,path::{Path,Component},time::Duration};
fn main() {
    let args:Vec<_>=env::args().collect();
    assert!(args.len()==3 && args[1]=="--config");
    let config=fs::read_to_string(&args[2]).unwrap();
    let value=|key:&str| config.lines().find_map(|s|s.split_once('=').filter(|(k,_)|*k==key).map(|(_,v)|v.to_string())).unwrap();
    let root=fs::canonicalize(value("root")).unwrap();
    let listener=TcpListener::bind(value("listen")).unwrap();
    for incoming in listener.incoming() {
        let Ok(mut stream)=incoming else {continue};
        let _=stream.set_read_timeout(Some(Duration::from_millis(500)));
        let _=stream.set_write_timeout(Some(Duration::from_millis(500)));
        let mut raw=Vec::new();
        while raw.len()<16384 && !raw.ends_with(b"\r\n\r\n") {
            let mut byte=[0]; if stream.read(&mut byte).unwrap_or(0)==0 {break} raw.push(byte[0]);
        }
        let text=String::from_utf8_lossy(&raw);
        let fields:Vec<_>=text.lines().next().unwrap_or("").split_whitespace().collect();
        let mut code=400;let mut body=Vec::new();
        if fields.len()==3 && fields[0]=="GET" && fields[1].starts_with('/') {
            let relative=Path::new(fields[1].split('?').next().unwrap().trim_start_matches('/'));
            if relative.components().any(|c| !matches!(c,Component::Normal(_))) {code=403}
            else {
                let mut path=root.clone();let mut valid=true;
                for c in relative.components() {path.push(c); if fs::symlink_metadata(&path).map(|m|m.file_type().is_symlink()).unwrap_or(false){valid=false;break}}
                if !valid {code=403}
                else if path.is_file() {match fs::read(path){Ok(data)=>{code=200;body=data},Err(_)=>code=404}}
                else {code=404}
            }
        }
        let _=write!(stream,"HTTP/1.1 {} Result\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",code,body.len());
        let _=stream.write_all(&body);
    }
}
