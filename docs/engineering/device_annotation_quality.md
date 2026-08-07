# Device Annotation Quality — Engineering Reference

**Sprint:** P4.1.6 — Dataset Annotation & Quality Assurance Framework (PART 5)
**Component:** Device Intelligence Engine (DIE) — YOLO Detector (milestone M1.4)
**Status:** Active
**Related:** `08_AI.md`, `device_detection_annotation.md` (P4.1.2),
`device_dataset_acquisition.md` (P4.1.4), `device_collection_process.md` (P4.1.5)
**Scope:** The **engineering-facing** view of the annotation QA framework — how
the human-facing governance docs (PARTs 1–4, 6) map onto the **frozen** P4.1.2
dataset code, the P4.1.4 acquisition runbook, and the P4.1.5 collection workflow.
It downloads nothing, trains nothing, and changes no code, schema, or interface.

---

## 1. Where This Fits

The AI-facing docs (`docs/ai/`) tell annotators, reviewers, and the QA lead
**what** to do. This document tells the engineer **which frozen code and which
prior-sprint contracts** realise each QA step, so the framework stays grounded in
the real pipeline rather than aspiration.

```
 docs/ai/  (people)                    code + prior sprints (frozen)              docs/engineering/ (this)
 ────────────────────────              ────────────────────────────────          ────────────────────────
 device_annotation_guidelines ─────▶   dataset/validator.py (structural)   ◀────  section 3
 annotation_review_manual     ─────▶   dataset/annotation_statistics.py    ◀────  section 4
 quality_assurance            ─────▶   dataset/image_validation.py (Gate A)◀────  section 5
 dataset_v1_definition_of_done─────▶   dataset/{split,version,release}     ◀────  section 6
```

**No code is added or modified in P4.1.6.** Every module named below already
exists (P4.1.2) and is **reused unchanged**; the acquisition targets/gates
(P4.1.4) and collection workflow (P4.1.5) are **frozen inputs** this framework
builds on.

---

## 2. Three Frozen Inputs This Framework Integrates

| Prior sprint | What it froze | What P4.1.6 adds on top |
| --- | --- | --- |
| **P4.1.2** — annotation pipeline | The validator/statistics **code** and the YOLO label contract. | Human labeling standard + QA metric definitions that call those validators. |
| **P4.1.4** — acquisition | Per-class **targets**, Gate A/B **thresholds**, blend policy. | Turns the gate thresholds into per-batch QA measurements + review procedure. |
| **P4.1.5** — collection workflow | The **collect → intake → review** operational flow + templates. | Extends review with roles/conflict/escalation and adds QA/error templates. |

The rest of this document walks each integration point.

---

## 3. P4.1.2 Validators → Structural QA

The P4.1.2 modules under `intelligence/device_ai/dataset/` are the **automated
half** of QA. They are frozen; the QA framework calls them and interprets their
output against thresholds — it does not change them.

