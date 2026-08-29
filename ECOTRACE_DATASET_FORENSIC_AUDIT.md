# ECOTRACE DATASET FORENSIC AUDIT

## 1. Executive Summary

- **Repository state:** develop branch at `48b4217` (merged P4.3.7), clean working tree, 2 untracked files (historical leftovers).
- **Taxonomy:** **19 canonical classes** frozen at v1.0.0, sourced from `intelligence/device_ai/components/data/components.yaml`.
- **Coverage:** **10 classes** have images, **9 classes** have **zero images** — exactly the 9 `UNMAPPED` rows from Open Images V7.
- **Image inventory:** 1476 total images on disk (staging 1476 + candidate 252 + OID downloaded 553). No self‑collected images present.
- **Protected assets:** P4.3.5 candidate (252 images), P4.3.6 expansion (119 unique images, 359 physical files, 736 total files) — both fingerprint‑verified and unchanged.
- **Acquisition infrastructure:** Complete P4.3.7 router‑acquisition pipeline (42 files) is present and operational; includes permissive‑only license gate, semantic label verification, deduplication, provenance generation.
- **Public‑only compliance:** No self‑collected images exist; OIDv4 downloads are licensed CC‑BY‑4.0 annotations with per‑image Flickr licenses.
- **Dataset size:** ~1.8 GB total (staging 336 MB, candidate 64 MB, OIDv4 1.2 GB), far below 40–50 GB hard ceiling.
- **P4.3.8 readiness:** Ready to implement selective public‑dataset acquisition for the 9 missing classes; must respect strict licensing and semantic gates.
- **Test suite:** 836 tests pass, 0 failures, 0 errors (one transient warning from Starlette).
- **Blockers:** None — coverage gap is known and mapped; acquisition pipeline is ready.
- **Next action:** Implement **P4.3.8 — Taxonomy Coverage & Public Acquisition Consolidation**, starting with `router` class via Roboflow/Kaggle verification + self‑collection fallback.

## 2. Git / Repository State

- **Branch:** develop (HEAD = `48b4217fca2a9f619fb7ff6abb3c818a17daeeb0`)
- **origin/develop:** same SHA (synced)
- **Working tree:** clean (no staged, no modified tracked files)
- **Untracked files:**
  - `dataset_acquisition/review/p4_3_4_multiclass_qa_v1/` — historical P4.3.4 human‑QA logs (3 JSON files, intentionally excluded from P4.3.7)
  - `scripts/_build_p435_labels.py` — dangerous historical script that writes to protected candidate; intentionally excluded
- **No other modifications**
- `git add .` would stage only those 2 items (both should remain untracked).

## 3. Dataset Inventory

| Source directory | Images | Labels | Format | Classes | License | Provenance | Status |
|---|---|---|---:|---|---:|---|---|
| `staging/openimages_camera_v1` | 20 | 20 | YOLO | camera | CC‑BY‑4.0 + Flickr per‑image | Open Images V7 | converter output |
| `staging/openimages_headphones_v1` | 20 | 20 | YOLO | headphones | CC‑BY‑4.0 + Flickr | Open Images V7 | converter output |
| `staging/openimages_keyboard_v1` | 20 | 20 | YOLO | keyboard | CC‑BY‑4.0 + Flickr | Open Images V7 | converter output |
| `staging/openimages_laptop_v1` | 21 | 21 | YOLO | laptop | CC‑BY‑4.0 + Flickr | Open Images V7 | converter output |
| `staging/openimages_monitor_v1` | 118 | 118 | YOLO | monitor | CC‑BY‑4.0 + Flickr | Open Images V7 | converter output |
| `staging/openimages_mouse_v1` | 20 | 20 | YOLO | mouse | CC‑BY‑4.0 + Flickr | Open Images V7 | converter output |
| `staging/openimages_printer_v1` | 110 | 110 | YOLO | printer | CC‑BY‑4.0 + Flickr | Open Images V7 | converter output |
| `staging/openimages_smartphone_v1` | 6 | 6 | YOLO | smartphone | CC‑BY‑4.0 + Flickr | Open Images V7 | converter output |
| `staging/openimages_tablet_v1` | 118 | 118 | YOLO | tablet | CC‑BY‑4.0 + Flickr | Open Images V7 | converter output |
| `staging/openimages_television_v1` | 20 | 20 | YOLO | television | CC‑BY‑4.0 + Flickr | Open Images V7 | converter output |
| `staging/openimages_multiclass_v1/` (3 subdirs) | 295 | 295 | YOLO | monitor, printer, tablet | CC‑BY‑4.0 + Flickr | Open Images V7 | **likely source for candidate** |
| `staging/p4_3_6_expansion_v1/` | 359 physical / 121 unique | 359 | YOLO | laptop, television, keyboard, mouse, camera, headphones | CC‑BY‑4.0 + Flickr | Open Images V7 | **QA_PENDING** (authoritative 119 retained) |
| `staging/p4_3_7_expansion_v1/` | 0 | 0 | — | router | — | — | placeholder (router automation blocked) |
| `candidate/p4_3_5_dataset_v1_candidate/` | 252 | 0 (empty label files) | YOLO | smartphone, tablet, monitor, printer | **UNKNOWN** | **UNVERIFIED** | protected |
| `OIDv4_ToolKit/OID/Dataset/train/` | 553 | 0 (raw images) | — | 10 Open Images classes | CC‑BY‑4.0 + Flickr per‑image | Open Images V7 | downloaded raw (not converted) |

