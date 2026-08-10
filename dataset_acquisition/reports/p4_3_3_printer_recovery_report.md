# P4.3.3 Printer Acquisition Recovery Report

Sprint: **P4.3.3 — Printer Acquisition Recovery & Low-Memory Open Images Ingestion**
Generated: 2026-08-10T00:00:00+00:00 (injected, deterministic — not wall clock)
Machine-readable companion: `dataset_acquisition/reports/p4_3_3_printer_recovery_report.json`

Every number in this report is derived from real on-disk artifacts (the
orchestrator status JSON `p4_3_3_real_printer.json`, the converter's
`conversion_report.json` / `conversion_errors.json`, the provenance manifest,
the visual-QA `qa_data.json`, and the measured `p4_3_3_memory_evidence.json`).
Where a value could not be measured it is recorded as **NOT MEASURED** — never
invented.

---

## 1. Sprint Overview

P4.3.3 recovers the **printer** class that P4.3.2 left **BLOCKED** by a genuine
host-memory OOM. The workflow followed was: INVESTIGATE OOM → BUILD LOW-MEMORY
ADAPTER → TEST → DRY-RUN → BOUNDED REAL ACQUISITION (limit 20, then 100) →
CONVERT / VALIDATE / VISUAL QA → REGRESSION → STOP. Printer reached
**QA_PENDING** with full evidence and **no OOM**. No model work, no Dataset v1.0
release, no other class touched.

## 2. Scope and Constraints

- Added exactly one project-owned, thin low-memory acquisition adapter
  (`scripts/acquire_openimages_lowmem.py`) that plugs into the **frozen** P4.3.1
  orchestrator through its existing `DownloadFn` seam. No second dataset
  architecture; no second annotation format; no website scraped; no datasets
  mixed.
- Reused verbatim: the orchestrator `acquire_openimages_multiclass.py`, the
  converter `convert_openimages_to_yolo.py`, the frozen validators, the
  `DuplicateDetector`, the provenance mechanism and the visual-QA generator.
- Did **not** solve by raising the limit only, disabling validation, deleting
  annotations, fabricating labels, reducing QA requirements, changing taxonomy,
  changing image-quality thresholds, changing provenance requirements, editing
  the vendored `OIDv4_ToolKit`, or falling back to another dataset.
- No frozen `intelligence/device_ai` module (`.py`) was modified.

## 3. Root Cause (P4.3.2 OOM)

The vendored `OIDv4_ToolKit` loads the entire Open Images train bounding-box CSV
in a single `pandas.read_csv`, inferring every column as `object` dtype. The
in-memory frame balloons past host memory and the process dies before a single
image is fetched. Captured verbatim in `p4_3_2_real_printer.json`:

```
numpy._core._exceptions._ArrayMemoryError: Unable to allocate 111. MiB for an
array with shape (14610229,) and data type object
```

Location: `OIDv4_ToolKit/modules/csv_downloader.py:TTV → pandas.read_csv`, over
`train-annotations-bbox.csv` (**1,194,033,454 bytes**, ~**14,610,229** rows, 13
columns). This is a genuine host-memory constraint, not a mapping or
data-absence problem — `Printer → printer` is MAPPED, and tablet/monitor read
the same CSV successfully in P4.3.2.

## 4. Remediation Design (thin adapter, frozen everything else)

`scripts/acquire_openimages_lowmem.py` replaces **only** the fragile annotation
*scan* with a memory-bounded, chunked reader, then reuses the toolkit's own
`aws s3 --no-sign-request` object layout and writes the exact OIDv4 per-class
source layout the frozen converter already consumes:

- **Chunked, narrow read.** `pandas.read_csv(usecols=<11 of 13 columns>,
  dtype=<string / float32 / int8>, chunksize=500000)`. The two frame-of-reference
  columns (`Source`, `Confidence`) are never loaded. Each chunk is filtered to
  the class MID (and any active attribute filters) before retention, so at most
  one narrow chunk is resident at a time.
- **Early exit + determinism.** ImageIDs are collected in first-seen CSV order
  until `--limit` distinct ids are held; because the bbox CSV is
  ImageID-contiguous, the scan stops the instant a *new* distinct id appears past
  the limit, at which point every selected image is complete. The selection is
  therefore identical for a given CSV + limit **independent of chunk size**
  (verified by a chunk-size-parametrized test over `[1, 2, 3, 7, 1000]`).
- **Source fidelity.** Exact source ImageIDs and exact source XYXY boxes are
  preserved; normalized OID coordinates are multiplied by the *real* downloaded
  image's pixel dimensions — the same math as the vendored `get_label`.
- **Integration seam.** It satisfies the orchestrator's public `DownloadFn`
  contract (`DownloadRequest → DownloadResult`) and is injected via
  `run(args, download_fn=...)`. The vendored toolkit is **not** modified.

## 5. Data Source

