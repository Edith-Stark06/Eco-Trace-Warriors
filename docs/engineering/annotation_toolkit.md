# Annotation Toolkit (Dataset v1.0)

Status: Active
Sprint: P4.2.2
Audience: dataset engineers, annotation reviewers, QA leads

---

## 1. Purpose

The annotation toolkit is a set of five command-line scripts that **validate,
analyse, visualise and prepare** the YOLO annotations for the Dataset v1.0
release. They are thin orchestration layers over the **frozen** P4.1.2 dataset
pipeline shipped in the `device_ai` package (`intelligence/`); they add no new
domain logic, mutate no dataset artefact, and touch no API surface.

Scope boundaries (unchanged by this toolkit):

- No model training, evaluation, or export.
- No dataset downloads.
- No architecture, API, or schema changes.
- The frozen pipeline modules under `intelligence/device_ai/dataset/` are reused
  as-is; only new files under `scripts/` and this document are added.

---

## 2. Where the scripts live

```
scripts/
  _ecotrace_toolkit.py       # P4.2.1 shared bootstrap (sys.path + filename parsing)
  _annotation_toolkit.py     # P4.2.2 shared glue (bootstrap re-export + label reader)
  validate_annotations.py    # PART 1 - validation
  annotation_statistics.py   # PART 2 - statistics
  visualize_annotations.py   # PART 3 - previews
  build_dataset_release.py   # PART 4 - release manifest
  annotation_dashboard.py    # PART 5 - dashboard (HTML + Markdown)
```

All scripts are launched as plain files from the repository root. The shared
`_annotation_toolkit.py` re-exports the P4.2.1 bootstrap, which prepends
`intelligence/` to `sys.path` so `import device_ai...` resolves without an
editable install.

Common conventions across every script:

- `python scripts/<name>.py [flags]`; `--help` on each.
- Machine-readable JSON is printed to stdout and (optionally) written with
  `--json-out`; JSON uses `indent=2, sort_keys=True` for stable diffs.
- Human-readable Markdown is written with `--md-out`; stdout is ASCII-only for
  Windows console (cp1252) safety.
- `main(argv=None) -> int` returning a documented exit code.

---

## 3. Reuse map (what comes from the frozen pipeline)

| Concern | Frozen component reused |
| --- | --- |
| YOLO line parsing | `device_ai.dataset.validator.parse_yolo_line` |
| Core validation (syntax, class ids, coord range, non-positive size, missing/orphan labels) | `device_ai.dataset.validator.AnnotationValidator` |
| Image / label pairing | `device_ai.dataset.layout.label_path_for`, `list_image_paths`, `relative_path` |
| Class distribution, bbox min/max/mean, completeness | `device_ai.dataset.annotation_statistics.AnnotationStatisticsCalculator` |
| Canonical taxonomy (19 classes, version) | `device_ai.dataset.taxonomy.load_taxonomy` |
| Image statistics | `device_ai.dataset.metadata.MetadataGenerator` + `statistics.StatisticsCalculator` |
| Content hash / manifest | `device_ai.dataset.versioning.compute_content_hash` |
| Release document | `device_ai.dataset.release.build_release`, `release_to_dict` |

Value objects (`AnnotationReport`, `AnnotationIssue`, `DatasetVersion`, ...) come
from `device_ai.dataset.records`.

---

## 4. PART 1 - `validate_annotations.py`

Validate YOLO labels against the frozen validator, plus three layered checks the
frozen validator does not itself encode.

**Checks and issue codes**

| Requirement | Issue code | Source |
| --- | --- | --- |
| YOLO syntax (5 fields, numeric) | `MALFORMED_LINE` | frozen |
| Negative class id | `NEGATIVE_CLASS_ID` | frozen |
| Class id outside `[0, num_classes)` | `CLASS_ID_OUT_OF_RANGE` | frozen |
| Normalised coordinate field outside `[0, 1]` | `COORD_OUT_OF_RANGE` | frozen |
| Zero / negative width or height | `NON_POSITIVE_SIZE` | frozen |
| Image has no label file | `MISSING_LABEL` | frozen |
| Label file has no image | `ORPHAN_LABEL` | frozen |
| Box **edge** extends beyond image frame | `BOX_OUT_OF_BOUNDS` | layered |
| Two boxes identical (class + geometry) | `DUPLICATE_BOX` | layered |
| Label file exists but has no boxes | `EMPTY_LABEL` | layered |

`BOX_OUT_OF_BOUNDS` complements `COORD_OUT_OF_RANGE`: the frozen check validates
the centre and size *fields* individually, while the layered check validates the
derived *edges* (`center +/- size/2`) so a box that is in-range per field but
still spills past an edge is caught.

**Inputs**

| Flag | Required | Description |
| --- | --- | --- |
| `--images-root` | yes | Directory of dataset images |
| `--labels-root` | yes | Directory of YOLO `.txt` labels |
| `--json-out` | no | Write JSON report to path |
| `--md-out` | no | Write Markdown report to path |

