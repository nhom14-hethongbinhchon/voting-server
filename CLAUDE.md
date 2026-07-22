# Quy ước code — voting-server

Đọc file này trước khi viết dòng code đầu tiên. Mọi module trong repo phải tuân thủ.

## Phạm vi kỹ thuật

- Python 3.11+ (máy phát triển đang chạy 3.12).
- Chỉ dùng standard library: `socket`, `ssl`, `threading`, `json`, `hashlib`, `hmac`,
  `secrets`, `struct`, `logging`, `argparse`, `unittest`, `datetime`, `os`, `sys`, `signal`, `time`.
- Không framework web, không SQL/ORM, không thư viện bên thứ ba.
- Không tạo file nằm ngoài cây thư mục đã mô tả trong kế hoạch (mục 2). Ngoại lệ được phép:
  `logs/` (log runtime) và `data/server_secret` (khoá sinh receipt), cả hai đều nằm trong `.gitignore`.

## Comment

- Viết bằng tiếng Việt, chỉ dùng dấu `#`, mỗi comment một dòng.
- Không dùng banner `=====` hay `-----`, không đánh số "PHẦN 1 / PHẦN 2".
- Comment chỉ giải thích *tại sao*, không mô tả lại điều code đã nói rõ.
- Docstring cho module và cho hàm public được phép, ngắn gọn, nêu mục đích và điều kiện lỗi.

## Đặt tên

- Hàm và biến: `snake_case`. Class: `PascalCase`. Hằng số: `UPPER_SNAKE_CASE`.
- Tên message type và error code là hằng số chuỗi trong `protocol.py`, không rải chuỗi thô khắp nơi.

## Chiều phụ thuộc (một chiều, không import ngược)

```
main → server → connection → handlers → store / sessions / broadcast → security / errors / protocol / framing
```

- Tầng dưới không được import tầng trên.
- `framing.py` là lá độc lập: không import `errors.py`. Nó tự định nghĩa exception riêng
  (`FrameTooLarge`) và để `json.JSONDecodeError` lan ra; tầng `connection` mới dịch sang error code.

## Xử lý lỗi

- Lỗi nghiệp vụ dùng `ProtocolError` (và lớp con) trong `errors.py`, mỗi lớp mang sẵn `code`
  và `message` tiếng Việt cho người dùng cuối.
- Client xử lý logic theo `code`, hiển thị `message`. `message` không được lộ chi tiết nội bộ.
- Exception ngoài dự kiến: log traceback đầy đủ ở server, trả `INTERNAL_ERROR` với message
  chung chung. Không bao giờ đẩy stack trace ra client.
- Đăng nhập sai user và sai mật khẩu trả cùng một `INVALID_CREDENTIALS`, cùng message.

## Đồng thời

- Mọi truy cập `DataStore` đi qua một `RLock` duy nhất. Kiểm tra điều kiện và ghi phải nằm
  trong cùng một lần giữ lock (chống bầu trùng).
- Không giữ lock của store khi gọi I/O mạng (ví dụ `hub.publish`).
- Mỗi connection có lock riêng cho việc gửi, vì thread broadcast và thread request cùng ghi
  vào một socket.

## Logging

- Không bao giờ log mật khẩu hoặc token đầy đủ. Token chỉ log 8 ký tự đầu.
- Mỗi request log kèm IP, `req_id`, `type`, thời gian xử lý.

## JSON và mã hoá

- `json.dump/dumps` luôn đặt `ensure_ascii=False` để giữ nguyên tiếng Việt có dấu.
- UTF-8 không BOM cho mọi payload trên dây.
- Ghi file dữ liệu phải atomic: ghi ra `.tmp`, `flush` + `fsync`, rồi `os.replace`.

## Phiếu kín

- `votes.json` không bao giờ chứa `voter_id`. Cờ "đã bầu" chỉ nằm ở `voters.json`,
  nội dung phiếu chỉ nằm ở `votes.json`, hai file không liên kết được.
- Không viết code nào ghi `voter_id` cạnh `candidate_id`.

## Test

- Dùng `unittest`, file đặt trong `tests/`, tên `test_*.py`.
- Chạy toàn bộ bằng `python -m unittest discover tests`.
- Test không được phụ thuộc mạng thật hay thứ tự chạy; dùng `socketpair`, thư mục tạm cho dữ liệu.

## Git

- Comment và tài liệu bằng tiếng Việt; tên biến/hàm bằng tiếng Anh theo chuẩn Python.
- Không commit `certs/*.key`, `certs/*.crt`, `config.json`, `data/*.json`, `data/server_secret`, `logs/`.
