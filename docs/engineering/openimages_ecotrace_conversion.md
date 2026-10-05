# Open Images → EcoTrace YOLO Conversion (Laptop Pilot)

Status: Active
Sprint: P4.2 dataset acquisition — Laptop conversion pilot
Audience: dataset engineers, annotation reviewers, QA leads

---

> **Scope statement — read first.**
> This document describes a **Dataset v1.0 acquisition pilot** covering the
> **`laptop`** class **only** (21 Open Images V7 images, 35 objects). It is **not**
> a Dataset v1.0 release, it does **not** mark the dataset as READY or RELEASED,
> and it invents **no** dataset statistics or quality scores. The pilot exists so
> the conversion pipeline can be reviewed on one class before acquisition scales
> to the remaining 18 taxonomy classes.

---

## 1. Purpose

`scripts/convert_openimages_to_yolo.py` converts a single-class Open Images V7
pilot (downloaded via the OIDv4 Toolkit) into the normalised YOLO annotation
format that the **frozen** EcoTrace `device_ai` dataset pipeline consumes,
**while preserving full provenance** for every image.

The converter is a thin orchestration layer:

- It **reuses** the frozen taxonomy (`device_ai.dataset.taxonomy.load_taxonomy`)
  and the frozen content hasher (`device_ai.dataset.hashing.sha256_hash`).
- It adds **no** new domain logic to the `device_ai` package.
- It **never** mutates the Open Images source images or labels.
- It writes **only** into a separate staging directory.

Scope boundaries (unchanged by this converter):

- No model training, evaluation, or export.
- No additional dataset downloads.
- No architecture, API, taxonomy, validator, config, or schema changes.
- The frozen pipeline modules under `intelligence/device_ai/dataset/` are reused
  as-is; only new files under `scripts/`, a test under
  `intelligence/device_ai/tests/`, and this document are added.

---

## 2. Where things live

```
scripts/
  _ecotrace_toolkit.py            # shared bootstrap (prepends intelligence/ to sys.path)
  convert_openimages_to_yolo.py   # THIS converter (new, additive)

intelligence/device_ai/tests/
  test_openimages_conversion.py   # 15 tests, the 10 mandated scenarios + e2e

docs/engineering/
  openimages_ecotrace_conversion.md  # this document
```

The converter is launched as a plain file from the repository root. Importing
`_ecotrace_toolkit` performs the `sys.path` bootstrap so `import device_ai …`
resolves the frozen package without installing anything.

---

## 3. Source format (Open Images V7 / OIDv4 Toolkit)

The OIDv4 Toolkit stores one annotation file per image under a sibling `Label/`
directory. Each non-empty line is a single box in **pixel-space XYXY**:

```
<SourceClass> x1 y1 x2 y2
```

Example (`…/train/Laptop/Label/14587a599414300c.txt`, image 1024×683):

```
Laptop 256.0 333.811469 583.04 558.701513
Laptop 880.64 215.920205 952.96 249.878282
Laptop 887.04 184.525427 906.88 221.04612
Laptop 916.48 143.519473 957.44 217.201513
Laptop 1005.44 213.35758900000002 1023.36 276.14714499999997
```

Key properties:

- Coordinates are **absolute pixels**, not normalised.
- `x1 y1` is the top-left corner; `x2 y2` is the bottom-right corner.
- The source class name may contain spaces (e.g. `CRT monitor`); the converter
  treats the **last four whitespace fields** as the coordinates and everything
  before them as the class name.
- Layout: images in `…/train/<Class>/`, labels in `…/train/<Class>/Label/`, one
  `.txt` per image sharing the stem.

For this pilot the only source class is **`Laptop`** (capitalised).

---

## 4. Class mapping (discovered, never assumed)

The EcoTrace taxonomy id for a source class is **resolved at runtime** from the
frozen taxonomy — it is never hardcoded:

```python
taxonomy = load_taxonomy()                     # frozen single source of truth
canonical = source_to_canonical["Laptop"]      # "laptop"
class_id  = taxonomy.class_id_for(canonical)   # -> 0 (discovered)
```

Two facts this pilot depends on:

