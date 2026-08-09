# Multi-Class Dataset Acquisition (Open Images V7 → EcoTrace)

Status: Active
Sprint: P4.3.1 — Production multi-class dataset acquisition orchestration
Audience: dataset engineers, annotation reviewers, QA leads, project leads

---

> **Scope statement — read first.**
> This document describes the **acquisition orchestration layer** that scales the
> P4.2.x single-class `laptop` pilot to the remaining EcoTrace device classes,
> using **Open Images V7 as the only approved source**. It builds **no** model,
> trains **nothing**, and invents **no** dataset statistics. Acquired data lands
> in `dataset_acquisition/staging/` at state **`QA_PENDING`** and is **never**
> auto-approved. **Dataset v1.0 is not released.** Only images a human reviewer
> explicitly advances to `QA_ACCEPTED` may ever become Dataset v1.0 candidates.

---

## 1. Purpose

`scripts/acquire_openimages_multiclass.py` is a controlled, reproducible,
manifest-driven batch orchestrator. For each selected EcoTrace class it:

1. **downloads** that class's Open Images V7 boxes through the existing
   `OIDv4_ToolKit` mechanism (never re-implemented),
2. **converts** the pixel-XYXY source to EcoTrace YOLO by calling the **frozen**
   pilot converter (`scripts/convert_openimages_to_yolo.py`) — the conversion
   mathematics, reject-never-clip rule, file-level atomicity and provenance are
   reused verbatim,
3. **validates** the staged output with the frozen `ImageValidator` (Gate A) and
   the P4.2.2 annotation validator (Gate B), and
4. leaves the class at **`QA_PENDING`**, recording every count from real files
   and the tools' own reports.

The orchestrator is deliberately thin: it adds **no** new domain logic to the
`device_ai` package and duplicates **no** conversion or validation code.

---

## 2. Non-goals / scope boundaries

The following are **explicitly out of scope** for this sprint and must not be
inferred from this tooling:

- No model training, evaluation, export, or inference.
- No Dataset v1.0 assembly, split, freeze, or release.
- No human QA decisions — `qa_accepted`/`qa_rejected` are always `0` here.
- No changes to the frozen taxonomy, validators, configs, schemas, detector,
  training, or API interfaces.
- No changes to existing P4.1.x / P4.2.x tooling (unless a genuine defect).
- No unbounded downloading — every run is bounded by an explicit `--limit`.
- No population of `intelligence/device_ai/datasets/` with unreviewed data.

This sprint is **additive**: one script, one test module, two manifest CSVs, a
machine-readable run report, and this document.

---

## 3. Where things live

```
scripts/
  _ecotrace_toolkit.py                    # shared bootstrap (prepends intelligence/ to sys.path)
  convert_openimages_to_yolo.py           # FROZEN pilot converter (reused, not modified)
  validate_annotations.py                 # P4.2.2 Gate B (reused)
  validate_image_batch.py                 # P4.2.1 Gate A wrapper (reused)
  acquire_openimages_multiclass.py        # THIS orchestrator (new, additive)

dataset_acquisition/
  manifests/
    p4_3_1_openimages_acquisition_plan.csv   # declarative input (hand-authored)
    p4_3_1_acquisition_status.csv            # realised status (machine-updated)
  reports/
    p4_3_1_run_report.json                   # machine-readable run report (per run)
    p4_3_1_acquisition_report.md             # human-readable acquisition report
  staging/
    openimages_<class>_v1/                   # isolated per-class staging (created per class)
    openimages_laptop_v1/                    # PROTECTED pilot staging (never overwritten)
    openimages_laptop_canonical_v1/          # PROTECTED pilot canonical staging
  OIDv4_ToolKit/                             # the download mechanism (git-ignored cache)

intelligence/device_ai/tests/
  test_multiclass_acquisition.py          # 15+ offline tests (synthetic fixtures)

docs/engineering/
  multiclass_dataset_acquisition.md       # this document
```

