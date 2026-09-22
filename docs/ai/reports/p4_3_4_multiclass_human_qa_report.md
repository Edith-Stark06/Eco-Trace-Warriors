# P4.3.4 — Multi-Class Human QA & Dataset Candidate Assessment Report

Status: Manual-review checkpoint (**MULTICLASS_REVIEW_REQUIRED**) — reviewer
package assembled, **nothing certified, nothing released**
Sprint: P4.3.4 — Multi-class human QA & dataset candidate assessment
Scope: the four real Open Images V7 acquisitions produced by P4.3.x —
`smartphone`, `tablet`, `monitor`, `printer` (the completed `laptop` pilot is
excluded and untouched)
Audience: annotation reviewers, QA leads (human sign-off required)

---

> **What this report is.** It is the *human reviewer package* for the four
> multi-class acquisitions staged by P4.3.x. It surfaces — per class — a
> deterministic data inventory, the automated pre-QA gate result, the visual QA
> material, a per-image sign-off template, a deterministic second-review sample,
> the (empty) Dataset-v1.0 candidate inventory, and a before/after integrity
> proof. It does **nothing else**. It **certifies nothing**: every one of the
> 301 reviewable items is `PENDING_REVIEW`, the human decision fields are
> deliberately blank, and no item was auto-accepted or auto-rejected.
>
> **Dataset v1.0 is NOT released. No human QA decision has been fabricated or
> inferred.**

> **Non-destruction guarantee (proven, not asserted).** The generator is
> strictly read-only on **both** the immutable Open Images source trees and the
> per-class staging directories. It writes **only** under
> `dataset_acquisition/review/p4_3_4_multiclass_qa_v1/`, which lives outside every
> dataset artifact. A SHA-256 snapshot of every source and staging image/label is
> taken before and after generation and compared; the comparison is recorded in
> `integrity_verification.json` (`all_unchanged: true`, 602 source + 602 staging
> files checked, zero added/removed/modified). No metric is invented — structural
> validity comes from the frozen `ImageValidator` (Gate A) and the P4.2.2
> `validate_annotations` layer (Gate B); blur numbers come from the frozen
> `device_ai.dataset.metadata.blur_score` against the frozen blur threshold
> (`100.0`); class names/ids come from the frozen taxonomy (v`1.0.0`).

> **How to reproduce.** From the repository root:
> ```
> python scripts/build_multiclass_qa_p434.py
> ```
> All inputs default to `dataset_acquisition/staging`; the only timestamp is
> injected (`--timestamp`, default `2026-08-10T00:00:00+00:00`) and the
> second-review sample uses a fixed seed (`--sample-seed`, default `20260810`),
> so identical inputs produce byte-identical machine-readable artifacts. Artifacts
> land under `dataset_acquisition/review/p4_3_4_multiclass_qa_v1/`.

---

## 1. Executive summary

The four real P4.3.x acquisitions were assembled into a single, read-only human
QA package. Every count below is read off real files and provenance manifests —
nothing is hard-coded.

| Metric | Value |
| --- | --- |
| Classes reviewed | 4 (`smartphone`, `tablet`, `monitor`, `printer`) |
| Total reviewable images | **301** |
| Total labels | 301 |
| Total objects (boxes) | 419 |
| Automated Gate A (image) pass | **4 / 4 classes** |
| Automated Gate B (annotation) pass | **4 / 4 classes** |
| Items `PENDING_REVIEW` | **301 / 301** |
| Human decisions recorded by tooling | **0** (blank, by design) |
| Second-review sample size | 60 (fixed seed `20260810`, ~20% per class) |
| Dataset v1.0 candidates promoted | **0** |
| Source trees unchanged | **true** (602 files) |
| Staging trees unchanged | **true** (602 files) |
| SHA-256 reconciled vs manifest | **true** (all 301 images) |

**Dataset v1.0 status: NOT RELEASED.** No image has been promoted; promotion
requires an explicit human `QA_ACCEPTED` decision that this tooling never makes.

## 2. Scope and constraints honoured

- **No existing commits modified.** No reset, rebase, or force-push; the working
  tree adds only new, untracked files (Section 11).
- **Frozen pipeline untouched.** `git diff -- intelligence/device_ai/device_ai/`
  is empty. The generator *imports* the frozen validators/taxonomy; it does not
  modify them.
- **No model trained, no dataset acquired.** This sprint only reads the artifacts
  P4.3.x already staged.
- **`laptop` pilot excluded.** The completed pilot (its own P4.2.5 sign-off) is
  skipped by name and never read or written.
- **Nothing committed automatically.** This report and the package are left in the
  working tree for human review.

## 3. Acquired-data inventory (Part 1)

Source: **Open Images V7**. Counts are derived from each class's
`provenance/provenance_manifest.json` and the real files on disk; each staged
image's SHA-256 is recomputed and reconciled against its manifest record.

