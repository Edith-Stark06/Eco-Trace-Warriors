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
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1:80/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
