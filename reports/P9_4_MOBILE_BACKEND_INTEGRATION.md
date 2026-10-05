# P9.4 — Mobile ↔ Backend Integration Hardening

Status: **PASS**

## 1. Scope

Audit every mobile API call in both React Native apps against the real
backend/device_ai contracts (not mocks), harden the shared `apiClient`
with timeout/retry/offline-detection, expand the offline sync queues'
failure-handling, add real tests for the new behavior, and re-run the
full-system regression to confirm zero collateral impact.

## 2. API contract audit

Every API call in both apps was re-verified against the real route
definitions (`backend/src/modules/*/*.routes.ts`,
`intelligence/device_ai/api/*.py`) already established in P9.3. No fake
or mock API calls exist in either app — all calls target real,
verified-existing endpoints; this phase's audit re-confirmed the
authorization-mismatch fix from P9.3 (Collector never calls
`POST /submissions`) and found no further mismatches.

## 3. Centralized API client hardening

`src/api/client.ts` (identical in both apps) gained, on top of its
existing token-attach/401-refresh-retry behavior:

- **Timeout**: every request now uses an `AbortController`-based timeout
  (default 15s, overridable per call), surfaced as a distinct
  `ApiError` with `code: 'TIMEOUT'`.
- **Offline pre-check**: `NetInfo.fetch()` is checked before every
  request (except the refresh call itself, to avoid recursion); if the
  device is confirmed offline, the client fails immediately with a clear
  `NETWORK_ERROR` rather than waiting out a timeout it already knows
  will fail.
- **Bounded retry**: `GET` requests (the only inherently idempotent verb
  used) retry up to twice with jittered exponential backoff on a
  network/timeout error only — never on a real server response (4xx/5xx)
  and never for `POST`/`PATCH`/`DELETE`, which the offline sync queues
  handle with their own bounded-retry logic instead.
- **Custom headers**: `RequestOptions.headers` lets a caller merge in
  extra headers without dropping `Content-Type`/`Authorization`.