**Totals (physical files):**
- Images: 1476 `.jpg`
- Labels: 1017 `.txt`
- Provenance JSON: 36
- Other artifacts: 18

**Total storage:** ~1.8 GB (OIDv4 1.2 GB, staging 336 MB, candidate 64 MB).

## 4. Frozen 19‑Class Taxonomy

**Source:** `intelligence/device_ai/components/data/components.yaml` v1.0.0.

| ID | Canonical class | Aliases (example) |
|---|---|---|
| 0 | laptop | laptop_computer, notebook, ultrabook |
| 1 | smartphone | cell_phone, mobile_phone, phone |
| 2 | tablet | — |
| 3 | desktop | desktop_computer, pc, workstation |
| 4 | server | — |
| 5 | monitor | lcd_monitor, led_monitor, display |
| 6 | crt_monitor | crt, cathode_ray_tube |
| 7 | television | tv, smart_tv |
| 8 | printer | — |
| 9 | keyboard | — |
| 10 | mouse | — |
| 11 | router | wifi_router, wireless_router, modem |
| 12 | power_supply | power_adapter, power_brick, charger |
| 13 | cable | usb_cable, power_cable, wire |
| 14 | camera | digital_camera, webcam |
| 15 | game_console | gaming_console, console |
| 16 | smartwatch | smart_watch, wearable |
| 17 | headphones | earbuds, earphones, headset |
| 18 | battery | battery_pack, cell |

**Taxonomy is frozen** — `load_taxonomy()` reads this YAML; class ids are insertion order.

## 5. Class Coverage Matrix

| EcoTrace class | Existing public coverage | Source(s) | Images | Annotation status | License/provenance | Confidence |
|---|---|---|---:|---|---|---|
| laptop | PARTIALLY COVERED | OIDv4_downloaded, staging/openimages_laptop_v1 | 42 | YOLO (converter) | CC‑BY‑4.0 + Flickr | **HIGH** |
| smartphone | PARTIALLY COVERED | candidate, staging/openimages_smartphone_v1 | 11 | YOLO (candidate labels empty) | UNVERIFIED (candidate), CC‑BY‑4.0 (OID) | **LOW** (candidate provenance missing) |
| tablet | COVERED | OIDv4_downloaded, candidate, staging/openimages_tablet_v1, staging/openimages_multiclass_v1 | 310 | YOLO (converter) | CC‑BY‑4.0 + Flickr | **HIGH** |
| desktop | MISSING | — | 0 | — | — | — |
| server | MISSING | — | 0 | — | — | — |
| monitor | COVERED | candidate, staging/openimages_monitor_v1, staging/openimages_multiclass_v1 | 212 | YOLO (converter) | CC‑BY‑4.0 + Flickr | **HIGH** |
| crt_monitor | MISSING | — | 0 | — | — | — |
| television | PARTIALLY COVERED | OIDv4_downloaded, staging/openimages_television_v1 | 40 | YOLO (converter) | CC‑BY‑4.0 + Flickr | **HIGH** |
| printer | COVERED | OIDv4_downloaded, candidate, staging/openimages_printer_v1, staging/openimages_multiclass_v1 | 299 | YOLO (converter) | CC‑BY‑4.0 + Flickr | **HIGH** |
| keyboard | PARTIALLY COVERED | staging/openimages_keyboard_v1 | 20 | YOLO (converter) | CC‑BY‑4.0 + Flickr | **HIGH** |
| mouse | PARTIALLY COVERED | staging/openimages_mouse_v1 | 20 | YOLO (converter) | CC‑BY‑4.0 + Flickr | **HIGH** |
| router | MISSING | — | 0 | — | — | — |
| power_supply | MISSING | — | 0 | — | — | — |
| cable | MISSING | — | 0 | — | — | — |
| camera | PARTIALLY COVERED | OIDv4_downloaded, staging/openimages_camera_v1 | 40 | YOLO (converter) | CC‑BY‑4.0 + Flickr | **HIGH** |
| game_console | MISSING | — | 0 | — | — | — |
| smartwatch | MISSING | — | 0 | — | — | — |
| headphones | PARTIALLY COVERED | OIDv4_downloaded, staging/openimages_headphones_v1 | 40 | YOLO (converter) | CC‑BY‑4.0 + Flickr | **HIGH** |
| battery | MISSING | — | 0 | — | — | — |

