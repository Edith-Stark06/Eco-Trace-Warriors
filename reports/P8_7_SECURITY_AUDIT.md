# P8.7 — Security & Privacy Audit

## 1. Scope

Builds on (does not re-derive) P7.4's full threat model and P6.8's earlier
hardening — this phase re-verifies those findings still hold against
current source, adds the categories P7.4 didn't cover in depth (a full
5-role authorization matrix, container runtime-user verification, CORS/
headers/error-leakage/correlation re-confirmation, mobile secrets/HTTP/
logging), and fixes two real, newly-found gaps.

---

## 2. Real gap #1 (CRITICAL→fixed): `intelligence/device_ai` had zero authentication

**Finding.** Every route in the Python AI service — `POST /devices/
register`, `.../confirm`, `.../finalize`, `.../enrich`, `POST .../passport/
anchor`, `POST .../passport/external-anchor`, `POST .../passport/reanchor`,
every `GET` — had **no authentication mechanism at all** (confirmed by
grep across `api/*.py` and `application.py`: zero `APIKeyHeader`/
`HTTPBearer`/`Depends(require_auth)` hits). The backend's JWT/RBAC layer
(§3) never sits in front of this service; nothing else did either.
`docker-compose.yml` maps this service's port to the host
(`"${DEVICE_AI_PORT:-8100}:8100"`, for local dev/demo convenience —
`scripts/demo/run_demo.py` and this phase's own P8.5/P8.6 evidence both
call it directly at `localhost:8100`), so in this deployment configuration
anyone reaching that port could register arbitrary devices and create or
overwrite local/external trust anchors — the exact trust-critical surface
this project's own architectural principles (CLAUDE.md /
`docs/engineering/`) require to stay protected — with zero credential.

