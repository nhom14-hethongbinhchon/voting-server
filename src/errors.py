"""Lỗi nghiệp vụ. Mỗi lớp mang sẵn code (để client xử lý logic) và message tiếng Việt.

Handler chỉ cần raise lớp phù hợp; tầng connection lo đóng gói thành response lỗi.
"""

from src import protocol


class ProtocolError(Exception):
    """Lỗi có thể trả về client an toàn. code và message mặc định lấy từ lớp con."""

    code = protocol.ERR_INTERNAL_ERROR
    message = "Đã xảy ra lỗi."

    def __init__(self, message: str | None = None):
        # Cho phép ghi đè message khi cần nêu chi tiết, ví dụ tên trường thiếu
        self.message = message or self.message
        super().__init__(self.message)


class BadRequest(ProtocolError):
    code = protocol.ERR_BAD_REQUEST
    message = "Yêu cầu thiếu trường bắt buộc hoặc sai kiểu dữ liệu."


class UnknownType(ProtocolError):
    code = protocol.ERR_UNKNOWN_TYPE
    message = "Loại yêu cầu không được hỗ trợ."


class ProtocolVersionMismatch(ProtocolError):
    code = protocol.ERR_PROTOCOL_VERSION_MISMATCH
    message = "Phiên bản giao thức không khớp."


class InvalidCredentials(ProtocolError):
    code = protocol.ERR_INVALID_CREDENTIALS
    # Thông điệp cố ý mơ hồ: không tiết lộ là sai user hay sai mật khẩu
    message = "Sai tài khoản hoặc mật khẩu."


class Unauthenticated(ProtocolError):
    code = protocol.ERR_UNAUTHENTICATED
    message = "Bạn chưa đăng nhập hoặc phiên đã hết hạn."


class Forbidden(ProtocolError):
    code = protocol.ERR_FORBIDDEN
    message = "Bạn không có quyền thực hiện thao tác này."


class RateLimited(ProtocolError):
    code = protocol.ERR_RATE_LIMITED
    message = "Bạn đã nhập sai quá nhiều lần. Vui lòng thử lại sau ít phút."


class VoteError(ProtocolError):
    """Gốc chung cho các lỗi khi bỏ phiếu, để store raise thống nhất."""


class AlreadyVoted(VoteError):
    code = protocol.ERR_ALREADY_VOTED
    message = "Cử tri này đã bỏ phiếu."


class ElectionNotOpen(VoteError):
    code = protocol.ERR_ELECTION_NOT_OPEN
    message = "Cuộc bầu cử chưa được mở."


class ElectionClosed(VoteError):
    code = protocol.ERR_ELECTION_CLOSED
    message = "Cuộc bầu cử đã đóng."


class CandidateNotFound(VoteError):
    code = protocol.ERR_CANDIDATE_NOT_FOUND
    message = "Không tìm thấy ứng viên."
