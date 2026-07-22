#!/usr/bin/env bash
# Sinh chứng chỉ tự ký cho server. Truyền IP LAN của máy server làm tham số để đưa vào SAN,
# nhờ đó client trong mạng có thể verify theo IP nếu muốn (mặc định client học tập bỏ qua verify).
#
#   bash certs/gen_cert.sh 192.168.1.10
#
set -euo pipefail

IP="${1:-127.0.0.1}"
DIR="$(cd "$(dirname "$0")" && pwd)"
CRT="$DIR/server.crt"
KEY="$DIR/server.key"
DAYS=825

SAN="subjectAltName=DNS:localhost,IP:127.0.0.1"
if [ "$IP" != "127.0.0.1" ]; then
  SAN="$SAN,IP:$IP"
fi

openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout "$KEY" -out "$CRT" -days "$DAYS" \
  -subj "/CN=voting-server" \
  -addext "$SAN"

chmod 600 "$KEY"

echo "Đã sinh chứng chỉ tự ký:"
echo "  cert: $CRT"
echo "  key : $KEY"
echo "  SAN : $SAN"
echo "Nhớ sinh lại nếu IP máy server thay đổi."
