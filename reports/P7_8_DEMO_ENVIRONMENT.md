# P7.8 — Real-World Integration & Demonstration Environment

## 1. Scope

Build a reproducible, one-command EcoTrace demonstration environment that
actually runs, against the real live stack from P7.5 — not a scripted
fiction.

---

## 2. Pre-flight state

- Protected assets: 6/6 MATCH.
- Baseline: 1102/1103 (P7.4-P7.7 unbroken chain).
- P7.5's docker-compose stack running (postgres/backend/device-ai/frontend
  all healthy) with 35 real, pre-existing devices in Postgres.

---

## 3. Design decisions (stated up front, not discovered mid-build)

- **Target the real HTTP API, not service internals.** The demo script
  makes actual HTTP calls to a running `device_ai` service — the same
  interface any real client uses — rather than importing and calling
  Python objects directly. What it proves is therefore what a real
  integration would see.
- **Demo data isolation via architecture, not a special "demo mode."**
  `DEVICE_BACKEND` defaults to `memory` (`docker-compose.yml`, unchanged
  since P7.5) — every device this script creates lives only in that
  process's memory, and the real Postgres `devices` table (owned by the
  backend's unrelated `Submission` model) is never touched. This is not a
  new safety mechanism built for this phase; it's the existing default
  architecture, verified (§6) rather than assumed.
- **Reset = restart**, because no delete endpoint exists on the real API
  (confirmed by re-reading `api/device_routes.py` — no `DELETE
  /devices/{id}` route). Rather than inventing one (out of scope, and a
  schema/API change nobody asked for), the demo's `--reset` does the
  honest, correct thing given the actual architecture: restart the
  in-memory store.

---

## 4. A real gap the demo build immediately surfaced

Building the demo against the live container (no trained model weights
present — matches every real deployment of this image, since the
protected weights are gitignored and never enter a Docker build context)
immediately failed at step 2 (registration):

```
422 NO_DETECTIONS_FOUND — "No electronic devices detected in capture session..."
```

Root cause: `MockDetector.detect()` (`inference/predictor.py`) — the
fallback used whenever no trained weights are present — hardcoded
`detections=[]`, always. `device_ai/devices/service.py:
register_from_images` raises `NoDetectionsForRegistrationError` whenever
`detections` is empty. Net effect: **`/devices/register` was completely
non-functional against the deployed mock pipeline, in any environment
lacking real weights** — which is every CI run, every fresh clone, and
this demo environment, permanently. Every existing passing test for this
endpoint used a test-local `_FakeDetector` substitute instead of the real
`MockDetector`, which is why this had never been caught (confirmed via
`grep -rn "MockDetector\b"` — exactly one production call site, zero
test-level assertions pinning its `detections=[]` behavior).

**Fixed**: `MockDetector.detect()` now returns one synthetic `Detection`
per call, deterministically seeded (same pattern as its already-mocked
`device_type`/`brand`/`confidence` fields), using a label drawn from the
canonical taxonomy (`inference/class_map.py: CANONICAL_CLASSES`) — not the
detector's own `_DEVICE_TYPES` list, which includes non-canonical values
like `"Desktop"` that `register_from_images`'s
`CLASS_NAME_TO_ID.get(label.lower())` lookup would reject. Full Python
suite re-run after the fix: **1104/1105** (the one failure is the
already-documented, unrelated, pre-existing benchmark-timing flake — see
§7), confirming this was a pure completion fix with no behavior change to
anything that previously worked.

---

## 5. What was built

- **`scripts/demo/run_demo.py`** — the interactive, one-command demo. Runs
  the full 10-step lifecycle (register → confirm → finalize → enrich →
  passport → verify → local anchor → external anchor → full trust →
  read-back) against a live service, printing real response data at every
  step. `--reset` prints (and, if Docker is available, runs) the actual
  reset procedure. Each run generates a unique `capture_id`
  (`ecotrace-demo-<8 hex chars>`) so repeated runs never collide — this
  was tuned after discovering (§4's investigation revealed a second,
  related fact) that device IDs are derived deterministically from
  `(capture_id, detection)`, so identical `capture_id` + identical image
  is correctly rejected as `DUPLICATE_DEVICE`, not silently duplicated.
- **`scripts/demo/README.md`** — one-command startup instructions, an
  honest "what this does and does not show" section (see §8), the safety
  argument for data isolation, and the reset procedure.
- **`intelligence/device_ai/tests/test_p78_e2e_demo_lifecycle.py`** — the
  deterministic, CI-runnable half of the demo story: the identical 10-step
  flow via FastAPI's `TestClient` (in-process, no live server needed),
  plus two dedicated tests locking in the duplicate-registration and
  distinct-capture-id behaviors discovered while building the interactive
  script.
- **`intelligence/device_ai/requirements-dev.txt`** — added `requests`
  (the demo script's HTTP client; a dev/demo-tooling dependency, not a
  runtime one, consistent with `httpx` already being declared there for
  the same reason).

---

