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
fn request(path:&str,fields:&str)->Vec<u8>{format!("GET {path} HTTP/1.1\r\nHost: x\r\n{fields}\r\n").into_bytes()}
#[test] fn path_boundaries(){for p in ["/%2f..%2fsecret", "/.%2e/x", "/a/%2e%2e/x", "/%2E%2E", "//../x"] {assert_eq!(parse(&request(p,"")),Err(403),"{p}");} for p in ["/%c0%af", "/%ed%a0%80", "/%f4%90%80%80", "/%00", "/%5c", "/%", "/%0g"] {assert_eq!(parse(&request(p,"")),Err(400),"{p}");} assert_eq!(parse(&request("/%252e%252e/x?query=1", "")).unwrap(),b"/%2e%2e/x");assert_eq!(parse(&request("/hello?x=%00", "")).unwrap(),b"/hello");}
#[test] fn length_boundaries(){for len in ["", "1", "0001", "+0", "-0", "0x0", "0,0", "18446744073709551616"] {assert_eq!(parse(&request("/hello",&format!("Content-Length: {len}\r\n"))),Err(400),"{len}");} for len in ["0", "000", "0000000000000000000000000000000000000000"] {assert_eq!(parse(&request("/hello",&format!("Content-Length: {len}\r\n"))).unwrap(),b"/hello");}assert_eq!(parse(&request("/hello","Content-Length: 0\r\ncOnTeNt-LeNgTh: 0\r\n")),Err(400));assert_eq!(parse(&request("/hello","tRaNsFeR-EnCoDiNg: identity\r\n")),Err(400));}