| Lookup                              | Result | Meaning                                   |
| ----------------------------------- | ------ | ----------------------------------------- |
| `class_id_for("laptop")`            | `0`    | canonical, lowercase — the id we emit     |
| `class_id_for("Laptop")`            | `None` | source spelling is **not** a taxonomy name |

Because the Open Images class `Laptop` (capitalised) is **not** a taxonomy name,
an explicit source→canonical mapping is required (`{"Laptop": "laptop"}`). The
converter fails fast and reports rather than guessing when a mapping is absent or
wrong:

| Condition                                        | Error code             |
| ------------------------------------------------ | ---------------------- |
| Source class has no entry in the mapping         | `UNKNOWN_SOURCE_CLASS` |
| Mapped canonical name is absent from the taxonomy | `WRONG_TAXONOMY_MAPPING` |

> The taxonomy is frozen at version `1.0.0` (19 classes). If the taxonomy is ever
> re-ordered, the emitted id changes automatically because it is looked up, not
> assumed.

---

## 5. Conversion formulas

Each pixel-space XYXY box on an image of size `W × H` is converted to a
normalised YOLO box `class_id x_center y_center width height`:

```
x_center = (x1 + x2) / 2 / W
y_center = (y1 + y2) / 2 / H
width    = (x2 - x1)     / W
height   = (y2 - y1)     / H
```

Output values are rounded to **6 decimal places** for cross-platform
determinism. Worked example (box 1 of the sample above, `W=1024, H=683`):

```
x_center = (256.0 + 583.04) / 2 / 1024 = 0.409687
y_center = (333.811469 + 558.701513) / 2 / 683 = 0.653377
width    = (583.04 - 256.0)     / 1024 = 0.319375
height   = (558.701513 - 333.811469) / 683 = 0.329268
-> "0 0.409687 0.653377 0.319375 0.329268"
```

### 5.1 Validation — reject, never clip

Normalised coordinates are validated against `[0, 1]` on the **raw**
(pre-rounding) values. A box that spills past the image frame is **reported as an
error, not silently clamped**:

| Condition                                     | Error code               |
| --------------------------------------------- | ------------------------ |
| Image width or height ≤ 0                      | `INVALID_IMAGE_DIMENSIONS` |
| `x2 ≤ x1` or `y2 ≤ y1` (degenerate box)       | `NON_POSITIVE_SIZE`      |
| Any normalised value leaves `[0, 1]`          | `COORD_OUT_OF_RANGE`     |
| Line has ≠ 5 fields / non-numeric coordinate  | `MALFORMED_LINE`         |

**File-level atomicity.** If *any* line of a label fails — or the label is
missing, empty, or unreadable, or the image cannot be decoded — the **whole
image is skipped**: no YOLO label is written and the image is **not** staged.
This guarantees the staging directory only ever holds fully-valid, one-to-one
image/label pairs. Every failure is still recorded in the error report.

| Whole-image condition                       | Error code            |
| ------------------------------------------- | --------------------- |
| Source image cannot be decoded              | `UNREADABLE_IMAGE`    |
| No matching source label for an image       | `MISSING_SOURCE_LABEL` |
| Source label unreadable                     | `UNREADABLE_LABEL`    |
| Source label contains no boxes              | `EMPTY_SOURCE_LABEL`  |
| Source label has no matching source image   | `MISSING_SOURCE_IMAGE` (orphan) |

---

## 6. Provenance (per image)

Every staged image carries a provenance record in
`provenance/provenance_manifest.json`. Fields:

| Field                        | Source                                             |
| ---------------------------- | -------------------------------------------------- |
| `stem`                       | shared image/label stem                            |
| `source`                     | `"Open Images V7"` (configurable)                  |
| `source_class`               | `"Laptop"` (the source spelling)                   |
| `ecotrace_class`             | `"laptop"` (canonical taxonomy name)               |
| `ecotrace_class_id`          | `0` (discovered via `load_taxonomy`)               |
| `source_image_filename`      | e.g. `14587a599414300c.jpg`                        |
| `source_annotation_filename` | e.g. `14587a599414300c.txt`                        |
| `sha256`                     | SHA-256 of the source image bytes (frozen hasher)  |
| `width`, `height`            | decoded image dimensions in pixels                 |
| `object_count`               | number of converted boxes                          |
| `conversion_version`         | injected `--conversion-version`                    |
| `conversion_timestamp`       | injected `--created-at` (ISO-8601)                 |