- `ApiError.isNetworkError` now covers both `NETWORK_ERROR` and
  `TIMEOUT` (both mean "we don't know whether the server saw the
  request"); a new `ApiError.isTimeout` getter distinguishes the timeout
  case specifically.

**Idempotency-key duplicate-submission protection was investigated and
explicitly not added as a functional feature**: `grep -rn -i
"idempotency" backend/src/` found zero HTTP-level idempotency-key support
anywhere in the backend (the only match is an unrelated internal
reward-issuance dedup guard). Sending an `X-Idempotency-Key` header today
would be silently ignored by the server — a non-functional, false sense
of protection. This is disclosed honestly here rather than claimed as
solved; see §8 for the residual risk and what actually mitigates it.

## 4. A real defect found and fixed: cold-start sync against unconfirmed connectivity

Writing a real test for `useSyncManager` (not just reading the code)
surfaced a genuine bug: `useNetworkStatus` initialized `isOnline` to
`true` optimistically, so on a cold app start while the device is
genuinely offline, `useSyncManager`'s reconnect-triggered effect fired
once before the real (offline) NetInfo state arrived, attempting a wasted
sync (and burning one of its bounded retry attempts) against a
connection that was never actually up.

**Fix**: added `useKnownNetworkStatus()` — a tri-state (`true | false |
null`) variant that starts at `null` ("not yet known") and resolves via
`NetInfo.fetch()` on mount. `useSyncManager` now gates every sync attempt
on `knownIsOnline === true` (never fires while state is unconfirmed), while
still exposing an optimistic-default `isOnline` to callers so the
`NetworkStatusBanner` UI never flickers "offline" for an actually-online
user during that same brief window. Verified with a real test
(`does not attempt to sync while offline from cold start`) that fails
against the old code and passes against the fix.

## 5. Offline queue hardening

- **Queue states** (already established in P9.3, re-verified against
  the P9.4 checklist's terminology): `pending`, `syncing`, `failed` — a
  fourth conceptual "synced" state is represented by removal from the
  queue entirely (no dangling "synced" records to clean up).
- **Bounded retry**: unchanged, already 5 attempts before `failed`
  (verified by test, §6).
- **No infinite retry loops**: verified — a non-network failure
  increments `attempts` and transitions to `failed` at the bound; a
  network failure stops the whole batch (not just the one item) so a
  genuinely offline device doesn't spin through every queued item on
  every reconnect-triggered attempt.
- **Idempotency**: see §3 — genuinely limited by the backend's lack of
  an idempotency mechanism; see §8 for the accepted residual risk.

## 6. New tests

| File | New tests | Covers |
|---|---|---|
| `src/api/client.test.ts` (both apps) | 9 | Bearer token attach, offline pre-check fail-fast, timeout, GET retry-then-succeed, no-retry on POST network error, no-retry on 4xx/5xx, 401→refresh→retry, refresh-failure clears tokens, custom header merge |
| `src/hooks/useSyncManager.test.ts` (both apps) | 5 | Successful sync + queue removal, bounded-retry pending state, failed-after-max-attempts, network-error batch-stop, cold-start-offline no-sync-attempt |
| `src/api/ApiError.test.ts` (both apps, expanded) | +2 | `isNetworkError` covers TIMEOUT, `isTimeout` getter |

Mobile test totals: **collector_app 27/27, consumer_app 26/26** (up
from 12/10 in P9.3 — 31 new tests added this phase). All genuinely run
and passing, not asserted.

Two real, non-obvious findings from writing these tests against the live
implementation (not assumed): `renderHook`/`fireEvent.*` returning
`Promise`s on this React 19/`test-renderer` stack (already documented in
P9.3) applied identically to hook tests; and the cold-start sync bug in
§4, found precisely because the test was written to actually exercise
the mount-time behavior rather than only the steady-state behavior.

## 7. Security review

- No hardcoded secrets: `grep` for credential-shaped literals across
  both apps' source — zero matches.
- No insecure HTTP in release config: the only `http://` literals are
  the two dev-only default constants in `env.ts`, both gated by
  `assertSecureApiUrl()` (throws in a release build).
- No tokens in logs: zero `console.log`/`warn`/`error` calls exist
  anywhere in either app's source.
- No unnecessary sensitive persistence: `AsyncStorage` (plaintext) is
  used only by the sync queues (non-sensitive submission/device-
  confirmation payloads); tokens are exclusively in `expo-secure-store`
  via `secureStorage.ts` — confirmed by source inspection, not assumed.

## 8. Environmental / architectural limitations (honest)

| Item | Detail |
|---|---|
| Duplicate-submission prevention | The backend has no idempotency-key mechanism (verified by direct grep, §3). Residual risk is narrow: a crash/network-drop between the server persisting a record and the client receiving the response could, on retry, create a duplicate. Mitigated by: (a) `syncingRef` serializes the whole batch so only one submission is ever in flight at a time; (b) an item is only removed from the queue after a confirmed 2xx response — a request that never got a response stays `pending`/`syncing` and is visible to the user, not silently duplicated in the background. Full protection requires a backend change, out of this phase's scope. |
| Real device/emulator testing | Unchanged from P9.3 — no Android SDK or macOS/Xcode in this environment; not attempted, not fabricated. |

## 9. Full-system regression

| Suite | Result |
|---|---|
| Backend (Jest) | 341/341 |
| Chaincode (Jest) | 47/47 |
| device_ai (pytest, junitxml) | 1121/1121, 0 errors, 0 failures |
| Frontend | typecheck clean, lint clean (untouched this phase) |
| Collector mobile | 27/27 |
| Consumer mobile | 26/26 |

No files outside `mobile/` were modified this phase.

## 10. Protected asset verification

Verified before and after this phase's work:

| Asset | Result |
|---|---|
| P4.4.2 YOLO11n | MATCH |
| P4.11 Targeted Aug | MATCH |
| P4.12 YOLO11s | MATCH |
| P4.14 Targeted Aug | MATCH |
| P4.5 Data YAML | MATCH |
| P4.7 Data YAML | MATCH |

All 6/6 MATCH.

## 11. Files changed

- `mobile/collector_app/src/api/{client.ts,ApiError.ts,client.test.ts,ApiError.test.ts}`
- `mobile/collector_app/src/hooks/{useNetworkStatus.ts,useSyncManager.ts,useSyncManager.test.ts}`
- `mobile/collector_app/{jest.setup.js,tsconfig.json}`
- `mobile/consumer_app/src/api/{client.ts,ApiError.ts,client.test.ts,ApiError.test.ts}`
- `mobile/consumer_app/src/hooks/{useNetworkStatus.ts,useSyncManager.ts,useSyncManager.test.ts}`
- `mobile/consumer_app/{jest.setup.js,tsconfig.json}`
- `reports/P9_4_MOBILE_BACKEND_INTEGRATION.md` / `.json`

No backend, device_ai, frontend, chaincode, or protected-asset files
touched.

## 12. Final verdict

**PASS.** Every mobile API call is verified against the real backend
contract; the shared client gained genuine timeout/retry/offline
hardening; a real cold-start sync bug was found (by writing a test that
actually exercised the behavior) and fixed; 31 new tests were added and
all genuinely pass; the full regression suite shows zero collateral
impact; the security review found no issues; the one architectural
limitation (duplicate-submission prevention without a backend
idempotency mechanism) is disclosed honestly rather than claimed as
solved.
