"""ClientConnection: một socket = một thread. Đọc frame, định tuyến, trả response.

Mỗi connection có lock riêng cho việc gửi vì thread broadcast và thread request cùng ghi vào
một socket. Exception ngoài dự kiến được log đầy đủ ở server nhưng chỉ trả INTERNAL_ERROR
chung chung ra client, không rò rỉ stack trace.
"""

import json
import logging
import socket
import threading
import time

from src import protocol
from src.errors import ProtocolError, ProtocolVersionMismatch, UnknownType
from src.framing import FrameTooLarge, recv_frame, send_frame
from src.handlers import HANDLERS, HandlerContext

logger = logging.getLogger(__name__)

# Timeout đọc dùng như nhịp thức dậy định kỳ để kiểm tra cờ dừng và làm backstop cho
# connection nửa-chết. Hết timeout mà chưa dừng thì lặp tiếp, KHÔNG đóng — nếu không
# subscriber ngồi im chờ push sẽ bị cắt oan.
_READ_TIMEOUT = 30.0


class ClientConnection:
    def __init__(self, sock, addr, store, sessions, hub, rate_limiter, stop_event):
        self._sock = sock
        self._addr = addr
        self._hub = hub
        self._stop = stop_event
        self._send_lock = threading.Lock()
        self._ctx = HandlerContext(store, sessions, hub, rate_limiter, self)

    def send(self, message: dict) -> None:
        """Gửi một message. Có khoá riêng để request thread và broadcast thread không xen frame."""
        with self._send_lock:
            send_frame(self._sock, message)

    def run(self) -> None:
        peer = "{}:{}".format(*self._addr) if isinstance(self._addr, tuple) else str(self._addr)
        logger.info("kết nối mới từ %s", peer)
        self._sock.settimeout(_READ_TIMEOUT)
        try:
            self._loop(peer)
        finally:
            # Dù thoát vì lý do gì cũng phải gỡ khỏi hub và đóng socket
            self._hub.unsubscribe(self)
            self._close()
            logger.info("ngắt kết nối %s", peer)

    def _loop(self, peer: str) -> None:
        while not self._stop.is_set():
            try:
                frame = recv_frame(self._sock)
            except socket.timeout:
                # Nhịp thức dậy: quay lại kiểm tra cờ dừng rồi chờ tiếp
                continue
            except FrameTooLarge:
                # Chưa đọc payload nên stream đã lệch nhịp, buộc phải đóng sau khi báo lỗi
                self._safe_send(protocol.make_error(
                    protocol.TYPE_ERROR, None,
                    protocol.ERR_PAYLOAD_TOO_LARGE, "Message vượt quá kích thước cho phép."))
                return
            except (json.JSONDecodeError, UnicodeDecodeError):
                # Frame có ranh giới rõ nhờ length-prefix nên stream vẫn khớp, báo lỗi rồi đọc tiếp
                self._safe_send(protocol.make_error(
                    protocol.TYPE_ERROR, None,
                    protocol.ERR_INVALID_JSON, "Nội dung không phải JSON hợp lệ."))
                continue
            except OSError:
                # Socket bị đóng hoặc lỗi mạng
                return

            if frame is None:
                # Peer đóng kết nối sạch
                return

            response = self._process(frame, peer)
            try:
                self.send(response)
            except OSError:
                return

    def _process(self, frame: dict, peer: str) -> dict:
        req_id = frame.get("req_id") if isinstance(frame, dict) else None
        req_type = frame.get("type") if isinstance(frame, dict) else None
        response_type = (protocol.result_type(req_type)
                         if isinstance(req_type, str) and req_type else protocol.TYPE_ERROR)

        started = time.monotonic()
        try:
            if not isinstance(frame, dict):
                raise ProtocolVersionMismatch("Message phải là đối tượng JSON.")
            if frame.get("v") != protocol.VERSION:
                raise ProtocolVersionMismatch()
            if not isinstance(req_type, str) or req_type not in HANDLERS:
                raise UnknownType()

            data = frame.get("data")
            if data is None:
                data = {}
            # Xoá session của request trước để handler không xác thực dùng nhầm phiên cũ
            self._ctx.session = None
            result = HANDLERS[req_type](self._ctx, data)
            response = protocol.make_ok(response_type, req_id, result)
            self._log_request(peer, req_id, req_type, started, protocol.STATUS_OK, None)
            return response
        except ProtocolError as exc:
            self._log_request(peer, req_id, req_type, started, protocol.STATUS_ERROR, exc.code)
            return protocol.make_error(response_type, req_id, exc.code, exc.message)
        except Exception:
            # Lỗi không lường trước: log traceback đầy đủ, giấu chi tiết khỏi client
            logger.exception("lỗi nội bộ khi xử lý %s từ %s", req_type, peer)
            self._log_request(peer, req_id, req_type, started,
                              protocol.STATUS_ERROR, protocol.ERR_INTERNAL_ERROR)
            return protocol.make_error(response_type, req_id,
                                       protocol.ERR_INTERNAL_ERROR, "Đã xảy ra lỗi máy chủ.")

    def _log_request(self, peer, req_id, req_type, started, status, code):
        elapsed_ms = (time.monotonic() - started) * 1000
        # Không log data: có thể chứa mật khẩu hoặc token. Chỉ log siêu dữ liệu.
        logger.info("%s req_id=%s type=%s status=%s%s %.1fms",
                    peer, req_id, req_type, status,
                    " code=" + code if code else "", elapsed_ms)

    def interrupt(self) -> None:
        """Ép recv đang chờ bật ra khi tắt máy, bằng cách đóng nửa đọc của socket."""
        try:
            self._sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            # Socket có thể đã đóng; bỏ qua
            pass

    def _safe_send(self, message: dict) -> None:
        try:
            self.send(message)
        except OSError:
            pass

    def _close(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass
