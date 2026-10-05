# P7.3 — Observability, Logging & Health Monitoring

## 1. Scope

Add production-grade observability where it was genuinely missing, and
verify what already existed rather than re-inventing it.

---

## 2. Pre-flight state

- Protected assets: 6/6 MATCH.
- Baseline tests: 1467/1468 (P7.1/P7.2), matching the user-supplied P6
  baseline exactly.

---

## 3. What already existed (audited, not rebuilt)

- **Backend**: structured Pino logging, request-correlation IDs
  (`X-Request-ID`), `GET /health` (liveness), `GET /ready` (readiness,
  pings Postgres), `GET /system/blockchain/health` (P6.5 proxy) — all
  already production-grade, confirmed in P6.8/P7.1's audits.
- **Python `intelligence/device_ai`**: structured Loguru logging with
  request-id context binding and per-request latency logging
  (`api/middleware.py`), `GET /` (liveness), `GET /health` (readiness with
  per-component status), `GET /system/blockchain/health` (P6.2).
- **Frontend**: `ServerError`/`SkeletonCards`/`AdminUnavailable` component
  kit already gives every dashboard section a real loading/error/
  unavailable state (P6.6), including the `BlockchainHealthCard` — this
  phase's own health-state requirement was already satisfied.
- **Mobile**: `mapDioExceptionToFailure` (both apps) already translates
  every network failure into a user-facing message before this phase.

No suggested exact paths (`/health/live`, `/health/ready`,
`/health/blockchain`) were added as aliases alongside the existing
`/health`+`/ready`(+`/system/blockchain/health`) trio: the brief frames
them as illustrative ("such as"), the existing trio already delivers
liveness + readiness + dependency health, and per this session's standing
"do not replace working architecture" / "no duplicate logic" rules, adding
parallel routes for the same capability would be exactly the kind of
unrequested churn to avoid. This is a deliberate choice, recorded here
rather than silently deviating from the brief's literal wording.

---

## 4. Real gaps found and fixed

### 4.1 No request/blockchain metrics anywhere (backend)
Added `backend/src/shared/metrics/` (`MetricsRegistry` + `metricsMiddleware`)
and `backend/src/modules/metrics/` (`GET /api/v1/metrics`, public,
read-only). Records per-route request count/avg latency/status-code
breakdown, plus blockchain health-check outcomes (`connected` /
`unavailable`-family / `proxy_unreachable`) via a new optional `onCheck`
hook on `BlockchainService`. **Deliberately not Prometheus**: no scrape
target exists anywhere in this environment, so `prom-client` would be an
unused dependency — a small JSON summary answers the same "how many
requests, how fast, how many blockchain checks failed" questions this
phase's brief actually asks.

### 4.2 No database health check in the Python service's `/health`
`intelligence/device_ai`'s `/health` reported pipeline/model-registry
status but never checked the database — a real gap versus the backend's
own `/ready`. Added `database/database.py: ping_engine()` (a bounded
`SELECT 1` round-trip, never raises) and wired it into `/health` as a new
`database` component — but **only when a component is actually configured
to use Postgres** (`device_backend`/`trust_anchor_backend == "postgres"`),
mirroring the same "Postgres is only a real dependency when configured"
rule the P7.2 production-safety validator already established. An
in-memory-backend deployment's `/health` is therefore unaffected — verified
by the existing `test_meta.py::test_health`, unchanged and still green.

### 4.3 No request/Fabric-transaction metrics in the Python service
Added `utils/metrics.py` (`MetricsRegistry`, mirrors the backend's design
exactly), wired into the existing `RequestContextMiddleware` (which already
computed `latency_ms`/`status`/`method`/`path` per request — the metrics
call reuses those values, nothing recomputed), and exposed at `GET
/metrics`. Fabric transaction success/failure counters are recorded at
`FabricGatewayClient.submitTransaction`/`evaluateTransaction` — the actual
call surface `FabricExternalTrustLedger` uses — specifically **not** inside
the internal `submit_transaction`/`evaluate_transaction` implementations,
to avoid touching P6.2's already-tested Endorse/sign/Submit/CommitStatus
logic at all.

### 4.4 No structured logging or connectivity diagnostics on mobile
Neither app had anything beyond scattered `debugPrint` calls. Added
`lib/core/diagnostics/app_logger.dart` to both apps (`AppLogger`:
debug/info/warn/error, `dart:developer`-backed so entries are filterable in
DevTools, gated by `kDebugMode` so release builds emit nothing — there is
no log-shipping backend to send them to). Wired into:
- `api_exception.dart` (both apps) — every mapped `DioException` now logs
  a structured warning with the failed method/path/status before
  translating to a user-facing `AppFailure`.
