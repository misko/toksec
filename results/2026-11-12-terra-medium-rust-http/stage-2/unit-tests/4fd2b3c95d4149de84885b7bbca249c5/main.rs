fn token(c:u8)->bool {c.is_ascii_alphanumeric()||b"!#$%&'*+-.^_`|~".contains(&c)}
fn hdr(raw:&[u8])->Result<bool,u16>{
 let mut lines=raw.split(|b|*b==b'\n');let request=lines.next().ok_or(400u16)?.strip_suffix(b"\r").ok_or(400u16)?;std::str::from_utf8(request).map_err(|_|400u16)?;
 let mut close=false;let mut cl=false;
 for line in lines {if line.is_empty(){continue}let l=line.strip_suffix(b"\r").ok_or(400u16)?;if l.is_empty(){continue}let colon=l.iter().position(|b|*b==b':').ok_or(400u16)?;let(name,v0)=l.split_at(colon);let val=&v0[1..];if name.is_empty()||!name.iter().copied().all(token)||val.iter().any(|b|*b==127||(*b<32&&*b!=b'\t')){return Err(400)}
 if name.eq_ignore_ascii_case(b"transfer-encoding"){return Err(400)}
 if name.eq_ignore_ascii_case(b"content-length"){if cl{return Err(400)}cl=true;let v=val.trim_ascii();if v.is_empty()||!v.iter().all(|b|*b==b'0'){return Err(400)}}
 if name.eq_ignore_ascii_case(b"connection"){for t in val.split(|b|*b==b','){if t.trim_ascii().eq_ignore_ascii_case(b"close"){close=true}}}
 }
 Ok(close)
}
#[test] fn obs_text(){let x=b"GET /hello.txt HTTP/1.1\r\nX: \xff\x80\r\n\r\n";assert!(std::str::from_utf8(x).is_err());assert_eq!(hdr(x),Ok(false));}
#[test] fn framing(){assert_eq!(hdr(b"GET / HTTP/1.1\r\nContent-Length: 000\r\n\r\n"),Ok(false));for x in [b"GET / HTTP/1.1\r\nContent-Length: 0\r\nContent-Length: 0\r\n\r\n".as_slice(),b"GET / HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n",b"GET / HTTP/1.1\r\nContent-Length: 1\r\n\r\n"]{assert_eq!(hdr(x),Err(400));}}
#[test] fn names_and_values(){for x in [b"GET / HTTP/1.1\r\n X: a\r\n\r\n".as_slice(),b"GET / HTTP/1.1\r\nX: \x01\r\n\r\n",b"GET / HTTP/1.1\r\nX\x80: a\r\n\r\n"]{assert_eq!(hdr(x),Err(400));}assert_eq!(hdr(b"GET / HTTP/1.1\r\nConnection: KEEP-ALIVE, ClOsE\r\n\r\n"),Ok(true));}