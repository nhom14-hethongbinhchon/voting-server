"""Server: accept loop, mỗi kết nối một thread, thread dọn phiên hết hạn, tắt máy êm.

Bọc TLS (nếu có ssl_context) diễn ra trong thread của từng connection để cái bắt tay chậm
của một client không chặn việc accept các client khác.
"""

import logging
import socket
import ssl
import threading

from src.connection import ClientConnection

logger = logging.getLogger(__name__)

# Hàng đợi kết nối chờ accept
_BACKLOG = 64
# Nhịp để accept loop và thread dọn phiên kiểm tra cờ dừng
_ACCEPT_TICK = 1.0
_PURGE_INTERVAL = 60.0
# Giới hạn thời gian bắt tay TLS để client xấu không giữ thread mãi
_HANDSHAKE_TIMEOUT = 15.0


class Server:
    def __init__(self, config, store, sessions, hub, rate_limiter, ssl_context=None):
        self._host = config.get("host", "0.0.0.0")
        self._port = int(config.get("port", 8443))
        self._store = store
        self._sessions = sessions
        self._hub = hub
        self._rate_limiter = rate_limiter
        self._ssl_context = ssl_context

        self._stop = threading.Event()
        self._listener = None
        self._lock = threading.Lock()
        self._conns = set()
        self._threads = []
        self._shutdown_done = False

    def serve_forever(self) -> None:
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind((self._host, self._port))
        self._listener.listen(_BACKLOG)
        self._listener.settimeout(_ACCEPT_TICK)

        purge_thread = threading.Thread(target=self._purge_loop, name="purge", daemon=True)
        purge_thread.start()

        scheme = "TLS" if self._ssl_context else "TCP (không mã hoá)"
        logger.info("server lắng nghe %s trên %s:%d", scheme, self._host, self._port)

        try:
            while not self._stop.is_set():
                try:
                    raw, addr = self._listener.accept()
                except socket.timeout:
                    # Nhịp thức dậy để dọn thread đã kết thúc và kiểm tra cờ dừng
                    self._prune_threads()
                    continue
                except OSError:
                    # Listener bị đóng khi tắt máy
                    break
                thread = threading.Thread(target=self._serve_connection,
                                          args=(raw, addr), daemon=True)
                with self._lock:
                    self._threads.append(thread)
                thread.start()
        finally:
            self.shutdown()

    def request_stop(self) -> None:
        """Yêu cầu dừng từ bên ngoài (ví dụ signal handler). An toàn gọi từ thread khác."""
        self._stop.set()
        # Đóng listener để accept đang chờ bật ra ngay thay vì đợi hết tick
        if self._listener is not None:
            try:
                self._listener.close()
            except OSError:
                pass

    def _serve_connection(self, raw, addr) -> None:
        sock = raw
        try:
            if self._ssl_context is not None:
                raw.settimeout(_HANDSHAKE_TIMEOUT)
                try:
                    sock = self._ssl_context.wrap_socket(raw, server_side=True)
                except (ssl.SSLError, OSError) as exc:
                    logger.warning("bắt tay TLS thất bại từ %s: %s", addr, exc)
                    raw.close()
                    return

            conn = ClientConnection(sock, addr, self._store, self._sessions,
                                    self._hub, self._rate_limiter, self._stop)
            with self._lock:
                self._conns.add(conn)
            try:
                conn.run()
            finally:
                with self._lock:
                    self._conns.discard(conn)
        except Exception:
            logger.exception("lỗi khi phục vụ %s", addr)

    def _purge_loop(self) -> None:
        # Event.wait trả True khi dừng, False khi hết interval; nhờ vậy thoát ngay khi tắt máy
        while not self._stop.wait(_PURGE_INTERVAL):
            removed = self._sessions.purge_expired()
            if removed:
                logger.info("đã dọn %d phiên hết hạn", removed)

    def _prune_threads(self) -> None:
        with self._lock:
            self._threads = [t for t in self._threads if t.is_alive()]

    def shutdown(self) -> None:
        """Đóng listener, ngắt mọi connection, chờ thread thoát. Idempotent."""
        with self._lock:
            if self._shutdown_done:
                return
            self._shutdown_done = True
            conns = list(self._conns)
            threads = list(self._threads)

        self._stop.set()
        if self._listener is not None:
            try:
                self._listener.close()
            except OSError:
                pass

        logger.info("đang tắt máy, ngắt %d kết nối...", len(conns))
        for conn in conns:
            conn.interrupt()
        for thread in threads:
            thread.join(timeout=2.0)
        logger.info("đã tắt máy")
