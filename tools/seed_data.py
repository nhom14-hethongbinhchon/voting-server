"""Sinh dữ liệu mẫu cho server: cử tri, ứng viên, admin, trạng thái bầu cử.

Chạy từ gốc repo:  python tools/seed_data.py [--force]
Mật khẩu được ghi ở dạng hash PBKDF2, không bao giờ lưu plaintext.
"""

import argparse
import json
import os
import sys

# Cho phép import gói src khi chạy script trực tiếp từ thư mục tools
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.security import hash_password, new_secret

DATA_DIR = os.path.join(_ROOT, "data")

# Mật khẩu mặc định cho môi trường học tập, đổi trước khi dùng thật
VOTER_PASSWORD = "123456"
ADMIN_PASSWORD = "admin123"

# Ghép họ + tên đệm + tên để có 30 cử tri khác nhau mà không cần dữ liệu ngẫu nhiên
_HO = ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Huỳnh", "Phan", "Vũ", "Võ", "Đặng"]
_DEM = ["Văn", "Thị", "Hoàng", "Minh", "Ngọc", "Gia"]
_TEN = ["An", "Bình", "Cường", "Dung", "Duyên", "Giang", "Hạnh", "Khánh", "Lan",
        "Minh", "Nam", "Oanh", "Phúc", "Quân", "Sơn", "Trang", "Uyên", "Vy", "Yến", "Đạt"]


def _voter_name(index: int) -> str:
    return "{} {} {}".format(
        _HO[index % len(_HO)],
        _DEM[index % len(_DEM)],
        _TEN[index % len(_TEN)],
    )


def build_voters(count: int = 30) -> list:
    voters = []
    for i in range(1, count + 1):
        voters.append({
            "voter_id": "HS{:03d}".format(i),
            "full_name": _voter_name(i),
            "password_hash": hash_password(VOTER_PASSWORD),
            "has_voted": False,
            "voted_at": None,
        })
    return voters


def build_candidates() -> list:
    return [
        {"id": 1, "name": "Nguyễn Văn A", "description": "Lớp 12A1", "photo_url": ""},
        {"id": 2, "name": "Trần Thị B", "description": "Lớp 12A2", "photo_url": ""},
        {"id": 3, "name": "Lê Hoàng C", "description": "Lớp 12A3", "photo_url": ""},
        {"id": 4, "name": "Phạm Minh D", "description": "Lớp 12A4", "photo_url": ""},
    ]


def build_admins() -> list:
    return [
        {
            "username": "admin",
            "display_name": "Ban tổ chức",
            "password_hash": hash_password(ADMIN_PASSWORD),
        }
    ]


def build_election() -> dict:
    return {
        "title": "Bầu cử Ban đại diện học sinh 2026",
        "status": "not_started",
        "opened_at": None,
        "closed_at": None,
    }


def _write(name: str, obj) -> None:
    path = os.path.join(DATA_DIR, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("  đã ghi {}".format(path))


def main() -> None:
    parser = argparse.ArgumentParser(description="Sinh dữ liệu mẫu cho voting-server")
    parser.add_argument("--force", action="store_true",
                        help="Ghi đè dù data đã tồn tại (xoá phiếu và cờ đã bầu hiện có)")
    args = parser.parse_args()

    os.makedirs(DATA_DIR, exist_ok=True)

    # Tránh vô tình xoá dữ liệu bầu cử thật khi đã chạy được một lúc
    voters_path = os.path.join(DATA_DIR, "voters.json")
    if os.path.exists(voters_path) and not args.force:
        print("data/ đã có dữ liệu. Dùng --force để ghi đè (sẽ mất phiếu hiện có).")
        sys.exit(1)

    print("Sinh dữ liệu mẫu vào {} ...".format(DATA_DIR))
    _write("election.json", build_election())
    _write("candidates.json", build_candidates())
    _write("voters.json", build_voters())
    _write("admins.json", build_admins())
    _write("votes.json", [])

    # server_secret sinh một lần, giữ ổn định để receipt cũ vẫn đối chiếu được
    secret_path = os.path.join(DATA_DIR, "server_secret")
    if not os.path.exists(secret_path) or args.force:
        with open(secret_path, "w", encoding="utf-8") as f:
            f.write(new_secret())
        print("  đã ghi {}".format(secret_path))

    print("Xong. 30 cử tri (HS001-HS030 / {}), 1 admin (admin / {}).".format(
        VOTER_PASSWORD, ADMIN_PASSWORD))


if __name__ == "__main__":
    main()