**Output** - JSON (and optional Markdown) with a `summary`, `issue_counts_by_code`,
per-class `class_counts`, and a full `issues` list (file, line, code, message).

**Exit codes** - `0` pass (no issues), `1` validation failures, `2` usage error.

**Examples**

```bash
python scripts/validate_annotations.py \
    --images-root datasets/raw --labels-root datasets/labels

python scripts/validate_annotations.py \
    --images-root datasets/raw --labels-root datasets/labels \
    --json-out datasets/quality/annotations.json \
    --md-out datasets/quality/annotations.md
```

---

## 5. PART 2 - `annotation_statistics.py`

Summarise the annotations: object counts, class frequencies, bounding-box size
distributions and per-class averages.

**What it reports**

- Total object count and mean boxes per labelled image.
- Class distribution across all 19 taxonomy classes (including zero-count).
- Per-class averages: images containing the class, total boxes, mean boxes per
  image that contains the class.
- Bounding-box **width**, **height** and **object-size (area)** histograms over
  the `[0, 1]` normalised domain (`--bins`, default 10).
- Images with many annotations (`--many-threshold`, default 10).
- Images without labels and orphan labels (from the frozen calculator).

**Inputs**

| Flag | Required | Description |
| --- | --- | --- |
| `--images-root` | yes | Directory of dataset images |
| `--labels-root` | yes | Directory of YOLO `.txt` labels |
| `--bins` | no | Histogram bucket count (default 10) |
| `--many-threshold` | no | Per-image box count flagged as heavy (default 10) |
| `--json-out` / `--md-out` | no | Write JSON / Markdown |

**Output** - JSON (and optional Markdown). The `core` block is the frozen
`annotation_statistics_to_dict` payload; sibling keys carry the histograms,
`many_annotations` and `per_class_averages`.

**Exit codes** - `0` success, `2` usage error.

**Example**

```bash
python scripts/annotation_statistics.py \
    --images-root datasets/raw --labels-root datasets/labels \
    --bins 10 --many-threshold 10 \
    --json-out datasets/quality/annotation_stats.json \
    --md-out datasets/quality/annotation_stats.md
```

---

## 6. PART 3 - `visualize_annotations.py`

Render preview images with bounding boxes drawn, for visual QA. **Originals are
opened read-only and never modified** - each preview is a freshly encoded copy
written under `output/previews/` (configurable via `--output-dir`), mirroring the
image's relative path.

**Selection modes**

- `--image PATH` - a single image.
- `--images-root DIR` - every image beneath a directory.
- `--images-root DIR --sample N` - a deterministic random sample of N images
  (seeded by `--seed`, default 42).

**Inputs**

| Flag | Required | Description |
| --- | --- | --- |
| `--labels-root` | yes | Directory of YOLO `.txt` labels |
| `--image` | one of | Single image to render |
| `--images-root` | one of | Directory to render / sample from |
| `--sample` | no | Render a random sample of N images |
| `--seed` | no | RNG seed for `--sample` (default 42) |
| `--output-dir` | no | Preview destination (default `output/previews`) |

**Output** - annotated PNG/JPEG previews under the output directory; a per-image
log line and a final summary on stdout.

**Exit codes** - `0` success (including nothing to render), `2` usage error.

**Examples**

```bash
python scripts/visualize_annotations.py \
    --image datasets/raw/laptop_field_000001.jpg \
    --images-root datasets/raw --labels-root datasets/labels

python scripts/visualize_annotations.py \
    --images-root datasets/raw --labels-root datasets/labels \
    --sample 20 --seed 42
```

---

## 7. PART 4 - `build_dataset_release.py`

Produce the deterministic Dataset v1.0 release manifest by composing the frozen
pipeline end to end. The manifest carries the version + release timestamp,
checksums (content hash + per-image SHA-256 manifest), image statistics,
annotation statistics, taxonomy version and a compact annotation summary.

**Determinism** - same images + labels + `--version` + `--created-at` produce
byte-identical output. The timestamp is **injected** (not read from the wall
clock); the content hash is derived from image bytes and never depends on run
time. The builder computes the version snapshot **in memory** and does not
persist a version into the managed dataset tree, so it never mutates pipeline
state.

**Inputs**

| Flag | Required | Description |
| --- | --- | --- |
| `--images-root` | yes | Directory of dataset images |
| `--labels-root` | yes | Directory of YOLO `.txt` labels |
| `--version` | no | Release version label (default `v1.0`) |
| `--created-at` | no | ISO-8601 release timestamp (default `2026-08-07T00:00:00+00:00`) |
| `--note` | no | Human-readable release note |
| `--out` | no | Write `dataset_manifest.json` to path |

