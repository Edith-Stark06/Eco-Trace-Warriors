#!/usr/bin/env bash
# EcoTrace India — local/demo self-signed TLS certificate generator (P9.1).
#
# Generates a self-signed certificate for LOCAL/DEMO HTTPS termination only.
# This is explicitly NOT a production-grade certificate — a real deployment
# replaces the two files this script writes (tls.crt, tls.key) with a real
# CA-issued certificate (e.g. Let's Encrypt) mounted at the same path; no
# other configuration changes are needed (frontend/nginx.conf reads these
# exact filenames).
#
# Usage:
#   bash deployment/tls/generate_local_cert.sh
set -euo pipefail
cd "$(dirname "$0")"

if [ -f tls.crt ] && [ -f tls.key ]; then
  echo "tls.crt/tls.key already exist — remove them first to regenerate."
  exit 0
fi

# Git-Bash/MSYS on Windows auto-converts a leading "/C=IN/..." in -subj
# into a Windows path, corrupting it. Harmless no-op on real Linux/macOS.
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

openssl req -x509 -nodes -newkey rsa:2048 \
  -keyout tls.key -out tls.crt -days 365 \
  -subj "/C=IN/ST=TamilNadu/L=Chennai/O=EcoTrace India/OU=Local Demo/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"

chmod 600 tls.key
echo "Generated deployment/tls/tls.crt and tls.key (self-signed, 365 days, local/demo only)."
