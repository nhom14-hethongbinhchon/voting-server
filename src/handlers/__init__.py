"""Bảng định tuyến type -> handler, cùng hạ tầng dùng chung: context, decorator, đọc trường.

Các submodule (auth, voting, admin) import helper từ đây, nên phần import submodule phải nằm
CUỐI file — lúc đó helper đã được định nghĩa, tránh vòng lặp import.
"""

import functools

from src import protocol
from src.errors import BadRequest, Forbidden, Unauthenticated


class HandlerContext:
    """Bó các thành phần dùng chung mà handler cần. Mỗi connection giữ một context riêng."""

    __slots__ = ("store", "sessions", "hub", "rate_limiter", "conn", "session")

    def __init__(self, store, sessions, hub, rate_limiter, conn):
        self.store = store
        self.sessions = sessions
        self.hub = hub
        self.rate_limiter = rate_limiter
        self.conn = conn
        # Decorator require_role gán session của request hiện tại vào đây
        self.session = None


def require_str(data: dict, key: str) -> str:
    """Lấy một trường chuỗi bắt buộc, không rỗng. Raise BadRequest nếu thiếu hoặc sai kiểu."""
    if not isinstance(data, dict):
        raise BadRequest("Trường 'data' phải là đối tượng.")
    value = data.get(key)
    if not isinstance(value, str) or value == "":
        raise BadRequest("Thiếu hoặc sai trường '{}'.".format(key))
    return value


def require_int(data: dict, key: str) -> int:
    """Lấy một trường số nguyên bắt buộc. bool bị loại vì là lớp con của int trong Python."""
    if not isinstance(data, dict):
        raise BadRequest("Trường 'data' phải là đối tượng.")
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise BadRequest("Thiếu hoặc sai trường '{}'.".format(key))
    return value


def require_role(role: str):
    """Decorator xác thực: đọc data.token, resolve phiên, kiểm tra vai trò, gắn ctx.session."""

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(ctx, data):
            # Thiếu token và token hết hạn đều trả UNAUTHENTICATED, không phân biệt
            token = data.get("token") if isinstance(data, dict) else None
            if not isinstance(token, str) or token == "":
                raise Unauthenticated()
            session = ctx.sessions.resolve(token)
            if session is None:
                raise Unauthenticated()
            if session.role != role:
                raise Forbidden()
            ctx.session = session
            return fn(ctx, data)

        return wrapper

    return decorator


def handle_ping(ctx, data):
    """Kiểm tra sức khoẻ, không thuộc hợp đồng client/admin. Echo lại data để tiện debug."""
    return {"pong": True, "echo": data if isinstance(data, dict) else None}


# Import submodule ở cuối để chúng thấy được các helper phía trên
from src.handlers import admin, auth, voting

# Bảng định tuyến. Type không có trong bảng sẽ nhận lỗi UNKNOWN_TYPE ở tầng connection.
HANDLERS = {
    protocol.LOGIN: auth.handle_login,
    protocol.ADMIN_LOGIN: auth.handle_admin_login,
    protocol.LOGOUT: auth.handle_logout,
    protocol.GET_CANDIDATES: voting.handle_get_candidates,
    protocol.CAST_VOTE: voting.handle_cast_vote,
    protocol.GET_MY_STATUS: voting.handle_get_my_status,
    protocol.GET_RESULTS: admin.handle_get_results,
    protocol.GET_STATS: admin.handle_get_stats,
    protocol.SUBSCRIBE_RESULTS: admin.handle_subscribe,
    protocol.UNSUBSCRIBE_RESULTS: admin.handle_unsubscribe,
    protocol.OPEN_ELECTION: admin.handle_open_election,
    protocol.CLOSE_ELECTION: admin.handle_close_election,
    protocol.PING: handle_ping,
}