**Severity: HIGH** (not maximal — exploitability depends on network
reachability to port 8100, a deployment-topology decision; the demo
compose file's host mapping is explicitly for local convenience, not a
claim about a real pilot's network boundary). But the application itself
provided no defense-in-depth if that boundary were ever misconfigured, so
this is fixed, not just documented.

**Fix — opt-in, backward-compatible shared-secret gate:**
- `configs/settings.py`: new `service_api_key: str | None` (default
  `None` = open, unchanged behavior for every existing caller: local dev,
  `run_demo.py`, the full test suite). Extended the existing
  `_validate_production_safety` model-validator (the same one that already
  requires `FABRIC_*`/`DATABASE_URL` in production) to also require
  `SERVICE_API_KEY` when `ENVIRONMENT=production` — mirrors the identical
  "refuse insecure defaults in production" pattern `backend/src/shared/
  config/env.schema.ts` already uses for JWT secrets.
- `api/service_auth.py` (new): `ServiceApiKeyMiddleware`, a raw ASGI
  middleware (same style as the existing `RequestContextMiddleware`) that,
  when `service_api_key` is set, requires a matching `X-Service-Api-Key`
  header on every route **except** a small public allowlist (`/`,
  `/health`, `/version`, `/metrics`, `/docs`, `/openapi.json`, `/redoc`,
  and `/system/blockchain/health` — the one read-only route the backend's
  own proxy actually calls, already public on the backend side for the
  same reason: no sensitive data, no writes).
- `application.py`: wired in right after `RequestContextMiddleware` so a
  401 still gets a correlation id and gets logged.
- `docker-compose.yml` / `.env.example`: `SERVICE_API_KEY` documented,
  defaults to empty (open) — no change to the demo/pilot stack's current
  posture unless an operator sets it.
- **No backend change needed**: the backend's only call to this service
  (`blockchain.service.ts` → `GET /system/blockchain/health`) is already
  in the public allowlist.

**Tests** (`tests/test_p87_service_auth.py`, 8 new): both the unset
("open, unchanged") and configured ("enforced, public routes still open")
halves of the contract, covering a sensitive mutating route (register), a
sensitive read route, the wrong key, and the correct key. Plus 3 new tests
in `tests/test_p72_production_config_validation.py` extending the existing
production-safety suite. **11/11 new, 1121/1121 full suite** (1110
baseline + 11 new — see §8).

**Live-verified against the real running container** (not just
in-process tests): rebuilt `device-ai`, confirmed the default (no key
configured) stack behaves identically to every prior phase
(`GET /devices/DEV-NONEXISTENT-CHECK` → real `404 DEVICE_NOT_FOUND`, not a
401), then in an isolated throwaway container with `SERVICE_API_KEY` set:
no header → `401`; wrong key → `401`; correct key → real `404` (reached
the actual handler); `/health` with no header → `200` (public allowlist
intact). All four outcomes exactly as designed.

---

## 3. Real gap #2 (MEDIUM→fixed): mobile apps had no release-build guard against shipping plain HTTP

**Finding.** Both `AppConfig.apiBaseUrl` defaults to
`http://10.0.2.2:3000` (the Android-emulator alias for the host's
`localhost`), overridable via `--dart-define=API_BASE_URL=https://...`.
Nothing enforced that override actually happened before a release build
shipped — a forgotten `--dart-define` would silently ship a release APK
still pointing at plain HTTP (in practice this fails to connect for a real
user, since `10.0.2.2` isn't routable outside an emulator, but the app
gives no earlier, clearer signal that the build itself was misconfigured).

**Severity: MEDIUM** (real actual exploitability is low — the emulator-only
address means a shipped mistake manifests as "app doesn't work," not silent
plaintext transport to a real server — but the fix is cheap, safe, and
mirrors an established pattern, so it's fixed rather than merely noted).

**Fix**: `lib/core/config/secure_url_guard.dart` (new, both apps) —
`assertSecureApiUrl({url, isReleaseMode})` throws `InsecureApiUrlError`
when `isReleaseMode && !url.startsWith('https://')`. Takes both values as
parameters (not read internally) so the logic is unit-testable without an
actual release build. Wired into both `main.dart`s: `assertSecureApiUrl(
url: AppConfig.apiBaseUrl, isReleaseMode: kReleaseMode)` before `runApp`.
Debug/profile builds (`kReleaseMode == false`) are completely unaffected —
the local-dev HTTP default keeps working exactly as before.

**Tests** (`secure_url_guard_test.dart`, 4 per app, 8 total): allows HTTP
in debug, allows HTTPS in release, throws on the plain-HTTP default in
release, error message names the offending URL.

**Results**: Collector app **26/26** (22 baseline + 4 new), 0 analyze
issues. Consumer app **22/22** (18 baseline + 4 new), 0 analyze issues.

---

## 4. Authentication (re-verified)

- bcrypt password hashing (configurable rounds, default 10), JWT
  access/refresh with separate secrets and expiries, refresh tokens
  server-side and revocable — all pre-existing (P5–P6), unchanged.
- `authRateLimiter` on `/auth/*` (P7.4): **re-confirmed live** this
  session — P8.6's own load test against `/auth/login` was correctly
  blocked with `429` after the configured threshold (`AUTH_RATE_LIMIT_MAX
  =10`/window), a genuine end-to-end HTTP trigger through the live stack,
  not just P7.9's in-process thread test.
- `env.schema.ts`'s production refinement (rejects `dev-insecure-*`
  placeholder JWT secrets when `NODE_ENV=production`) — re-confirmed
  present and unchanged; now has a direct Python-side sibling for
  `SERVICE_API_KEY` (§2).

---

## 5. Authorization — full 5-role matrix (new this phase)

Built directly from every `authorize(...)` call in every backend route
file (verified via grep, not inferred), cross-checked against P8.5's own
live discovery/fix of the Government audit-visibility gap:

| Route | ADMIN | GOVERNMENT | COLLECTOR | RECYCLER | CONSUMER |
|---|---|---|---|---|---|
| `POST /submissions` | – | – | – | – | ✅ |
| `GET /submissions` (list) | ✅ all | ✅ all (P8.5 fix) | own only | own only | own only |
| `GET /submissions/:id` | ✅ any | ✅ any (P8.5 fix) | own only | own only | own only |
| `PATCH /submissions/:id` | ✅ any, any status | – | owner, PENDING only | owner, PENDING only | owner, PENDING only |
| `DELETE /submissions/:id` | ✅ any, any status | – | owner, PENDING only | owner, PENDING only | owner, PENDING only |
| `PATCH /submissions/:id/assign` | ✅ override | ✅ strict path only | – | – | – |
| `PATCH /submissions/:id/accept\|start\|complete` | – | – | ✅ assigned collector only | – | – |
| `GET /collector/submissions` | – | – | ✅ own queue | – | – |
| `PATCH /submissions/:id/assign-recycler` | ✅ override | ✅ strict path only | – | – | – |
| `PATCH /submissions/:id/recycle/start\|complete` | – | – | – | ✅ assigned recycler only | – |
| `GET /recycler/submissions` | – | – | – | ✅ own queue | – |
| `POST /rewards/issue/:id` | ✅ | – | – | – | – |
| `GET /rewards/history\|balance` | own | own | own | own | own |
| `GET /users?role=` | ✅ | ✅ | – | – | – |
| `GET /health`, `/api-info`, `/metrics`, `/system/blockchain/health` | public (no auth) | | | | |

Every gate above is enforced twice: at the route (`authorize()`,
fail-closed — 401 with no principal, 403 for a disallowed role, confirmed
by reading `authorize.middleware.ts` directly) and again at the service
layer (ownership/status checks), matching the "defence in depth" pattern
already established. **No route was found reachable by a role not listed
here** — every route file was read in full, not sampled.

---

## 6. API security

| Control | Status | Evidence |
|---|---|---|
| SQL/command/path-traversal injection | **PASS**, re-confirmed by grep (0 raw SQL, 0 shell exec, filenames never used as paths) — unchanged since P7.4 | |
| Oversized payloads | **PASS** — `express.json({ limit: '1mb' })` (`app.ts`); image upload limits (`ImageValidator`, P5) unchanged | |
| Rate limiting | **PASS** — `apiRateLimiter` (300/min/IP global), `authRateLimiter` (10/window on `/auth/*`), Python `/predict` limiter (30/60s/IP) — all P7.4, re-confirmed present; `authRateLimiter` additionally live-triggered this session (§4) | |
| CORS | **PASS** — allowlist-based (`config.corsOrigins`), no wildcard, non-browser callers (no Origin header) unaffected, `credentials: true` safe because no cookie-based auth exists anywhere (grep re-confirmed: 0 `res.cookie`/`req.cookies` hits) | `cors.middleware.ts` |
| Security headers | **PASS** — Helmet applied first in the pipeline (`app.disable('x-powered-by')` + `securityHeaders()`), CSP deliberately off (documented: pure JSON API, would break future `/docs`) with all other Helmet defaults (HSTS, X-Content-Type-Options, X-Frame-Options, Referrer-Policy) on | `security-headers.middleware.ts` |
| Error-response leakage | **PASS** — `errorHandler` returns generic messages for unmapped/Prisma errors, logs the real exception server-side only, never a stack trace to the client | `error-handler.middleware.ts` |
| Correlation IDs | **PASS** — `requestId()` honors an incoming `X-Request-ID` (length-capped at 128 to prevent abuse) or generates a UUID, echoes it on the response, and it's threaded through every log line | `request-id.middleware.ts` |
| Service-to-service auth (device_ai) | **FIXED this phase** | §2 |

---

## 7. Database

Prisma parameterized queries exclusively (re-confirmed: the one
`$queryRaw` call is a hardcoded `SELECT 1` health probe, no
interpolation). Credentials sourced from environment variables only, no
hardcoded defaults reach a real deployment (`env.schema.ts`'s production
refinement). Postgres runs as the non-root `postgres` user for every
actual query-serving process (§9 — verified live, not assumed from the
base image's reputation).

**Informational finding, not fixed**: `docker-compose.yml` maps Postgres'
port directly to the host (`"${POSTGRES_PORT:-5432}:5432"`). Acceptable
for this file's documented scope (a "local/demo full-stack compose," per
its own header comment) — a genuine production deployment should omit
this mapping and rely on the Compose-internal network only, since direct
DB reachability from outside the app tier is an avoidable exposure. Not
changed here: doing so would break the local `psql`-for-debugging
ergonomics this demo file is explicitly for, and the fix is a deployment
topology decision (a production compose overlay), not an application
defect — recorded as a Suggested Improvement.

---

## 8. Blockchain (re-verified, extended)

P7.4's full blockchain threat-model table (keys/wallets never logged,
`.gitignore` excludes crypto material, no insecure TLS fallback, real
ECDSA-signed transactions, per-tx nonce replay protection, per-transition
chaincode `requireRole()` gates) re-read against current source — no
drift, all still accurate. **New evidence this session** extends rather
than repeats it:
- P8.2 added live chaincode tests for duplicate- and conflicting-anchor
  re-anchoring (idempotency, full audit trail) — cited, not re-derived.
