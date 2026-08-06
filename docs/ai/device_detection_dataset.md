# Device Detection Dataset Specification

**Sprint:** P4.1.1 — Device Detection Dataset & Training Foundation
**Component:** Device Intelligence Engine (DIE) — Device Detector (milestone M1.4)
**Status:** Active
**Scope:** Preparation only. This specification defines *how* a production
device-detection dataset is structured, annotated, versioned and quality-gated.
It does **not** train any model, download any dataset, or fetch any weights.

---

## 1. Purpose

This document is the single source of truth for the **device-detection
dataset**: the labelled images used to train the Ultralytics YOLO detector that
identifies e-waste devices for the EcoTrace India platform.

It is written to be executed by the **existing** dataset pipeline
(`intelligence/device_ai/dataset/`, milestone M1.2). Every rule below maps to a
concrete, already-implemented module — this specification introduces **no new
code paths** and reuses the pipeline end to end:

| Concern | Pipeline module | Configuration source |
| --- | --- | --- |
| Directory layout | `dataset/layout.py` (`DatasetLayout`) | `configs/settings.py::DATASET_SUBDIRS` |
| De-duplication | `dataset/duplicates.py` (`DuplicateDetector`) | `duplicate_hamming_threshold` |
| Quality metrics | `dataset/metadata.py` | `blur_threshold`, `brightness_*_threshold`, `min/max_image_dimension` |
| Annotation format | `dataset/validator.py` (`AnnotationValidator`) | YOLO 5-field txt |
| Splitting | `dataset/splitter.py` (`DatasetSplitter`) | `split_ratios`, `split_seed` |
| Augmentation | `dataset/augmenter.py` (`ImageAugmenter`) | `DEFAULT_OPERATIONS` |
| Export | `dataset/exporter.py` (`DatasetExporter`) | YOLO / COCO / VOC + `data.yaml` |
| Versioning | `dataset/versioning.py` (`DatasetVersionManager`) | content-addressed `versions.json` |

> **Non-negotiable:** the class list in §3 is authoritative. It is derived from
> the component/material knowledge base and the detector's canonical label map;
> changing it is a cross-cutting change, not a dataset edit.

---

## 2. Design Principles

- **Reproducible.** Every derived artifact (splits, augmentations, versions) is
  produced by a seeded, pure function. The same inputs and seed always yield
  byte-identical outputs.
- **Immutable snapshots.** A training run consumes a *version*, never a live
  directory. Versions are content-addressed and monotonic (`v1`, `v2`, …).
- **Quality-gated.** Images that fail resolution, blur, brightness, corruption
  or duplicate checks never reach the training set.
- **Label-aware.** Augmentation and splitting understand YOLO labels; geometric
  transforms that would invalidate boxes are excluded by default.
- **No hardcoded paths.** All directories resolve from `Settings`; no module
  hardcodes a dataset location.

---

## 3. Supported Device Taxonomy

The detector recognises **19 canonical device types**. This list is the same
taxonomy used by the component profiles (`components/data/components.yaml`) and
the material knowledge base (`materials/data/materials.yaml`), so a detection
flows straight into downstream component/material reasoning without remapping.

| Class ID | Canonical type | Example synonyms (normalised to canonical) |
| --- | --- | --- |
| 0 | `laptop` | notebook, ultrabook, laptop_computer |
| 1 | `smartphone` | cell_phone, mobile, handset, phone |
| 2 | `tablet` | — |
| 3 | `desktop` | pc, workstation, tower, personal_computer |
| 4 | `server` | — |
| 5 | `monitor` | lcd_monitor, led_monitor, display, screen |
| 6 | `crt_monitor` | crt, cathode_ray_tube |
| 7 | `television` | tv, smart_tv |
| 8 | `printer` | — |
| 9 | `keyboard` | — |
| 10 | `mouse` | — |
| 11 | `router` | wifi_router, wireless_router, modem, gateway |
| 12 | `power_supply` | charger, psu, power_adapter, adapter |
| 13 | `cable` | usb_cable, power_cable, wire |
| 14 | `camera` | digital_camera, webcam |
| 15 | `game_console` | gaming_console, console |
| 16 | `smartwatch` | wearable, smart_watch |
| 17 | `headphones` | earbuds, earphones, headset |
| 18 | `battery` | battery_pack, cell |

