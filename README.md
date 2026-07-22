# voting-server

Server bình chọn/bầu cử trực tuyến. Python 3.11+, **chỉ standard library**, TCP socket bọc TLS,
lưu trữ JSON trên đĩa. Đây là repo backend; hai repo client/admin (.NET WinForms) giao tiếp qua
giao thức mô tả trong [docs/PROTOCOL.md](docs/PROTOCOL.md).

## Yêu cầu

- Python 3.11 trở lên (đang phát triển trên 3.12).
- `openssl` để sinh chứng chỉ tự ký (chỉ cần khi bật TLS).
- Không cần cài gói bên ngoài.

## Chạy nhanh

```bash
# 1. Sinh dữ liệu mẫu (30 cử tri HS001-HS030 / mật khẩu 123456, admin / admin123)
python tools/seed_data.py

# 2. Sinh chứng chỉ tự ký (thay IP bằng IP LAN của máy server)
bash certs/gen_cert.sh 192.168.1.10

# 3. Sao cấu hình mẫu rồi chỉnh nếu cần
cp config.example.json config.json

# 4. Khởi động server
python -m src.main --config config.json
# Hoặc debug không TLS:
python -m src.main --no-tls --port 8443
```

## Công cụ dòng lệnh để test

```bash
python tools/cli_client.py --no-tls login HS001 123456
python tools/cli_client.py --no-tls candidates
python tools/cli_client.py --no-tls admin-login admin admin123
python tools/cli_client.py --no-tls open
python tools/cli_client.py --no-tls vote 3
python tools/cli_client.py --no-tls results
python tools/cli_client.py --no-tls subscribe          # giữ kết nối, in mọi push
python tools/cli_client.py --no-tls raw '{"v":1,"type":"PING"}'
```

Token được lưu ở `.cli_token` để không phải copy-paste giữa các lệnh.

## Chạy test

```bash
python -m unittest discover tests
```

## Cấu hình

Xem [config.example.json](config.example.json). `main.py` nhận `--config`, `--port`, `--no-tls`
(override để debug). Bind `0.0.0.0` để máy Windows trong LAN kết nối được.

## Cho team .NET (client + admin)

- Hợp đồng giao thức: [docs/PROTOCOL.md](docs/PROTOCOL.md). **Không đổi đơn phương.**
- File mẫu từng message: [docs/samples/](docs/samples/) — đối chiếu khi viết model.
- Bốn điều bắt buộc cho `VotingSystem.Shared`:
  1. Đọc frame phải lặp cho tới khi đủ byte (cả header lẫn payload).
  2. Header big-endian: dùng `IPAddress.NetworkToHostOrder`.
  3. Payload UTF-8 không BOM.
  4. Message không có `req_id` là server push → đẩy vào event, không khớp request đang chờ.

Bảng địa chỉ để điền khi test chung trong LAN:

| Mục | Giá trị |
|---|---|
| IP server (LAN) | _điền IP máy chạy server, ví dụ 192.168.1.10_ |
| Port | `8443` |
| TLS | bật (self-signed) — xem cách tin cert ở PROTOCOL.md mục 5 |
| Tài khoản cử tri mẫu | `HS001`..`HS030` / `123456` |
| Tài khoản admin | `admin` / `admin123` |

Tìm IP LAN của máy server: macOS `ipconfig getifaddr en0`, Linux `hostname -I`,
Windows `ipconfig`.

## Cấu trúc dự án

```
src/
  main.py         entry point: parse args, dựng thành phần, bắt tín hiệu
  server.py       accept loop, thread mỗi kết nối, dọn phiên, tắt êm
  connection.py   1 socket = 1 thread: đọc frame, định tuyến, trả response
  framing.py      length-prefix frame (4 byte big-endian + JSON UTF-8)
  protocol.py     hằng số type/error code, hàm dựng message
  errors.py       ProtocolError và lớp con (mang code + message tiếng Việt)
  security.py     hash/verify mật khẩu, sinh token, TLS context, receipt
  sessions.py     SessionManager (token -> phiên) + LoginRateLimiter
  store.py        DataStore: JSON trong RAM, ghi atomic, record_vote nguyên tử
  broadcast.py    BroadcastHub: quản lý subscriber, đẩy realtime
  handlers/       auth.py, voting.py, admin.py + bảng định tuyến (__init__.py)
tools/            seed_data.py, cli_client.py
tests/            test_framing / test_store / test_auth / test_voting
docs/             PROTOCOL.md + samples/
```

Chiều phụ thuộc một chiều (không import ngược):
`main → server → connection → handlers → store/sessions/broadcast → security/errors/protocol/framing`.

## Bảo mật & phiếu kín

- Mật khẩu băm PBKDF2-SHA256, 200.000 vòng, salt riêng từng người.
- `votes.json` **không chứa** `voter_id`: ai đã bầu chỉ ghi ở `voters.json`, bầu cho ai chỉ ghi ở
  `votes.json`, hai file không liên kết được.
- Biên nhận (receipt) = `sha256(vote_id + voter_id + server_secret)`, không suy ngược ra lá phiếu.

Cấu trúc mã nguồn và quy ước: xem [CLAUDE.md](CLAUDE.md).
