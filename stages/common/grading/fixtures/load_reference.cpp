// Host-only load-generator calibration probe. NOT a conforming stage solution.
// Serves deterministic 4/64 KiB payloads; never supplied to builder agents.
#include <sys/epoll.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <unistd.h>
#include <cerrno>
#include <string>
#include <unordered_map>

struct Client {
    std::string input;
    const std::string* response = nullptr;
    size_t offset = 0;
    unsigned requests = 0;
    bool close = false;
};
int main() {
    std::string responses[2][2];
    for (int large=0; large<2; ++large) {
        size_t size = large ? 65536 : 4096;
        std::string body(size, '\0');
        for (size_t i=0; i<size; ++i) body[i]=char(i%256);
        for (int close=0; close<2; ++close)
            responses[large][close] = "HTTP/1.1 200 OK\r\nContent-Length: " + std::to_string(size)
                + "\r\nConnection: " + (close ? "close" : "keep-alive") + "\r\n\r\n" + body;
    }
    int listener=socket(AF_INET, SOCK_STREAM|SOCK_NONBLOCK, 0), one=1;
    setsockopt(listener,SOL_SOCKET,SO_REUSEADDR,&one,sizeof(one));
    sockaddr_in address{};
    address.sin_family=AF_INET; address.sin_port=htons(8080);
    address.sin_addr.s_addr=htonl(INADDR_LOOPBACK);
    if(bind(listener,(sockaddr*)&address,sizeof(address)) || listen(listener,8192)) return 1;
    int ep=epoll_create1(0);
    epoll_event initial{}; initial.events=EPOLLIN; initial.data.fd=listener;
    epoll_ctl(ep,EPOLL_CTL_ADD,listener,&initial);
    std::unordered_map<int,Client> clients;
    epoll_event events[256];
    while (true) {
        int count=epoll_wait(ep,events,256,-1);
        if(count<0) { if(errno==EINTR) continue; return 2; }
        for(int i=0;i<count;++i) {
            int fd=events[i].data.fd;
            if(fd==listener) {
                while(true) {
                    int peer=accept4(listener,nullptr,nullptr,SOCK_NONBLOCK);
                    if(peer<0) break;
                    clients.emplace(peer,Client{});
                    epoll_event event{}; event.events=EPOLLIN; event.data.fd=peer;
                    epoll_ctl(ep,EPOLL_CTL_ADD,peer,&event);
                }
                continue;
            }
            auto found=clients.find(fd); if(found==clients.end()) continue;
            Client& client=found->second;
            bool dead=events[i].events&(EPOLLERR|EPOLLHUP);
            if(!dead && !client.response) {
                char buffer[8192];
                ssize_t length=recv(fd,buffer,sizeof(buffer),0);
                if(length>0) client.input.append(buffer,length);
                else if(length==0 || (errno!=EAGAIN && errno!=EINTR)) dead=true;
                if(client.input.size()>16384) dead=true;
                if(client.input.find("\r\n\r\n")!=std::string::npos) {
                    client.close=client.input.find("Connection: close")!=std::string::npos || ++client.requests>=100;
                    int large=client.input.find("/65536 ")!=std::string::npos;
                    client.response=&responses[large][client.close];
                }
            }
            if(!dead && client.response) {
                const auto& response=*client.response;
                ssize_t sent=send(fd,response.data()+client.offset,response.size()-client.offset,MSG_NOSIGNAL);
                if(sent>0) client.offset+=sent;
                else if(sent<0 && errno!=EAGAIN && errno!=EINTR) dead=true;
                if(client.offset==response.size()) {
                    dead=client.close;
                    client.response=nullptr; client.input.clear(); client.offset=0;
                }
            }
            if(dead) {epoll_ctl(ep,EPOLL_CTL_DEL,fd,nullptr); close(fd); clients.erase(fd);}
            else {
                epoll_event event{}; event.data.fd=fd;
                event.events=client.response ? EPOLLOUT : EPOLLIN;
                epoll_ctl(ep,EPOLL_CTL_MOD,fd,&event);
            }
        }
    }
}
