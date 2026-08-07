# Dataset Readiness Checklist — Dataset v1.0

**Sprint:** P4.1.5 — Production Dataset Collection Workflow (PART 5)
**Component:** Device Intelligence Engine (DIE) — YOLO Detector (milestone M1.4)
**Status:** Active
**Scope:** The single **release gate** for Dataset v1.0. Dataset v1.0 may be
built, versioned, and handed to training **only** when every item here is
satisfied. It downloads nothing, trains nothing, and changes no code or
interface.

---

## 1. Purpose

Individual batches are approved in review (PART 4); this checklist is the
**aggregate** gate over the whole dataset. It asserts five properties —
**coverage, class balance, annotation completeness, validation, duplicate
limits** — each tied to a concrete, checkable condition using the frozen P4.1.2
pipeline tools.

> **Thresholds are code-owned.** All numeric limits mirror `configs/settings.py`
> and the acquisition runbook. If code and this doc disagree, code wins.

Sign-off owner: **QA lead**. Evidence: the reports named in each section, linked
from `dataset_metadata.json` (`quality_gates`, `checksums`).

---

## 2. Coverage

Every taxonomy class must be present and meet at least its **minimum** target.

- [ ] **All 19 classes present** — no class has zero images
      (`AnnotationStatisticsCalculator` reports no `missing_classes`, or each is
      explicitly waived with cause).
- [ ] **Each class ≥ its `min_target`** from `collection_progress.csv`
      (recommended targets preferred; ideal targets aspirational).
- [ ] **Under-served classes cleared** — `server`, `crt_monitor`,
      `power_supply`, `cable`, `game_console`, `battery` each meet `min_target`
      via self-collection / partners (they are hardest to source publicly).
- [ ] **Negatives present** — ~5–10% negative images (no in-taxonomy device) are
      included to control false positives.

Evidence: aggregated `collection_progress.csv` + Gate B statistics report.

---

## 3. Class Balance

The dataset must not be dominated by a few easy classes.

- [ ] **Imbalance ratio bounded** — `max_class_images / min_class_images` is
      within the acquisition-runbook limit (target `≤ ~5×` after blending;
      report the measured ratio).
- [ ] **Source blend respected** — no single public dataset supplies more than
      ~50% of any class; synthetic images capped at ~20% of any class
      (acquisition runbook blend policy).
- [ ] **Per-split balance** — every class appears in **train, val, and test**
      (the `DatasetSplitter` 70/20/10, seed 42 split leaves no class absent from
      a split).
- [ ] **Box-count sanity** — classes with many small instances (`cable`,
      `battery`) report plausible boxes-per-image, not a single box standing in
      for a pile.

Evidence: `AnnotationStatisticsCalculator` per-class image/box counts +
per-split distribution.

---

## 4. Annotation Completeness

Every image is fully and correctly labelled.

- [ ] **`annotation_completeness == 1.0`** — every non-negative image has a
      label file and every label file has an image (`AnnotationValidator`).
- [ ] **`orphan_labels == ()`** — no label without a matching image.
- [ ] **No unlabelled positives** — first review (PART 4 §3) confirmed every
      visible in-taxonomy device is boxed.
- [ ] **All batches approved** — every batch reached `approved` in
      `review_log.csv`; none `in_review` or `blocked`.
- [ ] **Second-review agreement `≥ 95%`** on the ≥5% sample, dataset-wide.

Evidence: `AnnotationValidator` report + `review_log.csv` aggregate.

---

## 5. Validation (Gate A + structural)

Every image passed automated quality validation before annotation.

- [ ] **Gate A clean** — `ImageValidator` passed for 100% of retained images:
      short side `≥ 32 px`, long side `≤ 12000 px`, file `≤ 10 MiB`, format in
      `{jpg,jpeg,png,webp}`, focus (variance-of-Laplacian) `≥ 100.0`, mean
      luminance in `[40, 220]`.
- [ ] **`difficult`-flagged exceptions accounted for** — any retained
      below-threshold images are deliberate `difficult` samples, logged as such.
- [ ] **Provenance complete** — every image has a `ProvenanceRecord` (source,
      licence, contributor, collection_date, SHA-256 checksum); manifest exported.
- [ ] **Licence & privacy cleared** — every image has a permissive licence; no
      un-cleared personal/sensitive data.

Evidence: `ImageValidator` Gate A report + `ProvenanceManifest`.

---

## 6. Duplicate Limits

No duplicates within the dataset and no leakage across splits.

- [ ] **In-dataset duplicates removed** — `DuplicateDetector` finds no pair with
      perceptual-hash Hamming distance `≤ 5` (the `duplicate_hamming_threshold`).
- [ ] **No cross-split leakage** — no near-duplicate appears in more than one of
      train / val / test (a leaked pair inflates val/test scores).
- [ ] **Dedup accounted for** — `duplicates_dropped` counts recorded in
      `collection_progress.csv`; drops traceable in provenance.

Evidence: `DuplicateDetector` report.

---

## 7. Release Metadata & Versioning

Readiness is only real once it is recorded immutably.

- [ ] **`dataset_metadata.json` filled** — no placeholders; totals, split counts,
      class distribution, sources, quality-gate report paths, checksums all real.
- [ ] **Content-addressed version id** assigned (`DatasetVersionManager` /
      `build_release`); dataset is immutable once versioned.
- [ ] **Per-image checksum manifest** attached.
- [ ] **Gate A + Gate B report paths** linked in `quality_gates`.

Evidence: `dataset_metadata.json` + version manifest from `build_release`.

---

## 8. Sign-off

Dataset v1.0 is **RELEASE-READY** only when §§2–7 are all checked and the QA lead
signs off.

```
Coverage ............... [ ]   Validation (Gate A) .... [ ]
Class balance .......... [ ]   Duplicate limits ....... [ ]
Annotation completeness  [ ]   Metadata & versioning .. [ ]

Measured imbalance ratio: ______   Dataset-wide agreement %: ______
Total images: ______  train/val/test: ______ / ______ / ______

QA lead: __________________   Date: __________
```

If any box is unchecked, the dataset is **not** released; the failing property
routes back to collection (coverage/balance), annotation (completeness), or
intake (validation/duplicates).

---

## 9. Related Documents

| Document | Role |
| --- | --- |
| `docs/ai/device_collection_workflow.md` | Phases, contributor path, upload (PART 1) |
| `docs/ai/device_photo_guidelines.md` | Photo/annotation quality standard (PART 2) |
| `docs/ai/dataset_review_workflow.md` | Human review Gate B (PART 4) |
| `docs/engineering/device_dataset_acquisition.md` | Targets, gates, blend policy, release process |
| `docs/ai/templates/dataset_metadata.json` | Release metadata template |
| `configs/settings.py` | Source of every numeric threshold above |

> **Out of scope for P4.1.5:** no training, YOLO, OpenCLIP, OCR, or model/dataset
> downloads. This is the release gate, not the release itself.
