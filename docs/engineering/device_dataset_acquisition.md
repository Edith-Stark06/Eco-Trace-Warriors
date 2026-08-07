# Device Dataset Acquisition — Dataset v1.0

**Sprint:** P4.1.4 — Production Dataset Acquisition
**Component:** Device Intelligence Engine (DIE) — YOLO Detector (milestone M1.4)
**Status:** Active
**Scope:** Acquisition, organisation, and quality **planning** for Dataset v1.0.
This document defines the collection workflow, quality assurance, dataset
lifecycle, and release process. It does **not** download datasets, train a model,
fetch weights, implement inference, or modify any API or interface.

---

## 1. Purpose

This is the engineering runbook that turns the source catalogue
(`docs/ai/device_detection_sources.md`) into a **versioned, quality-gated,
YOLO-ready Dataset v1.0**. It defines *how* images are collected, *what* targets
they must hit, *how* they are annotated and quality-gated, and *how* the release
is produced — reusing the existing P4.1.2 dataset pipeline end to end.

Every executable step maps to an **already-implemented module** under
`intelligence/device_ai/dataset/`; this sprint adds **no new code and no
interface changes** — it is a planning and operational specification. The
annotation mechanics live in the companion runbook
(`docs/engineering/device_detection_annotation.md`); this document owns the
acquisition strategy, targets, and lifecycle around it.

| Concern | Reused module (no change) |
| --- | --- |
| Provenance-tracked import | `dataset/provenance.py` (`ProvenanceCollector`) |
| Structural validation | `dataset/image_validation.py` (`ImageValidator`) |
| Quality metrics | `dataset/metadata.py` (`MetadataGenerator`) |
| Duplicate detection | `dataset/duplicates.py` (`DuplicateDetector`) |
| Annotation validation | `dataset/validator.py` (`AnnotationValidator`) |
| Annotation statistics | `dataset/annotation_statistics.py` (`AnnotationStatisticsCalculator`) |
| Canonical taxonomy | `dataset/taxonomy.py` (`load_taxonomy`) |
| Deterministic splitting | `dataset/splitter.py` (`DatasetSplitter`) |
| Versioning | `dataset/versioning.py` (`DatasetVersionManager`) |
| Release manifest | `dataset/release.py` (`build_release`) |
| Split-aware training manifest | `training/detector/data_manifest.py` (P4.1.3) |

> **The taxonomy is code-owned.** The 19 classes and their IDs come from
> `components/data/components.yaml`. Do not hardcode or reorder them anywhere in
> the acquisition process — read them from `load_taxonomy()`.

---

## 2. Collection Strategy (PART 2)

Dataset v1.0 is assembled from six source families, blended so no single family
dominates a class. The blend is chosen to maximise **visual diversity** and
**Indian e-waste realism** while keeping every image **licence-clean**.

### 2.1 Source families and their role

| Family | Role in v1.0 | Governance |
| --- | --- | --- |
| **Public annotated sets** (Open Images, Objects365, LVIS, COCO) | Backbone for well-served classes; reuse existing boxes where licence-clean. | CC-BY/Apache-2.0 — verify per image; re-map labels to the 19-class taxonomy. |
| **Open Images** (called out explicitly) | Largest single source of boxed instances for common classes. | CC-BY 4.0 images; keep author/source for attribution. |
| **Manufacturer images** | **Reference only** (what a class looks like). Import **only** with a signed licence. | Copyrighted by default — excluded from import unless cleared. |
| **Community datasets** (Roboflow Universe, Kaggle) | E-waste framing and rarer classes. | Licence **varies per dataset** — verify and record before import. |
| **Self-collected images** | Rare/hazardous/under-served classes; Indian context; damaged/opened units. | Team-owned (`CC-BY-4.0`/`proprietary`); consent for any incidental PII. |
| **Synthetic augmentation** | Class balancing and hard negatives for under-served classes. | Derived; inherits the source licence; flagged `synthetic` in provenance. |

### 2.2 Blend policy

- **Cap any single public dataset at ~50%** of a class's images, so the model
  does not overfit one dataset's capture style.
- **Under-served classes** (server, crt_monitor, power_supply, cable,
  game_console, battery — see sources §5) lead with **self-collection +
  community + synthetic**; public sets are a top-up, not the base.
- **Synthetic images are capped at ~20%** of any class and are always flagged so
  a synthetic-free evaluation slice can be reconstructed.
- **Indian-context images** (self-collected from local e-waste streams) are
  prioritised to reduce geographic/domain bias.

