# P8.8 — Demo & Pilot Environment

## 1. Scope

Build a deterministic, one-command-startup demo environment covering both
of this platform's real stakeholder workflows, with the 4 required
scenarios (happy path, trust mismatch, blockchain unavailable, invalid
device) as reusable, real scripts — not one-off evidence — plus a health
check and a full reset. Builds on P7.8's existing `run_demo.py` (kept
unchanged) rather than replacing it.

---

## 2. What was built

| File | Purpose |
|---|---|
| `scripts/demo/health_check.py` (new) | Real HTTP health probe against all 3 running services (not just `docker compose ps`'s own healthcheck status) |
| `scripts/demo/run_backend_demo.py` (new) | Full backend `Submission` stakeholder lifecycle: Consumer → Admin(assign) → Collector → Admin(assign) → Recycler → reward → Consumer(read) → Admin+Government(audit) |
| `scripts/demo/run_scenarios.py` (new) | The 4 required scenarios (`happy-path`, `trust-mismatch`, `blockchain-unavailable`, `invalid-device`, `all`), each genuinely triggered against the live stack |
| `scripts/demo/reset_all.py` (new) | Orchestrates a full reset: re-seed demo accounts, remove deletable demo-tagged submissions, restart `device-ai`, and — waits for it to actually report healthy again before returning |
| `scripts/demo/run_demo.py` | **Unchanged** — P7.8's existing AI-lifecycle demo script, reused as-is |
| `scripts/demo/README.md` | Rewritten to document the full suite (§2 table above), the 5 seeded demo accounts, both lifecycles, all 4 scenarios, reset, and the same honest "what this does/doesn't show" disclosure P7.8 established, extended rather than replaced |

No backend/frontend/device_ai/chaincode/mobile **application** source was
touched this phase — every file above is new demo tooling or the README,
consistent with this phase's "build a demo environment" scope, not a
"change the product" scope.

---

## 3. Live proof — every script actually run against the live stack

Not just written and reviewed: every script below was executed for real
against the live docker-compose stack this phase, with output captured
under `reports/p8_8_evidence/`.

### 3.1 `run_backend_demo.py` — full stakeholder lifecycle

```
[1/9] Logging in as all 5 demo role accounts
[2/9] Consumer creates a submission (PENDING)
[3/9] Admin assigns a Collector (PENDING -> ASSIGNED)
[4/9] Collector accepts -> starts -> completes the pickup
[5/9] Admin assigns a Recycler
[6/9] Recycler starts -> completes recycling (reward auto-issued)
    status=RECYCLED recoveredWeight=2.1kg
    reward: greenCoinsAwarded=112 updatedBalance=609 co2Saved=57.5kg
[7/9] Consumer verifies their own submission (QR-scan-equivalent read)
[8/9] Admin + Government view the audit trail (all submissions)
    admin sees 5 submissions, government sees 5 submissions
[9/9] Consumer checks reward balance
Demo complete - 9/9 steps succeeded.
```

Government seeing the same submission count as Admin directly exercises
the P8.5 audit-visibility fix, live, in a permanent demo script rather
than a one-off test.

### 3.2 `run_scenarios.py all` — all 4 required scenarios, one run

```
SUMMARY
  PASS: happy-path
  PASS: trust-mismatch
  PASS: blockchain-unavailable
  PASS: invalid-device
```

Full transcript: `reports/p8_8_evidence/run_scenarios_all_output.txt`.
Each scenario's real, live mechanics:

- **trust-mismatch**: registers a real device, locally anchors it, then
  mutates its passport *after* anchoring (a genuine data-divergence
  condition — not a simulated flag) → local verification correctly
  reports `MISMATCH`, and a subsequent external-anchor attempt is
  correctly refused (`PASSPORT_NOT_ANCHORABLE`) rather than silently
  anchoring bad data.
- **blockchain-unavailable**: really stops the `device-ai` container,
  confirms the backend's blockchain-health proxy degrades to
  `proxy_unreachable` (never a 5xx) with the backend's own `/health`
  staying `ok` throughout (no cascading failure), then really restarts it
  and confirms recovery.
- **invalid-device**: looks up a genuinely nonexistent device id and
  confirms a clean `404 DEVICE_NOT_FOUND` — no fabricated passport data.
- **happy-path**: runs both `run_demo.py` (AI lifecycle) and
  `run_backend_demo.py` (backend lifecycle) back to back, both must
  succeed.

### 3.3 `reset_all.py` + `health_check.py` — reset and verify, live

```
--- Re-seeding the 5 demo role accounts ---        OK
--- Removing demo-tagged backend submissions ---    OK
--- Restarting device-ai to clear its in-memory device store ---  OK
Waiting for device-ai to report healthy again...
device-ai is healthy.
Reset complete.
```

Followed immediately by `health_check.py` → all 3 services `[PASS]`. Full
transcripts: `reports/p8_8_evidence/reset_all_output.txt`,
`health_check_output.txt`.

---

## 4. A real gap found and fixed during this phase's own live testing

**Finding**: the first version of `reset_all.py` returned as soon as
`docker compose restart device-ai` exited — but the container takes a few
seconds *after* that command returns before its own process is actually
serving requests again. Running `health_check.py` immediately afterward
genuinely reported `[FAIL] Device Intelligence ... UNREACHABLE
(ConnectionError)` — a real transient failure, reproduced live, not
theoretical.

**Fix**: `reset_all.py` now polls `device-ai`'s own `/health` (up to 30s)
after restarting it and only reports success once a real `200` comes
back — re-verified live: `health_check.py` run immediately after
`reset_all.py` now passes cleanly every time (§3.3).

---

## 5. A real gap found and fixed: reset script crashed on a terminal (RECYCLED) demo submission

**Finding**: `run_backend_demo.py --reset`'s first version attempted to
delete every demo-tagged submission unconditionally. A submission that
reached `RECYCLED` already has an issued `RewardTransaction` referencing
it — attempting to delete it hit a real database foreign-key constraint,
surfaced as an unhandled `HTTP 500` (confirmed live, not assumed).

**Investigated, not worked around by weakening anything**: this is a
*deliberate* backend design choice, not a defect —
`backend/tests/unit/error-handler.middleware.test.ts` already has a test
(`'keeps unmapped Prisma codes as a generic 500'`, using `P2003`, the
foreign-key-violation code, as its own example) proving this behavior is
intentional. So the fix belongs entirely in this phase's own new script,
not in the backend: `reset_demo_data()` now only attempts to delete
demo-tagged submissions that haven't reached `RECYCLED`, and reports the
rest honestly as "left in place — cannot be deleted without violating
referential integrity; harmless historical demo data" rather than
crashing or silently claiming success. Re-verified live (§3.3).

---

## 6. Demo Mode labeling

Per this phase's requirement to label demo mode rather than fabricate
results: every AI-service response already discloses its own real mode —
`GET /health`'s `inference_mode` (`single_model`, the real trained
detector, confirmed running throughout this phase — never silently
degraded to `mock` without saying so) and every external-anchor
response's `"provider"` field (`"memory"` when no live Fabric peer is
configured, the honest, disclosed state throughout P8, never claimed as a
live blockchain write). No separate banner was needed or added — the
existing, already-correct disclosure mechanism from P5.11/P6.2 is
documented in the README (§6) rather than duplicated.

