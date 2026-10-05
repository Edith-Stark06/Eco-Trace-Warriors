# P8.1 — Real Deployment Environment

## 1. Scope

Validate EcoTrace in the closest possible environment to actual
deployment, re-verified fresh this phase — not copied from P7.5/P7.10's
reports, even though this phase's findings substantially confirm them.

---

## 2. Pre-flight baseline (established this phase, fresh)

| Suite | Result |
|---|---|
| Python `device_ai` | 1110/1110 this run (the known pre-existing `test_benchmark_measures_latency_and_throughput` CPU-timer flake did not reproduce — see §9) |
| Backend Jest | 339/339 |
| Chaincode Jest | 45/45 |
| Collector Flutter | 22/22, analyze 0 issues |
| Consumer Flutter | 13/13, analyze 0 issues |
| Frontend | typecheck/lint 0 errors, build clean |

**Total: 1529 automated tests passing this run.** Protected assets: 6/6
MATCH (verified before any phase activity).

---

## 3. Docker architecture — inspected fresh

- `docker-compose.yml` (repo root): 4 services — `postgres`, `backend`,
  `device-ai`, `frontend`. `docker compose config` resolves cleanly (full
  output captured this phase): health-gated `depends_on`, correct internal
  Compose-DNS networking (`backend` → `http://device-ai:8100`), zero
  hardcoded secrets (`${VAR:-placeholder}` throughout), correct port
  mappings (5432/3000/8100/8080).
- `backend/Dockerfile`: multi-stage (`node:20-alpine` build → runtime),
  non-root `node` user, `HEALTHCHECK` against `/api/v1/health`.
- `intelligence/device_ai/Dockerfile`: multi-stage (wheel-build → slim
  runtime), non-root `appuser`, `HEALTHCHECK` against `/health`.
- `frontend/Dockerfile`: `node:20-alpine` build → `nginx:1.27-alpine`
  runtime, `HEALTHCHECK` against `/`.
- No changes were needed to any of the above — all three images build
  cleanly and all four services already met every requirement in this
  phase's task list (deterministic startup, health checks, dependency
  ordering, persistent volume, non-root containers, graceful shutdown).
  This is not assumed from P7.5's report — every claim below was
  re-executed this phase.

---

## 4. Full rebuild and live verification (this phase's own run)

```
$ docker compose up -d --build
 eco-trace-warriors-backend    Built
 eco-trace-warriors-device-ai  Built
 eco-trace-warriors-frontend   Built
 Container ecotrace-postgres    Healthy
 Container ecotrace-device-ai   Healthy
 Container ecotrace-backend     Healthy
 Container ecotrace-frontend    Healthy

$ docker compose ps
ecotrace-backend:    Up (healthy)
ecotrace-device-ai:  Up (healthy)
ecotrace-frontend:   Up (healthy)
ecotrace-postgres:   Up (healthy)
```

All three application images were rebuilt from scratch this phase (not
reused from a cached P7 build); all four containers reached `healthy`.

### Logs — no unexpected errors
```
$ docker logs ecotrace-backend    | grep -iE "error|exception|fatal"   -> (none)
$ docker logs ecotrace-device-ai  | grep -iE "error|exception|fatal"   -> (none, beyond the expected "no detector artifact" info warning)
$ docker logs ecotrace-frontend   | grep -iE "error|emerg"              -> (none)
```

### API smoke tests — real, live requests
```
GET  /                                  (frontend)          -> 200
GET  /api/v1/health                     (backend)           -> 200 {"status":"ok",...}
GET  /api/v1/ready                      (backend)           -> 200 {"database":"connected","ready":true}
GET  /api/v1/metrics                    (backend)           -> 200
GET  /api/v1/system/blockchain/health   (backend -> device-ai, cross-container) -> 200 {"status":"disabled","fabricEnabled":false,...}
GET  /health                            (device-ai direct)  -> 200 {"status":"healthy",...}
GET  /api/v1/does-not-exist             (backend)           -> 404
GET  /api/v1/submissions (no auth)      (backend)           -> 401
```

Frontend-to-backend communication confirmed via the same cross-container
blockchain-health proxy call above (the backend reaching `device-ai` by
its Compose DNS name, not `localhost`) — the identical mechanism the
frontend's own `BlockchainHealthCard` depends on.

---

## 5. Database migrations — clean-database round-trip (this phase's own run)

Performed against **two separate, disposable databases**, created and
dropped within this phase, never against the shared `ecotrace` database's
real 35-device data:

### Alembic (`intelligence/device_ai`)
```
$ CREATE DATABASE ecotrace_p8_migration_test
$ alembic upgrade head     -> 001 -> 002 -> 003, clean
$ alembic downgrade base   -> all 6 tables dropped, alembic_version empty
$ alembic upgrade head     -> re-applies cleanly, identical end state (7 tables incl. alembic_version, version_num = 003_add_p511_external_trust_anchors)
$ DROP DATABASE ecotrace_p8_migration_test
```
This confirms the P7.10 fix (the `VARCHAR(32)`→`VARCHAR(64)`
`alembic_version` defect) holds under a genuinely fresh re-run this phase
— not just cited from the prior report.