Example record:

```json
{
  "conversion_timestamp": "2026-08-08T00:00:00+00:00",
  "conversion_version": "openimages-laptop-v1",
  "ecotrace_class": "laptop",
  "ecotrace_class_id": 0,
  "height": 683,
  "object_count": 5,
  "sha256": "41a5bf97eea6d2c4a9d86d9d1f5579a894e50bd9df55c0b9668db8cd296f1ea5",
  "source": "Open Images V7",
  "source_annotation_filename": "14587a599414300c.txt",
  "source_class": "Laptop",
  "source_image_filename": "14587a599414300c.jpg",
  "stem": "14587a599414300c",
  "width": 1024
}
```

---

## 7. Staging layout (outputs)

The converter writes **only** under `--staging-root` (default
`dataset_acquisition/staging/openimages_laptop_v1/`), never into the OID source:

```
dataset_acquisition/staging/openimages_laptop_v1/
  images/                       # byte-identical copies of converted source images
    <stem>.jpg …
  labels/                       # converted YOLO labels, one per staged image
    <stem>.txt …
  provenance/
    provenance_manifest.json    # one provenance record per staged image
  reports/
    conversion_report.json      # per-image + summary counts (no invented stats)
    conversion_errors.json      # every recorded error (empty when clean)
```

- Staged images are **verbatim byte copies** of the source (same SHA-256).
- The `validation/` subdirectory (below) is written by the separate validation
  scripts, not by the converter.

The converter emits the JSON conversion report to **stdout** and a one-line
staging summary to **stderr**. Exit codes: `0` clean, `1` conversion errors
recorded, `2` usage error (missing directories, unknown class, invalid
timestamp).

---

## 8. Determinism & reproducibility

Given identical source inputs and an identical `--conversion-version`, the
converter produces **byte-identical** labels, provenance, and reports. The only
timestamp-like value, `conversion_timestamp`, is **injected** via `--created-at`
(the wall clock is never read).

Reproduce the pilot from the repository root:

```bash
python scripts/convert_openimages_to_yolo.py \
    --source-images-root dataset_acquisition/OIDv4_ToolKit/OID/Dataset/train/Laptop \
    --source-labels-root dataset_acquisition/OIDv4_ToolKit/OID/Dataset/train/Laptop/Label \
    --staging-root dataset_acquisition/staging/openimages_laptop_v1 \
    --source-class Laptop --ecotrace-class laptop \
    --conversion-version openimages-laptop-v1 \
    --created-at 2026-08-08T00:00:00+00:00
```

All of these arguments have the above values as defaults, so a bare
`python scripts/convert_openimages_to_yolo.py` reproduces the pilot exactly.

Determinism guarantees:

- Six-decimal rounding removes platform float-formatting drift.
- All JSON is serialised with `indent=2, sort_keys=True`.
- Images are discovered in sorted order; error records are sorted by
  `(stem, line, code)`.
- Running the converter twice into two staging roots yields byte-identical
  `labels/`, `provenance/`, `reports/`, and image bytes (verified — see §9).

---

## 9. Validation performed on the pilot

The converted pilot was checked with the **existing frozen** validators (no new
validation logic was written). Reports are written under the staging
`validation/` subdirectory.

| Check | Tool (existing) | Result |
| ----- | --------------- | ------ |
| Conversion | `scripts/convert_openimages_to_yolo.py` | 21/21 images, 35/35 objects, **0 conversion errors**, exit 0 |
| Annotation validation (P4.2.2) | `scripts/validate_annotations.py` | **`is_valid: true`**, 21 labels, 35 boxes, all `class_id 0`, 0 issues, 0 orphans, 0 missing |
| Image/label pairing | `validate_annotations.py` summary | `images_without_labels: 0`, `labels_without_images: 0` |
| Duplicate detection | frozen `device_ai.dataset.duplicates.DuplicateDetector` | 21 images, **0 exact/near-duplicate pairs** |
| Determinism | second conversion + byte diff | labels, provenance, report, errors, and image bytes **all byte-identical** |
| Image validation (P4.2.1) | `scripts/validate_image_batch.py` | see note below |

