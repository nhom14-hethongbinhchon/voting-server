"""Client dòng lệnh để test server thật. Không phải mock: nói chuyện với server, dữ liệu thật.

Ví dụ:
    python tools/cli_client.py --no-tls login HS001 123456
    python tools/cli_client.py --no-tls candidates
    python tools/cli_client.py --no-tls admin-login admin admin123
    python tools/cli_client.py --no-tls open
    python tools/cli_client.py --no-tls vote 3
    python tools/cli_client.py --no-tls results
    python tools/cli_client.py --no-tls subscribe
    python tools/cli_client.py --no-tls raw '{"v":1,"type":"PING"}'

Token lưu ở .cli_token để không phải copy-paste giữa các lệnh.
"""

import argparse
import json
import os
import socket
import ssl
import struct
import sys
import uuid

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.framing import recv_frame, send_frame

TOKEN_FILE = os.path.join(_ROOT, ".cli_token")


def connect(host: str, port: int, use_tls: bool):
    raw = socket.create_connection((host, port), timeout=10)
    if not use_tls:
        return raw
    # Cert tự ký trong môi trường học tập: bỏ qua verify hostname và chuỗi tin cậy
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context.wrap_socket(raw, server_hostname=host)


def load_token() -> str | None:
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return None


def save_token(token: str) -> None:
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(token)


def require_token() -> str:
    token = load_token()
    if not token:
        print("Chưa đăng nhập. Chạy lệnh login hoặc admin-login trước.")
        sys.exit(1)
    return token


def send_request(sock, msg_type: str, data: dict) -> dict:
    request = {"v": 1, "type": msg_type, "req_id": str(uuid.uuid4()), "data": data}
    send_frame(sock, request)
    return recv_frame(sock)


def show(obj) -> None:
    # flush ngay để chế độ subscribe in push tức thì khi bị redirect ra file/pipe
    print(json.dumps(obj, ensure_ascii=False, indent=2), flush=True)


def cmd_login(sock, args):
    resp = send_request(sock, "LOGIN", {"voter_id": args.voter_id, "password": args.password})
    show(resp)
    if resp and resp.get("status") == "ok":
        save_token(resp["data"]["token"])
        print("Đã lưu token.")


def cmd_admin_login(sock, args):
    resp = send_request(sock, "ADMIN_LOGIN",
                        {"username": args.username, "password": args.password})
    show(resp)
    if resp and resp.get("status") == "ok":
        save_token(resp["data"]["token"])
        print("Đã lưu token.")


def cmd_candidates(sock, args):
    show(send_request(sock, "GET_CANDIDATES", {"token": require_token()}))


def cmd_vote(sock, args):
    show(send_request(sock, "CAST_VOTE",
                      {"token": require_token(), "candidate_id": args.candidate_id}))


def cmd_status(sock, args):
    show(send_request(sock, "GET_MY_STATUS", {"token": require_token()}))


def cmd_logout(sock, args):
    show(send_request(sock, "LOGOUT", {"token": require_token()}))
    if os.path.exists(TOKEN_FILE):
        os.remove(TOKEN_FILE)


def cmd_results(sock, args):
    show(send_request(sock, "GET_RESULTS", {"token": require_token()}))


def cmd_stats(sock, args):
    show(send_request(sock, "GET_STATS", {"token": require_token()}))


def cmd_open(sock, args):
    show(send_request(sock, "OPEN_ELECTION", {"token": require_token()}))


def cmd_close(sock, args):
    show(send_request(sock, "CLOSE_ELECTION", {"token": require_token()}))


def cmd_subscribe(sock, args):
    # Giữ kết nối mở và in mọi message server đẩy xuống cho tới khi Ctrl-C
    resp = send_request(sock, "SUBSCRIBE_RESULTS", {"token": require_token()})
    show(resp)
    print("Đang lắng nghe push (Ctrl-C để dừng)...", flush=True)
    # Chờ push vô thời hạn: bỏ timeout của giai đoạn connect để socket không tự bật ra
    sock.settimeout(None)
    try:
        while True:
            push = recv_frame(sock)
            if push is None:
                print("Server đã đóng kết nối.")
                break
            show(push)
    except KeyboardInterrupt:
        print("\nDừng.")


def cmd_raw(sock, args):
    try:
        obj = json.loads(args.payload)
    except json.JSONDecodeError:
        # Gửi thẳng byte không phải JSON để test lỗi INVALID_JSON phía server
        payload = args.payload.encode("utf-8")
        sock.sendall(struct.pack(">I", len(payload)) + payload)
    else:
        send_frame(sock, obj)
    show(recv_frame(sock))


def build_parser():
    parser = argparse.ArgumentParser(description="Client dòng lệnh test voting-server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8443)
    parser.add_argument("--no-tls", action="store_true", help="kết nối TCP thuần, không TLS")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("login"); p.add_argument("voter_id"); p.add_argument("password")
    p.set_defaults(func=cmd_login)
    p = sub.add_parser("admin-login"); p.add_argument("username"); p.add_argument("password")
    p.set_defaults(func=cmd_admin_login)
    sub.add_parser("candidates").set_defaults(func=cmd_candidates)
    p = sub.add_parser("vote"); p.add_argument("candidate_id", type=int)
    p.set_defaults(func=cmd_vote)
    sub.add_parser("status").set_defaults(func=cmd_status)
    sub.add_parser("logout").set_defaults(func=cmd_logout)
    sub.add_parser("results").set_defaults(func=cmd_results)
    sub.add_parser("stats").set_defaults(func=cmd_stats)
    sub.add_parser("open").set_defaults(func=cmd_open)
    sub.add_parser("close").set_defaults(func=cmd_close)
    sub.add_parser("subscribe").set_defaults(func=cmd_subscribe)
    p = sub.add_parser("raw"); p.add_argument("payload"); p.set_defaults(func=cmd_raw)
    return parser


def main():
    args = build_parser().parse_args()
    sock = connect(args.host, args.port, use_tls=not args.no_tls)
    try:
        args.func(sock, args)
    finally:
        try:
            sock.close()
        except OSError:
            pass


if __name__ == "__main__":
    main()
