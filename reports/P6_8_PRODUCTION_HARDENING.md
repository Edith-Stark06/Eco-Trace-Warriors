# P6.8 — Production Hardening

## 1. Objective

Audit the whole P6-era system for real security/production issues and fix
what's genuinely fixable here — not invent controls the system doesn't need,
and not paper over gaps the environment prevents closing.

---

## 2. Secret scanning

- `git ls-files` grep for `.env`, `.pem`, `.key`, `.p12`, `.pfx`, `credentials`,
  `secret` (excluding `*.example`): **zero matches** — no secret-like file is
  tracked.
- `git grep` for hardcoded `api_key=`/`secret=`/`password=` literal-string
  assignments across `.py/.ts/.tsx/.js/.dart`, filtered for
  example/test/mock/env-var usage: **zero matches**.
- Root `.gitignore` covers `.env`, `.env.*` (with `!.env.example` allowed),
  `*.key`, `*.pem`, `*.p12`, `*.pfx`, `wallet/`, `credentials/`,
  `crypto-config/` (the last four added in P6.2 for Fabric identity material).
- **Verdict: PASS.**

---

## 3. Protected ML assets

Verified via `sha256sum` against the 6 hashes carried since P6.1:

| Asset | Status |
|---|---|
| `p4_4_2.../p442_yolo11n/weights/best.pt` | MATCH |
| `p4_11.../p411_yolo11n_targeted_aug/weights/best.pt` | MATCH |
| `p4_12.../p412_yolo11s/weights/best.pt` | MATCH |
| `p4_14.../p414_yolo11n_targeted_aug/weights/best.pt` | MATCH |
| `p4_5_real_world_v1/p45_data.yaml` | MATCH |
| `p4_7_wikimedia_ood_v1/p47_final_data.yaml` | MATCH |

None of these are git-tracked (`*.pt`/`runs/`/`dataset_acquisition/training/`
etc. are gitignored) — they're verified by hash against the working copy,
not against a commit. **All 6/6 match.**

---

## 4. Fabric Gateway client security review (P6.2)

- **No insecure gRPC fallback**: `fabric_gateway_client.py` has no
  `InsecureChannelCredentials` path — connecting without TLS root certs
  raises `FabricConfigurationError` ("required to connect to a Fabric peer
  (no insecure fallback)"), confirmed by grep, not assumed.
- **TLS hostname verification**: `grpc.ssl_target_name_override` is set from
  the configured peer host, not disabled.
- **Identity key handling**: loaded via
  `cryptography.hazmat.primitives.serialization.load_pem_private_key`,
  type-checked as `ec.EllipticCurvePrivateKey`, signs with
  `ECDSA(SHA256())` — matches Fabric's own MSP identity convention (verified
  against vendored protos in P6.2, low-S normalization applied).
- **No plaintext key persistence introduced by this service**: the client
  reads key material from paths supplied via `Settings`/env vars; it does not
  write, log, or cache private key bytes anywhere.
- **Verdict: PASS**, within the limits already disclosed in P6.2 (no live
  peer to test the TLS handshake against in this environment).

---

## 5. Backend hardening (`backend/`)

