# Annotation Quality Assurance — Dataset v1.0

**Sprint:** P4.1.6 — Dataset Annotation & Quality Assurance Framework (PART 3)
**Component:** Device Intelligence Engine (DIE) — YOLO Detector (milestone M1.4)
**Status:** Active
**Scope:** The **measurable QA metrics** that decide whether an annotated batch
is good enough for Dataset v1.0. It defines each metric, how it is computed
(from the frozen P4.1.2 tools plus the human review), its acceptance threshold,
and where it is recorded. It downloads nothing, trains nothing, and changes no
code or interface.

---

## 1. Purpose

Review (PART 2) produces per-image dispositions; QA turns those plus the
automated statistics into **numbers with thresholds** so "good enough" is a
measurement, not an opinion. Every metric below is either read directly from a
frozen pipeline tool or computed from the review log — none require new code.

> **Thresholds are code-owned where code owns them.** Structural thresholds
> mirror `configs/settings.py` and the P4.1.2 validators; review thresholds
> mirror `dataset_review_workflow.md` and `device_dataset_acquisition.md` §5.2.
> If code and this doc disagree, code wins.

QA is an **independent audit** — the QA lead is never the annotator or the
first reviewer of the batch being measured (PART 2 §1). Results are recorded per
batch in `docs/ai/templates/qa_report.csv`; individual defects are itemised in
`annotation_errors.csv` (PART 4).

---

## 2. Metric Summary

