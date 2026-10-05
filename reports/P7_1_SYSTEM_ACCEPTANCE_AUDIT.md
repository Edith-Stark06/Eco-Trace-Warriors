# P7.1 — Full System Acceptance Audit

## 1. Scope

A black-box re-verification of the entire repository, from scratch, not
trusting P5/P6 reports blindly. Every claim below was re-run in this
session; nothing is carried over from memory.

---

## 2. Pre-flight state

- Branch: `develop`. `HEAD == origin/develop` = `d1bedd02f326d3dcc841f0306d6540c84c6d9e18`.
- Working tree: clean.
- Protected assets: 6/6 MATCH (re-verified before any change, §7).

---

## 3. Environment discovery (new this phase)

- **Docker Desktop was not running at session start** — started successfully
  this phase (`Start-Process 'Docker Desktop.exe'`). Once up, `docker ps`
  revealed a **pre-existing, already-running `ecotrace-postgres` container**
  (`postgres:16`, `restart: unless-stopped`, 5 weeks old) with real prior
  data (35 devices, 8 users, 1 submission, 3 trust anchors — from earlier
  manual/local work, not created by this session). Two unrelated containers
  (`atlas-postgres`, `atlas-redis`) belonging to a different local project
  were also observed and **were not touched**.
- This means, **for the first time in P6/P7, a live PostgreSQL instance is
  available**. This materially upgrades what can be genuinely verified in
  later P7 phases (previously ENVIRONMENT_BLOCKED items). The existing
  `ecotrace` database's data was **not modified or wiped** by this audit —
  read-only inspection only (`\dt`, row counts, migration-status tables).
- A Flutter SDK from P6.3 was found (not on `PATH`) at `D:\dev-tools\flutter`
  (`3.47.2`, channel stable) and used directly for this phase's checks.
- Android SDK: still absent (`flutter doctor` → `Unable to locate Android
  SDK`). No macOS/Xcode on this Windows machine, so iOS tooling is
  categorically unavailable here.

---

## 4. Findings by component

### 4.1 Backend (`backend/`) — PASS
- `npm test`: **323/323 passed** (24 suites).
- `npm run lint`: 0 errors. `npm run typecheck`: 0 errors.
- `npm run build`: **initially FAILED** with `EPERM` renaming the Prisma
  query-engine DLL — root-caused to an **orphaned `tsx watch src/server.ts`
  process** left over from the P6.7 live smoke test (the earlier `TaskStop`
  call had killed the tracked task wrapper but not its detached child
  process tree — a known Windows behavior). Killed the 3 orphaned PIDs
  (verified via `Get-CimInstance Win32_Process` command-line inspection,
  confirming they were mine and not unrelated MCP tooling before touching
  anything), then the build succeeded cleanly. **Classified WARNING → now
  PASS**; recorded here since it's a real process-hygiene issue, not
  fabricated as if it never happened.

### 4.2 Frontend (`frontend/`) — PASS
- `npm run typecheck`: 0 errors. `npm run lint`: 0 errors.
- `npm run build`: succeeds (pre-existing >500kB chunk warning, unrelated).
- `npm test`: no test script exists in this project — **PRE_EXISTING**,
  same as reported in P6.6, not newly discovered.

### 4.3 Mobile Collector (`mobile/collector_app/`) — PASS (with limitation)
- `flutter analyze`: 0 issues. `flutter test`: **18/18 passed**.
- `flutter build apk --debug`: **ENVIRONMENT_BLOCKED** — no Android SDK.
- iOS build: **ENVIRONMENT_BLOCKED** — no macOS/Xcode on this host.

### 4.4 Mobile Consumer (`mobile/consumer_app/`) — PASS (with limitation)
- `flutter analyze`: 0 issues. `flutter test`: **9/9 passed**.
- Same Android/iOS build limitations as §4.3.

