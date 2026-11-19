// Host test fixture for the ordinary smoke surface only, NOT a stage solution.
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::collections::HashMap;
fn header(s: &mut TcpStream) -> Option<String> {
    let mut raw=Vec::new();
    while !raw.ends_with(b"\r\n\r\n") {
        let mut byte=[0u8];
        if s.read_exact(&mut byte).is_err() || raw.len()>16384 {return None;}
        raw.push(byte[0]);
    }
    String::from_utf8(raw).ok()
}
fn main() {
    let listener=TcpListener::bind("127.0.0.1:8080").unwrap();
    let mut cache: HashMap<String,Vec<u8>>=HashMap::new();
    for incoming in listener.incoming() {
        let mut s=incoming.unwrap();
        while let Some(raw)=header(&mut s) {
            let words:Vec<_>=raw.split_whitespace().collect();
            let path=words[1];
            let close=raw.contains("Connection: close");
            let body=if path.starts_with("/proxy/") {
                if let Some(body)=cache.get(path) {body.clone()} else {
                    let mut up=TcpStream::connect("127.0.0.1:8081").unwrap();
                    write!(up,"GET /{} HTTP/1.1\r\nHost: upstream\r\n\r\n",&path[7..]).unwrap();
                    let hdr=header(&mut up).unwrap();
                    let size:usize=hdr.lines().find_map(|line|line.strip_prefix("Content-Length: ")).unwrap().trim().parse().unwrap();
                    let mut body=vec![0;size]; up.read_exact(&mut body).unwrap();
                    if path=="/proxy/counter" {cache.insert(path.to_string(),body.clone());}
                    body
                }
            } else if raw.contains("Host: beta.test") {b"beta toksec\n".to_vec()}
            else {b"hello toksec\n".to_vec()};
            write!(s,"HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: {}\r\n\r\n",body.len(),if close {"close"} else {"keep-alive"}).unwrap();
            if words[0]!="HEAD" {s.write_all(&body).unwrap();}
            if close {break;}
        }
    }
}
