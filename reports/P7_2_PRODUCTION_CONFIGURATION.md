# P7.2 — Production Configuration & Environment Management

## 1. Scope

Audit and harden runtime configuration across every service; search for
hardcoded secrets/credentials; add configuration-validation tests; keep
docs in sync with what's actually implemented.

---

## 2. Pre-flight state

- Protected assets: 6/6 MATCH (re-verified before any change).
- Baseline tests: 1467/1468 (P7.1 baseline, unchanged going in).

---

## 3. Findings

| # | Finding | Classification |
|---|---|---|
| 1 | Backend (`env.schema.ts`) already fails fast in production on placeholder JWT secrets, missing `DATABASE_URL`, and matching access/refresh secrets — well-designed, no gaps found. | PASS |
| 2 | Python `configs/settings.py` had **no equivalent production-safety check at all** — a `postgres` backend with no `DATABASE_URL`, or `FABRIC_ENABLED=true` with no TLS/identity material, would only fail later, at first connection attempt, not at startup. | WARNING → FIXED |
| 3 | Root `.env.example` was an empty file — no index pointing to the four real per-service templates. | WARNING → FIXED |
| 4 | `docker-compose.yml`'s Postgres password (`ecotrace123`) was hardcoded directly in the compose file rather than sourced from an overridable env var. | WARNING → FIXED |
| 5 | `docker-compose.yml` had no healthcheck on the `postgres` service. | WARNING → FIXED |
| 6 | Secret scan (passwords/keys/tokens/certs, re-run with a broader pattern than P6.8/P7.1) across all tracked `.ts/.tsx/.js/.py/.dart/.yml/.yaml/.json` files. | **0 findings — PASS** |
| 7 | Hardcoded `localhost`/`127.0.0.1` search outside test/config files found exactly one hit: `frontend/src/lib/env.ts`'s `VITE_API_BASE_URL` fallback default — this **is** the configurable mechanism (env var with a sane dev default), not a bug. | PASS |
| 8 | Mobile apps (`collector_app`, `consumer_app`) already read their API base URL via `String.fromEnvironment('API_BASE_URL', ...)`, overridable at build time with `--dart-define` — already production-ready, no change needed. | PASS |
| 9 | `docs/engineering/11_DEPLOYMENT.md`'s "Configuration Management" section referenced a `deployment/env/` directory that does not exist in this repository — stale, pre-implementation planning text. | WARNING → FIXED (this section only) |
| 10 | The rest of `11_DEPLOYMENT.md` (NGINX gateway, `deployment/docker/`, GitHub Actions CI pipeline) is similarly aspirational/pre-implementation and does not match the actual repo layout (`backend/Dockerfile`, `intelligence/device_ai/Dockerfile`, root `docker-compose.yml`, no NGINX, no `deployment/` directory). **Not rewritten in this phase** — deferred to P7.5, where the real deployment stack is actually built, so the doc is corrected once, comprehensively, against final artifacts rather than twice. | WARNING — DEFERRED TO P7.5 |
| 11 | Top-level `ai/` directory (`ai/app/main.py`, one file, from the very first "establish project architecture" commit, never referenced by anything, never touched since) is dead scaffold entirely superseded by `intelligence/device_ai`. Its empty `.env.example` was left as-is — populating config for unused scaffold code would be inventing work. | INFORMATIONAL, no action taken |

---

## 4. A process note on this phase's own mistake

While writing a new backend config-validation test file
(`backend/tests/unit/config.test.ts`), an initial `Write` call **overwrote an
already-existing, already-comprehensive 17-test file** without reading it
first — a real error, not something to gloss over. `git status` immediately
after showed the file as **modified**, not new, which caught it. The
original file was restored via `git checkout HEAD --
backend/tests/unit/config.test.ts`, and only the 3 genuinely new test cases
(not already covered by the original 17) were appended as an addition, not
a rewrite. Verified: `npx jest tests/unit/config.test.ts` → 20/20, full
suite → 326/326 (323 baseline + 3 net-new), no pre-existing coverage lost.
This is recorded here in full because the standing instructions for this
session require never silently hiding a mistake or a near-loss of
previously-validated work.

---

## 5. Changes made

### 5.1 `intelligence/device_ai/configs/settings.py`
Added a `model_validator(mode="after")` (`_validate_production_safety`)
mirroring the backend's `env.schema.ts` refinement:
- `environment == "production"` + `device_backend == "postgres"` or
  `trust_anchor_backend == "postgres"` with no `DATABASE_URL` → rejected.
