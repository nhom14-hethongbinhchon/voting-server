"""Test framing: round-trip, tiếng Việt có dấu, frame bị phân mảnh, frame quá lớn, peer đóng."""

import json
import socket
import struct
import threading
import unittest

from src.framing import MAX_FRAME, FrameTooLarge, recv_frame, send_frame


class TestFraming(unittest.TestCase):
    def setUp(self):
        # socketpair cho ta hai đầu socket thật, không cần server để test framing
        self.a, self.b = socket.socketpair()
        self.addCleanup(self.a.close)
        self.addCleanup(self.b.close)

    def test_round_trip(self):
        obj = {"v": 1, "type": "PING", "data": {"n": 42, "flag": True}}
        send_frame(self.a, obj)
        self.assertEqual(recv_frame(self.b), obj)

    def test_vietnamese_utf8(self):
        # ensure_ascii=False phải giữ nguyên dấu tiếng Việt qua vòng round-trip
        obj = {"type": "LOGIN_RESULT", "data": {"voter_name": "Nguyễn Thị Bưởi Đỗ"}}
        send_frame(self.a, obj)
        received = recv_frame(self.b)
        self.assertEqual(received["data"]["voter_name"], "Nguyễn Thị Bưởi Đỗ")

    def test_fragmented_read(self):
        # Gửi từng byte một để ép _recv_exactly phải lặp recv nhiều lần
        obj = {"type": "CAST_VOTE", "data": {"candidate_id": 3}}
        payload = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        frame = struct.pack(">I", len(payload)) + payload

        result = {}

        def reader():
            result["obj"] = recv_frame(self.b)

        t = threading.Thread(target=reader)
        t.start()
        for byte in frame:
            self.a.sendall(bytes([byte]))
        t.join(timeout=5)
        self.assertFalse(t.is_alive())
        self.assertEqual(result["obj"], obj)

    def test_frame_too_large(self):
        # Chỉ cần gửi header khai length vượt giới hạn; recv_frame phải raise trước khi đọc payload
        self.a.sendall(struct.pack(">I", MAX_FRAME + 1))
        with self.assertRaises(FrameTooLarge):
            recv_frame(self.b)

    def test_send_rejects_oversized(self):
        big = {"data": "x" * (MAX_FRAME + 10)}
        with self.assertRaises(FrameTooLarge):
            send_frame(self.a, big)

    def test_peer_closed_returns_none(self):
        # Đóng đầu ghi trước khi gửi gì: recv_frame phải trả None chứ không treo hay lỗi
        self.a.close()
        self.assertIsNone(recv_frame(self.b))

    def test_truncated_after_header_returns_none(self):
        # Header hứa 100 byte nhưng chỉ gửi 10 rồi đóng: coi như stream đứt, trả None
        self.a.sendall(struct.pack(">I", 100) + b"0123456789")
        self.a.close()
        self.assertIsNone(recv_frame(self.b))


if __name__ == "__main__":
    unittest.main()