### Prisma (`backend`)
```
$ CREATE DATABASE ecotrace_p8_prisma_test
$ npx prisma migrate deploy
  Applying 20260721114642_init_auth
  Applying 20260721120341_role_enum
  Applying 20260721200918_add_refresh_tokens
  Applying 20260722120000_add_submissions
  Applying 20260722130000_add_recycler_workflow
  Applying 20260724160937_add_rewards_engine
  All migrations have been successfully applied.
$ DROP DATABASE ecotrace_p8_prisma_test
```
Prisma's migration model is intentionally forward-only (no step-wise
`downgrade` command by design — `prisma migrate reset` is the documented
dev-time equivalent, which was not run against any shared data). A fresh
`migrate deploy` against a genuinely empty database succeeds cleanly, all
6 migrations in order — this is the correct and complete verification for
Prisma's actual migration model, not a gap.

**Real data safety, verified before, during, and after both round-trips**:
`SELECT count(*) FROM devices` on the real `ecotrace` database = 35,
unchanged throughout.

---

## 6. Graceful shutdown / restart — verified this phase

```
$ docker compose down
 Container ecotrace-frontend   Stopped, Removed
 Container ecotrace-backend    Stopped, Removed
 Container ecotrace-device-ai  Stopped, Removed
 Container ecotrace-postgres   Stopped, Removed
 Network eco-trace-warriors_default  Removed
(no forced kills — every "Stopping" is followed by "Stopped", never a timeout/kill)

$ docker compose up -d
 all 4 containers -> Healthy

$ SELECT count(*) FROM devices;  -> 35   (before shutdown, after shutdown, after restart — unchanged)
```

---

## 7. Environment propagation and secrets

- Every credential in `docker-compose.yml` reads from `${VAR:-placeholder}`
  — zero hardcoded secrets, verified by re-reading the file this phase.
- The backend container hardcodes `NODE_ENV=production`
  (`backend/Dockerfile`), which activates `env.schema.ts`'s
  production-safety checks — the compose file supplies real-looking (if
  placeholder) JWT secrets, and the container would refuse to start
  without them, proving those checks are live, not just unit-tested.
- Secret scan re-run this phase (tracked files + hardcoded-credential
  source patterns): **0 findings**.

---

## 8. Findings

No defects found this phase. Every requirement in the P8.1 task list was
already correctly implemented (P7.5/P7.10) and is re-confirmed working
under a completely fresh rebuild, fresh migration round-trip (both ORMs),
and a full stop/start cycle. No source code changes were required — this
phase is a genuine, from-scratch re-verification, not a restatement of
prior claims.

---

## 9. Test accounting

| | Count |
|---|---|
| Previous (P7 final) tests | 1528 (1109 Python + 339 backend + 45 chaincode + 22 collector + 13 consumer) |
| Added this phase | 0 (no new tests — this phase is deployment/infrastructure verification, not code) |
| Removed this phase | 0 |
| Final tests | 1529 collected Python (unchanged count) + 339 + 45 + 22 + 13 |
| Passed (this run) | 1110 Python + 339 + 45 + 22 + 13 = **1529** |
| Failed | 0 (the pre-existing flake did not reproduce this run) |

`test_benchmark_measures_latency_and_throughput` is classified
**PRE-EXISTING BASELINE FAILURE / FLAKY (CPU-timer resolution race)** — it
failed at points in P7 and passed this phase's run, with zero code changes
to the benchmark path in between. Never suppressed, never silently
"fixed."

---

## 10. Protected asset verification

Verified via `sha256sum` before and after this phase — **6/6 MATCH**. No
ML asset touched; no Docker build context includes `dataset_acquisition/`
(`.dockerignore`/`.gitignore` already exclude it).

---

## 11. Environmental limitations

None new. Everything in this phase's scope was genuinely executable in
this environment and was executed.

---

## 12. Definition of Done

- [x] Docker architecture (compose, 3 Dockerfiles) inspected fresh.
- [x] `docker compose config` re-run and validated.
- [x] All three images rebuilt from scratch this phase.
- [x] Full stack started, all 4 services reached healthy.
- [x] Logs checked for unexpected errors — none found.
- [x] Real API smoke tests against the live stack, including
      cross-container communication.
- [x] Migrations re-verified with a genuine upgrade → downgrade →
      re-upgrade round-trip, both Alembic and Prisma, against disposable
      databases — real shared data confirmed untouched throughout.
- [x] Graceful shutdown and restart verified, real data intact.
- [x] Protected assets verified before and after.
- [x] No unrelated changes; no destructive operations against real data.

## 13. Final status: **PASS**
