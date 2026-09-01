# EcoTrace India — Demonstration Environment

A reproducible, deterministic way to stand up the platform and walk both
real stakeholder workflows end-to-end (P7.8, extended P8.8).

## 1. One-command startup

```bash
docker compose up -d --build
```

Starts every service that can genuinely run in this environment:
PostgreSQL, the Node backend, the Python device intelligence service, and
the static frontend (`docker-compose.yml`, P7.5). Migrations are already
baked into the images (Prisma for the backend, Alembic for the device
intelligence service — P8.1 verified both a fresh `migrate deploy`/
`upgrade` round-trip).

## 2. Confirm everything is healthy

```bash
python scripts/demo/health_check.py
```

Checks `docker compose ps` isn't the only signal — it also makes a real
HTTP call to each service's own health endpoint (backend, device-ai,
frontend). Wait for `[PASS]` on all three before continuing.

## 3. Seed the demo role accounts

```bash
docker compose exec backend npx --yes tsx prisma/seed.ts
```

Idempotent (upsert-based, `backend/prisma/seed.ts`) — safe to run any
number of times. Creates the 5 demo accounts every scenario below uses:

| Role | Email | Password |
|---|---|---|
| Admin | `admin@ecotrace.com` | `Admin@123` |
| Government | `government@ecotrace.com` | `Admin@123` |
| Collector | `collector@ecotrace.com` | `Admin@123` |
| Recycler | `recycler@ecotrace.com` | `Admin@123` |
| Consumer | `consumer@ecotrace.com` | `Admin@123` |

## 4. Run the demonstrations

This platform has two architecturally distinct systems (established since
P6.5/P6.7/P7.8 — not new to P8.8), each with its own demo script:

### 4a. AI device intelligence lifecycle (Python service, port 8100)

```bash
python scripts/demo/run_demo.py
```

register → confirm → finalize → enrich → passport → verify → local trust
anchor → external (blockchain-abstraction) trust anchor → full trust
status. See the script's own docstring / the original P7.8 write-up below
(§7) for full detail.

### 4b. Backend stakeholder lifecycle (Node backend, port 3000)

```bash
python scripts/demo/run_backend_demo.py
```

Logs in as all 5 seeded role accounts and walks the real `Submission`
state machine over the real API: Consumer creates a submission → Admin
assigns a Collector → Collector accepts/starts/completes the pickup →
Admin assigns a Recycler → Recycler starts/completes recycling (a reward
is auto-issued) → Consumer verifies their own submission (the
QR-scan-equivalent read) → Admin and Government both view the full audit
trail. Every submission this script creates is tagged
`"EcoTrace Demo — ..."` in its description, so it's always identifiable.

### 4c. All four required demo scenarios

```bash
python scripts/demo/run_scenarios.py happy-path
python scripts/demo/run_scenarios.py trust-mismatch
python scripts/demo/run_scenarios.py blockchain-unavailable
python scripts/demo/run_scenarios.py invalid-device
python scripts/demo/run_scenarios.py all
```

| Scenario | What it proves |
|---|---|
| `happy-path` | Both 4a and 4b, back to back — the complete golden path. |
| `trust-mismatch` | Registers and locally anchors a device, then mutates its passport data *after* anchoring — a genuine data-divergence condition, not a simulated flag — and shows the local trust check correctly reports `MISMATCH` rather than silently staying `VERIFIED`. |
| `blockchain-unavailable` | Stops `device-ai`, shows the backend's blockchain-health proxy degrade gracefully (`proxy_unreachable`, never a 5xx, no cascading failure to the backend's own health), then restarts it. |
| `invalid-device` | Looks up a device id that was never registered and shows a clean `404 DEVICE_NOT_FOUND` — no fabricated or corrupted passport. |

`trust-mismatch` additionally proves the architectural invariant "never
create an external anchor from an unverified local passport": the scenario
attempts exactly that and shows the system refuses
(`PASSPORT_NOT_ANCHORABLE`).

## 5. Resetting demo data

```bash
python scripts/demo/reset_all.py
```

Re-seeds the 5 demo accounts, removes every demo-tagged backend submission
that is safe to delete, and restarts `device-ai` to clear its in-memory
device store — in that order, one command. Individual resets are also
available: `python scripts/demo/run_backend_demo.py --reset` (backend
only) and `python scripts/demo/run_demo.py --reset` (device-ai only).

**A disclosed, honest limitation, not a bug**: a demo submission that
reached `RECYCLED` already has an issued `RewardTransaction` referencing
it — the database's own foreign-key constraint correctly refuses to
delete it (this is a deliberate design choice already locked in by
`backend/tests/unit/error-handler.middleware.test.ts`'s own test that a
foreign-key violation stays an unmapped, generic error rather than being
given a friendly "conflict" message). `run_backend_demo.py --reset`
therefore only deletes demo-tagged submissions that haven't reached that
terminal state yet, and reports the rest as "left in place — harmless
historical demo data" rather than crashing or silently pretending they
were removed.