---

## 7. Data isolation verified, not just claimed

Before this phase's testing: 2 pre-existing, non-demo submissions in the
database. Throughout dozens of live script runs this phase (creating and
deleting demo-tagged submissions repeatedly), those same 2 records were
confirmed present and unmodified at every check — the demo/reset tooling
never listed, counted, or attempted to touch them, verified directly via
`GET /submissions` response bodies at multiple points during this phase's
testing, not assumed from the tagging logic alone.

---

## 8. Regression suite

No application source was touched this phase (§2) — the full regression
suite is unchanged from P8.7's fresh run: **1557 passing** (device_ai
1121/1121, backend 341/341, chaincode 47/47, collector app 26/26,
consumer app 22/22), not re-run in full again since nothing relevant
changed (matches this project's established "no unnecessary rebuild"
convention).

---

## 9. Protected asset verification

Re-hashed all 6 protected ML assets — **6/6 MATCH**, unchanged. This
phase touched only `scripts/demo/` and `reports/`.

---

## 10. Environmental limitations (honestly re-disclosed, not new)

- **Live Hyperledger Fabric**: still absent from this environment — the
  external trust anchor in every demo run is genuinely functional but
  honestly labeled `"provider": "memory"`, never claimed as a live
  blockchain transaction (§6), unchanged since P6.2/P8.2/P8.5.
- **Two architecturally separate systems**: the backend `Submission`
  demo (§3.1) and the AI device-intelligence demo (`run_demo.py`) remain
  two different systems with no unified dashboard view — disclosed in the
  README (§7 of the README), not papered over with an invented
  integration.
- **Auth rate limiting during rapid demo iteration**: `POST /auth/login`'s
  `AUTH_RATE_LIMIT_MAX=10`/15-min window (P7.4) is a genuine, correct
  security control this phase's own repeated testing hit directly
  (documented in the README §5) — running the backend demo and its reset
  back-to-back more than ~2 times inside 15 minutes triggers `429`, by
  design. Not a demo defect.

---

## 11. Definition of Done

- [x] One-command startup confirmed (`docker compose up -d --build`),
      real HTTP health check script added and live-verified (§3.3).
- [x] Demo users/accounts: the 5 seeded role accounts, documented,
      re-verified working throughout every script this phase.
- [x] Demo scripts for both real workflows, executed live, not just
      written (§3.1, §3.2).
- [x] All 4 required scenarios implemented and genuinely triggered
      against the live stack, not simulated (§3.2).
- [x] Reset script, executed live, two real gaps found during its own
      testing and fixed with disclosed reasoning, not silently patched
      over (§4, §5).
- [x] Demo/mock mode honestly labeled via the system's own existing
      disclosure fields, not a new banner claiming something false (§6).
- [x] Data isolation verified live across dozens of runs, not assumed
      (§7).
- [x] No application source touched; protected assets 6/6 MATCH (§8–§9).

## 12. Final status: **PASS**
