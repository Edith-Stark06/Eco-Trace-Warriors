# EcoTrace Frontend — multi-stage build (P7.5)
#
# Vite bakes `VITE_*` variables into the bundle at BUILD time, not runtime
# (see src/lib/env.ts) — there is no server-side process to read env vars
# from once the static assets are built. `VITE_API_BASE_URL` is therefore a
# build ARG here: a deployment that needs a different backend URL rebuilds
# the image with a different --build-arg, it is not something docker-compose
# `environment:` can override after the fact. This is the standard tradeoff
# for a purely static SPA; documented rather than silently assumed.

# ---- Build stage ----
FROM node:20-alpine AS build
WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .

ARG VITE_API_BASE_URL=http://localhost:3000/api/v1
ARG VITE_API_TIMEOUT=15000
ARG VITE_APP_NAME="EcoTrace India"
ARG VITE_APP_VERSION=0.1.0
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_API_TIMEOUT=$VITE_API_TIMEOUT \
    VITE_APP_NAME=$VITE_APP_NAME \
    VITE_APP_VERSION=$VITE_APP_VERSION

RUN npm run build

# ---- Runtime stage ----
FROM nginx:1.27-alpine AS runtime

COPY --from=build /app/dist /usr/share/nginx/html
# Both configs are staged at fixed, stable paths outside /etc/nginx/conf.d/
# — docker-entrypoint-tls.sh copies the right ONE into conf.d/default.conf
# on every single container start (not just the first), so the choice is
# idempotent across `docker compose restart` regardless of what a PREVIOUS
# start of this same container instance wrote there (e.g. a cert that was
# mounted before and has since been removed).
COPY nginx.conf /etc/nginx/nginx.http.conf
COPY nginx.tls.conf /etc/nginx/nginx.tls.conf
COPY docker-entrypoint-tls.sh /docker-entrypoint-tls.sh
RUN chmod +x /docker-entrypoint-tls.sh

EXPOSE 80 443

# Checks whichever port is actually active (same certificate-presence
# test the entrypoint uses) — --no-check-certificate is safe here since
# it is only ever a container-internal loopback check, never external
# traffic; a self-signed cert failing browser trust is expected and
# unrelated to whether the server itself is healthy.
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD sh -c 'if [ -f /etc/nginx/tls/tls.crt ]; then wget --no-check-certificate -qO- https://127.0.0.1:443/; else wget -qO- http://127.0.0.1:80/; fi' || exit 1

ENTRYPOINT ["/docker-entrypoint-tls.sh"]
CMD ["nginx", "-g", "daemon off;"]
