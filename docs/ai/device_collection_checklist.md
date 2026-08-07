# Device Collection Checklist — Dataset v1.0

**Sprint:** P4.1.4 — Production Dataset Acquisition
**Component:** Device Intelligence Engine (DIE) — YOLO Detector (milestone M1.4)
**Status:** Active
**Scope:** Operational checklist for building **Dataset v1.0**. Follow this
top-to-bottom to collect, validate, annotate, QA, and release the dataset. It
downloads nothing and trains nothing — it is the runbook you execute by hand.

> Companion documents: source catalogue
> (`docs/ai/device_detection_sources.md`), acquisition engineering runbook
> (`docs/engineering/device_dataset_acquisition.md`), annotation mechanics
> (`docs/engineering/device_detection_annotation.md`), templates
> (`docs/ai/templates/`).

---

## 0. Before you start

- [ ] Read the sources catalogue and the acquisition runbook end to end.
- [ ] Confirm the 19-class taxonomy from code, not memory:
      `python -c "from device_ai.dataset.taxonomy import load_taxonomy as t; print([ (i,n) for i,n in enumerate(t().class_names)])"`.
- [ ] Copy the four templates from `docs/ai/templates/` into your working
      tracking folder (do **not** edit the templates in place).
- [ ] Confirm dataset sub-folders exist: `datasets/raw/`, `datasets/labels/`,
      `datasets/metadata/` (created by the pipeline on first import).
- [ ] Agree per-class targets (acquisition runbook §3.1) with the dataset lead.

---

## 1. Plan (Stage 0)

- [ ] For each of the 19 classes, record the **minimum / recommended / ideal**
      target (acquisition §3.1) in `annotation_progress.csv`.
- [ ] For each class, pick primary + secondary sources (sources §4).
- [ ] Flag the **under-served** classes for extra self-collection + synthetic:
      `server`, `crt_monitor`, `power_supply`, `cable`, `game_console`, `battery`.
- [ ] Confirm the split policy: **70 / 20 / 10**, seed **42** (do not override
      without sign-off).

---

## 2. Acquire (Stage 1a)

For **each source batch**:

- [ ] Verify the **licence permits ML training + redistribution** (sources §6).
      When unclear → **exclude**.
- [ ] Confirm the actual image count and terms (public counts drift — verify,
      don't trust the estimate in the catalogue).
- [ ] Record the batch in `collection_log.csv`: source, licence, contributor,
      class(es), count, collection date, URL/attribution.
- [ ] For CC-BY/CC-BY-SA, capture **author + source URL** for attribution.
- [ ] For **manufacturer imagery**: do **not** import without a signed licence
      (reference only).
- [ ] For **synthetic** images: mark them `synthetic`, keep them ≤ ~20% of the
      class, and record the derivation source.
- [ ] For **self-collected** images: note consent for any incidental PII (faces,
      serial numbers, screens with personal data); blur/exclude as needed.

---

## 3. Import with provenance (Stage 1b)

- [ ] Import via `ProvenanceCollector` (never copy files in by hand) so every
      image gets a `ProvenanceRecord` (source, licence, contributor, date,
      SHA-256 checksum).
- [ ] Use per-image overrides for images whose source/licence differs from the
      batch default.
- [ ] Persist the provenance manifest alongside `datasets/raw/`.
- [ ] Confirm the importer's de-duplication ran (exact SHA-256 duplicates are
      dropped at import).

---

## 4. Validate — Gate A (Stage 2)

Run `ImageValidator` on `datasets/raw/` and archive the JSON report.

- [ ] **Blocking** issues are **zero**: corrupt, unsupported extension, exact
      duplicate, duplicate filename. (Fix or exclude before proceeding.)
- [ ] Review **advisory** issues and decide per image:
  - [ ] Resolution: `min(w,h) ≥ 32 px`, `max(w,h) ≤ 12000 px`.
  - [ ] File size ≤ 10 MiB.
  - [ ] Blur: variance-of-Laplacian ≥ 100 (keep blurry ones only as `difficult`).
  - [ ] Brightness: mean luminance in [40, 220] (keep dark/bright only as `difficult`).
