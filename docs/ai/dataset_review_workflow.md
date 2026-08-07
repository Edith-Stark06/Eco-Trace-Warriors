# Dataset Review Workflow — Dataset v1.0

**Sprint:** P4.1.5 — Production Dataset Collection Workflow (PART 4)
**Component:** Device Intelligence Engine (DIE) — YOLO Detector (milestone M1.4)
**Status:** Active
**Scope:** The **two-stage human review** that annotated images pass through
before they can be released. It defines first review, second review, approval,
rejection, and re-annotation. It downloads nothing, trains nothing, and changes
no code or interface.

---

## 1. Purpose

Collection and annotation produce candidate labelled images; **review** decides
which ones are trustworthy enough for Dataset v1.0. Review is a **Gate B**
activity — annotation quality — and complements the automated
`AnnotationValidator` / `AnnotationStatisticsCalculator` checks with human
judgement.

- Automated checks catch **structural** problems (orphan labels, out-of-range
  boxes, missing classes).
- Human review catches **semantic** problems (wrong class, sloppy box, missed
  object, mislabelled occlusion).

Both must pass before release (see `dataset_readiness_checklist.md`, PART 5).

> **Separation of duties.** A reviewer never reviews their own annotations, and
> the second reviewer is not the first. This mirrors the contributor/reviewer
> split in `device_collection_workflow.md` §3.

---

## 2. Review Stages Overview

```
 annotated batch
      │
      ▼
 [Gate B auto] AnnotationValidator + statistics  ──fail──▶ back to annotation
      │ pass
      ▼
 FIRST REVIEW (100% of batch, primary reviewer)  ──reject──▶ RE-ANNOTATION ─┐
      │ pass                                                                 │
      ▼                                                                      │
 SECOND REVIEW (≥5% sample, independent reviewer) ──disagree──▶ RE-ANNOTATION┘
      │ ≥95% agreement
      ▼
 APPROVED → eligible for split/version/release
```

Every review event is logged in `docs/ai/templates/review_log.csv` (from P4.1.4).

---

## 3. First Review

**Coverage:** every annotated image in the batch (100%).
**Reviewer:** primary reviewer, not the annotator.

For each image the reviewer checks:

1. **Class correctness** — every box has the right taxonomy class.
2. **Completeness** — every in-taxonomy device meeting the visibility rule
   (`≥ 40%` visible, `device_photo_guidelines.md` §6) is labelled; no missed
   positives.
3. **Box tightness** — boxes are snug (no large slack, no clipping of the real
   extent); occluded devices boxed to full expected extent.
4. **Flag correctness** — `difficult` / `occluded` / `negative` flags match
   reality.
5. **Duplicates / leakage** — image is not a near-duplicate already present in
   another split.

**Outcome per image:** `pass` or `needs_fix`. A batch **passes first review**
only when all images are `pass` (or fixed and re-passed). Any `needs_fix` image
goes to **re-annotation** (§7) before the batch advances.

Record: `review_id, review_date, batch_id, gate=B, review_type=first,
reviewer, sample_size=<batch size>, sample_pct=100, agreement_pct,
issues_found, outcome, followup_action, notes`.

---

## 4. Second Review

**Coverage:** an independent random sample of **≥ 5%** of the batch (minimum 20
images, or the whole batch if smaller).
**Reviewer:** a second, independent reviewer (not the annotator, not the first
reviewer).

Purpose: verify the first review was itself reliable — an audit of the audit.

- The second reviewer re-checks the sampled images against the same five criteria
  (§3) **blind** to the first reviewer's per-image verdict where practical.
- Compute **agreement** = fraction of sampled images where the second reviewer
  concurs with the first reviewer's disposition.
- **Acceptance threshold:** `agreement ≥ 95%`.

**If agreement `< 95%`:** the batch fails second review. The whole batch returns
to first review + re-annotation; the disagreement pattern is noted so the
annotation guideline or reviewer briefing can be corrected.

Record with `review_type=second, sample_pct≈5 (≥5), agreement_pct=<measured>`.

---

## 5. Approval

A batch is **approved** when **all** hold:

- [ ] Gate B automated checks clean: `annotation_completeness == 1.0`,
      `orphan_labels == ()`, no unwaived `missing_classes`.
- [ ] First review: 100% of images `pass`.
- [ ] Second review: sample `agreement ≥ 95%`.
- [ ] No cross-split duplicate leakage detected (`DuplicateDetector`).

On approval:
- Mark the batch `approved` in `review_log.csv` (`outcome=approved`).
- Update `collection_progress.csv` `reviewed` counts per class.
- The batch becomes **eligible** for split/version/release — approval does **not**
  itself release; release is the readiness gate in PART 5.

Approval is per-batch; Dataset v1.0 is released only when the **aggregate**
readiness checklist passes.

---

## 6. Rejection

An image or batch is **rejected** when it cannot be made release-worthy by a
reasonable fix. Common rejection reasons:

- Source image fails Gate A on re-check (blur, exposure, resolution, duplicate).
- Device is out-of-taxonomy or genuinely unidentifiable.
- Licence/consent cannot be established.
- Annotation cannot be made correct because the image is ambiguous.

Handling:
- **Image-level reject:** drop the image from the batch; log the
  `rejection_reason` in `image_inventory.csv` and, if it changes the disposition,
  in `review_log.csv`. Notify the contributor for possible re-capture.
- **Batch-level reject:** if a large fraction fails, return the whole batch to
  collection with a written cause (guideline gap, licensing issue).

Rejected images are **excluded**, never silently deleted from the audit trail —
the log keeps the reason.

---

## 7. Re-annotation

When first or second review finds a **fixable** annotation problem:

1. The image returns to an annotator (**not** the reviewer who flagged it) with
   the specific issue noted (wrong class, loose box, missed object, wrong flag).
2. The annotator corrects the labels only — the image is unchanged.
3. The corrected image **re-enters first review** (not straight to approval).
4. If it was in the second-review sample, the corrected result feeds a recomputed
   agreement.
5. Log the loop: `followup_action=re-annotation`, and a new first-review row when
   it returns.

**Loop limit:** if an image needs re-annotation more than **twice**, treat it as
a **rejection** (§6) — persistent ambiguity means the image is not worth the
label cost.

---

## 8. Roles & Log

| Role | Review responsibility |
| --- | --- |
| Annotator | Produces labels; performs re-annotation; never reviews own work. |
| First reviewer | 100% pass, class/box/completeness/flags. |
| Second reviewer | ≥5% independent audit; computes agreement. |
| QA lead | Owns thresholds, resolves disputes, signs off aggregate readiness. |

All events append to `docs/ai/templates/review_log.csv`. Never overwrite a review
row — corrections are new rows so the history stays auditable.

---

## 9. Related Documents

| Document | Role |
| --- | --- |
| `docs/ai/device_collection_workflow.md` | Phases, contributor path, upload (PART 1) |
| `docs/ai/device_photo_guidelines.md` | Photo/annotation quality standard (PART 2) |
| `docs/ai/dataset_readiness_checklist.md` | v1.0 aggregate release gate (PART 5) |
| `docs/engineering/device_dataset_acquisition.md` | Gate A/B definitions + thresholds |
| `docs/ai/templates/review_log.csv` | Review event log |

> **Out of scope for P4.1.5:** no training, YOLO, OpenCLIP, OCR, or model/dataset
> downloads. This document governs human review only.
