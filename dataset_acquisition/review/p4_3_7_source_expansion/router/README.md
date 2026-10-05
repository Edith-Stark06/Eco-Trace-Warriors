# P4.3.7 Router Wave 1 — Evidence Directory

**Taxonomy ID:** 11 · **Class:** `router` · **Wave:** 1 (pipeline validation)
**Protected HEAD:** `b4604f9` · **Status:** **AWAITING HUMAN SELF-COLLECTION**

---

## Current status (honest)

This directory is **empty of image evidence** because the approved acquisition
source is **self-collection** (family E in `docs/ai/device_detection_sources.md`),
which requires a **person with a camera / physical access to real routers**. The
automated agent cannot photograph physical devices, cannot download external
images (web access unavailable this session), and **must not fabricate** images,
provenance, annotations, counts, or QA results (repo "No fabrication" policy;
`dataset_v1_freeze_policy.md §1`).

Therefore **no router images were collected, staged, annotated, de-duplicated, or
split.** Every data-dependent result in `../P4_3_7_ROUTER_WAVE1_REPORT.md` is
recorded as `BLOCKED` / `UNVERIFIED`, not guessed.

What **is** done: the pipeline tools are verified present and runnable, the
staging/provenance scaffolding is prepared, and this turnkey runbook is ready for
the human collector.

---

## What will be stored here (once collection happens)

| Artefact | Produced by | Stage |
| --- | --- | --- |
| `collection_log.csv` (filled from the template) | human collector + `ProvenanceCollector` | acquire |
| `gate_a_image_validation.json` | `ImageValidator` | Gate A |
| `annotation_validation.json` | `validate_annotations` / `AnnotationValidator` | Gate B (structural) |
| `annotation_statistics.json` | `AnnotationStatisticsCalculator` | Gate B (completeness) |
| `duplicate_evidence.json` | **frozen** `DuplicateDetector` (Hamming ≤ 5, unchanged) | dedup |
| `visual_qa/` preview crops + notes | manual reviewer | manual QA |
| `split_result.json` | `DatasetSplitter.from_settings` (0.7/0.2/0.1, seed 42) | split |
| `readiness.json` | `scripts/audit_dataset_readiness.py` | audit |

> **Staging note:** the actual **images and YOLO `.txt` labels** are staged
> **git-ignored** under
> `dataset_acquisition/staging/p4_3_7_expansion_v1/selfcollect_router_v1/` — they
> are **never** written into `dataset_acquisition/candidate/`. Only QA/provenance
> **evidence** (JSON + preview crops) lives in this review directory.

---

## Turnkey next steps for the human collector

1. Photograph real routers/modems/gateways (exclude set-top boxes). Vary angle,
   background, model, and condition (Indian e-waste context preferred).
2. Fill `collection_log.template.csv` → `collection_log.csv` (one row per image;
   fields mirror `ProvenanceRecord`).
3. Import via `ProvenanceCollector` into the git-ignored staging path above.
4. Run the stages in the table order; drop each JSON/report here.
5. Confirm `router` appears in train **and** val **and** test; run the readiness
   audit; record the actual result in the report. If a split slice is empty,
   **collect more router images and re-run** — do **not** change ratios/seed or
   invent a minimum.
