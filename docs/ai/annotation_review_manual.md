# Annotation Review Manual — Dataset v1.0

**Sprint:** P4.1.6 — Dataset Annotation & Quality Assurance Framework (PART 2)
**Component:** Device Intelligence Engine (DIE) — YOLO Detector (milestone M1.4)
**Status:** Active
**Scope:** The **human review procedure** for YOLO annotations: who reviews,
in what order, how disagreements are resolved, and what makes a batch accepted,
rejected, or escalated. It operationalises the two-stage review already defined
in `dataset_review_workflow.md` and adds the roles, conflict resolution, and
escalation path this sprint requires. It downloads nothing, trains nothing, and
changes no code or interface.

---

## 1. Purpose

Automated validators catch **structural** faults (orphan labels, out-of-range
boxes, missing classes); people catch **semantic** faults (wrong class, sloppy
box, missed object, wrong flag). This manual defines the human half so it is
repeatable and auditable.

It sits on top of two existing documents and does not contradict them:

- `dataset_review_workflow.md` — the first/second review flow and thresholds.
- `device_annotation_guidelines.md` (PART 1) — the standard reviewers check
  against.

> **Separation of duties.** For any given image: annotator ≠ first reviewer ≠
> second reviewer. Nobody reviews their own work, and the second reviewer is
> never the first. This mirrors the contributor/reviewer split in
> `device_collection_workflow.md` §3.

Every review event is appended to `docs/ai/templates/annotation_review.csv`
(PART 4); no row is ever overwritten (§8).

---

## 2. Roles at a Glance

| Role | Responsibility | Coverage |
| --- | --- | --- |
| **Annotator** | Produces labels per PART 1; runs `AnnotationValidator` self-check; performs re-annotation. Never reviews own work. | — |
| **First reviewer** | 100% semantic review of the batch: class, completeness, box tightness, flags, duplicates. | Every image |
| **Second reviewer** | Independent audit of the first review; computes agreement. | ≥ 5% sample (min 20) |
| **QA lead** | Owns thresholds, resolves conflicts, runs the QA metrics (PART 3), signs off. | Aggregate |

The first and second reviewer are the two review roles named in the sprint; the
QA lead is the conflict-resolution and escalation authority (§5, §7).

---

## 3. First Reviewer

**Coverage:** every annotated image in the batch (100%).
**Reviewer:** the primary reviewer — not the annotator.