The orchestrator is launched as a plain file from the repository root. Importing
`_ecotrace_toolkit` performs the `sys.path` bootstrap so `import device_ai …`
and `import convert_openimages_to_yolo …` resolve without installing anything.

---

## 4. Source policy — Open Images V7 only

Open Images V7 (via the OIDv4 Toolkit) is the **only** approved source this
sprint. A `MAPPED` plan row must name the approved source string
`"Open Images V7"`; the orchestrator refuses any other value
(`UNAPPROVED_SOURCE`). Image licences are **per-image Flickr licences that vary
and must be verified per image**; Open Images box annotations are CC-BY-4.0
(Google). See §14 for the licence/provenance posture.

---

## 5. Taxonomy is dynamic (never hardcoded)

The 19 classes and their ids come from
`device_ai.dataset.taxonomy.load_taxonomy()` at runtime. The plan manifest is
validated against that frozen taxonomy on every run: each row's
`(class_id, ecotrace_class)` pair must match `taxonomy.name_for(class_id)`, the
plan must cover **every** taxonomy class exactly once, and no class may appear
twice. If the taxonomy is re-ordered, validation follows automatically because
ids are looked up, not assumed.

| Validation issue code            | Meaning                                              |
| -------------------------------- | ---------------------------------------------------- |
| `CLASS_ID_OUT_OF_RANGE`          | plan `class_id` is outside the taxonomy              |
| `TAXONOMY_MISMATCH`              | `class_id` names a different class than `ecotrace_class` |
| `DUPLICATE_CLASS`                | a class appears more than once in the plan           |
| `MISSING_CLASS`                  | a taxonomy class is absent from the plan             |
| `MAPPED_WITHOUT_SOURCE_CLASS`    | `MAPPED` row has no Open Images class                |
| `UNMAPPED_WITH_SOURCE_CLASS`     | `UNMAPPED` row names an Open Images class            |
| `UNAPPROVED_SOURCE`              | `MAPPED` row's source is not `Open Images V7`        |
| `UNKNOWN_MAPPING_STATUS`         | `mapping_status` is neither `MAPPED` nor `UNMAPPED`  |

Any issue aborts the run with exit code `2` before any download.

---

## 6. Class mapping (explicit, never guessed)

The source→canonical mapping is decided from the Open Images V7 boxable label
set and recorded in `p4_3_1_openimages_acquisition_plan.csv`. A class is
**`MAPPED`** only when a single unambiguous Open Images boxable label exists;
otherwise it is **`UNMAPPED`** and **blocked** from canonical staging (its
`open_images_class` cell is empty and it is never downloaded).

**MAPPED (10):**

| EcoTrace class | Open Images V7 class | Note                       |
| -------------- | -------------------- | -------------------------- |
| laptop         | Laptop               | completed pilot (P4.2.x)   |
| smartphone     | Mobile phone         |                            |
| tablet         | Tablet computer      |                            |
| monitor        | Computer monitor     |                            |
| television     | Television           |                            |
| printer        | Printer              |                            |
| keyboard       | Computer keyboard    |                            |
| mouse          | Computer mouse       |                            |
| camera         | Camera               |                            |
| headphones     | Headphones           |                            |

**UNMAPPED / blocked (9):** `desktop`, `server`, `crt_monitor`, `router`,
`power_supply`, `cable`, `game_console`, `smartwatch`, `battery`.

Rationale for the blocked classes (never guessed):

- `smartwatch` — Open Images only has `Watch`, which merges analog + smart
  watches (ambiguous).
- `crt_monitor` — indistinguishable from `Computer monitor`.
- `power_supply` — `Power plugs and sockets` ≠ a PSU.
- `desktop`, `server`, `router`, `cable`, `game_console`, `battery` — no safe
  boxable Open Images source label exists.

---

## 7. Per-class state lifecycle (kept strictly separated)

Each class advances through a small, explicit state machine. Download,
conversion, validation and QA are **never** conflated:

```
NOT_STARTED
   │  (mapped + selected)
   ▼
DOWNLOAD_FAILED ◄─ download error (no fabricated success)
DOWNLOAD_EMPTY  ◄─ download ok but zero images
   │  (images present)
   ▼
CONVERSION_FAILED ◄─ downloaded but nothing converts cleanly
   │  (≥1 converted)
   ▼
QA_PENDING  ───────────────►  QA_ACCEPTED | QA_REJECTED   (HUMAN ONLY)
```

Other terminal states the orchestrator may report for a class in one run:

| State              | Meaning                                                         |
| ------------------ | -------------------------------------------------------------- |
| `BLOCKED_UNMAPPED` | class has no safe Open Images mapping; never downloaded         |
| `ALREADY_ACQUIRED` | staging already has a provenance manifest (resume); or the pilot |
| `DRY_RUN`          | `--dry-run`: plan only, no side effects                        |

**Only a human** may set `QA_ACCEPTED` / `QA_REJECTED`. The orchestrator never
writes those states and never auto-approves Open Images annotations. Only
`QA_ACCEPTED` data may later become a Dataset v1.0 candidate.

---

## 8. Per-class directory isolation & safety

Each class writes **only** to its own directory
`dataset_acquisition/staging/openimages_<class>_v1/`, produced by the frozen
converter's `write_outputs` (`images/`, `labels/`, `provenance/`, `reports/`).
Safety guarantees enforced in code:

- The `laptop` pilot is **protected**: acquiring it returns `ALREADY_ACQUIRED`
  and performs no download or write, even with `--force`. Its staging and
  canonical staging are never touched.
- Staging into `intelligence/device_ai/datasets/` (or any child) is **refused**
  (`--staging-root` guard, exit `2`).
- A class whose staging already holds `provenance/provenance_manifest.json` is
  **skipped** (`ALREADY_ACQUIRED`) unless `--force` is passed — so one class is
  never silently overwritten and interrupted runs resume cleanly.
- The Open Images source tree is read-only; only staging is written.

---

## 9. CLI

Run from the repository root:

```bash
# List the taxonomy classes and their Open Images mapping, then exit.
python scripts/acquire_openimages_multiclass.py --list

# Plan a single class without downloading (no side effects).
python scripts/acquire_openimages_multiclass.py --class printer --limit 20 --dry-run

# Acquire a single class (bounded).
python scripts/acquire_openimages_multiclass.py --class printer --limit 20

# Acquire several named classes.
python scripts/acquire_openimages_multiclass.py --classes printer keyboard --limit 20

# Acquire every MAPPED class (UNMAPPED and the pilot are skipped).
python scripts/acquire_openimages_multiclass.py --all --limit 20
```

| Flag                    | Purpose                                                        |
| ----------------------- | ------------------------------------------------------------- |
| `--list`                | Print the class/mapping table and exit `0`.                   |
| `--class CLASS`         | Acquire one EcoTrace class by name.                           |
| `--classes C1 C2 …`     | Acquire several classes by name.                              |
| `--all`                 | Acquire every class in the plan (UNMAPPED/pilot self-skip).   |
| `--limit N`             | Max images requested per class (default `20`).                |
| `--dry-run`             | Validate + report intent; no download/convert/validate.       |
| `--force`               | Re-acquire even if staging exists (never the pilot).          |
| `--plan PATH`           | Plan manifest CSV (default the P4.3.1 plan).                  |
| `--staging-root PATH`   | Base staging dir (per-class dirs beneath it).                 |
| `--toolkit-root PATH`   | Root of the OIDv4_ToolKit download mechanism.                 |
| `--status-out PATH`     | Machine-readable JSON run report destination.                 |
| `--conversion-version`  | Version identifier recorded in provenance.                    |
| `--created-at`          | Injected ISO-8601 timestamp (the clock is never read).        |
| `--run-label`           | Free-text label recorded in the report header.                |

Exit codes: `0` all selected classes succeeded (or `--list`/clean `--dry-run`);
`1` at least one class failed to acquire (download failed/empty/nothing
converted); `2` usage error (bad args, invalid plan, invalid mapping, forbidden
staging root, invalid timestamp).

