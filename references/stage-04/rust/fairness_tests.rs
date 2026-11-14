// This suffix is appended to an exact server snapshot and compiled with rustc
// --test by the sandbox. It drives the real admission/dispatch methods directly,
// so the ready-event ordering below is deterministic and needs no timing load.
#[cfg(test)]
mod fairness_regression {
    use super::*;

    fn configured_server() -> (Server, Vec<TcpListener>) {
        let listeners: Vec<_> = (0..2)
            .map(|_| TcpListener::bind("127.0.0.1:0").unwrap())
            .collect();
        let cfg = Config {
            listen: "127.0.0.1:0".parse().unwrap(),
            root: File::open("/tmp").unwrap(),
            beta: File::open("/tmp").unwrap(),
            alias: File::open("/tmp").unwrap(),
            beta_host: "beta.test".into(),
            default_host: "alpha.test".into(),
            alias_prefix: "/assets/".into(),
            redir_path: "/old".into(),
            redir_to: "/hello.txt".into(),
            index: "index.html".into(),
            proxy_prefix: "/proxy/".into(),
            upstreams: listeners.iter().map(|l| l.local_addr().unwrap()).collect(),
            // Leave room for the simulated 64 occupied slots per authority
            // plus the waiting/new clients, while retaining the 64-slot pool cap.
            max_connections: 256,
            header_bytes: 8192,
            header_timeout: Duration::from_millis(1000),
            idle_timeout: Duration::from_millis(2000),
            write_timeout: Duration::from_millis(2000),
            max_requests: 100,
            pipeline_depth: 16,
            upstream_timeout: Duration::from_millis(500),
            body_bytes: 1048576,
        };
        (Server::new(cfg).unwrap(), listeners)
    }

    fn client(s: &mut Server) -> (i32, Client, TcpStream) {
        let peer = TcpStream::connect(s.listener.local_addr().unwrap()).unwrap();
        let (stream, _) = s.listener.accept().unwrap();
        stream.set_nonblocking(true).unwrap();
        let fd = stream.as_raw_fd();
        ep_set(s.ep, 1, fd, IN | RDHUP, fd as u64);
        (
            fd,
            Client {
                stream,
                input: Vec::new(),
                phase: Phase::Reading,
                first: None,
                idle: Instant::now() + s.cfg.idle_timeout,
                count: 0,
            },
            peer,
        )
    }

    fn req(s: &Server, path: &str, method: &str) -> Request {
        request(
            format!("{} {} HTTP/1.1\r\nHost: alpha.test\r\n\r\n", method, path).as_bytes(),
            &s.cfg,
        )
        .unwrap()
    }

    fn admit(s: &mut Server, which: usize, path: &str) -> (i32, TcpStream) {
        let (fd, mut c, peer) = client(s);
        let req = req(s, path, "GET");
        s.round = which;
        s.initiate(fd, &mut c, req, Vec::new());
        s.register_down(&c);
        s.clients.insert(fd, c);
        (fd, peer)
    }

    fn is_queued(s: &Server, fd: i32) -> bool {
        matches!(s.clients[&fd].phase, Phase::Queued { .. })
    }
    fn is_proxy(s: &Server, fd: i32, path: &str) -> bool {
        matches!(&s.clients[&fd].phase,Phase::Proxy(p) if p.req.path==path)
    }

    #[test]
    fn free_slot_does_not_let_new_arrival_overtake_old_waiter() {
        let (mut s, _upstream_listeners) = configured_server();
        s.active[0] = 64;
        let (old, _old_peer) = admit(&mut s, 0, "/proxy/old");
        assert!(is_queued(&s, old));
        s.active[0] -= 1; // an earlier event in this epoll batch completes
        let (new, _new_peer) = admit(&mut s, 0, "/proxy/new");
        assert!(
            is_queued(&s, new),
            "new arrival claimed the old waiter's free slot"
        );
        s.dispatch_pending();
        assert!(is_proxy(&s, old, "/proxy/old"));
        assert!(is_queued(&s, new));
    }

