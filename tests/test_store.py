"""Test DataStore: ghi phiếu nguyên tử, kiểm phiếu, thống kê, phiếu kín, ghi atomic, bền vững."""

import glob
import json
import os
import tempfile
import unittest

from src.errors import AlreadyVoted, CandidateNotFound, ElectionClosed, ElectionNotOpen
from src.store import DataStore


def read_json(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read_text(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def write_seed(data_dir: str, status: str = "open") -> None:
    def dump(name, obj):
        with open(os.path.join(data_dir, name), "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)

    dump("election.json", {"title": "T", "status": status,
                           "opened_at": None, "closed_at": None})
    dump("candidates.json", [
        {"id": 1, "name": "Ứng viên Một", "description": "", "photo_url": ""},
        {"id": 2, "name": "Ứng viên Hai", "description": "", "photo_url": ""},
    ])
    dump("voters.json", [
        {"voter_id": "HS001", "full_name": "Cử tri A",
         "password_hash": "x", "has_voted": False, "voted_at": None},
        {"voter_id": "HS002", "full_name": "Cử tri B",
         "password_hash": "x", "has_voted": False, "voted_at": None},
    ])
    dump("admins.json", [{"username": "admin", "display_name": "BTC", "password_hash": "x"}])
    dump("votes.json", [])


class TestDataStore(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = self._tmp.name
        write_seed(self.dir, status="open")
        self.store = DataStore(self.dir)

    def test_record_vote_happy(self):
        result = self.store.record_vote("HS001", 1)
        self.assertIn("receipt", result)
        self.assertIn("voted_at", result)
        self.assertTrue(self.store.find_voter("HS001")["has_voted"])

    def test_double_vote_rejected(self):
        self.store.record_vote("HS001", 1)
        with self.assertRaises(AlreadyVoted):
            self.store.record_vote("HS001", 1)

    def test_election_not_open(self):
        write_seed(self.dir, status="not_started")
        store = DataStore(self.dir)
        with self.assertRaises(ElectionNotOpen):
            store.record_vote("HS001", 1)

    def test_election_closed(self):
        write_seed(self.dir, status="closed")
        store = DataStore(self.dir)
        with self.assertRaises(ElectionClosed):
            store.record_vote("HS001", 1)

    def test_candidate_not_found(self):
        with self.assertRaises(CandidateNotFound):
            self.store.record_vote("HS001", 999)

    def test_votes_have_no_voter_id(self):
        self.store.record_vote("HS001", 1)
        self.store.record_vote("HS002", 2)
        raw = read_text(os.path.join(self.dir, "votes.json"))
        # Không được xuất hiện voter_id ở bất kỳ đâu trong file phiếu
        self.assertNotIn("voter_id", raw)
        self.assertNotIn("HS001", raw)
        self.assertNotIn("HS002", raw)
        for vote in json.loads(raw):
            self.assertEqual(set(vote.keys()), {"vote_id", "candidate_id", "timestamp"})

    def test_tally(self):
        self.store.record_vote("HS001", 1)
        self.store.record_vote("HS002", 1)
        tally = self.store.tally()
        self.assertEqual(tally["total_votes"], 2)
        by_id = {r["candidate_id"]: r for r in tally["results"]}
        self.assertEqual(by_id[1]["votes"], 2)
        self.assertEqual(by_id[1]["percent"], 100.0)
        self.assertEqual(by_id[2]["votes"], 0)

    def test_stats(self):
        self.store.record_vote("HS001", 1)
        stats = self.store.stats()
        self.assertEqual(stats["total_voters"], 2)
        self.assertEqual(stats["voted_count"], 1)
        self.assertEqual(stats["remaining"], 1)
        self.assertEqual(stats["turnout_percent"], 50.0)

    def test_atomic_write_leaves_no_tmp(self):
        self.store.record_vote("HS001", 1)
        self.assertEqual(glob.glob(os.path.join(self.dir, "*.tmp")), [])
        # File vẫn parse được sau khi ghi
        read_json(os.path.join(self.dir, "votes.json"))
        read_json(os.path.join(self.dir, "voters.json"))

    def test_persistence_across_reload(self):
        self.store.record_vote("HS001", 1)
        # Store mới nạp lại từ đĩa phải thấy phiếu và cờ đã bầu
        reloaded = DataStore(self.dir)
        self.assertTrue(reloaded.find_voter("HS001")["has_voted"])
        self.assertEqual(reloaded.tally()["total_votes"], 1)

    def test_open_close_sets_timestamps(self):
        write_seed(self.dir, status="not_started")
        store = DataStore(self.dir)
        opened = store.set_election_status("open")
        self.assertEqual(opened["status"], "open")
        self.assertIsNotNone(opened["opened_at"])
        closed = store.set_election_status("closed")
        self.assertEqual(closed["status"], "closed")
        self.assertIsNotNone(closed["closed_at"])


if __name__ == "__main__":
    unittest.main()