- `sync_manager.dart` (collector only — the consumer app has no offline
  queue by design, per P6.4) — logs queue-drain start, each item's
  success/retry/permanent-failure outcome.
- `sync_providers.dart` (collector only) — logs online/offline transitions.

---

## 5. Tests

| Area | Result |
|---|---|
| Backend new: `metrics.test.ts` (unit) | 7/7 |
| Backend new: `metrics.test.ts` (integration) | 3/3 |
| Backend updated: `blockchain.service.test.ts` (+1 for `onCheck`) | 7/7 |
| Backend full suite | **336/336** (326 P7.2 baseline + 10 new) |
| Backend lint/typecheck/build | 0/0 errors, build succeeds |
| Python new: `test_p73_observability.py` | 11/11 |
| Python updated: `test_p62_fabric_gateway.py` (+3 for tx metrics) | 46/46 |
| Python full suite | **1095/1095** (1081 P7.2 baseline + 14 new; the pre-existing benchmark-latency flake did not reproduce this run) |
| Collector Flutter analyze/test | 0 issues / **22/22** (18 baseline + 4 new `AppLogger` smoke tests) |
| Consumer Flutter analyze/test | 0 issues / **13/13** (9 baseline + 4 new) |
| Frontend typecheck/lint | 0/0 errors (unaffected — no frontend files touched) |

**Total automated tests passing: 336 + 1095 + 22 + 13 = 1466** in the
newly-touched components (frontend's untouched count folds in at the
system level — see the P7.1-style running total in the final audit).

A genuine flaky-test note, consistent with prior phases: the pre-existing
`test_benchmark_measures_latency_and_throughput` CPU-timer race (documented
since P6.2, reconfirmed failing in P7.1) did not reproduce in this phase's
runs — reported honestly as "did not reproduce," not claimed as fixed,
since nothing in this phase touched that code path.

New-code lint/type hygiene: `ruff check`/`mypy` were run scoped to every
file this phase touched. One genuine mypy error introduced by this phase's
own new code (`utils/metrics.py`'s heterogeneous-dict `sum()` typing) was
found and fixed. All other findings surfaced by a whole-file scan were
verified via `git diff` to be pre-existing lines this phase never touched,
and were left alone — consistent with P7.1's "don't mass-fix pre-existing
debt" policy.

---

## 6. Security considerations

- `GET /metrics` (both services) is public and read-only, exposing only
  aggregate counts/timings keyed by matched route template — never raw
  URLs, query strings, request/response bodies, or per-user data. Judged to
  carry no more sensitive information than the existing `/health` endpoints
  (same reasoning already applied there).
- `ping_engine()` never logs connection strings or credentials — only a
  boolean outcome and, on failure, the driver's own exception message via
  the existing `logger.warning`.
- `AppLogger` never activates in a release build (`kDebugMode` gate) — no
  new risk of logging tokens/PII in production, since there is no
  production log sink for mobile at all.

---

## 7. Protected asset verification

Verified via `sha256sum` before and after this phase's changes — **6/6
MATCH**. No ML asset touched.

---

## 8. Git state

Diff scoped exactly to: `backend/src/app.ts`,
`backend/src/modules/blockchain/blockchain.service.ts` (+test),
`backend/src/shared/metrics/` (new), `backend/src/modules/metrics/` (new),
`backend/tests/{unit,integration}/metrics.test.ts` (new),
`intelligence/device_ai/{api/middleware.py, api/routes.py, api/schemas.py,
database/database.py, devices/fabric_gateway_client.py, utils/metrics.py
(new)}`, `intelligence/device_ai/tests/{test_p73_observability.py (new),
test_p62_fabric_gateway.py}`, `mobile/{collector_app,consumer_app}/lib/core/
diagnostics/app_logger.dart` (new) + their `api_exception.dart` and (collector
only) `sync_manager.dart`/`sync_providers.dart`, plus this phase's reports
and test files. Verified via `git status`/`git diff --stat` before commit —
nothing unrelated touched.

---

## 9. Environmental limitations

None new. No metrics scrape target (Prometheus/Grafana) exists in this
environment — addressed by design (§4.1/4.3), not left as a gap.

---

## 10. Definition of Done

- [x] Existing observability surface audited and confirmed adequate before
      adding anything (§3) — no unnecessary duplicate routes.
- [x] Real gaps identified and fixed with tests: backend/Python request
      metrics, Python database health check, Python/backend Fabric
      transaction metrics, mobile structured logging (§4).
- [x] No sensitive data newly exposed (§6).
- [x] New code's own lint/type hygiene verified and fixed where the issue
      was this phase's own, pre-existing debt left untouched (§5).
- [x] Protected assets verified before and after.
- [x] No unrelated refactoring; no existing endpoint broken or renamed.

## 11. Final status: **PASS**
