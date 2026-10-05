# Device Detection Annotation Pipeline

**Sprint:** P4.1.2 — Device Detection Dataset Collection & Annotation Pipeline
**Component:** Device Intelligence Engine (DIE) — YOLO Detector (milestone M1.4)
**Status:** Active
**Scope:** Dataset engineering only. This document defines the **collection,
annotation, review, QA, and versioning workflow** for the device-detection
dataset. It does **not** train any model, download any dataset, or fetch any
weights.

---

## 1. Purpose

This document is the operational runbook for turning **raw device images** into
a **versioned, quality-gated, YOLO-ready dataset**. It sits between two existing
specifications and reuses the pipeline end to end:

- Dataset structure and taxonomy — `docs/ai/device_detection_dataset.md` (P4.1.1)
- Training foundation that consumes releases — `docs/engineering/device_detection_training.md` (P4.1.1)

Every step below maps to an **already-implemented module** under
`intelligence/device_ai/dataset/`. Sprint P4.1.2 introduced **no new
architecture and no interface changes** — it added focused, composable
collaborators on top of the M1.2 pipeline:

| Concern | Module (P4.1.2 addition) | Reuses |
| --- | --- | --- |
| Provenance tracking | `dataset/provenance.py` (`ProvenanceCollector`) | `DatasetImporter`, `sha256_hash` |
| Structural image validation | `dataset/image_validation.py` (`ImageValidator`) | `MetadataGenerator`, `DuplicateDetector` |
| Canonical taxonomy accessor | `dataset/taxonomy.py` (`DeviceTaxonomy`, `load_taxonomy`) | `components/data/components.yaml` |
| Annotation statistics | `dataset/annotation_statistics.py` (`AnnotationStatisticsCalculator`) | `AnnotationValidator`, `parse_yolo_line`, `DeviceTaxonomy` |
| Enriched release manifest | `dataset/release.py` (`build_release`) | `DatasetVersion`, statistics, split |

The pre-existing M1.2 collaborators are reused unchanged:

| Concern | Module | Configuration source |
| --- | --- | --- |
| Directory layout | `dataset/layout.py` (`DatasetLayout`) | `configs/settings.py::DATASET_SUBDIRS` |
| Import / de-duplication | `dataset/importer.py` (`DatasetImporter`) | byte-level SHA-256 |
| Quality metrics | `dataset/metadata.py` (`MetadataGenerator`) | `blur_threshold`, `brightness_*_threshold`, `min/max_image_dimension` |
| Near-duplicate detection | `dataset/duplicates.py` (`DuplicateDetector`) | `duplicate_hamming_threshold` |
| Annotation validation | `dataset/validator.py` (`AnnotationValidator`) | YOLO 5-field txt |
| Aggregate statistics | `dataset/statistics.py` (`StatisticsCalculator`) | — |
| Splitting | `dataset/splitter.py` (`DatasetSplitter`) | `split_ratios`, `split_seed` |
| Versioning | `dataset/versioning.py` (`DatasetVersionManager`) | content-addressed `versions.json` |
| Orchestration facade | `dataset/service.py` (`DatasetService`) | injected `Settings` + clock |

> **Frozen interfaces.** The inference detector
> (`inference/yolo_detector.py::YOLODetector`) and the dataset value objects
> (`dataset/records.py`) are **frozen**. This runbook produces artifacts those
> interfaces consume; it does not change them.

---

## 2. Dataset Lifecycle (overview)

The dataset moves through five stages, each with an owner and an exit gate. A
stage may only advance when its gate passes.

```
   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
   │ 1. COLLECT  │──▶│ 2. VALIDATE │──▶│ 3. ANNOTATE │──▶│ 4. REVIEW+QA│──▶│ 5. RELEASE  │
   │ provenance  │   │ structural  │   │ label tools │   │ two-pass    │   │ versioned   │
   └─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘
        raw/            (gate A)          labels/           (gate B)         exports/ + version
```

| Stage | Owner | Exit gate |
| --- | --- | --- |
| 1. Collect | Data engineer | Every image has a provenance record (source, license, checksum). |
| 2. Validate | Data engineer | `ImageValidator` reports **zero blocking issues** (`is_valid == true`). |
| 3. Annotate | Annotator | Every retained image has a YOLO `.txt` label (may be empty for a true negative). |
| 4. Review + QA | Reviewer + QA lead | `AnnotationValidator` clean; QA sample meets the acceptance thresholds in §7. |
| 5. Release | Release owner | An immutable `DatasetVersion` + enriched release manifest is recorded. |

---

## 3. Stage 1 — Collection & Provenance (PART 1)

### 3.1 Goal

Ingest images from **one or more sources** into `datasets/raw/` while recording
**where each image came from**. Provenance closes the audit trail from a
released dataset version back to the original source — required for
data-governance and reproducibility.

### 3.2 Tracked fields

`ProvenanceRecord` (`dataset/provenance.py`) stamps every imported image with:

| Field | Meaning | Example |
| --- | --- | --- |
| `relative_path` | POSIX path relative to the dataset root | `laptop_field_000001.jpg` |
| `source` | Human-readable source identifier | `field_collection_2026` |
| `license` | License identifier | `CC-BY-4.0`, `proprietary`, `public_domain` |
| `contributor` | Person/organization that provided the image | `team_ecotrace` |
| `collection_date` | ISO-8601 UTC timestamp of collection | `2026-01-01T00:00:00+00:00` |
| `checksum` | SHA-256 of the file bytes at import time | `7c878e2d…` |

### 3.3 How to run

`ProvenanceCollector` **wraps** the existing `DatasetImporter` — it does not
re-implement copy or de-duplication. Bulk defaults apply to the whole batch;
`per_image_metadata` overrides individual images:

```python
from device_ai.configs.settings import Settings
from device_ai.dataset.provenance import ProvenanceCollector, manifest_to_dict

collector = ProvenanceCollector.from_settings(Settings())
summary, manifest = collector.import_with_provenance(
    source_root="/incoming/field_batch_2026_01",
    destination="datasets/raw",
    source="field_collection_2026",
    license_id="CC-BY-4.0",
    contributor="team_ecotrace",
    # collection_date omitted → falls back to the import timestamp
    per_image_metadata={
        "donated/tablet_0007.jpg": {"source": "partner_ewaste_india", "license": "proprietary"},
    },
)
# Persist the manifest alongside the dataset for the audit trail.
```

> `license` is the serialized field/JSON key; the function parameter is
> `license_id` because `license` shadows a Python builtin.

### 3.4 Source-specific guidance

| Source type | `source` convention | Licensing note |
| --- | --- | --- |
| Field collection (team photos) | `field_collection_<year>` | Team owns rights; record `CC-BY-4.0` or `proprietary`. |
| Partner / donor images | `partner_<name>` | Confirm redistribution rights **before** import; record the exact license. |
| Public/open datasets | `open_<dataset_name>` | Record the upstream license verbatim; never relabel a restrictive license as permissive. |

**Rule:** never import an image whose license permits neither use nor
redistribution for model training. When in doubt, exclude it.

---

## 4. Stage 2 — Structural Validation (PART 2)

### 4.1 Goal

Reject unusable images **before** any annotation effort is spent on them.
`ImageValidator` (`dataset/image_validation.py`) composes `MetadataGenerator`
(decode + quality) and `DuplicateDetector` (exact content match) and returns a
JSON-serialisable `ImageValidationReport`.

### 4.2 Checks and issue codes

| Check | Issue code | Trigger |
| --- | --- | --- |
| Unsupported extension | `UNSUPPORTED_EXTENSION` | Extension not in `ALLOWED_IMAGE_EXTENSIONS` (`.jpg/.jpeg/.png/.webp`). |
| Corrupt / unreadable | `CORRUPTED_IMAGE` | Image fails to decode. |
| Resolution too small | `RESOLUTION_TOO_SMALL` | `min(w, h) < min_image_dimension` (32 px). |
| Resolution too large | `RESOLUTION_TOO_LARGE` | `max(w, h) > max_image_dimension` (12000 px). |
| Invalid aspect ratio | `INVALID_ASPECT_RATIO` | `w/h` outside `[0.25, 4.0]` (injectable). |
| File too large | `FILE_TOO_LARGE` | `size_bytes > max_file_size` (10 MiB). |
| Duplicate filename | `DUPLICATE_FILENAME` | Same bare filename at more than one path. |
| Duplicate content | `DUPLICATE_HASH` | Exact SHA-256 match with an earlier image. |

Aspect-ratio bounds are **not** a settings field; they default to `0.25–4.0` and
are injectable via the constructor so `settings.py` stays untouched:

```python
from device_ai.dataset.image_validation import ImageValidator, image_validation_to_dict

report = ImageValidator(Settings()).validate(images_root=Path("datasets/raw"))
if not report.is_valid:
    payload = image_validation_to_dict(report)  # write to datasets/quality/
```

### 4.3 Gate A

- **Blocking (must fix before Stage 3):** `CORRUPTED_IMAGE`, `UNSUPPORTED_EXTENSION`,
  `DUPLICATE_HASH`, `DUPLICATE_FILENAME`.
- **Advisory (record, decide case-by-case):** `RESOLUTION_TOO_SMALL/LARGE`,
  `INVALID_ASPECT_RATIO`, `FILE_TOO_LARGE`. Small/odd images may still be usable
  for hard-negative mining; document the decision.

A worked example report lives at `intelligence/device_ai/docs/examples/dataset/validation_report.json`.

---

## 5. Stage 3 — Annotation Pipeline (PART 3)

### 5.1 Label format (the contract)

The **on-disk contract is YOLO** — one `.txt` per image, same stem, in
`datasets/labels/`. Each line is `class_id cx cy w h`:

- `class_id` — integer `0–18`, following the **exact ordering** in
  `docs/ai/device_detection_dataset.md` §3 (sourced from `components.yaml`).
- `cx cy w h` — box centre and size, **normalised to `[0, 1]`**.
- An **empty** label file is valid and means "true negative — no device".

`DeviceTaxonomy` (`dataset/taxonomy.py`) is the single source of truth for the
class list at annotation time:

```python
from device_ai.dataset.taxonomy import load_taxonomy

tax = load_taxonomy()            # version "1.0.0", 19 classes
tax.name_for(0)                  # "laptop"
tax.class_id_for("smartphone")  # 1
```

### 5.2 Supported annotation tools

Any tool may be used **so long as it exports YOLO format** matching the class-ID
contract above. Recommended tools and their round-trip procedure:

| Tool | Export procedure → YOLO | Import back into pipeline |
| --- | --- | --- |
| **Roboflow** | Project → *Generate* → *Export* → **YOLO v8/v11 TXT**. Download the `train/`, `valid/`, `test/` `labels/` folders. | Copy `.txt` files into `datasets/labels/` (flatten splits — the pipeline re-splits deterministically in Stage 5). |
| **CVAT** | Menu → *Export task dataset* → format **YOLO 1.1**. | Extract `obj_train_data/*.txt` into `datasets/labels/`. Verify `obj.names` order matches §3. |
| **Label Studio** | *Export* → **YOLO**. | Move `labels/*.txt` into `datasets/labels/`; drop the tool's `classes.txt` after confirming the order. |
| **Manual / scripted YOLO** | Author `.txt` directly. | Place in `datasets/labels/`. |

**Class-map alignment (critical).** Every tool maintains its own class list.
Before importing, confirm the tool's class ordering is **identical** to §3
(class 0 = `laptop` … class 18 = `battery`). A mismatched order silently
mislabels the entire dataset. Use `DeviceTaxonomy` to generate the authoritative
ordering when configuring a tool:

```python
names = [tax.name_for(i) for i in range(tax.num_classes)]  # ordered class list
```

### 5.3 Labeling standards

1. **One box per visible device instance.** Do not merge two laptops into one box.
2. **Tight boxes.** The box hugs the visible extent; include attached, integral
   parts (e.g. a laptop's screen + base) but exclude detached accessories.
3. **Occlusion.** Label a device visible ≥ ~40%; box the visible extent, do not
   guess the hidden part.
4. **Truncation.** Label devices cut off by the frame edge; box only what is in-frame.
5. **Ambiguous class.** Use the canonical class from §3 and its alias hints;
   never invent a class. If genuinely unclassifiable, exclude the image (log it).
6. **True negatives.** Images with no device get an **empty** `.txt` (not a
   missing file) so the reviewer can distinguish "no devices" from "not yet annotated".
7. **Normalisation.** Coordinates are normalised `[0, 1]`; `w, h > 0`.

### 5.4 Export back to a training framework

Framework-ready export is the **existing** `DatasetExporter`
(`dataset/exporter.py`), invoked via `DatasetService.export(...)`. Always pass
the ordered class names so exports carry real names, not `class_<id>`:

```python
service.export(export_format="yolo", records=records, class_names=names)
# → datasets/exports/yolo/ + data.yaml (names: from DeviceTaxonomy)
```

---

## 6. Stage 4a — Review Workflow

Review is a **two-pass, separation-of-duties** process. The annotator and the
reviewer are never the same person for a given image.

```
annotator ──▶ self-check ──▶ reviewer (pass 1) ──▶ [fixes] ──▶ reviewer (pass 2) ──▶ QA sample
```

1. **Annotator self-check.** Run `AnnotationValidator` locally; fix all
   structural errors before submitting.
2. **Reviewer pass 1 (structural).** Confirm `AnnotationValidator` is clean:
   - `MISSING_LABEL` — image with no label file (annotation gap).
   - `ORPHAN_LABEL` — label with no image.
   - `MALFORMED_LINE`, `UNREADABLE_LABEL` — file-level errors.
   - `NEGATIVE_CLASS_ID`, `CLASS_ID_OUT_OF_RANGE` — class-map violations.
   - `COORD_OUT_OF_RANGE`, `NON_POSITIVE_SIZE` — geometry violations.
3. **Reviewer pass 2 (semantic).** Spot-check that boxes are tight, correctly
   classed, and follow the labeling standards in §5.3. Reject the batch back to
   the annotator with specific file references if any standard is violated.
4. **Sign-off.** A batch advances to QA only after both passes are clean.

```python
report = service.validate_annotations(
    images_root=Path("datasets/raw"),
    labels_root=Path("datasets/labels"),
    num_classes=load_taxonomy().num_classes,   # 19 → enables range checks
)
assert report.is_valid, report.issues
```

---

## 7. Stage 4b — QA Process & Acceptance Metrics

QA is an **independent audit** on a random sample, using
`AnnotationStatisticsCalculator` (`dataset/annotation_statistics.py`) plus a
manual sample review.

### 7.1 Automated statistics (PART 4)

`AnnotationStatisticsCalculator.compute(images_root=…, labels_root=…)` returns:

| Metric | Field | Use in QA |
| --- | --- | --- |
| Class distribution | `class_distribution` (all 19 classes) | Detect class imbalance early. |
| Missing classes | `missing_classes` | Classes with **zero** instances — flag for targeted collection. |
| Bounding-box counts | `total_boxes` | Sanity-check against expected volume. |
| Bounding-box sizes | `bounding_box_stats` (min/max/mean w, h, area) | Catch systematic mis-scaling (e.g. all boxes tiny). |
| Annotation completeness | `annotation_completeness` (`[0, 1]`) | Fraction of images with a label file. |
| Images without labels | `images_without_labels` | Annotation gaps. |
| Orphan labels | `orphan_labels` | Labels without an image. |

### 7.2 Acceptance thresholds

A dataset version passes QA only when **all** of the following hold:

| Criterion | Threshold |
| --- | --- |
| Structural validity | `AnnotationValidator.is_valid == true` (zero issues). |
| Annotation completeness | `annotation_completeness == 1.0` (every retained image labelled — empty files count). |
| Orphan labels | `orphan_labels == ()` (none). |
| Class coverage | No class in `missing_classes` **unless** explicitly waived and logged for the release. |
| Manual sample accuracy | Reviewer agrees with ≥ **95%** of boxes in a random ≥ 5% sample (class + tightness). |

A worked statistics example lives at `intelligence/device_ai/docs/examples/dataset/statistics.json`;
per-image metadata at `intelligence/device_ai/docs/examples/dataset/metadata.json`.

---

## 8. Stage 5 — Versioning & Release (PART 5 & PART 6)

### 8.1 Deterministic splitting (PART 6)

Splitting reuses the **existing** `DatasetSplitter` (`dataset/splitter.py`) — no
new code. It is deterministic and reproducible:

- **Ratios:** `split_ratios` (default `0.70 / 0.20 / 0.10` for train/val/test),
  overridable per call.
- **Seed:** `split_seed` (default `42`). The same records + ratios + seed always
  produce the same assignment.

```python
split = service.split(records)              # writes datasets/splits/split.json
# or, with overrides:
split = service.split(records, ratios=(0.8, 0.1, 0.1), seed=7)
```

### 8.2 Immutable version record

`DatasetVersionManager` (`dataset/versioning.py`) records a **content-addressed**
snapshot — the version id is derived from the image content hashes, so identical
content yields the same version.

### 8.3 Enriched release manifest (PART 5)

`build_release(...)` (`dataset/release.py`) composes the version, image
statistics, annotation statistics, and split into a single manifest. Every
release **must** carry all six required elements:

| Required element | Source in manifest |
| --- | --- |
| Metadata | `version` block (created_at, note) |
| Statistics | `image_statistics` + `annotation_statistics` |
| Taxonomy version | `taxonomy_version` (from annotation statistics; `"1.0.0"`) |
| Creation timestamp | `version.created_at` (ISO-8601 UTC) |
| Checksums | `checksums.content_hash` + per-image `checksums.manifest` |
| Split information | `split` (seed, counts, assignments) — `null` only if omitted |

```python
from device_ai.dataset.release import build_release, release_to_dict

release = build_release(
    version=version,
    image_statistics=image_stats,
    annotation_statistics=annotation_stats,
    split=split,
)
payload = release_to_dict(release)   # archive alongside the exported dataset
```

The training foundation (`docs/engineering/device_detection_training.md`)
consumes exactly this release: the `data.yaml` from Stage 5 export + the pinned
version id give a fully reproducible training run.

---

## 9. End-to-End Example (composition)

```python
from datetime import UTC, datetime
from pathlib import Path

from device_ai.configs.settings import Settings
from device_ai.dataset.annotation_statistics import AnnotationStatisticsCalculator
from device_ai.dataset.duplicates import DuplicateDetector
from device_ai.dataset.image_validation import ImageValidator
from device_ai.dataset.metadata import MetadataGenerator
from device_ai.dataset.provenance import ProvenanceCollector
from device_ai.dataset.release import build_release, release_to_dict
from device_ai.dataset.splitter import DatasetSplitter
from device_ai.dataset.statistics import StatisticsCalculator
from device_ai.dataset.taxonomy import load_taxonomy
from device_ai.dataset.versioning import DatasetVersionManager

settings, tax = Settings(), load_taxonomy()
images, labels, meta = Path("datasets/raw"), Path("datasets/labels"), Path("datasets/metadata")

# 1. Collect with provenance.
ProvenanceCollector.from_settings(settings).import_with_provenance(
    "/incoming/batch", images, source="field_collection_2026", license_id="CC-BY-4.0"
)
# 2. Structurally validate (gate A).
assert ImageValidator(settings).validate(images_root=images).is_valid
# 3–4. Annotate externally, then audit.
records = MetadataGenerator.from_settings(settings).analyze_directory(images)
image_stats = StatisticsCalculator().compute(
    records, duplicates=DuplicateDetector.from_settings(settings).detect(records)
)
ann_stats = AnnotationStatisticsCalculator(tax).compute(images_root=images, labels_root=labels)
# 5. Split, version, release.
split = DatasetSplitter.from_settings(settings).split_records(records)
version = DatasetVersionManager(meta).create_version(records, created_at=datetime.now(UTC))
release = release_to_dict(build_release(
    version=version, image_statistics=image_stats,
    annotation_statistics=ann_stats, split=split,
))
```

---

## 10. Roles & Responsibilities

| Role | Owns | Tooling |
| --- | --- | --- |
| Data engineer | Stages 1–2: ingest, provenance, structural validation. | `ProvenanceCollector`, `ImageValidator` |
| Annotator | Stage 3: labels per §5.3. | Roboflow / CVAT / Label Studio → YOLO |
| Reviewer | Stage 4a: two-pass review. | `AnnotationValidator` |
| QA lead | Stage 4b: independent audit + acceptance. | `AnnotationStatisticsCalculator` |
| Release owner | Stage 5: split, version, release manifest. | `DatasetSplitter`, `DatasetVersionManager`, `build_release` |

---

## 11. Reference Artifacts

| Artifact | Path |
| --- | --- |
| Example per-image metadata | `intelligence/device_ai/docs/examples/dataset/metadata.json` |
| Example aggregate statistics | `intelligence/device_ai/docs/examples/dataset/statistics.json` |
| Example structural validation report | `intelligence/device_ai/docs/examples/dataset/validation_report.json` |
| Example generator (deterministic) | `intelligence/device_ai/scripts/gen_dataset_examples.py` |
| Dataset structure & taxonomy spec | `docs/ai/device_detection_dataset.md` |
| Training foundation spec | `docs/engineering/device_detection_training.md` |

> **Out of scope for P4.1.2:** no model is trained, no weights or datasets are
> downloaded, no inference/OpenCLIP/OCR is implemented, and no API or detector
> interface is modified. This runbook prepares data; training happens later.
