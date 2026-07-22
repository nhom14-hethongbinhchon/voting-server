"""BroadcastHub: giữ danh sách subscriber và đẩy message realtime tới tất cả.

Lỗi gửi ở một subscriber không được làm hỏng các subscriber khác: bắt exception, log,
và tự động gỡ connection chết ra khỏi hub.
"""

import logging
import threading

logger = logging.getLogger(__name__)


class BroadcastHub:
    def __init__(self):
        self._subscribers = set()
        self._lock = threading.Lock()

    def subscribe(self, conn) -> None:
        with self._lock:
            self._subscribers.add(conn)

    def unsubscribe(self, conn) -> None:
        with self._lock:
            self._subscribers.discard(conn)

    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)

    def publish(self, message: dict) -> None:
        """Gửi message tới mọi subscriber. Không giữ lock trong lúc gửi qua mạng."""
        with self._lock:
            # Lặp trên bản sao để subscribe/unsubscribe trong lúc gửi không làm hỏng vòng lặp
            targets = list(self._subscribers)

        dead = []
        for conn in targets:
            try:
                conn.send(message)
            except Exception:
                # Một subscriber chậm hoặc đã ngắt không được kéo sập cả buổi phát
                logger.warning("gỡ subscriber do lỗi khi gửi push", exc_info=True)
                dead.append(conn)

        if dead:
            with self._lock:
                for conn in dead:
                    self._subscribers.discard(conn)