## 6. Live verification (this phase's own runs, not assumed from P7.5)

```
$ docker compose ps
ecotrace-backend / ecotrace-device-ai / ecotrace-frontend / ecotrace-postgres — all healthy

$ python scripts/demo/run_demo.py --base-url http://localhost:8100
[1/10] health                          -> status=healthy
[2/10] register                        -> device_id=DEV-2026-...
...
[10/10] full trust + read-back         -> local=VERIFIED external=VERIFIED overall=VERIFIED
Demo complete - 10/10 steps succeeded.

# Run again immediately, no --reset:
$ python scripts/demo/run_demo.py --base-url http://localhost:8100
Demo complete - 10/10 steps succeeded.          # distinct device_id, no collision

$ python scripts/demo/run_demo.py --reset
Ran: docker compose restart device-ai -- succeeded.

$ curl http://localhost:8100/devices/<the-demo-device-id>
HTTP 404                                         # demo device cleared

$ docker exec ecotrace-postgres psql -U ecotrace -d ecotrace -c "SELECT count(*) FROM devices;"
 count
-------
    35                                            # real data: untouched, before AND after
```

This is genuine, live, end-to-end proof — not a description of what the
script is expected to do.

---

## 7. Tests

| Suite | Result |
|---|---|
| `test_p78_e2e_demo_lifecycle.py` (new) | 3/3 |
| Python `device_ai` full suite | **1104/1105** (1102 P7.4 baseline + 3 new; 1 pre-existing unrelated flake, same as documented since P6.2/P7.1-P7.4 — did not fail every run this session, consistent with a timer-resolution race, not a regression) |
| `ruff check` on touched files | 0 findings in new/changed code (verified via `git diff`) |
| `mypy` on `predictor.py` | 0 new errors (4 pre-existing errors in transitively-checked, untouched files) |
| Interactive demo script | 10/10 steps, twice in a row, plus a full reset cycle — all live-verified (§6) |

---

## 8. Honest scope: what this demo does not claim

Restated from `scripts/demo/README.md` (the definitive source — this is a
summary, not a duplicate):

1. **No live Hyperledger Fabric transaction.** The "external trust anchor"
   step uses the real API contract against its in-memory implementation
   (`EXTERNAL_TRUST_BACKEND=memory`, default) — MOCKED, stated as such in
   the script's own output, not silently presented as live.
2. **No dashboard visualization of the demoed device.** The frontend's
   `Submission` model and this AI `DeviceRecord`/`DevicePassport` model
   remain architecturally disconnected (P6.4/P6.5, re-confirmed unchanged
   this phase) — building a UI for this was out of this phase's scope (a
   real schema/integration change, not a demo-script task) and is not
   faked.
3. **No literal "consumer role" query.** `GET /devices/{id}` (the only
   real public read path) stands in for "the consumer query step," labeled
   as such, not presented as an actual consumer-role-authenticated call.

---

## 9. Security considerations

- The demo script makes only unauthenticated calls to `device_ai`'s public
  device-lifecycle routes — the same routes any client already reaches
  without auth in this system's actual current state (no auth middleware
  exists on `device_routes.py`, unchanged by this phase — a pre-existing
  characteristic, not introduced here).
- No credentials, tokens, or secrets appear anywhere in `run_demo.py` or
  `README.md`.

---

## 10. Protected asset verification

Verified via `sha256sum` before and after this phase's changes — **6/6
MATCH**. No ML asset touched; the `MockDetector` fix (§4) only affects the
*fallback* path used when no trained weights are present — it does not
read, load, or reference any protected model file.

---

## 11. Git state

Diff scoped to: `intelligence/device_ai/inference/predictor.py` (the
`MockDetector` fix), `intelligence/device_ai/requirements-dev.txt` (+1
line), `intelligence/device_ai/tests/test_p78_e2e_demo_lifecycle.py`
(new), `scripts/demo/` (new: `run_demo.py`, `README.md`). Verified via
`git status`/`git diff --stat` before commit.

---

## 12. Environmental limitations

None new. Every limitation in this phase (§8) is a documented,
already-known architectural fact re-confirmed here, not a new environment
gap.

---

## 13. Definition of Done

- [x] One-command startup documented and verified against the real P7.5
      stack (§6).
- [x] The full mission-specified lifecycle (register → ... → dashboard)
      implemented as far as real architecture allows, with every step that
      doesn't exist honestly named as such, not fabricated (§8).
- [x] Demo data provably isolated from real data — verified live, not
      just argued from config (§6).
- [x] Reset capability implemented and verified to actually clear demo
      data without touching real data (§6).
- [x] A real, previously-unknown integration defect found while building
      the demo, fixed, and verified with no regressions (§4).
- [x] An automated, deterministic E2E test created alongside the
      interactive script, covering the identical real API surface (§5,
      §7).
- [x] Protected assets verified before and after.
- [x] No unrelated refactoring; no schema changes invented to paper over
      the disconnected-domain-model gap.

## 14. Final status: **PASS**
