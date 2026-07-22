"""Test xác thực: đăng nhập đúng/sai, phiên hợp lệ/hết hạn, FORBIDDEN, UNAUTHENTICATED, rate limit."""

import json
import os
import tempfile
import unittest

from src.broadcast import BroadcastHub
from src.errors import Forbidden, InvalidCredentials, RateLimited, Unauthenticated
from src.handlers import HandlerContext, admin, auth
from src.security import hash_password
from src.sessions import LoginRateLimiter, SessionManager
from src.store import DataStore


def write_seed(data_dir: str) -> None:
    def dump(name, obj):
        with open(os.path.join(data_dir, name), "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)

    dump("election.json", {"title": "T", "status": "open",
                           "opened_at": None, "closed_at": None})
    dump("candidates.json", [{"id": 1, "name": "A", "description": "", "photo_url": ""}])
    dump("voters.json", [
        {"voter_id": "HS001", "full_name": "Cử tri A",
         "password_hash": hash_password("123456"), "has_voted": False, "voted_at": None},
    ])
    dump("admins.json", [
        {"username": "admin", "display_name": "BTC", "password_hash": hash_password("admin123")},
    ])
    dump("votes.json", [])


class AuthTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        write_seed(self._tmp.name)
        self.store = DataStore(self._tmp.name)

    def make_ctx(self, ttl=7200, max_attempts=5, lockout=300):
        sessions = SessionManager(ttl)
        rate_limiter = LoginRateLimiter(max_attempts, lockout)
        return HandlerContext(self.store, sessions, BroadcastHub(), rate_limiter, conn=None)


class TestLogin(AuthTestBase):
    def test_login_success(self):
        ctx = self.make_ctx()
        result = auth.handle_login(ctx, {"voter_id": "HS001", "password": "123456"})
        self.assertEqual(result["voter_name"], "Cử tri A")
        self.assertFalse(result["has_voted"])
        session = ctx.sessions.resolve(result["token"])
        self.assertIsNotNone(session)
        self.assertEqual(session.role, "voter")
        self.assertEqual(session.principal_id, "HS001")

    def test_login_wrong_password(self):
        ctx = self.make_ctx()
        with self.assertRaises(InvalidCredentials):
            auth.handle_login(ctx, {"voter_id": "HS001", "password": "sai"})

    def test_login_unknown_voter_same_error(self):
        # User không tồn tại phải trả cùng lỗi như sai mật khẩu, không lộ user có tồn tại không
        ctx = self.make_ctx()
        with self.assertRaises(InvalidCredentials):
            auth.handle_login(ctx, {"voter_id": "KHONG_CO", "password": "123456"})

    def test_admin_login_success(self):
        ctx = self.make_ctx()
        result = auth.handle_admin_login(ctx, {"username": "admin", "password": "admin123"})
        self.assertEqual(result["display_name"], "BTC")
        self.assertEqual(ctx.sessions.resolve(result["token"]).role, "admin")

    def test_admin_login_wrong(self):
        ctx = self.make_ctx()
        with self.assertRaises(InvalidCredentials):
            auth.handle_admin_login(ctx, {"username": "admin", "password": "sai"})

    def test_logout_revokes_token(self):
        ctx = self.make_ctx()
        token = auth.handle_login(ctx, {"voter_id": "HS001", "password": "123456"})["token"]
        auth.handle_logout(ctx, {"token": token})
        self.assertIsNone(ctx.sessions.resolve(token))


class TestSessions(AuthTestBase):
    def test_resolve_valid_then_revoke(self):
        manager = SessionManager(7200)
        token = manager.create("HS001", "voter")
        self.assertIsNotNone(manager.resolve(token))
        manager.revoke(token)
        self.assertIsNone(manager.resolve(token))

    def test_expired_session_not_resolved(self):
        # TTL âm khiến phiên hết hạn ngay khi tạo, kiểm tra nhánh hết hạn một cách tất định
        manager = SessionManager(-1)
        token = manager.create("HS001", "voter")
        self.assertIsNone(manager.resolve(token))

    def test_purge_removes_expired(self):
        manager = SessionManager(-1)
        manager.create("HS001", "voter")
        manager.create("HS002", "voter")
        self.assertEqual(manager.purge_expired(), 2)


class TestAuthorization(AuthTestBase):
    def test_voter_token_forbidden_on_admin_api(self):
        ctx = self.make_ctx()
        voter_token = auth.handle_login(ctx, {"voter_id": "HS001", "password": "123456"})["token"]
        with self.assertRaises(Forbidden):
            admin.handle_get_results(ctx, {"token": voter_token})

    def test_missing_token_unauthenticated(self):
        ctx = self.make_ctx()
        with self.assertRaises(Unauthenticated):
            admin.handle_get_results(ctx, {})

    def test_bad_token_unauthenticated(self):
        ctx = self.make_ctx()
        with self.assertRaises(Unauthenticated):
            admin.handle_get_results(ctx, {"token": "khong-hop-le"})


class TestRateLimit(AuthTestBase):
    def test_locked_after_max_attempts(self):
        ctx = self.make_ctx(max_attempts=5, lockout=300)
        # 5 lần sai đầu vẫn là INVALID_CREDENTIALS
        for _ in range(5):
            with self.assertRaises(InvalidCredentials):
                auth.handle_login(ctx, {"voter_id": "HS001", "password": "sai"})
        # Lần thứ 6 bị khoá, kể cả mật khẩu đúng cũng không qua
        with self.assertRaises(RateLimited):
            auth.handle_login(ctx, {"voter_id": "HS001", "password": "123456"})


if __name__ == "__main__":
    unittest.main()