- [ ] Resolve near-duplicates (perceptual-hash Hamming ≤ 5 ⇒ near-dupe) **now**,
      before annotation and split.
- [ ] Record Gate A outcome in `review_log.csv`.

---

## 5. Annotate (Stage 3)

- [ ] Configure the annotation tool's class list to the **exact** taxonomy order
      (class 0 = `laptop` … class 18 = `battery`) — a mismatched order silently
      mislabels everything.
- [ ] Label per the expanded guidelines (acquisition §4): one tight box per
      visible instance; occlusion/truncation ≥ ~40% visible; tiny objects ≥ 8×8 px;
      empty `.txt` for true negatives.
- [ ] Collect **~5–10% negative samples** including hard negatives (book≈tablet,
      lunchbox≈console).
- [ ] Flag `difficult` images in `annotation_progress.csv`.
- [ ] Export YOLO `.txt` into `datasets/labels/` (flatten any tool splits — the
      pipeline re-splits deterministically).
- [ ] Update per-class counts in `annotation_progress.csv` against targets.

---

## 6. Review + QA — Gate B (Stage 4)

- [ ] **Reviewer pass 1 (structural):** `AnnotationValidator` is clean (no
      missing/orphan labels, no malformed lines, no class-range/geometry errors).
- [ ] **Reviewer pass 2 (semantic):** boxes tight + correctly classed on a spot
      check; annotator ≠ reviewer for the same image.
- [ ] **QA audit (independent):** random **≥ 5%** stratified sample; **≥ 95%**
      box agreement required.
- [ ] Run `AnnotationStatisticsCalculator`; check:
  - [ ] `annotation_completeness == 1.0`.
  - [ ] `orphan_labels == ()`.
  - [ ] `missing_classes` empty (or each waiver logged).
  - [ ] no class below its §3.1 minimum; imbalance within §3.3 bound.
- [ ] Separately sample `difficult`-flagged images.
- [ ] Record every finding + the Gate B pass/fail in `review_log.csv`.

---

## 7. Split, Version, Release (Stage 5)

- [ ] Confirm near-duplicates were resolved (no physical item across train/test).
- [ ] Split with `DatasetSplitter.from_settings(settings)` (70/20/10, seed 42) —
      never by hand.
- [ ] Confirm each class retains ≥ 1 instance in **val** and **test**.
- [ ] Create the immutable version with `DatasetVersionManager.create_version`.
- [ ] Build the release manifest with `build_release(...)` (six required
      elements present).
- [ ] Fill `dataset_metadata.json` (counts, per-class distribution, split sizes,
      source blend, licences, taxonomy + dataset version).
- [ ] Archive: release manifest + `dataset_metadata.json` + Gate A/B reports +
      provenance manifest, all next to the dataset.

---

## 8. Definition of Done — Dataset v1.0

- [ ] Every class meets **at least its minimum** target (§3.1).
- [ ] Gate A and Gate B both **pass** with archived reports.
- [ ] `annotation_completeness == 1.0`; no orphan labels; no unwaived missing class.
- [ ] Deterministic 70/20/10 split with every class present in val + test.
- [ ] Immutable `DatasetVersion` + release manifest + `dataset_metadata.json`
      recorded, pinning taxonomy version `1.0.0`.
- [ ] Every image traces to a permissive-licence `ProvenanceRecord`.
- [ ] All four tracking logs complete and archived.

> When every box is checked, Dataset v1.0 is ready to hand to the P4.1.3 training
> pipeline (`build_training_manifest` → `data.yaml` → YOLO trainer). **Training
> is out of scope for this sprint.**

---

## 9. Do NOT (out of scope)

- [ ] Do **not** train YOLO, download weights, or run inference.
- [ ] Do **not** modify any API, interface, or the taxonomy.
- [ ] Do **not** import restrictive/unclear-licence or manufacturer imagery
      without a signed licence.
- [ ] Do **not** hand-edit a released dataset version — create a new version.