### 4.5 Fabric chaincode (`blockchain/chaincode/ecotrace-lifecycle/`) — FAIL → FIXED → PASS
- `npx jest`: 45/45 passed (before and after the fix below — no regression).
- `npx tsc --noEmit`: clean.
- `npx eslint .`: **FAILED** — 2 real parsing errors. The `.eslintrc.json`
  (added in P6.1) pointed `parserOptions.project` at `tsconfig.json`, whose
  `include`/`exclude` only cover `src/**/*` and explicitly exclude
  `**/*.test.ts` — so ESLint's type-aware linting could never actually
  parse `test/ecotrace-lifecycle.test.ts` or `test/mock-context.ts`. This
  means **chaincode lint has been silently broken since P6.1** and nobody
  caught it because CI/reports only ever reported the Jest numbers.
  **Fixed** by adding `tsconfig.eslint.json` (extends the build config,
  re-includes `test/**/*`, overrides `exclude` so the parent's
  `**/*.test.ts` exclusion doesn't leak through) and pointing ESLint at it
  instead. Re-verified: `eslint .` → 0 errors, `jest` → still 45/45,
  `tsc --noEmit` (using the original build config) → still clean, so the
  production build/compile behavior is unaffected — only linting was fixed.

### 4.6 Fabric Gateway client (`intelligence/device_ai/devices/fabric_gateway_client.py`) — PASS
- Covered by the Python suite below; re-confirmed no insecure TLS fallback
  exists (re-grepped, same result as P6.8).

### 4.7 Python `intelligence/device_ai` — PASS (1 pre-existing failure)
- `python -m pytest`: **1072/1073 passed**. The one failure is the exact,
  named, pre-existing failure from the task brief:
  `tests/test_detector_benchmark.py::test_benchmark_measures_latency_and_throughput`
  (`assert result["latency_ms"] > 0` → `assert 0.0 > 0`, a CPU-timer
  resolution artifact on this machine, not something this session
  introduced or silently patched over). **Classified PRE_EXISTING.**
- `ruff check .`: **1470 findings** (303 auto-fixable). This is `ruff`'s
  first-ever real run against this ~316-file legacy codebase judging by
  the volume — it has clearly never been enforced. **Classified
  PRE_EXISTING / WARNING**, not fixed here: a 1470-finding mass reformat
  is exactly the kind of broad, unrequested rewrite this repo's own rules
  (and this session's standing instructions) prohibit. Left untouched.
- `mypy device_ai`: **203 errors in 81 files**. Same story — mostly
  `Optional[...]`-typed fixtures accessed without a None-narrow in test
  files (low real risk), a couple of genuine source-level type mismatches
  (`acquisition/pipeline.py:440`, `api/routes.py:102`,
  `acquisition/report.py:125-126`), and two missing third-party stub
  packages (`grpc`, `ultralytics`). **Classified PRE_EXISTING / WARNING**
  — same reasoning: mass-fixing 203 errors across 81 files is out of this
  audit's scope and risk budget; flagged for a dedicated future pass.

### 4.8 Database / Alembic / Prisma — PASS (live-verified, not just static)
- Live `ecotrace` database (§3): `alembic_version` = `003_add_p511_external_trust_anchors`
  (head) — matches the code's own migration chain exactly.
  `_prisma_migrations` table shows all 6 Prisma migrations applied and
  unrolled-back, in order. **This is a genuine live confirmation**, an
  upgrade over P6.7/P6.8's static-only chain verification.
- A full destructive `upgrade → downgrade → upgrade` round-trip was
  **deliberately not run against this shared database** — it holds
  pre-existing data (35 devices, 8 users) that is not this session's to
  destroy. That round-trip is scheduled for P7.9/P7.10 against a disposable,
  purpose-created database instead.

### 4.9 Docker / deployment config — WARNING
- Docker daemon: now running (§3), `docker-compose.yml` at repo root
  **only defines the `postgres` service** — no backend, frontend, or Fabric
  services, and the Postgres password (`ecotrace123`) is **hardcoded
  directly in the compose file** rather than sourced from an env var or
  `.env`. `backend/Dockerfile` and `intelligence/device_ai/Dockerfile` both
  exist and are well-formed (multi-stage, non-root user, `HEALTHCHECK`),
  but nothing wires them into the compose stack. **No frontend Dockerfile
  exists.** This is real, actionable scope for P7.5 — recorded here as a
  finding, addressed there as a fix, not duplicated in both reports.

### 4.10 Fabric network — ENVIRONMENT_BLOCKED (unchanged from P6)
- No peer/orderer/CA binaries or running network anywhere in this repo or
  environment. Confirmed by the same absence checks as P6.2/P6.5/P6.7.

### 4.11 Authentication / Authorization / RBAC — PASS
- Re-confirmed via the passing `authenticate.middleware.test.ts` and
  `authorize.middleware.test.ts` suites (§4.1) plus a source re-read: JWT
  access/refresh split, bcrypt hashing, role-based route guards
  (`requireRole`) unchanged since P6.8's review — no regressions found.

### 4.12 API contracts — PASS
- Every backend route file re-grepped against its Zod schema; every route
  responds through the shared `SuccessResponse`/`ErrorResponse` envelope
  (unchanged since P5/P6). No orphaned or undocumented routes found.

### 4.13 Trust verification / lifecycle transitions / audit events — PASS
- Covered by the Python suite's `test_p54`–`test_p512` modules (all green
  except the one named pre-existing failure) and the chaincode's lifecycle
  transition tests (45/45). No changes made, none needed.

### 4.14 OCR / barcode / ML inference — PASS (unchanged, protected)
- Covered by the existing Python suite; no protected asset was touched
  (§7). Not re-benchmarked beyond the existing (pre-existing-failing)
  latency test already discussed in §4.7.

### 4.15 Repository integrity — PASS
- `git fsck --no-progress`: only `dangling blob/commit/tree` entries
  (normal garbage from historical amends/resets by the human collaborator
  before this session, safely collectible, not corruption) — **no
  "missing"/"broken link"/error entries**. Repository object graph is
  intact.
- Secret scan re-run (same methodology as P6.8 §2): 0 tracked secret-like
  files, 0 hardcoded-credential source patterns.

---

## 5. Fix summary (this phase)

| Fix | File(s) | Why |
|---|---|---|
| Chaincode ESLint could not parse test files (silently broken since P6.1) | `blockchain/chaincode/ecotrace-lifecycle/tsconfig.eslint.json` (new), `.eslintrc.json` (1-line change) | Real, scoped bug — small, safe, immediately re-verified against jest/tsc |
| Orphaned `tsx watch` process blocking the Prisma build | (process kill only, no file change) | Left over from P6.7's own background task; blocked `npm run build` |

No other source code was modified in this phase — everything else was
audit-only.

---

## 6. Test suite matrix (this phase, fresh)

| Suite | Result |
|---|---|
| Python pytest (`intelligence/device_ai`) | 1072/1073 (1 PRE_EXISTING) |
| Chaincode Jest | 45/45 |
| Chaincode ESLint | 0 errors (was FAIL, now fixed) |
| Chaincode `tsc --noEmit` | 0 errors |
| Backend Jest | 323/323 |
| Backend ESLint / typecheck / build | 0 / 0 errors, build succeeds |
| Frontend typecheck / lint / build | 0 / 0 errors, build succeeds |
| Frontend test suite | PRE_EXISTING — none exists |
| Collector Flutter analyze / test | 0 issues / 18/18 |
| Consumer Flutter analyze / test | 0 issues / 9/9 |
| Ruff (device_ai) | 1470 findings — PRE_EXISTING, not fixed |
| Mypy (device_ai) | 203 errors — PRE_EXISTING, not fixed |

**Total automated tests passing: 1072 + 45 + 323 + 18 + 9 = 1467** — identical
to the P6 baseline the user supplied, confirming no regression.

---

## 7. Protected asset verification

Verified via `sha256sum` **before** this phase's one code change and
**again after**:

```
c40a4afccacbbde89fce2a3a5fb73467e8614dc09365ea4678b24f7ad9218e92  p442_yolo11n
ca10aaf0de5cc6e24874a24a472b5cf8135f7163f7b54289a74554265a97355c  p411_yolo11n_targeted_aug
96f156d0a46240f6a67187704f91f8a7b1e675e1b94246cf0d83f19f3f0380bc  p412_yolo11s
8fdb02a43db526f7ebb4ba413e6e3dcf5d8eb516590bcd0120d26118e79e9d81  p414_yolo11n_targeted_aug
b5fae47d73ec30698d9825cb04c06722bc1cb41d687a917bb208f1bd1c3bdf5b  p45_data.yaml
5daa90ae1ebca5fe7b5578dd37530e5eba90b47ce7873c35e133e51f7e60e284  p47_final_data.yaml
```

**6/6 MATCH, both times.**

---

## 8. Environmental limitations (carried forward, none new)

1. No live Hyperledger Fabric peer/orderer (§4.10).
2. No Android SDK / no macOS-Xcode — no native mobile builds (§4.3-4.4).
3. Live Postgres is **now available** (§3) — this limitation from P6 is
   **partially lifted** starting this phase; full DB-backed E2E and a live
   migration round-trip are deferred to later P7 phases where they belong
   (P7.8, P7.9/P7.10) rather than duplicated here.

---

## 9. Definition of Done

- [x] Every listed subsystem (1-20 in the task brief) inspected against
      real source, not assumed from prior reports.
- [x] Every runnable test/lint/typecheck/build command actually executed
      this session, with real numbers.
- [x] Every finding classified PASS / WARNING / FAIL / ENVIRONMENT_BLOCKED
      / PRE_EXISTING — nothing left unclassified.
- [x] One real regression-risk bug found and fixed (chaincode ESLint),
      re-verified with no side effects.
- [x] Protected assets verified before and after.
- [x] No unrelated refactoring performed.

## 10. Final status: **PASS WITH DOCUMENTED WARNINGS**

No FAIL-classified findings remain open. Two large, genuinely pre-existing
lint/type-check backlogs (ruff, mypy) are documented as WARNING/PRE_EXISTING
and explicitly not mass-fixed in this audit, consistent with this session's
"small, reviewable, scoped changes only" rule. The Docker/deployment
service-wiring gap is documented as WARNING and deferred to P7.5, where it
is the actual task scope.
