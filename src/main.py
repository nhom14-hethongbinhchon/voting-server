"""Điểm vào: nạp cấu hình, dựng các thành phần, khởi động server, bắt tín hiệu để tắt êm.

Chạy:  python -m src.main --config config.json
Debug: python -m src.main --no-tls --port 8443
"""

import argparse
import json
import logging
import os
import signal
import sys

# Cho phép chạy cả `python -m src.main` lẫn `python src/main.py`
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.broadcast import BroadcastHub
from src.security import build_ssl_context
from src.server import Server
from src.sessions import LoginRateLimiter, SessionManager
from src.store import DataStore

logger = logging.getLogger(__name__)

# Giá trị mặc định, khớp config.example.json, dùng khi cấu hình thiếu trường
_DEFAULTS = {
    "host": "0.0.0.0",
    "port": 8443,
    "use_tls": True,
    "cert_file": "certs/server.crt",
    "key_file": "certs/server.key",
    "data_dir": "data",
    "session_ttl_seconds": 7200,
    "max_login_attempts": 5,
    "login_lockout_seconds": 300,
    "log_level": "INFO",
}


def _resolve(path: str) -> str:
    # Đường dẫn tương đối tính từ gốc repo, để chạy từ đâu cũng đúng
    return path if os.path.isabs(path) else os.path.join(_ROOT, path)


def load_config(path: str | None) -> dict:
    config = dict(_DEFAULTS)
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            config.update(json.load(f))
    return config


def setup_logging(level_name: str, log_path: str) -> None:
    level = getattr(logging, str(level_name).upper(), logging.INFO)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s",
                            "%Y-%m-%d %H:%M:%S")
    root = logging.getLogger()
    root.setLevel(level)
    # Xoá handler cũ để gọi lại (ví dụ trong test) không nhân đôi dòng log
    root.handlers.clear()
    for handler in (logging.StreamHandler(), logging.FileHandler(log_path, encoding="utf-8")):
        handler.setFormatter(fmt)
        root.addHandler(handler)


def build_server(config: dict) -> Server:
    data_dir = _resolve(config["data_dir"])
    store = DataStore(data_dir)
    sessions = SessionManager(int(config["session_ttl_seconds"]))
    hub = BroadcastHub()
    rate_limiter = LoginRateLimiter(int(config["max_login_attempts"]),
                                    int(config["login_lockout_seconds"]))

    ssl_context = None
    if config["use_tls"]:
        cert = _resolve(config["cert_file"])
        key = _resolve(config["key_file"])
        if not (os.path.exists(cert) and os.path.exists(key)):
            logger.error("Thiếu chứng chỉ TLS (%s / %s). Sinh bằng certs/gen_cert.sh "
                         "hoặc chạy với --no-tls để debug.", cert, key)
            sys.exit(1)
        ssl_context = build_ssl_context(cert, key)

    return Server(config, store, sessions, hub, rate_limiter, ssl_context)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Server bình chọn trực tuyến")
    parser.add_argument("--config", default="config.json", help="đường dẫn file cấu hình")
    parser.add_argument("--port", type=int, help="ghi đè cổng lắng nghe")
    parser.add_argument("--no-tls", action="store_true", help="tắt TLS để debug")
    args = parser.parse_args(argv)

    config = load_config(_resolve(args.config))
    if args.port is not None:
        config["port"] = args.port
    if args.no_tls:
        config["use_tls"] = False

    setup_logging(config["log_level"], _resolve(os.path.join("logs", "server.log")))

    server = build_server(config)

    # Bắt SIGINT (Ctrl-C) và SIGTERM để tắt máy êm thay vì chết đột ngột
    def _on_signal(signum, frame):
        logger.info("nhận tín hiệu %s, đang dừng...", signum)
        server.request_stop()

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    server.serve_forever()


if __name__ == "__main__":
    main()