**Class-ID contract.** The integer `class_id` in every YOLO label file MUST
follow the ordering above (0–18). This ordering is the `names:` list written
into the exported `data.yaml` (see §11) and MUST be passed to
`DatasetExporter(class_names=...)` so exports carry real names rather than the
synthesised `class_<id>` fallback.

> The inference-time detector (`inference/yolo_detector.py`) title-cases and
> alias-maps raw model labels through its own `label_map`; that interface is
> **frozen** and unchanged by this specification. The alias columns above exist
> only to guide human annotators toward the correct canonical class.

---

## 4. Directory Layout

A managed dataset is the set of sub-directories defined by
`configs/settings.py::DATASET_SUBDIRS` and materialised by `DatasetLayout`,
all resolved relative to `Settings.dataset_dir` (default `datasets/`):

```
datasets/
├── raw/          # Original ingested images, untouched (source of truth for pixels)
├── processed/    # Normalised/resized intermediates (optional pipeline stage)
├── cleaned/      # Images that passed quality + duplicate gates
├── augmented/    # Offline, label-aware augmentation outputs
├── annotations/  # Human-authored annotation artifacts (e.g. exported tool JSON)
├── labels/       # YOLO .txt label files (one per image, same stem)
├── metadata/     # Per-image quality metrics + versions.json (version registry)
├── quality/      # Quality reports (JSON/HTML) produced by the pipeline
├── splits/       # Deterministic train/val/test split manifests
└── exports/      # Framework-ready exports (yolo/, coco/, voc/) + data.yaml
```

**Rules:**

1. `raw/` is append-only. Cleaning, processing and augmentation never mutate it.
2. Every image in a labelled set has exactly one label file in `labels/` with
   the **same stem** (`img_000123.jpg` ↔ `img_000123.txt`).
3. An image with **no objects** is a valid negative example: it has an **empty**
   `.txt` file (zero lines), not a missing file.
4. Generated directories (`cleaned/`, `augmented/`, `splits/`, `exports/`) are
   reproducible from `raw/` + `labels/` + settings, and may be regenerated.

---

## 5. Annotation Format

Labels use the **YOLO detection format** enforced by
`dataset/validator.py::AnnotationValidator`:

- One `.txt` file per image, one bounding box per line.
- Each line has exactly **5 whitespace-separated fields**:

  ```
  <class_id> <x_center> <y_center> <width> <height>
  ```

- `class_id` — integer in `[0, 18]` (see §3). Negative or out-of-range IDs are
  rejected.
- `x_center`, `y_center`, `width`, `height` — floats **normalised to `[0, 1]`**
  relative to image width/height. `width`/`height` must be in `(0, 1]`.
- No header, no trailing metadata, UTF-8 encoded.

**Example** (`labels/img_000123.txt` — a laptop and a mouse):

```
0 0.512 0.480 0.640 0.550
10 0.815 0.760 0.120 0.150
```

Validation is mandatory before splitting/export: run the pipeline's validator
and treat any reported issue as a hard failure for that file.

---

## 6. Naming Convention

Consistent, collision-free, sortable names keep the pipeline deterministic.

- **Images:** `{class}_{source}_{seq}.{ext}`
  - `class` — canonical device type (§3), lower snake_case.
  - `source` — short origin tag (e.g. `field`, `web`, `donor`, `partner`).
  - `seq` — zero-padded 6-digit sequence, unique within `(class, source)`.
  - `ext` — one of the allowed extensions (§8).
  - Example: `laptop_field_000042.jpg`.
- **Labels:** identical stem, `.txt` extension (`laptop_field_000042.txt`).
- **Augmented images:** the augmenter suffixes the operation to the stem
  (e.g. `laptop_field_000042__hflip.jpg`); labels follow the same stem.
- Use only `[a-z0-9_]` plus a single dot before the extension. No spaces, no
  uppercase, no unicode — this guarantees cross-platform, sortable paths.

