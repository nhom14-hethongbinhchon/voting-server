"""Quản lý phiên đăng nhập (token -> phiên) và giới hạn tốc độ đăng nhập sai.

Cả hai đều là trạng thái xác thực dùng chung, có khoá riêng, an toàn khi nhiều thread truy cập.
Dùng đồng hồ monotonic cho việc hết hạn để không bị ảnh hưởng khi giờ hệ thống bị chỉnh.
"""

import threading
import time

from src.errors import RateLimited
from src.security import new_token


class Session:
    __slots__ = ("token", "principal_id", "role", "created_at", "expires_at")

    def __init__(self, token: str, principal_id: str, role: str,
                 created_at: float, expires_at: float):
        self.token = token
        self.principal_id = principal_id
        self.role = role
        self.created_at = created_at
        self.expires_at = expires_at


class SessionManager:
    """Bảng token -> Session, hết hạn sau ttl_seconds kể từ lúc tạo."""

    def __init__(self, ttl_seconds: int):
        self._ttl = ttl_seconds
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def create(self, principal_id: str, role: str) -> str:
        """Tạo phiên mới, trả token. role là 'voter' hoặc 'admin'."""
        token = new_token()
        now = time.monotonic()
        session = Session(token, principal_id, role, now, now + self._ttl)
        with self._lock:
            self._sessions[token] = session
        return token

    def resolve(self, token: str) -> Session | None:
        """Trả Session nếu token hợp lệ và chưa hết hạn, ngược lại None.

        Tiện thể xoá luôn token đã hết hạn khi gặp, để bảng không phình mãi.
        """
        now = time.monotonic()
        with self._lock:
            session = self._sessions.get(token)
            if session is None:
                return None
            if session.expires_at <= now:
                del self._sessions[token]
                return None
            return session

    def revoke(self, token: str) -> None:
        with self._lock:
            self._sessions.pop(token, None)

    def purge_expired(self) -> int:
        """Xoá mọi phiên đã hết hạn. Trả số phiên đã dọn. Gọi định kỳ từ thread nền."""
        now = time.monotonic()
        with self._lock:
            dead = [t for t, s in self._sessions.items() if s.expires_at <= now]
            for token in dead:
                del self._sessions[token]
        return len(dead)


class LoginRateLimiter:
    """Khoá đăng nhập sau quá nhiều lần sai cho cùng một danh tính.

    Đếm theo key (voter_id hoặc username). Vượt max_attempts thì khoá trong lockout_seconds.
    """

    def __init__(self, max_attempts: int, lockout_seconds: int):
        self._max = max_attempts
        self._lockout = lockout_seconds
        self._lock = threading.Lock()
        self._state: dict[str, dict] = {}

    def check(self, key: str) -> None:
        """Raise RateLimited nếu key đang bị khoá. Gọi trước khi verify mật khẩu."""
        with self._lock:
            entry = self._state.get(key)
            if entry and entry["locked_until"] > time.monotonic():
                raise RateLimited()

    def record_failure(self, key: str) -> None:
        with self._lock:
            entry = self._state.setdefault(key, {"fails": 0, "locked_until": 0.0})
            now = time.monotonic()
            # Nếu lần khoá trước đã hết hạn thì bắt đầu đếm lại từ đầu
            if entry["fails"] >= self._max and entry["locked_until"] <= now:
                entry["fails"] = 0
            entry["fails"] += 1
            if entry["fails"] >= self._max:
                entry["locked_until"] = now + self._lockout

    def record_success(self, key: str) -> None:
        # Đăng nhập đúng thì xoá lịch sử sai để không cấn lần sau
        with self._lock:
            self._state.pop(key, None)
