# PROTOCOL — hợp đồng giữa server và client

Tài liệu này là **hợp đồng chung** giữa `voting-server` (Python) và các client `.NET`
(Client cử tri + Admin, WinForms). **Không bên nào được đổi đơn phương.** Phiên bản giao thức
hiện tại là `v = 1`.

Xem các file mẫu trong [samples/](samples/) để đối chiếu khi viết model.

## 1. Framing

TCP là byte stream, không có ranh giới message. Mỗi message được đóng gói:

```
+----------------+----------------------------+
| 4 bytes length | payload JSON UTF-8          |
| unsigned, big  | (length = số byte payload)  |
| endian         |                             |
+----------------+----------------------------+
```

- Độ dài tối đa payload: **1 MiB (1.048.576 byte)**. Vượt quá → server trả lỗi
  `PAYLOAD_TOO_LARGE` rồi đóng kết nối.
- Bên đọc **phải** đọc đủ 4 byte header, sau đó đọc đủ `length` byte (lặp `recv`/`Read` tới khi
  đủ). Không được giả định một lần đọc trả về trọn một message.
- Header là big-endian: bên .NET dùng `IPAddress.NetworkToHostOrder` để đổi endianness.
- Payload là UTF-8 **không BOM**: bên .NET dùng `new UTF8Encoding(false)` hoặc `Encoding.UTF8`
  (khi ghi phải chắc chắn không chèn BOM).

## 2. Cấu trúc message

**Request (client → server):**

```json
{ "v": 1, "type": "CAST_VOTE", "req_id": "b3f1c2a4-...", "data": { "candidate_id": 3 } }
```

**Response thành công (server → client):**

```json
{ "v": 1, "type": "CAST_VOTE_RESULT", "req_id": "b3f1c2a4-...", "status": "ok",
  "data": { "receipt": "a91f...", "voted_at": "2026-07-22T09:31:04Z" } }
```

**Response lỗi:**

```json
{ "v": 1, "type": "CAST_VOTE_RESULT", "req_id": "b3f1c2a4-...", "status": "error",
  "error": { "code": "ALREADY_VOTED", "message": "Cử tri này đã bỏ phiếu." } }
```

**Server push (không có `req_id`):**

```json
{ "v": 1, "type": "RESULTS_UPDATE", "data": { "results": [ ], "total_votes": 42 } }
```

Quy tắc:

- `v` luôn bằng `1`. Client gửi `v` khác → lỗi `PROTOCOL_VERSION_MISMATCH`.
- Tên response luôn là `<TÊN_REQUEST>_RESULT`.
- `req_id` do client sinh (UUID4 dạng chuỗi), server echo lại nguyên văn. Client dùng nó để
  ghép response với request đang chờ.
- **Message do server tự đẩy xuống không có `req_id`** — đây là cách client phân biệt push với
  response. Push phải đẩy vào event/handler, KHÔNG khớp vào request đang chờ.
- `status` chỉ nhận `"ok"` hoặc `"error"`. Khi `error` có trường `error`, không có `data`;
  khi `ok` có trường `data`, không có `error`.
- Token xác thực đặt trong `data.token`, trừ `LOGIN` / `ADMIN_LOGIN`.
- Lỗi xảy ra **trước khi** server kịp đọc được `type`/`req_id` (JSON hỏng, frame quá lớn) trả về
  với `type` = `"ERROR"` và không có `req_id`. Client nên có nhánh xử lý lỗi cấp thấp này.

## 3. Bảng message

### Cử tri (Client)

| Type | data (request) | data (response ok) |
|---|---|---|
| `LOGIN` | `voter_id`, `password` | `token`, `voter_name`, `has_voted`, `election_status` |
| `GET_CANDIDATES` | `token` | `candidates: [{id, name, description, photo_url}]` |
| `CAST_VOTE` | `token`, `candidate_id` | `receipt`, `voted_at` |
| `GET_MY_STATUS` | `token` | `has_voted`, `election_status` |
| `LOGOUT` | `token` | `{}` |

### Quản trị (Admin)