Single source: **Open Images V7**. Confirmed in the per-class status JSON
(`"source": "Open Images V7"`) and in every provenance manifest record.

## 6. Taxonomy Basis

The class and its ID were loaded dynamically from
`intelligence/device_ai/dataset/taxonomy.py` (frozen taxonomy **v1.0.0**) via
`load_taxonomy()`. No class ID was assumed. Verified live: **printer = 8**.

## 7. Source Class Mapping (resolved, not hardcoded)

Resolved from the actual P4.3.1 plan manifest
`dataset_acquisition/manifests/p4_3_1_openimages_acquisition_plan.csv`; the MID
was resolved at runtime from `class-descriptions-boxable.csv`.

| EcoTrace class | class_id | Open Images V7 class | MID        | Mapping status |
|----------------|----------|----------------------|------------|----------------|
| printer        | 8        | Printer              | `/m/01m4t` | MAPPED         |

The mapping was never hardcoded in the adapter.

## 8. Memory Evidence (measured, not invented)

Measured on this host with `tracemalloc` (Python peak) and the Windows
`GetProcessMemoryInfo` `PeakWorkingSetSize` (whole-process high-water mark)
around a **real** scan of the full 1.11 GiB CSV at `--limit 20`. Full detail in
`p4_3_3_memory_evidence.json`.

| Metric | Value |
|--------|------:|
| CSV size | 1,194,033,454 bytes (1.11 GiB) |
| Rows read | 1,000,000 |
| Chunks read | 2 (of ~30 possible) |
| Matched rows | 31 |
| Selected images | 20 |
| Python peak (tracemalloc) | 48.3 MiB |
| Process peak working set | 175.6 MiB |
| Process peak ÷ CSV size | 0.154 |
| OOM reproduced | **false** |

The resident set stays a small fraction of the file because only the leading
chunks are streamed and the columns are narrowed. The P4.3.2 OOM did not occur.

## 9. Acquisition Target and Ceiling Policy

Pilot start: **20** (proves the pipeline with no OOM). Controlled target:
**100** — a ceiling, not a promise. The printer plan row records
min/recommended/max = **150 / 300 / 500**, so 100 is a bounded pilot well within
the recommended figure. Where Open Images supplied fewer readable images than
requested, the actual count is recorded; the dataset was never padded.

## 10. Execution: Dry-Run First

Printer was dry-run before any real download: `state: DRY_RUN`,
`mapping_status: MAPPED`, `requested: 20`, `dry_run: true`
(`p4_3_3_dryrun_printer.json`). The dry-run wrote no image data.

## 11. Execution: Bounded Real Acquisition

Two bounded real runs, each through the frozen orchestrator with the low-memory
`download_fn` injected:

| Run | Limit | State | Downloaded | Converted | OOM |
|-----|------:|-------|-----------:|----------:|:---:|
| Pilot     | 20  | QA_PENDING | 20 | 20 | none |
| Controlled | 100 | QA_PENDING | 96 | 96 | none |

The limit-100 scan selected **100** distinct ImageIDs; **96** landed as readable
files from the public S3 bucket. The 4-image gap is honestly reported as not
downloaded (unavailable/unreadable objects) — not padded and not fabricated.

## 12. Acquisition Accounting (no unexplained counts)

Derived from `conversion_report.json`, `conversion_errors.json`, the provenance
manifest and the orchestrator status JSON:

**printer (id 8)** — requested 100, downloaded 96, source images found 96,
source labels found 96, converted 96, conversion_failed 0, orphan source labels
0, valid_images 96, valid_annotations 96, total source objects 121, total
converted objects 121, within-class duplicates 0.

Reconciliation: `downloaded == source_images_found == converted ==
valid_images == valid_annotations == 96`; `source_objects == converted_objects
== 121`; `conversion_failed == orphans == duplicates == 0`. Every count is
accounted for.

## 13. Provenance

Every staged image retains full provenance via the frozen P4.3.1 mechanism.
Each `provenance/provenance_manifest.json` record carries `source`
("Open Images V7"), `source_class` ("Printer"), `source_image_filename`,
`source_annotation_filename`, `ecotrace_class` ("printer"), `ecotrace_class_id`
(8), `sha256`, `width`, `height`, `object_count`, `conversion_version`
("openimages-multiclass-v1"), `conversion_timestamp`, `taxonomy_version`
("1.0.0"). Provenance records: **96**. SHA-256 present: **96/96**. Provenance
missing: **0**.

License note (per record `provenance_note`):
`images=per-image-Flickr(VARY-verify); annotations=CC-BY-4.0(Google)`. No
redistribution claim is asserted beyond this recorded per-image note.

## 14. Conversion

Conversion used the frozen `scripts/convert_openimages_to_yolo.py` (version
`openimages-multiclass-v1`). The converter was not rewritten, its normalization
math was not modified, **no invalid box was clipped** and no source annotation
was silently repaired. `conversion_errors.json` `error_count` is **0**.

