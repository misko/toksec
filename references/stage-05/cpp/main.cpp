#include <algorithm>
#include <array>
#include <cerrno>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <deque>
#include <fcntl.h>
#include <fstream>
#include <iostream>
#include <list>
#include <memory>
#include <netdb.h>
#include <netinet/tcp.h>
#include <optional>
#include <set>
#include <signal.h>
#include <sstream>
#include <string>
#include <string_view>
#include <sys/epoll.h>
#include <sys/sendfile.h>
#include <sys/signalfd.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <unistd.h>
#include <unordered_map>
#include <utility>
#include <vector>

using namespace std;
using Clock = chrono::steady_clock;
static uint64_t now_ms() { return chrono::duration_cast<chrono::milliseconds>(Clock::now().time_since_epoch()).count(); }
static string lower(string_view v) { string s(v); for (char &c:s) if(c>='A'&&c<='Z') c+=32; return s; }
static string trim(string_view v) { size_t a=0,b=v.size(); while(a<b&&(v[a]==' '||v[a]=='\t')) ++a; while(b>a&&(v[b-1]==' '||v[b-1]=='\t')) --b; return string(v.substr(a,b-a)); }
static bool number(string_view v,uint64_t &n) { if(v.empty()) return false; n=0; for(unsigned char c:v) { if(c<'0'||c>'9'||n>(UINT64_MAX-(c-'0'))/10) return false; n=n*10+c-'0'; } return true; }
static bool token(string_view s) { if(s.empty())return false; for(unsigned char c:s) if(!((c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||string_view("!#$%&'*+-.^_`|~").find(c)!=string_view::npos)) return false; return true; }
static bool utf8(string_view s) { size_t i=0; while(i<s.size()) { unsigned char a=s[i++]; if(a<128)continue; unsigned n; uint32_t cp,min; if(a>=0xc2&&a<=0xdf){n=1;cp=a&31;min=128;}else if(a>=0xe0&&a<=0xef){n=2;cp=a&15;min=2048;}else if(a>=0xf0&&a<=0xf4){n=3;cp=a&7;min=65536;}else return false; if(i+n>s.size())return false; while(n--){unsigned char b=s[i++]; if((b&192)!=128)return false; cp=(cp<<6)|(b&63);} if(cp<min||cp>0x10ffff||(cp>=0xd800&&cp<=0xdfff))return false; } return true; }
static vector<string> comma(string_view s) { vector<string> v; size_t p=0; do { size_t q=s.find(',',p); if(q==string_view::npos)q=s.size(); v.push_back(lower(trim(s.substr(p,q-p)))); p=q+1; } while(p<=s.size()); return v; }
using Headers=vector<pair<string,string>>;
static string field(const Headers& h,string_view n) { string r; bool found=false; for(auto& [k,v]:h)if(k==n){if(found)r+=",";r+=v;found=true;}return r; }
static int count_field(const Headers& h,string_view n) {int c=0;for(auto& p:h)c+=p.first==n;return c;}
static bool has_token(const Headers& h,string_view name,string_view val) {for(auto &v:comma(field(h,name)))if(v==val)return true;return false;}
static bool parse_header_line(string_view line,Headers& h) {size_t p=line.find(':');if(p==string_view::npos||!token(line.substr(0,p)))return false;for(unsigned char c:line)if(c==0||c=='\r'||c=='\n')return false;h.emplace_back(lower(line.substr(0,p)),trim(line.substr(p+1)));return true;}
static bool bad_lines(string_view s) {for(size_t i=0;i<s.size();++i){if(s[i]==0)return true;if(s[i]=='\n'&&(i==0||s[i-1]!='\r'))return true;if(s[i]=='\r'&&i+1<s.size()&&s[i+1]!='\n')return true;}return false;}
static bool chunk_extensions(string_view s,size_t p) {
 while(p<s.size()){
  while(p<s.size()&&(s[p]==' '||s[p]=='\t'))++p;
  if(p==s.size()||s[p++]!=';')return false;
  while(p<s.size()&&(s[p]==' '||s[p]=='\t'))++p;
  size_t a=p;while(p<s.size()&&token(s.substr(p,1)))++p;if(a==p)return false;
  while(p<s.size()&&(s[p]==' '||s[p]=='\t'))++p;
  if(p<s.size()&&s[p]=='='){
   ++p;while(p<s.size()&&(s[p]==' '||s[p]=='\t'))++p;if(p==s.size())return false;
   if(s[p]=='"'){++p;bool closed=false;while(p<s.size()){unsigned char c=s[p++];if(c=='"'){closed=true;break;}if(c=='\\'){if(p==s.size())return false;c=s[p++];if(c!='\t'&&(c<32||c==127))return false;}else if(c!='\t'&&(c<32||c==127))return false;}if(!closed)return false;}
   else{a=p;while(p<s.size()&&token(s.substr(p,1)))++p;if(a==p)return false;}
   while(p<s.size()&&(s[p]==' '||s[p]=='\t'))++p;
  }
  if(p<s.size()&&s[p]!=';')return false;
 }
 return true;
}

struct Address {sockaddr_storage sa{};socklen_t len=0;string authority;};
static optional<Address> address(string s) {size_t p=s.rfind(':');if(p==string::npos||p==0)return {};string host=s.substr(0,p),port=s.substr(p+1);uint64_t n;if(!number(port,n)||n==0||n>65535)return {};if(host.front()=='['&&host.back()==']')host=host.substr(1,host.size()-2);addrinfo hint{},*out=nullptr;hint.ai_socktype=SOCK_STREAM;hint.ai_family=AF_UNSPEC; if(getaddrinfo(host.c_str(),port.c_str(),&hint,&out))return {};Address a; a.authority=s;for(auto q=out;q;q=q->ai_next)if(q->ai_family==AF_INET||q->ai_family==AF_INET6){memcpy(&a.sa,q->ai_addr,q->ai_addrlen);a.len=q->ai_addrlen;break;}freeaddrinfo(out);if(!a.len)return {};return a;}
static bool hostname(string_view s) {if(s.empty())return false;for(unsigned char c:s)if(!((c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='-'||c=='.'))return false;return true;}
struct Dir {int fd=-1; explicit Dir(string const& s){fd=open(s.c_str(),O_RDONLY|O_DIRECTORY|O_CLOEXEC);}~Dir(){if(fd>=0)close(fd);}};
struct Config {
 string listen,root,default_host,host_name,host_path,alias_prefix,alias_path,redirect_path,redirect_to,index,proxy_prefix;
 Address binding;vector<Address> upstreams;shared_ptr<Dir> rootfd,hostfd,aliasfd;
 uint64_t max_connections,header_bytes,header_timeout_ms,idle_timeout_ms,write_timeout_ms,max_requests,pipeline_depth,upstream_timeout_ms,body_bytes,cache_ttl_ms,cache_bytes,rate_per_second,rate_burst,drain_timeout_ms;
};
static shared_ptr<Config> read_config(const string& path) {
 ifstream f(path);if(!f)return {};unordered_map<string,string> m;string s;
 while(getline(f,s)){if(!s.empty()&&s.back()=='\r')s.pop_back();s=trim(s);if(s.empty()||s[0]=='#')continue;if(!utf8(s)||s.find('\0')!=string::npos)return {};size_t p=s.find('=');if(p==string::npos)return {};string k=trim(string_view(s).substr(0,p)),v=trim(string_view(s).substr(p+1));if(!m.emplace(k,v).second)return {};}
 static const vector<string> keys={"listen","root","max_connections","header_bytes","header_timeout_ms","idle_timeout_ms","write_timeout_ms","max_requests","pipeline_depth","default_host","host_root","alias","redirect","index","proxy_prefix","upstreams","upstream_timeout_ms","body_bytes","cache_ttl_ms","cache_bytes","rate_per_second","rate_burst","drain_timeout_ms"};
 if(m.size()!=keys.size())return {};for(auto& k:keys)if(!m.count(k))return {};
 auto c=make_shared<Config>();auto num=[&](const char*k,uint64_t&n,bool zero=false){return number(m[k],n)&&(n||zero);};
 if(!num("max_connections",c->max_connections)||!num("header_bytes",c->header_bytes)||!num("header_timeout_ms",c->header_timeout_ms)||!num("idle_timeout_ms",c->idle_timeout_ms)||!num("write_timeout_ms",c->write_timeout_ms)||!num("max_requests",c->max_requests)||!num("pipeline_depth",c->pipeline_depth)||!num("upstream_timeout_ms",c->upstream_timeout_ms)||!num("body_bytes",c->body_bytes)||!num("cache_ttl_ms",c->cache_ttl_ms)||!num("cache_bytes",c->cache_bytes)||!num("rate_per_second",c->rate_per_second,true)||!num("rate_burst",c->rate_burst)||!num("drain_timeout_ms",c->drain_timeout_ms))return {};
 c->listen=m["listen"];auto bind=address(c->listen);if(!bind)return {};c->binding=*bind;c->root=m["root"];c->default_host=lower(m["default_host"]);if(!hostname(c->default_host))return {};
 auto split=[&](const char* k,string& a,string& b){size_t p=m[k].find(':');if(p==string::npos)return false;a=m[k].substr(0,p);b=m[k].substr(p+1);return !a.empty()&&!b.empty();};
 if(!split("host_root",c->host_name,c->host_path)||!hostname(c->host_name)||!split("alias",c->alias_prefix,c->alias_path)||!split("redirect",c->redirect_path,c->redirect_to))return {};
 c->host_name=lower(c->host_name);c->index=m["index"];c->proxy_prefix=m["proxy_prefix"];
 for(auto& p:{c->root,c->host_path,c->alias_path,c->alias_prefix,c->redirect_path,c->redirect_to,c->proxy_prefix})if(p.empty()||p[0]!='/'||p.find_first_of("\r\n")!=string::npos)return {};
 if(c->index.empty()||c->index=="."||c->index==".."||c->index.find_first_of("/\\\r\n")!=string::npos)return {};
 if(c->alias_prefix.back()!='/'||c->proxy_prefix.back()!='/')return {};
 c->rootfd=make_shared<Dir>(c->root);c->hostfd=make_shared<Dir>(c->host_path);c->aliasfd=make_shared<Dir>(c->alias_path);if(c->rootfd->fd<0||c->hostfd->fd<0||c->aliasfd->fd<0)return {};
 size_t p=0;do{size_t q=m["upstreams"].find(',',p);if(q==string::npos)q=m["upstreams"].size();auto a=address(trim(string_view(m["upstreams"]).substr(p,q-p)));if(!a)return {};c->upstreams.push_back(*a);p=q+1;}while(p<=m["upstreams"].size());return c;
}

struct Chunk {
 enum State{SIZE,DATA,CRLF,TRAILERS,DONE};State state=SIZE;uint64_t remaining=0;size_t trailer_bytes=0;
 // 0 means incomplete, 1 complete; 400 malformed, 413 decoded limit.
 int consume(string& in,string& body,uint64_t limit,uint64_t headerlimit) {
  for(;;){if(state==DONE)return 1;
   if(state==DATA){size_t n=min<uint64_t>(remaining,in.size());if(n){body.append(in.data(),n);in.erase(0,n);remaining-=n;}if(remaining)return 0;state=CRLF;}
   if(state==CRLF){if(in.size()>=1&&in[0]!='\r')return 400;if(in.size()<2)return 0;if(in[1]!='\n')return 400;in.erase(0,2);state=SIZE;}
   if(state==SIZE||state==TRAILERS){size_t p=in.find("\r\n");if(p==string::npos){if(in.size()>headerlimit||bad_lines(in))return 400;return 0;}string line=in.substr(0,p);if(bad_lines(line))return 400;in.erase(0,p+2);
    if(state==TRAILERS){trailer_bytes+=p+2;if(trailer_bytes>headerlimit)return 400;if(line.empty()){state=DONE;return 1;}Headers ignored;if(!parse_header_line(line,ignored))return 400;continue;}
    size_t end=line.find_first_of("; \t");if(end==string::npos)end=line.size();if(!end||!chunk_extensions(line,end))return 400;uint64_t n=0;for(size_t i=0;i<end;++i){unsigned char c=line[i];unsigned x;if(c>='0'&&c<='9')x=c-'0';else if(c>='a'&&c<='f')x=c-'a'+10;else if(c>='A'&&c<='F')x=c-'A'+10;else return 400;if(n>(UINT64_MAX-x)/16)return 400;n=n*16+x;}
    if(n>limit-body.size())return 413;remaining=n;state=n?DATA:TRAILERS;
   }
  }
 }
};
struct Request {string method,target,path,rawpath,query,host,body;Headers headers;bool head=false,persist=false,proxy=false,chunked=false;uint64_t length=0;Chunk chunk;shared_ptr<Config> cfg;};
struct Data {int status=200;Headers headers;shared_ptr<string> body=make_shared<string>();uint64_t length=0;};
struct Response {string header;size_t header_pos=0,body_pos=0;shared_ptr<string> body;int file=-1;off_t offset=0;uint64_t remaining=0;bool close=false;~Response(){if(file>=0)::close(file);}};
using Pending=list<pair<int,uint64_t>>;
struct Conn {int fd;uint64_t tag;string in;Request req;unique_ptr<Response> out;bool parsed=false,ending=false,queued=false,admitted=false;Pending::iterator waiting;uint64_t requests=0,first=0,last=0,write_last=0;int upstream=-1;unsigned attempts=0;};
struct Up {enum State{CONNECT,WRITE,HEADER,LENGTH,CHUNKS,IDLE};State state=CONNECT;int fd,client=-1;uint64_t tag,deadline=0,last=0;Address addr;string send,in,body;size_t send_pos=0;Headers headers;int status=200;bool chunked=false,keep=true;uint64_t length=0;Chunk chunk;};
struct CacheEntry {Data data;uint64_t expiry,metadata_bytes;list<string>::iterator lru;};

class Server {
 int ep=-1,listener=-1,sigfd=-1;uint32_t serial=1;string config_path;shared_ptr<Config> cfg;
 unordered_map<int,unique_ptr<Conn>> clients;unordered_map<int,unique_ptr<Up>> ups;unordered_map<string,vector<pair<int,uint64_t>>> pool;
 unordered_map<string,CacheEntry> cache;list<string> lru;uint64_t cache_used=0,cache_metadata=0,round_robin=0,next_scan=0;double tokens=0;uint64_t refill=0;bool draining=false;uint64_t drain_end=0;
 Pending pending;size_t admitted=0;bool pumping=false,stopping=false;static constexpr size_t proxy_slots=64;
 uint64_t tag(int fd){return (uint64_t(++serial)<<32)|uint32_t(fd);}
 void add(int fd,uint64_t t,uint32_t events){epoll_event e{};e.events=events;e.data.u64=t;epoll_ctl(ep,EPOLL_CTL_ADD,fd,&e);}
 void mod(int fd,uint64_t t,uint32_t events){epoll_event e{};e.events=events;e.data.u64=t;epoll_ctl(ep,EPOLL_CTL_MOD,fd,&e);}
 void interest(Conn& c){uint32_t ev=0;if(c.out)ev|=EPOLLOUT;else if(c.upstream<0&&!c.queued)ev|=EPOLLIN|EPOLLRDHUP;mod(c.fd,c.tag,ev);}
 void close_up(int fd){auto it=ups.find(fd);if(it==ups.end())return;epoll_ctl(ep,EPOLL_CTL_DEL,fd,nullptr);close(fd);ups.erase(it);}
 void release_slot(Conn& c){if(c.admitted){c.admitted=false;--admitted;}}
 void close_client(int fd){auto it=clients.find(fd);if(it==clients.end())return;auto&c=*it->second;if(c.queued)pending.erase(c.waiting);release_slot(c);if(c.upstream>=0)close_up(c.upstream);epoll_ctl(ep,EPOLL_CTL_DEL,fd,nullptr);close(fd);clients.erase(it);pump_upstreams();}
 static string reason(int s){switch(s){case 200:return "OK";case 206:return "Partial Content";case 301:return "Moved Permanently";case 302:return "Found";case 304:return "Not Modified";case 400:return "Bad Request";case 403:return "Forbidden";case 404:return "Not Found";case 405:return "Method Not Allowed";case 408:return "Request Timeout";case 413:return "Content Too Large";case 416:return "Range Not Satisfiable";case 429:return "Too Many Requests";case 431:return "Request Header Fields Too Large";case 502:return "Bad Gateway";case 504:return "Gateway Timeout";default:return "Response";}}
 void respond(Conn& c,int status,Headers headers={},shared_ptr<string> body={},uint64_t length=0,int file=-1,off_t offset=0,bool fatal=false){
  auto r=make_unique<Response>();auto conf=c.req.cfg?c.req.cfg:cfg;r->close=fatal||draining||!c.req.persist||c.requests>=conf->max_requests;
  r->header="HTTP/1.1 "+to_string(status)+" "+reason(status)+"\r\nContent-Length: "+to_string(length)+"\r\nConnection: "+(r->close?"close":"keep-alive")+"\r\n";
  for(auto& [k,v]:headers)r->header+=k+": "+v+"\r\n";r->header+="\r\n";
  if(!c.req.head){r->body=move(body);r->file=file;r->offset=offset;r->remaining=length;}else if(file>=0)close(file);
  c.out=move(r);c.write_last=now_ms();interest(c);
 }
 void error(Conn& c,int status,bool fatal=true){respond(c,status,{},nullptr,0,-1,0,fatal);}
 static int decode_path(Request& r){
  if(r.target.empty()||r.target[0]!='/'||r.target.find('#')!=string::npos)return 400;size_t p=r.target.find('?');r.rawpath=r.target.substr(0,p);r.query=p==string::npos?"":r.target.substr(p);
  auto hex=[](char c)->int{if(c>='0'&&c<='9')return c-'0';if(c>='a'&&c<='f')return c-'a'+10;if(c>='A'&&c<='F')return c-'A'+10;return -1;};
  for(size_t i=0;i<r.rawpath.size();++i){unsigned char c=r.rawpath[i];if(c=='%'){if(i+2>=r.rawpath.size())return 400;int a=hex(r.rawpath[i+1]),b=hex(r.rawpath[i+2]);if(a<0||b<0)return 400;c=a*16+b;i+=2;}if(c==0||c=='\\'||c<32||c==127)return 400;r.path+=char(c);}if(!utf8(r.path))return 400;
  size_t a=0;while(a<r.path.size()){size_t b=r.path.find('/',a);if(b==string::npos)b=r.path.size();if(r.path.substr(a,b-a)=="..")return 403;a=b+1;}return 0;
 }
 int parse_request(Conn& c,size_t end){
  Request& r=c.req;r.cfg=cfg;string_view raw(c.in.data(),end);if(bad_lines(raw))return 400;size_t lineend=raw.find("\r\n");if(lineend==string_view::npos)return 400;string_view line=raw.substr(0,lineend);size_t a=line.find(' '),b=a==string_view::npos?a:line.find(' ',a+1);
  if(a==string_view::npos||b==string_view::npos||a==0||b==a+1||line.find(' ',b+1)!=string_view::npos||!token(line.substr(0,a)))return 400;
  string_view version=line.substr(b+1);if(version!="HTTP/1.1"&&version!="HTTP/1.0")return 400;r.method=string(line.substr(0,a));r.head=r.method=="HEAD";r.target=string(line.substr(a+1,b-a-1));
  size_t pos=lineend+2;while(pos+2<end){size_t q=raw.find("\r\n",pos);if(q==string_view::npos)return 400;if(q==pos)break;if(!parse_header_line(raw.substr(pos,q-pos),r.headers))return 400;pos=q+2;}
  r.persist=version=="HTTP/1.1"&&!has_token(r.headers,"connection","close");
  int hosts=count_field(r.headers,"host");if(hosts>1||(version=="HTTP/1.1"&&hosts!=1))return 400;
  r.host=hosts?lower(field(r.headers,"host")):r.cfg->default_host;size_t colon=r.host.find(':');if(colon!=string::npos){uint64_t port;if(!number(string_view(r.host).substr(colon+1),port)||port>65535)return 400;r.host.resize(colon);}if(!hostname(r.host)||(r.host!=r.cfg->default_host&&r.host!=r.cfg->host_name))return 400;
  int d=decode_path(r);if(d)return d;r.proxy=r.path.rfind(r.cfg->proxy_prefix,0)==0;
  if(r.method!="GET"&&r.method!="HEAD"&&!(r.proxy&&r.method=="POST"))return 405;
  int cl=count_field(r.headers,"content-length"),te=count_field(r.headers,"transfer-encoding");if(cl>1||te>1||(cl&&te))return 400;if(cl&&!number(field(r.headers,"content-length"),r.length))return 400;
  if(!r.proxy){if(te||r.length)return 400;}else{if(te){if(lower(field(r.headers,"transfer-encoding"))!="chunked")return 400;r.chunked=true;}if(r.length>r.cfg->body_bytes)return 413;}
  return 0;
 }
 bool take_token(){if(!cfg->rate_per_second)return true;uint64_t now=now_ms();tokens=min<double>(cfg->rate_burst,tokens+double(now-refill)*cfg->rate_per_second/1000);refill=now;if(tokens>=1){tokens-=1;return true;}return false;}
 static set<string> hops(const Headers& h){set<string> n={"connection","keep-alive","proxy-connection","proxy-authenticate","proxy-authorization","te","trailer","transfer-encoding","upgrade"};for(auto& s:comma(field(h,"connection")))if(!s.empty())n.insert(s);return n;}
 string cache_key(const Request& r){return "http\n"+r.host+"\n"+r.target+"\n"+field(r.headers,"accept-encoding")+"\n"+field(r.headers,"range")+"\n"+field(r.headers,"if-none-match")+"\n"+field(r.headers,"if-modified-since");}
 void erase_cache(unordered_map<string,CacheEntry>::iterator it){cache_used-=it->second.data.body->size();cache_metadata-=it->second.metadata_bytes;lru.erase(it->second.lru);cache.erase(it);}
 bool cache_get(Conn& c){if(c.req.cfg!=cfg||c.req.length||c.req.chunked||(c.req.method!="GET"&&!c.req.head))return false;if(count_field(c.req.headers,"authorization"))return false;auto it=cache.find(cache_key(c.req));if(it==cache.end())return false;if(it->second.expiry<=now_ms()){erase_cache(it);return false;}lru.splice(lru.begin(),lru,it->second.lru);auto& d=it->second.data;respond(c,d.status,d.headers,d.body,d.length);return true;}
 // Bound active uploads, upstream connection attempts and buffered noncached
 // responses together. Waiting clients retain only their initial input fragment.
 void queue_proxy(Conn& c){c.queued=true;pending.emplace_back(c.fd,c.tag);c.waiting=prev(pending.end());interest(c);pump_upstreams();}
 void pump_upstreams(){if(pumping||stopping)return;pumping=true;while(admitted<proxy_slots&&!pending.empty()){auto [fd,t]=pending.front();pending.pop_front();auto it=clients.find(fd);if(it==clients.end()||it->second->tag!=t)continue;Conn&c=*it->second;c.queued=false;c.admitted=true;++admitted;process_client(fd);}pumping=false;}
 void cache_put(const Request& r,const Data& d){if(r.cfg!=cfg||r.method!="GET"||count_field(r.headers,"authorization")||d.status<200||d.status>=300||count_field(d.headers,"set-cookie"))return;
  bool pub=false,bypass=false;uint64_t age=0;bool gotage=false;for(auto& v:comma(field(d.headers,"cache-control"))){size_t p=v.find('=');string k=trim(string_view(v).substr(0,p));if(k=="public")pub=true;if(k=="private"||k=="no-store")bypass=true;if(k=="max-age"&&p!=string::npos){string z=trim(string_view(v).substr(p+1));if(z.size()>=2&&z[0]=='"'&&z.back()=='"')z=z.substr(1,z.size()-2);uint64_t a;if(number(z,a)){age=a;gotage=true;}else bypass=true;}}
  for(auto& v:comma(field(d.headers,"vary")))if(!v.empty()&&v!="accept-encoding")bypass=true;
  if(!pub||bypass||!gotage||!age||d.body->size()>cfg->cache_bytes)return;uint64_t ttl=age>UINT64_MAX/1000?UINT64_MAX:age*1000;ttl=min(ttl,cfg->cache_ttl_ms);if(!ttl)return;string key=cache_key(r);uint64_t metadata=512+2*key.size()+d.headers.capacity()*sizeof(pair<string,string>);for(auto&[k,v]:d.headers)metadata+=k.capacity()+v.capacity()+2;constexpr uint64_t metadata_limit=4*1024*1024;if(metadata>metadata_limit)return;auto old=cache.find(key);if(old!=cache.end())erase_cache(old);while((cache_used>cfg->cache_bytes-d.body->size()||cache_metadata>metadata_limit-metadata||cache.size()>=4096)&&!lru.empty())erase_cache(cache.find(lru.back()));lru.push_front(key);cache.emplace(key,CacheEntry{d,now_ms()+ttl,metadata,lru.begin()});cache_used+=d.body->size();cache_metadata+=metadata;
 }
 void local(Conn& c){Request& r=c.req;auto conf=r.cfg;if(r.path==conf->redirect_path){respond(c,302,{{"Location",conf->redirect_to}});return;}
  shared_ptr<Dir> root=r.host==conf->host_name?conf->hostfd:conf->rootfd;string path=r.path;if(path.rfind(conf->alias_prefix,0)==0){root=conf->aliasfd;path=path.substr(conf->alias_prefix.size());}
  int fd=dup(root->fd);if(fd<0){error(c,403,false);return;}struct stat st{};vector<string> parts;size_t a=0;while(a<path.size()){size_t b=path.find('/',a);if(b==string::npos)b=path.size();string p=path.substr(a,b-a);if(!p.empty()&&p!=".")parts.push_back(move(p));a=b+1;}
  for(auto& part:parts){struct stat lst{};if(fstatat(fd,part.c_str(),&lst,AT_SYMLINK_NOFOLLOW)<0){int e=errno;close(fd);error(c,e==ENOENT||e==ENOTDIR?404:403,false);return;}if(S_ISLNK(lst.st_mode)||(!S_ISREG(lst.st_mode)&&!S_ISDIR(lst.st_mode))){close(fd);error(c,403,false);return;}int next=openat(fd,part.c_str(),O_RDONLY|O_NONBLOCK|O_NOFOLLOW|O_CLOEXEC);int e=errno;close(fd);if(next<0){error(c,e==ENOENT?404:403,false);return;}fd=next;}
  if(fstat(fd,&st)<0){close(fd);error(c,403,false);return;}
  string selected=r.path;if(S_ISDIR(st.st_mode)){if(r.path.back()!='/'){close(fd);respond(c,301,{{"Location",r.rawpath+"/"+r.query}});return;}struct stat lst{};if(fstatat(fd,conf->index.c_str(),&lst,AT_SYMLINK_NOFOLLOW)<0||!S_ISREG(lst.st_mode)){close(fd);error(c,403,false);return;}int next=openat(fd,conf->index.c_str(),O_RDONLY|O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC);close(fd);if(next<0){error(c,403,false);return;}fd=next;if(fstat(fd,&st)<0){close(fd);error(c,403,false);return;}selected+=conf->index;
  }else if(!S_ISREG(st.st_mode)||(!r.path.empty()&&r.path.back()=='/')){close(fd);error(c,403,false);return;}
  if(!S_ISREG(st.st_mode)||st.st_size<0){close(fd);error(c,403,false);return;}
  uint64_t size=st.st_size;string mime="application/octet-stream";if(selected.ends_with(".txt"))mime="text/plain";else if(selected.ends_with(".html"))mime="text/html";
  string etag="\""+to_string(st.st_dev)+"-"+to_string(st.st_ino)+"-"+to_string(size)+"-"+to_string(st.st_mtim.tv_sec)+"-"+to_string(st.st_mtim.tv_nsec)+"\"";Headers h={{"Content-Type",mime},{"ETag",etag}};
  bool match=false;for(auto& item:comma(field(r.headers,"if-none-match"))){string tag=item;if(tag.rfind("w/",0)==0)tag=tag.substr(2);if(tag=="*"||tag==lower(etag))match=true;}if(match){close(fd);respond(c,304,h);return;}
  uint64_t start=0,end=size?size-1:0;int status=200;
  if(count_field(r.headers,"range")){string range=field(r.headers,"range");bool invalid=false,unsat=false;if(range.rfind("bytes=",0)!=0||range.find(',')!=string::npos)invalid=true;else{string v=range.substr(6);size_t dash=v.find('-');if(dash==string::npos||v.find('-',dash+1)!=string::npos)invalid=true;else{string left=v.substr(0,dash),right=v.substr(dash+1);uint64_t l=0,n=0;if(left.empty()){if(!number(right,n))invalid=true;else if(n==0||size==0)unsat=true;else{start=n>=size?0:size-n;end=size-1;}}else if(!number(left,l)||(!right.empty()&&!number(right,n)))invalid=true;else if(size==0||l>=size||(!right.empty()&&n<l))unsat=true;else{start=l;end=right.empty()?size-1:min(n,size-1);}}}
   if(invalid){close(fd);error(c,400);return;}if(unsat){close(fd);respond(c,416,{{"Content-Range","bytes */"+to_string(size)}});return;}status=206;h.emplace_back("Content-Range","bytes "+to_string(start)+"-"+to_string(end)+"/"+to_string(size));
  }
  respond(c,status,move(h),nullptr,status==206?end-start+1:size,fd,start);
 }
 string proxy_target(const Request& r){if(r.rawpath.rfind(r.cfg->proxy_prefix,0)==0)return "/"+r.rawpath.substr(r.cfg->proxy_prefix.size())+r.query;string p=r.path.substr(r.cfg->proxy_prefix.size()),out="/";const char*hex="0123456789ABCDEF";for(unsigned char c:p){if((c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||string_view("/-._~!$&'()*+,;=:@").find(c)!=string_view::npos)out+=c;else{out+='%';out+=hex[c>>4];out+=hex[c&15];}}return out+r.query;}
 void start_proxy(Conn& c){auto conf=c.req.cfg;Address addr=conf->upstreams[round_robin++%conf->upstreams.size()];Up* u=nullptr;auto &idle=pool[addr.authority];while(!idle.empty()){auto [fd,t]=idle.back();idle.pop_back();auto it=ups.find(fd);if(it!=ups.end()&&it->second->tag==t&&it->second->state==Up::IDLE&&it->second->addr.authority==addr.authority){u=it->second.get();break;}}
  if(!u){int fd=socket(addr.sa.ss_family,SOCK_STREAM|SOCK_NONBLOCK|SOCK_CLOEXEC,0);if(fd<0){proxy_failure(c,502);return;}int one=1;setsockopt(fd,IPPROTO_TCP,TCP_NODELAY,&one,sizeof(one));auto fresh=make_unique<Up>();fresh->fd=fd;fresh->tag=tag(fd);fresh->addr=addr;u=fresh.get();ups.emplace(fd,move(fresh));int result=connect(fd,reinterpret_cast<const sockaddr*>(&addr.sa),addr.len);if(result<0&&errno!=EINPROGRESS){close_up(fd);proxy_failure(c,502);return;}u->state=result==0?Up::WRITE:Up::CONNECT;add(fd,u->tag,EPOLLOUT|EPOLLRDHUP);
  }else{u->state=Up::WRITE;u->headers.clear();u->in.clear();u->body.clear();u->send.clear();u->chunk=Chunk{};u->keep=true;u->chunked=false;mod(u->fd,u->tag,EPOLLOUT|EPOLLRDHUP);}
  u->client=c.fd;u->deadline=now_ms()+conf->upstream_timeout_ms;u->send_pos=0;c.upstream=u->fd;auto skip=hops(c.req.headers);skip.insert("host");skip.insert("content-length");u->send=c.req.method+" "+proxy_target(c.req)+" HTTP/1.1\r\nHost: "+addr.authority+"\r\nConnection: keep-alive\r\n";for(auto&[k,v]:c.req.headers)if(!skip.count(k))u->send+=k+": "+v+"\r\n";u->send+="Content-Length: "+to_string(c.req.body.size())+"\r\n\r\n";u->send+=c.req.body;interest(c);
 }
 void proxy_failure(Conn& c,int status){if(c.upstream>=0){int fd=c.upstream;c.upstream=-1;close_up(fd);}if((c.req.method=="GET"||c.req.head)&&c.attempts++==0&&!draining){start_proxy(c);return;}error(c,status,false);}
 void finish_up(int fd){auto it=ups.find(fd);if(it==ups.end())return;Up& u=*it->second;auto cit=clients.find(u.client);if(cit==clients.end()){close_up(fd);return;}Conn& c=*cit->second;Data d;d.status=u.status;d.body=make_shared<string>(move(u.body));d.length=c.req.head?u.length:d.body->size();auto skip=hops(u.headers);skip.insert("content-length");for(auto&h:u.headers)if(!skip.count(h.first))d.headers.push_back(h);c.upstream=-1;cache_put(c.req,d);bool keep=u.keep&&!draining&&u.in.empty();u.client=-1;u.send.clear();u.in.clear();u.headers.clear();u.send.shrink_to_fit();u.state=Up::IDLE;u.last=now_ms();
  if(keep&&pool[u.addr.authority].size()<256){pool[u.addr.authority].push_back({fd,u.tag});mod(fd,u.tag,EPOLLIN|EPOLLRDHUP);}else close_up(fd);respond(c,d.status,move(d.headers),d.body,d.length);process_client(c.fd);
 }
 int parse_up_header(Up& u,Conn& c,size_t end){string_view raw(u.in.data(),end);if(bad_lines(raw))return 502;size_t p=raw.find("\r\n");if(p==string_view::npos)return 502;string_view line=raw.substr(0,p);if(line.size()<12||(line.substr(0,9)!="HTTP/1.1 "&&line.substr(0,9)!="HTTP/1.0 "))return 502;if(line[9]<'1'||line[9]>'5'||line[10]<'0'||line[10]>'9'||line[11]<'0'||line[11]>'9'||(line.size()>12&&line[12]!=' '))return 502;u.status=(line[9]-'0')*100+(line[10]-'0')*10+line[11]-'0';u.headers.clear();size_t pos=p+2;while(pos+2<end){size_t q=raw.find("\r\n",pos);if(q==string_view::npos)return 502;if(q==pos)break;if(!parse_header_line(raw.substr(pos,q-pos),u.headers))return 502;pos=q+2;}
  int cl=count_field(u.headers,"content-length"),te=count_field(u.headers,"transfer-encoding");if(cl>1||te>1||(cl&&te))return 502;u.length=0;if(cl&&!number(field(u.headers,"content-length"),u.length))return 502;if(te&&lower(field(u.headers,"transfer-encoding"))!="chunked")return 502;u.chunked=te;u.keep=line.substr(0,8)=="HTTP/1.1"&&!has_token(u.headers,"connection","close");if(u.status>=100&&u.status<200)return u.status==101?502:100;
  if(u.status==204&&(cl||te))return 502;if(c.req.head||u.status==204||u.status==304){if(!c.req.head)u.length=0;return 1;}if(!cl&&!te)return 502;if(cl&&u.length>c.req.cfg->body_bytes)return 502;u.body.reserve(te?min<uint64_t>(65536,c.req.cfg->body_bytes):u.length);u.state=te?Up::CHUNKS:Up::LENGTH;return 0;
 }
 void process_up(int fd,uint32_t events){auto it=ups.find(fd);if(it==ups.end())return;Up& u=*it->second;if(u.state==Up::IDLE){close_up(fd);return;}auto cit=clients.find(u.client);if(cit==clients.end()){close_up(fd);return;}Conn& c=*cit->second;if(events&EPOLLERR){proxy_failure(c,502);return;}if(u.state==Up::CONNECT){int err=0;socklen_t len=sizeof(err);if(getsockopt(fd,SOL_SOCKET,SO_ERROR,&err,&len)||err){proxy_failure(c,502);return;}u.state=Up::WRITE;}
  size_t budget=512*1024;
  if(u.state==Up::WRITE){while(u.send_pos<u.send.size()&&budget){size_t n=min(budget,u.send.size()-u.send_pos);ssize_t sent=send(fd,u.send.data()+u.send_pos,n,MSG_NOSIGNAL);if(sent>0){u.send_pos+=sent;budget-=sent;}else if(sent<0&&(errno==EAGAIN||errno==EWOULDBLOCK)){return;}else if(sent<0&&errno==EINTR)continue;else{proxy_failure(c,502);return;}}if(u.send_pos<u.send.size())return;u.send.clear();u.state=Up::HEADER;mod(fd,u.tag,EPOLLIN|EPOLLRDHUP);}
  for(;;){
   if(u.state==Up::HEADER){size_t end=u.in.find("\r\n\r\n");if(end!=string::npos){end+=4;if(end>c.req.cfg->header_bytes){proxy_failure(c,502);return;}int result=parse_up_header(u,c,end);u.in.erase(0,end);if(result==100)continue;if(result==502){proxy_failure(c,502);return;}if(result==1){if(!u.in.empty()){proxy_failure(c,502);return;}finish_up(fd);return;}}else if(u.in.size()>c.req.cfg->header_bytes||bad_lines(u.in)){proxy_failure(c,502);return;}}
   if(u.state==Up::LENGTH){uint64_t remaining=u.length-u.body.size();size_t n=min<uint64_t>(remaining,u.in.size());u.body.append(u.in.data(),n);u.in.erase(0,n);if(u.body.size()==u.length){if(!u.in.empty()){proxy_failure(c,502);return;}finish_up(fd);return;}}
   if(u.state==Up::CHUNKS){int result=u.chunk.consume(u.in,u.body,c.req.cfg->body_bytes,c.req.cfg->header_bytes);if(result>=400){proxy_failure(c,502);return;}if(result==1){if(!u.in.empty()){proxy_failure(c,502);return;}finish_up(fd);return;}}
   if(!budget)return;char buf[16384];ssize_t n=recv(fd,buf,min(sizeof(buf),budget),0);if(n>0){u.in.append(buf,n);budget-=n;continue;}if(n<0&&errno==EINTR)continue;if(n<0&&(errno==EAGAIN||errno==EWOULDBLOCK))return;proxy_failure(c,502);return;
  }
 }
 bool write_response(Conn& c,size_t& budget){auto& r=*c.out;while(budget){ssize_t n;if(r.header_pos<r.header.size()){size_t count=min(budget,r.header.size()-r.header_pos);n=send(c.fd,r.header.data()+r.header_pos,count,MSG_NOSIGNAL);if(n>0)r.header_pos+=n;}
   else if(r.remaining&&r.file>=0){n=sendfile(c.fd,r.file,&r.offset,min<uint64_t>(budget,r.remaining));if(n>0)r.remaining-=n;}
   else if(r.remaining&&r.body){n=send(c.fd,r.body->data()+r.body_pos,min<uint64_t>(budget,r.remaining),MSG_NOSIGNAL);if(n>0){r.body_pos+=n;r.remaining-=n;}}
   else return true;
   if(n>0){budget-=n;c.write_last=now_ms();}else if(n<0&&errno==EINTR)continue;else if(n<0&&(errno==EAGAIN||errno==EWOULDBLOCK))return false;else{close_client(c.fd);return false;}}
  return r.header_pos==r.header.size()&&r.remaining==0;
 }
 void process_client(int fd){auto it=clients.find(fd);if(it==clients.end())return;Conn& c=*it->second;size_t budget=512*1024;
  for(;;){if(c.queued)return;if(c.ending){char discard[16384];while(budget){ssize_t n=recv(fd,discard,min(sizeof(discard),budget),0);if(n>0){budget-=n;continue;}if(n<0&&errno==EINTR)continue;if(n<0&&(errno==EAGAIN||errno==EWOULDBLOCK)){interest(c);return;}close_client(fd);return;}interest(c);return;}
   if(c.out){if(!write_response(c,budget))return;bool ending=c.out->close;c.out.reset();release_slot(c);if(ending){shutdown(fd,SHUT_WR);c.ending=true;c.last=now_ms();c.in.clear();pump_upstreams();continue;}c.req=Request{};c.parsed=false;c.attempts=0;c.last=now_ms();if(c.in.empty())c.first=0;pump_upstreams();}
   if(c.upstream>=0)return;
   if(!c.parsed){size_t end=c.in.find("\r\n\r\n");uint64_t limit=cfg->header_bytes;if(end!=string::npos){end+=4;++c.requests;if(end>limit){error(c,431);continue;}int result=parse_request(c,end);c.in.erase(0,end);if(result){error(c,result);continue;}c.parsed=true;if(!take_token()){respond(c,429,{{"Retry-After","1"}},nullptr,0,-1,0,c.req.chunked||c.req.length>0);continue;}if(c.req.proxy){if(cache_get(c))continue;queue_proxy(c);return;}}
    else if(c.in.size()>limit){error(c,431);continue;}else if(bad_lines(c.in)){error(c,400);continue;}}
   if(c.parsed){bool ready=true;if(c.req.proxy){if(c.req.chunked){int result=c.req.chunk.consume(c.in,c.req.body,c.req.cfg->body_bytes,c.req.cfg->header_bytes);if(result>=400){error(c,result);continue;}ready=result==1;}else{size_t n=min<uint64_t>(c.req.length-c.req.body.size(),c.in.size());c.req.body.append(c.in.data(),n);c.in.erase(0,n);ready=c.req.body.size()==c.req.length;}}
    if(ready){if(c.req.proxy){if(cache_get(c))continue;start_proxy(c);return;}local(c);continue;}}
   if(!budget){interest(c);return;}char buf[16384];ssize_t n=recv(fd,buf,min(sizeof(buf),budget),0);if(n>0){uint64_t now=now_ms();if(c.in.empty()&&!c.first)c.first=now;c.last=now;c.in.append(buf,n);budget-=n;continue;}if(n<0&&errno==EINTR)continue;if(n<0&&(errno==EAGAIN||errno==EWOULDBLOCK)){interest(c);return;}close_client(fd);return;
  }
 }
 void accept_clients(){for(unsigned i=0;i<256;++i){int fd=accept4(listener,nullptr,nullptr,SOCK_NONBLOCK|SOCK_CLOEXEC);if(fd<0){if(errno==EINTR){--i;continue;}break;}if(clients.size()>=cfg->max_connections){close(fd);continue;}int one=1;setsockopt(fd,IPPROTO_TCP,TCP_NODELAY,&one,sizeof(one));auto c=make_unique<Conn>();c->fd=fd;c->tag=tag(fd);c->last=now_ms();add(fd,c->tag,EPOLLIN|EPOLLRDHUP);clients.emplace(fd,move(c));}}
 void signals(){signalfd_siginfo info;while(read(sigfd,&info,sizeof(info))==sizeof(info)){if(info.ssi_signo==SIGHUP&&!draining){auto next=read_config(config_path);if(next&&next->listen==cfg->listen){cfg=move(next);cache.clear();lru.clear();cache_used=0;cache_metadata=0;tokens=cfg->rate_burst;refill=now_ms();vector<int> idle;for(auto&[fd,u]:ups)if(u->state==Up::IDLE)idle.push_back(fd);for(int fd:idle)close_up(fd);pool.clear();}}
   else if((info.ssi_signo==SIGTERM||info.ssi_signo==SIGINT)&&!draining){draining=true;drain_end=now_ms()+cfg->drain_timeout_ms;epoll_ctl(ep,EPOLL_CTL_DEL,listener,nullptr);close(listener);listener=-1;vector<int> idle;for(auto&[fd,c]:clients)if(!c->out&&c->upstream<0&&!c->parsed&&c->in.empty())idle.push_back(fd);for(int fd:idle)close_client(fd);}}
 }
 void scan(uint64_t now){vector<int> closefds;for(auto&[fd,c]:clients){auto conf=c->req.cfg?c->req.cfg:cfg;if(c->ending){if(now-c->last>=100)closefds.push_back(fd);}else if(c->out){if(now-c->write_last>=conf->write_timeout_ms)closefds.push_back(fd);}else if(c->upstream<0&&!c->queued){if(!c->parsed&&!c->in.empty()&&c->first&&now-c->first>=conf->header_timeout_ms)closefds.push_back(fd);else if(now-c->last>=conf->idle_timeout_ms)closefds.push_back(fd);}}for(int fd:closefds)close_client(fd);vector<int> bad,expired;for(auto&[fd,u]:ups){if(u->state==Up::IDLE){if(now-u->last>=cfg->idle_timeout_ms)bad.push_back(fd);}else if(now>=u->deadline)expired.push_back(fd);}for(int fd:bad)close_up(fd);for(int fd:expired){auto it=ups.find(fd);if(it==ups.end())continue;auto c=clients.find(it->second->client);if(c!=clients.end()){proxy_failure(*c->second,504);if(clients.count(c->first))process_client(c->first);}else close_up(fd);}}
public:
 explicit Server(string path):config_path(move(path)){}
 int run(){cfg=read_config(config_path);if(!cfg)return 1;tokens=cfg->rate_burst;refill=now_ms();signal(SIGPIPE,SIG_IGN);sigset_t mask;sigemptyset(&mask);sigaddset(&mask,SIGHUP);sigaddset(&mask,SIGTERM);sigaddset(&mask,SIGINT);if(sigprocmask(SIG_BLOCK,&mask,nullptr)<0)return 1;sigfd=signalfd(-1,&mask,SFD_NONBLOCK|SFD_CLOEXEC);ep=epoll_create1(EPOLL_CLOEXEC);if(sigfd<0||ep<0)return 1;listener=socket(cfg->binding.sa.ss_family,SOCK_STREAM|SOCK_NONBLOCK|SOCK_CLOEXEC,0);if(listener<0)return 1;int one=1;setsockopt(listener,SOL_SOCKET,SO_REUSEADDR,&one,sizeof(one));if(bind(listener,reinterpret_cast<sockaddr*>(&cfg->binding.sa),cfg->binding.len)||listen(listener,8192))return 1;add(listener,uint32_t(listener),EPOLLIN);add(sigfd,uint32_t(sigfd),EPOLLIN);array<epoll_event,512> events;
  while(true){uint64_t now=now_ms();if(draining&&(clients.empty()||now>=drain_end))break;if(now>=next_scan){scan(now);next_scan=now+20;}int n=epoll_wait(ep,events.data(),events.size(),20);if(n<0){if(errno==EINTR)continue;break;}for(int i=0;i<n;++i){uint64_t t=events[i].data.u64;int fd=uint32_t(t);uint32_t ev=events[i].events;if(fd==listener&&t==uint32_t(listener)){accept_clients();continue;}if(fd==sigfd&&t==uint32_t(sigfd)){signals();continue;}auto c=clients.find(fd);if(c!=clients.end()&&c->second->tag==t){if(ev&(EPOLLERR|EPOLLHUP)){close_client(fd);continue;}process_client(fd);continue;}auto u=ups.find(fd);if(u!=ups.end()&&u->second->tag==t)process_up(fd,ev);}}
  stopping=true;vector<int> all;for(auto&[fd,c]:clients)all.push_back(fd);for(int fd:all)close_client(fd);all.clear();for(auto&[fd,u]:ups)all.push_back(fd);for(int fd:all)close_up(fd);if(listener>=0)close(listener);close(sigfd);close(ep);return 0;
 }
};

int main(int argc,char**argv){if(argc!=3||string(argv[1])!="--config")return 1;try{Server s(argv[2]);return s.run();}catch(const exception& e){cerr<<"server: "<<e.what()<<'\n';return 1;}}
