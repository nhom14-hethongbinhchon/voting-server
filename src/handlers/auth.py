"""Xác thực: LOGIN (cử tri), ADMIN_LOGIN (quản trị), LOGOUT."""

import secrets

from src.errors import InvalidCredentials
from src.handlers import require_str
from src.security import hash_password, verify_password

# Hash giả để verify khi không tìm thấy tài khoản, giữ thời gian phản hồi tương đương
# nhằm không lộ việc tài khoản có tồn tại hay không qua timing.
_DUMMY_HASH = hash_password(secrets.token_hex(8))


def handle_login(ctx, data):
    voter_id = require_str(data, "voter_id")
    password = require_str(data, "password")

    # Chặn brute-force trước khi verify; nếu đang bị khoá thì raise RATE_LIMITED luôn
    ctx.rate_limiter.check(voter_id)

    voter = ctx.store.find_voter(voter_id)
    if voter is None:
        verify_password(password, _DUMMY_HASH)
        ctx.rate_limiter.record_failure(voter_id)
        raise InvalidCredentials()
    if not verify_password(password, voter["password_hash"]):
        ctx.rate_limiter.record_failure(voter_id)
        raise InvalidCredentials()

    ctx.rate_limiter.record_success(voter_id)
    token = ctx.sessions.create(voter_id, "voter")
    election = ctx.store.get_election()
    return {
        "token": token,
        "voter_name": voter["full_name"],
        "has_voted": voter["has_voted"],
        "election_status": election["status"],
    }


def handle_admin_login(ctx, data):
    username = require_str(data, "username")
    password = require_str(data, "password")

    ctx.rate_limiter.check(username)

    admin = ctx.store.find_admin(username)
    if admin is None:
        verify_password(password, _DUMMY_HASH)
        ctx.rate_limiter.record_failure(username)
        raise InvalidCredentials()
    if not verify_password(password, admin["password_hash"]):
        ctx.rate_limiter.record_failure(username)
        raise InvalidCredentials()

    ctx.rate_limiter.record_success(username)
    token = ctx.sessions.create(username, "admin")
    return {
        "token": token,
        "display_name": admin["display_name"],
    }


def handle_logout(ctx, data):
    # Đăng xuất cho cả cử tri lẫn admin; thu hồi token dù nó còn hạn hay không (idempotent)
    token = require_str(data, "token")
    ctx.sessions.revoke(token)
    return {}