For each image, check the five criteria (identical to `dataset_review_workflow.md`
§3, restated here as the reviewer's working list):

1. **Class correctness** — every box carries the right taxonomy class
   (`device_annotation_guidelines.md` §14 confusions resolved correctly).
2. **Completeness** — every in-taxonomy device meeting the visibility rule
   (≥ ~40% visible, ≥ 8×8 px) is boxed; no missed positives.
3. **Box tightness** — boxes hug the visible extent (PART 1 §4); occluded /
   truncated devices boxed to the **visible** extent only (PART 1 §6–§7).
4. **Flag correctness** — `difficult` / `occluded` / `multi_object` / `negative`
   match reality (PART 1 §11, §13).
5. **Duplicates / leakage** — the image is not a near-duplicate already present
   under another stem in the batch or another split.

**Outcome per image:** `pass` or `needs_fix`. A batch **passes first review**
only when every image is `pass` (or was fixed and re-passed). Any `needs_fix`
image routes to **re-annotation** (`dataset_review_workflow.md` §7) before the
batch advances.

**Record** in `annotation_review.csv`: `review_id, review_date, batch_id,
image_id, review_stage=first, reviewer_id, class_ok, completeness_ok,
box_tightness_ok, flags_ok, duplicate_ok, disposition, error_count,
error_ref, notes`.

---

## 4. Second Reviewer

**Coverage:** an independent random sample of **≥ 5%** of the batch (minimum 20
images, or the whole batch if smaller).
**Reviewer:** a second, independent reviewer — not the annotator, not the first
reviewer.

Purpose: verify the first review was itself reliable — an audit of the audit.

- Re-check the sampled images against the same five criteria (§3), **blind** to
  the first reviewer's per-image verdict where practical.
- Compute **agreement** = fraction of sampled images where the second reviewer's
  disposition matches the first reviewer's.
- **Acceptance threshold:** `agreement ≥ 95%`.

**If agreement `< 95%`:** the batch fails second review. It returns to first
review + re-annotation; the disagreement pattern is noted so PART 1 or the
reviewer briefing can be corrected (this is a §7 escalation trigger).

**Record** with `review_stage=second, sample_pct` (≥5), `agreement_pct`
(measured).

---

## 5. Conflict Resolution

A *conflict* is any disagreement about a label the two reviewers cannot settle
between themselves — e.g. first reviewer passed an image the second rejects, or
the annotator disputes a `needs_fix`.

**Resolution ladder — stop at the first step that settles it:**

1. **Re-read the standard.** Most conflicts are resolved by
   `device_annotation_guidelines.md` — the two reviewers re-read the relevant
   section (class confusion → §14; box reach under occlusion → §7; tiny object →
   §10) and apply it verbatim. If the standard is unambiguous, its ruling wins.
2. **Reviewer discussion.** The first and second reviewer confer and agree on the
   correct label per the standard. Agreement here closes the conflict; log the
   agreed disposition.
3. **QA lead ruling.** If the two reviewers still disagree, the **QA lead
   decides**. The QA lead's ruling is final for that image and is recorded as the
   authoritative disposition.
4. **Guideline gap → escalation.** If the conflict exists because the standard is
   **silent or contradictory** (not because someone misread it), the QA lead
   records it as a guideline gap and escalates per §7 so PART 1 can be clarified
   for every future annotator.

**Every conflict resolution is logged** as its own row in
`annotation_review.csv` (`review_stage=conflict`, `disposition` = the agreed
outcome, `notes` = the rule applied and who decided). The original review rows
are **not** edited — the conflict row supersedes them, preserving the history.

**Tie-break defaults** (apply only when the standard is genuinely silent, pending
a §7 clarification):
- **Uncertain class → exclude the image**, do not guess (PART 1 §14).
- **Uncertain visibility (~40% borderline) → skip the instance**, do not box.
- **Uncertain `difficult` → flag it `difficult`** (conservative: more QA, not
  less).

---

## 6. Acceptance and Rejection

### 6.1 Acceptance

An image is **accepted** when it is `pass` at first review (and, if sampled,
concurred at second review). A **batch is accepted** when **all** hold — matching
`dataset_review_workflow.md` §5:

- [ ] Gate B automated checks clean: `annotation_completeness == 1.0`,
      `orphan_labels == ()`, no unwaived `missing_classes`
      (`AnnotationValidator` + `AnnotationStatisticsCalculator`).
- [ ] First review: 100% of images `pass`.
- [ ] Second review: sample `agreement ≥ 95%`.
- [ ] No cross-split duplicate leakage (`DuplicateDetector`).

On acceptance, mark the batch `accepted` in `annotation_review.csv`, roll the
per-class `reviewed` counts into `collection_progress.csv`, and record the QA
metrics for the batch in `qa_report.csv` (PART 4). Acceptance makes a batch
**eligible** for split/version/release — it is not itself the release (that is
the Definition of Done, PART 6).

### 6.2 Rejection

An image or batch is **rejected** when it cannot be made release-worthy by a
reasonable fix (aligns with `dataset_review_workflow.md` §6). Common reasons:

- Source image fails Gate A on re-check (blur, exposure, resolution, duplicate).
- Device is out-of-taxonomy or genuinely unidentifiable.
- Licence/consent cannot be established.
- Annotation cannot be made correct because the image itself is ambiguous.
- The image required re-annotation **more than twice** (loop limit —
  `dataset_review_workflow.md` §7): persistent ambiguity is rejected.

**Handling:**
- **Image-level reject:** drop the image from the batch; log `rejection_reason`
  in `image_inventory.csv` and `annotation_errors.csv` (PART 4). Notify the
  contributor for possible re-capture.
- **Batch-level reject:** if a large fraction fails, return the whole batch to
  collection with a written cause (guideline gap, licensing issue).

Rejected images are **excluded, never silently deleted** from the audit trail —
the log keeps the reason.

---

## 7. Escalation Process

Escalation moves a decision that cannot be settled at the reviewer level, or that
signals a systemic problem, to the authority that can fix it.

**Escalate to the QA lead when:**
- Two reviewers cannot agree after §5 steps 1–2 (per-image conflict).
- Second-review `agreement < 95%` (batch-level reliability failure).
- The annotation standard is silent or self-contradictory (guideline gap).
- A class trends toward a systematic error (e.g. `monitor`/`television` confused
  across many images) — a briefing or guideline problem, not a one-off.

**Escalate beyond the QA lead (to the dataset lead / collection lead) when:**
- A whole batch is rejected for a **licensing or consent** failure (governance,
  not annotation).
- A class cannot reach its minimum target because source images do not exist —
  routes back to collection planning (`device_collection_checklist.md` §1).
- A guideline change would alter already-accepted labels — the dataset lead
  decides whether to re-review prior batches.

**Escalation path:**

```
 annotator ─▶ first reviewer ─▶ second reviewer ─▶ QA lead ─▶ dataset/collection lead
             (per-image)        (audit)            (conflicts,   (governance,
                                                    guideline)    targets, re-review scope)
```

**Every escalation is logged** in `annotation_review.csv`
(`review_stage=escalation`, `notes` = trigger + who it went to + the ruling).
A guideline gap that reaches the QA lead is written back into
`device_annotation_guidelines.md` so the same conflict does not recur — the fix
is to the standard, applied to all future work, not a silent per-image
override.

---

## 8. Logging Rules

- **Append-only.** Never overwrite a review row. A correction, conflict ruling,
  or re-review is a **new row** that supersedes the earlier one, so the full
  history stays auditable (mirrors `dataset_review_workflow.md` §8).
- **One row per event** — first review of an image, second-review sample verdict,
  conflict resolution, escalation, accept/reject — each is its own row.
- **Cross-reference errors.** A `needs_fix` / rejection row references the error
  captured in `annotation_errors.csv` via `error_ref`, so the metric and the
  narrative stay linked.
- **Templates, not real rows.** The shipped CSVs carry clearly-marked example
  rows only (PART 4); real review data is tracked in a working copy, never in the
  committed templates.

---

## 9. Related Documents

| Document | Role |
| --- | --- |
| `docs/ai/device_annotation_guidelines.md` | The labeling standard reviewers check against (PART 1) |
| `docs/ai/quality_assurance.md` | Measurable QA metrics + acceptance thresholds (PART 3) |
| `docs/ai/dataset_review_workflow.md` | Two-stage review flow + thresholds (P4.1.5) |
| `docs/ai/templates/annotation_review.csv` | Review event log (PART 4) |
| `docs/ai/templates/annotation_errors.csv` | Per-error log (PART 4) |
| `docs/engineering/device_dataset_acquisition.md` | Gate B definition + thresholds (P4.1.4) |

> **Out of scope for P4.1.6:** no training, YOLO execution, model evaluation,
> OpenCLIP, OCR, or model/dataset downloads. This manual governs human review of
> annotations only.
