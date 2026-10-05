# P8.9 — Documentation & Technical Evidence

## 1. Scope

Review every documentation surface a pilot evaluator would actually
read, correct what no longer matches (or never matched) the real,
shipped system, and create the evaluator-first-run guide this phase
explicitly requires. Not a cosmetic pass: every correction below was
verified against real source, running containers, or git history before
being written — consistent with this phase's own "never claim features
that don't exist" mandate applied to the documentation itself.

---

## 2. A real, significant finding: several core docs described a system that was never built

Auditing `docs/engineering/` against the actual, live-verified P5–P8
implementation surfaced a genuine, substantial documentation-reality gap
— not new to this phase, but never previously corrected:

- **`08_AI.md`** described a `classification`/`forecasting`/`fraud`-module
  service living in `ai/app/` with `/internal/classify` endpoints. The
  real, shipped AI service is `intelligence/device_ai/` — a device
  registration → passport → trust-anchor lifecycle, live-verified
  throughout P5–P8.8. Confirmed by inspection: `ai/app/main.py` is a
  0-byte stub from the repository's first commit, never built out.
- **`05_API.md`**'s "Internal AI Service API" section listed the same
  fictional `/internal/classify`/`/internal/forecast`/`/internal/
  fraud-check` contract, and claimed it was "consumed only by the
  backend" — also inaccurate: the real service is reached directly by
  evaluators/demo scripts too (its port is host-mapped for exactly that
  reason).
