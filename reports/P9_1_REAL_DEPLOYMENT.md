# P9.1 — Real Deployment Environment

Status: **COMPLETE WITH ENVIRONMENTAL LIMITATIONS**

## 1. Scope

Move the local/demo Docker Compose stack (established P7.5, hardened P8.1–P8.10) closer to a
reproducible, production-like deployment, without rewriting its working architecture. Concretely:
audit and verify env-var configuration, secrets handling, service health/dependencies, DB
migration startup, clean builds, inter-service communication, graceful shutdown, restart
behavior, log hygiene, and — the one net-new capability this phase adds — optional local/demo TLS
termination on the frontend, satisfying the P9.1 instruction "if reverse proxy/TLS infrastructure
is possible locally, configure and validate it."

Real cloud deployment was explicitly out of reach: no cloud credentials exist anywhere in this
repository or environment, and the P9 order forbids inventing them. That capability is classified
`BLOCKED — ENVIRONMENT` below, not silently skipped.

## 2. Baseline (start of phase)

- Branch `develop`, HEAD `6f027c3347872b8243dc8481bd6e8f0bc5320b24` = `origin/develop`, clean tree.
- P8 final verdict: COMPLETE WITH ENVIRONMENTAL LIMITATIONS.
- Compose stack: `postgres`, `backend`, `device-ai`, `frontend` — no Fabric service (documented,
  intentional; see `docker-compose.yml` header comment and `docs/engineering/11_DEPLOYMENT.md`).
- All 6 protected asset hashes verified MATCH before any work began.

## 3. Implementation

### 3.1 Optional local/demo TLS termination (net-new capability)

Added opt-in HTTPS to the frontend nginx container, selected at **container startup** (not build
time) based purely on whether a certificate is mounted — so the default `docker compose up`
experience (plain HTTP on 8080) is completely unaffected unless a user deliberately opts in.

- `deployment/tls/generate_local_cert.sh` — generates a self-signed cert for local/demo use only
  (`openssl req -x509 -newkey rsa:2048 -days 365`, SAN `DNS:localhost,IP:127.0.0.1`). Explicitly
  documented as not production-grade; a real deployment mounts a real CA-issued cert at the same
  two filenames with no other config change needed.
- `frontend/nginx.tls.conf` (new) — HTTP→HTTPS 301 redirect + HTTPS server block, alongside the
  unchanged default `frontend/nginx.conf` (HTTP-only, byte-identical to P7.5 except a header
  comment explaining the split).
- `frontend/docker-entrypoint-tls.sh` (new) — chooses which config to activate on **every single
  container start** (checks for `/etc/nginx/tls/tls.crt` + `tls.key`), then `exec`s the base
  `nginx:1.27-alpine` image's own entrypoint rather than replacing it.
- `frontend/Dockerfile` — stages both configs at fixed paths, wires up the new entrypoint,
  extends the `HEALTHCHECK` to probe whichever protocol is actually active.
