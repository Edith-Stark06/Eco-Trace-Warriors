# EcoTrace India — Demonstration Environment

A reproducible, one-command way to stand up the platform and walk the real
device intelligence lifecycle end-to-end (P7.8).

## One-command startup

```bash
docker compose up -d --build
```

This starts everything that can genuinely run in this environment:
PostgreSQL, the Node backend, the Python device intelligence service, and
the static frontend (see `docker-compose.yml`, P7.5). Migrations for the
backend's own tables are already baked into the Postgres image via Prisma's
migration history; the device intelligence service defaults to an
in-memory device store (`DEVICE_BACKEND=memory`), so there is nothing to
migrate for it in the default configuration.

Wait for every service to report healthy:

```bash
docker compose ps
```

## Run the demonstration

```bash
python scripts/demo/run_demo.py
```

Walks the complete, real device lifecycle over the device intelligence
service's actual HTTP API (`http://localhost:8100` by default — override
with `--base-url`):

1. Health check
2. Register a device from a (synthetic, generated in-memory) capture image
3. Confirm (`DETECTED` → `CONFIRMED`)
4. Finalize (`CONFIRMED` → `REGISTERED`)
5. Enrich (brand/condition/material/carbon intelligence)
6. Generate the Device Passport
7. Verify the Device Passport (local)
8. Create a local Trust Anchor
9. Create an external (blockchain-abstraction) Trust Anchor
10. Verify full trust status, and read the device back (the "consumer
    query" read path)

Every step is a real HTTP call against a real running service — nothing in
the script talks to Python internals directly. Run it as many times as you
like; each run generates its own unique `capture_id`, so back-to-back runs
never collide (see "Why device IDs don't collide" below).

## What this demo honestly does — and does not — show

**Real and working:**
- The entire device registration → passport → trust-anchoring lifecycle,
  over the real API, against a real running service.
- The local Trust Anchor and the external Trust Anchor abstraction (P5.9,
  P5.11) — both genuinely create, store, and verify anchors.

**Not shown, and not faked:**
- **A live Hyperledger Fabric transaction.** No Fabric peer/orderer/CA
  exists anywhere in this repository or environment (confirmed repeatedly:
  P6.2, P6.7, P7.1, P7.5). The "external trust anchor" step above uses the
  real `ExternalTrustLedger` API contract against its in-memory
  implementation (`EXTERNAL_TRUST_BACKEND=memory`, the default) — this is
  **MOCKED**, not live, and the demo script says so explicitly in its own
  output. Setting `FABRIC_ENABLED=true` against a real peer would exercise
  the genuine P6.2 gRPC client instead, with zero code changes to this
  script.
- **A dashboard visualization of this specific device.** The frontend's
  `Submission` model (pickup logistics: category/weight/address) and this
  AI-detected `DeviceRecord`/`DevicePassport` model are two different,
  architecturally disconnected systems (established P6.4, confirmed again
  P6.5/P7.8) — there is no view in `frontend/` that renders an AI-detected
  device's lifecycle. Building one was out of scope for this phase (it
  would require a real backend schema change, not a demo-script
  workaround) and is not faked here.
- **A "consumer" role querying this device.** No consumer-facing endpoint
  for AI-detected devices exists on the real backend. Step 10 above uses
  `GET /devices/{id}` — the actual, only public read path that exists —
  labeled honestly as "the closest real equivalent," not as literal
  consumer-role access.

## Safety: demo data can never touch real data

- Every demo device is tagged with a `capture_id` starting
  `ecotrace-demo-`, trivially identifiable.
- Unless the service is explicitly reconfigured with
  `DEVICE_BACKEND=postgres`, every device record this script creates lives
  **only in the device-ai process's memory** — `docker-compose.yml`'s
  default configuration never sets that variable, so this is the actual
  running state, not a documented-but-unverified assumption.
- The real Postgres `devices` table belongs to a completely different
  system (the backend's `Submission` workflow) that this script never
  queries or writes to. Verified in this phase: the pre-existing 35-row
  real dataset was unaffected before, during, and after every demo run.

## Resetting demo data

```bash
python scripts/demo/run_demo.py --reset
```

Prints the reset procedure and — if Docker Compose is available — runs it
automatically: `docker compose restart device-ai`. This clears every demo
device (the in-memory store is freshly re-created on startup) without
touching Postgres or any other service. You normally don't need this
between runs (each run uses a fresh `capture_id`), but it's here for a
clean-slate restart.

## Why device IDs don't collide (and what happens if you force it)

Device IDs are derived deterministically from `(capture_id, detection)`,
not randomly assigned (`intelligence/device_ai/devices/service.py:
register_from_images`). Registering the **exact same** `capture_id` twice
with the same image is correctly rejected as `DUPLICATE_DEVICE` — this is
intentional idempotency, not a bug, and is covered by a dedicated test
(`test_registering_the_same_capture_twice_is_rejected_not_duplicated` in
`intelligence/device_ai/tests/test_p78_e2e_demo_lifecycle.py`). The script
avoids this entirely by generating a unique `capture_id` per invocation.

## Automated E2E coverage

The same 10-step flow, deterministic and CI-runnable (no live server or
Docker required — uses FastAPI's `TestClient` in-process):

```bash
cd intelligence/device_ai
python -m pytest tests/test_p78_e2e_demo_lifecycle.py -v
```

This is the automated half of the demo story; `run_demo.py` above is the
interactive half. Both exercise the identical real HTTP routes.
