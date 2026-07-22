"""Băm mật khẩu, sinh token, và tạo TLS context. Module lá, chỉ phụ thuộc stdlib."""

import base64
import hashlib
import hmac
import secrets
import ssl

# Tham số PBKDF2. Đổi ITERATIONS sẽ làm hash cũ không verify được, nên giữ cố định.
_ALGORITHM = "pbkdf2_sha256"
_ITERATIONS = 200_000
_SALT_BYTES = 16


def hash_password(plain: str) -> str:
    """Trả chuỗi lưu trữ dạng pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>."""
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt, _ITERATIONS)
    return "{}${}${}${}".format(
        _ALGORITHM,
        _ITERATIONS,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def verify_password(plain: str, stored: str) -> bool:
    """So khớp mật khẩu với chuỗi đã lưu. Dùng compare_digest để tránh timing attack."""
    try:
        algorithm, iters, salt_b64, hash_b64 = stored.split("$")
        if algorithm != _ALGORITHM:
            return False
        iterations = int(iters)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
    except (ValueError, TypeError):
        # Chuỗi lưu trữ hỏng định dạng thì coi như không khớp, không raise
        return False
    actual = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def new_token() -> str:
    """Sinh token phiên đăng nhập, đủ dài để không đoán được."""
    return secrets.token_urlsafe(32)


def new_secret() -> str:
    """Sinh server_secret dùng để tạo receipt phiếu bầu."""
    return secrets.token_hex(32)


def make_receipt(vote_id: str, voter_id: str, server_secret: str) -> str:
    """Biên nhận = sha256(vote_id + voter_id + server_secret).

    Cử tri giữ chuỗi này để đối chiếu, nhưng từ nó không suy ngược ra lá phiếu.
    """
    material = (vote_id + voter_id + server_secret).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def build_ssl_context(cert_file: str, key_file: str) -> ssl.SSLContext:
    """TLS context phía server, tối thiểu TLS 1.2."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=cert_file, keyfile=key_file)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context
