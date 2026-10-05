# EcoTrace India — Quickstart

Get the full platform running and see it genuinely work, end to end, in
under 10 minutes. Every command below is real and was executed live
during P8.8's demo-environment validation and P8.9's documentation
review — nothing here is aspirational.

## Prerequisites

- Docker + Docker Compose
- Python 3.10+ with `requests` and `Pillow` installed (`pip install requests Pillow`) — only needed to run the demo scripts, not the platform itself

## 1. Start the full stack

```bash
docker compose up -d --build
```

This starts PostgreSQL, the Node backend (port 3000), the Python AI
service (port 8100), and the React frontend (port 8080). Migrations are
already baked into the images — nothing else to run.

## 2. Confirm everything is healthy

```bash
python scripts/demo/health_check.py
```

Expect `[PASS]` on all three services. If anything fails, give it another
30 seconds (first boot pulls/builds images) and re-run.

## 3. Seed the demo accounts

```bash
docker compose exec backend npx --yes tsx prisma/seed.ts
```

Idempotent — safe to run any number of times. Creates 5 accounts, one per
role, all with password `Admin@123`:

| Role | Email |
|---|---|
| Admin | `admin@ecotrace.com` |
| Government | `government@ecotrace.com` |
| Collector | `collector@ecotrace.com` |
| Recycler | `recycler@ecotrace.com` |
| Consumer | `consumer@ecotrace.com` |

## 4. See it work

```bash
python scripts/demo/run_scenarios.py all
```

Runs, against the real live stack, all four required demo scenarios:

1. **`happy-path`** — a Consumer submits e-waste, an Admin assigns a
   Collector, the Collector picks it up, an Admin assigns a Recycler, the
   Recycler processes it and a reward is auto-issued — **and**,
   separately, the full AI device lifecycle (register → passport → local
   trust anchor → external trust anchor).
2. **`trust-mismatch`** — a real, live-triggered local trust mismatch
   (not simulated), and proof the system refuses to create a blockchain
   anchor from unverified data.
3. **`blockchain-unavailable`** — the AI service is genuinely stopped and
   restarted; the backend's health proxy is shown degrading gracefully,
   never crashing.
4. **`invalid-device`** — a clean, honest 404 for a device that was never
   registered.

Expect a `SUMMARY` block at the end with `PASS` on all four.

## 5. Explore individually

```bash
python scripts/demo/run_demo.py              # AI device lifecycle only
python scripts/demo/run_backend_demo.py       # backend stakeholder lifecycle only
```

Or open the dashboard at **http://localhost:8080** and log in with any
of the 5 accounts above.

## 6. Reset and go again

```bash
python scripts/demo/reset_all.py
```

Re-seeds the demo accounts, cleans up demo-tagged data, and restarts the
AI service — gets you back to a clean starting point.

## What this honestly shows — and doesn't

Every demo script above discloses its own scope in its output:

- The AI service's external ("blockchain") trust anchor is real,
  functional, and honestly labeled `"provider": "memory"` — there is no
  live Hyperledger Fabric network in this environment (the chaincode and
  Gateway client are real and independently tested; see
  `reports/P8_2_LIVE_BLOCKCHAIN.md`).
- The backend Submission lifecycle and the AI device-intelligence
  lifecycle are two separate systems (see `docs/engineering/
  03_ARCHITECTURE.md`) — each demo script exercises one, honestly.

## Something not working?

- `python scripts/demo/health_check.py` first — it tells you exactly
  which service isn't responding.
- Hit `429 Too Many Requests` on login? The auth endpoint is deliberately
  rate-limited (10 attempts/15 minutes/IP — real brute-force protection,
  see `reports/P8_7_SECURITY_AUDIT.md`). Either wait, or
  `docker compose restart backend` to clear it during rapid iteration.
- Full details: `scripts/demo/README.md`, and every phase's real,
  evidence-backed report under `reports/`.

## Next steps

- `docs/engineering/` — current architecture, API contract, and
  subsystem documentation.
- `reports/P8_7_SECURITY_AUDIT.md` — the full security posture.
- `reports/P8_5_COMPLETE_E2E.md` — every real end-to-end scenario this
  platform has been proven against.
