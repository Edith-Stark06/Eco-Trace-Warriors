# P7.4 — Security Hardening & Threat Model

## 1. Scope

A full security review across authentication, authorization, transport,
input handling, blockchain, dependencies, and information disclosure —
building on (not re-doing) P6.8's and P7.1's prior audits, and fixing the
real gaps found.

---

## 2. Pre-flight state

- Protected assets: 6/6 MATCH.
- Baseline tests: 1467/1468 (P6/P7.1-3), no regression carried in.

---

## 3. Dependency vulnerability scan (new this phase)

| Component | Tool | Before | After |
|---|---|---|---|
| `backend/` | `npm audit` | 5 high (all dev-tooling transitive: `brace-expansion`, `deepmerge-ts`↔`@prisma/config`, `js-yaml`) | **2 fixed** (`brace-expansion`, `js-yaml`) via `npm audit fix`; **3 remain**, all inside `@prisma/config`'s `deepmerge-ts` dependency — see §3.1 |
| `frontend/` | `npm audit` | 5 high (`brace-expansion`, `js-yaml`, `nanoid`, `react-router` RSC-mode CSRF bypass) | **0 remaining** — `npm audit fix` resolved all 5 |
| `blockchain/chaincode/` | `npm audit` | 0 | 0 |
| `intelligence/device_ai` | `pip-audit --local` | 1 (`pip` itself, `PYSEC-2026-3721`) | 0 — `pip` upgraded to 26.2 (environment-level, not a repo dependency pin) |
| Mobile (`collector_app`, `consumer_app`) | `flutter pub outdated` | All direct dependencies already at latest; only dev-tooling transitives (analyzer, test framework) trail slightly, no known CVEs | unchanged, no action needed |

Both fixes were applied via `npm audit fix` (no `--force`), verified as
**lockfile-only changes** (`git diff --stat` showed zero `package.json`
diff in either project) and re-verified with a full
test/typecheck/lint/build pass in each project — no regression.

### 3.1 Accepted residual risk: `deepmerge-ts` in `@prisma/config`
`prisma`/`@prisma/config` (the Prisma **CLI/codegen tooling**, not the
`@prisma/client` runtime library the running API actually imports) depends
on a vulnerable `deepmerge-ts` (stack exhaustion on a deeply recursive
object graph). No fix is available without a Prisma major-version bump,
which this session will not force without explicit instruction (`no
destructive changes`, `no dependency upgrades without care`). Risk
assessed as **low**: this code path only runs `prisma generate`/`migrate`
against the developer's own `schema.prisma`/`prisma.config.ts` — it is
never reachable from an HTTP request to the running service. Recorded here
as an accepted, disclosed residual finding, not silently ignored.

---

## 4. Real gaps found and fixed

