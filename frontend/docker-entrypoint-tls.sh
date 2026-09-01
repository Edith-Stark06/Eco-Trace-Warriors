#!/bin/sh
# EcoTrace India — optional TLS entrypoint wrapper (P9.1).
#
# Swaps in the HTTPS-enabled nginx config only when a certificate is
# actually mounted at /etc/nginx/tls/ — keeps zero-config `docker compose
# up` on plain HTTP exactly as before (nginx.conf, unchanged from P7.5)
# when no certificate is present, since nginx refuses to start at all if
# `ssl_certificate` in its config points at a file that doesn't exist.
#
# Then hands off to the base nginx:1.27-alpine image's own entrypoint
# (which does its own template/envsubst setup) rather than replacing it.
set -e

# Re-decided on every start (not just the container's first start) so a
# certificate that was removed since the last `docker compose restart`
# correctly falls back to plain HTTP rather than nginx refusing to start
# against a config that references a now-missing file.
if [ -f /etc/nginx/tls/tls.crt ] && [ -f /etc/nginx/tls/tls.key ]; then
  echo "TLS certificate found — enabling HTTPS on 443 (+ HTTP->HTTPS redirect on 80)."
  # The HTTP->HTTPS redirect must name the *host-mapped* HTTPS port
  # (FRONTEND_TLS_PORT, default 8443) — nginx inside the container has no
  # way to know Docker's port mapping on its own.
  sed "s/__TLS_PORT__/${FRONTEND_TLS_PORT:-8443}/" /etc/nginx/nginx.tls.conf > /etc/nginx/conf.d/default.conf
else
  echo "No TLS certificate mounted — serving plain HTTP on 80 only (default)."
  cp /etc/nginx/nginx.http.conf /etc/nginx/conf.d/default.conf
fi

exec /docker-entrypoint.sh "$@"