| Class | id | images | labels | objects | SHA-256 reconciled | staging root |
| --- | --- | --- | --- | --- | --- | --- |
| smartphone | 1 | 6 | 6 | 13 | true | `dataset_acquisition/staging/openimages_smartphone_v1` |
| tablet | 2 | 100 | 100 | 124 | true | `.../openimages_multiclass_v1/openimages_tablet_v1` |
| monitor | 5 | 99 | 99 | 161 | true | `.../openimages_multiclass_v1/openimages_monitor_v1` |
| printer | 8 | 96 | 96 | 121 | true | `.../openimages_multiclass_v1/openimages_printer_v1` |
| **Total** | | **301** | **301** | **419** | **true** | |

Per-image SHA-256 tables, provenance/conversion-report pointers and any existing
visual-QA artifacts are recorded in `inventory.json` / `inventory.md`. Classes
are discovered dynamically by walking
`staging/**/provenance/provenance_manifest.json`, so the top-level `smartphone`
class and the nested `tablet`/`monitor`/`printer` classes are all found without
hard-coded paths.

## 4. Automated pre-QA gate (Part 2)

Two frozen gates run per class. A gate PASS is **structural only** and is **not**
a human QA sign-off.

| Class | Gate A (image) | Gate B (annotation) | image issues | annotation issues | duplicate hashes |
| --- | --- | --- | --- | --- | --- |
| smartphone | PASS | PASS | 0 | 0 | 0 |
| tablet | PASS | PASS | 0 | 0 | 0 |
| monitor | PASS | PASS | 0 | 0 | 0 |
| printer | PASS | PASS | 0 | 0 | 0 |

- **Gate A** — frozen `device_ai.dataset.image_validation.ImageValidator`
  (corruption, dimensions, aspect ratio, byte size, duplicate filenames/hashes).
- **Gate B** — P4.2.2 `validate_annotations.validate` (frozen `AnnotationValidator`
  plus the layered `BOX_OUT_OF_BOUNDS` / `DUPLICATE_BOX` / `EMPTY_LABEL` checks).

Full machine-readable detail is in `preqa_report.json` / `preqa_report.md`.

## 5. Visual QA material (Part 3)

For every class the package renders one annotated preview per image (converted
YOLO boxes overlaid, box tags resolved from the frozen taxonomy, captioned with
filename / dimensions / box count / blur) and tiles them into deterministic
contact-sheet pages of at most 30 tiles. Every `qa_data.json` carries
`qa_status: QA_PENDING`.

| Class | previews | contact-sheet pages |
| --- | --- | --- |
| smartphone | 6 | 1 |
| tablet | 100 | 4 |
| monitor | 99 | 4 |
| printer | 96 | 4 |

Material is under `dataset_acquisition/review/p4_3_4_multiclass_qa_v1/<class>/`
(`previews/`, `contact_sheet_pNN.jpg`, `qa_data.json`). The renderer is the shared
`make_visual_qa_multiclass` module, so blur numbers and tags agree with P4.3.2.

## 6. Sign-off template (Parts 4/5)

`signoff_template.json` holds one machine-readable row per image (301 rows). Each
row carries the item id, class, canonical + source filename, source image id,
SHA-256, box count, an advisory `issue_summary` and `proposed_decision`, and the
human fields — all blank:

```
"status": "PENDING_REVIEW", "human_decision": "", "reviewer": "",
"review_date": "", "notes": ""
```

The only decision states a reviewer may record are exactly:

`PENDING_REVIEW` · `QA_ACCEPTED` · `QA_REVIEW_REQUIRED` · `QA_REJECTED`

`proposed_decision` uses the same vocabulary but is an **advisory** suggestion
derived only from the frozen gates + blur flag; it never sets `status` without an
explicit human edit. At generation:

| Field | Value |
| --- | --- |
| Total items | 301 |
| `status == PENDING_REVIEW` | 301 (100%) |
| Distinct `status` values | `{PENDING_REVIEW}` |
| Distinct `human_decision` values | `{""}` (all blank) |
| `proposed_decision == QA_ACCEPTED` (advisory) | 249 |
| `proposed_decision == QA_REVIEW_REQUIRED` (advisory) | 52 |

The 52 review-hints are driven by the frozen blur metric / gate codes and are
suggestions only; no item is accepted or rejected by the tool.

## 7. Second-review sample (Part 6)

A deterministic, representative second-review sample is drawn with a fixed seed
(`20260810`) and a per-class fraction (`0.2`, at least one item per class), so an
independent reviewer can re-check a cross-class subset. All entries are
`PENDING_REVIEW`.

| Class | sampled |
| --- | --- |
| smartphone | 1 |
| tablet | 20 |
| monitor | 20 |
| printer | 19 |
| **Total** | **60** |

Detail is in `second_review_sample.json` / `second_review_sample.md`. Re-running
the generator on the same inputs produces a byte-identical sample.

## 8. Dataset v1.0 candidate inventory (Part 7)

`candidate_inventory.json` / `candidate_inventory.md` admit **only** items whose
`status == "QA_ACCEPTED"`. At generation every item is `PENDING_REVIEW`, so:

| Metric | Value |
| --- | --- |
| Reviewable items | 301 |
| Promoted candidates | **0** |
| `is_released` | false |
| `dataset_v1_released` | false |

