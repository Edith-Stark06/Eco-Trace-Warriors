# Device Collection Process — Engineering Reference

**Sprint:** P4.1.5 — Production Dataset Collection Workflow (PART 6)
**Component:** Device Intelligence Engine (DIE) — YOLO Detector (milestone M1.4)
**Status:** Active
**Related:** `08_AI.md`, `device_dataset_acquisition.md`,
`device_detection_annotation.md`, `device_detection_deployment.md`
**Scope:** The **engineering-facing** view of the collection workflow — how the
operational process (PARTs 1–5) maps onto the frozen P4.1.2 dataset code, which
modules run at each step, and what a data engineer executes at intake. It
downloads nothing, trains nothing, and changes no code, schema, or interface.

---

## 1. Where This Fits

The AI-facing docs (`docs/ai/`) tell contributors and reviewers **what** to do.
This document tells the engineer **which frozen code** realises each step, so the
process stays grounded in the real pipeline rather than aspiration.

```
 docs/ai/  (people)                 code (frozen P4.1.2)                 docs/engineering/  (this)
 ─────────────────────              ──────────────────────               ───────────────────────
 collection_workflow  ─────────▶    dataset/importer.py            ◀────  process mapping (§3)
 photo_guidelines     ─────────▶    dataset/quality (ImageValidator)◀────  Gate A (§4)
 dataset_review       ─────────▶    dataset/annotation validators  ◀────  Gate B (§5)
 readiness_checklist  ─────────▶    dataset/{split,version,release} ◀────  release (§6)
```

No code is added or modified in P4.1.5. The modules below already exist and are
**reused unchanged**.

---

## 2. Reused Modules (unchanged, frozen)

| Concern | Module / entry point | Role in collection |
| --- | --- | --- |
| Taxonomy | `dataset/taxonomy.py::load_taxonomy()` | Authoritative 19 classes + ids (from `components/data/components.yaml`). |
| Provenance | `dataset/provenance.py` (`ProvenanceRecord`, `ProvenanceManifest`, `ProvenanceCollector`) | Records source/licence/contributor/date/checksum at import. |
| Import | `dataset/importer.py` (`DatasetImporter.import_directory`) | Copies bytes, **preserves relative path/filename**, returns imported paths. |
| Image validation (Gate A) | `ImageValidator` | Dimension/size/format/blur/brightness checks. |
| Metadata | `MetadataGenerator` | Per-image metadata. |
| De-duplication | `DuplicateDetector` | Perceptual-hash Hamming (`≤ 5` ⇒ duplicate). |
| Annotation validation (Gate B) | `AnnotationValidator` | Completeness, orphan labels, missing classes. |
| Annotation stats | `AnnotationStatisticsCalculator` | Per-class/box counts, distribution. |
| Split | `DatasetSplitter` | 70/20/10, seed 42. |
| Version / release | `DatasetVersionManager`, `build_release` | Immutable, content-addressed release. |
| Service facade | `DatasetService` | Orchestrates the above. |

All settings come from `configs/settings.py`; see §7.

---

## 3. Process ↔ Code Mapping

| Phase (PART 1) | Actor | Engineering action / module |
| --- | --- | --- |
| P0 Onboard | Collection lead | Register in `contributors.csv`; assign classes from `load_taxonomy()`. No code run. |
| P1 Capture | Contributor | Photos per `device_photo_guidelines.md`. No code run. |
| P2 Stage & submit | Contributor | Rename `<class>_<source>_<seq>.<ext>`; log in `image_inventory.csv`; upload batch folder. No code run. |
| P3 Intake | **Data engineer** | `ProvenanceCollector` import → `ImageValidator` Gate A → `DuplicateDetector` → stage into `datasets/raw/`. **This section.** |
| Annotate | Annotator | External tool; labels land beside images (see `device_detection_annotation.md`). |
| Review | Reviewers | `AnnotationValidator` + `AnnotationStatisticsCalculator` (Gate B) + human review (PART 4). |
| Release | QA lead | Readiness checklist (PART 5) → `DatasetSplitter` → `build_release` / `DatasetVersionManager`. |

---

## 4. Intake Step (data engineer runbook)

The naming convention exists **because the importer does not rename**. Confirmed
behaviour in `dataset/importer.py`:

```python
source_rel = relative_path(path, source_root)
out_path = destination / source_rel     # preserves the source's relative path + filename
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_bytes(data)
imported.append(relative_path(out_path, destination))
```

So the filename a contributor assigns at capture is the filename on disk after
import, and it is the join key across provenance, inventory, and labels.

**Intake sequence (per batch):**

1. **Verify manifest** — the batch's `image_inventory.csv` slice matches the
   files present (filename, class, licence, contributor).
2. **Import with provenance** — `ProvenanceCollector.import_with_provenance(...)`
   passing source/licence/contributor/collection_date from the manifest; it
   computes SHA-256 checksums and builds the `ProvenanceManifest`.
3. **Gate A** — run `ImageValidator` over the imported batch; retained set = pass
   set plus explicitly `difficult`-flagged exceptions.
4. **De-duplicate** — `DuplicateDetector`; drop Hamming `≤ 5` pairs; record
   `duplicates_dropped`.
5. **Update counters** — write accepted/rejected/imported/gate_a_passed/
   duplicates_dropped into `collection_progress.csv`; set `intake_status` in
   `image_inventory.csv`.
6. **Notify** — return reject reasons to the contributor for re-capture.

Images are **staged into the existing dataset layout** under the repo's dataset
root; no new top-level folders are introduced.

---

## 5. Quality Gates (engineering view)

| Gate | When | Module | Pass condition (from `settings.py`) |
| --- | --- | --- | --- |
| **A — image** | intake, pre-annotation | `ImageValidator` | short side `≥ 32`, long `≤ 12000`, `≤ 10 MiB`, format `{jpg,jpeg,png,webp}`, blur var-Laplacian `≥ 100.0`, luminance `[40, 220]` |
| **B — annotation** | post-annotation, pre-release | `AnnotationValidator` + `AnnotationStatisticsCalculator` + human review | `annotation_completeness == 1.0`, `orphan_labels == ()`, no unwaived `missing_classes`, ≥95% agreement on ≥5% sample |

Gate B's human half is the review workflow (PART 4); its automated half is the
validators. Both must pass — the readiness checklist (PART 5) is the aggregate.

---

## 6. Release Step (engineering)

Once the readiness checklist passes:

1. `DatasetSplitter` — deterministic 70/20/10 split, `split_seed = 42`; verify
   every class present in each split (no leakage — cross-split dedup already done
   in §4).
2. `build_release` / `DatasetVersionManager` — produce an **immutable,
   content-addressed** dataset version with a per-image checksum manifest.
3. Fill `docs/ai/templates/dataset_metadata.json` with real totals, distribution,
   sources, quality-gate report paths, and checksums (no placeholders).

The released dataset is the **input to training**, which remains **deferred and
out of scope** (`device_detection_deployment.md` §9). P4.1.5 stops at a
release-ready dataset definition; it does not build or train one.

---

## 7. Configuration Reference

All thresholds are read from `configs/settings.py` (do not hardcode elsewhere):

```
min_image_dimension        = 32        # px, short side floor
max_image_dimension        = 12000     # px, long side ceiling
max_file_size              = 10 * 1024 * 1024   # 10 MiB
blur_threshold             = 100.0     # variance-of-Laplacian
brightness_dark_threshold  = 40.0      # mean luminance floor
brightness_bright_threshold= 220.0     # mean luminance ceiling
duplicate_hamming_threshold= 5         # perceptual-hash distance
split_ratios               = (0.7, 0.2, 0.1)
split_seed                 = 42
```

---

## 8. Constraints

- **Frozen:** architecture, training pipeline, dataset pipeline, all interfaces
  (`Detector`, Prediction API, dataset value objects in `records.py`).
- **No new top-level folders** (CLAUDE.md); images stage into the existing
  dataset layout.
- **No secrets** — intake locations and credentials come from environment /
  configuration, never committed.
- **Images are not committed to git** — only templates and docs are versioned.
- **Out of scope (P4.1.5):** no training, YOLO, OpenCLIP, OCR, or model/dataset
  downloads.

---

## 9. Related Documents

| Document | Role |
| --- | --- |
| `docs/engineering/08_AI.md` | DIE architecture overview |
| `docs/engineering/device_dataset_acquisition.md` | Acquisition strategy, targets, gates (P4.1.4) |
| `docs/engineering/device_detection_annotation.md` | Annotation tooling/format |
| `docs/engineering/device_detection_deployment.md` | Training/deployment runbook (training deferred) |
| `docs/ai/device_collection_workflow.md` | Contributor workflow (PART 1) |
| `docs/ai/dataset_review_workflow.md` | Human review (PART 4) |
| `docs/ai/dataset_readiness_checklist.md` | Release gate (PART 5) |
