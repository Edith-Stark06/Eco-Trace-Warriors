# Open Images → EcoTrace Laptop Pilot — Remediation & Canonical Ingestion Report

Status: Manual-review checkpoint (remediation applied, canonical candidate staged — **not** released)
Sprint: P4.2.4 — Laptop pilot remediation & canonical ingestion
Scope: `laptop` class only — remediation of the 21-image Open Images V7 pilot into a 20-image canonical candidate
Audience: dataset engineers, annotation reviewers, QA leads

---

> **What this report is.** It records the remediation actions taken on the Laptop
> pilot in response to the manual visual-QA verdict `PILOT_PASS_WITH_REVIEW`
> (see `docs/ai/reports/openimages_laptop_pilot_visual_qa.md`), the creation of a
> **new canonical candidate** staging directory under the code-owned filename
> convention, and the re-run of the existing validators against that candidate.
> It reports **only observed counts and honest validator output** — no quality
> score, accuracy percentage, or dataset-readiness metric is invented. It marks
> **nothing** as READY or RELEASED. **This is a single-class acquisition pilot,
> NOT Dataset v1.0.**

> **Provenance & non-destruction guarantees.**
> - The Open Images source download and the source-preserved staging
>   (`dataset_acquisition/staging/openimages_laptop_v1/`) were **only read**. No
>   source image or source label was modified, renamed, or deleted — including
>   the excluded image, which still exists byte-identically in the source.
> - Every retained canonical image is a **verbatim byte copy** of its source
>   image; the tool re-computed each SHA-256 with the frozen
>   `device_ai.dataset.hashing.sha256_hash` and refused to proceed on any
>   mismatch.
> - Corrected annotations were normalised and validated through the frozen-style
>   `convert_box` (reject-never-clip); the `laptop` class id (`0`) was
>   **discovered** via `load_taxonomy()`, never assumed.

> **How to reproduce.** From the repository root:
> ```
> python scripts/ingest_laptop_canonical.py
> ```
> All inputs default to the Laptop pilot; the only timestamp is injected
> (`--remediation-timestamp`, default `2026-08-09T00:00:00+00:00`), so identical
> inputs produce byte-identical outputs. Artifacts land under
> `dataset_acquisition/staging/openimages_laptop_canonical_v1/`.

---

## 1. Source pilot statistics (input to remediation)

| Fact | Value | Source |
| ---- | ----- | ------ |
| Source staged images | 21 | `openimages_laptop_v1/provenance/provenance_manifest.json` |
| Source converted boxes | 35 | same |
| Class | `laptop` (id `0`, discovered via `load_taxonomy`) | frozen taxonomy v1.0.0 |
| Visual-QA verdict | `PILOT_PASS_WITH_REVIEW` | `openimages_laptop_pilot_visual_qa.md` |
| — ACCEPT | 16 images / 26 boxes | visual-QA report §3 |
| — REVIEW | 4 images / 8 boxes (QA01, QA03, QA04, QA15) | visual-QA report §3 |
| — REJECT | 1 image / 1 box (QA14) | visual-QA report §3 |

---

## 2. Remediation actions (observed)

Only the five visually-flagged images required an action; the other 16 were
accepted unchanged. **No AI-authored correction is self-certified.** Per the
annotation review manual (separation of duties), every re-annotation and the
held REVIEW image is emitted `reviewer_status = PENDING_REVIEW` and re-enters
independent first review; the proposed pixel coordinates are deliberate visual
estimates, not tool-measured ground truth.

| QA | Canonical file | Source stem | Action | Remediation status | Reviewer status | Objects (orig → corr) |
| -- | -------------- | ----------- | ------ | ------------------ | --------------- | --------------------- |
| 14 | *(excluded)* | `79182035199f2b58` | `EXCLUDE` | `EXCLUDED` | `EXCLUDED` | 1 → — |
| 03 | `laptop_openimages_000003` | `0171ad35f1651698` | `REANNOTATE_SPLIT` | `REMEDIATION_REVIEW_PENDING` | `PENDING_REVIEW` | 1 → 5 |
| 04 | `laptop_openimages_000004` | `14587a599414300c` | `REANNOTATE_ADD_INSTANCE` | `REMEDIATION_REVIEW_PENDING` | `PENDING_REVIEW` | 5 → 6 |
| 15 | `laptop_openimages_000014` | `936a6d462e9d4873` | `REANNOTATE_TIGHTEN` | `REMEDIATION_REVIEW_PENDING` | `PENDING_REVIEW` | 1 → 1 |
| 01 | `laptop_openimages_000001` | `00767fb6565581c6` | `KEEP_REVIEW_PENDING` | `REVIEW_PENDING` | `PENDING_REVIEW` | 1 → 1 |