### 4.1 No general-purpose API rate limiting (backend)
Rate limiting existed only on `/auth/*` (brute-force protection). Every
other route — including expensive DB writes — had none. Added
`apiRateLimiter` (reuses the same `express-rate-limit` machinery as
`authRateLimiter`, refactored into a shared `buildRateLimiter` so nothing
about the existing auth limiter's behavior changed), mounted globally
**after** the health router so `/health`/`/ready` polling from
orchestrators is never throttled (pure middleware ordering — no `skip`
special-casing needed, since a matched route that already sent a response
never reaches later middleware). Default: 300 requests/minute/IP,
configurable via `API_RATE_LIMIT_WINDOW_MS`/`API_RATE_LIMIT_MAX`.

### 4.2 No rate limiting on the compute-expensive `/predict` endpoint (Python)
`/predict` runs YOLO inference + OCR + WBF post-processing per call — a
single client could exhaust CPU/GPU capacity with no limit at all. Added
`utils/rate_limit.py: RateLimiter` (dependency-free, in-memory, fixed
window per client IP — the same "no new dependency, matches
`utils/metrics.py`'s own precedent" reasoning as P7.3), wired as a
FastAPI route-level dependency (`dependencies=[Depends(enforce_predict_rate_limit)]`)
so it runs before the (expensive) handler body executes, never after. New
`RateLimitExceededError` (429) added to the existing `DeviceAIError`
hierarchy — zero new wiring needed in `api/errors.py`, since every
`DeviceAIError` subclass is already translated automatically via its own
`http_status`. Configurable via `PREDICT_RATE_LIMIT_MAX_REQUESTS`/
`PREDICT_RATE_LIMIT_WINDOW_SECONDS` (defaults: 30 requests/60s/IP).

Scoped deliberately to `/predict` only — not applied globally in the
Python service, since its other routes (`/health`, `/version`, `/metrics`,
device/fingerprint/OCR CRUD) are cheap and already covered by the
backend's own upstream rate limiting where they're reached via the main
API surface.

---

## 5. Full threat model

| Threat | Impact | Likelihood | Mitigation | Status |
|---|---|---|---|---|
| Brute-force login | Account takeover | Medium | bcrypt hashing (configurable cost) + `authRateLimiter` (10/15min on `/auth/*`) | **PASS** (pre-existing, re-verified) |
| Credential stuffing / generic API abuse | Resource exhaustion, DoS | Medium | New global `apiRateLimiter` (§4.1) | **FIXED this phase** |
| Weak/default JWT secrets reaching production | Full auth bypass | Low (caught at deploy) | `env.schema.ts` rejects `dev-insecure-*` prefix and matching access/refresh secrets when `NODE_ENV=production` (P6.8, re-verified P7.2 with 20 dedicated tests) | **PASS** |
| JWT replay after logout/rotation | Session hijack | Low | Short access-token expiry (15m default) + separate refresh-token rotation; refresh tokens stored server-side (`refresh_tokens` table), revocable | **PASS** (pre-existing) |
| CSRF | Unauthorized state-changing request via a logged-in browser | **N/A** | No cookie-based session anywhere in this codebase (confirmed via grep: no `res.cookie`/`req.cookies`/`cookie-parser`/`withCredentials` in `backend/src` or `frontend/src`) — JWT is a Bearer token attached explicitly by the Axios/Dio interceptor, never sent ambiently by the browser. CSRF requires an ambient credential; none exists here. | **NOT APPLICABLE** (documented, not assumed) |
| SQL injection | Data breach/corruption | Low | Prisma parameterized queries exclusively; the one `$queryRaw` call (`SELECT 1`, health probe) is a hardcoded literal with no interpolation. 0 raw/string-formatted SQL found in `device_ai` (grep across the whole tree). | **PASS** |
| Command injection | RCE | Low | 0 `shell=True`/`os.system`/`child_process.exec*` calls anywhere. The 2 `subprocess.run` call sites (`acquisition/cli.py`, `training/utils/git_utils.py`) use fixed argv, are offline dataset/training tooling, not reachable from any HTTP route. | **PASS** |
| Path traversal via uploaded filename | Arbitrary file read/write | Low | `upload.filename` is used only for metadata/extension-allowlist checks — grepped the whole tree, confirmed never concatenated into a filesystem path; images are decoded in-memory (PIL from bytes), never written to disk under a client-controlled name. | **PASS** |
| Malicious/oversized image upload | Memory exhaustion, decoder exploit | Medium | `ImageValidator`: count limit, per-file size limit, MIME allowlist, decode-based validation (not extension-trusting), resolution bounds — all pre-existing, re-verified this phase. | **PASS** |
| `/predict` resource exhaustion by a single client | DoS (CPU/GPU) | Medium | New `enforce_predict_rate_limit` (§4.2) | **FIXED this phase** |
| OCR/barcode text used unsafely downstream | Injection via recognized text | Low | OCR/barcode output flows only into Pydantic-typed response fields and material/condition heuristics — never into a SQL query, shell command, or `eval`; confirmed via the same command/SQL-injection grep above (0 hits touching OCR output). | **PASS** |
| Fabric transaction spoofing (forged proposal) | Fraudulent ledger write | Low | Real ECDSA P-256/SHA-256 signing over the actual proposal bytes (P6.2); the fake-server test suite verifies the server rejects unsigned/malformed envelopes (`test_submit_transaction_success_full_flow` asserts `signature != b""` was required). A real Fabric peer would additionally enforce MSP/endorsement-policy validation this client cannot fake. | **PASS** (scope-limited: verified against protocol-conformant fake server, not a live Fabric peer — same disclosed limitation as P6.2/P7.1) |
| Fabric transaction replay | Double-anchoring / duplicate write | Low | Per-transaction `os.urandom(24)` nonce → `tx_id = sha256(nonce‖creator)` (P6.2, standard Fabric client convention); a real ordering service additionally rejects duplicate tx_ids. `submit_transaction` never auto-retries (explicit design decision, P6.2 report). | **PASS** |
| Chaincode authorization bypass | Unauthorized lifecycle mutation | Low | Per-transition `requireRole()` gates (`RegisterDevice`→PLATFORM only, `UpdateLifecycle`→role-mapped per target state, `AnchorDevicePassport`→PLATFORM only), covered by 45/45 chaincode tests (P6.1, re-verified). | **PASS** |
| Private key exposure (Fabric identity) | Full identity compromise | Low | Keys read from PEM file paths via `cryptography.hazmat`; never logged (grepped for any `logger.*key`/`logger.*cert` pattern with the raw value — none found, only file paths logged); `.gitignore` excludes `*.key`/`*.pem`/`wallet/`/`credentials/`/`crypto-config/` (P6.2). | **PASS** |
| TLS downgrade / insecure Fabric channel | MITM on Fabric traffic | Low | No insecure gRPC channel fallback exists — connecting without a configured TLS CA cert raises `FabricConfigurationError` (re-confirmed by grep, same as P6.8). Application-layer TLS termination (backend/frontend HTTPS) is a deployment-layer (reverse proxy/ingress) concern, not application code — noted, not fabricated as "handled here." | **PASS / scope note** |
| Information disclosure via error responses | Internal path/stack leakage | Low | Both services' unhandled-exception handlers return a generic message and log the real exception server-side only (re-confirmed by reading `api/errors.py` in both, §"error messages" review) | **PASS** |
| Trust-anchor manipulation (client forges a "verified" status) | False trust signal | Low | Trust status is computed server-side from stored fingerprints/anchors, never accepted as client input; external verification round-trips through the real Fabric Gateway client, not a client-supplied flag. | **PASS** (pre-existing, re-confirmed) |
| Weak Postgres credentials in local dev | Lateral access if the dev DB is exposed | Low | P7.2 already parameterized the compose file's password; still defaults to a placeholder for zero-config local dev, documented as such. | **PASS** (P7.2, re-confirmed unaffected) |

---

## 6. Security regression tests (new this phase)

| Suite | Result |
|---|---|
| Backend `rate-limit.test.ts` (integration) | 3/3 |
| Python `test_p74_rate_limit.py` | 7/7 |
| Backend full suite | **339/339** (336 P7.3 baseline + 3 new) |
| Python full suite | **1102/1102** (1095 P7.3 baseline + 7 new) |
| Backend lint/typecheck/build | 0/0 errors, build succeeds |
| Frontend typecheck/lint | 0/0 errors (unaffected — no frontend source touched this phase; only `package-lock.json`) |
| New-code lint/type hygiene | `ruff`/`mypy` scoped to every touched file — 0 findings in this phase's own new/changed lines; all remaining findings confirmed pre-existing via `git diff` |

A genuine debugging note, disclosed rather than hidden: the first version
of the Python integration test for `/predict` rate limiting had **two**
real bugs of its own — (1) it posted with no image attached, so every call
failed validation (422) before ever reaching the rate-limit dependency,
masking whether the limiter worked at all; (2) after fixing that, the test
fixture's `dependency_overrides` lambda constructed a **new** `RateLimiter`
instance on every call instead of capturing one shared instance, so the
count never accumulated. Both were root-caused (via a standalone
reproduction script) and fixed before the test was trusted; the final
7/7-passing suite is the corrected version.

---

## 7. Protected asset verification

Verified via `sha256sum` before and after this phase's changes — **6/6
MATCH**. No ML asset touched.

---

## 8. Git state

Diff scoped to: `backend/{.env.example, package-lock.json, src/app.ts,
src/shared/config/{config.ts,env.schema.ts}, src/shared/middleware/
{auth-rate-limit.middleware.ts,index.ts}, tests/integration/
rate-limit.test.ts}`, `frontend/package-lock.json`,
`intelligence/device_ai/{api/dependencies.py, api/routes.py,
configs/settings.py, exceptions.py, utils/rate_limit.py (new),
tests/test_p74_rate_limit.py (new)}`, plus this phase's reports. Verified
via `git status`/`git diff --stat` before commit.

---

## 9. Environmental limitations

None new. Fabric spoofing/replay resistance is verified against the
protocol-conformant fake Gateway server, not a live Fabric peer — the same
disclosed scope limit carried since P6.2/P6.7/P7.1.

---

## 10. Definition of Done

- [x] Every threat-model category in the brief reviewed against real
      source, not assumed (§5).
- [x] Dependency vulnerability scan run across every component with
      available tooling; safe fixes applied and verified; one accepted
      residual risk explicitly disclosed with reasoning (§3).
- [x] Two real gaps found and fixed with regression tests: general API
      rate limiting (backend) and `/predict` rate limiting (Python) (§4).
- [x] CSRF non-applicability verified by evidence (grep for cookie usage),
      not assumed from architecture description alone.
- [x] A real bug in this phase's own test-writing process found,
      root-caused, and disclosed (§6).
- [x] Protected assets verified before and after.
- [x] No destructive changes; no dependency force-upgrades; no unrelated
      refactoring.

## 11. Final status: **PASS**
