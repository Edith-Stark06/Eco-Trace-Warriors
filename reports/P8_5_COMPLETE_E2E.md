# P8.5 — Complete Stakeholder End-to-End Workflow Validation

## 1. Scope and method

This phase exercises the **real, live** system — the full docker-compose
stack (`postgres`, `backend`, `device-ai`, `frontend`, all rebuilt and
brought up fresh) — through genuine HTTP requests against the actual
running services, using the 5 real seeded role accounts
(`backend/prisma/seed.ts`: `admin@ecotrace.com`, `government@ecotrace.com`,
`collector@ecotrace.com`, `recycler@ecotrace.com`, `consumer@ecotrace.com`,
all `Admin@123`). Every request/response pair is captured as raw JSON
evidence under `reports/p8_5_evidence/` (JWTs redacted before commit); the
runner script (`run_scenarios.sh`) is committed alongside so every step is
reproducible.

As established honestly since P6.7/P7.8, this system has **two
architecturally distinct halves** that do not share a database or an
API boundary:

1. **`backend/` (Node)** — the real product surface mobile/web clients use:
   `Submission` lifecycle (`PENDING → ASSIGNED → ACCEPTED → IN_PROGRESS →
   COLLECTED → RECYCLING → RECYCLED`), auth, rewards, users, and a
   read-only Fabric-health proxy.
2. **`intelligence/device_ai/` (Python)** — the AI device lifecycle:
   register → confirm → finalize → enrich → passport → local trust anchor →
   external (blockchain-abstraction) trust anchor → full trust status.

The P8 mission's 10 scenarios are mapped honestly onto whichever real
system actually implements them, exactly as P6.7 did for its own scenario
list — never invented, never faked.

---

## 2. Scenario 1 — Full lifecycle: Consumer → Collector → Recycler → Material recovery

Real backend `Submission` state machine, driven end to end with 3 different
authenticated roles, one submission (`id=b900c76b-…`), zero shortcuts:

| Step | Actor | Call | Result |
|---|---|---|---|
| 1 | Consumer | `POST /submissions` | `201`, `status=PENDING` |
| 2 | Admin | `PATCH /submissions/:id/assign` | `status=ASSIGNED` |
| 3 | Collector | `PATCH /submissions/:id/accept` | `status=ACCEPTED` |
| 4 | Collector | `PATCH /submissions/:id/start` | `status=IN_PROGRESS`, `pickupScheduledAt` stamped |
| 5 | Collector | `PATCH /submissions/:id/complete` | `status=COLLECTED` |
| 6 | Admin | `PATCH /submissions/:id/assign-recycler` | recycler attached, still `COLLECTED` |
| 7 | Recycler | `PATCH /submissions/:id/recycle/start` | `status=RECYCLING`, `processingStartedAt` stamped |
| 8 | Recycler | `PATCH /submissions/:id/recycle/complete` (`recoveredWeight`, `materialRecovery`) | `status=RECYCLED`, `recycledAt` stamped, **reward auto-issued**: `113 greenCoins`, `updatedBalance=273`, `sustainability.co2Saved=62.5kg` |
| 9 | Consumer | `GET /submissions/:id` ("QR verification") | own record, `RECYCLED`, all fields intact |
| 10 | Consumer | `GET /rewards/balance` | `greenCoins=273` — the exact balance credited in step 8 |

Evidence: `reports/p8_5_evidence/s1_1_create.json` … `s1_10_reward_balance.json`.

No status was skipped, no transition was forced out of order, and the
reward issued in step 8 exactly matches the balance read back independently
in step 10 — proving the reward pipeline and the read path agree, not just
that each endpoint individually returns `200`.

---

## 3. Scenario 2 — Government/Admin audit trail: a real gap found and fixed

Auditing this scenario (Admin and Government both list all submissions)
turned up a genuine, real authorization inconsistency:

**Before this phase:** `submission.service.ts`'s `list()` and `getById()`
used `isAdmin(actor)` — `ADMIN` only — to decide whether an actor sees every
submission or just their own. But `assignCollector()`/`assignRecycler()`
already use a *different*, wider check, `canAssign()` (`ADMIN` **or**
`GOVERNMENT`), documented in the route file itself: *"Admin/Government
assign a collector."* The result: a `GOVERNMENT` actor could blindly route
work to any submission by ID (via `assign`/`assign-recycler`) but could
**not** list submissions, view one by ID, or discover IDs to act on in the
first place — a role with system-wide write power and no matching read/audit
visibility. Live-proven in this phase: `GET /submissions` as `government@
ecotrace.com` returned `{"data":[]}` (evidence: `s2_2_government_audit_list.
json`) while the same call as `admin@ecotrace.com` returned both real
submissions (`s2_1_admin_audit_list.json`).

**Root-cause classification:** genuine production defect (authorization
gap), not a test defect or environmental limitation — discovered by live
E2E scenario execution exactly as intended by this phase.

**Fix** (`backend/src/modules/submission/submission.service.ts`):
added a `canAudit()` helper (`ADMIN` or `GOVERNMENT`) used **only** for
read paths — `list()` and a new `loadForAudit()` used by `getById()`.
`update()`/`delete()` deliberately keep using the original `isAdmin()`-gated
`loadAccessible()` unchanged, so this fix grants Government **read/audit
visibility only** — it does **not** grant the admin-only mutation override
(editing/deleting someone else's submission, or bypassing the strict
assignment state machine), preserving the deliberate, pre-existing
distinction between Admin's full override authority and Government's
strict-path authority (`assignCollector`'s own comment: *"Admin may
re-assign at any point (override); Government follows the strict state
machine"*).

**Verified live after rebuild:** `GET /submissions` as `government@
ecotrace.com` now returns both submissions, identical to Admin's view
(evidence: `s2_2b_government_audit_list_FIXED.json`). Consumer's own list
(`s2_3_consumer_list_scope.json`) is unaffected — still scoped to their own
records only, confirming the fix did not loosen consumer-level visibility.

**Tests added** (`backend/tests/unit/submission.service.test.ts`):
- `list` — *"returns every submission for a government actor (audit
  visibility, P8.5)"*
- `getById` — *"returns the submission for a government actor regardless of
  owner (audit visibility, P8.5)"*

No existing test asserted Government was restricted to own-only visibility
in `list()`/`getById()` (confirmed by search before writing the fix), so
this is a real gap closed, not a weakened test.

---

## 4. Scenario 3 — Unauthorized mutation / impossible transition / unauthenticated access, all rejected

| Attempt | Expected | Actual | Evidence |
|---|---|---|---|
| Consumer calls `PATCH /submissions/:id/assign` (role-forbidden) | `403 FORBIDDEN` | `403 FORBIDDEN` | `s3_1_consumer_assign_forbidden.json` |
| Recycler re-triggers `recycle/start` on an already-`RECYCLED` submission (impossible transition) | `409 CONFLICT` | `409 CONFLICT`, `"Cannot change status from RECYCLED to RECYCLING."` | `s3_2_impossible_transition.json` |
| No `Authorization` header on a protected route | `401 UNAUTHORIZED` | `401 UNAUTHORIZED` | `s3_3_unauthenticated.json` |

No impossible transition succeeded; no unauthorized mutation succeeded;
authentication is enforced, not optional.

---

## 5. Scenario 4 — Duplicate reward issuance guarded (no duplicate blockchain-adjacent side effect)

Admin attempted a manual `POST /rewards/issue/:submissionId` against the
submission already auto-rewarded in Scenario 1 step 8. Result: `409
CONFLICT`, `"Reward has already been issued for this submission."` — no
second reward transaction, no double-counted `greenCoins`. Evidence:
`s4_1_duplicate_reward.json`.

---

## 6. Scenario 5 — Full AI device lifecycle (register → passport → local anchor → external anchor → full trust)

Ran the real P7.8 demo script (`scripts/demo/run_demo.py`) against the live
`device-ai` container — genuine HTTP calls, no service internals touched:

```
[1/10] health: status=healthy
[2/10] register: device_id=DEV-2026-066B779C-01 device_type=mouse
[3/10] confirm: DETECTED -> CONFIRMED
[4/10] finalize: CONFIRMED -> REGISTERED
[5/10] enrich: carbon_score=0.446
[6/10] passport: eco_id=ET-2026-E08AA5A7
[7/10] verify_passport: VERIFIED
[8/10] local trust anchor: ANCHORED
[9/10] external trust anchor: provider=hyperledger_fabric status=ANCHORED (mocked — no live Fabric peer, disclosed)
[10/10] full trust: local=VERIFIED external=VERIFIED overall=VERIFIED
Demo complete - 10/10 steps succeeded.
```

Evidence: `s5_ai_lifecycle_demo.txt`.

---

## 7. Scenario 6 — Invalid/nonexistent device (passport lookup)

`GET /devices/DEV-NONEXISTENT-00/passport` → `404`,
`{"code":"DEVICE_NOT_FOUND", ...}`. No 500, no fabricated passport, no
silent success. Evidence: `s6_negative_scenarios.txt`.

---

## 8. Scenario 7 — Local trust mismatch (real, not simulated)

A second device (`DEV-2026-SCENARIO-01`) was registered, enriched, and
**locally anchored**. It was then **re-enriched again** (changing its OCR
text/device classification), which changes the passport's recomputed
fingerprint while the trust anchor still holds the pre-mutation fingerprint
— a genuine data-divergence condition, not a forged request:

```
GET /devices/DEV-2026-SCENARIO-01/passport/anchor/verify
  status: MISMATCH
  stored_fingerprint:  81117996b5ab4f07...
  current_fingerprint: 66b62e07dac0c800...
  message: "Passport fingerprint MISMATCH against anchored trust record
            (data may have been modified)."

GET /devices/DEV-2026-SCENARIO-01/trust/full
  local_status: MISMATCH
  overall_status: MISMATCH
```

The mismatch was surfaced accurately and was **not** silently downgraded to
a success — the architectural invariant *"never silently downgrade a failed
trust verification into success"* holds under a real, live-triggered
divergence. Evidence: `s7_anchor_verify_after_mutation.json`,
`s7_trust_full_after_mutation.json`.

---

## 9. Scenario 8 — Blockchain (external anchor) mismatch: the system refuses to anchor, rather than anchoring bad data

Attempting `POST /devices/DEV-2026-SCENARIO-01/passport/external-anchor`
while the device was already in local `MISMATCH` state was **rejected**,
not silently accepted:

```
{"success":false,"error":{"code":"PASSPORT_NOT_ANCHORABLE",
 "message":"Cannot anchor device 'DEV-2026-SCENARIO-01' externally:
            device passport is in MISMATCH state. Passport must be
            locally verified before external anchoring.", ...}}
```

This is a direct, live proof of the required architectural invariant
*"never allow an external anchor to be created from an unverified local
passport"* — under a genuine failure condition, not a hypothetical. A
second mutation afterward left the device correctly `NOT_ANCHORED`
externally and `MISMATCH` locally in `GET /trust/full` — no drift, no false
positive. Evidence: `s8_1_external_anchor.json`, `s8_3_external_mismatch.
json`, `s8_4_full_trust_both_mismatch.json`.

A **conflicting-external-anchor** mismatch (an already-anchored device
re-anchored with a different fingerprint) is separately covered by the
chaincode-level tests added in P8.2 (`'replaces the anchor on a conflicting
re-anchor with a different fingerprint, fully audited'`) — not re-derived
here to avoid duplicating that evidence.

---

## 10. Scenario 9 — Blockchain unavailable: graceful degradation, no cascading failure

With the full stack live, the `device-ai` container was stopped
(`docker compose stop device-ai`) and the backend's Fabric-health proxy was
queried immediately after:

```
Before: GET /api/v1/system/blockchain/health -> 200 {"status":"disabled", "fabricEnabled":false, ...}
Stop device-ai.
After:  GET /api/v1/system/blockchain/health -> 200 {"status":"proxy_unreachable", "message":"Could not reach the device intelligence / Fabric Gateway service."}
         GET /api/v1/health                  -> 200 {"status":"ok"}   (backend itself unaffected — no cascading failure)
```

Never a `5xx`, never a fabricated status, and the backend's own health
stayed `ok` throughout — matching the identical live-kill proof first
established in P6.7 and re-verified fresh here. `device-ai` was restarted
afterward and confirmed healthy. Evidence: `s9_blockchain_unavailable.txt`.

---

## 11. Scenario 10 — API unavailable: honest failure, then clean recovery

The `backend` container itself was stopped and a client request issued
against it directly:

```
Before: GET /api/v1/health -> 200 {"status":"ok"}
Stop backend.
During: GET /api/v1/health -> curl exit 7 (connection refused), HTTP_STATUS:000
Restart backend.
After:  GET /api/v1/health -> 200 {"status":"ok"}, uptime=5.15s (fresh process, clean recovery)
```

No silent success, no stale cached "ok" — a genuinely unavailable API
fails honestly, and comes back cleanly once restarted. Evidence:
`s10_api_unavailable.txt`.

---

## 12. Scenario-to-mission mapping