> Human QA decisions are pending; no images have been promoted.
> **Dataset v1.0 is NOT released.**

## 9. Integrity verification (Part 8)

Every source and staging tree was SHA-256-snapshotted before and after
generation and compared. Result: `all_unchanged: true`.

| Class | source files | source unchanged | staging files | staging unchanged |
| --- | --- | --- | --- | --- |
| smartphone | 12 | true | 12 | true |
| tablet | 200 | true | 200 | true |
| monitor | 198 | true | 198 | true |
| printer | 192 | true | 192 | true |
| **Total** | **602** | **true** | **602** | **true** |

No `added`, `removed`, or `modified` path in any class. In addition, all 301
staged image SHA-256 values reconcile against their provenance manifest records
(`all_sha256_reconciled: true`); a single mismatch would have aborted the build
with exit code 1 before any package was written.

## 10. Verification: tests, lint, types

| Gate | Command | Result |
| --- | --- | --- |
| New tests (Part 9) | `pytest tests/test_multiclass_qa_p434.py` | **25 passed** |
| P4.3.x acquisition tests | `pytest tests/test_multiclass_expansion_p432.py tests/test_lowmem_acquisition_p433.py` | **42 passed** |
| Full `device_ai` suite | `pytest` (from `intelligence/device_ai`) | **894 passed** |
| Lint (new code) | `ruff check scripts/build_multiclass_qa_p434.py tests/test_multiclass_qa_p434.py` | **clean** |
| Types (new code) | `mypy scripts/build_multiclass_qa_p434.py` | **clean** ¹ |
| Whitespace/conflict | `git diff --check` | **clean** |
| Frozen pipeline | `git diff -- intelligence/device_ai/device_ai/` | **empty (untouched)** |

¹ The only mypy finding under the run is a **pre-existing** `no-any-return` in the
unmodified `scripts/validate_annotations.py:75` (present on HEAD, not introduced
here). The new script is mypy-clean.

The new test file (`tests/test_multiclass_qa_p434.py`, 25 tests) covers dynamic
discovery, pilot exclusion, snapshot/diff determinism, SHA-256 reconciliation and
mismatch detection, all-`PENDING_REVIEW` + blank human fields, the advisory-only
`proposed_decision`, deterministic second-review sampling, candidate-inventory
exclusion of `PENDING_REVIEW` and inclusion only of `QA_ACCEPTED`, read-only
behaviour w.r.t. source + staging, end-to-end determinism, malformed/missing
label tolerance, missing conversion-report tolerance, the SHA-256-mismatch abort,
and every CLI usage error.

## 11. Files created / modified

**Created (production):**
- `scripts/build_multiclass_qa_p434.py` — the read-only QA package generator
  (Parts 1–8), class-agnostic, reusing the frozen validators and the shared
  visual-QA renderer.
- `intelligence/device_ai/tests/test_multiclass_qa_p434.py` — 25 offline tests
  (Part 9).
- `docs/ai/reports/p4_3_4_multiclass_human_qa_report.md` — this report (Part 12).

**Generated (review package, under
`dataset_acquisition/review/p4_3_4_multiclass_qa_v1/`):**
`inventory.{json,md}`, `preqa_report.{json,md}`, `signoff_template.json`,
`second_review_sample.{json,md}`, `candidate_inventory.{json,md}`,
`integrity_verification.json`, `package_manifest.json`, and per-class
`<class>/{previews/,contact_sheet_pNN.jpg,qa_data.json}`.

**Modified (tracked):** none. `git status` shows only the three new untracked
paths above plus the review package directory. No frozen pipeline file, no
staging data, and no existing commit was changed.

## 12. What this package does NOT do

- It does **not** certify any class or declare Dataset v1.0 ready.
- It does **not** change any item's `status` from `PENDING_REVIEW`, and it fills
  no `human_decision` / `reviewer` / `review_date`.
- It does **not** promote any image (candidate inventory is empty).
- It does **not** modify any source or staging image/label (proven by
  `integrity_verification.json`).
- It does **not** invent a quality/accuracy metric or a new threshold.
- It does **not** train anything, download anything, or touch the `laptop` pilot.

## 13. Recommended next action

1. A human reviewer opens each class's `contact_sheet_pNN.jpg` and edits
   `signoff_template.json`, setting `status` to one of the four allowed states
   and filling `human_decision` / `reviewer` / `review_date` per image.
2. An independent reviewer re-checks the 60-item `second_review_sample.json`.
3. Once decisions are recorded, a **separate** promotion step (not this tool)
   may assemble the Dataset-v1.0 candidate set from the `QA_ACCEPTED` items — a
   distinct, human-gated sprint. Until then, Dataset v1.0 remains unreleased.

## 14. Dataset v1.0 status (explicit)

**Dataset v1.0 is NOT RELEASED.** Zero images are promoted. No human QA decision
has been fabricated or inferred by any tooling in this sprint. Every reviewable
item is `PENDING_REVIEW` pending an explicit human decision.
