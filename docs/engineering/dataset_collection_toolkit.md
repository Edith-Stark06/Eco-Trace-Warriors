# Dataset Collection Toolkit — Engineering Reference

**Sprint:** P4.2.1 — Production Image Collection Toolkit
**Component:** Device Intelligence Engine (DIE) — YOLO Detector (milestone M1.4)
**Status:** Active
**Related:** `08_AI.md`, `device_collection_process.md`,
`device_dataset_acquisition.md`, `device_detection_annotation.md`
**Scope:** Four command-line tools that help the team collect **Dataset v1.0**
efficiently, plus the shared glue that binds them to the frozen P4.1.2 dataset
pipeline. The toolkit **downloads nothing, trains nothing, defines no API, and
changes no schema, model, or interface.** Every image metric, hash, duplicate
check, and provenance record is produced by existing `device_ai` code; the
scripts only orchestrate and format.

---

## 1. Where This Fits

Contributors submit folders of images. Before those images become an immutable
dataset version, the team needs to answer four operational questions:

| Question | Tool |
| --- | --- |
| Is this batch clean enough to accept? | `scripts/validate_image_batch.py` |
| How far along is each class toward its target? | `scripts/dataset_progress.py` |
| How do I combine everyone's folders without losing provenance? | `scripts/merge_collection_batches.py` |
| What is the overall state of the collection effort? | `scripts/collection_dashboard.py` |

The tools sit at repository top level under `scripts/` and reuse the frozen
dataset code shipped in `intelligence/device_ai/`:

```
 scripts/ (this toolkit)                  intelligence/device_ai/ (frozen P4.1.2)
 ─────────────────────────                ────────────────────────────────────────
 validate_image_batch.py  ──reuses──▶     dataset/image_validation.py  (ImageValidator)
                          ──reuses──▶     dataset/metadata.py          (MetadataGenerator)
 dataset_progress.py      ──reuses──▶     dataset/taxonomy.py          (load_taxonomy)
 merge_collection_batches ──reuses──▶     dataset/provenance.py        (ProvenanceCollector)
 collection_dashboard.py  ──reuses──▶     dataset/{duplicates,metadata,layout}
 _ecotrace_toolkit.py     ──bootstraps──▶ the device_ai import path + filename parsing
```

No code under `device_ai/` is added or modified. The scripts import the public
API surface only.

---

## 2. Prerequisites & Invocation

* **Python** ≥ 3.12 with the `device_ai` runtime dependencies installed
  (`pillow`, `numpy`, `pydantic`, `pydantic-settings`, `pyyaml`). These are the
  same dependencies the AI service already requires
  (`intelligence/device_ai/requirements.txt`).
* Run every tool **from the repository root**. Each script bootstraps the
  `device_ai` import path itself (via `scripts/_ecotrace_toolkit.py`), so no
  `PYTHONPATH` export or editable install is required:

  ```bash
  python scripts/validate_image_batch.py <batch_dir>
  ```

* All tools are **read-only** with respect to the dataset and the source
  folders, except `merge_collection_batches.py`, which **copies** (never moves
  or mutates) images into a staging directory you name.

### Configuration

Thresholds are **not** hardcoded. Every quality/size/dimension limit is read
from `device_ai.configs.settings.Settings`, which loads from environment
variables (or a local `.env`). The relevant knobs:

| Setting | Env var | Default | Used by |
| --- | --- | --- | --- |
| `min_image_dimension` | `MIN_IMAGE_DIMENSION` | 32 | validate, dashboard |
| `max_image_dimension` | `MAX_IMAGE_DIMENSION` | 12000 | validate, dashboard |
| `max_file_size` | `MAX_FILE_SIZE` | 10 MB | validate, dashboard |
| `blur_threshold` | `BLUR_THRESHOLD` | 100.0 | validate, dashboard |
| `brightness_dark_threshold` | `BRIGHTNESS_DARK_THRESHOLD` | 40.0 | validate, dashboard |
| `brightness_bright_threshold` | `BRIGHTNESS_BRIGHT_THRESHOLD` | 220.0 | validate, dashboard |
| `duplicate_hamming_threshold` | `DUPLICATE_HAMMING_THRESHOLD` | 5 | dashboard |

---

## 3. Filename Convention

The counting and validation tools infer an image's device class from its
filename, following the convention already documented in
`docs/ai/templates/image_inventory.csv`:

```
<class_name>_<source_tag>_<seq>.<ext>
```

* `class_name` — a **canonical taxonomy class** (code-owned, 19 classes, read
  from `components/data/components.yaml` via `load_taxonomy()`). Class names may
  themselves contain underscores (`crt_monitor`, `power_supply`); the parser
  matches the **longest** class-name prefix so `crt_monitor` is never mistaken
  for `monitor`.
* `source_tag` — an alphanumeric origin tag (`field`, `partnerX`, `web`, …).
* `seq` — a zero-padded numeric sequence (`000001`).
* `ext` — a supported image extension (`.jpg`, `.jpeg`, `.png`, `.webp`).

Parsing lives in `scripts/_ecotrace_toolkit.py` (`parse_collection_filename`,
`class_from_filename`) so all tools agree on one definition. This is the only
piece of collection logic the frozen pipeline does not already encode.

---

## 4. `validate_image_batch.py` (PART 1)

**Purpose:** Decide whether a single contributor batch is clean enough to
accept, before intake.

**Checks (and where each comes from):**

| Check | Source | Severity |
| --- | --- | --- |
| Filename convention | `_ecotrace_toolkit.parse_collection_filename` (new) | blocking |
| Unsupported extension | `ImageValidator` | blocking |
| Corrupted / undecodable | `ImageValidator` | blocking |
| Resolution too small / too large | `ImageValidator` | blocking |
| Invalid aspect ratio | `ImageValidator` | blocking |
| File too large | `ImageValidator` | blocking |
| Duplicate filename | `ImageValidator` | blocking |
| Duplicate content (exact SHA-256) | `ImageValidator` | blocking |
| Blur (variance of Laplacian) | `MetadataGenerator` / `evaluate_quality` | blocking¹ |
| Brightness (too dark / too bright) | `MetadataGenerator` / `evaluate_quality` | blocking¹ |

¹ Quality issues are blocking by default; pass `--allow-quality-warnings` to
downgrade blur/brightness/low-resolution to non-failing warnings.

**Usage:**

```bash
python scripts/validate_image_batch.py inbox/alice \
    --json reports/alice_validation.json

# quality issues become warnings instead of failures:
python scripts/validate_image_batch.py inbox/alice --allow-quality-warnings
```

**Inputs:** a directory of images.
**Outputs:** a human-readable summary on stdout (unless `--quiet`) and, with
`--json`, a full JSON report (`is_valid`, per-code counts, per-file issues).
**Exit codes:** `0` clean · `1` blocking issues found · `2` usage error. The
exit code makes it usable directly in a pre-commit hook or CI gate.

---

## 5. `dataset_progress.py` (PART 2)

**Purpose:** Show, per taxonomy class, how much data has been collected and how
far it is from the Dataset v1.0 targets.

**Reports:**

* **Per-class counts** — images bucketed by the class inferred from each
  filename (all 19 classes always listed, including empty ones).
* **Class imbalance** — the `max/min` ratio across non-empty classes.
* **Missing classes** — classes with zero images.
* **Progress vs targets** — counts against `min_target` / `recommended_target`
  / `ideal_target` read from `docs/ai/templates/collection_progress.csv` (or any
  CSV with the same columns via `--targets`).
* **Collection summary** — totals, unclassified count, and how many classes
  have met each target tier.

**Usage:**

```bash
python scripts/dataset_progress.py datasets/staging \
    --json reports/progress.json \
    --markdown reports/progress.md

# use a working copy of the targets sheet:
python scripts/dataset_progress.py datasets/staging \
    --targets ops/collection_progress.csv
```

**Inputs:** a directory of images; an optional targets CSV.
**Outputs:** Markdown on stdout (unless `--quiet`); JSON with `--json`; Markdown
file with `--markdown`. The taxonomy (ids, names, order) comes from
`load_taxonomy()` so the report can never drift from the code.
**Exit codes:** `0` success · `2` usage error.

---

## 6. `merge_collection_batches.py` (PART 3)

**Purpose:** Combine multiple contributor folders into one staging dataset
while preserving provenance.

**How it works:** For each batch it calls the frozen
`ProvenanceCollector.import_with_provenance` (which wraps `DatasetImporter`) to
copy and de-duplicate images and stamp a `ProvenanceRecord` (source, license,
contributor, collection date, SHA-256) on each. Each contributor's images land
under their **own namespace sub-folder** (`staging/<contributor>/…`), so
identical filenames from different contributors never collide. The per-batch
manifests are merged into one manifest keyed by the staging-relative path.

**Two ways to describe batches:**

```bash
# 1) repeatable --batch flags sharing bulk defaults
python scripts/merge_collection_batches.py datasets/staging \
    --batch alice=inbox/alice \
    --batch bob=inbox/bob \
    --source field_collection_2026 --license CC-BY-4.0 \
    --manifest datasets/staging/provenance_merged.json

# 2) a JSON spec with per-batch overrides
python scripts/merge_collection_batches.py datasets/staging \
    --spec ops/batches.json --manifest datasets/staging/provenance_merged.json
```

`batches.json` is a list of objects: `path` (required), `contributor`,
`source`, `license`, `collection_date`. Any omitted field falls back to the
bulk default.

**Inputs:** contributor source folders; optional spec JSON.
**Outputs:** a staging tree of copied images; with `--manifest`, a merged JSON
report (per-batch summaries plus the combined provenance records). Pass
`--no-deduplicate` to keep exact duplicates within a batch.
**Exit codes:** `0` success · `2` usage error (missing/invalid batch or spec).
Contributor ids are sanitised to a single safe path segment, so a malicious or
malformed id can never escape the staging directory.

---

## 7. `collection_dashboard.py` (PART 4)

**Purpose:** One page that summarises the whole collection effort.

**Sections:**

* **Totals** — total images, total size, missing-class count, imbalance ratio.
* **Class distribution** — per-class counts and progress toward the v1.0
  targets (reuses PART 2's `build_progress`).
* **Contributor statistics** — from the merged provenance manifest when supplied
  (`--manifest`), otherwise inferred from each image's staging namespace.
* **Validation failures** — grouped by issue code (reuses PART 1's
  `validate_batch`).
* **Duplicate statistics** — exact and near-duplicate pair counts (reuses the
  frozen `DuplicateDetector`).

**Usage:**

```bash
# Markdown (default) to a file
python scripts/collection_dashboard.py datasets/staging \
    --manifest datasets/staging/provenance_merged.json \
    --output reports/dashboard.md

# self-contained HTML
python scripts/collection_dashboard.py datasets/staging \
    --manifest datasets/staging/provenance_merged.json \
    --format html --output reports/dashboard.html
```

**Inputs:** a staging directory; optional merged manifest and targets CSV.
**Outputs:** Markdown (default) or HTML (`--format html`) to stdout or
`--output`; the raw data as JSON with `--json`. The HTML is self-contained (no
external assets) and HTML-escapes all interpolated values.
**Exit codes:** `0` success · `2` usage error.

---

## 8. Shared Module — `_ecotrace_toolkit.py`

Not a CLI tool. It centralises the small amount the four scripts share so no
logic is duplicated:

* **Import bootstrap** — prepends `intelligence/` to `sys.path` once, so the
  scripts can `import device_ai...` when run as plain files from the repo root.
* **Filename parsing** — `parse_collection_filename` and `class_from_filename`
  implement the §3 convention against the code-owned taxonomy.

---

## 9. Typical End-to-End Flow

```bash
# 1. Each contributor's batch is validated at intake.
python scripts/validate_image_batch.py inbox/alice --json reports/alice.json
python scripts/validate_image_batch.py inbox/bob   --json reports/bob.json

# 2. Clean batches are merged into staging with provenance preserved.
python scripts/merge_collection_batches.py datasets/staging \
    --batch alice=inbox/alice --batch bob=inbox/bob \
    --source field_collection_2026 --license CC-BY-4.0 \
    --manifest datasets/staging/provenance_merged.json

# 3. Track progress toward the per-class targets.
python scripts/dataset_progress.py datasets/staging --markdown reports/progress.md

# 4. Publish a dashboard for the team.
python scripts/collection_dashboard.py datasets/staging \
    --manifest datasets/staging/provenance_merged.json \
    --format html --output reports/dashboard.html
```

The merged staging set then feeds the existing frozen pipeline (annotation,
split, versioning, release) unchanged — see `device_collection_process.md`.

---

## 10. Guarantees & Non-Goals

**Guarantees**

* No `device_ai` module, API, schema, or model is modified by this toolkit.
* All thresholds are injected from `Settings`; nothing is hardcoded.
* Dataset images are never committed to git (only templates and docs are
  versioned); the tools operate on working directories outside version control.
* Contributor ids are sanitised before use as path segments.

**Non-goals**

* No image is downloaded, scraped, or generated.
* No model is trained, evaluated, or exported.
* No annotation, split, versioning, or release step is performed — those remain
  the responsibility of the frozen pipeline documented elsewhere.
