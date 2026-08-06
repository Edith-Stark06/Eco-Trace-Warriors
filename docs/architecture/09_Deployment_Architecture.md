# Deployment Architecture

**Version:** 1.0.0  
**Status:** Active  
**Last Updated:** 2026-08-06

**Scope:** Deployment layer only — the container images, Docker Compose stacks, environment configuration, build process, and continuous-integration assets that actually exist in the repository (`backend/Dockerfile`, `intelligence/device_ai/Dockerfile`, the three `docker-compose*.yml` files, `.dockerignore` files, `.env.example` templates, and `.github/workflows/backend-ci.yml`).

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Deployment Overview](#2-deployment-overview)
3. [Overall Deployment Topology](#3-overall-deployment-topology)
4. [Docker Architecture](#4-docker-architecture)
5. [Docker Compose Architecture](#5-docker-compose-architecture)
6. [Container Relationships](#6-container-relationships)
7. [Service Startup Sequence](#7-service-startup-sequence)
8. [Environment Configuration](#8-environment-configuration)
9. [Frontend Deployment](#9-frontend-deployment)
10. [Backend Deployment](#10-backend-deployment)
11. [AI Service Deployment](#11-ai-service-deployment)
12. [Database Deployment](#12-database-deployment)
13. [Networking](#13-networking)
14. [Storage Strategy](#14-storage-strategy)
15. [Logging](#15-logging)
16. [Health Monitoring](#16-health-monitoring)
17. [Build Process](#17-build-process)
18. [Configuration Management](#18-configuration-management)
19. [Development Workflow](#19-development-workflow)
20. [Production Considerations](#20-production-considerations)
21. [Scalability](#21-scalability)
22. [Security Considerations](#22-security-considerations)
23. [Current Limitations](#23-current-limitations)
24. [Future Deployment Evolution](#24-future-deployment-evolution)
25. [Design Rationale](#25-design-rationale)
26. [Conclusion](#26-conclusion)

---

## 1. Executive Summary

EcoTrace India's deployment layer is **container-first and Docker Compose–orchestrated**, and — importantly for an honest architecture record — it is *partially realized*. This document reverse-engineers only what the repository actually contains; it does not describe infrastructure that is aspirational.

What exists today, verifiable in the tree:

- **Two production-grade Dockerfiles.** `backend/Dockerfile` builds the REST API ([07 — Backend API Architecture]) as a multi-stage `node:20-alpine` image; `intelligence/device_ai/Dockerfile` builds the Device Intelligence Engine ([03 — Device Intelligence Architecture]) as a multi-stage `python:3.12-slim` image. Both run as non-root users and declare container `HEALTHCHECK`s.
- **Three independent Docker Compose files.** A root `docker-compose.yml` (PostgreSQL only), a development stack `deployment/docker/docker-compose.dev.yml` (backend + PostgreSQL, with health-gated startup ordering), and `intelligence/device_ai/docker-compose.yml` (the AI service with its persistent volumes). These are **separate stacks**, not one unified full-stack compose.
- **One CI workflow.** `.github/workflows/backend-ci.yml` runs the backend quality gate (lint, type-check, format, test, build) and a Docker image build. There is no CI for the frontend or the AI service yet.
- **Twelve-factor configuration.** Every service is configured exclusively through environment variables, validated once at startup — Zod for the backend ([07], [08]) and `pydantic-settings` for the AI service ([03]).

What does **not** yet exist (documented plainly in §23): there is no Kubernetes, Terraform, Helm, cloud provider (AWS/Azure/GCP), NGINX gateway, frontend container image, blockchain/Fabric deployment ([05]), or single command that brings the entire platform up together. The directories `deployment/kubernetes/`, `deployment/nginx/`, and `scripts/*` are present but empty placeholders. This document describes the deployment the repository *is*, and reserves the deployment it *intends to become* for §24.

---

## 2. Deployment Overview

### 2.1 Deployable Units That Exist

| Unit | Source | Image / base | Port | Status |
|---|---|---|---|---|
| Backend API | `backend/Dockerfile` | `node:20-alpine` (multi-stage) | 3000 | Containerized ✓ |
| Device Intelligence Engine (AI) | `intelligence/device_ai/Dockerfile` | `python:3.12-slim` (multi-stage) | 8100 | Containerized ✓ |
| PostgreSQL database | compose (`postgres:16` / `postgres:16-alpine`) | official image | 5432 | Containerized ✓ |
| Frontend dashboard | `frontend/` (Vite build → `dist/`) | — | 5173 (dev) | Static build, **no image** |

### 2.2 Orchestration Assets That Exist

| File | Brings up | Purpose |
|---|---|---|
| `docker-compose.yml` (root) | PostgreSQL | Standalone database for local backend dev |
| `deployment/docker/docker-compose.dev.yml` | Backend + PostgreSQL | Development stack with health-gated ordering |
| `intelligence/device_ai/docker-compose.yml` | AI service | Runs the DIE in isolation with persistent volumes |
| `.github/workflows/backend-ci.yml` | — (CI) | Backend quality gate + Docker build |

### 2.3 Cross-References

The deployment layer packages the subsystems documented elsewhere: the backend ([07 — Backend API Architecture]) and its database ([08 — Database Architecture]); the AI Device Intelligence Engine ([03 — Device Intelligence Architecture]) within the wider AI platform ([02 — AI Platform Architecture]); and the web dashboard ([06 — Web Platform Architecture]). The overall system these belong to is [01 — System Architecture]. Blockchain deployment ([05 — Blockchain Architecture]) is out of scope here because no blockchain deployment asset exists in the repository.

---

## 3. Overall Deployment Topology

The realized topology is a set of **containerizable services plus one static frontend build**, wired together by environment variables rather than by a single orchestrator.

**Overall Deployment Diagram**

```
                         ┌──────────────────────────────────────────┐
                         │            Developer host                 │
                         │         (Docker Engine + Node/Vite)       │
                         └──────────────────────────────────────────┘
                                          │
        ┌─────────────────────────────────┼─────────────────────────────────┐
        │                                 │                                  │
        ▼                                 ▼                                  ▼
┌────────────────┐              ┌────────────────────┐            ┌────────────────────┐
│  Frontend      │  HTTP        │  Backend API       │  HTTP      │  Device Intelligence│
│  (Vite dist/)  │ ───────────► │  container :3000   │ ─ ─ ─ ─ ─► │  Engine :8100       │
│  static assets │  VITE_API_   │  node:20-alpine    │  (AI call, │  python:3.12-slim   │
│  NO Dockerfile │  BASE_URL    │  /api/v1           │  planned)  │  /health            │
└────────────────┘              └─────────┬──────────┘            └─────────┬──────────┘
                                          │  DATABASE_URL                   │
                                          ▼                                 ▼
                                ┌────────────────────┐            ┌────────────────────┐
                                │  PostgreSQL :5432  │            │  Named volumes     │
                                │  postgres:16       │            │  models/artifacts/ │
                                │  volume: pgdata    │            │  mlruns            │
                                └────────────────────┘            └────────────────────┘

  Solid arrows = wiring that exists in the repo.  Dashed arrow = intended backend→AI
  call path (the AI service is defined and runnable, but no compose file joins it to
  the backend yet — see §6, §23).
```

### 3.1 Topology Notes

- **No public gateway exists.** The engineering intent (`docs/engineering/11_DEPLOYMENT.md`) describes an NGINX front door, but `deployment/nginx/` is empty; every service currently publishes its own host port directly.
- **Services are independently deployable.** Each has (or, for the frontend, could trivially have) its own build and its own configuration surface. No service imports another's code; they integrate only over HTTP and the database connection string.
- **The frontend is not containerized.** It is built to static assets (`frontend/dist/`) and would be served by any static host or CDN; the repository ships no image or web-server config for it (§9).

---

## 4. Docker Architecture

Both containerized services use the same disciplined pattern: **multi-stage builds, slim bases, non-root runtime users, and declared health checks.**

### 4.1 Backend Image (`backend/Dockerfile`)

```dockerfile
# ---- Build stage ----
FROM node:20-alpine AS build
WORKDIR /app
ENV HUSKY=0
COPY package.json package-lock.json* ./
COPY .husky/install.mjs ./.husky/install.mjs
COPY prisma ./prisma
RUN npm ci
COPY tsconfig.json tsconfig.build.json ./
COPY src ./src
RUN npm run build            # prisma generate + tsc + tsc-alias

# ---- Runtime stage ----
FROM node:20-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production
ENV HUSKY=0
COPY package.json package-lock.json* ./
COPY .husky/install.mjs ./.husky/install.mjs
COPY prisma ./prisma
RUN npm ci --omit=dev && npm cache clean --force
COPY --from=build /app/dist ./dist
USER node                    # non-root
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://127.0.0.1:3000/api/v1/health || exit 1
CMD ["node", "dist/server.js"]
```

Salient properties, all from the file:

- **Two stages.** The `build` stage installs the full dependency set and compiles TypeScript to `dist/`; the `runtime` stage installs only production dependencies (`--omit=dev`), then copies the compiled `dist/` from the build stage. The runtime image never contains dev dependencies or TypeScript sources.
- **`HUSKY=0`.** Git hook installation is disabled inside the image (no `.git` present), so `npm ci` does not try to wire Husky. The single `.husky/install.mjs` shim is copied so the `prepare` script is a no-op rather than an error.
- **Prisma is copied before install.** The `prisma/` directory is present so `prisma generate` (invoked by `npm run build`, see [08 — Database Architecture]) can produce the client.
- **Non-root.** The image switches to the `node` user provided by the base image before `CMD`.
- **Health check.** A `wget` probe against `/api/v1/health` gates container readiness (§16).

### 4.2 AI Image (`intelligence/device_ai/Dockerfile`)

```dockerfile
# ---- builder: build wheels ----
FROM python:3.12-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /wheels
COPY requirements.txt .
RUN pip wheel --wheel-dir /wheels -r requirements.txt

# ---- runtime ----
FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 \
    HOST=0.0.0.0 PORT=8100 \
    MODEL_DIR=/app/models UPLOAD_DIR=/app/uploads \
    ARTIFACT_DIR=/app/artifacts MLRUNS_DIR=/app/mlruns \
    EXPERIMENT_TRACKER=json LOG_LEVEL=INFO
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
RUN groupadd --system appgroup \
    && useradd --system --gid appgroup --create-home --home-dir /home/appuser appuser
WORKDIR /app
COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-index --find-links=/wheels -r requirements.txt && rm -rf /wheels
COPY . /app/device_ai
RUN mkdir -p /app/models /app/uploads /app/artifacts /app/mlruns \
    && chown -R appuser:appgroup /app
USER appuser                 # non-root
EXPOSE 8100
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl --fail http://localhost:8100/health || exit 1
CMD ["uvicorn", "device_ai.app:app", "--host", "0.0.0.0", "--port", "8100"]
```

Salient properties, all from the file:

- **Wheel-building stage.** The `builder` stage compiles all dependencies into wheels; the `runtime` stage installs them offline (`--no-index --find-links=/wheels`) and deletes the wheel cache. This keeps the runtime image free of a compiler toolchain and makes installs fast and reproducible.
- **Baked-in filesystem contract.** The runtime `ENV` block sets `MODEL_DIR`, `UPLOAD_DIR`, `ARTIFACT_DIR`, and `MLRUNS_DIR`, and the image `mkdir`s and `chown`s exactly those directories to the non-root `appuser` (§11, §14).
- **`curl` for health.** `curl` is installed solely so the container `HEALTHCHECK` can probe `/health`.
- **Package layout.** The application is copied to `/app/device_ai` and served as `device_ai.app:app`; `/app` is the working directory and on `sys.path`, so the import resolves.
- **Deferred heavy models.** Per the file's own comment and `requirements.txt`, only core runtime dependencies (FastAPI, Uvicorn, Pydantic, Pillow, NumPy, Loguru) are installed; heavy model packages are intentionally deferred, keeping the base image small (§11, [03 — Device Intelligence Architecture]).

### 4.3 `.dockerignore` Discipline

Each image ships a `.dockerignore` that keeps the build context minimal and reproducible:

- **Backend** excludes `node_modules`, `dist`, `coverage`, `.env`, logs, tests, and lint/format config; it keeps only `.husky/install.mjs` from `.husky`.
- **AI** excludes Python caches, `.env`, virtualenvs, `models/**` and `datasets/**` (except `.gitkeep`), notebooks, `uploads/`, tests, and the `requirements-dev.txt` / `requirements-models.txt` files not needed at runtime.

Excluding `.env` from both contexts is a security control (§22): secrets can never be accidentally baked into an image layer.

---

## 5. Docker Compose Architecture

The repository contains **three distinct Compose files**, each a self-contained stack. They are not layered together and there is no single "everything up" file — an honest and important characteristic of the current deployment.

**Docker Compose Diagram**

```
 ┌──────────────────────────────────────────────────────────────────────────┐
 │ (A) ./docker-compose.yml            — DATABASE ONLY                        │
 │     services: postgres (postgres:16)                                       │
 │     env: ecotrace / ecotrace123 / ecotrace     port 5432                   │
 │     volume: postgres_data                                                  │
 │     restart: unless-stopped                                                │
 └──────────────────────────────────────────────────────────────────────────┘
 ┌──────────────────────────────────────────────────────────────────────────┐
 │ (B) ./deployment/docker/docker-compose.dev.yml   — DEV STACK              │
 │     name: ecotrace-dev                                                     │
 │     ┌───────────────┐  depends_on: service_healthy  ┌──────────────────┐  │
 │     │ backend :3000 │ ───────────────────────────►  │ postgres :5432   │  │
 │     │ build ../../  │                                │ postgres:16-alpine│ │
 │     │      backend  │  DATABASE_URL=…@postgres:5432  │ healthcheck:     │  │
 │     └───────────────┘                                │  pg_isready      │  │
 │                                                      │ volume: pgdata   │  │
 │                                                      └──────────────────┘  │
 └──────────────────────────────────────────────────────────────────────────┘
 ┌──────────────────────────────────────────────────────────────────────────┐
 │ (C) ./intelligence/device_ai/docker-compose.yml  — AI SERVICE ONLY        │
 │     service: device-ai (build . )  image ecotrace/device-ai:1.0.0         │
 │     port 8100   healthcheck: curl /health                                  │
 │     volumes: device-ai-models, device-ai-artifacts, device-ai-mlruns      │
 └──────────────────────────────────────────────────────────────────────────┘
```

### 5.1 Stack (A) — Root `docker-compose.yml`

Defines a single `postgres:16` service named `ecotrace-postgres`, with `restart: unless-stopped`, credentials `ecotrace / ecotrace123 / ecotrace`, host port `5432:5432`, and a named volume `postgres_data`. It is the minimal database a developer runs while working on the backend outside Docker. It has **no health check** and no other services.

### 5.2 Stack (B) — `deployment/docker/docker-compose.dev.yml`

The development stack (Compose project name `ecotrace-dev`) is the most complete orchestration in the repository. It defines:

- **`backend`** — built from `../../backend` (the Dockerfile in §4.1), container `ecotrace-backend`, environment `NODE_ENV=development`, `PORT=3000`, `API_PREFIX=/api/v1`, `LOG_LEVEL=debug`, and `DATABASE_URL=postgresql://ecotrace:ecotrace@postgres:5432/ecotrace?schema=public`. It publishes `3000:3000` and declares `depends_on: postgres: condition: service_healthy`.
- **`postgres`** — `postgres:16-alpine`, container `ecotrace-postgres`, credentials `ecotrace / ecotrace / ecotrace`, port `5432:5432`, volume `ecotrace-pgdata`, and a `pg_isready` health check (`interval 5s`, `timeout 3s`, `retries 10`).

The `DATABASE_URL` uses the **service name `postgres` as the host**, which is how the backend container reaches the database over the Compose network (§13).

### 5.3 Stack (C) — `intelligence/device_ai/docker-compose.yml`

Runs the Device Intelligence Engine in isolation. Its own header comment states the intent plainly: *"Runs the mock AI microservice in isolation. The existing EcoTrace backend is NOT modified; it will call this service over HTTP at the exposed port."* It defines one `device-ai` service built from `.`, tagged `ecotrace/device-ai:1.0.0`, container `ecotrace-device-ai`, `restart: unless-stopped`, port `8100:8100`, a `curl /health` health check, and three named volumes (`device-ai-models`, `device-ai-artifacts`, `device-ai-mlruns`). Its environment block restates the filesystem contract from the Dockerfile plus upload limits (`MAX_IMAGES=6`, `MAX_FILE_SIZE=10485760`) and `JSON_LOGS=false`.

### 5.4 Why Three Separate Stacks

The Compose files mirror the project's phased build-out: the database and backend were containerized first (Phase 2, per the dev-stack header comment), and the AI engine was containerized independently so it could be developed without touching the backend. The consequence — no unified stack, and the AI service not wired to the backend in Compose — is a real current limitation (§23), not a design endpoint.

---

## 6. Container Relationships

**Container Relationships Diagram**

```
   EXISTS IN COMPOSE (dev stack B)              EXISTS IN COMPOSE (stack C)
 ┌───────────────────────────────┐           ┌───────────────────────────────┐
 │ ecotrace-backend              │           │ ecotrace-device-ai            │
 │  • depends_on postgres        │           │  • standalone                 │
 │    (condition: service_healthy)│          │  • no dependency declared     │
 │  • DATABASE_URL → postgres    │           │  • volumes: models/artifacts/ │
 │  • publishes :3000            │           │    mlruns                     │
 └───────────────┬───────────────┘           │  • publishes :8100            │
                 │ TCP 5432                   └───────────────────────────────┘
                 ▼
 ┌───────────────────────────────┐
 │ ecotrace-postgres             │
 │  • healthcheck: pg_isready    │
 │  • volume: ecotrace-pgdata    │
 └───────────────────────────────┘

   NOT WIRED IN ANY COMPOSE FILE (integration is intended, not realized):
   backend ──HTTP──► device-ai      frontend ──HTTP──► backend
```

### 6.1 Declared Dependencies (what the files actually say)

- **backend → postgres** is the only cross-service dependency declared anywhere: `depends_on: { postgres: { condition: service_healthy } }` in the dev stack. Compose will not start the backend until the database reports healthy (§7).
- **device-ai** declares **no** `depends_on`; it is fully standalone.
- **frontend** appears in no Compose file at all.

### 6.2 Runtime Integration (what is intended but not composed)

- The backend is expected to call the AI service over HTTP (the AI compose header says exactly this), but **no Compose file places them on the same network**, and the backend's environment does not yet define an AI-service URL. The integration is HTTP-ready but not orchestrated.
- The frontend reaches the backend via `VITE_API_BASE_URL` (default `http://localhost:3000/api/v1`), a build/runtime configuration of the frontend, not a container link.

This separation is faithfully reported because inventing a backend↔AI Compose link would violate the "document exactly what exists" rule.

---

## 7. Service Startup Sequence

The only orchestrated startup ordering that exists is in the dev stack (B), where the backend waits on a healthy database.

**Startup Flow Diagram**

```
 docker compose -f deployment/docker/docker-compose.dev.yml up
        │
        ▼
 ┌──────────────────────────────┐
 │ 1. postgres starts           │
 │    postgres:16-alpine boots  │
 └──────────────┬───────────────┘
                │  Compose runs healthcheck:
                │  pg_isready -U ecotrace -d ecotrace
                │  every 5s, up to 10 retries
                ▼
        ┌───────────────┐   not healthy
        │ healthy?      │ ───────────────► keep probing (backend still waiting)
        └───────┬───────┘
                │ yes (condition: service_healthy satisfied)
                ▼
 ┌──────────────────────────────┐
 │ 2. backend starts            │
 │    node dist/server.js       │
 │    • loadConfig() validates  │
 │      env (fail-fast, §8)     │
 │    • app.listen(PORT=3000)   │
 └──────────────┬───────────────┘
                │  container HEALTHCHECK:
                │  wget /api/v1/health every 30s
                ▼
        ┌───────────────┐
        │ backend ready │  (readiness probe also checks DB, §16)
        └───────────────┘
```

### 7.1 Backend Process Startup (`backend/src/server.ts`)

Independent of Compose, the backend process itself follows a deterministic sequence: load `dotenv`, call `getConfig()` (which validates the environment through the Zod schema and **fails fast** on invalid configuration, §8), build the app, and `app.listen(config.port)`. It registers `SIGTERM`/`SIGINT` handlers that close the HTTP server and call `disconnectPrisma()` for a graceful shutdown, with a 10-second force-exit safety net. There is **no automatic database migration on startup** in the code — migrations are a separate operation ([08 — Database Architecture], §17 here).

### 7.2 AI Process Startup

The AI container's `CMD` launches Uvicorn serving `device_ai.app:app`. Settings are parsed once at import time via the `get_settings()` singleton (`pydantic-settings`, §8), and the ASGI app is constructed by `create_app()`. No dependency wait is declared because the standalone stack (C) has no dependencies.

### 7.3 Ordering Guarantee Scope

Health-gated ordering (`condition: service_healthy`) exists **only** in the dev stack for backend↔postgres. The root database-only stack and the AI stack have no inter-service ordering because each contains a single service.

---

## 8. Environment Configuration

Every service is configured by environment variables validated at startup — the twelve-factor "config in the environment" principle, consistent with [07 — Backend API Architecture] and [03 — Device Intelligence Architecture].

### 8.1 Backend Variables (validated by Zod — `env.schema.ts`)

| Variable | Default | Notes |
|---|---|---|
| `NODE_ENV` | `development` | `development | test | production` |
| `PORT` | `3000` | coerced int, 1–65535 |
| `API_PREFIX` | `/api/v1` | must start with `/` |
| `LOG_LEVEL` | `info` | `fatal…trace` |
| `DATABASE_URL` | — | URL; **required in production** (refinement) |
| `CORS_ORIGINS` | `http://localhost:5173` | comma-split into an allow-list |
| `JWT_SECRET` / `JWT_REFRESH_SECRET` | dev placeholders | ≥32 chars; **placeholders rejected in production** |
| `JWT_ACCESS_EXPIRY` / `JWT_REFRESH_EXPIRY` | `15m` / `7d` | token lifetimes |
| `BCRYPT_ROUNDS` | `10` | int 4–15 |
| `AUTH_RATE_LIMIT_WINDOW_MS` / `AUTH_RATE_LIMIT_MAX` | `900000` / `10` | auth-only rate limit |

The schema's `superRefine` enforces production hardening: in `production`, `DATABASE_URL` must be present, the JWT secrets must not start with `dev-insecure-`, and the two secrets must differ. This is a deployment-time safety net — a misconfigured production image fails fast rather than booting insecurely (§22).

### 8.2 AI Variables (validated by `pydantic-settings` — `configs/settings.py`)

The Device Intelligence Engine parses a strongly-typed `Settings` model once (cached via `@lru_cache`), from environment variables and an optional `.env`. Deployment-relevant fields include `HOST` (`0.0.0.0`), `PORT` (`8100`), the filesystem roots `MODEL_DIR`/`UPLOAD_DIR`/`ARTIFACT_DIR`/`MLRUNS_DIR`/`DATASET_DIR`, `EXPERIMENT_TRACKER` (`json`), `LOG_LEVEL`/`JSON_LOGS`, and upload bounds `MAX_IMAGES`/`MAX_FILE_SIZE`. Many additional model/engine tuning fields exist but are AI internals ([03]) and out of scope here. The Docker image sets deployment-critical defaults directly in its `ENV` block (§4.2) so the container is correctly configured even with an empty environment.

### 8.3 Frontend Variables (Vite `VITE_*`)

The frontend reads build-time variables prefixed `VITE_`: `VITE_API_BASE_URL` (default `http://localhost:3000/api/v1`), `VITE_API_TIMEOUT` (`15000`), `VITE_APP_NAME`, and `VITE_APP_VERSION`. Because Vite inlines these at build time, they are baked into the static bundle when `npm run build` runs (§9, §17).

### 8.4 `.env.example` Templates

Committed templates document each surface without leaking secrets: `backend/.env.example`, `frontend/.env.example`, and `intelligence/device_ai/.env.example`. The backend template explicitly warns that the `dev-insecure-*` JWT placeholders must be overridden in production. Real `.env` files are git-ignored and dockerignored (§22). (Root `.env.example` and `ai/.env.example` exist but are empty placeholders.)

---

## 9. Frontend Deployment

### 9.1 What Exists

The frontend (`frontend/`) is a **React 19 + Vite 6 single-page application** ([06 — Web Platform Architecture]). Its deployment artifact is a static build:

```
npm run build   →   tsc -b && vite build   →   frontend/dist/
                                                 ├── index.html
                                                 ├── favicon.svg
                                                 └── assets/   (hashed JS/CSS bundles)
```

The repository already contains a committed `frontend/dist/` output (built assets), confirming the build target.

### 9.2 What Does Not Exist

There is **no `frontend/Dockerfile`** and **no web-server configuration** (no NGINX config, no static-hosting manifest) committed for the frontend. In development it is served by the Vite dev server on port `5173` (`vite.config.ts`: `server.port = 5173`, `host: true`). For any deployed environment, the `dist/` bundle would be served by an external static host, CDN, or reverse proxy — but the repository does not yet prescribe or automate that.

### 9.3 Backend Coupling

The bundle is coupled to the backend only through `VITE_API_BASE_URL`, inlined at build time (§8.3). Deploying the frontend against a different backend origin therefore requires a rebuild with the appropriate `VITE_API_BASE_URL`, or a proxy that preserves the default `http://localhost:3000/api/v1` path shape. CORS on the backend must list the frontend origin (`CORS_ORIGINS`, §8.1).

---

## 10. Backend Deployment

### 10.1 Image and Runtime

The backend deploys as the multi-stage `node:20-alpine` image (§4.1): production dependencies only, compiled `dist/`, non-root `node` user, `EXPOSE 3000`, and `CMD ["node", "dist/server.js"]`. In the dev stack it is built from source (`build: ../../backend`); in CI it is built as `ecotrace-backend:ci` (§17).

### 10.2 Configuration at Deploy Time

The backend is fully environment-driven (§8.1). The dev stack injects `NODE_ENV`, `PORT`, `API_PREFIX`, `LOG_LEVEL`, and `DATABASE_URL` directly. For production, the Zod refinements force a real `DATABASE_URL` and strong, distinct JWT secrets before the process will boot (§22).

### 10.3 Database Dependency and Migrations

At runtime the backend reaches PostgreSQL via `DATABASE_URL` (Prisma, [08 — Database Architecture]). The dev stack sequences startup with `depends_on: service_healthy` (§7). Because the process performs **no automatic migration** on boot, applying migrations (`prisma migrate deploy`) is an operational step that must be run separately against the target database — a deliberate, forward-only posture consistent with [08].

### 10.4 Lifecycle

`SIGTERM`/`SIGINT` trigger graceful shutdown: stop accepting connections, disconnect Prisma, exit — with a 10-second force-exit guard (§7.1). This makes the container safe to stop and reschedule.

---

## 11. AI Service Deployment

### 11.1 Image and Runtime

The Device Intelligence Engine deploys as the multi-stage `python:3.12-slim` image (§4.2): offline wheel install, non-root `appuser`, `EXPOSE 8100`, and Uvicorn serving `device_ai.app:app`. The compose file tags it `ecotrace/device-ai:1.0.0`.

### 11.2 Model, Artifact, and Upload Directories

The image and compose file establish a clear filesystem contract, all under `/app`:

| Env var | Path | Holds |
|---|---|---|
| `MODEL_DIR` | `/app/models` | Versioned model artifacts (mounted volume) |
| `ARTIFACT_DIR` | `/app/artifacts` | Training checkpoints/exports/reports (mounted volume) |
| `MLRUNS_DIR` | `/app/mlruns` | Experiment-tracking runs (mounted volume) |
| `UPLOAD_DIR` | `/app/uploads` | Transient upload persistence (in-image; not a named volume) |

These directories are created and `chown`ed to `appuser` at build time so the non-root process can write to them (§4.2, §14).

### 11.3 Lean Base, Deferred Models

Per `requirements.txt` and the Dockerfile comments, only core runtime dependencies are installed; the heavy model stack (PyTorch, Ultralytics, OpenCLIP, EasyOCR, ONNX Runtime) is intentionally deferred to a future `requirements-models.txt`. Consequently the deployable image today runs the engine in its lightweight/mock-capable configuration ([03 — Device Intelligence Architecture]); model weights are supplied via the mounted `models` volume rather than baked into the image (`.dockerignore` excludes `models/**`).

### 11.4 Standalone Today

As noted (§6), the AI service is deployed standalone via stack (C). It is HTTP-ready for the backend to call, but no Compose wiring or backend-side URL joins them yet (§23).

---

## 12. Database Deployment

### 12.1 Image and Credentials

PostgreSQL is deployed from the official image — `postgres:16` in the root stack, `postgres:16-alpine` in the dev stack. Both set `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB` via environment. The credentials committed in the compose files (`ecotrace / ecotrace123` and `ecotrace / ecotrace`) are **local development defaults**, not production secrets (§22, §23).

### 12.2 Persistence

Data survives container restarts through a named volume mounted at `/var/lib/postgresql/data`: `postgres_data` (root stack) or `ecotrace-pgdata` (dev stack). Deleting the container preserves the volume; deleting the volume is the destructive reset (§14).

### 12.3 Readiness

The dev stack's `pg_isready -U ecotrace -d ecotrace` health check is what the backend's `depends_on: service_healthy` waits on (§7, §16). The schema and migration lifecycle themselves are the concern of [08 — Database Architecture]; here the database is treated purely as a deployable, stateful container.

---

## 13. Networking

**Network Topology Diagram**

```
 HOST (developer machine)
 ┌─────────────────────────────────────────────────────────────────────┐
 │  published ports (host:container)                                     │
 │                                                                       │
 │   localhost:5173 ──► Vite dev server (frontend, dev only)             │
 │   localhost:3000 ──► ecotrace-backend      :3000                      │
 │   localhost:5432 ──► ecotrace-postgres     :5432                      │
 │   localhost:8100 ──► ecotrace-device-ai    :8100                      │
 └─────────────────────────────────────────────────────────────────────┘

 Compose default bridge network (dev stack B only):
 ┌─────────────────────────────────────────────────────────────────────┐
 │   backend ──(service DNS name: "postgres":5432)──► postgres          │
 │   DATABASE_URL=postgresql://ecotrace:ecotrace@postgres:5432/ecotrace  │
 └─────────────────────────────────────────────────────────────────────┘

 No shared network joins backend ↔ device-ai (separate compose files).
 No NGINX / reverse proxy / gateway exists (deployment/nginx/ is empty).
```

### 13.1 Service Discovery

Within the dev stack, Compose's default bridge network provides DNS by service name: the backend resolves `postgres` to the database container, which is why `DATABASE_URL` uses `@postgres:5432`. This is the only intra-network service-to-service resolution configured.

### 13.2 Port Publishing

Every service publishes its port directly to the host (`3000`, `5432`, `8100`; the frontend dev server `5173`). There is no gateway consolidating these behind a single ingress, and no TLS termination — appropriate for local development, a gap for production (§20, §23).

### 13.3 Cross-Stack Isolation

Because the AI service lives in a separate Compose file, it is on a **different Compose network** from the backend. Any backend→AI call today would traverse the host (e.g. `http://localhost:8100`) rather than an internal service name, until a unified network is introduced (§24).

---

## 14. Storage Strategy

**Volume Layout Diagram**

```
 ┌────────────────────────────────────────────────────────────────────┐
 │ DATABASE (stateful)                                                 │
 │   root stack:  postgres_data     ─► /var/lib/postgresql/data        │
 │   dev  stack:  ecotrace-pgdata   ─► /var/lib/postgresql/data        │
 └────────────────────────────────────────────────────────────────────┘
 ┌────────────────────────────────────────────────────────────────────┐
 │ AI SERVICE (stateful artifacts)                                     │
 │   device-ai-models     ─► /app/models      (model weights)          │
 │   device-ai-artifacts  ─► /app/artifacts   (checkpoints/exports/…)  │
 │   device-ai-mlruns     ─► /app/mlruns      (experiment runs)        │
 │   (uploads: /app/uploads is in-image, transient — NOT a volume)     │
 └────────────────────────────────────────────────────────────────────┘
 ┌────────────────────────────────────────────────────────────────────┐
 │ BACKEND (stateless)  — no volumes; all state in PostgreSQL          │
 │ FRONTEND (stateless) — static dist/, no runtime volumes             │
 └────────────────────────────────────────────────────────────────────┘
```

### 14.1 Stateful vs. Stateless

- **PostgreSQL** is the only durable business-data store, on a named volume (§12.2). It is the system-of-record ([08 — Database Architecture]).
- **The AI service** persists model weights, training artifacts, and experiment runs on three named volumes, keeping large/generated assets out of the image and out of Git (§4.2, §11.2).
- **The backend and frontend are stateless.** The backend keeps no local state (everything is in PostgreSQL), and the frontend is immutable static output — both can be freely restarted or replicated (§21).

### 14.2 The `uploads` Exception

`UPLOAD_DIR` (`/app/uploads`) is created in the image but is **not** backed by a named volume in the compose file, so uploaded bytes there are transient and lost on container replacement — acceptable because uploads are described as transient/optional-use in the settings (§8.2), not a durable store.

---

## 15. Logging

### 15.1 Backend

The backend logs to **stdout** as structured records via its logger ([07 — Backend API Architecture]); verbosity is controlled by `LOG_LEVEL` (the dev stack sets `debug`). The startup line is a single structured record naming service, version, environment, port, API prefix, and log level — and, by design, never includes secrets (`server.ts`). Logging to stdout is the container-native pattern: the Docker runtime captures the stream.

### 15.2 AI Service

The Device Intelligence Engine uses Loguru, with `LOG_LEVEL` and a `JSON_LOGS` toggle (`configs/settings.py`). The compose file sets `LOG_LEVEL=INFO` and `JSON_LOGS=false` (human-readable console logs) for local runs; setting `JSON_LOGS=true` yields machine-readable JSON suitable for log aggregation. Output goes to stdout (`PYTHONUNBUFFERED=1` ensures it is not buffered away).

### 15.3 Aggregation Posture

Both services follow the "log to stdout, let the platform collect" model. The repository does **not** ship a log-aggregation stack (no ELK/Loki/etc.); collection is delegated to whatever runs the containers. This is sufficient for the current local/CI scope and is a documented v1 posture (§23, §24).

---

## 16. Health Monitoring

Health is enforced at two layers that the repository actually implements: application health endpoints and Docker health checks.

### 16.1 Application Endpoints

- **Backend:** `GET /api/v1/health` (liveness) and a readiness endpoint served by the health module; readiness includes a database check ([07 — Backend API Architecture], [08 — Database Architecture] `pingDatabase()` `SELECT 1`). The health routes are public (no authentication).
- **AI service:** `GET /health` returns per-component readiness, reporting `"healthy"` when every pipeline component is ready and `"degraded"` otherwise (`api/routes.py`). It also exposes `GET /` and `GET /version`.

### 16.2 Container Health Checks

Both Dockerfiles declare a `HEALTHCHECK` with identical cadence (`interval 30s`, `timeout 5s`, `start-period 10s`, `retries 3`):

- Backend: `wget -qO- http://127.0.0.1:3000/api/v1/health`.
- AI: `curl --fail http://localhost:8100/health`.

The AI compose file restates the same check; the dev-stack PostgreSQL uses `pg_isready`. These checks are what make `depends_on: service_healthy` meaningful (§7).

### 16.3 Documentation vs. Implementation Note

The engineering doc (`docs/engineering/11_DEPLOYMENT.md`) refers to the AI health path as `/internal/health`; the **implemented** path — in both the Dockerfile and `api/routes.py` — is `/health`. This document follows the implementation, per the "implementation is the source of truth" rule. Beyond endpoints and container checks, no metrics/alerting stack exists yet (§23).

---

## 17. Build Process

**Build Pipeline Diagram**

```
 ┌────────────────────────────────────────────────────────────────────────┐
 │ BACKEND IMAGE                                                            │
 │   build stage:  npm ci → npm run build (prisma generate → tsc →         │
 │                 tsc-alias) → /app/dist                                   │
 │   runtime stage: npm ci --omit=dev → COPY --from=build /app/dist         │
 │                 → node dist/server.js                                    │
 └────────────────────────────────────────────────────────────────────────┘
 ┌────────────────────────────────────────────────────────────────────────┐
 │ AI IMAGE                                                                 │
 │   builder stage: pip wheel -r requirements.txt → /wheels                 │
 │   runtime stage: pip install --no-index --find-links=/wheels             │
 │                 → COPY . /app/device_ai → uvicorn device_ai.app:app      │
 └────────────────────────────────────────────────────────────────────────┘
 ┌────────────────────────────────────────────────────────────────────────┐
 │ FRONTEND BUNDLE (no image)                                               │
 │   npm run build → tsc -b && vite build → frontend/dist/ (static)         │
 └────────────────────────────────────────────────────────────────────────┘
 ┌────────────────────────────────────────────────────────────────────────┐
 │ CI (.github/workflows/backend-ci.yml)  — backend only                    │
 │   quality job: checkout → setup-node 20 (npm cache) → npm ci →           │
 │     lint → typecheck → format:check → test → build                       │
 │   docker  job: needs quality → docker/build-push-action                  │
 │     context=backend, push=false, tags=ecotrace-backend:ci                │
 └────────────────────────────────────────────────────────────────────────┘
```

### 17.1 Image Builds

Both images are multi-stage (§4). The backend's compile step is `npm run build` = `prisma generate && tsc -p tsconfig.build.json && tsc-alias` — Prisma client generation is a build prerequisite ([08 — Database Architecture]). The AI build front-loads dependency compilation into wheels so the runtime install is offline and toolchain-free.

### 17.2 Frontend Build

`npm run build` type-checks (`tsc -b`) then bundles with Vite into `frontend/dist/`. This is a build artifact, not an image (§9).

### 17.3 Continuous Integration (only what exists)

`.github/workflows/backend-ci.yml` is the **only** workflow. It triggers on `workflow_dispatch` and on `push`/`pull_request` to `develop`/`main` filtered to `backend/**` and the workflow file itself. Two jobs:

1. **`quality`** — on `ubuntu-latest`, Node 20 with npm cache: `npm ci`, then `lint`, `typecheck`, `format:check`, `test`, `build`. This mirrors the Definition of Done gates in CLAUDE.md.
2. **`docker`** — `needs: quality`; builds the backend image with `docker/build-push-action@v6` (`context: backend`, `push: false`, `tags: ecotrace-backend:ci`). It **builds but does not publish** — there is no registry push, and no deploy step.

There is **no** CI for the frontend, the AI service, end-to-end tests, image publishing, or deployment. Reporting this accurately matters: the "CI/CD readiness" of the repository is *CI for the backend, no CD anywhere*.

---

## 18. Configuration Management

### 18.1 Principles Actually Enforced

- **Config in the environment.** No service hardcodes deployment parameters; all read env vars (§8).
- **Validated at startup, fail-fast.** The backend rejects invalid/insecure config via Zod refinements; the AI service validates types via `pydantic-settings`. A bad configuration stops the process rather than producing undefined behavior.
- **Templates, not secrets, in Git.** `*.env.example` files document each surface; real `.env` files are git-ignored and excluded from image contexts (§22).
- **Sensible in-image defaults.** The AI Dockerfile bakes non-secret operational defaults (paths, port, tracker) so the container is runnable with an empty environment; secrets are never among them.

### 18.2 Per-Stack Overrides

The dev stack overrides backend config inline (development log level, in-network `DATABASE_URL`). The AI compose file overrides operational knobs (upload limits, log format). This is "build once, configure per environment" applied at the Compose layer.

### 18.3 Gap vs. Engineering Intent

`docs/engineering/11_DEPLOYMENT.md` references a `deployment/env/` directory of per-environment templates; that directory does not exist. Today the templates live beside their services (`backend/`, `frontend/`, `intelligence/device_ai/`).

---

## 19. Development Workflow

### 19.1 Common Local Paths

The repository supports several local workflows, each backed by a real asset:

- **Database only + backend on host:** `docker compose up` (root `docker-compose.yml`) starts PostgreSQL on `5432`; run the backend with `npm run dev` (`tsx watch`) pointing `DATABASE_URL` at `localhost:5432`.
- **Containerized backend + database:** `docker compose -f deployment/docker/docker-compose.dev.yml up` builds and runs both, with health-gated ordering (§7).
- **AI service:** `docker compose -f intelligence/device_ai/docker-compose.yml up` (or `uvicorn device_ai.app:app`) on `8100`.
- **Frontend:** `npm run dev` (Vite) on `5173`, pointing `VITE_API_BASE_URL` at the backend.

### 19.2 Quality Gates Locally

The same commands CI runs are available as npm scripts (`lint`, `typecheck`, `format:check`, `test`, `build`), and Husky/lint-staged enforce them on commit for the backend. Running them locally reproduces the CI `quality` job exactly (§17.3), consistent with the Definition of Done in CLAUDE.md.

### 19.3 Branch/CI Interaction

CI fires on `push`/`pull_request` to `develop`/`main` for `backend/**` changes, matching the `feature → PR → develop → main` workflow mandated by the project. Frontend and AI changes are not yet gated by CI (§23).

---

## 20. Production Considerations

The repository is **demo/development-ready, not production-hardened**. Stated honestly against what exists:

### 20.1 What Is Production-Aligned

- **Non-root containers** and **multi-stage minimal images** for both services (§4).
- **Fail-fast production config guards** in the backend: real `DATABASE_URL` required, dev JWT placeholders rejected, secrets must differ (§8.1, §22).
- **Graceful shutdown** on `SIGTERM`/`SIGINT` (§7.1).
- **Health checks** suitable for orchestrator readiness/liveness probes (§16).
- **Stateless backend/frontend + volume-backed stateful services** (§14) — the right shape for horizontal scaling and safe restarts.

### 20.2 What Is Missing for Production

- No reverse proxy / TLS termination / single ingress (`deployment/nginx/` empty).
- No image publishing or deployment automation (CI builds, never pushes; no CD) (§17.3).
- No unified full-stack orchestration; the AI service is not wired to the backend (§6, §23).
- No secrets manager; compose credentials are local defaults (§22).
- No metrics/alerting/log-aggregation stack (§15.3, §16.3).
- No frontend deployment automation or image (§9).
- No blockchain deployment ([05 — Blockchain Architecture]) — none exists in the repo.

These are not defects to hide; they are the accurate boundary between the current prototype deployment and a production one (§24).

---

## 21. Scalability

Scalability is assessed only against the realized architecture.

### 21.1 Horizontal Scaling Readiness

- **Backend** is stateless (all state in PostgreSQL, [08 — Database Architecture]), so multiple replicas can run behind a future load balancer without sticky sessions — JWT auth is stateless by design ([07 — Backend API Architecture]). Each replica opens its own Prisma connection pool; aggregate database connections scale with replica count (the primary scaling parameter to watch, per [08]).
- **AI service** is likewise request/response and stateless per call (durable data lives on the model/artifact volumes), so it can be replicated — provided replicas share access to model weights (today via a local named volume, which would need shared/read-only storage across nodes to scale out, §24).
- **Frontend** is static; it scales trivially via any CDN/static host (§9).

### 21.2 Vertical and Data Scaling

PostgreSQL scales vertically and via the evolution options in [08 — Database Architecture] (indexes, read replicas, pooling). The single-container database in the compose files is a development convenience, not a scaling ceiling of the design.

### 21.3 Current Constraints

There is no orchestrator, load balancer, or autoscaler in the repository, so scaling is presently manual (`docker compose up --scale` is not configured, and services publish fixed host ports that would collide if naively scaled). Real horizontal scaling is a §24 concern.

---

## 22. Security Considerations

Security controls that actually exist in the deployment assets:

### 22.1 Image and Runtime Hardening

- **Non-root execution** in both images (`USER node`; `USER appuser`).
- **Minimal runtime surface** — production-only dependencies (backend `--omit=dev`), offline wheel install (AI), no compiler toolchain in runtime stages, no source maps or tests shipped (`.dockerignore`).
- **`.env` excluded from build context** in both `.dockerignore` files — secrets cannot be baked into image layers.

### 22.2 Configuration Security

- **Production config refinements** (backend Zod `superRefine`): `DATABASE_URL` mandatory; `dev-insecure-*` JWT secrets rejected; access and refresh secrets must differ; secret length ≥ 32. A misconfigured production image fails to boot rather than running insecurely.
- **CORS allow-list** via `CORS_ORIGINS`; **auth rate limiting** via `AUTH_RATE_LIMIT_*` — both environment-tunable per deployment ([07 — Backend API Architecture]).
- **Secrets never in Git** — only `*.env.example` templates are committed; the backend template explicitly warns to replace placeholders in production.

### 22.3 Known Security Gaps (honest)

- **Compose credentials are plaintext local defaults** (`ecotrace123`, `ecotrace`) — acceptable for local dev, unacceptable for production; no secrets manager is wired.
- **No TLS anywhere** — all published ports are plaintext HTTP/TCP; there is no gateway to terminate TLS (§13, §20).
- **Database and AI ports are published to the host** rather than kept private behind a gateway, contrary to the engineering intent that they not be publicly exposed (§13.2, §23).

---

## 23. Current Limitations

Stated plainly, from the repository as it stands:

- **No unified full-stack orchestration.** Three separate Compose files exist; none brings the whole platform up together. There is no `docker-compose.yml` that includes backend + AI + database + frontend.
- **AI service not wired to the backend.** They live in different Compose files on different networks; no backend-side AI URL and no shared network exist (§6, §13.3).
- **No frontend container or deployment automation.** The frontend builds to static `dist/` with no image and no serving config (§9).
- **CI is backend-only; no CD.** One workflow gates the backend and builds (never pushes) its image. No frontend/AI CI, no E2E, no image publishing, no deploy (§17.3).
- **Empty placeholder directories.** `deployment/kubernetes/`, `deployment/nginx/`, and `scripts/{database,deployment,setup,utilities}/` exist but are empty — no Kubernetes manifests, no NGINX config, no automation scripts.
- **No gateway / TLS / secrets manager / metrics stack.** (§15.3, §16.3, §20.2, §22.3.)
- **No blockchain deployment.** Consistent with there being no deployable blockchain assets in the repo ([05 — Blockchain Architecture]).
- **Engineering doc is partly aspirational.** `docs/engineering/11_DEPLOYMENT.md` describes NGINX, Fabric, a dashboard image, `deployment/env/`, auto-migration on startup, and `/internal/health` — none of which are implemented as described. This architecture document intentionally diverges from it wherever it diverges from the code.

---

## 24. Future Deployment Evolution

Aligned with the roadmap in [01 — System Architecture] and the intent captured in `docs/engineering/11_DEPLOYMENT.md`, plausible next steps — **none implemented today** — include:

- **A unified `docker-compose.yml`** joining backend, AI, PostgreSQL, and a served frontend on one network, with the backend given an AI-service URL and health-gated ordering across all services.
- **An NGINX (or equivalent) gateway** for single-ingress routing (`/api/*` → backend, `/` → frontend static assets), TLS termination, and keeping the database and AI service off the public network.
- **A frontend image / static-hosting pipeline** (containerized static server or CDN deploy of `dist/`).
- **CI/CD maturation:** frontend and AI CI jobs, E2E on the composed stack, image publishing to a registry, and a deploy stage with smoke tests.
- **Secrets management** replacing plaintext compose credentials; per-environment secret provisioning outside Git.
- **Shared model storage** for AI horizontal scaling (read-only shared volume or object storage for `MODEL_DIR`).
- **Observability stack:** metrics and alerting alongside the existing logs + health checks.
- **Orchestration** (the empty `deployment/kubernetes/` signals the intended direction) once the unified Compose stack is proven.

Each item is a clean addition to the existing container-first foundation, not a rewrite.

---

## 25. Design Rationale

Why the deployment is shaped the way it is:

- **Container-first, twelve-factor.** Every runnable service is a multi-stage, non-root, health-checked image configured only through the environment. This makes services reproducible, environment-agnostic, and safe to restart — the foundation any later orchestration builds on.
- **Separate Compose files reflect phased delivery.** The database/backend stack and the AI stack were containerized independently so each subsystem could progress without coupling. The cost (no unified stack yet) is accepted deliberately and tracked as a limitation, not disguised.
- **Lean images, externalized heavy assets.** Both images defer bulk out of the image — dev dependencies (backend) and model weights/heavy ML packages (AI) — keeping builds fast and images small, with large artifacts on volumes and out of Git.
- **Fail-fast configuration.** Validating env at startup (Zod / pydantic-settings) turns misconfiguration into an immediate, visible boot failure rather than a latent production incident — especially the backend's production secret guards.
- **Honesty over completeness.** The repository does not pretend to a production platform it has not built. Documenting exactly the two images, three compose files, and one CI workflow that exist — and naming the empty placeholders — is what makes this architecture record trustworthy to IEEE reviewers and DevOps engineers alike.
- **Stateless compute, stateful data.** Concentrating durable state in PostgreSQL and AI volumes while keeping backend and frontend stateless is the single most important enabler of the future scaling and orchestration in §24.

---

## 26. Conclusion

EcoTrace India's deployment layer is a disciplined, container-first foundation that is deliberately partial. Two multi-stage, non-root, health-checked images (backend on `node:20-alpine`, the Device Intelligence Engine on `python:3.12-slim`), three focused Docker Compose stacks (database-only, a health-gated backend+database dev stack, and a standalone AI stack with persistent model/artifact/experiment volumes), a static Vite frontend build, and a single backend CI workflow constitute the entirety of what the repository deploys today. Configuration is uniformly environment-driven and validated at startup; state is concentrated in PostgreSQL and the AI volumes while the backend and frontend remain stateless.

Every component described here is present in `backend/Dockerfile`, `intelligence/device_ai/Dockerfile`, the three `docker-compose*.yml` files, the `.dockerignore` and `.env.example` templates, and `.github/workflows/backend-ci.yml` — nothing was invented, and the gaps (no unified stack, no gateway, no CD, no Kubernetes/NGINX, empty placeholder directories) are named as plainly as the assets. The result is a deployment architecture that is reproducible and honest about its boundary: a strong prototype foundation for the IEEE YESIST 2026 demonstration, with a clear, additive path (§24) toward a production platform beneath the subsystems documented in [01]–[08].

---

*Source of truth: `backend/Dockerfile`, `intelligence/device_ai/Dockerfile`, `docker-compose.yml`, `deployment/docker/docker-compose.dev.yml`, `intelligence/device_ai/docker-compose.yml`, `backend/.dockerignore`, `intelligence/device_ai/.dockerignore`, `.github/workflows/backend-ci.yml`, the `*.env.example` templates, `backend/src/shared/config/env.schema.ts`, `backend/src/server.ts`, `intelligence/device_ai/configs/settings.py`, and `intelligence/device_ai/api/routes.py`. This document reverse-engineers the deployment layer only and does not modify Documents 01–08.*
