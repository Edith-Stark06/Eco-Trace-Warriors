# P4.3.2 Multi-Class Dataset Expansion Report

Sprint: **P4.3.2 — Controlled Multi-Class Dataset Expansion**
Generated: 2026-08-10T00:00:00+00:00 (injected, deterministic — not wall clock)
Machine-readable companion: `dataset_acquisition/reports/p4_3_2_multiclass_expansion_report.json`

Every number in this report is derived from real on-disk artifacts (per-class
orchestrator status JSONs, conversion reports, provenance manifests, visual-QA
`qa_data.json`, and the analysis roll-up). Where a value could not be measured,
it is recorded as **NOT MEASURED** or **BLOCKED** — never invented.

---

## 1. Sprint Overview

P4.3.2 expands the real EcoTrace dataset from the single-class smartphone pilot
into a controlled **three-class** acquisition batch: **tablet, monitor, printer**.
The workflow followed was: BUILD → TEST → SMALL REAL ACQUISITION → VALIDATE →
VISUAL QA PREPARATION → STOP. No commit, no push, no P4.3.3, no model work,
no Dataset v1.0 release.

## 2. Scope and Constraints

- Reused the frozen P4.3.1 orchestrator `scripts/acquire_openimages_multiclass.py`.
  No second downloader was created; no website was scraped; no datasets were mixed.
- The nine BLOCKED_UNMAPPED classes were not touched. No model was downloaded or
  retrained. Dataset v1.0 was not released.
- Only the three requested classes were acquired. Acquisition wrote to isolated
  per-class staging directories under
  `dataset_acquisition/staging/openimages_multiclass_v1/`.

## 3. Data Source

Single source: **Open Images V7**. Confirmed in every per-class status JSON
(`"source": "Open Images V7"`) and in each provenance manifest.

## 4. Taxonomy Basis

Classes and IDs were loaded dynamically from
`intelligence/device_ai/dataset/taxonomy.py` (frozen taxonomy **v1.0.0**). No
alternate class list was created and no class ID was assumed. Verified live IDs:
**tablet = 2, monitor = 5, printer = 8**.

## 5. Source Class Mapping (verified, not guessed)

Mappings were read from the actual P4.3.1 manifest, not invented:

| EcoTrace class | class_id | Open Images V7 class | Mapping status |
|----------------|----------|----------------------|----------------|
| tablet         | 2        | Tablet computer      | MAPPED         |
| monitor        | 5        | Computer monitor     | MAPPED         |
| printer        | 8        | Printer              | MAPPED         |

No mapping was ambiguous; no class was invented or padded.

## 6. Acquisition Target and Ceiling Policy

Requested ceiling: **100 images/class** (a ceiling, not a promise). Where Open
Images supplied fewer than requested, the actual count is recorded; the dataset
was never padded and no missing image was fabricated.

## 7. Execution: Dry-Run First

All three classes were dry-run before any real download. Each dry-run reported
`state: DRY_RUN`, `mapping_status: MAPPED`, `requested: 100`, `dry_run: true`
(`p4_3_2_dryrun_tablet.json`, `p4_3_2_dryrun_monitor.json`,
`p4_3_2_dryrun_printer.json`). No dry-run wrote image data.

## 8. Execution: Bounded Real Acquisition

Each class was then acquired as a controlled, bounded operation. When printer
failed, acquisition of that class stopped and was investigated before moving on;
the failure was not hidden. Per-class terminal states:

| Class   | State           | Downloaded | Converted | Staging dir                                   |
|---------|-----------------|-----------:|----------:|-----------------------------------------------|
| tablet  | QA_PENDING      | 100        | 100       | `openimages_multiclass_v1/openimages_tablet_v1`  |
| monitor | QA_PENDING      | 99         | 99        | `openimages_multiclass_v1/openimages_monitor_v1` |
| printer | DOWNLOAD_FAILED | 0          | 0         | (none — download never produced data)         |

## 9. Acquisition Accounting (per class, no unexplained counts)

Derived from each class's `conversion_report.json`, provenance manifest and the
analysis roll-up:

**tablet (id 2)** — requested 100, downloaded 100, source images found 100,
source labels found 100, converted 100, conversion_failed 0, valid_images 100,
valid_annotations 100, total boxes 124, within-class exact duplicates 0,
within-class near duplicates 2.

**monitor (id 5)** — requested 100, downloaded 99, source images found 99,
source labels found 99, converted 99, conversion_failed 0, valid_images 99,
valid_annotations 99, total boxes 161, within-class exact duplicates 0,
within-class near duplicates 1.

**printer (id 8)** — requested 100, downloaded 0, converted 0, valid_images 0,
valid_annotations 0. **NOT MEASURED** (no data staged). See §17.

## 10. Provenance

Every staged image retains full provenance via the frozen P4.3.1 mechanism. Each
`provenance/provenance_manifest.json` record carries: `source` ("Open Images V7"),
`source_class`, `source_image_filename`, `source_annotation_filename`,
`ecotrace_class`, `ecotrace_class_id`, `sha256`, `width`, `height`,
`object_count`, `conversion_version` ("openimages-multiclass-v1"),
`conversion_timestamp`, `taxonomy_version` ("1.0.0"). Provenance records:
tablet 100, monitor 99. Provenance SHA-256 verified: tablet 100/100,
monitor 99/99. Provenance missing: 0. SHA mismatched: 0.

License note (per record `provenance_note`):
`images=per-image-Flickr(VARY-verify); annotations=CC-BY-4.0(Google)`.

## 11. Conversion