- P8.5 §8 live-triggered a genuine local-trust-mismatch condition and
  confirmed the system **refuses** to create an external anchor from an
  already-mismatched local passport (`PASSPORT_NOT_ANCHORABLE`) — a direct,
  live proof of the "never anchor externally from an unverified local
  passport" architectural invariant under a real failure condition, not a
  hypothetical.
- This phase's §2 fix closes the one blockchain-adjacent gap P7.4 hadn't
  covered: the AI service that actually creates local/external trust
  anchors had no caller-authentication of its own.

---

## 9. Mobile

| Check | Status |
|---|---|
| Secure token storage | **PASS** — `flutter_secure_storage` (platform keychain/keystore), unchanged |
| Debug logging of secrets | **PASS** — grepped both apps for `print`/`debugPrint` of token/password patterns: 0 hits |
| Hardcoded secrets | **PASS** — grepped for API-key/secret/password literal patterns: 0 hits |
| Insecure HTTP by default | **FIXED this phase** | §3 |
| Role enforcement at login | **PASS** — both apps reject a login for the wrong role client-side before persisting any token (collector app since P6.3; consumer app fixed in P8.4) |

---

## 10. Containers (verified live, not assumed)

| Container | Base image | Runs as | Verified how |
|---|---|---|---|
| `ecotrace-backend` | `node:20-alpine` | `node` (non-root) | `docker exec ecotrace-backend whoami` → `node` |
| `ecotrace-device-ai` | `python:3.12-slim` | `appuser` (dedicated non-root) | `docker exec ... whoami` → `appuser` |
| `ecotrace-frontend` | `nginx:1.27-alpine` | worker processes: `nginx` (non-root); master (PID 1): `root` | `docker exec ... ps aux` — this is nginx's own standard, documented design (master needs root only to bind port 80 and manage workers; every actual request is served by an unprivileged worker) |
| `ecotrace-postgres` | `postgres:16` | server + every connection-handling backend process: `postgres` (non-root); only a *fresh exec shell* defaults to root, irrelevant to the serving process | `docker exec ... ps aux` |