Machine-readable detail: `openimages_laptop_canonical_v1/reports/remediation_manifest.json`.

### 2.1 QA14 — exclusion (PART 2)

- **Source (unchanged):** `79182035199f2b58.jpg`, 1024×1024, 1 box, SHA-256
  `275c18b4bfc6c54eaaba25798a5f0a40d5922208d99f7838f3fa47cb1bc3bcaf`.
- **QA decision:** REJECT. **Reviewer decision:** EXCLUDED.
- **Reason:** Blurry (blur 58.7) extreme keyboard macro with no laptop form
  factor visible; visually indistinguishable from the separate `keyboard`
  taxonomy class. Not a usable `laptop` exemplar.
- **Handling:** Omitted from the canonical candidate only. The source copy is
  retained byte-identically in Open Images staging. Full record kept in the
  manifest `exclusions[]`.

### 2.2 QA03 — group box split (PART 3)

- **Original annotation (1 box):** `0 0.286133 0.657552 0.572266 0.682292` — one
  box spanning a receding row of ~5–6 distinct laptops (violates
  one-box-per-instance, guidelines §3/§9).
- **Corrected annotation (5 boxes):** per-laptop boxes for the distinguishable
  foreground/mid instances; image proposed as a `difficult` example (dense,
  receding, overlapping cluster — guidelines §9/§11). Corrected label:
  `laptop_openimages_000003.txt`.
- **Reason / status:** re-annotation to satisfy one-box-per-instance;
  `REMEDIATION_REVIEW_PENDING`, `PENDING_REVIEW`. Source annotation not modified.

### 2.3 QA04 — missing instance added (PART 4)

- **Original annotation (5 boxes):** front MacBook + 4 small background laptops.
- **Corrected annotation (6 boxes):** the five source boxes are **preserved**;
  one box is added for the prominent open sticker-covered laptop (centre-right)
  the source omitted. Corrected label: `laptop_openimages_000004.txt`.
- **Reason / status:** missing prominent foreground instance;
  `REMEDIATION_REVIEW_PENDING`, `PENDING_REVIEW`. Source annotation not modified.

### 2.4 QA15 — loose box tightened (PART 5)

- **Original annotation (1 box):** `0 0.212110 0.500521 0.424219 0.996875` —
  near-full-frame-height box; ~half the area is cat/desk, not laptop (violates
  tight-box guideline §4).
- **Corrected annotation (1 box):** `0 0.205078 0.570312 0.410156 0.859375` —
  top raised to the screen bezel and right edge pulled in to the truncated white
  MacBook (screen + keyboard base) only. Corrected label:
  `laptop_openimages_000014.txt`.
- **Reason / status:** tightened per guidelines §4; `REMEDIATION_REVIEW_PENDING`,
  `PENDING_REVIEW`. Source annotation not modified.

### 2.5 QA01 — held REVIEW_PENDING (PART 6)

- **Annotation (unchanged, 1 box):** `0 0.626667 0.211250 0.743333 0.422500`.
- **Status:** `REVIEW_PENDING`, `PENDING_REVIEW`. **Not** automatically
  discarded and **not** automatically accepted.
- **Reason:** borderline low-light blur (blur 45.6, the lowest in the set); the
  laptop is still identifiable and the box is correct. The dataset readiness
  checklist (Gate A) authorises **no** automatic accept/reject for a
  below-threshold blur score — a below-threshold image may be retained **only**
  as a deliberate `difficult` sample with explicit human sign-off. That sign-off
  does not exist, and no new threshold was invented, so the honest outcome is to
  hold the image for a human reviewer.

---

## 3. Canonical filename ingestion (PART 7)

- **New directory:** `dataset_acquisition/staging/openimages_laptop_canonical_v1/`
  (`images/`, `labels/`, `provenance/`, `reports/`, `validation/`). The
  source-preserved `openimages_laptop_v1/` staging is untouched.