| # | Mission scenario | Real status |
|---|---|---|
| 1 | Full lifecycle Collector → Consumer | §2 steps 1–5 (Consumer submits, Collector picks up) — **PASS, live** |
| 2 | Collector → Recycler | §2 steps 6–7 — **PASS, live** |
| 3 | Recycler → Material recovery | §2 step 8 (`materialRecovery`, reward, sustainability) — **PASS, live** |
| 4 | Consumer QR verification | §2 step 9 — **PASS, live** (scope matches P6.4/P8.4's documented reality: scans resolve a submission id, not a device passport) |
| 5 | Government/Admin audit trail | §3 — **real gap found and fixed, then PASS, live** |
| 6 | Invalid/corrupted passport | §7 (nonexistent device, 404) + §8 (mismatch correctly refused rather than accepted) — **PASS, live** |
| 7 | Local trust mismatch | §8 — **PASS, live, genuinely triggered** |
| 8 | Blockchain mismatch | §9 (external anchor correctly blocked on an already-mismatched local passport) + P8.2's conflicting-re-anchor chaincode tests — **PASS, live + existing coverage** |
| 9 | Blockchain unavailable | §10 — **PASS, live** |
| 10 | API unavailable | §11 — **PASS, live** |

Additional invariants explicitly required by this phase, all verified: no
impossible transitions succeeded (§4), no trust bypasses occurred (§8–§9),
no unauthorized mutations succeeded (§4), no duplicate reward/anchor side
effects occurred (§5, §9's conflicting-anchor tests), no corrupted passport
was accepted (§7–§8).

---

## 13. Full regression suite (fresh, this phase)

Docker compose stack stopped before host-level suites (established
port-collision-avoidance pattern), stopped/restarted around the live
scenarios in §10–§11, and brought back up healthy afterward.

| Suite | Result | Command |
|---|---|---|
| Backend (Node/Jest) | **341 / 341** (339 baseline + 2 new, §3) | `npm test` |
| Backend lint | 0 errors | `npm run lint` |
| Backend typecheck | 0 errors | `npm run typecheck` |
| Chaincode (TypeScript/Jest) | **47 / 47** (unchanged since P8.2) | `npx jest` |
| `intelligence/device_ai` (Python) | **1109 / 1110** — 1 pre-existing baseline failure (`test_benchmark_measures_latency_and_throughput`, wall-clock-timing flake, unchanged/documented since P6.2) | `pytest` (junitxml: `tests=1110 failures=1 errors=0 skipped=0`) |
| Collector app (Flutter) | **22 / 22**, analyze 0 issues | `flutter test` |
| Consumer app (Flutter) | **18 / 18**, analyze 0 issues | `flutter test` |
| Frontend (React) | typecheck 0, lint 0, build succeeds; no test suite exists (unchanged) | `npm run typecheck && npm run lint && npm run build` |

**Total: 341 + 47 + 1109 + 22 + 18 = 1537 passing.**

---

## 14. Test accounting

| | Count |
|---|---|
| Previous (P8.4 baseline) | 339 (backend) + 47 (chaincode) + 1109/1110 (device_ai) + 22 (collector) + 18 (consumer) = 1535 |
| Added this phase | 2 (backend, §3) |
| Removed this phase | 0 |
| Final | 1537 passing, 1 pre-existing unrelated baseline failure (unchanged) |

---

## 15. Protected asset verification

Re-hashed all 6 protected ML assets before and after this phase's code
change — **6/6 MATCH**, byte-for-byte identical (this phase touched only
`backend/src/modules/submission/submission.service.ts` and its test file;
no ML asset was read, written, or referenced):

```
c40a4afccacbbde89fce2a3a5fb73467e8614dc09365ea4678b24f7ad9218e92  p442_yolo11n/best.pt
ca10aaf0de5cc6e24874a24a472b5cf8135f7163f7b54289a74554265a97355c  p411_yolo11n_targeted_aug/best.pt
96f156d0a46240f6a67187704f91f8a7b1e675e1b94246cf0d83f19f3f0380bc  p412_yolo11s/best.pt
8fdb02a43db526f7ebb4ba413e6e3dcf5d8eb516590bcd0120d26118e79e9d81  p414_yolo11n_targeted_aug/best.pt
b5fae47d73ec30698d9825cb04c06722bc1cb41d687a917bb208f1bd1c3bdf5b  p45_data.yaml
5daa90ae1ebca5fe7b5578dd37530e5eba90b47ce7873c35e133e51f7e60e284  p47_final_data.yaml
```

---

## 16. Git state / scope

Diff scoped to exactly: `backend/src/modules/submission/submission.
service.ts` (the `canAudit()` fix, §3), `backend/tests/unit/submission.
service.test.ts` (2 new tests, §3), plus new evidence-only additions under
`reports/p8_5_evidence/` and this report. No ML asset, no chaincode, no
mobile, no frontend, no unrelated file touched. Verified via `git status`/
`git diff --stat` before commit.

---

## 17. Environmental limitations (unchanged, re-confirmed)

- **Live Hyperledger Fabric peer**: still absent from this environment
  (§6, §9's "external anchor" is the in-memory/mock provider, disclosed in
  its own response as `"provider":"memory"`). `LIVE FABRIC = BLOCKED BY
  ENVIRONMENT`, consistent with P8.2.
- **Android/iOS native builds**: unchanged from P8.3/P8.4, not re-attempted
  this phase (no relevant code changed).
- The two backend "halves" (`backend/` Submission model and
  `intelligence/device_ai` AI/passport model) remain architecturally
  disconnected, as documented since P6.5/P7.8/P6.7 — this phase validated
  each honestly on its own terms rather than inventing a fictitious unified
  flow between them.

---

## 18. Definition of Done

- [x] All 10 mission scenarios executed against the real, live system (not
      simulated), each with captured request/response evidence (§2–§11,
      §12 mapping table).
- [x] A genuine production defect found through live scenario execution
      (Government audit-visibility gap), root-cause classified, fixed
      narrowly, tests added, fix re-verified live post-rebuild (§3).
- [x] No impossible transitions, no trust bypasses, no unauthorized
      mutations, no duplicate reward/anchor side effects, no corrupted
      passport accepted — all explicitly verified (§4–§9, §12).
- [x] Full regression suite re-run fresh this phase, real counts, no
      fabrication, pre-existing failure correctly labeled (§13–§14).
- [x] Protected assets verified 6/6 MATCH (§15).
- [x] Scope kept narrow — one real defect fix, no unrelated refactoring
      (§16).
- [x] Environmental limitations honestly re-confirmed, not silently
      dropped (§17).

## 19. Final status: **PASS — LIVE FABRIC BLOCKED BY ENVIRONMENT (unchanged, disclosed)**
