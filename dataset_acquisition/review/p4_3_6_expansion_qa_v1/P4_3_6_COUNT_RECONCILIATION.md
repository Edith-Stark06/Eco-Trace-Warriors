# P4.3.6 — Count Reconciliation (119 candidates vs 359 on-disk images)

**Audit type:** read-only forensic reconciliation. **Nothing was modified, deleted, or committed.**
**Date:** 2026-08-16
**Trigger:** the P4.3.7 router-automation preflight measured the protected P4.3.6 tree
(`dataset_acquisition/staging/p4_3_6_expansion_v1`) as **359 images**, whereas the P4.3.6
acquisition report and QA evidence state **119 retained candidates**. This document explains
the difference exactly and states the authoritative candidate count.

> **Method / honesty note.** Every count and hash below was measured directly with read-only
> tools (`find`, `sha256sum`, `comm`, `cat`, plus the frozen `preflight.fingerprint_tree`).
> No count is inferred. The frozen duplicate threshold, taxonomy, split ratios, and readiness
> gates were **read, never changed**. The two protected trees were fingerprinted before this
> audit began and again at the end; both are byte-identical (§9).

---

## 1. Verdict (definitive)

- **There are NOT 359 distinct P4.3.6 candidates.** The tree holds **121 unique images**
  (measured by distinct SHA-256), physically materialised across **three parallel working
  directories**, plus a small number of provenance/QA JSON artifacts.
- **The authoritative P4.3.6 candidate count is `119` images / `174` boxes across `6` classes.**
  This is the deduplicated, visually-QA'd, annotation-validated set — the same 119 the P4.3.6
  `COVERAGE_REPORT.md` reports.
- **None of the "extra" 240 images are additional candidate data.** They are 238 redundant
  copies of the 119 candidates plus 2 intentionally-excluded near-duplicates (§6).
- **Use `119` for all future coverage/split calculations. Do not use 359, 121, or 240.**

---

## 2. The headline arithmetic — `359 = 121 + 119 + 119`

`find … -name '*.jpg'` over the protected tree returns **359** files. They partition cleanly by
directory into three copies of the same acquisition wave:

| # | Subtree | Role | .jpg | .txt |
|---|---|---|---:|---:|
| 1 | `openimages_<class>_v1/images` + `/labels` | Converter output (staging), **pre-dedup** | 121 | 121 |
| 2 | `_qa_kept/<class>/images` + `/labels` | Deduped + visually-QA'd **retained set** | 119 | 119 |
| 3 | `_validate/images/<class>` + `/labels/<class>` | Same 119 re-laid-out for the frozen `AnnotationValidator` | 119 | 119 |
| | **Total images** | | **359** | |
| | **Total labels** | | | **359** |

Plus **18 JSON** artifacts (§4). Full tracked-file total: **359 + 359 + 18 = 736**, which is
exactly the file count the preflight fingerprint reports for this tree.

So the "359" is **not** a candidate count — it is the acquisition wave counted **three times**
(once per pipeline stage directory), because each stage copies rather than moves its inputs.

---

## 3. Distinct-content proof (why 359 physical files ≠ 359 images)

Measured over all 359 `.jpg`:

| Measurement | Value | Meaning |
|---|---:|---|
| Physical `.jpg` files | 359 | files on disk |
| Distinct SHA-256 contents | **121** | genuinely unique images |
| Distinct basenames (stems) | **121** | unique Open Images IDs |
| Distinct `(basename, sha256)` pairs | **121** | ⇒ each stem has exactly **one** content hash |

Because distinct basenames (121) equals distinct `(basename, sha256)` pairs (121), **every
cross-tree copy of a given stem is byte-identical**. Spot-verified against provenance, e.g.
`laptop/00767fb6565581c6.jpg` in all three trees hashes to
`805e3223e5e3583a7cfc9bf8f7bdca7368c7187a76e5958c29a748ac6de9d6a6`, matching its
`provenance_manifest.json` record.

**Identity relationship between the 359 and the 119:** the 359 physical files reduce to 121
unique images; of those 121, exactly **119** are the retained candidate set (present in all
three trees) and **2** are excluded near-duplicates (present only in the converter-output tree).
The 119 are a strict subset of the 121.

---

## 4. Directory breakdown & file classification