Conversion used the frozen `scripts/convert_openimages_to_yolo.py`
(version `openimages-multiclass-v1`). The converter was not rewritten, its
normalization math was not modified, no invalid box was clipped and no source
annotation was silently repaired. `conversion_errors.json` `error_count` is
**0** for both staged classes.

## 12. Image Validation (frozen P4.2.x tooling, no threshold changes)

Frozen thresholds applied: blur 100.0, dark 40.0, bright 220.0, min_dim 32,
max_dim 12000, duplicate hamming 5. Structural `ImageValidator` issue counts
(CORRUPTED_IMAGE / RESOLUTION_* / INVALID_ASPECT_RATIO / FILE_TOO_LARGE /
DUPLICATE_* / UNSUPPORTED_EXTENSION):

| Class   | Structural image issues |
|---------|-------------------------|
| tablet  | 0                       |
| monitor | 0                       |
| printer | NOT MEASURED            |

## 13. Image Quality Flags (reported, not auto-rejected)

Quality flags are advisory metadata; no blurry image was auto-rejected and no
difficult sample was auto-approved. Flag counts:

| Class   | Blurry | Dark | Bright |
|---------|-------:|-----:|-------:|
| tablet  | 23     | 1    | 0      |
| monitor | 12     | 2    | 0      |
| printer | NOT MEASURED | NOT MEASURED | NOT MEASURED |

## 14. Annotation Validation

`validate_annotations` issue counts are **0** (empty `annotation_issue_counts`)
for both staged classes. Pairing is exact — images without labels: 0; labels
without images: 0 (tablet 100↔100, monitor 99↔99). Class-ID validation: every
box carries the correct class id (tablet `{"2": 124}`, monitor `{"5": 161}`);
no foreign or out-of-range class id present. No Open Images annotation was
silently corrected — human QA remains authoritative.

## 15. QA Boundary

Every converted image ends **QA_PENDING**. No new data was marked QA_ACCEPTED
automatically. Per-class QA counters: tablet qa_pending 100 / qa_accepted 0 /
qa_rejected 0; monitor qa_pending 99 / qa_accepted 0 / qa_rejected 0. The batch
QA boundary constant is `QA_PENDING`.

## 16. Visual QA Preparation

Annotated previews and one contact sheet per class were generated with
`scripts/make_visual_qa_multiclass.py` (read-only w.r.t. staged data). Each
`manual_review/qa_data.json` carries `"qa_status": "QA_PENDING"`:

| Class   | Previews | Contact sheet | Objects tagged | qa_status  |
|---------|---------:|:-------------:|---------------:|------------|
| tablet  | 100      | yes           | 124            | QA_PENDING |
| monitor | 99       | yes           | 161            | QA_PENDING |

Generating previews is **not** QA sign-off. Visual QA is **NOT COMPLETE** — these
artifacts exist only to support a human reviewer. Final state remains QA_PENDING
because no human review has occurred.

## 17. Printer — Honest Failure Surface (BLOCKED)

Printer is recorded as **DOWNLOAD_FAILED / BLOCKED**, quality **NOT MEASURED**.
It is not silently dropped. Root cause, captured verbatim in
`p4_3_2_real_printer.json`:

```
numpy._core._exceptions._ArrayMemoryError: Unable to allocate 111. MiB for an
array with shape (14610229,) and data type object
```

The failure occurs inside the vendored OIDv4_ToolKit
(`csv_downloader.TTV → pandas.read_csv`) while loading the ~14.6M-row Open Images
train bounding-box CSV — a genuine host-memory constraint, not a mapping or
data-absence problem (the mapping `Printer → printer` is MAPPED; tablet and
monitor read the same CSV successfully earlier in the run). One controlled bounded
retry was attempted and reproduced the same error, confirming the blocker.

Per spec, the response was: do **not** edit the vendored toolkit, do **not** build
a second downloader, do **not** fabricate counts. Printer awaits a
higher-memory environment or a chunked-read remediation in a future sprint.

## 18. Duplicate Detection (within-class and cross-class)

Within-class (frozen `DuplicateDetector`, hamming 5): tablet — 0 exact,
2 near; monitor — 0 exact, 1 near. Near-duplicates are reported, not deleted;
removal requires provenance review.

Cross-class (tablet vs monitor; printer produced no data): **0** cross-class
duplicate pairs out of 3 total pairs considered in the batch. No duplicate was
auto-deleted.

## 19. Pilot / Laptop / Smartphone Protection

Live fingerprints were compared against the pre-acquisition baseline
(`p4_3_2_pilot_baseline.json`). All three protected pilots are **unchanged**:

| Protected pilot                    | Baseline files / bytes | Live files / bytes | Unchanged |
|------------------------------------|------------------------|--------------------|:---------:|
| openimages_laptop_v1               | 72 / 10,525,045        | 72 / 10,525,045    | yes       |
| openimages_laptop_canonical_v1     | 47 / 6,110,063         | 47 / 6,110,063     | yes       |
| openimages_smartphone_v1           | 15 / 1,003,504         | 15 / 1,003,504     | yes       |

Nothing unexpected changed; the STOP-on-change condition was not triggered.

## 20. Dataset v1.0 Status and Stop Condition

- `is_dataset_v1`: **false** — **Dataset v1.0 is NOT RELEASED.**
- `is_released`: **false**. No merge into production `datasets/`. No model exists;
  no mAP/precision/recall is claimed.
- Two classes are staged and QA_PENDING (tablet, monitor); one is BLOCKED
  (printer). All staged data awaits **explicit human review**.

**STOP.** Per the sprint contract, work halts here: no further acquisition, no
touching blocked classes, no QA_ACCEPTED, no v1.0 release, no training, no
commit, no push, and P4.3.3 is not started. Awaiting explicit human review.
