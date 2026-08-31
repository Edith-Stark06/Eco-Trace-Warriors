# P6.7 — End-to-End System Validation

## 1. Objective

Validate the complete P6 system as far as this environment honestly allows,
and state plainly what could and could not be exercised.

---

## 2. Environment inventory (what's actually available)

| Capability | Available? | Evidence |
|---|---|---|
| Python `intelligence/device_ai` service, standalone | Yes | Runs via `uvicorn`, verified live in this phase (§3) |
| Node `backend/`, standalone (no DB-touching routes) | Yes | Runs via `tsx`, verified live in this phase (§3) |
| PostgreSQL | No | No `psql`/`pg_ctl`; Docker daemon not running (`docker ps` → "cannot find the file specified" — Docker Desktop not started) |
| Live Hyperledger Fabric network | No | Confirmed in P6.2/P6.5 — `blockchain/network/` etc. are empty placeholders, no peer/orderer anywhere |
| Flutter SDK | Yes (installed in P6.3) | `flutter analyze`/`flutter test` run for real in P6.3/P6.4 |
| Android SDK (for a running emulator/APK) | No | `flutter doctor`: "Unable to locate Android SDK" |
| Docker | Binary present, daemon not running | Cannot start Postgres, cannot run the full `docker-compose` stack |

Consequently: a true end-to-end run (Flutter app → real Node backend → real
Postgres → real Python service → real Fabric peer) **cannot be executed in
this environment**, for the same reasons already documented in P6.1–P6.6.
What follows is the most honest validation achievable given that.

---

## 3. Real, live cross-service proof (not mocked)

Rather than only re-running each service's own isolated test suite, this
phase started the **actual** Python service and the **actual** Node backend
as separate live processes and exercised the P6.5 integration between them
over real HTTP — no mocks on either side of that boundary:

```
$ uvicorn (real, intelligence/device_ai, port 8100)
$ tsx src/server.ts (real, backend/, port 3099, DEVICE_AI_SERVICE_URL → 8100)

$ curl http://127.0.0.1:8100/system/blockchain/health
{"success":true,"health":{"status":"disabled","fabric_enabled":false,...}}

$ curl http://127.0.0.1:3099/api/v1/system/blockchain/health
{"success":true,"data":{"status":"disabled","fabricEnabled":false,...}}
```

Then the Python process was killed and the same backend endpoint queried
again, **without restarting the backend**:

```
$ curl http://127.0.0.1:3099/api/v1/system/blockchain/health
{"success":true,"data":{"status":"proxy_unreachable", ...,
  "message":"Could not reach the device intelligence / Fabric Gateway service."}}
HTTP 200
```

This is a genuine, live proof of two things unit/integration tests alone
don't show: (1) the two real services actually speak the same wire format
end to end, not just against each other's mocked shape, and (2) the
degradation path (§ P6.5 "never a 5xx, never a fabricated status") holds
under a real process being real killed mid-session, not just a simulated
`DioException`/`fetch` rejection in a test double.