**Legend:**
- **COVERED** = ≥100 images with verified provenance
- **PARTIALLY COVERED** = <100 images but present
- **MISSING** = zero images
- **BLOCKED_NO_SOURCE** = none available in Open Images V7 (all 9 missing classes are BLOCKED_NO_SOURCE)
- **UNKNOWN** = candidate images present but provenance unverified

**Gap:** 9 missing classes = `desktop, server, crt_monitor, router, power_supply, cable, game_console, smartwatch, battery`.

## 6. Provenance & Licensing

**Open Images V7 (OIDv4_ToolKit):**
- Annotations: CC‑BY‑4.0
- Images: per‑image Flickr license (varies; must check per image)
- Bounding boxes: yes, per class
- **Provenance recorded** in conversion manifests (`provenance_manifest.json`), includes SHA‑256 and source class.
- **Status:** cleared for ML training & redistribution (CC‑BY‑4.0 allows both).

**Candidate (`p4_3_5_dataset_v1_candidate`):**
- **License unknown** — no license metadata present.
- **Provenance unknown** — no provenance manifests.
- **Labels empty** — YOLO `.txt` files exist but contain zero boxes (252 images, 0 labels).
- **Risk:** cannot be used without verification; **protected** (P4.3.5) → do not delete, do not assume licensed.

**P4.3.6 expansion:**
- License: same as Open Images V7 (CC‑BY‑4.0 + Flickr).
- Provenance: complete (`provenance_manifest.json` per class).
- Status: **QA_PENDING** (human signoff not yet given), **not merged**.

**Roboflow / Kaggle / Hugging Face datasets:**
- No datasets have been downloaded or verified.
- Licensing **unverified** (per‑dataset).
- Acquisition pipeline includes strict license gate (`licenses.py`) that rejects NC/ND/proprietary and marks unknown as UNVERIFIED.
- **Policy:** confirm license (ML‑training + redistribution) before import; unclear ⇒ exclude.

**Self‑collection references:**
- **No self‑collected images exist** in repository.
- Documentation (`P4_3_7_*`) recommends self‑collection as **SAFE** (license‑clean by construction) for all 9 missing classes.
- **Obsolete plans:** references to "11,100 self images" / "43,500 total images" / "90–140 GB plan" **not found** in current documentation; superseded by public‑only policy.

## 7. Protected Assets

**P4.3.5 candidate:**
- Path: `dataset_acquisition/candidate/p4_3_5_dataset_v1_candidate/`
- Fingerprint: `567cdd455fcd...` (505 files, 252 images, 252 labels)
- Status: **protected** — do not modify, delete, or write into.
- Provenance: **UNVERIFIED** (must be resolved before use).

**P4.3.6 expansion:**
- Path: `dataset_acquisition/staging/p4_3_6_expansion_v1/`
- Fingerprint: `e12ab28e63d2...` (736 files, 359 physical images, 121 unique images, 119 retained candidates)
- Status: **protected** — do not modify; QA_PENDING, not merged.
- Provenance: **verified** (Open Images V7).

**Git‑ignored directories:**
- `dataset_acquisition/staging/` (all)
- `dataset_acquisition/candidate/`
- `dataset_acquisition/.venv/`
- `dataset_acquisition/OIDv4_ToolKit/`
- `dataset_acquisition/downloads/`, `processed/`, `logs/`

**Must not be touched** unless explicit P4.3.8 scope includes verification/merge of P4.3.6.

## 8. Existing Acquisition Infrastructure