> The pipeline does not *require* this scheme to function (it keys off file
> stems), but production datasets MUST follow it so provenance is legible and
> merges across sources never collide.

---

## 7. Duplicate Handling

De-duplication is performed by `dataset/duplicates.py::DuplicateDetector`
(constructed via `DuplicateDetector.from_settings(settings)`):

- **Exact duplicates** — identical **SHA-256** (byte-for-byte). Always removed;
  keep the first occurrence.
- **Near-duplicates** — perceptual hashes (**aHash / dHash / pHash**). Two
  images are near-duplicates when the **minimum** Hamming distance across the
  three hashes is `<= duplicate_hamming_threshold` (default **5**).

**Policy:**

1. Run duplicate detection on `raw/` before annotation to avoid labelling the
   same device twice.
2. Remove exact duplicates unconditionally.
3. Near-duplicates are removed by default; retain a near-duplicate **only** when
   it adds genuine variation (different angle/lighting of the same unit) and the
   decision is recorded in the source log.
4. De-duplication happens **before** splitting so that near-identical images can
   never straddle the train/val/test boundary and leak.

---

## 8. Quality Requirements

Quality gates use the per-image metrics from `dataset/metadata.py` and the
thresholds in `configs/settings.py`. An image must pass **all** gates to enter
`cleaned/`:

| Gate | Rule | Setting (default) |
| --- | --- | --- |
| Format | Extension ∈ `{.jpg, .jpeg, .png, .webp}` | `ALLOWED_IMAGE_EXTENSIONS` |
| Not corrupt | Decodes to a valid image | `dataset/metadata.py` |
| Min resolution | `min(width, height) >= 32 px` | `min_image_dimension` (32) |
| Max resolution | `max(width, height) <= 12000 px` | `max_image_dimension` (12000) |
| File size | `<= 10 MiB` | `max_file_size` (10 MiB) |
| Not blurry | Variance-of-Laplacian `>= 100.0` | `blur_threshold` (100.0) |
| Not too dark | Mean luminance `>= 40.0` | `brightness_dark_threshold` (40.0) |
| Not too bright | Mean luminance `<= 220.0` | `brightness_bright_threshold` (220.0) |

**Content quality (human-reviewed, not machine-gated):**

- The target device is clearly visible and is the dominant subject.
- Bounding boxes are tight (≤ ~2% slack) and cover the whole device.
- Each class has adequate diversity: angles, backgrounds, lighting, device
  makes/models, and states (intact / damaged / partial).
- Aim for a **minimum of 200 annotated instances per class**, with rarer
  classes (e.g. `crt_monitor`, `server`) explicitly tracked for shortfall.
- Class imbalance is reported per version; heavily under-represented classes are
  flagged for targeted collection rather than synthetic over-sampling.

---

## 9. Augmentation Policy

Offline, **label-aware** augmentation is performed by
`dataset/augmenter.py::ImageAugmenter` and written to `augmented/`.

- **Default operations** (`DEFAULT_OPERATIONS`): `hflip`, `brightness`,
  `grayscale`. These are **photometric or box-preserving** — the original YOLO
  labels remain valid, so labels are copied to the augmented stem unchanged.
- **Geometric operations** (`GEOMETRIC_OPERATIONS`, e.g. `rotate90`) **invalidate
  bounding boxes** and are therefore **excluded from the default detection
  pipeline**. They must not be used unless a matching label-transform is added
  (out of scope for this sprint).
- Augmentation is **deterministic** (fixed Pillow operations, no RNG), so a
  version's augmented set is fully reproducible.

**Rules:**

1. Augment **only the training split**. Validation and test splits are never
   augmented — they must reflect the real distribution.
2. Augmentation runs **after** the split, so augmented copies inherit their
   source image's split assignment and cannot leak across splits.
3. Ultralytics also applies **online** train-time augmentation (mosaic, HSV,
   flips). Offline augmentation here is complementary and intentionally
   conservative to avoid double-augmenting into unrealistic images.

---

## 10. Train / Validation / Test Split

Splitting is performed by `dataset/splitter.py::DatasetSplitter` using a seeded
NumPy shuffle over relative image paths — a pure function of `(paths, ratios,
seed)`.