- **Convention:** `<class_name>_<source_tag>_<seq>.<ext>` — here
  `laptop_openimages_<NNNNNN>.jpg`, parsed and confirmed valid by the code-owned
  `_ecotrace_toolkit.parse_collection_filename`.
- **Mapping:** deterministic `source stem → canonical stem`, sequence assigned in
  sorted source-stem order over **retained** images (the excluded QA14 consumes
  no sequence number, so numbering is gap-free). Full map:
  `reports/canonical_filename_map.json`.

| Canonical stem | Source stem | QA | Note |
| -------------- | ----------- | -- | ---- |
| `laptop_openimages_000001` | `00767fb6565581c6` | 01 | held REVIEW_PENDING |
| `laptop_openimages_000003` | `0171ad35f1651698` | 03 | re-annotated (split) |
| `laptop_openimages_000004` | `14587a599414300c` | 04 | re-annotated (add) |
| `laptop_openimages_000014` | `936a6d462e9d4873` | 15 | re-annotated (tighten) |
| `laptop_openimages_000020` | `f663d03a10e841bf` | 21 | clean ACCEPT |

(The remaining 15 retained images are clean ACCEPTs; the excluded `79182035199f2b58` (QA14) maps to no canonical file.)

Each canonical record carries: canonical filename, source filename, source
SHA-256, source dataset (`Open Images V7`), source class (`Laptop`), EcoTrace
class (`laptop`), EcoTrace class_id (`0`), original object count, corrected
object count, remediation status, and reviewer status.

---

## 4. Final accepted counts (observed)

| Statistic | Value |
| --------- | ----- |
| Source images | 21 |
| Excluded images | 1 (QA14) |
| **Retained canonical images** | **20** |
| — clean ACCEPT (unchanged) | 16 |
| — re-annotated (pending review) | 3 (QA03, QA04, QA15) |
| — held REVIEW_PENDING | 1 (QA01) |
| Retained objects (original) | 34 |
| **Retained objects (corrected)** | **39** |
| — QA03 split | 1 → 5 (+4) |
| — QA04 add | 5 → 6 (+1) |
| — all others | unchanged |

---

## 5. Validation results on the canonical candidate (PART 8)

Run with the **existing frozen validators** — no new validation logic, nothing
suppressed. Reports under `openimages_laptop_canonical_v1/validation/`.

| Check | Tool (existing) | Result |
| ----- | --------------- | ------ |
| Annotation validation (P4.2.2) | `scripts/validate_annotations.py` | **`is_valid: true`** — 20 labels, 39 boxes, all `class_id 0`, 0 issues, 0 orphans, 0 missing |
| Image/label pairing | `validate_annotations.py` summary | `images_without_labels: 0`, `labels_without_images: 0` |
| Image validation — filename+structural (P4.2.1) | `scripts/validate_image_batch.py --allow-quality-warnings` | **PASS, 0 blocking** — `FILENAME_CONVENTION` **gone** (was 21×); 3 non-blocking `IMAGE_BLURRY` warnings |
| Image validation — default policy (blur blocking) | `scripts/validate_image_batch.py` | **FAIL, 3 blocking `IMAGE_BLURRY`** (QA01, QA17, QA18) — reported honestly; see §6 |
| Duplicate detection | frozen `device_ai.dataset.duplicates.DuplicateDetector` | 20 images, **0 exact/near-duplicate pairs** (Hamming threshold 5) |

**The mandated outcome held:** the expected `FILENAME_CONVENTION` failure (21×
in the source-preserved pilot) **disappeared** in canonical staging — all 20
canonical filenames satisfy the convention.

---

## 6. Remaining warnings / errors (nothing suppressed)

- **`IMAGE_BLURRY` (3×, non-integrity):** `laptop_openimages_000001` (QA01, blur
  45.6), `_000016` (QA17, blur 60.0), `_000017` (QA18, blur 77.0). These are the
  same blur flags recorded in the pilot QA:
  - QA17/QA18 were judged **acceptable** difficult examples in the visual QA
    (the boxed laptop is in focus; the low score is a low-texture/soft-global
    artifact), but they carry **no Gate A `difficult` sign-off**, so under the
    default blur-blocking policy they remain blocking. They are surfaced, not
    hidden.
  - QA01 is held `REVIEW_PENDING` (§2.5).
  - The 4th blurry pilot image (QA14) was excluded, so only 3 remain.
