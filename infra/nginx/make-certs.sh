#!/bin/sh
# Development TLS certificate for https://localhost (spec §17.0, DECISIONS D3).
# Uses mkcert when installed (locally trusted; needed for phone testing before demos),
# otherwise an openssl self-signed certificate (browser warning must be accepted).
set -eu
DIR="$(cd "$(dirname "$0")" && pwd)/certs"
mkdir -p "$DIR"
if [ -s "$DIR/dev.crt" ] && [ -s "$DIR/dev.key" ] && [ "${FORCE:-0}" != "1" ]; then
  echo "certs exist in $DIR (FORCE=1 to regenerate)"; exit 0
fi
if command -v mkcert >/dev/null 2>&1; then
  mkcert -cert-file "$DIR/dev.crt" -key-file "$DIR/dev.key" localhost 127.0.0.1 ::1 nginx
  echo "mkcert certificate written to $DIR"
else
  openssl req -x509 -newkey rsa:2048 -sha256 -days 365 -nodes \
    -keyout "$DIR/dev.key" -out "$DIR/dev.crt" -subj "/CN=localhost" \
    -addext "subjectAltName=DNS:localhost,DNS:nginx,IP:127.0.0.1" 2>/dev/null
  echo "self-signed certificate written to $DIR (install mkcert for a trusted one)"
fi
# Nginx runs as uid 101 inside the container and must read the key.
chmod 644 "$DIR/dev.crt" "$DIR/dev.key"