```
staging/p4_3_6_expansion_v1/
├── openimages_laptop_v1/       ┐  CONVERTER OUTPUT (pre-dedup staging), one dir per class
│   ├── images/  (*.jpg)        │    laptop 21, television 20, keyboard 20,
│   ├── labels/  (*.txt)        │    mouse 20, camera 20, headphones 20  = 121 img + 121 lbl
│   ├── provenance/provenance_manifest.json   (SHA-256 + source class per image)
│   └── reports/conversion_report.json, conversion_errors.json
├── openimages_television_v1/   │
├── openimages_keyboard_v1/     │  → 6 class dirs × 3 JSON = 18 JSON artifacts
├── openimages_mouse_v1/        │
├── openimages_camera_v1/       │
├── openimages_headphones_v1/   ┘
├── _qa_kept/<class>/           ┐  RETAINED CANDIDATE SET (post-dedup, post-visual-QA)
│   ├── images/ (*.jpg)         │    laptop 20, television 19, keyboard 20,
│   └── labels/ (*.txt)         ┘    mouse 20, camera 20, headphones 20  = 119 img + 119 lbl
└── _validate/                  ┐  ANNOTATION-VALIDATION LAYOUT (same 119, class-partitioned)
    ├── images/<class>/ (*.jpg) │    119 img + 119 lbl
    └── labels/<class>/ (*.txt) ┘
```

| File kind | Count | Classification |
|---|---:|---|
| `.jpg` in `openimages_*_v1` | 121 | Converted candidates (staging), incl. 2 later-excluded near-dupes |
| `.jpg` in `_qa_kept` | 119 | **Authoritative retained candidates** (copies) |
| `.jpg` in `_validate` | 119 | Validation working copies (copies of the same 119) |
| `.txt` labels | 359 | YOLO labels mirroring the images 1:1 (121+119+119) |
| `provenance_manifest.json` | 6 | Provenance artifact (per source class) |
| `conversion_report.json` | 6 | QA/conversion artifact |
| `conversion_errors.json` | 6 | QA/conversion artifact (0 errors each) |

There are **no** stray source archives, no orphan images, and no unexplained files. Nothing in
the tree is fabricated data — all 121 unique images carry Open Images V7 provenance with SHA-256.

---

## 5. Per-class image counts

| ecotrace class | class_id | Converter output (`openimages_*`) | Retained (`_qa_kept` / `_validate`) | Dropped by dedup |
|---|---:|---:|---:|---:|
| laptop | 0 | 21 | 20 | 1 |
| television | 7 | 20 | 19 | 1 |
| keyboard | 9 | 20 | 20 | 0 |
| mouse | 10 | 20 | 20 | 0 |
| camera | 14 | 20 | 20 | 0 |
| headphones | 17 | 20 | 20 | 0 |
| **total** | | **121** | **119** | **2** |

(class_ids resolved from the frozen 19-class taxonomy v1.0.0.) These retained per-class counts
match the P4.3.6 `COVERAGE_REPORT.md` §2 table exactly.

---

## 6. What the "extra 240" (359 − 119) actually are

| Component | Files | Legitimate additional candidates? |
|---|---:|---|
| 2nd + 3rd copies of the 119 retained set (`_qa_kept` + `_validate`) | 119 × 2 = **238** | No — redundant working-tree copies |
| Excluded near-duplicates, present only in `openimages_*` (`laptop/f663d03a10e841bf.jpg`, `television/34932ec3bf06d3ef.jpg`) | **2** | No — dropped by the duplicate gate |
| **Total "extra"** | **240** | **None are additional candidates** |

**Answer to "are any of the additional 240 legitimate candidate data?": No — zero.**

---

## 7. The exact files in the P4.3.6 duplicate gate

Source of truth: `duplicate_evidence.json` (this directory). The frozen detector
`device_ai.dataset.duplicates.DuplicateDetector` was run at **Hamming threshold 5 (not weakened)**.

- **Scenario A — expansion vs itself:** input = the **121** converter-output images;
  duplicates found = **0**.
- **Scenario B — combined, candidate-first:** input = **252** protected P4.3.5 candidate images
  **+ 121** expansion images = **373** total, scanned candidate-first so only expansion samples
  can be flagged. Flagged = **2**:

| Dropped (expansion) | Nearest kept (P4.3.5 candidate) | Hamming dist | Exact (sha256_equal) |
|---|---|---:|---|
| `expansion/laptop/f663d03a10e841bf.jpg` | `candidate/tablet/d4285391c9dbfbe8.jpg` | 1 | false |
| `expansion/television/34932ec3bf06d3ef.jpg` | `candidate/tablet/293b420b3319821c.jpg` | 5 | false |

