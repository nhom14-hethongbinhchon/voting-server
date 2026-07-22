"""Hằng số giao thức và hàm dựng message. Một chỗ duy nhất định nghĩa mọi chuỗi type và code.

Module lá: không import module nào khác trong repo.
"""

# Phiên bản giao thức. Client gửi v khác 1 sẽ bị từ chối.
VERSION = 1

STATUS_OK = "ok"
STATUS_ERROR = "error"

# Hậu tố tên response. Response của FOO luôn là FOO_RESULT.
RESULT_SUFFIX = "_RESULT"

# Type dùng cho lỗi xảy ra trước khi kịp biết request type (JSON hỏng, frame quá lớn)
TYPE_ERROR = "ERROR"

# Request type của cử tri
LOGIN = "LOGIN"
GET_CANDIDATES = "GET_CANDIDATES"
CAST_VOTE = "CAST_VOTE"
GET_MY_STATUS = "GET_MY_STATUS"
LOGOUT = "LOGOUT"

# Request type của quản trị
ADMIN_LOGIN = "ADMIN_LOGIN"
GET_RESULTS = "GET_RESULTS"
GET_STATS = "GET_STATS"
SUBSCRIBE_RESULTS = "SUBSCRIBE_RESULTS"
UNSUBSCRIBE_RESULTS = "UNSUBSCRIBE_RESULTS"
OPEN_ELECTION = "OPEN_ELECTION"
CLOSE_ELECTION = "CLOSE_ELECTION"

# Kiểm tra sức khoẻ, không thuộc hợp đồng client/admin nhưng tiện cho việc test
PING = "PING"

# Message server tự đẩy xuống, không có req_id
RESULTS_UPDATE = "RESULTS_UPDATE"
ELECTION_STATE_CHANGED = "ELECTION_STATE_CHANGED"

# Mã lỗi. Client xử lý logic theo code, hiển thị message.
ERR_INVALID_JSON = "INVALID_JSON"
ERR_BAD_REQUEST = "BAD_REQUEST"
ERR_UNKNOWN_TYPE = "UNKNOWN_TYPE"
ERR_PROTOCOL_VERSION_MISMATCH = "PROTOCOL_VERSION_MISMATCH"
ERR_PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
ERR_INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
ERR_UNAUTHENTICATED = "UNAUTHENTICATED"
ERR_FORBIDDEN = "FORBIDDEN"
ERR_ALREADY_VOTED = "ALREADY_VOTED"
ERR_ELECTION_NOT_OPEN = "ELECTION_NOT_OPEN"
ERR_ELECTION_CLOSED = "ELECTION_CLOSED"
ERR_CANDIDATE_NOT_FOUND = "CANDIDATE_NOT_FOUND"
ERR_RATE_LIMITED = "RATE_LIMITED"
ERR_INTERNAL_ERROR = "INTERNAL_ERROR"

# Trạng thái bầu cử
ELECTION_NOT_STARTED = "not_started"
ELECTION_OPEN = "open"
ELECTION_CLOSED_STATE = "closed"


def result_type(request_type: str) -> str:
    """Tên response tương ứng với một request type."""
    return request_type + RESULT_SUFFIX


def make_ok(response_type: str, req_id, data: dict) -> dict:
    """Dựng response thành công. req_id echo lại nguyên văn của request."""
    return {
        "v": VERSION,
        "type": response_type,
        "req_id": req_id,
        "status": STATUS_OK,
        "data": data,
    }


def make_error(response_type: str, req_id, code: str, message: str) -> dict:
    """Dựng response lỗi. Bỏ req_id nếu chưa parse được (JSON hỏng, frame quá lớn)."""
    envelope = {
        "v": VERSION,
        "type": response_type,
        "status": STATUS_ERROR,
        "error": {"code": code, "message": message},
    }
    if req_id is not None:
        envelope["req_id"] = req_id
    return envelope


def make_push(push_type: str, data: dict) -> dict:
    """Dựng message server đẩy xuống. Không có req_id để client phân biệt với response."""
    return {
        "v": VERSION,
        "type": push_type,
        "data": data,
    }
