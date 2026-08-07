# Device Collection Workflow — Dataset v1.0

**Sprint:** P4.1.5 — Production Dataset Collection Workflow
**Component:** Device Intelligence Engine (DIE) — YOLO Detector (milestone M1.4)
**Status:** Active
**Scope:** The **operational workflow** for collecting the real production image
dataset. It defines phases, responsibilities, the contributor path, image
acceptance, naming, and upload. It downloads nothing, trains nothing, and changes
no code or interface.

---

## 1. Purpose

This is the hands-on runbook a contributor follows to turn **real device photos**
into images ready for the P4.1.2 dataset pipeline. It operationalises the
strategy in `docs/engineering/device_dataset_acquisition.md` and feeds the
checklist in `docs/ai/device_collection_checklist.md`.

- **Photo standards** are in `docs/ai/device_photo_guidelines.md` (PART 2).
- **Review** is in `docs/ai/dataset_review_workflow.md` (PART 4).
- **Readiness** is in `docs/ai/dataset_readiness_checklist.md` (PART 5).
- **Engineering integration** is in `docs/engineering/device_collection_process.md` (PART 6).

> **Taxonomy is code-owned.** The 19 classes and their IDs (0 = `laptop` …
> 18 = `battery`) come from `components/data/components.yaml` via
> `dataset/taxonomy.py::load_taxonomy()`. Never invent or reorder classes.

---

## 2. Collection Phases

Collection runs in four phases. A phase opens only when the previous one's exit
criterion is met.

```
 P0. ONBOARD ─▶ P1. CAPTURE ─▶ P2. STAGE+SUBMIT ─▶ P3. INTAKE
 contributors    photos per      rename + log +        provenance import
 briefed         guidelines      self-check            + Gate A validation
```

| Phase | Goal | Exit criterion |
| --- | --- | --- |
| **P0 — Onboard** | Contributors registered and briefed. | Row in `contributors.csv`; licence/consent agreed; guidelines read. |
| **P1 — Capture** | Photos taken per `device_photo_guidelines.md`. | Images pass the contributor self-check (§5). |
| **P2 — Stage & submit** | Images named, logged, and uploaded. | Named per §6, logged in `image_inventory.csv`, uploaded per §7. |
| **P3 — Intake** | Images imported with provenance and structurally validated. | `ProvenanceCollector` import done; `ImageValidator` Gate A clean. |

After P3, images enter the **annotation → review → release** stages defined in
the acquisition runbook and review workflow. This document owns P0–P3.

---

## 3. Responsibilities

| Role | Owns | Phase |
| --- | --- | --- |
| **Collection lead** | Per-class targets, source plan, contributor assignments, weekly progress. | P0, oversight |
| **Contributor** | Capturing photos to guideline, naming, logging, uploading. | P1–P2 |
| **Data engineer** | Provenance import, Gate A validation, de-duplication, staging into `datasets/raw/`. | P3 |
| **Reviewer** | First/second annotation review (see PART 4). | post-P3 |
| **QA lead** | Independent audit + readiness sign-off (PART 5). | release |

A contributor never reviews their own submissions; a reviewer never reviews their
own annotations (separation of duties, mirroring the annotation runbook).

---

## 4. Contributor Workflow

```
 register ─▶ get class assignment ─▶ read photo guidelines ─▶ capture ─▶
 self-check ─▶ rename ─▶ log in image_inventory.csv ─▶ upload ─▶ hand off to data engineer
```

1. **Register** in `contributors.csv` (id, name/handle, org, licence default,
   consent flag, assigned classes).
2. **Receive a class assignment** from the collection lead (which classes + how
   many; prioritise under-served: `server`, `crt_monitor`, `power_supply`,
   `cable`, `game_console`, `battery`).
3. **Read** `device_photo_guidelines.md` before the first capture.
4. **Capture** photos: varied angle, lighting, distance, and background per the
   guidelines; include some occlusion / multi-object / difficult shots on purpose.
5. **Self-check** each image against the acceptance rules (§5); delete obvious
   rejects before submitting.
6. **Rename** each file per the naming convention (§6).
7. **Log** each image in `image_inventory.csv` (filename, class, contributor,
   licence, capture date, condition, flags).
8. **Upload** to the intake location (§7) in the agreed batch structure.
9. **Hand off**: notify the data engineer that batch `<id>` is ready for intake.

---

## 5. Image Acceptance (contributor self-check)

