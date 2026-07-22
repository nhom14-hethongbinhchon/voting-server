"""Đóng/mở khung message trên TCP: 4-byte length prefix (big-endian) + payload JSON UTF-8.

Module lá, không import module nào khác trong repo. TCP là byte stream không có ranh giới
message, nên mọi lần đọc phải lặp recv cho tới khi đủ số byte cần.
"""

import json
import struct

# Giới hạn 1 MiB. Vượt quá coi là bất thường, không cấp phát bộ nhớ theo length client khai báo.
MAX_FRAME = 1024 * 1024

# Header độ dài: unsigned 32-bit big-endian
_HEADER = struct.Struct(">I")


class FrameTooLarge(Exception):
    """Frame vượt MAX_FRAME. Tầng connection dịch thành lỗi PAYLOAD_TOO_LARGE rồi đóng kết nối."""

    def __init__(self, length: int):
        super().__init__("frame {} byte vượt giới hạn {}".format(length, MAX_FRAME))
        self.length = length


def _recv_exactly(sock, n: int) -> bytes | None:
    """Đọc đúng n byte. Trả None nếu peer đóng kết nối trước khi đủ (stream kết thúc sớm)."""
    chunks = []
    remaining = n
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            # recv trả b"" nghĩa là peer đã đóng đầu ghi
            return None
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def send_frame(sock, obj: dict) -> None:
    """Serialize obj thành JSON UTF-8, ghi header độ dài rồi payload trong một lần sendall."""
    payload = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    if len(payload) > MAX_FRAME:
        raise FrameTooLarge(len(payload))
    # Gộp header và payload để tránh gửi hai gói nhỏ và để sendall lo phần phân mảnh
    sock.sendall(_HEADER.pack(len(payload)) + payload)


def recv_frame(sock) -> dict | None:
    """Đọc trọn một frame và trả về dict đã parse.

    Trả None khi peer đóng kết nối sạch. Raise FrameTooLarge nếu length vượt giới hạn.
    Raise json.JSONDecodeError nếu payload không phải JSON hợp lệ.
    """
    header = _recv_exactly(sock, _HEADER.size)
    if header is None:
        return None
    (length,) = _HEADER.unpack(header)
    # Kiểm tra trước khi đọc payload để không đọc/nuốt một khối khổng lồ do client bịa length
    if length > MAX_FRAME:
        raise FrameTooLarge(length)
    payload = _recv_exactly(sock, length)
    if payload is None:
        # Header hứa length byte nhưng stream đứt giữa chừng
        return None
    return json.loads(payload.decode("utf-8"))
