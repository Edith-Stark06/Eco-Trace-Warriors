# Definition of Done — Dataset v1.0

**Sprint:** P4.1.6 — Dataset Annotation & Quality Assurance Framework (PART 6)
**Component:** Device Intelligence Engine (DIE) — YOLO Detector (milestone M1.4)
**Status:** Active
**Scope:** The **single completion contract** for Dataset v1.0. It states the
five conditions — coverage, QA pass rate, review completion, validation
completion, release approval — that must all hold before Dataset v1.0 is declared
done and handed to the (deferred) training pipeline. It downloads nothing, trains
nothing, and changes no code or interface.

---

## 1. Purpose

The readiness checklist (`dataset_readiness_checklist.md`, P4.1.5) is the
operational release gate; this document is the **Definition of Done (DoD)** —
the crisp, auditable statement of *what "done" means* for Dataset v1.0, phrased
as the five acceptance areas this sprint requires. The two are consistent: every
DoD item resolves to a concrete check already defined in the readiness checklist,
the QA metrics (PART 3), or the review manual (PART 2).

> **Thresholds are code-owned / frozen.** Numeric limits mirror
> `configs/settings.py` and the P4.1.4 acquisition runbook. The taxonomy is the
> frozen 19 classes (version `1.0.0`) from `load_taxonomy()`. If code and this
> doc disagree, code wins.

**Sign-off owner:** QA lead (with dataset lead for governance items).
**Evidence:** the reports and logs named per area, linked from
`dataset_metadata.json` (`quality_gates`, `checksums`).

Dataset v1.0 is **DONE** only when **all five** areas (§§2–6) are satisfied and
§7 sign-off is recorded.

---

## 2. Coverage — DONE when…

Every taxonomy class is present and adequately populated.

- [ ] **All 19 classes present** — no class has zero images
      (`AnnotationStatisticsCalculator` reports empty `missing_classes`, or each
      absent class is explicitly waived with a written cause in `qa_report.csv`).
- [ ] **Each class ≥ its `min_target`** from `collection_progress.csv`
      (recommended preferred; ideal aspirational).
- [ ] **Under-served classes cleared** — `server`, `crt_monitor`,
      `power_supply`, `cable`, `game_console`, `battery` each meet `min_target`.
- [ ] **Negatives present** — ~5–10% true-negative images (empty `.txt`),
      including hard negatives (PART 1 §13).
- [ ] **Class balance bounded** — `max_class_images / min_class_images` within the
      acquisition-runbook limit (`≤ ~5×` after blending); measured ratio recorded.

**Evidence:** aggregated `collection_progress.csv` + `AnnotationStatisticsCalculator`
class/box counts.

---

## 3. QA Pass Rate — DONE when…

Every batch passed the eight QA metrics (`quality_assurance.md` §2).

- [ ] **Every batch `qa_pass`** in `qa_report.csv` — no batch left `qa_fail` or
      unrun.