| Control | Status | Evidence |
|---|---|---|
| Security headers | **On** | `helmet()` in `security-headers.middleware.ts`; CSP intentionally left off with a documented reason (pure JSON API + Swagger docs route), all other Helmet defaults (HSTS, X-Content-Type-Options, X-Frame-Options, Referrer-Policy) stay on |
| CORS | **Explicit allow-list** | `CORS_ORIGINS` env var, default `http://localhost:5173` only — no wildcard |
| Password hashing | **bcrypt**, configurable cost (`BCRYPT_ROUNDS`) | `password.service.ts` |
| JWT | Separate access/refresh secrets, min 32 chars, prod-strength enforced (`env.schema.ts` rejects a `dev-` prefixed secret and rejects `JWT_REFRESH_SECRET === JWT_SECRET` outside dev) | `env.schema.ts` `superRefine` |
| Auth rate limiting | **On**, `express-rate-limit` mounted on `/auth` only | `auth-rate-limit.middleware.ts` |
| Request validation | **Zod schemas** on every mutating route (established pre-P6, unchanged) | existing `*.schema.ts` files per module |
| SQL injection | **N/A by construction** — Prisma parameterized queries only, no raw SQL found in any P6 module (`grep $queryRaw` → 0 hits in `blockchain`/new P6.5 code) | |
| Request correlation | **On** — `requestId()` middleware sets `req.id`, propagated into every log line via `request-logger.middleware.ts` and the error handler | `app.ts:96` |
| Error responses | Never leak stack traces to the client — error handler logs `err` server-side only, response body uses the existing `ErrorResponse` envelope | `error-handler.middleware.ts` |
| New P6.5 blockchain route specifically | Stateless proxy, no auth required (matches `/health`'s own public status), never throws past its own boundary (`getHealth()` catches everything internally, § P6.5 report) | `blockchain.service.ts` |

No new hardening changes were required in `backend/` — all of the above
predates or was built correctly during P6.5/P6.6. Nothing was found that
needed fixing.

---

## 6. Frontend hardening (`frontend/`)

- No `dangerouslySetInnerHTML` anywhere in `src/` — zero matches.
- API base URL comes from `env.apiBaseUrl` (Vite env var), not hardcoded.
- Blockchain health card (P6.6) renders only backend-controlled enum-like
  status strings and numeric latency — no raw user/network content is ever
  interpolated into HTML.
- Axios instance is shared and centrally configured (no ad-hoc `fetch`
  calls bypassing the token-refresh interceptor were introduced in P6.6).
- **Verdict: PASS.** No test suite exists in this project to add a security
  regression test to (already disclosed in P6.6); nothing else to change.

---

## 7. Mobile hardening (`mobile/collector_app`, `mobile/consumer_app`)

- **Token storage**: `flutter_secure_storage` used for tokens/identifiers in
  both apps (Keychain/EncryptedSharedPreferences-backed), not `SharedPreferences`
  or plain files.
- **No hardcoded secrets**: `app_config.dart` in both apps only contains a
  base URL and timeouts, sourced from compile-time defaults meant for local
  dev (`10.0.2.2` — the Android emulator's host-loopback address), not a
  production credential.
- **Native platform hardening (cleartext traffic, network security config,
  certificate pinning) could not be reviewed or set**: neither app has an
  `android/` or `ios/` platform directory in this repository. As documented
  in P6.3 §9, no APK/IPA build was attempted (no Android SDK, no Xcode) and
  platform scaffolding was never generated — there is no
  `AndroidManifest.xml` or `Info.plist` for this phase to harden. This is a
  **disclosed, unresolved gap** carried from P6.3/P6.4, not new to P6.8.
- **Verdict: PARTIAL** — Dart-level storage and config hygiene verified;
  native platform hardening blocked by the same environment limitation
  already on record.

---

## 8. Database / migration chain

No live PostgreSQL instance exists in this environment (§ P6.7 §2), so a
real `upgrade → downgrade → upgrade` run against a database could not be
executed. What was verified statically instead:

- `alembic history` (schema-directory-only, no DB connection needed) shows
  a single linear chain, one head:
  `<base> → 001_initial_p54_device_schema → 002_add_p59_trust_anchors →
  003_add_p511_external_trust_anchors (head)` — no branch points, no
  divergent heads.
- Every one of the 3 revisions has both `upgrade()` and `downgrade()`
  functions with real bodies (not `pass` stubs) — checked via AST parsing,
  not by reading revision *names* and assuming.
- Prisma migration history (`backend/prisma/migrations/`) is similarly a
  single ordered folder chain (6 migrations, timestamp-ordered directory
  names, standard Prisma convention — no manual editing found).
- **Verdict: STRUCTURALLY SOUND, NOT LIVE-VERIFIED.** The chain is provably
  linear and every step is reversible in principle; whether each `downgrade()`
  actually round-trips cleanly on a real Postgres instance is untested here,
  same environmental limitation as the rest of P6.7/P6.8.

---

## 9. Observability

- Structured logging (`pino`, `createLogger`) used throughout `backend/`,
  correlated by `req.id` from the request-id middleware.
- `GET /health` (pre-existing) and `GET /system/blockchain/health` (P6.5)
  both give a real, honest liveness signal without requiring auth.
- Python `intelligence/device_ai` uses its own existing structured logging
  (unchanged by P6) plus the new `fabric_gateway_client.py`'s `health_check()`
  (a dedicated connection-level probe, distinct from a transaction — see
  P6.2 §6, not modified here).
- **No metrics/tracing backend (Prometheus, OpenTelemetry) exists in either
  service.** This was true before P6 and remains true — out of scope to add
  as a "hardening" side effect without being asked to build an observability
  stack.

---

## 10. Performance notes (informational only — no code changed)

- The blockchain health proxy (P6.5) has no caching; every dashboard poll
  (30s interval, P6.6) triggers a fresh upstream call to the Python service.
  At current scale this is negligible; if the health card's poll interval
  were tightened significantly, a short-TTL cache in `blockchain.service.ts`
  would be the natural next step — **not built now**, since nothing in this
  session's scope calls for it and speculative caching without a measured
  need would violate this repo's own "avoid premature optimization" rule.
- No N+1 query patterns were introduced by any P6 module — the blockchain
  route touches no database at all.

---

## 11. Documentation

- This report and `reports/P6_7_END_TO_END_VALIDATION.md` are themselves the
  required documentation updates for this phase's API/architecture surface
  (`GET /system/blockchain/health` on both services, already documented in
  P6.2/P6.5's own reports).
- No README/architecture-doc changes were required beyond what P6.1–P6.7
  already added, verified by re-reading `AdminDashboardPage.tsx`'s own
  top-of-file doc comment (§ P6.6, still accurate) and the P6.2/P6.5 reports'
  endpoint documentation — nothing found to be stale.

---

## 12. Definition of Done

- [x] Secret scan across tracked files and source patterns — 0 findings.
- [x] Protected asset hashes re-verified — 6/6 match.
- [x] Fabric Gateway client security review — no insecure fallback, correct
      TLS/identity handling confirmed by reading the actual code.
- [x] Backend, frontend, mobile hardening reviewed; all findings either
      already-satisfied controls or previously-disclosed environmental gaps
      — nothing new swept under the rug.
- [x] Migration chain integrity statically verified (linear, real
      downgrades); live DB round-trip honestly reported as not executable
      here.
- [x] Observability and performance reviewed and reported informationally;
      no speculative work added.
- [x] No unrelated refactoring performed — this phase produced zero source
      code changes, only these reports (verified: `git diff --stat` for this
      phase touches only `reports/`).
