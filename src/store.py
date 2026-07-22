"""DataStore: nạp toàn bộ dữ liệu JSON vào RAM, mọi truy cập qua một RLock duy nhất.

Ghi đĩa atomic (ghi .tmp, fsync, os.replace) để không hỏng file khi crash giữa chừng.
record_vote là điểm chống bầu trùng: toàn bộ kiểm tra và ghi nằm trong cùng một lần giữ lock.
"""

import json
import os
import secrets
import threading
from datetime import datetime, timezone

from src.errors import (
    AlreadyVoted,
    CandidateNotFound,
    ElectionClosed,
    ElectionNotOpen,
    Unauthenticated,
)
from src.security import make_receipt, new_secret

# Trạng thái bầu cử hợp lệ
_NOT_STARTED = "not_started"
_OPEN = "open"
_CLOSED = "closed"


def _now_iso() -> str:
    """Thời điểm hiện tại theo ISO-8601 UTC, ví dụ 2026-07-22T09:31:04Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json(path: str, obj) -> None:
    """Ghi atomic: ghi ra file tạm, ép xuống đĩa, rồi thay thế nguyên tử."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _read_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class DataStore:
    def __init__(self, data_dir: str):
        self._dir = data_dir
        self._lock = threading.RLock()

        self._election_path = os.path.join(data_dir, "election.json")
        self._candidates_path = os.path.join(data_dir, "candidates.json")
        self._voters_path = os.path.join(data_dir, "voters.json")
        self._admins_path = os.path.join(data_dir, "admins.json")
        self._votes_path = os.path.join(data_dir, "votes.json")
        self._secret_path = os.path.join(data_dir, "server_secret")

        self._election = _read_json(self._election_path)
        self._candidates = _read_json(self._candidates_path)
        self._voters = _read_json(self._voters_path)
        self._admins = _read_json(self._admins_path)
        # votes.json có thể chưa tồn tại ở lần chạy đầu
        self._votes = _read_json(self._votes_path) if os.path.exists(self._votes_path) else []

        # Chỉ mục theo id để tra cứu O(1) thay vì quét danh sách mỗi lần
        self._voters_by_id = {v["voter_id"]: v for v in self._voters}
        self._admins_by_name = {a["username"]: a for a in self._admins}
        self._candidate_ids = {c["id"] for c in self._candidates}

        self._server_secret = self._load_or_create_secret()

    def _load_or_create_secret(self) -> str:
        # Giữ secret ổn định để receipt cũ vẫn đối chiếu được; sinh mới nếu chưa có
        if os.path.exists(self._secret_path):
            with open(self._secret_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        secret = new_secret()
        with open(self._secret_path, "w", encoding="utf-8") as f:
            f.write(secret)
        return secret

    def get_candidates(self) -> list[dict]:
        """Trả bản sao danh sách ứng viên để bên ngoài không sửa được state nội bộ."""
        with self._lock:
            return [
                {
                    "id": c["id"],
                    "name": c["name"],
                    "description": c.get("description", ""),
                    "photo_url": c.get("photo_url", ""),
                }
                for c in self._candidates
            ]

    def find_voter(self, voter_id: str) -> dict | None:
        with self._lock:
            return self._voters_by_id.get(voter_id)

    def find_admin(self, username: str) -> dict | None:
        with self._lock:
            return self._admins_by_name.get(username)

    def get_election(self) -> dict:
        with self._lock:
            return dict(self._election)

    def set_election_status(self, status: str) -> dict:
        """Đổi trạng thái bầu cử, ghi mốc thời gian mở/đóng, flush. Trả election sau khi đổi."""
        with self._lock:
            self._election["status"] = status
            if status == _OPEN and not self._election.get("opened_at"):
                self._election["opened_at"] = _now_iso()
            if status == _CLOSED:
                self._election["closed_at"] = _now_iso()
            _write_json(self._election_path, self._election)
            return dict(self._election)

    def record_vote(self, voter_id: str, candidate_id: int) -> dict:
        """Ghi một phiếu một cách nguyên tử. Trả {receipt, voted_at}.

        Mọi kiểm tra (bầu cử mở, ứng viên tồn tại, chưa bầu) và việc ghi nằm trong cùng một
        critical section, nên hai thread không thể lách qua khe để cùng bầu một tài khoản.
        """
        with self._lock:
            status = self._election["status"]
            if status != _OPEN:
                # Phân biệt chưa mở với đã đóng để client hiển thị đúng
                raise ElectionClosed() if status == _CLOSED else ElectionNotOpen()

            if candidate_id not in self._candidate_ids:
                raise CandidateNotFound()

            voter = self._voters_by_id.get(voter_id)
            if voter is None:
                # Token hợp lệ nhưng cử tri đã bị xoá khỏi danh sách
                raise Unauthenticated()
            if voter["has_voted"]:
                raise AlreadyVoted()

            vote_id = secrets.token_hex(16)
            timestamp = _now_iso()
            # votes.json cố ý không chứa voter_id: không liên kết được phiếu với người bầu
            self._votes.append({
                "vote_id": vote_id,
                "candidate_id": candidate_id,
                "timestamp": timestamp,
            })
            voter["has_voted"] = True
            voter["voted_at"] = timestamp

            # Ghi cờ has_voted xuống đĩa TRƯỚC lá phiếu: nếu crash giữa hai lần ghi thì
            # cùng lắm mất một phiếu, chứ không cho phép bầu trùng sau khi khởi động lại.
            _write_json(self._voters_path, self._voters)
            _write_json(self._votes_path, self._votes)

            receipt = make_receipt(vote_id, voter_id, self._server_secret)
            return {"receipt": receipt, "voted_at": timestamp}

    def tally(self) -> dict:
        """Kết quả kiểm phiếu: số phiếu và phần trăm từng ứng viên, tổng phiếu, trạng thái."""
        with self._lock:
            counts = {c["id"]: 0 for c in self._candidates}
            for vote in self._votes:
                cid = vote["candidate_id"]
                if cid in counts:
                    counts[cid] += 1
            total = len(self._votes)
            results = []
            for c in self._candidates:
                votes = counts[c["id"]]
                percent = round(votes / total * 100, 1) if total else 0.0
                results.append({
                    "candidate_id": c["id"],
                    "name": c["name"],
                    "votes": votes,
                    "percent": percent,
                })
            return {
                "results": results,
                "total_votes": total,
                "election_status": self._election["status"],
            }

    def stats(self) -> dict:
        """Thống kê tỉ lệ đi bầu."""
        with self._lock:
            total = len(self._voters)
            voted = sum(1 for v in self._voters if v["has_voted"])
            turnout = round(voted / total * 100, 1) if total else 0.0
            return {
                "total_voters": total,
                "voted_count": voted,
                "remaining": total - voted,
                "turnout_percent": turnout,
            }