**A real, disclosed rate-limiting consideration**: `POST /auth/login` is
deliberately rate-limited (`AUTH_RATE_LIMIT_MAX=10` per 15-minute window
per IP, P7.4) — correct, intentional brute-force protection, re-verified
live under load in P8.6/P8.7. Each full run of `run_backend_demo.py` logs
in as all 5 accounts; `reset_all.py` adds one more. Running the backend
demo and its reset back-to-back more than ~2 times inside 15 minutes will
correctly trigger `429 Too Many Requests` on the next login — this is the
security control working as designed, not a defect. If you hit it during
rapid iteration, either wait for the window to elapse or
`docker compose restart backend` (the rate limiter's counters are
in-memory and reset with the process).

## 6. Demo mode labeling

Every response from the AI device intelligence service's inference and
external-anchor endpoints already discloses its own mode honestly, with
no separate "DEMO MODE" banner needed:

- `GET /health`'s `inference_mode` field reports `single_model` (the real
  trained detector — confirmed running throughout P8, not a mock) or
  `mock` if the model directory isn't available.
- Every external/blockchain trust anchor response includes
  `"provider": "memory"` when `FABRIC_ENABLED=false` (the default, no live
  Hyperledger Fabric peer exists in this environment) — never claimed as
  a live blockchain transaction it did not perform.

## 7. What this demo honestly does — and does not — show

**Real and working:**
- The entire AI device registration → passport → trust-anchoring
  lifecycle (§4a), over the real API, against a real running service with
  a real trained model.
- The entire backend stakeholder submission lifecycle (§4b), over the
  real API, against real Postgres, with real reward issuance.
- All four required demo scenarios (§4c), against the live stack, with no
  simulated failures — every "failure" scenario is a genuinely triggered
  condition (a real container stop, a real post-anchor data mutation, a
  real nonexistent device id).

**Not shown, and not faked:**
- **A live Hyperledger Fabric transaction.** No Fabric peer/orderer/CA
  exists anywhere in this repository or environment (confirmed
  repeatedly: P6.2, P6.7, P7.1, P7.5, P8.2). The external trust anchor
  step uses the real `ExternalTrustLedger` API contract against its
  in-memory implementation — genuinely functional, honestly labeled
  `"provider": "memory"`, not a live blockchain write.
- **A single, unified dashboard view spanning both systems.** The
  frontend's `Submission` model (§4b) and the AI-detected `DeviceRecord`/
  `DevicePassport` model (§4a) are two different, architecturally
  disconnected systems (established P6.4, confirmed again P6.5/P7.8/P8.5)
  — there is no view in `frontend/` that renders an AI-detected device's
  lifecycle. Each demo script is honest about which system it exercises.

## 8. Safety: demo data can never touch real data

- Every AI-service demo device is tagged with a `capture_id` starting
  `ecotrace-demo-` (or `ecotrace-scenario-` for the scenario runner) and
  lives only in `device-ai`'s process memory
  (`DEVICE_BACKEND=memory`, the default) — it never touches Postgres.
- Every backend demo submission is tagged `"EcoTrace Demo — ..."` in its
  description, trivially identifiable and cleanly removable (§5).
- Verified this phase: the pre-existing, non-demo submissions in the
  database were confirmed present, unmodified, and correctly excluded
  from every demo-data listing/reset operation throughout P8.8's live
  testing.

## 9. Automated E2E coverage (no live server or Docker required)

```bash
cd intelligence/device_ai
python -m pytest tests/test_p78_e2e_demo_lifecycle.py -v
```

The same AI-lifecycle flow as §4a, deterministic and CI-runnable via
FastAPI's `TestClient` in-process — the automated half of the demo story;
`run_demo.py` is the interactive half. Both exercise the identical real
HTTP routes.

## 10. Why AI-service device IDs don't collide (and what happens if you force it)

Device IDs are derived deterministically from `(capture_id, detection)`,
not randomly assigned (`intelligence/device_ai/devices/service.py:
register_from_images`). Registering the **exact same** `capture_id` twice
with the same image is correctly rejected as `DUPLICATE_DEVICE` — this is
intentional idempotency, not a bug, and is covered by a dedicated test
(`test_registering_the_same_capture_twice_is_rejected_not_duplicated` in
`intelligence/device_ai/tests/test_p78_e2e_demo_lifecycle.py`). Every
script in this directory generates a unique id per invocation, so this is
never actually hit in normal use.