- `docker-compose.yml` — maps `FRONTEND_TLS_PORT` (default 8443) alongside the existing
  `FRONTEND_PORT` (default 8080), mounts `./deployment/tls:/etc/nginx/tls:ro` (safe when empty),
  passes `FRONTEND_TLS_PORT` through as an env var so the HTTP→HTTPS redirect names the correct
  host-mapped port, and updates the compose-level `healthcheck:` (which overrides the Dockerfile's)
  to match.
- `.gitignore` — added `deployment/tls/*.crt` and `deployment/tls/*.key` so generated cert
  material is never committed, even self-signed local ones.

Two real defects were found and fixed by live testing before this was considered done (full detail
in §5). The frontend was left in its plain-HTTP resting state at the end of this phase — the
existing demo tooling (`scripts/demo/*.py`, `QUICKSTART.md`) assumes plain `http://localhost:8080`,
and changing that default was out of scope for this phase.

### 3.2 Verified, unchanged from prior phases (re-confirmed fresh this phase)

- Zero hardcoded secrets: `docker-compose.yml` uses `${VAR:-local-dev-placeholder}` for every
  credential; source-tree grep for hardcoded password/secret/api-key literals found nothing besides
  a third-party library's own docstring example (`pydantic/types.py`).
- Env-var templates: `FRONTEND_TLS_PORT` follows the exact same documentation convention already
  used by `FRONTEND_PORT`/`BACKEND_PORT`/`DEVICE_AI_PORT` — documented in `docker-compose.yml`'s
  own comments, not `.env.example` (root `.env.example` explicitly defers to compose's comments
  for these). No gap introduced.
- DB migrations remain a deliberate, explicit, non-automatic step (documented
  `docs/engineering/11_DEPLOYMENT.md:107-114`, verified with a real round-trip in P7.10). This
  phase re-confirmed both are currently at head against the live compose Postgres:
  - Prisma: `prisma migrate status` → "Database schema is up to date!" (6 migrations found).
  - Alembic: `alembic current` → `003_add_p511_external_trust_anchors (head)`.

## 4. Tests performed

| Test | Result |
|---|---|
| `docker compose build --no-cache` (backend, device-ai, frontend) | PASS — VERIFIED (12m39s, exit 0, all 3 images built) |
| `docker compose up -d` from cold stop, freshly-built images | PASS — VERIFIED (all 4 services `healthy` within 37s) |
| API health smoke tests (`/api/v1/health`, `/health`) | PASS — VERIFIED |
| Inter-service call (backend → device-ai blockchain-health proxy) | PASS — VERIFIED (honest `"status":"disabled"`, matches known limitation) |
| Correlation ID present on responses (`x-request-id`) | PASS — VERIFIED |
| `docker compose stop` graceful shutdown, all 4 services | PASS — VERIFIED (2.4s total; SIGTERM handled cleanly by backend/device-ai/nginx; Postgres clean checkpoint shutdown) |
| Restart behavior (full stack cold stop → up) | PASS — VERIFIED |
| TLS opt-in: cert present → HTTPS active, correct redirect port, healthcheck passes | PASS — VERIFIED |
| TLS opt-in: cert removed → clean fallback to plain HTTP, no crash, idempotent across restart | PASS — VERIFIED (after fixing the idempotency defect, §5) |
| Live container log secret-scan (all 4 services) | PASS — VERIFIED (no password/secret/token/key leakage; `authorization` header explicitly `[REDACTED]`) |
| Source-tree hardcoded-secret grep | PASS — VERIFIED (no findings in project code) |
| Migration status (Prisma + Alembic) against live DB | PASS — VERIFIED (both at head, zero drift) |
| Backend regression suite | PASS — VERIFIED (341/341) |
| device_ai regression suite | PASS — VERIFIED (1121/1121, 0 errors) |
| Chaincode regression suite | PASS — VERIFIED (47/47) |
| Frontend typecheck / lint / build | PASS — VERIFIED (all clean) |
| Real cloud deployment | BLOCKED — ENVIRONMENT (no cloud credentials exist anywhere in this repo/environment; never invented) |
| Protected asset verification (6/6) | PASS — VERIFIED (all MATCH, before and after) |

## 5. Failures found, root causes, and fixes

All four were found and fixed during this phase's own live testing, before commit — none were
pre-existing defects from P8.

1. **Windows Git-Bash/MSYS path-mangling of `openssl -subj`.** `generate_local_cert.sh`'s first run
   corrupted the `-subj` argument into a Windows path. Root cause: MSYS auto-converts leading-slash
   arguments. Fix: `export MSYS_NO_PATHCONV=1` / `MSYS2_ARG_CONV_EXCL="*"` before the `openssl`
   call — a no-op on real Linux/macOS.
2. **Missing port in the HTTP→HTTPS redirect.** `nginx.tls.conf` originally redirected to the
   implicit default port 443, which is not host-reachable (only the non-standard 8443 is mapped).
   Fix: templated the redirect target via a `__TLS_PORT__` placeholder substituted at container
   startup from `FRONTEND_TLS_PORT`.
3. **Healthcheck cert-validation failure when TLS is active.** Both the Dockerfile `HEALTHCHECK`
   and the compose-level `healthcheck:` (which overrides it) originally probed plain HTTP
   unconditionally; with TLS active, that hits a self-signed-cert redirect that plain `wget`
   rejects. Fix: both checks now branch on certificate-file presence, using
   `wget --no-check-certificate` for the HTTPS case — safe because it is a container-internal
   loopback check only, never external traffic.
4. **Non-idempotent entrypoint across `docker compose restart` (most significant).** After
   verifying WITH a cert, removing the cert and restarting crashed the container into a restart
   loop: nginx refused to start because `/etc/nginx/conf.d/default.conf` still held the
   TLS-referencing config written during the *previous* start (`docker compose restart` reuses the
   same container's writable filesystem layer — the "no cert" branch only printed a message and
   never actively restored the plain-HTTP config). Fix: staged an immutable copy of the original
   HTTP-only config at a fixed path (`/etc/nginx/nginx.http.conf`) in the image, and changed the
   "no cert" branch to explicitly `cp` it into `conf.d/default.conf` on every single start,
   regardless of prior state. Re-verified the full cycle in both directions after the fix: cert
   present → HTTPS active (200, 301 redirect to the correct port, healthy); cert removed →
   restart → clean fallback to plain HTTP (200, no crash, `RestartCount=0`, healthy).

Separately, unrelated to the TLS work: the `intelligence/device_ai/.venv` was missing
`cryptography`, `grpcio`, and `protobuf` (all pinned in `requirements.txt` for the P6.2 Fabric
Gateway client) — a stale local venv, not a repository defect. Installed the three pinned versions
directly (all had prebuilt Windows wheels, no rebuild needed) rather than a blind
`pip install -r requirements.txt`, which triggered a numpy source rebuild failure unrelated to the
actual gap (Python 3.14 lacks a prebuilt numpy 2.2.1 wheel; the already-installed numpy 2.5.1 was
left untouched). This restored the full 1121-test device_ai suite to a runnable state with 0
failures — not a code fix, an environment-sync fix.

## 6. Files changed

- `.gitignore` — ignore generated `deployment/tls/*.crt` / `*.key`.
- `deployment/tls/generate_local_cert.sh` (new).
- `frontend/nginx.conf` (unchanged content, header comment updated).
- `frontend/nginx.tls.conf` (new).
- `frontend/docker-entrypoint-tls.sh` (new).
- `frontend/Dockerfile` (runtime stage: stage both configs, new entrypoint, TLS-aware healthcheck).
- `docker-compose.yml` (frontend: TLS port mapping, tls volume mount, TLS-aware healthcheck).
- `reports/P9_1_REAL_DEPLOYMENT.md` / `.json` (this report).

No protected asset was modified. No backend/device-ai/chaincode/mobile source was touched.

## 7. Security observations

- No secrets logged anywhere across all 4 services (explicit log scan performed).
- No hardcoded secrets in project source (explicit grep performed).
- Self-signed TLS cert is explicitly local/demo-only and gitignored; the design supports dropping
  in a real CA-issued cert with zero code changes.
- `SERVICE_API_KEY` (P8.7) and `secure_url_guard.dart` (P8.7) remain unchanged and unaffected.

## 8. Environmental limitations (honest, per P9 classification scheme)

| Item | Classification | Detail |
|---|---|---|
| Real cloud deployment | `BLOCKED — ENVIRONMENT` | No cloud provider credentials exist in this repository or environment; the P9 order explicitly forbids inventing them. |
| Live Hyperledger Fabric network | `BLOCKED — ENVIRONMENT` (unchanged from P8) | No peer/orderer/CA binaries or channel artifacts exist; addressed in depth in P9.2. |
| Reverse proxy in front of the whole stack (unified origin for frontend+backend+device-ai) | `NOT APPLICABLE` to this phase | Considered and deliberately scoped out — would require reworking CORS/`VITE_API_BASE_URL` and rewriting working, already-hardened architecture (P7.5/P8.7) for no P9.1-mandated benefit; the narrower "optional TLS on the existing frontend container" fully satisfies P9.1's own conditional instruction without that overreach. |

## 9. Protected asset verification

Verified before this phase began and again after all implementation/tests, against the exact file
paths and hashes established in `reports/P5_1_DEVICE_INTELLIGENCE_PRODUCTION.md`:

| Asset | Expected SHA-256 | Result |
|---|---|---|
| P4.4.2 YOLO11n | `c40a4afc...9218e92` | MATCH |
| P4.11 Targeted Aug | `ca10aaf0...a97355c` | MATCH |
| P4.12 YOLO11s | `96f156d0...f0380bc` | MATCH |
| P4.14 Targeted Aug | `8fdb02a4...9e9d81` | MATCH |
| P4.5 Data YAML | `b5fae47d...bdf5b` | MATCH |
| P4.7 Data YAML | `5daa90ae...e60e284` | MATCH |

All 6/6 MATCH. No protected asset was modified at any point in this phase.

## 10. Git state at end of phase

- Branch `develop`.
- All P9.1 changes committed in a single commit: `feat(p9): establish production-like deployment environment`.
- Pushed to `origin/develop`; `HEAD == origin/develop` verified.
- Working tree clean after push.

## 11. Final verdict

**P9.1 COMPLETE WITH ENVIRONMENTAL LIMITATIONS.** Every task within genuine reach of this
environment was executed and verified live (clean no-cache builds, full-stack clean startup, health
checks, smoke tests, migration status, graceful shutdown, restart idempotency including a real
defect found and fixed, log/source secret hygiene, opt-in local TLS, full regression suite). Real
cloud deployment remains `BLOCKED — ENVIRONMENT` for the only reason the P9 order permits: no
credentials exist and none were invented.