| # | Metric | Source | Acceptance threshold |
| --- | --- | --- | --- |
| 1 | **Bounding-box accuracy** | Human sample review | ≥ 95% of sampled boxes correct (class + tightness) |
| 2 | **Missing labels** | `AnnotationValidator` + review | 0 missing label files; 0 missed positives in sample |
| 3 | **Duplicate labels** | Review + geometry check | 0 unintended duplicate boxes on one instance |
| 4 | **Incorrect classes** | Human sample review | 0 wrong classes in sample (folds into #1) |
| 5 | **Class consistency** | `AnnotationStatisticsCalculator` + review | Confusable pairs resolved by one rule dataset-wide |
| 6 | **Image completeness** | `ImageValidator` (Gate A) | 100% retained images pass Gate A or are logged `difficult` |
| 7 | **Annotation completeness** | `AnnotationStatisticsCalculator` | `annotation_completeness == 1.0`; `orphan_labels == ()` |
| 8 | **Review agreement** | `annotation_review.csv` | Second-review `agreement ≥ 95%` on ≥ 5% sample |

A batch **passes QA** only when **every** metric meets its threshold (or an
exception is explicitly waived and logged — §11).

---

## 3. Bounding-Box Accuracy

**Definition:** the fraction of sampled boxes that are **correctly classed and
tightly drawn** per `device_annotation_guidelines.md` §4.

- **Measure:** draw a random **≥ 5%** sample of the batch, **stratified by
  class** so rare classes are represented. For each box in the sample the
  reviewer marks it correct or not on two axes — class and tightness.
- **Formula:** `bbox_accuracy = correct_boxes / sampled_boxes`.
- **Threshold:** `≥ 0.95` (matches the Gate B ≥95% sample rule,
  `device_dataset_acquisition.md` §5.2).
- **Tightness rule:** a box is "tight" when each edge is within ~2–3 px of the
  device's visible extent (PART 1 §4); systematic slack or clipping fails.
- **Record:** `qa_report.csv` (`bbox_accuracy_pct`, `sample_boxes`); each failed
  box → one row in `annotation_errors.csv` (`error_type=loose_box` or
  `wrong_class`).
- **Below threshold:** batch fails QA → back to re-annotation (PART 2 §6.2), the
  failing pattern noted for a possible guideline clarification (PART 2 §7).

---

## 4. Missing Labels

**Definition:** in-taxonomy devices that should be boxed but are not, plus image
stems with no label file at all.

- **Two sub-checks:**
  - **Missing label files** — `AnnotationValidator` reports `MISSING_LABEL`
    (a retained image with no `.txt`). Automated, whole-batch.
  - **Missed positives** — a visible device (≥ ~40% visible, ≥ 8×8 px) left
    unboxed. Human, caught in first review (PART 2 §3 criterion 2) and the QA
    sample.
- **Formula:** `missing_label_files = count(MISSING_LABEL)`;
  `missed_positives = boxes_expected − boxes_present` over the reviewed sample.
- **Threshold:** `missing_label_files == 0` **and** `missed_positives == 0` in
  the sample. A missed positive is the most damaging annotation error (it teaches
  suppression of real detections), so there is **no tolerance** for it in-sample.
- **Record:** `qa_report.csv` (`missing_labels`); each occurrence →
  `annotation_errors.csv` (`error_type=missing_label` or `missed_positive`).
- **Note:** an **empty** `.txt` on a negative image is **not** a missing label —
  it is a true negative (PART 1 §13). `annotation_completeness` (#7) counts it as
  present.

---

## 5. Duplicate Labels

**Definition:** more than one box drawn on a **single** device instance, or two
identical/near-identical boxes in one label file.

- **Measure:** in review, confirm one-box-per-instance (PART 1 §3, §8); flag any
  instance carrying two overlapping boxes of the same class as a duplicate. A
  geometry spot-check finds label lines whose boxes are near-identical
  (high overlap, same class) — a strong duplicate signal.
- **Formula:** `duplicate_boxes = count(instances with > 1 box for the same
  physical device)`.
- **Threshold:** `duplicate_boxes == 0`. (Two *different* devices of the same
  class correctly get two boxes — that is **not** a duplicate; PART 1 §8
  overlapping devices.)
- **Record:** `qa_report.csv` (`duplicate_labels`); each → `annotation_errors.csv`
  (`error_type=duplicate_box`).
- **Distinction from image duplicates:** duplicate *images* are a Gate A /
  `DuplicateDetector` concern (#6, and the readiness checklist); this metric is
  about duplicate *boxes* within an image.

---

## 6. Incorrect Classes

**Definition:** a box drawn on the right device but with the **wrong taxonomy
class**.

- **Measure:** part of the sample review (#1); tracked separately so
  class-confusion trends are visible even when overall accuracy passes.
- **Formula:** `incorrect_classes = count(boxes with wrong class in sample)`;
  reported as a rate `incorrect_class_pct = incorrect_classes / sample_boxes`.
- **Threshold:** `incorrect_classes == 0` in the sample. A single wrong class in
  the sample fails QA and prompts a full re-check of that class in the batch.
- **Record:** `qa_report.csv` (`incorrect_classes`); each →
  `annotation_errors.csv` (`error_type=wrong_class`, `expected_class`,
  `actual_class`).
- **Common offenders** (PART 1 §14): `monitor`↔`television`,
  `tablet`↔`smartphone`, `power_supply`↔`cable`. A cluster of these on one pair
  is a class-consistency problem (#5), not just isolated errors.

---

## 7. Class Consistency

**Definition:** the **same physical device type is always labelled the same
class** across annotators, images, and batches.

- **Measure:**
  - `AnnotationStatisticsCalculator.class_distribution` — a class whose count
    swings implausibly between batches, or a confusable pair whose ratio flips,
    signals inconsistent labelling.
  - The QA sample confirms the confusable pairs (#6) are resolved by **one rule**
    (PART 1 §14) everywhere — e.g. every computer display is `monitor`, every
    tuner-equipped set is `television`.
- **Formula (indicator):** for each confusable pair, `consistency_ok` = the same
  disambiguation rule applied in 100% of sampled instances.
- **Threshold:** every confusable pair resolved consistently; no class in
  `missing_classes` unless waived (coverage, §11).
- **Record:** `qa_report.csv` (`class_consistency_ok`, plus the measured
  `class_distribution` archived alongside).
- **Below threshold:** a systematic confusion is a **guideline / briefing**
  problem — escalate per PART 2 §7 and clarify PART 1 §14, then re-review the
  affected class.

---

## 8. Image Completeness

**Definition:** every **retained image** passed automated image-quality
validation (Gate A) before annotation — the images are complete and usable.

- **Measure:** `ImageValidator` (`dataset/image_validation.py`) over
  `datasets/raw/`, plus `MetadataGenerator` + `DuplicateDetector`. Thresholds are
  the configured settings (do **not** hardcode): short side `≥ 32 px`, long side
  `≤ 12000 px`, `≤ 10 MiB`, format `{jpg,jpeg,png,webp}`, focus
  variance-of-Laplacian `≥ 100.0`, mean luminance `[40, 220]`, no exact
  duplicate.
- **Formula:** `image_completeness = images_passing_gate_A / retained_images`.
- **Threshold:** `image_completeness == 1.0` — every retained image either passes
  Gate A **or** is a deliberate `difficult` exception logged as such
  (`device_dataset_acquisition.md` §5.1).
- **Record:** `qa_report.csv` (`image_completeness_pct`); the Gate A JSON report
  is archived and its path linked.
- **Note:** this is an **image**-quality metric feeding annotation QA — it is the
  Gate A half; #1–#5 are the Gate B (annotation) half.

---

## 9. Annotation Completeness

**Definition:** every retained image has a label file, and every label file has
an image — no annotation gaps, no orphans.

- **Measure:** `AnnotationStatisticsCalculator.compute(images_root=…,
  labels_root=…)` returns `annotation_completeness` (`[0, 1]`),
  `images_without_labels`, and `orphan_labels`; `AnnotationValidator` cross-checks
  `MISSING_LABEL` / `ORPHAN_LABEL`.
- **Formula:** `annotation_completeness = images_with_label_file /
  retained_images` (an **empty** `.txt` counts as present — PART 1 §13).
- **Threshold:** `annotation_completeness == 1.0` **and** `orphan_labels == ()`
  (matches `device_detection_annotation.md` §7.2).
- **Record:** `qa_report.csv` (`annotation_completeness_pct`, `orphan_labels`);
  the statistics JSON is archived.
- **Below threshold:** unlabelled images route back to annotation; orphan labels
  are removed or their image restored — neither is waivable.

---

## 10. Review Agreement

**Definition:** how strongly the second reviewer concurs with the first — the
reliability of the review itself.

- **Measure:** from `annotation_review.csv`, over the second-review sample
  (≥ 5% of the batch, min 20): `agreement = concurring_images / sampled_images`
  (PART 2 §4).
- **Threshold:** `agreement ≥ 0.95` (`dataset_review_workflow.md` §4).
- **Record:** `qa_report.csv` (`review_agreement_pct`, `review_sample_size`).
- **Below threshold:** the batch fails; it returns to first review +
  re-annotation and the disagreement pattern is escalated (PART 2 §7). Low
  agreement usually means the **standard** is unclear, not that one reviewer is
  wrong — fix PART 1, then re-review.

---

## 11. QA Run & Waivers

**Per-batch QA run (the QA lead executes):**

1. **Automated sweep.** Run `ImageValidator` (Gate A, #6) and, after annotation,
   `AnnotationValidator` + `AnnotationStatisticsCalculator` (#7, #9). Archive the
   JSON reports and link their paths in `qa_report.csv`.
2. **Sample review.** Draw the random ≥ 5% stratified sample; score #1, #6, #7.
3. **Log defects.** Itemise every failed box/image in `annotation_errors.csv`.
4. **Agreement.** Read #10 from `annotation_review.csv`.
5. **Verdict.** Write one `qa_report.csv` row: every metric + `qa_pass` (all
   thresholds met) or `qa_fail` (any missed).

**Waivers.** Only **coverage** items are ever waivable, and only explicitly: a
class in `missing_classes` may be waived with a written cause for the release
(`device_dataset_acquisition.md` §5.2). Structural metrics (#9 annotation
completeness, orphan labels) and safety metrics (#6 incorrect class in sample,
#4 missed positive) are **never** waived — they route back to the owning stage.
Every waiver is a logged row (`qa_report.csv` `waiver_reason`), signed by the QA
lead.

---

## 12. Metrics ↔ Sources Map

| Metric | Primary tool / source | Log column |
| --- | --- | --- |
| Bounding-box accuracy | Human sample | `qa_report.csv::bbox_accuracy_pct` |
| Missing labels | `AnnotationValidator` + review | `qa_report.csv::missing_labels` |
| Duplicate labels | Review + geometry | `qa_report.csv::duplicate_labels` |
| Incorrect classes | Human sample | `qa_report.csv::incorrect_classes` |
| Class consistency | `AnnotationStatisticsCalculator` + review | `qa_report.csv::class_consistency_ok` |
| Image completeness | `ImageValidator` | `qa_report.csv::image_completeness_pct` |
| Annotation completeness | `AnnotationStatisticsCalculator` | `qa_report.csv::annotation_completeness_pct` |
| Review agreement | `annotation_review.csv` | `qa_report.csv::review_agreement_pct` |

---

## 13. Related Documents

| Document | Role |
| --- | --- |
| `docs/ai/device_annotation_guidelines.md` | The labeling standard the metrics measure (PART 1) |
| `docs/ai/annotation_review_manual.md` | Review roles + escalation feeding QA (PART 2) |
| `docs/ai/templates/qa_report.csv` | Per-batch QA metric record (PART 4) |
| `docs/ai/templates/annotation_errors.csv` | Per-defect log (PART 4) |
| `docs/engineering/device_annotation_quality.md` | How validators/acquisition/workflow integrate into QA (PART 5) |
| `docs/engineering/device_dataset_acquisition.md` | Gate A/B thresholds (P4.1.4) |
| `docs/engineering/device_detection_annotation.md` | Acceptance metrics §7.2 (P4.1.2) |
| `configs/settings.py` | Source of every structural threshold |

> **Out of scope for P4.1.6:** no training, YOLO execution, model evaluation,
> OpenCLIP, OCR, or model/dataset downloads. These metrics measure annotation
> quality, not model quality.