After dropping the 2, the pre-merge combined set is **371** with **0** residual duplicates.
Removal policy (verified in the evidence): only expansion samples are dropped; source staging
is never modified; the 252 candidate is never touched.

---

## 8. The exact files in the 119-image QA package

The human-QA package is `dataset_acquisition/review/p4_3_6_expansion_qa_v1/` (this directory):
per-class `previews/qaNN_<stem>.jpg`, `contact_sheet.jpg`, and `qa_data.json`.

- Preview images measured: **119** (laptop 20, television 19, keyboard 20, mouse 20, camera 20,
  headphones 20).
- **Set equality proven:** the 119 preview stems are exactly equal to the 119 `_qa_kept` stems
  (both directional set-differences are empty).
- The 2 dedup-excluded stems (`f663d03a10e841bf`, `34932ec3bf06d3ef`) are **absent** from the QA
  package — i.e. visual QA was performed on the post-dedup 119, never on the excluded pair.
- Annotation validation over the same 119 (`_validate` tree): **119 labels / 174 boxes, 0
  issues** (`annotation_validation.md`). All 119 remain **QA_PENDING** (`signoff_template.json`);
  the sprint decision was "Leave QA_PENDING" and **no merge was performed**.

---

## 9. Protected-state confirmation (measured, read-only)

Fingerprints recomputed with the frozen `preflight.fingerprint_tree` and compared to the values
recorded in the P4.3.7 report:

| Tree | Files | Images | Labels | Content hash (prefix) | Expected | Match |
|---|---:|---:|---:|---|---|---|
| `p4_3_5_dataset_v1_candidate` | 505 | 252 | 252 | `567cdd455fcd` | `567cdd455fcd` | ✅ |
| `p4_3_6_expansion_v1` | 736 | 359 | 359 | `e12ab28e63d2` | `e12ab28e63d2` | ✅ |

`git status --short`: only untracked (`??`) additions — no tracked file modified.
`git diff --stat`: empty.

Note: `staging/p4_3_6_expansion_v1` is a git-ignored workspace, so its 736 files never appear in
`git status`; the merged preview referenced by the report (`staging/p4_3_6_merged_preview/`, 371)
is likewise git-ignored and was **not** created or altered by this audit.

---

## 10. Reconciliation against the P4.3.6 acquisition report & QA evidence

| Claim in P4.3.6 evidence | This audit's measurement | Agree? |
|---|---|---|
| `COVERAGE_REPORT.md`: "119 samples survived the duplicate cross-check" | `_qa_kept` = 119, `_validate` = 119 | ✅ |
| `COVERAGE_REPORT.md`: "2 … near-duplicates … excluded" | 121 − 119 = 2, named & evidenced (§7) | ✅ |
| `COVERAGE_REPORT.md` per-class kept (20/19/20/20/20/20) | Measured identical (§5) | ✅ |
| `COVERAGE_REPORT.md`: total 174 boxes | `_qa_kept` labels = 174 boxes | ✅ |
| `annotation_validation.md`: 119 labels / 174 boxes / 0 issues | Matches `_validate` tree | ✅ |
| `duplicate_evidence.json`: threshold 5, candidate-first, 373 combined, 2 dropped | Matches (§7) | ✅ |
| P4.3.7 report: P4.3.6 = 359 images / 736 files | Confirmed; 359 = 121+119+119 (§2) | ✅ |
| Protected 252 candidate unchanged | Hash `567cdd455fcd` matches (§9) | ✅ |

**Conclusion:** there is no data discrepancy or integrity problem. The 359 is a raw physical
file count that triple-counts a single 119-image wave across three pipeline-stage directories
(plus the 2 excluded near-dupes retained only in the converter-output stage). The P4.3.6 report's
**119 / 174 / 6 classes** is correct and remains the authoritative candidate figure.

---

## 11. Authoritative figures for future work

| Quantity | Value |
|---|---:|
| **P4.3.6 candidate images (authoritative)** | **119** |
| **P4.3.6 candidate boxes** | **174** |
| **P4.3.6 classes added** | **6** (laptop, television, keyboard, mouse, camera, headphones) |
| Unique images physically present in the staging tree | 121 (= 119 kept + 2 excluded) |
| Coverage if merged (P4.3.5 252 + P4.3.6 119) | 10 / 19 classes; audit still INCOMPLETE (9 missing + split too thin) |

Merge status remains **DEFERRED / QA_PENDING**; no release was built (readiness INCOMPLETE).