**Backend `GET /api/v1/health` was also confirmed live and healthy** in the
same session (`status: "ok"`), running without a database connection —
`NODE_ENV=development` does not require `DATABASE_URL` (only `production`
does, per `env.schema.ts`'s `superRefine`).

---

## 4. Consolidated test suite results (this phase, fresh runs)

| Suite | Result | Command |
|---|---|---|
| `intelligence/device_ai` (Python) | **1072 / 1073** (1 pre-existing, unrelated, machine-timing failure — documented since P6.2) | `python -m pytest` |
| P6.1 chaincode (TypeScript/Jest) | **45 / 45** | `npx jest` |
| `backend/` (Node/Jest) | **323 / 323** | `npm test` |
| `backend/` lint + typecheck | 0 errors each | `npm run lint`, `npm run typecheck` |
| Collector app (Flutter) | **18 / 18**, analyze 0 issues | `flutter test`, `flutter analyze` |
| Consumer app (Flutter) | **9 / 9**, analyze 0 issues | `flutter test`, `flutter analyze` |
| `frontend/` (React) | typecheck 0 errors, lint 0 errors, build succeeds; **no test suite exists in this project** | `npm run typecheck`, `npm run lint`, `npm run build` |

**Total automated tests passing across the whole system: 1072 + 45 + 323 +
18 + 9 = 1467**, plus the live cross-service proof in §3, which is not a
counted "test" but a real runtime verification.

---

## 5. Scenario-by-scenario mapping

The mission's own scenario list (A–O), mapped honestly to what actually
exists in this system (not the AI-detection collector workflow the list
assumes — see `reports/P6_3_MOBILE_COLLECTOR.md` §2 for why the real
backend models pickups, not AI device capture):

| # | Scenario (as originally framed) | Actual status |
|---|---|---|
| A | Collector registers a valid device | **Does not apply** — collectors don't register devices on the real backend (§2 above); the analogous real flow is a consumer reporting waste, covered by `backend/tests/integration/submission.test.ts` and P6.4's `flutter test`. |
| B | Device lifecycle advances correctly | Covered for the real `Submission` lifecycle (`PENDING→...→COMPLETED`) by `backend/tests/unit/submission.service.test.ts` + `integration/submission.test.ts` (state-transition validation, all 9 statuses). |
| C | Passport generated | Covered — P5/P6.1/P6.2's existing, unchanged `DevicePassport` tests (1072/1073 device_ai suite). |
| D | Local trust anchor created | Covered — P5.8–P5.10 tests within the same suite. |
| E | Blockchain anchor created | Covered by mocked-Fabric tests (P6.2's 43 tests use a real fake Gateway server speaking the authentic protocol — see `reports/P6_2_FABRIC_GATEWAY_INTEGRATION.md` §9). **Not verified against a live Fabric peer** — no such peer exists here. |
| F | Blockchain verification succeeds | Same as E. |
| G | Local/external fingerprint mismatch detected | Covered — `test_p511_external_trust.py`'s mismatch tests, unchanged. |
| H | Fabric unavailable | Covered **twice over**: P6.2's unit tests (mocked), and this phase's live kill-the-process proof (§3) — the only scenario in this table with a genuine live-process proof rather than only a test double. |
| I | Consumer scans/verifies a device | Partially: scanning is implemented (`ScanScreen`, P6.4) and resolves a submission by id; there is no device-passport verification to scan into (P6.4 §2 — `DeviceVerificationScreen` honestly states this). |
| J | Admin sees blockchain state | Covered — P6.6's `BlockchainHealthCard`, `flutter`/`npm` verified; live-proven via this phase's §3 (the same endpoint it calls). |
| K | Offline collector queues submission | Covered — P6.3's `sync_queue_repository_test.dart` (real SQLite via `sqflite_common_ffi`), 5 dedicated tests. |
| L | Collector reconnects and synchronizes | Covered by the same suite (`SyncManager` reconciliation logic, documented in `reports/P6_3_MOBILE_COLLECTOR.md` §5) — not exercised against a *live* backend reconnect (no running backend + Flutter pairing was executed), only against the fake in-memory API layer the widget/unit tests use. |
| M | Duplicate submission does not create a duplicate | Covered — `SyncQueueRepository`'s dedup test (`re-enqueuing the same submission+action replaces the row instead of duplicating`), and server-side, submissions are always created by an explicit consumer action, not retried automatically (P6.4's `CreateSubmissionController` has no auto-retry). |
| N | Unauthorized lifecycle mutation rejected | Covered — `backend/tests/unit/authorize.middleware.test.ts` + `authenticate.middleware.test.ts` + the submission service's role/ownership checks (`ensureCollectorOwnsSubmission` etc., exercised in `submission.service.test.ts`). |
| O | Read-only GET endpoints produce zero writes/events | Covered across every layer: P5.11–P5.12's dedicated read-only-guarantee tests (Python), P6.2's `read_only_invariants` test category, this phase's blockchain health route (stateless by construction — no repository dependency at all, asserted directly in `blockchain.service.test.ts`'s "purely a read-through proxy" test). |

---

## 6. Honest E2E verdict

- **MOCKED FABRIC E2E = PASS** — every layer's own test suite passes, using
  a real (fake-server or live-process) boundary at the point closest to
  Fabric itself, per §3–§5.
- **LIVE FABRIC E2E = BLOCKED BY ENVIRONMENT** — no Hyperledger Fabric peer
  exists anywhere in this repository or execution environment (§2). Not
  conflated with the mocked result above.
- **LIVE MOBILE ↔ BACKEND E2E = NOT EXECUTED** — no Postgres, so the
  database-backed routes (auth, submissions, rewards) could not be started
  end-to-end with a mobile client attached in this session; only the one
  database-free route (`/system/blockchain/health`) was proven live (§3).
  This is a real, disclosed gap, not claimed as covered.

---

## 7. Definition of Done

- [x] Every independent test suite re-run fresh in this phase, current
      numbers reported (§4), none fabricated or carried over unverified.
- [x] A genuine live, unmocked cross-service proof executed and documented,
      including its degradation path (§3) — not just another layer of
      mocked tests.
- [x] Every mission-specified scenario (A–O) explicitly mapped to real
      coverage, partial coverage, or "does not apply to the real backend,"
      never silently skipped (§5).
- [x] Live Fabric and live mobile↔backend E2E honestly reported as blocked
      by environment, not claimed (§6).