**Output** - `dataset_manifest.json` (also printed). Top-level keys:
`taxonomy_version`, `version`, `checksums`, `image_statistics`,
`annotation_statistics`, `split` (null - the release is not split here) and
`annotation_summary`.

**Exit codes** - `0` success, `2` usage error (missing directories, no images, or
an invalid `--created-at`).

**Example**

```bash
python scripts/build_dataset_release.py \
    --images-root datasets/raw --labels-root datasets/labels \
    --version v1.0 --created-at 2026-08-07T00:00:00+00:00 \
    --note "Dataset v1.0 release candidate" \
    --out datasets/exports/dataset_manifest.json
```

---

## 8. PART 5 - `annotation_dashboard.py`

Render a one-page annotation dashboard as **HTML and Markdown**. It composes the
sibling scripts and the frozen pipeline (no new metrics) and folds in the
optional tracking CSVs.

**Sections**

- **Validation summary** - reuses PART 1 (`validate` / `report_to_dict`).
- **Class distribution** and **missing labels** - reuse PART 2.
- **Annotation progress** - from `annotation_progress.csv` (per-class annotated
  vs targets).
- **Review status** - from `annotation_review.csv` (counts by stage/disposition).
- **QA failures** - from `qa_report.csv` (failing batches surfaced).

The CSV inputs are the P4.1.x templates under `docs/ai/templates/`. Comment lines
(`#`) and the shipped `EXAMPLE-` placeholder rows are skipped, so a
freshly-copied template contributes nothing misleading. Every value is HTML
escaped. The dashboard reads only.

**Inputs**

| Flag | Required | Description |
| --- | --- | --- |
| `--images-root` | yes | Directory of dataset images |
| `--labels-root` | yes | Directory of YOLO `.txt` labels |
| `--progress-csv` | no | `annotation_progress.csv` |
| `--review-csv` | no | `annotation_review.csv` |
| `--qa-csv` | no | `qa_report.csv` |
| `--html-out` / `--md-out` / `--json-out` | no | Write HTML / Markdown / JSON |

**Output** - a self-contained HTML page, a Markdown mirror, and the raw dashboard
data as JSON. Markdown is printed to stdout.

**Exit codes** - `0` success, `2` usage error.

**Example**

```bash
python scripts/annotation_dashboard.py \
    --images-root datasets/raw --labels-root datasets/labels \
    --progress-csv docs/ai/templates/annotation_progress.csv \
    --review-csv docs/ai/templates/annotation_review.csv \
    --qa-csv docs/ai/templates/qa_report.csv \
    --html-out datasets/quality/dashboard.html \
    --md-out datasets/quality/dashboard.md
```

---

## 9. Integration into the Dataset v1.0 workflow

The toolkit slots into the annotation stage of the collection process
(`device_collection_process.md`) after images are imported and labelled:

1. **Annotate** labels into `datasets/labels/` (mirroring `datasets/raw/`).
2. **Validate** - run `validate_annotations.py`. Exit `1` means blocking issues;
   fix and re-run until it exits `0`.
3. **Visualise** - spot-check a random sample with `visualize_annotations.py`;
   confirm boxes are tight and correctly classified.
4. **Analyse** - run `annotation_statistics.py`; check class balance against the
   per-class targets and investigate under-served or heavily-annotated classes.
5. **Track** - update `annotation_progress.csv`, `annotation_review.csv` and
   `qa_report.csv`; regenerate the dashboard with `annotation_dashboard.py` for a
   single review artefact.
6. **Release** - once validation passes and QA signs off, run
   `build_dataset_release.py` to produce the deterministic
   `dataset_manifest.json` for Dataset v1.0.

A minimal CI gate is: `validate_annotations.py` must exit `0`, and
`build_dataset_release.py` must reproduce the recorded `content_hash`.

---

## 10. Exit-code reference

| Script | 0 | 1 | 2 |
| --- | --- | --- | --- |
| `validate_annotations.py` | no issues | validation failures | usage error |
| `annotation_statistics.py` | success | - | usage error |
| `visualize_annotations.py` | success | - | usage error |
| `build_dataset_release.py` | success | - | usage error |
| `annotation_dashboard.py` | success | - | usage error |

---

## 11. Design notes

- **No duplicated parsing.** Every box is parsed by the frozen
  `parse_yolo_line`; the shared `_annotation_toolkit.iter_label_boxes` /
  `read_label_boxes` wrap it so the layered checks and the visualiser never
  re-implement parsing.
- **Read-only.** No script writes into `datasets/raw`, `datasets/labels`, or any
  frozen module. Previews and reports go to caller-specified paths.
- **Deterministic.** JSON is sorted; sampling and the release timestamp are
  seeded/injected; the release content hash is content-addressed.
- **ASCII stdout.** Human-readable stdout avoids non-ASCII characters for Windows
  console (cp1252) safety; HTML files use entities (e.g. `&mdash;`).