| Type | data (request) | data (response ok) |
|---|---|---|
| `ADMIN_LOGIN` | `username`, `password` | `token`, `display_name` |
| `GET_RESULTS` | `token` | `results`, `total_votes`, `election_status` |
| `GET_STATS` | `token` | `total_voters`, `voted_count`, `remaining`, `turnout_percent` |
| `SUBSCRIBE_RESULTS` | `token` | `{}` — sau đó server bắt đầu đẩy `RESULTS_UPDATE` |
| `UNSUBSCRIBE_RESULTS` | `token` | `{}` |
| `OPEN_ELECTION` | `token` | `election_status` |
| `CLOSE_ELECTION` | `token` | `election_status` |

`results` có dạng:

```json
[ { "candidate_id": 1, "name": "Nguyễn Văn A", "votes": 17, "percent": 40.5 } ]
```

`election_status` ∈ `not_started` | `open` | `closed`.

### Server push

| Type | data | Gửi khi nào |
|---|---|---|
| `RESULTS_UPDATE` | `results`, `total_votes`, `election_status` | Sau mỗi phiếu hợp lệ |
| `ELECTION_STATE_CHANGED` | `election_status` | Khi admin mở/đóng bầu cử |

> `SUBSCRIBE_RESULTS` gắn **kết nối hiện tại** vào danh sách nhận push. Vì vậy client admin muốn
> nhận realtime phải **giữ kết nối mở** sau khi subscribe (không đóng rồi mở lại cho từng lệnh).

### Kiểm tra sức khoẻ (không bắt buộc)

| Type | data (request) | data (response ok) |
|---|---|---|
| `PING` | (tuỳ ý) | `pong: true`, `echo` |

`PING` chỉ để test/health-check, không thuộc luồng nghiệp vụ.

## 4. Mã lỗi

| Code | Ý nghĩa |
|---|---|
| `INVALID_JSON` | Payload không parse được |
| `BAD_REQUEST` | Thiếu trường bắt buộc hoặc sai kiểu |
| `UNKNOWN_TYPE` | `type` không tồn tại |
| `PROTOCOL_VERSION_MISMATCH` | `v` không phải 1 |
| `PAYLOAD_TOO_LARGE` | Frame vượt 1 MiB |
| `INVALID_CREDENTIALS` | Sai tài khoản/mật khẩu |
| `UNAUTHENTICATED` | Thiếu token hoặc token hết hạn |
| `FORBIDDEN` | Token cử tri gọi API admin (hoặc ngược lại) |
| `ALREADY_VOTED` | Cử tri đã bỏ phiếu |
| `ELECTION_NOT_OPEN` | Chưa mở bầu cử |
| `ELECTION_CLOSED` | Đã đóng bầu cử |
| `CANDIDATE_NOT_FOUND` | `candidate_id` không tồn tại |
| `RATE_LIMITED` | Quá nhiều lần đăng nhập sai |
| `INTERNAL_ERROR` | Lỗi không lường trước |

Trường `message` là tiếng Việt, dành cho người dùng cuối. **Client hiển thị `message`, xử lý
logic theo `code`** (không parse `message`).

## 5. TLS

- Server bọc TLS (tối thiểu TLS 1.2). Client kết nối bằng TLS.
- Cert là tự ký trong môi trường học tập. Bên .NET có hai lựa chọn:
  - **Học tập/nhanh:** đặt `RemoteCertificateValidationCallback` trả về `true` để bỏ qua verify.
  - **Chuẩn hơn:** import `certs/server.crt` vào Trusted Root Certification Authorities của máy
    Windows, rồi kết nối theo đúng tên/địa chỉ có trong SAN.
- Có thể chạy server với `--no-tls` để debug giao thức bằng TCP thuần trước khi bật TLS.

## 6. Lưu ý bắt buộc cho `VotingSystem.Shared`

1. Đọc frame phải **lặp cho tới khi đủ byte** — cả 4 byte header lẫn `length` byte payload.
2. Header dùng `IPAddress.NetworkToHostOrder` (big-endian) khi đọc, `HostToNetworkOrder` khi ghi.
3. Payload UTF-8 **không BOM**.
4. Message **không có `req_id`** là server push → đẩy vào event, không khớp vào request đang chờ.
5. Mỗi request nên có timeout chờ response; nhưng kết nối `SUBSCRIBE_RESULTS` thì để đọc chờ
   vô thời hạn (push đến bất cứ lúc nào).
