fn token(c:u8)->bool { c.is_ascii_alphanumeric()||b"!#$%&'*+-.^_`|~".contains(&c) }
fn hex(c:u8)->Option<u8>{match c {b'0'..=b'9'=>Some(c-b'0'),b'a'..=b'f'=>Some(c-b'a'+10),b'A'..=b'F'=>Some(c-b'A'+10),_=>None}}
fn parse(buf:&[u8])->Result<Vec<u8>,u16>{
 let mut lines=buf[..buf.len()-4].split(|&b|b==b'\n');
 let line=lines.next().ok_or(400u16)?; let line=line.strip_suffix(b"\r").unwrap_or(line);
 let parts:Vec<&[u8]>=line.split(|&b|b==b' ').collect(); if parts.len()!=3||parts[0].is_empty()||!parts[0].iter().copied().all(token)||parts[1].is_empty()||!(parts[2]==b"HTTP/1.0"||parts[2]==b"HTTP/1.1"){return Err(400)}
 let target=parts[1]; if target[0]!=b'/' || target.iter().any(|&b|b==b'#'||b==0||b==b'\\'||b<=32||b==127){return Err(400)}
 let mut seen=false;
 for line in lines { let line=line.strip_suffix(b"\r").unwrap_or(line); if line.is_empty(){return Err(400)} let i=line.iter().position(|&c|c==b':').ok_or(400u16)?; if i==0||!line[..i].iter().copied().all(token){return Err(400)} let name=&line[..i];let value=&line[i+1..]; if value.iter().any(|&b|(b<32&&b!=b'\t')||b==127){return Err(400)}
 if name.eq_ignore_ascii_case(b"transfer-encoding"){return Err(400)} if name.eq_ignore_ascii_case(b"content-length"){if seen{return Err(400)}seen=true;let v=value.trim_ascii();if v.is_empty()||!v.iter().all(|&c|c==b'0'){return Err(400)}} }
 let p=target.split(|&b|b==b'?').next().unwrap(); let mut out=Vec::with_capacity(p.len());let mut i=0;while i<p.len(){let c=if p[i]==b'%' {if i+2>=p.len(){return Err(400)}let h=hex(p[i+1]).ok_or(400u16)?;let l=hex(p[i+2]).ok_or(400u16)?;i+=3;h*16+l}else{let c=p[i];i+=1;c};if c==0||c==b'\\'{return Err(400)}out.push(c)}if std::str::from_utf8(&out).is_err(){return Err(400)}
 if parts[0]!=b"GET"{return Err(405)} if out.split(|&c|c==b'/').any(|c|c==b".."){return Err(403)} Ok(out)
}
fn checked(b:&[u8])->Result<Vec<u8>,u16>{assert!(b.ends_with(b"\r\n\r\n"));for j in 0..b.len(){if b[j]==0||(b[j]==b'\n'&&(j==0||b[j-1]!=b'\r'))||(b[j]==b'\r'&&j+1<b.len()&&b[j+1]!=b'\n'){return Err(400)}}parse(b)}
#[test] fn no_host(){assert_eq!(checked(b"GET /hello.txt HTTP/1.0\r\n\r\n"),Ok(b"/hello.txt".to_vec()));assert_eq!(checked(b"GET /hello.txt HTTP/1.1\r\n\r\n"),Ok(b"/hello.txt".to_vec()));assert_eq!(checked(b"POST /hello.txt HTTP/1.1\r\n\r\n"),Err(405));}
#[test] fn normal_and_bad_lines(){assert_eq!(checked(b"GET /hello.txt HTTP/1.1\r\nX: a\r\n\r\n"),Ok(b"/hello.txt".to_vec()));assert_eq!(checked(b"GET /hello.txt HTTP/1.1\nX: a\r\n\r\n"),Err(400));assert_eq!(checked(b"GET /hello.txt HTTP/1.1\r\n X: a\r\n\r\n"),Err(400));assert_eq!(checked(b"GET / HTTP/1.1\rX: a\r\n\r\n"),Err(400));}
#[test] fn framing(){assert_eq!(checked(b"GET / HTTP/1.1\r\nContent-Length: 000\r\n\r\n"),Ok(b"/".to_vec()));assert_eq!(checked(b"GET / HTTP/1.1\r\nContent-Length: 0\r\nContent-Length: 0\r\n\r\n"),Err(400));assert_eq!(checked(b"GET / HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n"),Err(400));}