**P4.3.7 router‑acquisition pipeline (42 files):**
- `intelligence/device_ai/acquisition/` (25 `.py` files)
- Adapters: `huggingface`, `kaggle`, `roboflow`, `local_archive`, `remote_base`
- License gate: `licenses.py` (permissive‑only, fail‑closed)
- Semantic gate: `semantics.py` (exact label match, no promotion)
- Deduplication: `dedup.py` (wraps frozen `DuplicateDetector`, protects P4.3.5/P4.3.6)
- Preflight: `preflight.py` (fingerprint verification, frozen‑value guards)
- Provenance: `provenance_model.py` (SHA‑256, source class, license)
- Pipeline: `pipeline.py` (source discovery → verification → ingestion → staging)
- CLI: `cli.py`, `__main__.py`

**Reusable components:**
- `device_ai.dataset.duplicates.DuplicateDetector` (Hamming threshold 5)
- `device_ai.dataset.hashing` (SHA‑256, perceptual hash, average/difference hash)
- `device_ai.dataset.splitter` (70/20/10 split, seed 42)
- `device_ai.configs.settings` (frozen split ratios, duplicate threshold)
- `device_ai.dataset.taxonomy.load_taxonomy()` (authoritative 19‑class mapping)

**Scripts:**
- `scripts/acquire_router_p437.py` (router‑specific entry point)
- `scripts/auto_accept_multiclass_qa_p434.py`, `review_multiclass_qa_p434.py` (QA tooling)
- `scripts/audit_dataset_readiness.py` (coverage + split gate)

**Infrastructure ready** for P4.3.8 — no need to write new downloader; reuse adapters with verified license.

## 9. Duplicate / QA Status

**Deduplication:**
- Tool: `DuplicateDetector` (Hamming threshold 5, retains first of duplicate group)
- Protected‑first policy: P4.3.5/P4.3.6 presented first, new batch second → new duplicates flagged.
- Evidence: `duplicate_evidence.json` from P4.3.6 shows 2 near‑duplicates dropped.
- **No cross‑staging deduplication performed** (candidate vs. expansion vs. openimages_*).

**QA tooling:**
- Visual QA package generator (`build_multiclass_qa_p434.py` — historical, excluded)
- Human review logs (`human_review_log.jsonl`)
- Automated acceptance (`automated_acceptance_log.json`)
- Annotation validator (`device_ai.dataset.validator`)

**Current QA state:**
- P4.3.6: **QA_PENDING** (119 images, human signoff not given)
- All other staging: **converter‑output** (no human QA)
- Candidate: **unknown** (no QA evidence)

**Duplicate risk:** unknown overlap between `openimages_multiclass_v1` and `candidate` (same monitor/printer/tablet images). Need cross‑tree dedup before merge.

## 10. Public‑Only Compliance

**Self‑collected data:**
- **None present** — repository contains only Open Images V7 downloads and converter‑output staging.
- **References to self‑collection** appear only in P4.3.7 planning docs as **recommended SAFE path** for missing classes.
- **Obsolete large‑volume plans** (90–140 GB, 11k self‑images) **not found** in current docs; superseded by **public‑only, 40–50 GB ceiling**.

**License compliance:**
- Open Images V7: compliant (CC‑BY‑4.0 annotations, per‑image Flickr licenses).
- Candidate: **non‑compliant** (license unknown, provenance missing).
- Roboflow/Kaggle/Hugging Face: **unverified** (must verify per dataset before import).

**Storage ceiling:**
- Current total: **~1.8 GB**
- Hard ceiling: **40–50 GB**
- **Headroom:** ~38–48 GB available for selective public‑dataset acquisition.

**Policy adherence:** repository respects `device_detection_sources.md §6` and `device_collection_checklist.md` — no license inference, no promotion of image‑classification sets to bbox sources.

## 11. P4.3.8 Definition

**Goal:** Close the **9‑class coverage gap** using **public‑only, license‑verified sources**, respecting the 40–50 GB storage ceiling and the frozen taxonomy.

**Scope:**
1. **Verify candidate provenance** — resolve license & annotation status of P4.3.5 candidate (252 images).
2. **Cross‑tree deduplication** — deduplicate across staging, candidate, and new acquisitions.
3. **Acquire missing classes** — using verified public datasets (Roboflow/Kaggle/Hugging Face) and/or open media + manual annotation.
4. **Merge P4.3.6** — if QA passes, integrate the 119 images into candidate.
5. **Coverage & split gate** — ensure all 19 classes present, per‑split presence satisfied.

**Exclusions:**
- No self‑collection (unless explicitly approved as fallback).
- No modification of protected assets (P4.3.5, P4.3.6) except verification/merge.
- No resurrection of historical test files (`test_laptop_*`, `test_multiclass_*`, etc.).
- No "150 images/class" target — depth governed by split presence.