**Image validation note (expected, non-integrity).** `validate_image_batch.py`
reports `FAIL` **only** because of two policy checks that do not apply to a raw
OID pilot:

- `FILENAME_CONVENTION` (21×): the EcoTrace collection convention is
  `<class>_<source>_<seq>.<ext>`, but requirement 6 mandates **preserving the
  original OID stems** (hash-style, e.g. `14587a599414300c.jpg`) so provenance
  stays traceable. The mismatch is therefore expected and intentional.
- `IMAGE_BLURRY` (4×, **warnings**): four images fall below the sharpness
  heuristic; these are non-blocking warnings, recorded for reviewer awareness.

No **image-integrity** failures were found (no corrupt, undersized, oversized, or
unreadable images). These results are reported verbatim; no score is invented and
nothing is suppressed.

---

## 10. Tests

`intelligence/device_ai/tests/test_openimages_conversion.py` (15 tests, all
passing) covers the ten mandated scenarios plus end-to-end staging:

1. Normal box — centre/size formula.
2. Boundary box touching all four edges — still valid (`1.0`).
3. Multiple boxes in one label.
4. Normalised-coordinate correctness (exact formula, 6-place rounding).
5. Invalid source coordinates out of frame — `COORD_OUT_OF_RANGE`, not clipped;
   plus `NON_POSITIVE_SIZE` and whole-image voiding.
6. Missing source image — `MISSING_SOURCE_IMAGE` (orphan label).
7. Missing source label — `MISSING_SOURCE_LABEL`.
8. Unknown source class — `UNKNOWN_SOURCE_CLASS`.
9. Wrong taxonomy mapping — `WRONG_TAXONOMY_MAPPING`; plus a test asserting the
   laptop id is **discovered** (`class_id_for("laptop")`) and that
   `class_id_for("Laptop")` is `None`.
10. Deterministic conversion — labels, provenance, and report byte-identical
    across two runs.

Plus an end-to-end test that only clean conversions are staged, the source is
never modified, and the provenance record carries every mandated field, and a
`MALFORMED_LINE` test.

The converter is ruff-clean and mypy-clean (the two remaining mypy findings are
pre-existing in the frozen `device_ai/utils/image_utils.py` and untouched here).

---

## 11. Limitations

- **Single class, small pilot.** 21 images / 35 objects of `laptop` only. This is
  not statistically representative and is **not** a dataset release.
- **No quality scoring beyond the existing validators.** The converter invents no
  metrics; it only reports what the frozen validators produce.
- **Filename convention not applied.** Original OID stems are preserved for
  provenance, so the collection-naming policy intentionally does not hold here. A
  future canonical-rename step (with a stem→canonical mapping recorded in
  provenance) would be needed before these images join a named collection.
- **One-to-one, whole-image atomicity.** A single bad box voids its entire image
  rather than emitting a partial label; this is deliberate for a curated pilot but
  means a noisy source could drop otherwise-usable images.
- **Extension set** for source discovery is `.jpg/.jpeg/.png/.webp`.

---

## 12. Next steps (out of scope for this pilot)

The following are **explicitly not** part of this sprint and must be reviewed
before proceeding:

- Manual review of the 21 staged laptop conversions and the 4 blur warnings.
- A canonical-rename / collection-ingest step if these images are to enter a
  named EcoTrace collection.
- Scaling acquisition + conversion to the remaining 18 taxonomy classes.
- Dataset v1.0 assembly, statistics, split, freeze, and release (governed
  separately by `docs/ai/dataset_v1_freeze_policy.md` and
  `docs/engineering/dataset_v1_release.md`).

> This pilot changes none of the frozen architecture, interfaces, taxonomy,
> validators, configs, or existing P4.1.x / P4.2.x tooling. It is additive:
> one script, one test module, and this document.