| Module (frozen) | QA metric it feeds (PART 3) | Field consumed |
| --- | --- | --- |
| `validator.py` (`AnnotationValidator`) | Missing labels (#2), Annotation completeness (#9) | `MISSING_LABEL`, `ORPHAN_LABEL`, `COORD_OUT_OF_RANGE`, `NON_POSITIVE_SIZE`, `CLASS_ID_OUT_OF_RANGE` |
| `annotation_statistics.py` (`AnnotationStatisticsCalculator`) | Annotation completeness (#9), Class consistency (#7) | `annotation_completeness`, `orphan_labels`, `class_distribution`, `missing_classes`, `bounding_box_stats` |
| `image_validation.py` (`ImageValidator`) | Image completeness (#8) | Gate A issue codes (dimension/size/format/blur/brightness) |
| `metadata.py` (`MetadataGenerator`) | Image completeness (#8) | per-image quality metadata |
| `duplicates.py` (`DuplicateDetector`) | Duplicate limits (release) | perceptual-hash Hamming `≤ 5` |
| `taxonomy.py` (`load_taxonomy`) | Every class-typed metric | authoritative 19 class names + ids |

**Division of labour.** The validators catch **structural** faults deterministically
(malformed lines, orphan/missing files, out-of-range geometry, class-id range).
The QA framework adds the **semantic** metrics the code cannot judge — box
tightness, correct class, missed positives, class consistency — via the human
sample review (PART 2/3). Structural + semantic together are Gate B.

```python
# Illustrative — the QA lead runs the FROZEN validators; no new code (P4.1.2 API).
from device_ai.dataset.taxonomy import load_taxonomy
report = service.validate_annotations(
    images_root=Path("datasets/raw"),
    labels_root=Path("datasets/labels"),
    num_classes=load_taxonomy().num_classes,   # 19 → enables class-range checks
)
assert report.is_valid            # feeds QA metric #9 (annotation completeness)
```

---

## 4. P4.1.4 Acquisition → QA Thresholds & Gates

The acquisition runbook (`device_dataset_acquisition.md`) owns the **numbers**;
this framework consumes them so QA measures against exactly one source of truth.

| Acquisition artifact (frozen) | Used by QA as |
| --- | --- |
| §3.1 per-class **targets** (min/recommended/ideal) | Coverage check in the Definition of Done (PART 6) + `collection_progress.csv`. |
| §3.3 **balance** bound (`≤ ~5×` after blending) | Class-balance metric in the DoD. |
| §5.1 **Gate A** thresholds (dim/size/format/blur/brightness) | QA metric #8 (image completeness) — read from `settings.py`, never re-declared. |
| §5.2 **Gate B** criteria (`completeness == 1.0`, `orphan_labels == ()`, ≥95% on ≥5%) | QA metrics #2, #7, #9, #10 acceptance thresholds. |
| §4 **annotation rules** (occlusion/truncation/tiny/negatives) | The authoritative basis for PART 1; PART 1 §7 states the visible-extent rule wins. |

**Key alignment:** the ≥95% agreement on a ≥5% sample is defined once in
acquisition §5.2 and review-workflow §4; PART 2 (review) and PART 3 (QA metric
#10) reference it, they do not re-set it. Same for the Gate A pixel/blur/luminance
limits — all resolve to `configs/settings.py` (§7 below).

---

## 5. P4.1.5 Workflow → Review & QA Operations

The collection workflow (`device_collection_workflow.md`,
`device_collection_process.md`) froze the **operational flow** and the tracking
templates; this framework extends the review/QA end of that flow.

| P4.1.5 artifact (frozen) | P4.1.6 extension |
| --- | --- |
| `dataset_review_workflow.md` two-stage review | `annotation_review_manual.md` adds explicit **roles, conflict resolution, escalation** (PART 2). |
| `review_log.csv` (event log) | `annotation_review.csv` — per-image/per-event review rows with the five criteria columns (PART 4). |
| Gate A intake (`device_collection_process.md` §4) | Feeds QA metric #8; QA re-reads the archived Gate A report, does not re-run intake. |
| `collection_progress.csv` (per-class status) | QA rolls `reviewed` counts into it; DoD reads coverage from it (PART 6). |
| `image_inventory.csv` (per-image intake) | Rejections/flags cross-referenced from `annotation_errors.csv`. |

**Separation of duties is inherited, not re-invented.** The
contributor≠reviewer split (`device_collection_workflow.md` §3) and
annotator≠reviewer split (`device_detection_annotation.md` §6) extend directly to
annotator≠first-reviewer≠second-reviewer (PART 2 §1).

---

## 6. End-to-End QA Data Flow

How a single batch moves through the framework, and which artifact records each
step:

```
 ANNOTATE ──▶ SELF-CHECK ──▶ FIRST REVIEW ──▶ SECOND REVIEW ──▶ QA RUN ──▶ ACCEPT/REJECT
 (PART 1)     Annotation      100% semantic     ≥5% audit         8 metrics    batch verdict
              Validator       (PART 2 §3)       (PART 2 §4)       (PART 3)     (PART 2 §6)
                 │               │                 │                │             │
                 ▼               ▼                 ▼                ▼             ▼
          validator.py    annotation_review  annotation_review  qa_report    collection_progress
          (structural)    .csv (first)       .csv (second)      .csv +       .csv (reviewed++)
                                                                 annotation_
                                                                 errors.csv
```

1. **Annotate** to PART 1; annotator runs `AnnotationValidator` locally
   (self-check) and fixes structural errors before submitting.
2. **First review** — 100%, five criteria → rows in `annotation_review.csv`;
   defects → `annotation_errors.csv`; `needs_fix` loops to re-annotation.
3. **Second review** — ≥5% independent audit → agreement row; `< 95%` fails.
4. **QA run** — QA lead runs the frozen validators + sample review, writes one
   `qa_report.csv` row scoring all eight metrics + verdict.
5. **Accept/reject** — accepted batch updates `collection_progress.csv`; the batch
   becomes eligible for the aggregate Definition of Done (PART 6).

Conflicts (PART 2 §5) and escalations (PART 2 §7) are additional
`annotation_review.csv` rows; nothing is overwritten.

---

## 7. Configuration Reference

Every structural threshold is read from `configs/settings.py` — the QA docs
mirror these values and never re-declare them:

```
min_image_dimension        = 32        # px, short side floor (Gate A / metric #8)
max_image_dimension        = 12000     # px, long side ceiling
max_file_size              = 10 * 1024 * 1024   # 10 MiB
blur_threshold             = 100.0     # variance-of-Laplacian
brightness_dark_threshold  = 40.0      # mean luminance floor
brightness_bright_threshold= 220.0     # mean luminance ceiling
duplicate_hamming_threshold= 5         # perceptual-hash distance
split_ratios               = (0.7, 0.2, 0.1)
split_seed                 = 42
```

Review/QA thresholds that are **not** in `settings.py` live in the acquisition
runbook (frozen): **≥ 95%** agreement on a **≥ 5%** sample (min 20 images);
`annotation_completeness == 1.0`; `orphan_labels == ()`. The taxonomy (19 classes,
version `1.0.0`) is read from `load_taxonomy()`.

---

## 8. Constraints

- **Frozen:** architecture, training pipeline, dataset pipeline, all interfaces
  (`Detector`, Prediction API, dataset value objects in `records.py`), the
  taxonomy, and the P4.1.4/P4.1.5 targets, gates, and workflow.
- **No new code, schema, or interface** — P4.1.6 is documentation + CSV templates
  only.
- **No new top-level folders** (CLAUDE.md); QA artifacts stage into the existing
  `datasets/quality/` and `docs/ai/templates/` locations.
- **Images are not committed to git** — only templates and docs are versioned.
- **Out of scope (P4.1.6):** no training, YOLO execution, model evaluation,
  OpenCLIP, OCR, or model/dataset downloads.

---

## 9. Related Documents

| Document | Role |
| --- | --- |
| `docs/ai/device_annotation_guidelines.md` | Labeling standard (PART 1) |
| `docs/ai/annotation_review_manual.md` | Review roles/conflict/escalation (PART 2) |
| `docs/ai/quality_assurance.md` | Measurable QA metrics (PART 3) |
| `docs/ai/dataset_v1_definition_of_done.md` | Aggregate release DoD (PART 6) |
| `docs/engineering/device_detection_annotation.md` | P4.1.2 validators + label contract |
| `docs/engineering/device_dataset_acquisition.md` | P4.1.4 targets + Gate A/B thresholds |
| `docs/engineering/device_collection_process.md` | P4.1.5 workflow ↔ code mapping |
| `configs/settings.py` | Source of every structural threshold |
