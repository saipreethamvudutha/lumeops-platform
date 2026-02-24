#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# Generate self-signed TLS certificates for local development/testing.
# These are NOT suitable for production — use Let's Encrypt or a real CA.
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

CERT_DIR="$(cd "$(dirname "$0")/certs" && pwd)"
mkdir -p "$CERT_DIR"

echo "Generating self-signed TLS certificate for development..."

openssl req -x509 -nodes \
  -days 365 \
  -newkey rsa:2048 \
  -keyout "$CERT_DIR/privkey.pem" \
  -out "$CERT_DIR/fullchain.pem" \
  -subj "/C=US/ST=Development/L=Local/O=LumeOps/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,DNS:*.localhost,IP:127.0.0.1"

echo ""
echo "Certificates generated:"
echo "  $CERT_DIR/fullchain.pem"
echo "  $CERT_DIR/privkey.pem"
echo ""
echo "These are self-signed (development only). For production, use Let's Encrypt."
