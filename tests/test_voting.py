"""Test bỏ phiếu: luồng bình thường, các lỗi, phát realtime, và test đua chống bầu trùng."""

import json
import os
import tempfile
import threading
import unittest

from src.broadcast import BroadcastHub
from src.errors import AlreadyVoted, CandidateNotFound, ElectionNotOpen
from src.handlers import HandlerContext, voting
from src.sessions import LoginRateLimiter, SessionManager
from src.store import DataStore


def write_seed(data_dir: str, status: str = "open") -> None:
    def dump(name, obj):
        with open(os.path.join(data_dir, name), "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)

    dump("election.json", {"title": "T", "status": status,
                           "opened_at": None, "closed_at": None})
    dump("candidates.json", [
        {"id": 1, "name": "A", "description": "", "photo_url": ""},
        {"id": 2, "name": "B", "description": "", "photo_url": ""},
    ])
    dump("voters.json", [
        {"voter_id": "HS001", "full_name": "Cử tri A",
         "password_hash": "x", "has_voted": False, "voted_at": None},
        {"voter_id": "HS002", "full_name": "Cử tri B",
         "password_hash": "x", "has_voted": False, "voted_at": None},
    ])
    dump("admins.json", [{"username": "admin", "display_name": "BTC", "password_hash": "x"}])
    dump("votes.json", [])


class FakeConn:
    """Connection giả cho hub: chỉ lưu lại message được đẩy tới để kiểm tra."""

    def __init__(self):
        self.received = []

    def send(self, message):
        self.received.append(message)


class DeadConn:
    """Connection giả đã chết: mọi lần gửi đều lỗi, để test hub tự gỡ nó ra."""

    def send(self, message):
        raise OSError("kết nối đã đóng")


class TestBroadcastHub(unittest.TestCase):
    def test_dead_subscriber_removed_and_others_unaffected(self):
        hub = BroadcastHub()
        dead = DeadConn()
        alive = FakeConn()
        hub.subscribe(dead)
        hub.subscribe(alive)

        # Một subscriber lỗi không được làm hỏng buổi phát: alive vẫn nhận được
        hub.publish({"type": "RESULTS_UPDATE", "data": {"total_votes": 1}})
        self.assertEqual(len(alive.received), 1)
        # dead đã bị tự động gỡ khỏi hub
        self.assertEqual(hub.subscriber_count(), 1)

        # Lần phát sau chỉ còn alive, không còn đụng tới dead
        hub.publish({"type": "RESULTS_UPDATE", "data": {"total_votes": 2}})
        self.assertEqual(len(alive.received), 2)


class VotingTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        write_seed(self._tmp.name, status="open")
        self.store = DataStore(self._tmp.name)
        self.hub = BroadcastHub()
        self.sessions = SessionManager(7200)
        self.ctx = HandlerContext(self.store, self.sessions, self.hub,
                                  LoginRateLimiter(5, 300), conn=None)

    def voter_token(self, voter_id="HS001"):
        return self.sessions.create(voter_id, "voter")


class TestVotingHandlers(VotingTestBase):
    def test_get_candidates(self):
        data = voting.handle_get_candidates(self.ctx, {"token": self.voter_token()})
        self.assertEqual(len(data["candidates"]), 2)

    def test_cast_vote_success(self):
        token = self.voter_token()
        result = voting.handle_cast_vote(self.ctx, {"token": token, "candidate_id": 1})
        self.assertIn("receipt", result)
        self.assertTrue(self.store.find_voter("HS001")["has_voted"])

    def test_cast_vote_twice(self):
        token = self.voter_token()
        voting.handle_cast_vote(self.ctx, {"token": token, "candidate_id": 1})
        with self.assertRaises(AlreadyVoted):
            voting.handle_cast_vote(self.ctx, {"token": token, "candidate_id": 1})

    def test_cast_vote_candidate_not_found(self):
        with self.assertRaises(CandidateNotFound):
            voting.handle_cast_vote(self.ctx, {"token": self.voter_token(), "candidate_id": 99})

    def test_cast_vote_election_not_open(self):
        write_seed(self._tmp.name, status="not_started")
        self.store = DataStore(self._tmp.name)
        self.ctx.store = self.store
        with self.assertRaises(ElectionNotOpen):
            voting.handle_cast_vote(self.ctx, {"token": self.voter_token(), "candidate_id": 1})

    def test_my_status(self):
        token = self.voter_token()
        before = voting.handle_get_my_status(self.ctx, {"token": token})
        self.assertFalse(before["has_voted"])
        voting.handle_cast_vote(self.ctx, {"token": token, "candidate_id": 1})
        after = voting.handle_get_my_status(self.ctx, {"token": token})
        self.assertTrue(after["has_voted"])

    def test_vote_broadcasts_results_update(self):
        # Subscriber phải nhận RESULTS_UPDATE ngay sau một phiếu hợp lệ
        sub = FakeConn()
        self.hub.subscribe(sub)
        voting.handle_cast_vote(self.ctx, {"token": self.voter_token(), "candidate_id": 1})
        self.assertEqual(len(sub.received), 1)
        push = sub.received[0]
        self.assertEqual(push["type"], "RESULTS_UPDATE")
        self.assertNotIn("req_id", push)
        self.assertEqual(push["data"]["total_votes"], 1)


class TestVoteRace(VotingTestBase):
    def test_twenty_threads_one_success(self):
        # 20 thread cùng bầu bằng một tài khoản; critical section trong record_vote phải
        # đảm bảo đúng 1 phiếu được ghi, 19 thread còn lại nhận ALREADY_VOTED.
        n = 20
        barrier = threading.Barrier(n)
        successes = []
        already = []
        lock = threading.Lock()

        def worker():
            barrier.wait()
            try:
                self.store.record_vote("HS001", 1)
                with lock:
                    successes.append(1)
            except AlreadyVoted:
                with lock:
                    already.append(1)

        threads = [threading.Thread(target=worker) for _ in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(already), n - 1)
        # Trên đĩa cũng chỉ đúng một phiếu
        with open(os.path.join(self._tmp.name, "votes.json"), encoding="utf-8") as f:
            votes = json.load(f)
        self.assertEqual(len(votes), 1)
        self.assertTrue(self.store.find_voter("HS001")["has_voted"])


if __name__ == "__main__":
    unittest.main()