- **`09_BLOCKCHAIN.md`** listed a fictional chaincode function surface
  (`RegisterDevice(ecoId, recordHash)`, `RecordEvent`, `IssueCertificate`,
  `VerifyCertificate`) that doesn't match the real, shipped, 47/47-tested
  contract (`RegisterDevice`, `UpdateLifecycle`, `AnchorDevicePassport`,
  `VerifyPassportFingerprint`, `GetDeviceAnchor`, `GetDeviceHistory`,
  `GetDevice`, `DeviceExists`, `GetAllDeviceIds` — verified directly
  against `ecotrace-lifecycle.ts`'s real `@Transaction()` methods).
- **`03_ARCHITECTURE.md`**'s ADR-002 ("Backend as sole blockchain
  gateway") and Data Flow rule #2 directly contradict the real
  architecture: `backend/`'s own `blockchain.service.ts` explicitly holds
  no Fabric connection at all — the Python AI service is the actual
  Gateway client (P6.2), a decision that was made during real
  implementation but never reflected back into the ADR.
- **`11_DEPLOYMENT.md`**'s "Backup & Recovery" section described
  scheduled dumps, a rehearsed restore procedure, Fabric-ledger backup,
  and a `deployment/runbooks/` directory — confirmed via direct search:
  none of this exists anywhere in the repository.
- **`11_DEPLOYMENT.md`**'s CI/CD section claimed "no `.github/workflows/`
  directory exists... as of P7.10" — also inaccurate: a real
  `.github/workflows/backend-ci.yml` already existed (lint, typecheck,
  format check, test, build, Docker build on every push/PR to
  `develop`/`main`), just undocumented and scoped to the backend only.
- **Repository-structure claims** in the top-level `README.md` and
  `03_ARCHITECTURE.md`'s Component Architecture table pointed at `ai/`,
  `dashboard/`, `database/`, `deployment/`, `testing/` as if they held the
  real implementation. Verified directly: `dashboard/`, `database/`,
  `testing/` are empty (0 files); `ai/` holds only the same 0-byte stub;
  `deployment/` holds one superseded docker-compose file. The real code
  lives in `backend/`, `frontend/`, `intelligence/device_ai/`, `mobile/`,
  `blockchain/chaincode/` — none of which the README even mentioned by
  their real names.

**Root-cause classification**: these are genuine, disclosed documentation
defects — early-planning-phase documents that were never reconciled with
what actually got built across P5–P8, not something P8 introduced. Fixed
this phase because P8.9's own mandate ("never claim features that don't
exist") applies to documentation as much as to test results.

---

## 3. What was fixed, file by file

| File | What changed |
|---|---|
| `README.md` | Full rewrite: real features (marked what's built vs. not), accurate architecture diagram, accurate tech stack, accurate repository structure (with the unused scaffold directories explicitly disclosed, not deleted — out of scope for a documentation phase), a "Project Status" section citing real reports, and a pointer to the new `QUICKSTART.md`. |
| `QUICKSTART.md` (new) | The required evaluator-first-run guide — every command in it was executed live this phase against the running stack before being written (§4). |
| `docs/engineering/05_API.md` | Corrected the `GET /submissions`/`GET /submissions/{id}` role notes to reflect P8.5's Government audit-visibility fix; replaced the fictional Internal AI Service API section with the real endpoint list (verified against the live OpenAPI schema used throughout P8.5–P8.8) and documented P8.7's new service authentication. |
| `docs/engineering/08_AI.md` | Corrected the Service Architecture diagram, Directory Layout, and API Surface example to the real `intelligence/device_ai/` structure and a real, captured response shape. |
| `docs/engineering/09_BLOCKCHAIN.md` | Corrected Network Design (no live network exists, confirmed `blockchain/network/` is empty), Chaincode Design (the real 9-function contract), and Directory Layout (`fabric-protos/` is real and populated; `network/`/`fabric-network/`/`scripts/`/`docs/` are empty). |
| `docs/engineering/11_DEPLOYMENT.md` | Corrected CI/CD status (a real backend-only workflow exists), rewrote Backup & Recovery to state what genuinely exists (a persistent Docker volume, forward-only migrations) vs. what doesn't (no scheduled backup, no runbooks), and documented `SERVICE_API_KEY`. |
| `docs/engineering/03_ARCHITECTURE.md` | Corrected the Component Architecture table to real directories/technologies, corrected Data Flow rules #2 and #5 (the AI service, not the backend, is the real Fabric client), and marked ADR-002 as superseded rather than leaving it silently wrong. |

Not touched this phase (time-bounded scope, lower evaluator visibility):
`04_DATABASE.md`, `06_BACKEND.md`, `07_FRONTEND.md`, `10_TESTING.md`,
`12_ROADMAP.md` — a spot-check of `10_TESTING.md` found it deliberately
avoids hardcoding test counts (no staleness risk there); the others were
not deep-audited this phase and may carry similar gaps, honestly
disclosed as unreviewed rather than silently assumed clean (§8).

---

## 4. `QUICKSTART.md` — every step live-verified

Not written and assumed correct — actually run, this phase, against the
live stack, in order, exactly as documented:

1. `docker compose up -d --build` → all 4 containers healthy.
2. `python scripts/demo/health_check.py` → `[PASS]` on all 3 services.
3. `docker compose exec backend npx --yes tsx prisma/seed.ts` → 5 demo
   accounts seeded.
4. `python scripts/demo/run_scenarios.py all` → `PASS` on all 4 scenarios
   (`happy-path`, `trust-mismatch`, `blockchain-unavailable`,
   `invalid-device`).
5. `curl http://localhost:8080/` → confirmed real React app HTML
   (`<title>EcoTrace India</title>`, real built JS bundle references),
   not a placeholder.
6. `python scripts/demo/reset_all.py` → clean reset, followed immediately
   by a passing `health_check.py`.

If any of these had failed, `QUICKSTART.md` would have been rewritten to
match reality rather than left describing a broken path — the whole
point of writing it this way.

---

## 5. A real, disclosed rate-limiting consideration this phase's own testing hit

Repeated login calls across this phase's live verification (health
checks, demo runs, scenario runs) genuinely triggered the
`AUTH_RATE_LIMIT_MAX=10`/15-minute-window rate limiter (P7.4) more than
once — correct, intentional security behavior, not a defect. Documented
explicitly in both `QUICKSTART.md`'s "Something not working?" section and
`scripts/demo/README.md` (P8.8) so an evaluator hitting it understands
why, rather than concluding the platform is broken.

---

## 6. Regression suite

No application source touched this phase (§3 — every change is
documentation). Unchanged from P8.8's fresh run: **1,557 passing** tests.

---

## 7. Protected asset verification

Re-hashed all 6 protected ML assets — **6/6 MATCH**. This phase touched
only Markdown files.

---

## 8. Environmental limitations / honestly disclosed gaps

- `04_DATABASE.md`, `06_BACKEND.md`, `07_FRONTEND.md`, `12_ROADMAP.md`
  were not deep-audited this phase for the same class of staleness found
  in §2 — genuinely unreviewed, not claimed clean. A future documentation
  pass should apply the same "verify against real source" method to
  these.
- The `Device Lifecycle Flow` sequence diagram in `03_ARCHITECTURE.md`
  was left as an illustrative target flow (already framed as "the core
  business flow the architecture must serve") rather than rewritten
  line-by-line to match the real, two-system split documented elsewhere
  in the same corrected file — a bounded scope decision, not an oversight
  (the surrounding prose now correctly frames it as aspirational).
- `ai/`, `dashboard/`, `database/`, `deployment/`, `testing/` scaffold
  directories were disclosed as unused, not deleted — removing them was
  judged out of scope for a documentation-correction phase (it would be a
  repository-structure change, reviewed and executed separately if the
  team wants it).

---

## 9. Definition of Done

- [x] Every documentation claim corrected this phase was verified against
      real source, a running container, or git history first — not
      asserted from memory of what "should" be true (§2–§3).
- [x] `QUICKSTART.md` created and every one of its steps genuinely
      executed against the live stack before being documented (§4).
- [x] README rewritten to reflect real, working features vs. disclosed
      gaps, not the original pre-implementation pitch.
- [x] Architecture, AI-pipeline, blockchain-architecture, API-endpoints,
      deployment, env-vars, and known-limitations/backup/recovery all
      reviewed and corrected where wrong (§3).
- [x] Never claims a feature that doesn't exist — the opposite direction
      was also avoided: real, working features (P8.5's audit fix, P8.7's
      service auth, P8.8's demo suite) are now documented, not omitted.
- [x] Unreviewed documentation areas explicitly disclosed, not silently
      assumed correct (§8).
- [x] Protected assets verified 6/6 MATCH; no application source touched.

## 10. Final status: **PASS**