- **No image-integrity failures:** no corrupt, undersized, oversized, or
  unreadable images.
- **No annotation-validation failures, no orphans, no duplicates.**

> These three blur warnings are the **only** reason the strict (default) image
> policy reports FAIL. They are non-integrity quality flags awaiting the human
> `difficult`-sample sign-off that Gate A requires; no threshold was invented to
> clear them.

---

## 7. Provenance guarantees (restated)

- Open Images source and `openimages_laptop_v1/` staging: **read-only**, byte-unchanged.
- Every retained canonical image: verbatim byte copy, SHA-256 re-verified against
  source provenance on write.
- Corrected boxes: normalised + range-validated via frozen-style `convert_box`;
  class id discovered, not assumed.
- Determinism: sorted-stem sequence assignment, injected timestamp, all JSON
  `indent=2, sort_keys=True`.
- Traceability: `source stem → canonical stem` mapping + per-image provenance
  records link every canonical artifact back to its Open Images origin.

---

## 8. Scope statement

This remains a **single-class (`laptop`) Dataset v1.0 acquisition pilot**. It is
**NOT** Dataset v1.0, it is **NOT** a release, and it asserts **no** dataset-level
quality metric. No model was trained, no additional classes were downloaded, and
nothing was committed. Dataset v1.0 assembly, split, freeze, and release remain
governed separately by `docs/ai/dataset_v1_freeze_policy.md` and
`docs/engineering/dataset_v1_release.md`.

---

## 9. Machine-readable artifacts

| Artifact | Path |
| -------- | ---- |
| Remediation manifest | `dataset_acquisition/staging/openimages_laptop_canonical_v1/reports/remediation_manifest.json` |
| Canonical filename map | `dataset_acquisition/staging/openimages_laptop_canonical_v1/reports/canonical_filename_map.json` |
| Canonical provenance manifest | `dataset_acquisition/staging/openimages_laptop_canonical_v1/provenance/provenance_manifest.json` |
| Annotation validation | `dataset_acquisition/staging/openimages_laptop_canonical_v1/validation/annotation_validation.json` |
| Image validation (warnings allowed) | `dataset_acquisition/staging/openimages_laptop_canonical_v1/validation/image_validation.json` |
| Image validation (strict / blur-blocking) | `dataset_acquisition/staging/openimages_laptop_canonical_v1/validation/image_validation_strict.json` |
| Duplicate report | `dataset_acquisition/staging/openimages_laptop_canonical_v1/validation/duplicate_report.json` |

---

## 10. Pilot decision

### `PILOT_REVIEW_REQUIRED`

The canonical ingestion is **structurally clean**: annotation validation passes,
image/label pairing is complete, the filename convention now holds (the expected
`FILENAME_CONVENTION` failure is resolved), and there are zero duplicates. The
converter/ingestion pipeline showed **no implementation defect** — every original
problem originated in the source Open Images annotations, faithfully reproduced.

The verdict is **`PILOT_REVIEW_REQUIRED`**, not `PILOT_READY_FOR_SCALE`, because
the P4.2.4 readiness bar is not fully met and the remaining items are, by policy,
**human** decisions the tooling cannot make for itself:

1. **QA01 is unresolved.** It is `REVIEW_PENDING` by design — Gate A grants no
   authority to auto-accept/reject a below-threshold blur image without human
   `difficult`-sample sign-off.
2. **The three re-annotations are `PENDING_REVIEW`.** Separation of duties
   (annotation review manual) forbids an author from certifying its own
   corrections; QA03/QA04/QA15 must pass independent first review.
3. **Three `IMAGE_BLURRY` flags remain** under the default policy, without the
   Gate A `difficult` sign-off that would clear them.

Once (1) a reviewer signs off QA01, (2) the three corrections pass independent
review, and (3) the blur difficult-sample sign-offs are recorded, the candidate
can be re-audited for `PILOT_READY_FOR_SCALE`.

---

> **STOP.** This checkpoint ends here. Per the sprint instruction: do **not**
> process other classes, download more data, train YOLO, assemble Dataset v1.0,
> or commit. Await explicit review and approval of this candidate before any
> next step.