    #[test]
    fn dispatch_starts_oldest_directly_without_requeue_inversion() {
        let (mut s, _upstream_listeners) = configured_server();
        s.active[0] = 64;
        let (first, _first_peer) = admit(&mut s, 0, "/proxy/first");
        let (second, _second_peer) = admit(&mut s, 0, "/proxy/second");
        let (third, _third_peer) = admit(&mut s, 0, "/proxy/third");
        s.active[0] -= 1;
        s.dispatch_pending();
        assert!(is_proxy(&s, first, "/proxy/first"));
        assert_eq!(
            s.pending.iter().map(|q| q.fd).collect::<Vec<_>>(),
            vec![second, third]
        );
        let c = s.clients.remove(&first).unwrap();
        s.dispose(first, c);
        s.dispatch_pending();
        assert!(is_proxy(&s, second, "/proxy/second"));
        assert!(is_queued(&s, third));
    }

    #[test]
    fn blocked_authority_does_not_stop_another_authoritys_fifo() {
        let (mut s, _upstream_listeners) = configured_server();
        s.active[0] = 64;
        s.active[1] = 64;
        let (a, _a_peer) = admit(&mut s, 0, "/proxy/a");
        let (b, _b_peer) = admit(&mut s, 1, "/proxy/b");
        let (c, _c_peer) = admit(&mut s, 0, "/proxy/c");
        s.active[1] -= 1;
        s.dispatch_pending();
        assert!(is_proxy(&s, b, "/proxy/b"));
        assert_eq!(
            s.pending.iter().map(|q| q.fd).collect::<Vec<_>>(),
            vec![a, c]
        );
    }

    #[test]
    fn retry_created_mid_dispatch_stays_behind_all_old_blocked_entries() {
        let (mut s, _upstream_listeners) = configured_server();
        s.active = vec![64, 64];
        let (a, _a_peer) = admit(&mut s, 0, "/proxy/a");
        let (retry, _retry_peer) = admit(&mut s, 1, "/proxy/retry");
        let (c, _c_peer) = admit(&mut s, 0, "/proxy/c");
        let (d, _d_peer) = admit(&mut s, 0, "/proxy/d");
        // The nonexistent interface index makes a link-local connect fail
        // synchronously on Linux, without a timing-dependent peer response.
        let impossible = SocketAddr::V6(std::net::SocketAddrV6::new(
            "fe80::1".parse().unwrap(),
            9,
            0,
            u32::MAX,
        ));
        assert!(nonblocking_connect(impossible).is_err());
        s.cfg.upstreams[1] = impossible;
        s.active[1] = 0;
        s.dispatch_pending();
        assert!(is_queued(&s, retry));
        assert_eq!(
            s.pending.iter().map(|q| q.fd).collect::<Vec<_>>(),
            vec![a, c, d, retry],
            "retry generated in this pass overtook an older blocked request"
        );
    }

    fn expired_exchange(s: &mut Server, method: &str, attempt: u8) -> (i32, TcpStream) {
        let (fd, mut c, peer) = client(s);
        let request = req(s, "/proxy/retry", method);
        let mut p = s.start_proxy(fd, request, Vec::new(), 0, attempt).unwrap();
        p.deadline = Instant::now() - Duration::from_millis(1);
        let up = p.stream.as_raw_fd();
        c.phase = Phase::Proxy(p);
        s.register_down(&c);
        s.clients.insert(fd, c);
        s.upstream(up);
        (fd, peer)
    }

    #[test]
    fn retry_waits_behind_old_requests_for_its_next_authority() {
        let (mut s, _upstream_listeners) = configured_server();
        s.active[1] = 64;
        let (old, _old_peer) = admit(&mut s, 1, "/proxy/old");
        s.active[1] -= 1;
        let (retry, _retry_peer) = expired_exchange(&mut s, "GET", 0);
        assert!(
            is_queued(&s, retry),
            "retry bypassed an older waiter on its next authority"
        );
        s.dispatch_pending();
        assert!(is_proxy(&s, old, "/proxy/old"));
        assert!(is_queued(&s, retry));
    }

    #[test]
    fn post_failure_never_enters_retry_queue() {
        let (mut s, _upstream_listeners) = configured_server();
        let (fd, _peer) = expired_exchange(&mut s, "POST", 0);
        assert!(s.pending.iter().all(|q| q.fd != fd));
        assert!(!is_queued(&s, fd));
        assert_eq!(s.active, vec![0, 0]);
    }

    #[test]
    fn second_attempt_failure_never_enters_another_retry_queue() {
        let (mut s, _upstream_listeners) = configured_server();
        let (fd, _peer) = expired_exchange(&mut s, "GET", 1);
        assert!(s.pending.iter().all(|q| q.fd != fd));
        assert!(!is_queued(&s, fd));
        assert_eq!(s.active, vec![0, 0]);
    }
}