No secrets baked into any image layer (all 3 Dockerfiles read fully: zero
`ENV`/`ARG` lines with credential-shaped values; secrets flow in only via
`docker-compose.yml`'s `environment:` at container start). All 3 services
carry a `HEALTHCHECK`. Exposed ports match their documented purpose;
Postgres' host exposure is the one informational note (§7).

---

## 11. Dependencies (fresh scan, this phase)

| Component | Tool | Result |
|---|---|---|
| `backend/` (production deps) | `npm audit --omit=dev` | 3 high, all `deepmerge-ts` under `@prisma/config` (CLI/codegen tooling only, never imported by the running service) — same accepted residual risk as P7.4 §3.1, re-confirmed no safe fix available (`npm audit fix --dry-run` shows no resolution) |
| `frontend/` | `npm audit` | **0 vulnerabilities** |
| `blockchain/chaincode/` | `npm audit` | **0 vulnerabilities** |
| `intelligence/device_ai` | `pip-audit --local` | **0 vulnerabilities** |
| `mobile/collector_app`, `mobile/consumer_app` | `flutter pub outdated` | All direct dependencies at latest; only dev-tooling transitives (analyzer/test framework) trail slightly, no known CVEs (Dart's tooling has no CVE-scanning equivalent to `npm audit`/`pip-audit` — same disclosed limitation as P7.4) |

No regression, no new vulnerability introduced by this phase's own new
code (`service_api_key`/`secure_url_guard` add no new third-party
dependency).

---

## 12. Regression suite (fresh, this phase)

| Suite | Result |
|---|---|
| `intelligence/device_ai` (Python) | **1121/1121** (1110 baseline + 11 new: 8 service-auth + 3 production-config). The previously-documented flaky `test_benchmark_measures_latency_and_throughput` did not fail this particular run — it remains inherently timing-dependent/non-deterministic (unchanged, not "fixed," since nothing in this phase touched it) |
| Backend (Node/Jest) | **341/341**, unchanged (no backend source touched this phase) |
| Backend lint/typecheck | 0/0 errors |
| Chaincode (TypeScript/Jest) | **47/47**, unchanged |
| Collector app (Flutter) | **26/26** (22 baseline + 4 new, §3), 0 analyze issues |
| Consumer app (Flutter) | **22/22** (18 baseline + 4 new, §3), 0 analyze issues |
| Frontend | typecheck 0, lint 0, unchanged (no frontend source touched) |

**Total: 1121 + 341 + 47 + 26 + 22 = 1557 passing.**

---

## 13. Test accounting

| | Count |
|---|---|
| Previous (P8.6 baseline) | 1537 |
| Added this phase | 20 (11 Python `service_auth`/production-config + 4 collector `secure_url_guard` + 4 consumer `secure_url_guard`, note: P8.6's total already included the +2 from P8.5) |
| Removed | 0 |
| Final | 1557 passing |

---

## 14. Protected asset verification

Re-hashed all 6 protected ML assets before and after this phase's changes
— **6/6 MATCH**. This phase touched no ML asset, only application
source/config/tests.

---

## 15. Git state

Diff scoped to: `intelligence/device_ai/{configs/settings.py,
application.py, api/service_auth.py (new), .env.example, tests/
test_p72_production_config_validation.py, tests/test_p87_service_auth.py
(new)}`, `docker-compose.yml` (one new env line), `mobile/collector_app/
{lib/core/config/secure_url_guard.dart (new), lib/main.dart, test/unit/
secure_url_guard_test.dart (new)}`, `mobile/consumer_app/` (same 3 files),
plus this phase's reports. No backend/frontend/chaincode source touched.
No ML asset touched. Verified via `git status`/`git diff --stat` before
commit.

---

## 16. Environmental limitations

- Live Hyperledger Fabric MSP/endorsement-policy enforcement still cannot
  be verified against a real peer (unchanged since P6.2/P8.2) — the
  chaincode-level authorization gates and the fake-Gateway-server protocol
  conformance tests remain the strongest available evidence.
- `npm audit`'s one accepted residual finding (`deepmerge-ts` in
  `@prisma/config`) has no safe fix without a Prisma major-version bump —
  unchanged from P7.4, re-confirmed still the case.
- Dart/Flutter tooling has no CVE-scanning equivalent to `npm audit`/
  `pip-audit` — `flutter pub outdated` is the strongest available signal,
  unchanged limitation since P7.4.

---

## 17. Definition of Done

- [x] Authentication, authorization (full 5-role matrix, new), API
      security, database, blockchain, mobile, containers, and dependencies
      all reviewed against current source (§4–§11), not assumed from prior
      phases' descriptions.
- [x] Two real gaps found and fixed, both with regression tests and (for
      the CRITICAL/HIGH one) live verification against the running
      containers, not just in-process tests (§2–§3).
- [x] Findings classified by severity; the one accepted residual
      dependency risk and the one informational container/port note are
      explicitly disclosed with reasoning, not silently dropped (§7, §11).
- [x] Fresh dependency vulnerability scan across every component with
      available tooling (§11).
- [x] Full regression suite re-run fresh, real counts, zero fabrication
      (§12–§13).
- [x] Protected assets verified 6/6 MATCH (§14).
- [x] No unrelated refactoring; both fixes are narrowly scoped, additive,
      and backward-compatible by construction (§2's default-open key,
      §3's release-mode-only guard).

## 18. Final status: **PASS**