- [ ] **Bounding-box accuracy ≥ 95%** on each batch's stratified ≥5% sample
      (metric #1).
- [ ] **Zero missed positives and zero wrong classes in every sample**
      (metrics #2, #6) — the non-waivable safety metrics.
- [ ] **Zero duplicate boxes** (metric #5) and **class consistency `y`**
      (metric #7) across batches.
- [ ] **Every defect resolved** — no `open` blocking/major row remains in
      `annotation_errors.csv`.

**Evidence:** `qa_report.csv` (all rows `qa_pass`) + `annotation_errors.csv`
(no open blocking/major defects).

---

## 4. Review Completion — DONE when…

Every batch cleared both review stages with separation of duties.

- [ ] **First review 100% `pass`** on every batch (`annotation_review.csv`,
      `review_stage=first`) — every image passed or was fixed and re-passed.
- [ ] **Second review agreement ≥ 95%** on each batch's ≥5% sample
      (`review_stage=second`, metric #10).
- [ ] **Separation of duties honoured** — annotator ≠ first reviewer ≠ second
      reviewer for every image (PART 2 §1).
- [ ] **All conflicts resolved and logged** — no `conflict` row left unresolved;
      each has an authoritative disposition (PART 2 §5).
- [ ] **All escalations closed** — every `escalation` row has a recorded ruling;
      any guideline gap written back into PART 1 (PART 2 §7).
- [ ] **Re-annotation loop limit respected** — no image exceeded two
      re-annotations without being rejected (`dataset_review_workflow.md` §7).

**Evidence:** `annotation_review.csv` aggregate (all batches `accepted`).

---

## 5. Validation Completion — DONE when…

Every image passed automated structural and image-quality validation.

- [ ] **Gate A clean** — `ImageValidator` passed for 100% of retained images:
      short side `≥ 32 px`, long side `≤ 12000 px`, `≤ 10 MiB`, format in
      `{jpg,jpeg,png,webp}`, focus (variance-of-Laplacian) `≥ 100.0`, mean
      luminance `[40, 220]` (metric #8).
- [ ] **`difficult` exceptions accounted for** — any retained below-threshold
      image is a deliberate `difficult` sample, logged as such.
- [ ] **Annotation validation clean** — `AnnotationValidator.is_valid == true`;
      `annotation_completeness == 1.0`; `orphan_labels == ()` (metrics #2, #9).
- [ ] **Duplicates resolved** — `DuplicateDetector` finds no pair with
      perceptual-hash Hamming `≤ 5`; no near-duplicate straddles train/val/test.
- [ ] **Provenance complete** — every image has a `ProvenanceRecord` (source,
      licence, contributor, `collection_date`, SHA-256); manifest exported.
- [ ] **Licence & privacy cleared** — every image permissively licensed; no
      un-cleared personal/sensitive data.

**Evidence:** archived `ImageValidator` + `AnnotationValidator` +
`AnnotationStatisticsCalculator` + `DuplicateDetector` reports + `ProvenanceManifest`.

---

## 6. Release Approval — DONE when…

Readiness is recorded immutably and the release is composed with the frozen
pipeline (no new code).

- [ ] **Deterministic split** produced by `DatasetSplitter.from_settings(settings)`
      (70/20/10, seed 42) — not by hand — with **every class present in train,
      val, and test**.
- [ ] **Immutable, content-addressed version** assigned
      (`DatasetVersionManager.create_version`); dataset frozen once versioned.
- [ ] **Enriched release manifest** built with `build_release(...)` carrying all
      six required elements (metadata, statistics, taxonomy version, timestamp,
      checksums, split).
- [ ] **`dataset_metadata.json` filled** — no placeholders; real totals, split
      counts, class distribution, sources, licences, quality-gate report paths,
      checksums, and pinned taxonomy version `1.0.0`.
- [ ] **Per-image checksum manifest attached**; Gate A + Gate B report paths
      linked in `quality_gates`.
- [ ] **Readiness checklist (P4.1.5) fully checked** — §§2–7 all satisfied.

**Evidence:** `dataset_metadata.json` + `build_release` manifest +
`dataset_readiness_checklist.md` signed.

---

## 7. Sign-off

Dataset v1.0 is **DONE / RELEASE-READY** only when §§2–6 are all satisfied and
the QA lead signs off.

```
Coverage ............... [ ]   Validation completion .. [ ]
QA pass rate ........... [ ]   Release approval ....... [ ]
Review completion ...... [ ]

Measured imbalance ratio: ______   Dataset-wide agreement %: ______
Total images: ______  train/val/test: ______ / ______ / ______
All batches qa_pass: [ ]   Open blocking/major defects: ______ (must be 0)

QA lead: __________________   Date: __________
Dataset lead (governance): __________________   Date: __________
```

If any area is unmet, Dataset v1.0 is **not** done; the failing area routes back:
coverage/balance → collection; QA/review → re-annotation; validation → intake;
release → readiness checklist. A regression that drops a class below minimum
after de-duplication returns the dataset to collection for top-up.

> When every area is satisfied, Dataset v1.0 is ready to hand to the P4.1.3
> training pipeline (`build_training_manifest` → `data.yaml` → YOLO trainer).
> **Training remains out of scope for this sprint.**

---

## 8. Related Documents

| Document | Role |
| --- | --- |
| `docs/ai/quality_assurance.md` | The eight QA metrics + thresholds (PART 3) |
| `docs/ai/annotation_review_manual.md` | Review roles/conflict/escalation (PART 2) |
| `docs/ai/dataset_readiness_checklist.md` | Operational release gate (P4.1.5) |
| `docs/ai/templates/qa_report.csv` | Per-batch QA verdicts |
| `docs/ai/templates/annotation_review.csv` | Review event log |
| `docs/ai/templates/dataset_metadata.json` | Release metadata (must be placeholder-free) |
| `docs/engineering/device_dataset_acquisition.md` | Targets, gates, blend policy (P4.1.4) |
| `configs/settings.py` | Source of every structural threshold |

> **Out of scope for P4.1.6:** no training, YOLO execution, model evaluation,
> OpenCLIP, OCR, or model/dataset downloads. This is the completion contract for
> the dataset, not for a trained model.