- `environment == "production"` + `fabric_enabled == True` with any of
  `FABRIC_TLS_CERT_PATH` / `FABRIC_IDENTITY_CERT_PATH` /
  `FABRIC_IDENTITY_KEY_PATH` unset → rejected, naming exactly which are
  missing.
- `staging` is deliberately **not** held to these rules (matches the
  three-way `development | staging | production` split — staging is a
  distinct, less strict tier).

New test file: `intelligence/device_ai/tests/test_p72_production_config_validation.py`
(8 tests, all passing).

### 5.2 `backend/tests/unit/config.test.ts`
3 net-new test cases appended (§4): isolated `JWT_REFRESH_SECRET` placeholder
rejection, malformed `DEVICE_AI_SERVICE_URL` rejection, and the dev-mode
"identical secrets allowed outside production" convenience case.

### 5.3 `docker-compose.yml`
Postgres `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB`/port now read
from `${VAR:-default}` env-var substitution with the exact same defaults as
before (fully backward compatible — `docker compose up` with no `.env`
behaves identically). Added a `pg_isready` healthcheck. Validated with
`docker compose config` (resolves correctly) — **not** applied to the
already-running `ecotrace-postgres` container (a `docker compose up` would
be required to pick up the change; not run here, since that container holds
real pre-existing data this phase does not touch, per P7.1 §3).

### 5.4 `.env.example` (repo root)
Populated with an index pointing at the four real per-service templates and
explaining the mobile `--dart-define` mechanism — was previously empty.

### 5.5 `docs/engineering/11_DEPLOYMENT.md`
"Configuration Management" section corrected to describe the actual
per-service `.env.example` layout and the new production-safety validators,
replacing the stale `deployment/env/` reference (§3 finding #9).

---

## 6. Tests (this phase)

| Suite | Result |
|---|---|
| `intelligence/device_ai` full pytest | **1081/1081** (1073 baseline + 8 new; the previously-observed pre-existing benchmark flake did not reproduce on this run — see note below) |
| New `test_p72_production_config_validation.py` | 8/8 |
| `backend` full Jest | **326/326** (323 baseline + 3 net-new) |
| `backend` lint / typecheck | 0 / 0 errors |
| `docker compose config` | resolves without error |

**Note on the pre-existing flake:** `test_benchmark_measures_latency_and_throughput`
failed in P7.1's run and passed in this phase's run, with no change to the
benchmark code in between — consistent with a CPU-timer-resolution race
already documented as pre-existing, not something this phase fixed or
should claim credit for. Both outcomes are reported so neither run is
cherry-picked.

---

## 7. Security considerations

- No real secret was ever committed or handled in this phase; all example
  values remain obvious placeholders (`dev-insecure-...`, `ecotrace123`).
- The new Python production-safety validator closes a real gap: previously,
  a misconfigured production Fabric deployment would only discover its
  missing identity material on the **first transaction attempt**, not at
  process startup — now it fails immediately with a specific, actionable
  message, matching the backend's existing fail-fast posture.

---

## 8. Protected asset verification

Verified via `sha256sum` before and after this phase's changes — **6/6
MATCH**, both times (no ML asset touched; all changes were to config/docs/
tests).

---

## 9. Git state

All changes scoped to: `intelligence/device_ai/configs/settings.py`,
`intelligence/device_ai/tests/test_p72_production_config_validation.py`,
`backend/tests/unit/config.test.ts`, `docker-compose.yml`, `.env.example`,
`docs/engineering/11_DEPLOYMENT.md`, plus this phase's reports. No
unrelated files touched (verified via `git status`/`git diff --stat`
before commit).

---

## 10. Environmental limitations

None new. The already-running `ecotrace-postgres` container was
deliberately not restarted to pick up the compose-file parameterization,
since doing so is unnecessary risk to real pre-existing data for a
non-functional (defaults-preserving) config change.

---

## 11. Definition of Done

- [x] Configuration audited across backend, Python service, frontend,
      mobile, Docker.
- [x] Real gap found and fixed (Python production-safety validator), with
      tests.
- [x] Secret scan re-run, 0 findings.
- [x] `.env.example` completeness addressed (root index).
- [x] Hardcoded credential (compose Postgres password) parameterized with
      no behavior change.
- [x] Documentation updated where this phase's changes affect it; the
      larger pre-existing doc/reality drift in `11_DEPLOYMENT.md` is
      explicitly flagged and deferred to P7.5, not silently left stale.
- [x] A real process mistake (test file overwrite) caught, corrected, and
      disclosed rather than hidden.
- [x] No unrelated refactoring.

## 12. Final status: **PASS**
