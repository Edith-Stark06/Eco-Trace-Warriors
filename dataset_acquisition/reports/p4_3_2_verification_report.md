# P4.3.2 Verification Report

Sprint: **P4.3.2 — Controlled Multi-Class Dataset Expansion**
Date (injected, deterministic): 2026-08-10T00:00:00+00:00
Scope verified: tablet (id 2), monitor (id 5), printer (id 8) — Open Images V7 only.

All figures below are read from real artifacts under
`dataset_acquisition/reports/` and `dataset_acquisition/staging/openimages_multiclass_v1/`.
Nothing is invented; unmeasurable values are recorded as **NOT MEASURED / BLOCKED**.

---

## Acquisition Results

| Class   | Requested | Downloaded | Converted | Valid | Errors | Duplicates (within / cross) | QA         |
|---------|----------:|-----------:|----------:|------:|-------:|-----------------------------|------------|
| tablet  | 100       | 100        | 100       | 100   | 0      | 0 exact, 2 near / 0         | QA_PENDING |
| monitor | 100       | 99         | 99        | 99    | 0      | 0 exact, 1 near / 0         | QA_PENDING |
| printer | 100       | 0          | 0         | 0     | 0      | NOT MEASURED / NOT MEASURED | BLOCKED (DOWNLOAD_FAILED) |

- **tablet**: 124 total boxes; class-id counts `{"2": 124}`; provenance 100/100 SHA-verified.
- **monitor**: 161 total boxes; class-id counts `{"5": 161}`; provenance 99/99 SHA-verified.
- **printer**: BLOCKED — host-memory `numpy._core._exceptions._ArrayMemoryError`
  while pandas loads the ~14.6M-row Open Images bbox CSV inside the vendored
  OIDv4_ToolKit. Reproduced on one bounded retry. No toolkit edit, no second
  downloader, no fabricated counts. Quality **NOT MEASURED**.

## Verification Steps Performed

| Check | Command / basis | Result |
|-------|-----------------|--------|
| Full device_ai suite | `pytest` from `intelligence/device_ai` rootdir | **848 passed**, 1 warning (pre-existing Starlette deprecation) |
| P4.3.2 offline tests | `pytest tests/test_multiclass_expansion_p432.py` | **21 passed** |
| Lint (changed Python) | `ruff check` on the 3 changed files | **All checks passed** (fixed 5×E501, 1×UP038) |
| Types (changed production Python) | `mypy` on the 2 scripts | Both **type-clean**; only 2 errors remain, both in FROZEN `utils/image_utils.py:62,81` (pre-existing, untouched, out of scope) |
| 3 dry-runs | `p4_3_2_dryrun_{tablet,monitor,printer}.json` | all `DRY_RUN`, `MAPPED`, requested 100 |
| 3 bounded real acquisitions | `p4_3_2_real_{tablet,monitor,printer}.json` | tablet/monitor QA_PENDING; printer DOWNLOAD_FAILED (surfaced, not hidden) |
| Conversion validation | per-class `reports/conversion_errors.json` | `error_count: 0` (both staged classes) |
| Cross-class duplicate check | analysis roll-up | 0 cross-class pairs of 3 total; none auto-deleted |
| Visual QA artifacts | per-class `manual_review/qa_data.json` | tablet 100 previews, monitor 99 previews, both `qa_status: QA_PENDING`, contact sheets present |
| Pilot protection | live vs `p4_3_2_pilot_baseline.json` | laptop_v1 72/10,525,045, laptop_canonical_v1 47/6,110,063, smartphone_v1 15/1,003,504 — all **unchanged: true** |
| Frozen-dir diff | `git diff -- intelligence/device_ai/` | no tracked diffs (only the new untracked test file) |
| Whitespace/markers | `git diff --check` | clean |
| Working tree | `git status --short` | only intended P4.3.2 artifacts; index empty (no commit); `scripts/__pycache__/` is git-ignored |

## Constraint Compliance

- Reused the frozen P4.3.1 orchestrator and the frozen converter — no rewrite,
  no normalization-math change, no box clipping, no silent annotation repair.
- Taxonomy loaded dynamically (v1.0.0); no class list duplicated; no class ID assumed.
- Only the three requested classes touched; the nine BLOCKED_UNMAPPED classes
  untouched; no model downloaded/retrained.
- Every converted image ended QA_PENDING; **nothing** marked QA_ACCEPTED
  automatically; visual QA is prepared, **not complete**.
- No fabrication: printer honestly reported BLOCKED / NOT MEASURED.

## Dataset v1.0 Status

**Dataset v1.0 is NOT RELEASED.** (`is_dataset_v1: false`, `is_released: false`.)
No merge into production `datasets/`. No model exists; no mAP / precision / recall
is claimed. Two classes are staged and QA_PENDING; one is BLOCKED.

## STOP

Per the sprint contract, work halts here. No further acquisition, no touching
blocked classes, no QA_ACCEPTED, no v1.0 release, no training, **no commit, no
push**, and P4.3.3 is not started. All staged data awaits **explicit human
review**.