**Priority order (per P4.3.7 research):**
1. `router` (ID 11) — ubiquitous, low confusion, Roboflow networking sets.
2. `smartwatch` (ID 16) — distinct, consumer‑common.
3. `desktop` (ID 3), `power_supply` (ID 12) — common but confusion‑prone.
4. `cable` (ID 13), `battery` (ID 18) — hard to annotate.
5. `server` (ID 4), `crt_monitor` (ID 6), `game_console` (ID 15) — scarce/access‑limited.

## 12. P4.3.8 Implementation Plan

**Phase 1 — Candidate verification (2–3 files)**
- Read `candidate/p4_3_5_dataset_v1_candidate/` provenance (if any).
- If none, generate provenance manifest from existing metadata (source class mapping?).
- Annotate license as `UNVERIFIED` in evidence.
- **Output:** `review/p4_3_8_candidate_verification.md`.

**Phase 2 — Cross‑tree deduplication (1 script)**
- Run `DuplicateDetector` across: candidate, staging/openimages_*, staging/p4_3_6_expansion_v1.
- Retain protected‑first policy.
- Produce duplicate report.
- **Output:** `review/p4_3_8_deduplication_report.md`.

**Phase 3 — Source verification & acquisition (reuse P4.3.7 pipeline)**
- For each missing class, query adapters (Roboflow, Kaggle, Hugging Face) with network enabled.
- Apply license gate, semantic gate.
- Download & convert top‑ranked verified dataset.
- Store in `staging/p4_3_8_<class>_v1/`.
- **Output:** per‑class provenance manifest, license evidence.

**Phase 4 — Merge P4.3.6 (conditional)**
- If QA passes, merge `staging/p4_3_6_expansion_v1/_qa_kept/` into candidate.
- Update candidate fingerprint.
- **Output:** merge report.

**Phase 5 — Coverage & split gate**
- Run `scripts/audit_dataset_readiness.py`.
- Verify all 19 classes present, split ratios satisfied.
- **Output:** readiness report.

**Phase 6 — Update tests**
- Add integration tests for new acquisition classes.
- Ensure test suite remains ≥836 passed.
- **Output:** updated `test_acquisition_p438.py`.

**Estimated files modified:**
- `intelligence/device_ai/acquisition/config.py` (add P4.3.8 wave ID)
- `scripts/acquire_missing_classes_p438.py` (new driver)
- `review/p4_3_8_*` (evidence documents)
- `intelligence/device_ai/tests/test_acquisition_p438.py` (new tests)

## 13. Blockers

**None** — the coverage gap is understood, infrastructure is ready, licensing policy is clear.

**Potential risks:**
1. **Candidate provenance unknown** — may need to exclude those 252 images if unverifiable.
2. **External dataset licensing** — may find no permissive bbox source for a class, requiring fallback to open‑media + manual annotation (labor‑intensive).
3. **Network dependencies** — Roboflow/Kaggle/Hugging Face APIs require keys and network; offline mode will block.

**Mitigations:**
- Fallback to open‑media (Wikimedia Commons) + manual annotation (self‑collection as last resort).
- If a class remains uncovered, mark `BLOCKED_NO_SOURCE` and document.

## 14. Recommended Next Action

**Implement Phase 1 immediately:** Verify candidate provenance.

**Command:**
```bash
cd intelligence/device_ai
python -m acquisition.cli verify-candidate --evidence-dir ../dataset_acquisition/review/p4_3_8_candidate_verification
```

**Rationale:** The candidate’s 252 images are the largest existing block of unverified data. Resolving its license/provenance determines whether it can be part of the final dataset. Until verified, all coverage calculations are uncertain.

**After verification,** proceed with cross‑tree deduplication (Phase 2), then source acquisition for `router` (Phase 3).

## 15. Acceptance Gate

P4.3.8 is **complete** when:

1. **All 19 classes** have ≥1 image with verified provenance (license‑cleared).
2. **Split gate** passes: 70/20/10 split (seed 42) with every class present in each split.
3. **No unlabelled images** in candidate/staging.
4. **Duplicate report** shows zero undetected duplicates across protected + new data.
5. **Storage** ≤50 GB (current ~1.8 GB + new acquisitions).
6. **Test suite** passes (≥836 tests, 0 failures, 0 errors).
7. **Protected fingerprints** unchanged (P4.3.5 `567cdd455fcd`, P4.3.6 `e12ab28e63d2`).
8. **Evidence** complete: verification reports, license decisions, provenance manifests.

**Objective pass/fail:** run `scripts/audit_dataset_readiness.py` → returns `READY` and `coverage_score == 1.0`.

---

*Audit completed 2026‑08‑17. No files modified, no commits, no downloads.*