---

## 10. Manifests

### 10.1 Plan (`p4_3_1_openimages_acquisition_plan.csv`) — declarative input

Hand-authored. One row per taxonomy class (0–18). Columns: `class_id`,
`ecotrace_class`, `open_images_class`, `mapping_status`, `source`,
`source_license`, `planned_min`, `planned_recommended`, `planned_ideal`,
`notes`. `class_id`/`ecotrace_class` are code-owned (taxonomy) and must not be
reordered or renamed. The plan fabricates **no** acquisition results.

### 10.2 Status (`p4_3_1_acquisition_status.csv`) — realised counts

Machine-updated. One row per class. Every count column is derived from **real
files / real tool reports on disk** — never hand-fabricated. A class that has
not been run stays `state=NOT_STARTED` with all counts `0`. Columns include
`requested`, `downloaded`, `converted`, `valid_images`, `valid_annotations`,
`duplicates`, `conversion_errors`, `qa_pending`, `qa_accepted`, `qa_rejected`,
`state`, `staging_dir`, `last_updated`, `provenance_note`.

### 10.3 Run report (`p4_3_1_run_report.json`) — machine-readable

Written every run to `--status-out`. Deterministic JSON (`indent=2,
sort_keys=True`). Carries the run context (`source`, `taxonomy_version`,
`limit_per_class`, `dry_run`, `created_at`, `conversion_version`,
`is_dataset_v1: false`, `is_released: false`), a per-state summary and totals,
and one object per class with the full count set and human-readable `messages`.

---

## 11. Counts are derived, never fabricated

| Count               | Where it comes from                                              |
| ------------------- | --------------------------------------------------------------- |
| `requested`         | the `--limit` asked for the class                               |
| `downloaded`        | real image files present after the OID download                 |
| `converted`         | frozen converter report `summary.images_converted`              |
| `conversion_errors` | frozen converter report `summary.conversion_error_count`        |
| `valid_images`      | frozen `ImageValidator`: `total_images` minus files with issues |
| `valid_annotations` | P4.2.2 validator: `total_labels` minus labels with issues       |
| `duplicates`        | frozen `ImageValidator` exact-SHA-256 `duplicate_hashes`        |
| `qa_pending`        | number of converted images awaiting human QA                    |
| `qa_accepted`/`qa_rejected` | always `0` here (human-only, out of scope)              |

A download that returns zero images is reported as `DOWNLOAD_EMPTY` with
`downloaded=0` — **never** as a success. A download that returns images none of
which convert cleanly is reported as `CONVERSION_FAILED` with `converted=0`.

---

## 12. Reuse map (no duplicated logic)

| Concern                    | Reused component (unchanged)                              |
| -------------------------- | -------------------------------------------------------- |
| taxonomy                   | `device_ai.dataset.taxonomy.load_taxonomy`               |
| pixel-XYXY → YOLO math     | `convert_openimages_to_yolo.convert_dataset`             |
| staging writer + provenance| `convert_openimages_to_yolo.write_outputs`               |
| content hashing            | `device_ai.dataset.hashing.sha256_hash` (via converter)  |
| image structural gate (A)  | `device_ai.dataset.image_validation.ImageValidator`      |
| annotation gate (B)        | `scripts/validate_annotations.py:validate`               |
| settings / thresholds      | `device_ai.configs.settings.Settings`                    |
| download mechanism         | `dataset_acquisition/OIDv4_ToolKit` (subprocess)         |

The orchestrator injects the download function, so unit tests substitute an
offline fake and never touch the network.

---

## 13. Determinism & reproducibility

- The only timestamp-like value, `conversion_timestamp`, is **injected** via
  `--created-at`; the wall clock is never read.
- The run report and all converter outputs are serialised with `indent=2,
  sort_keys=True` and a trailing newline.
- A class already acquired is skipped, so re-running is idempotent unless
  `--force` is used.
- Because the converter is reused verbatim, its determinism guarantees (six-
  decimal rounding, sorted discovery, sorted error records) hold here too.

---

## 14. Licence & provenance posture

- **Never** claim commercial or redistribution rights without evidence. The
  plan records what is known **without** asserting rights: Open Images image
  licences are per-image Flickr licences that **vary and must be verified per
  image**; Open Images box annotations are CC-BY-4.0 (Google).
- `UNMAPPED` rows carry `UNKNOWN` licence.
- Every staged image keeps its original OID stem and a full provenance record
  (source, source class, canonical class, class id, SHA-256, dimensions,
  conversion version + timestamp), so each image is traceable to its source.

---

## 15. Real pilot performed this sprint

A very small, bounded real acquisition was run for exactly **one** remaining
MAPPED class with `--limit 20` to exercise the end-to-end path
(download → convert → validate → `QA_PENDING`). The exact class, requested /
downloaded / converted / valid counts, duplicates, conversion errors, and the
final `QA_PENDING` status are recorded verbatim in
`dataset_acquisition/reports/p4_3_1_acquisition_report.md` and the status CSV.
If the environment could not run the real download (e.g. the AWS CLI required by
the OIDv4 Toolkit is absent, or there is no network), that exact blocker is
reported and **no** results are fabricated.

---

## 16. Tests

`intelligence/device_ai/tests/test_multiclass_acquisition.py` covers the fifteen
mandated scenarios with **synthetic fixtures and an injected offline download**
(no network): taxonomy-driven plan validation, valid mapping → `QA_PENDING`,
invalid mapping, unmapped-class blocking, dry-run no-op, per-class isolation,
manifest parsing, resumability (skip then `--force`), count aggregation, no
fabricated success (failed + empty downloads), provenance propagation, invalid
config (bad timestamp / forbidden staging root / unknown class / no selector),
zero-converted → `CONVERSION_FAILED`, multiple classes via `run()`, and limit
handling — plus pilot-protection and `--list` checks.

---

## 17. Definition of done for this sprint

- Orchestrator implemented and reusing (not duplicating) frozen tooling.
- Plan + status manifests present; status counts derived from real files only.
- Tests pass from the `intelligence/device_ai` rootdir; ruff + mypy clean on
  changed files.
- One real bounded pilot run ending at `QA_PENDING` (or an honest blocker).
- This document and the acquisition report written.
- No frozen code, no `laptop` staging, and no unreviewed `device_ai/datasets/`
  data modified. **Dataset v1.0 is not released.**

---

## 18. Limitations

- **Bounded, small runs only.** Acquisition is intentionally throttled by
  `--limit`; this tool does not assemble a full dataset.
- **Whole-image atomicity.** A single bad box voids its image (inherited from
  the frozen converter) — deliberate for curated acquisition.
- **Nine classes are blocked.** They have no safe Open Images source and require
  a different acquisition strategy (out of scope).
- **No quality scoring beyond the frozen validators.** Counts are reported, not
  invented.
- **Human QA is required** before any acquired class can progress.

---

## 19. Next steps (out of scope for this sprint)

- Human QA of each `QA_PENDING` class (sign-off manifests, as for the pilot).
- A canonical-rename / collection-ingest step per class before images join a
  named EcoTrace collection.
- An acquisition strategy for the nine blocked classes.
- Dataset v1.0 assembly, split, freeze and release — governed separately by
  `docs/ai/dataset_v1_freeze_policy.md` and
  `docs/engineering/dataset_v1_release.md`.

---

## 20. Change log

| Date       | Change                                                            |
| ---------- | ----------------------------------------------------------------- |
| 2026-08-09 | P4.3.1: initial multi-class acquisition orchestrator + manifests + tests + this doc. Dataset v1.0 not released. |

> This sprint changes none of the frozen architecture, interfaces, taxonomy,
> validators, configs, or existing P4.1.x / P4.2.x tooling. It is additive: one
> script, one test module, two manifests, a run report, and this document.