- **Default ratios:** `train:val:test = 0.7 : 0.2 : 0.1`
  (`Settings.split_ratios`; validated to be non-negative and sum to `1.0`).
- **Seed:** `Settings.split_seed` (default **42**) for reproducibility.
- **Determinism:** identical inputs + ratios + seed → identical partitions,
  every run, every machine.

**Rules:**

1. Split on **de-duplicated** images (§7) so near-duplicates cannot leak.
2. Split **before** augmentation (§9); augmented images inherit their source's
   split.
3. Persist the split manifest under `splits/` so a version records exactly which
   image went where.
4. When class imbalance is severe, splitting is still global; per-class coverage
   in each split is reported (not stratified in this sprint — see Risks in the
   training doc).

---

## 11. Export Format

`dataset/exporter.py::DatasetExporter` produces framework-ready trees under
`exports/`. The detector consumes the **YOLO** export:

```
exports/yolo/
├── images/       # image files
├── labels/       # matching .txt labels
└── data.yaml     # dataset manifest consumed by Ultralytics
```

The generated `data.yaml` has the shape:

```yaml
path: .
train: images
val: images
nc: 19
names: ['laptop', 'smartphone', 'tablet', 'desktop', 'server', 'monitor',
        'crt_monitor', 'television', 'printer', 'keyboard', 'mouse', 'router',
        'power_supply', 'cable', 'camera', 'game_console', 'smartwatch',
        'headphones', 'battery']
```

**Notes:**

- `nc` and `names` derive from the class list passed to `DatasetExporter`. Always
  pass the §3 ordering so `names` is correct and `nc = 19`; otherwise the
  exporter synthesises generic `class_<id>` names.
- The exporter's default `data.yaml` points both `train:` and `val:` at
  `images/`. For a real training run, supply a `data.yaml` whose `train:`/`val:`
  (and optional `test:`) keys reference the split directories produced in §10.
  The path passed to the trainer's `--data-config` is this `data.yaml`.
- COCO and VOC exports are available for interoperability but are not used by the
  YOLO trainer.

---

## 12. Versioning

Dataset snapshots are managed by
`dataset/versioning.py::DatasetVersionManager` (stored in
`metadata/versions.json`):

- Each version records: monotonic label (`v1`, `v2`, …), `created_at`,
  `image_count`, a **content hash** over the file manifest, an optional human
  `note`, and the manifest itself.
- Versions are **content-addressed**: the same set of files yields the same
  content hash, so accidental duplicate snapshots are detectable.
- `dataset_version: latest` in a training config resolves to the newest recorded
  version at run time; pin an explicit `v<N>` for a reproducible run.

**Rules:**

1. Cut a new version whenever the labelled set changes (added images, corrected
   labels, new augmentation policy).
2. Never mutate a published version; corrections create a new version.
3. A model record (see the training doc) stamps the exact dataset version it was
   trained on, closing the provenance loop from prediction → model → dataset.

---

## 13. End-to-End Preparation Checklist

1. Ingest source images into `raw/` following the naming convention (§6).
2. Run duplicate detection; remove exact + near-duplicates (§7).
3. Run quality metrics; move passing images into `cleaned/` (§8).
4. Annotate `cleaned/` images into `labels/` using the YOLO format (§5) and the
   class IDs in §3.
5. Validate every label file with `AnnotationValidator`; fix all issues (§5).
6. Split into train/val/test with the seeded splitter (§10).
7. Augment **only** the training split (§9).
8. Export to `exports/yolo/` with the §3 class names; verify `data.yaml`
   (`nc: 19`) (§11).
9. Cut a dataset version and record its note (§12).
10. Hand the `data.yaml` path to the training foundation
    (`docs/engineering/device_detection_training.md`).

> This sprint stops here. **No training and no downloads are performed.**

---

## 14. Related Documents

- `docs/engineering/device_detection_training.md` — how the YOLO training
  foundation consumes this dataset (configs, metrics, provenance).
- `intelligence/device_ai/docs/engineering/detector.md` — the M1.4 detector
  engineering reference.
- `docs/engineering/08_AI.md` — AI architecture overview.