Accept an image only if **all** hold (full quality spec in
`device_photo_guidelines.md`; thresholds mirror the pipeline's Gate A):

- [ ] The target device is **clearly identifiable** and is an in-taxonomy class.
- [ ] Resolution `min(w, h) ≥ 32 px` (aim **≥ 640 px** on the short side).
- [ ] File ≤ **10 MiB**; format `.jpg / .jpeg / .png / .webp`.
- [ ] In focus — not motion/soft-blurred (unless deliberately flagged
      `difficult`).
- [ ] Reasonable exposure — not near-black or blown-out (mean luminance roughly
      in **[40, 220]**).
- [ ] Not a duplicate/near-duplicate of another image in the same batch.
- [ ] No sensitive personal data on screens/labels (serial numbers, faces,
      account info) unless consented and licence-cleared; otherwise reframe or blur.

Images that fail identifiability, resolution, size, or format are **rejected at
source**. Blur/exposure/occlusion borderline cases may be kept **and flagged**
`difficult` so the model learns robustness — the data engineer confirms at intake.

---

## 6. Naming Convention

The pipeline importer **preserves the source filename** (it copies bytes and
keeps the relative path — `dataset/importer.py`), so the naming convention is
applied **by the contributor at capture time**, not by the code.

**Pattern:**

```
<class_name>_<source_tag>_<seq>.<ext>
```

- `class_name` — exact canonical class from the taxonomy (e.g. `laptop`,
  `crt_monitor`, `power_supply`). Use the underscore form verbatim.
- `source_tag` — short source identifier matching the `source` recorded in
  provenance (e.g. `field`, `partnerX`, `web`). Lowercase, no spaces.
- `seq` — zero-padded 6-digit sequence, unique within (class, source)
  (e.g. `000001`).
- `ext` — lowercase extension (`jpg`, `png`, `webp`).

**Examples** (consistent with the provenance example in the annotation runbook):

```
laptop_field_000001.jpg
crt_monitor_partnerX_000004.png
power_supply_web_000012.webp
```

Rules:
- One primary class per filename (the dominant device); multi-device images still
  get labelled for every class at annotation time — the filename only names the
  **intended** target.
- Never rename after upload — the filename is the join key across
  `image_inventory.csv`, provenance, and labels.
- ASCII only; no spaces, parentheses, or non-Latin characters.

---

## 7. Upload Process

1. **Batch structure.** Group a submission as a flat folder named
   `<contributor_id>_<batch_seq>/` containing the renamed images plus that
   batch's rows exported from `image_inventory.csv`.
2. **Transfer.** Upload the batch folder to the agreed intake location (shared
   drive / object storage bucket the collection lead provides). Do **not** commit
   images to the git repository.
3. **Manifest.** Include the batch's `image_inventory.csv` slice so the data
   engineer can map filename → class → licence → contributor at import.
4. **Intake (data engineer).** Import with `ProvenanceCollector.import_with_provenance(...)`
   — source/licence/contributor/date come from the manifest; SHA-256 checksums
   and de-duplication are automatic. Then run `ImageValidator` for Gate A.
5. **Acknowledge.** The data engineer updates `collection_progress.csv` with the
   accepted/rejected counts and notifies the contributor of any rejects with
   reasons (logged for re-capture).

> **Licence & privacy gate at upload.** A batch is accepted into intake only when
> every image has a permissive licence recorded and any personal data is
> consented/cleared. Unclear licence ⇒ the image is excluded (acquisition
> runbook §6).

---

## 8. Related Documents

| Document | Role |
| --- | --- |
| `docs/ai/device_photo_guidelines.md` | Photo quality standards (PART 2) |
| `docs/ai/dataset_review_workflow.md` | Review/approval/rejection/re-annotation (PART 4) |
| `docs/ai/dataset_readiness_checklist.md` | v1.0 readiness gate (PART 5) |
| `docs/engineering/device_collection_process.md` | Engineering integration (PART 6) |
| `docs/engineering/device_dataset_acquisition.md` | Acquisition strategy, targets, gates (P4.1.4) |
| `docs/ai/device_collection_checklist.md` | Build checklist (P4.1.4) |
| `docs/ai/templates/` | contributors / collection_progress / image_inventory templates (PART 3) |

> **Out of scope for P4.1.5:** no training, YOLO, OpenCLIP, OCR, or model/dataset
> downloads. This workflow collects and stages images; downstream stages are
> already documented and their code frozen.
