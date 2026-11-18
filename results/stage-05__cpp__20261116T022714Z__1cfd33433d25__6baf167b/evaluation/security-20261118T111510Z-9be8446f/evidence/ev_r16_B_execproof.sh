#!/bin/bash
# usage: execproof.sh <build> <conf> <port> <label> <bodyprefix>
set -u
B="$1"; C="$2"; P="$3"; L="$4"
D=/tmp/r16B/laneB
mkdir -p "$D"
rm -f "$D/up_$L.log" "$D/strace_$L".*
timeout 30 python3 ev_r16_B_peer.py $((P+1)) "$D/up_$L.log" > "$D/peer_$L.port" 2>&1 &
UP=$!
sleep 0.6
timeout 40 strace -f -qq -o "$D/strace_$L.txt" -e trace=execve,execveat,clone,clone3,fork,vfork ./bin/"$B" --config "$C" >/dev/null 2>&1 &
SRV=$!
sleep 1.3
H=$(printf 'GET /api/exec?cmd=id HTTP/1.1\r\nHost: alpha.test\r\nConnection: close\r\n\r\n' | xxd -p | tr -d '\n')
timeout 10 python3 ev_r16_B_client.py "$P" "$H" 3 > "$D/ctl_$L.txt" 2>&1
echo "ctl_exit=$?"
head -2 "$D/ctl_$L.txt" | cut -c1-160
sleep 0.4
kill $SRV 2>/dev/null; wait $SRV 2>/dev/null
kill $UP 2>/dev/null; wait $UP 2>/dev/null