## 15. Image Validation (frozen P4.2.x tooling, no threshold changes)

Frozen thresholds applied unchanged: blur 100.0, dark 40.0, bright 220.0,
min_dim 32, max_dim 12000, duplicate hamming 5. Structural image issues
(CORRUPTED / RESOLUTION_* / INVALID_ASPECT_RATIO / FILE_TOO_LARGE / DUPLICATE_* /
UNSUPPORTED_EXTENSION): **0**. `valid_images == converted == 96` ⇒ zero
structural rejections. No threshold was altered.

## 16. Image Quality Flags (reported, not auto-rejected)

Quality flags are advisory metadata; no blurry image was auto-rejected and no
difficult sample auto-approved.

| Class   | Blurry | Blur threshold |
|---------|-------:|---------------:|
| printer | 16     | 100.0          |

## 17. Annotation Validation

`validate_annotations` issue count is **0**. Pairing is exact — images without
labels: **0**; labels without images: **0** (96 ↔ 96). Class-ID validation:
every box carries the correct class id (`{"8": 121}`); no foreign or
out-of-range class id is present. No Open Images annotation was silently
corrected — human QA remains authoritative.

## 18. Duplicate Detection (within-class)

Frozen `DuplicateDetector` (hamming 5): printer — **0 exact, 0 near**. No
duplicate was auto-deleted. (Cross-class detection is a batch-level P4.3.2
concern and is out of scope for this single-class recovery.)

## 19. QA Boundary

Every converted image ends **QA_PENDING**. No new data was marked QA_ACCEPTED
automatically. Per-class QA counters: printer qa_pending **96** / qa_accepted
**0** / qa_rejected **0**. The batch QA boundary constant is `QA_PENDING`.

## 20. Visual QA Preparation

Annotated previews and one contact sheet were generated with
`scripts/make_visual_qa_multiclass.py` (read-only w.r.t. staged data). The
`manual_review/qa_data.json` carries `"qa_status": "QA_PENDING"`:

| Class   | Previews | Contact sheet | Objects tagged | qa_status  |
|---------|---------:|:-------------:|---------------:|------------|
| printer | 96       | yes           | 121            | QA_PENDING |

Generating previews is **not** QA sign-off. Visual QA is **NOT COMPLETE** — these
artifacts exist only to support a human reviewer. Final state remains QA_PENDING
because no human review has occurred.

## 21. Pilot / Sibling-Class Protection

Live fingerprints were compared against the pre-acquisition baseline
(`p4_3_3_pilot_baseline.json`; after-capture in `p4_3_3_pilot_after.json`). All
five protected directories — the three P4.2.x/P4.3.1 pilots plus the two P4.3.2
staged classes — are **unchanged** (file_count + total_bytes identical):

| Protected directory                | Baseline files / bytes | Live files / bytes  | Unchanged |
|------------------------------------|------------------------|---------------------|:---------:|
| openimages_laptop_v1               | 72 / 10,525,045        | 72 / 10,525,045     | yes       |
| openimages_laptop_canonical_v1     | 47 / 6,110,063         | 47 / 6,110,063      | yes       |
| openimages_smartphone_v1           | 15 / 1,003,504         | 15 / 1,003,504      | yes       |
| openimages_tablet_v1               | 305 / 42,838,399       | 305 / 42,838,399    | yes       |
| openimages_monitor_v1              | 302 / 44,514,158       | 302 / 44,514,158    | yes       |

Nothing unexpected changed; the STOP-on-change condition was **not** triggered.

## 22. Dataset v1.0 Status and Stop Condition

**Testing.** P4.3.3 adapter tests: **21 passed**. Full `device_ai` suite:
**869 passed**. Ruff: clean on the new script and test (strict repo config).
Mypy on the new module: **clean** (0 errors from `acquire_openimages_lowmem.py`).
A single pre-existing mypy error at `validate_annotations.py:75`
(`[no-any-return]`) lives in a frozen validator reached transitively; it appears
identically when checking the untouched orchestrator alone, was not introduced by
P4.3.3, and was not "fixed" (frozen code, out of scope).

**Frozen-code verification.** No frozen `intelligence/device_ai` `.py` module was
changed. The only change under that tree is `requirements-dev.txt` (declaring
`pandas==3.0.5` as a test dependency so the suite can import the adapter). `git
diff --check` is clean.

**Release status.**

- `is_dataset_v1`: **false** — **Dataset v1.0 is NOT RELEASED.**
- `is_released`: **false**. No merge into production `datasets/`. No model
  exists; no mAP/precision/recall is claimed.
- Printer is staged and **QA_PENDING** (96 images, 121 boxes); all staged data
  awaits **explicit human review**.

**STOP.** Per the sprint contract, work halts here: printer reached QA_PENDING
with all evidence generated — no further acquisition, no touching sibling
classes, no QA_ACCEPTED, no v1.0 release, no training, no commit, no push.
Awaiting explicit human review.