### 2.3 Collection workflow (end to end)

```
   plan ──▶ acquire ──▶ import+provenance ──▶ validate ──▶ annotate ──▶ review+QA ──▶ split ──▶ version+release
  (targets) (per source)  (ProvenanceCollector) (ImageValidator) (external tool)  (two-pass) (Splitter) (build_release)
```

1. **Plan** per-class targets (§4) and pick sources per class (sources §4).
2. **Acquire** images per source, honouring the licence policy; log each batch
   in `collection_log.csv`.
3. **Import with provenance** via `ProvenanceCollector` (source, licence,
   contributor, date, checksum) into `datasets/raw/`.
4. **Validate** structurally with `ImageValidator` (Gate A, §5).
5. **Annotate** externally in YOLO format (annotation runbook §5).
6. **Review + QA** two-pass (annotation runbook §6–7; Gate B, §5).
7. **Split** deterministically with `DatasetSplitter` (§4.3).
8. **Version + release** with `DatasetVersionManager` + `build_release`.

---

## 3. Dataset Targets (PART 3)

### 3.1 Per-class image targets

Targets are per **class** (a single image may contribute to more than one class
when multiple devices are present). **Minimum** is the floor for a class to ship
in v1.0; **recommended** is the planning goal; **ideal** is the stretch target
for a well-balanced detector. Under-served classes (sources §5) carry the same
targets but rely more on self-collection + synthetic to reach them.

| ID | Class | Minimum | Recommended | Ideal | Val % | Test % |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 0 | `laptop` | 300 | 600 | 1000 | 20% | 10% |
| 1 | `smartphone` | 300 | 600 | 1000 | 20% | 10% |
| 2 | `tablet` | 200 | 400 | 700 | 20% | 10% |
| 3 | `desktop` | 200 | 400 | 700 | 20% | 10% |
| 4 | `server` | 150 | 300 | 500 | 20% | 10% |
| 5 | `monitor` | 250 | 500 | 800 | 20% | 10% |
| 6 | `crt_monitor` | 150 | 300 | 500 | 20% | 10% |
| 7 | `television` | 250 | 500 | 800 | 20% | 10% |
| 8 | `printer` | 200 | 400 | 700 | 20% | 10% |
| 9 | `keyboard` | 200 | 400 | 700 | 20% | 10% |
| 10 | `mouse` | 200 | 400 | 700 | 20% | 10% |
| 11 | `router` | 200 | 400 | 700 | 20% | 10% |
| 12 | `power_supply` | 200 | 400 | 700 | 20% | 10% |
| 13 | `cable` | 200 | 400 | 700 | 20% | 10% |
| 14 | `camera` | 200 | 400 | 700 | 20% | 10% |
| 15 | `game_console` | 150 | 300 | 500 | 20% | 10% |
| 16 | `smartwatch` | 200 | 400 | 700 | 20% | 10% |
| 17 | `headphones` | 200 | 400 | 700 | 20% | 10% |
| 18 | `battery` | 200 | 400 | 700 | 20% | 10% |
| — | **Dataset total** | **~3,950** | **~7,900** | **~13,300** | 20% | 10% |

> Totals are the sum of per-class minima/recommended/ideal and are a **planning
> aid**, not a hard budget; shared images make the realised image count lower
> than the summed class count.

### 3.2 Split policy

- **Train / Validation / Test = 70% / 20% / 10%**, matching the code default
  `split_ratios = (0.7, 0.2, 0.1)` in `configs/settings.py` and the deterministic
  `split_seed = 42`.
- The split is produced by the **existing** `DatasetSplitter` — do not split by
  hand. The same records + ratios + seed always reproduce the same assignment.
- The split is **class-aware in intent**: every class should retain ≥ 1 instance
  in each of val and test. Classes near the minimum target are the risk; the
  acquisition checklist tracks per-class split coverage before release.
- **No leakage:** near-duplicates (`DuplicateDetector`) must be resolved *before*
  splitting so the same physical item does not straddle train and test.

### 3.3 Balance target

- Aim for **no class below its minimum** and **no class above ~3× the smallest
  class's realised count**, to bound imbalance.
- Track imbalance with `AnnotationStatisticsCalculator.class_distribution` and
  `missing_classes`; a class in `missing_classes` blocks release unless explicitly
  waived and logged (§5, §6).

---

## 4. Annotation Guidelines (PART 4)

These **expand** the labeling standards in the annotation runbook
(`docs/engineering/device_detection_annotation.md` §5.3). The on-disk contract is
unchanged: one YOLO `.txt` per image (same stem, in `datasets/labels/`), each
line `class_id cx cy w h`, normalised `[0, 1]`, class IDs `0–18` in taxonomy
order; an **empty** file means "true negative — no device".

### 4.1 Occlusion
- Label a device when **≥ ~40% is visible**; box only the **visible extent**, do
  not guess the hidden part.
- When two devices overlap, draw **separate tight boxes** for each — never one
  merged box.
- If occlusion drops visibility below ~40%, **skip that instance** (do not box);
  it becomes background.

### 4.2 Multiple objects
- **One box per visible instance**, even for many instances of the same class
  (e.g. a bin of 20 phones → up to 20 boxes as far as they are individually
  distinguishable).
- When instances are packed and individually indistinguishable (a dense pile),
  box the clearly separable units and leave the ambiguous mass unboxed; log the
  image as `difficult` (§4.7).
- Mixed-class scenes are encouraged — they teach co-occurrence (laptop + charger
  + mouse). Label **every** in-taxonomy device present.

### 4.3 Partial visibility
- Devices partially behind another object follow the occlusion rule (§4.1): box
  the visible extent if ≥ ~40% visible.
- Do **not** extrapolate a box beyond the pixels you can see.

### 4.4 Truncated devices (frame edge)
- Label devices cut off by the **image border**; box only the in-frame portion.
- A device with < ~40% of its body in-frame may be skipped; if boxed, keep the
  box tight to the visible pixels and never past the image edge.

### 4.5 Tiny objects
- Small objects (mouse, battery, cable, earbuds, coin cells) are in scope even at
  small pixel sizes, but a box must be **≥ 8×8 px** and visually identifiable.
- Below that, skip the instance (it adds label noise). Prefer collecting a
  **closer** image of tiny classes over boxing an unidentifiable speck.
- `w, h > 0` always; zero-area boxes are rejected by `AnnotationValidator`.

### 4.6 Difficult images
- Motion-blurred, low-light, reflective-screen, or cluttered images are **kept**
  when the target device is still identifiable — they improve robustness.
- Flag them `difficult` in `annotation_progress.csv` so QA can sample them
  separately and so a "clean-only" evaluation slice can be reconstructed.
- If the target device is **not** confidently identifiable, exclude the image and
  log the reason (do not guess a class).

### 4.7 Negative samples (true negatives)
- Images with **no in-taxonomy device** get an **empty** `.txt` (not a missing
  file). This is how the pipeline distinguishes "no devices" from "not yet
  annotated" (annotation runbook §5.3, `annotation_completeness`).
- Target **~5–10% negatives** across the dataset: backgrounds, non-electronic
  clutter, and **hard negatives** (objects that look like a class but are not — a
  book resembling a tablet, a lunchbox resembling a console).
- Hard negatives are the highest-value negatives; source or synthesise them for
  classes prone to false positives (tablet, monitor/TV, battery).

### 4.8 Ambiguous class
- Use the canonical class and its alias hints from `components.yaml`
  (sources §2). Never invent a class.
- Monitor vs television and tablet vs smartphone are the common confusions —
  resolve by the aliases and by physical size cues; when genuinely
  unclassifiable, exclude the image and log it.

---

## 5. Quality Gates (PART 5)

Two hard gates bracket annotation; both reuse existing pipeline checks. **All**
criteria in a gate must pass before the stage advances.

### 5.1 Gate A — image quality (before annotation)

Enforced by `ImageValidator` (`dataset/image_validation.py`) + `MetadataGenerator`
+ `DuplicateDetector`. Thresholds are the configured settings (do not hardcode
new ones):

| Criterion | Rule | Source of the threshold |
| --- | --- | --- |
| **Minimum resolution** | `min(w, h) ≥ 32 px` | `min_image_dimension = 32` |
| **Maximum resolution** | `max(w, h) ≤ 12000 px` | `max_image_dimension = 12000` |
| **Maximum file size** | `size ≤ 10 MiB` | `max_file_size = 10*1024*1024` |
| **Supported format** | `.jpg/.jpeg/.png/.webp` | `ALLOWED_IMAGE_EXTENSIONS` |
| **Not corrupt** | image decodes | `ImageValidator` |
| **Maximum blur** | variance-of-Laplacian **≥ 100.0** (below ⇒ flagged blurry) | `blur_threshold = 100.0` |
| **Brightness window** | mean luminance in **[40, 220]** (outside ⇒ dark/bright) | `brightness_dark_threshold = 40`, `brightness_bright_threshold = 220` |
| **Exact duplicates** | zero `DUPLICATE_HASH` / `DUPLICATE_FILENAME` | `DuplicateDetector` (SHA-256) |
| **Near-duplicate threshold** | perceptual-hash Hamming distance **> 5** to keep as distinct | `duplicate_hamming_threshold = 5` |

- **Blocking** (must fix/exclude before annotation): corrupt, unsupported
  extension, exact duplicate, duplicate filename.
- **Advisory** (record + decide): resolution too small/large, invalid aspect
  ratio, file too large, blurry, too dark/bright. Blurry/low-light images may be
  intentionally kept as `difficult` (§4.6) — the decision is logged.

### 5.2 Gate B — annotation quality (before release)

Enforced by `AnnotationValidator` + `AnnotationStatisticsCalculator` + manual
sample review (annotation runbook §6–7):

| Criterion | Rule |
| --- | --- |
| **Structural validity** | `AnnotationValidator.is_valid == true` (no malformed/geometry/class-range errors) |
| **Annotation completeness** | `annotation_completeness == 1.0` (every retained image labelled; empty files count) |
| **No orphan labels** | `orphan_labels == ()` |
| **Class coverage** | no class in `missing_classes` unless waived + logged |
| **Class balance** | no class below its §3.1 minimum; imbalance within §3.3 bound |
| **Annotation review** | reviewer agrees with **≥ 95%** of boxes in a random **≥ 5%** sample (class + tightness) |
| **Duplicate threshold** | near-duplicates resolved (Hamming > 5) **before** split, so none straddle train/test |

### 5.3 Gate outcomes

- **Pass** → advance to split/version/release.
- **Fail** → return to the owning stage with specific file references (logged in
  `review_log.csv`); never waive a blocking criterion silently.

---

## 6. Quality Assurance

QA is an **independent audit**, run by someone other than the annotator, on top
of the automated gates:

1. **Automated sweep.** Run `ImageValidator` (Gate A) and, after annotation,
   `AnnotationValidator` + `AnnotationStatisticsCalculator` (Gate B). Archive the
   JSON reports alongside the dataset.
2. **Sample review.** Draw a random **≥ 5%** sample stratified by class; the
   reviewer confirms class correctness and box tightness. Acceptance is **≥ 95%**
   agreement (Gate B).
3. **Balance & coverage review.** Check `class_distribution` and `missing_classes`
   against §3 targets; flag under-target classes for more collection.
4. **Difficult-slice review.** Separately sample `difficult`-flagged images so
   their higher error rate does not hide in the aggregate.
5. **Provenance audit.** Spot-check that every image traces back to a
   `ProvenanceRecord` with a permissive licence (sources §6).

Every QA finding is recorded in `review_log.csv`; a batch advances only when all
Gate B criteria pass.

---

## 7. Dataset Lifecycle

The dataset moves through the same five gated stages as the annotation runbook,
extended with the acquisition-specific planning front:

```
 0. PLAN ─▶ 1. COLLECT ─▶ 2. VALIDATE ─▶ 3. ANNOTATE ─▶ 4. REVIEW+QA ─▶ 5. RELEASE
 targets    provenance     Gate A          YOLO labels    Gate B          version + manifest
```

| Stage | Owner | Exit gate |
| --- | --- | --- |
| 0. Plan | Dataset lead | Per-class targets + source plan agreed (§3, sources §4). |
| 1. Collect | Data engineer | Every image has a `ProvenanceRecord`; batch in `collection_log.csv`. |
| 2. Validate | Data engineer | `ImageValidator` — zero **blocking** issues (Gate A). |
| 3. Annotate | Annotator | Every retained image has a YOLO `.txt` (empty allowed). |
| 4. Review + QA | Reviewer + QA lead | `AnnotationValidator` clean; sample ≥ 95%; balance met (Gate B). |
| 5. Release | Release owner | Immutable `DatasetVersion` + enriched release manifest recorded. |

A stage advances only when its gate passes. Regressions (e.g. a class falls under
minimum after de-duplication) send the dataset back to Stage 1 for top-up.

---

## 8. Release Process

Dataset v1.0 is released with the **existing** versioning + release pipeline — no
new code:

1. **Resolve duplicates** (`DuplicateDetector`, Hamming > 5) so no near-duplicate
   straddles the split.
2. **Split** with `DatasetSplitter.from_settings(settings)` (70/20/10, seed 42).
3. **Version** with `DatasetVersionManager.create_version(records, created_at=…)`
   — a **content-addressed** snapshot: identical content yields the same version.
4. **Build the release manifest** with `build_release(version, image_statistics,
   annotation_statistics, split)`. Every release carries the six required
   elements: metadata, statistics, taxonomy version, creation timestamp,
   checksums, split.
5. **Fill `dataset_metadata.json`** (template, PART 7) as the human-facing summary
   of the release: counts, per-class distribution, split sizes, source blend,
   licences, and the pinned taxonomy + dataset version.
6. **Hand off to training.** The release feeds `build_training_manifest`
   (P4.1.3, `training/detector/data_manifest.py`) which emits the split-aware
   `data.yaml` the YOLO trainer consumes — closing the loop to
   `docs/engineering/device_detection_deployment.md`. **Training itself is out of
   scope for this sprint.**

```python
# Release composition (reusing the P4.1.2 pipeline — illustrative, not run here).
from device_ai.dataset.splitter import DatasetSplitter
from device_ai.dataset.versioning import DatasetVersionManager
from device_ai.dataset.release import build_release, release_to_dict

split = DatasetSplitter.from_settings(settings).split_records(records)
version = DatasetVersionManager(meta_dir).create_version(records, created_at=now)
release = release_to_dict(build_release(
    version=version,
    image_statistics=image_stats,
    annotation_statistics=annotation_stats,
    split=split,
))  # archive alongside dataset_metadata.json
```

### 8.1 Versioning & immutability

- A `DatasetVersion` is **immutable and content-addressed**; re-releasing the
  same content reproduces the same id.
- v1.0 pins the **taxonomy version** (`1.0.0`) so a trained model's
  `dataset_version` traces back to an exact class list.
- Corrections after release create a **new** version (v1.0.1 / v1.1) — never edit
  a released version in place (mirrors the model-registry immutability in
  deployment §5).

---

## 9. Metadata & Templates (PART 7)

The acquisition process is tracked with four templates (data only, no images).
Their location and schema:

| Template | Path | Role |
| --- | --- | --- |
| `dataset_metadata.json` | `docs/ai/templates/dataset_metadata.json` | Human-facing release summary (counts, splits, sources, licences, versions). |
| `collection_log.csv` | `docs/ai/templates/collection_log.csv` | One row per acquired batch (source, licence, class, counts, dates). |
| `annotation_progress.csv` | `docs/ai/templates/annotation_progress.csv` | Per-class annotation status against targets. |
| `review_log.csv` | `docs/ai/templates/review_log.csv` | QA/review findings and gate outcomes. |

These templates are the operational backbone of the acquisition checklist
(`docs/ai/device_collection_checklist.md`).

---

## 10. Roles & Responsibilities

| Role | Owns | Tooling |
| --- | --- | --- |
| Dataset lead | Stage 0: targets + source plan. | Sources catalogue, this runbook |
| Data engineer | Stages 1–2: acquire, provenance, Gate A. | `ProvenanceCollector`, `ImageValidator` |
| Annotator | Stage 3: labels per §4. | Roboflow / CVAT / Label Studio → YOLO |
| Reviewer | Stage 4a: two-pass review. | `AnnotationValidator` |
| QA lead | Stage 4b: independent audit + Gate B. | `AnnotationStatisticsCalculator` |
| Release owner | Stage 5: split, version, release manifest. | `DatasetSplitter`, `DatasetVersionManager`, `build_release` |

---

## 11. Related Documents

| Document | Role |
| --- | --- |
| `docs/ai/device_detection_sources.md` | Per-class source catalogue (P4.1.4 PART 1) |
| `docs/ai/device_collection_checklist.md` | Operational checklist (P4.1.4 PART 6) |
| `docs/ai/templates/` | Metadata templates (P4.1.4 PART 7) |
| `docs/engineering/device_detection_annotation.md` | Annotation/review/QA/versioning mechanics (P4.1.2) |
| `docs/engineering/device_detection_deployment.md` | Downstream training & deployment (P4.1.3) |
| `intelligence/device_ai/components/data/components.yaml` | Canonical taxonomy source of truth |

> **Out of scope for P4.1.4:** no dataset is downloaded, no model is trained, no
> weights are fetched, no inference is implemented, and no API or interface is
> modified. This runbook plans and organises acquisition; training happens later
> (P4.1.3 pipeline is already in place and waiting on Dataset v1.0).
