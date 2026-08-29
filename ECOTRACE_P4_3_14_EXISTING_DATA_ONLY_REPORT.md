# EcoTrace India — P4.3.14 EXISTING-DATA-ONLY EXPERIMENT — Consolidated Report

**Date:** 2026-08-24
**Unit (staging):** `dataset_acquisition/staging/p4_3_14_existing_data_only_v1/`
**Unit (training):** `dataset_acquisition/training/p4_3_14_existing_data_only_v1/`
**Status flags (held throughout):** `is_dataset_v1 = false`, `is_released = false`, **no commits, no pushes**.
**Hard constraints honored:** ZERO new downloads · ZERO source modification · ZERO frozen-gate modification · ZERO fabricated annotations · ZERO ImageID substitution · ZERO protected-tree modification.

> ## ⚠ EXECUTION STATUS — INTERIM (read this first)
> This report is **complete for every step whose inputs already exist on disk** (STEP 1 inventory, STEP 2 reconciliation, STEP 7/11 coverage, STEP 12 blockers, STEP 13 recommendation, plus the full 665 baseline for STEP 10). The steps that require **running code** — STEP 3 (frozen-pipeline promotion of camera), STEP 5 (resumable promotion), STEP 6 (dataset assembly), STEP 8 (training), STEP 9 (evaluation), and therefore the STEP 10 head-to-head numbers — are marked **`PENDING EXECUTION`** because the host's Bash/IDE safety-classifier service (`openrouter/nvidia/nemotron-…`) has been **timed-out for this entire session**, which gates *all* command execution (both `Bash` and the Jupyter kernel). **No pipeline, dataset, or metric number in the PENDING sections has been fabricated** — they will be filled by running the four staged commands in §Execution Plan. All four scripts are written, parity-faithful, and ready.

---

## 1. Inventory (STEP 1) — every existing acquisition/staging tree on disk

**Candidate new data = the P4.3.11 train-expansion archives that were built but never run through the frozen pipeline.** The prior assumption of *five* untapped archives (camera, mouse, printer, smartphone, tablet) is **refuted by disk evidence** — only **camera** was actually downloaded.

| class | archive | images on disk | labels on disk | manifest plan | actually downloaded | already promoted (in 665) | not-yet-processed | usable downstream |
|-------|---------|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| **camera** | P4.3.11 | **337** | **337** | 3077 planned | **337 (ledger)** | 7 (from P4.3.10) | **337 (never pipelined)** | **YES — candidate** |
| mouse | P4.3.11 | 0 | 0 | 588 planned | 0 (all `not_acquired`) | 26 (P4.3.10) | 0 | NO — link-rot, no files |
| printer | P4.3.11 | 0 | 0 | planned | 0 | 27 (P4.3.10) | 0 | NO — link-rot, no files |
| smartphone | P4.3.11 | 0 | 0 | planned | 0 | 35 (P4.3.10) | 0 | NO — link-rot, no files |
| tablet | P4.3.11 | 0 | 0 | planned | 0 | 23 (P4.3.10) | 0 | NO — link-rot, no files |
| headphones | P4.3.11 | ~841 | ~841 | — | yes | **430 promoted** | 411 (360 UNVERIFIED + 51 REJECT) | NO — 0 more without a forbidden override |
| television | P4.3.13/older | present | present | — | yes | 0 | all AUTO_REJECT (16) | NO — frozen QA rejected |
| keyboard | P4.3.13/older | present | present | — | yes | 0 | all AUTO_REJECT (23) | NO — frozen QA rejected |

**Net:** the only promotable *new* on-disk data in the entire repository is **337 camera images (class_id 14)**. Everything else is either already in the 665, or was already adjudicated 0-usable by the frozen gates (re-running deterministic QA on the same bytes cannot change that, and overriding it is forbidden).

*(The machine-readable `reports/inventory.json` artifact is produced by `inventory.py` — see §Execution Plan step 1. The table above is derived directly from the underlying evidence files, which were read this session.)*

---

## 2. Reconciliation (STEP 2) — per-image provenance for the camera candidate

The task's rule — *"Do NOT assume an image is valid merely because it exists in a folder"* — applies exactly here, because `archive_manifest_camera.json` shows **all 3077 records `not_acquired` / `verified:false`**. That manifest is a **stale pre-download PLAN that was never back-filled**; it is **not** the acquisition record.

**The authoritative acquisition record is `_work/dl_ledger_camera.json`:**

| ledger field | count | meaning |
|---|:--:|---|
| total attempted records | **875** | seed-42 selection actually attempted |
| `status: downloaded` | **337** | bytes fetched — **matches the 337 files on disk exactly** |
| `verified: true` | **337** | `base64(md5(downloaded_bytes)) == OI OriginalMD5` (gold-standard OI byte-verification) |
| `status: download_failed` | **538** | link-rot — **no files on disk** (correctly absent) |

**Verdict:** the 337 on-disk camera images **have valid acquisition + provenance evidence** (byte-verified CC-BY-2.0 Open Images V7, MID `/m/0dv5r`, "Camera"). Provenance *confirms* them; the stale manifest is a bookkeeping artifact, not a provenance failure. The frozen pipeline independently re-verifies at ingest and remains the authority. Archive labels carry the single-class local id `0` (per the archive `data.yaml` `names:{0:"Camera"}`); the frozen ingest remaps to taxonomy id **14**, exactly as it remapped headphones→17 in the 665 (which recorded **0 label-id anomalies**).

---

## 3. Promotion through the frozen pipeline (STEP 3) — `PENDING EXECUTION`

`promote_existing.py --all` runs the **AUDITED, UNMODIFIED** frozen pipeline over the camera archive: preflight → gates → ingest → provenance → `run_dedup` → `run_automated_qa(duplicate_paths=dedup.batch_duplicates)` → `run_split`, then `evaluate_promotion`. It processes **camera** and safely skips mouse/printer/smartphone/tablet as `NO_SOURCE` (no `images/` dir). No gate is forked or weakened; no disposition is flipped.

- **Protected roots for dedup:** the promoted 665 dataset (`training/p4_3_preliminary_baseline_v1/dataset`) + any P4.3.14 sibling already staged. The source archive is never in the protected set (would self-match).
- **Ceiling:** 337. **Expected < 337** after deterministic dedup (Hamming ≤ 5 vs the 665) + automated QA (AUTO_REJECT/UNVERIFIED) + split. The exact `PROMOTED / AUTO_ACCEPT_NOT_PROMOTED / UNVERIFIED / AUTO_REJECT` counts are produced by the run and will be inserted here from `review/camera/automation/promotion_evidence.json`. **Not fabricated.**

## 4. De-duplication (STEP 4) — `PENDING EXECUTION`
Frozen `run_dedup` (perceptual-hash, Hamming ≤ 5, protected-first) vs the 665. P4.3.11 train IDs vs the 665 (P4.3.9/10 val+test-derived) are expected to be largely disjoint (prior analysis: split ID overlap = 0), so most rejections would be near-duplicate content hits, count TBD by the run → `duplicate_evidence.json`.

## 5. Automated QA (STEP 5) — `PENDING EXECUTION`
Frozen `run_automated_qa` (resolution/aspect/label-sanity/duplicate-aware) with `taxonomy_id=14`, `num_classes=19`. Counts → `automated_qa.json`. The resumable wrapper adds only reap-resilience (integrity gate: `compute_sha256` vs provenance, SystemExit on mismatch; skip-if-cached artifacts) — it never bypasses a gate.

## 6. Provenance integrity (STEP 6 part A) — `PENDING EXECUTION for the assembled set`
Assembly (`build_p4314_dataset.py`) re-checks every copied image: sha256 vs evidence, label class-ids == `[14]`, no duplicate destination names. Reports `sha256_mismatches` and `label_class_id_anomalies` (both expected 0, as in the 665). Baseline provenance is already clean (below).

---

## 7. Final dataset composition (STEP 6 part B) — `PENDING EXECUTION` (baseline shown, delta pending)

**RAW AVAILABLE (existing, promotable):** 665 baseline images **+ up to 337 camera** (pre-gate ceiling).
**TRAINING USED:** `665 + (camera PROMOTED count)`. **Default: NO train cap** — P4.3.12 established that capping the dominant class does not beat the 665 baseline, and the task requires the *largest legitimate* dataset (val/test always full; a cap would only ever be a deterministic seed-42 train-only option, unused by default).

**665 baseline composition (verified this session):**

| class | train | val | test | total |
|---|:--:|:--:|:--:|:--:|
| camera | 4 | 1 | 2 | **7** |
| headphones | 303 | 86 | 44 | 433 |
| laptop | 41 | 11 | 7 | 59 |
| monitor | 38 | 11 | 6 | 55 |
| smartphone | 24 | 7 | 4 | 35 |
| printer | 18 | 5 | 4 | 27 |
| mouse | 18 | 5 | 3 | 26 |
| tablet | 16 | 4 | 3 | 23 |
| **total** | **462** | **130** | **73** | **665** |

The P4.3.14 assembled set = this table with **camera** grown by the PROMOTED count (split verbatim from the frozen split), all other rows identical. **Coverage stays 8/19** (camera is already populated) — the experiment adds *depth*, not *breadth*.

---

## 8. Training configuration (STEP 8) — `PENDING EXECUTION`

Trainer staged: `training/p4_3_14_existing_data_only_v1/_tooling/train_yolo11_p4314.py` — a byte-faithful copy of the frozen-verified baseline trainer, defaults **pinned to the authoritative 665 recipe** for an apples-to-apples comparison:

```
model=yolo11n.pt · epochs=50 · imgsz=512 · batch=8 · seed=42 · device=cpu · workers=0 · cache=False · patience=20 · --resume (reap-safe: last.pt every epoch)
```

**Guard:** if the assembled dataset is byte-identical to the 665 (i.e., **camera PROMOTED = 0**), training is **skipped** and the outcome is **`DATASET_UNCHANGED`** (STEP 10 decision D) — no wasted 50-epoch CPU run, per the task.

## 9. Evaluation (STEP 9) — `PENDING EXECUTION`
`best.pt` evaluated on val **and** test → `metrics.json` (mAP50, mAP50-95, precision, recall, per-class). Same evaluator, same splits as the baseline.

---

## 10. Comparison vs the 665 baseline (STEP 10) — baseline locked, P4.3.14 `PENDING`

**Authoritative 665 baseline metrics (verified this session — `p4_3_preliminary_baseline_v1/metrics.json`, run `p43_after_headphones_yolo11n`):**

| split | mAP50 | mAP50-95 | precision | recall |
|---|:--:|:--:|:--:|:--:|
| **test** | **0.6300** | **0.4966** | 0.7129 | 0.5002 |
| val | 0.5166 | 0.4101 | 0.5737 | 0.4605 |

**Per-class TEST ap50 / recall (baseline):** camera **0.59 / 0.00** ← weakest · headphones 0.72 / 0.66 · laptop 0.46 / 0.38 · monitor 0.82 / 0.68 · mouse 0.40 / 0.33 · printer 0.86 / 0.75 · smartphone 0.38 / 0.20 · tablet 0.83 / 1.00.

**The decisive observation:** the baseline's camera **test recall is 0.00** (it detects no cameras) off just 4 train / 1 val / 2 test images. P4.3.14's 337 verified camera images target *exactly* this failure. The head-to-head (P4.3.14 mAP50/50-95 and, critically, camera recall) is filled after STEP 9.

**Decision rubric (letter assigned post-eval — NOT pre-judged):**
- **D · `DATASET_UNCHANGED`** — camera PROMOTED = 0 → dataset == 665 → skip training, keep the 665 model.
- **Improve** — P4.3.14 test mAP50-95 > 0.4966 (esp. camera recall > 0) → adopt P4.3.14 as the new preliminary baseline (still `is_released=false`).
- **Neutral/Regress** — no meaningful gain → keep the 665 model; camera depth alone insufficient.
- **Insufficient** — existing data exhausted at 8/19 → the ceiling of existing data is reached; further progress *requires* acquisition (STEP 13).

---

## 11. Coverage across all 19 taxonomy classes (STEP 7 / 11)

| status | classes | count | why |
|---|---|:--:|---|
| **PROMOTED (populated)** | camera*, headphones, laptop, monitor, mouse, printer, smartphone, tablet | **8** | in the 665; *camera gains depth this wave (pending) |
| **DEDUPED / QA-REJECTED (data exists, 0 usable)** | television, keyboard | 2 | frozen QA = all AUTO_REJECT; tv/kb fresh pool is 100% dedup-blocked (P4.3.12/13) |
| **NO LICENSED BBOX SOURCE (source-blocked)** | desktop, server, crt_monitor, router, power_supply, cable, game_console, smartwatch, battery | 9 | P4.3.13 audit: none cleanly ACQUIRABLE under the permissive-license gate |

**Existing data cannot exceed 8/19 populated classes.** The 11 empty classes have no promotable on-disk data, and per the P4.3.13 external-source audit cannot be sourced this wave without weakening the license gate.

---

## 12. Blockers (STEP 12)

1. **Execution blocker (active, infrastructural):** the Bash/IDE safety-classifier service is timed-out for the whole session, gating all command execution. STEPS 3/5/6/8/9 are staged but unrun. **Mitigation:** the four commands in §Execution Plan are ready to run the moment the classifier recovers, or immediately via the in-session `!` prefix.
2. **Data-ceiling blocker (structural):** existing data tops out at 8/19 classes; the marginal input is camera depth only.
3. **No override path:** headphones surplus (411), television (16), keyboard (23) are frozen-gate-rejected; promoting them is forbidden (would require flipping a disposition).

---

## 13. Next-phase recommendation (STEP 13)

1. **Finish P4.3.14 (run the four staged commands)** — cost is one CPU training run *only if* camera PROMOTED > 0; otherwise it self-terminates as `DATASET_UNCHANGED`. This definitively answers "how far can existing data take us" with a number on camera recall.
2. **If camera depth helps but coverage still 8/19 (expected):** the existing-data ceiling is reached. The next real progress is **acquisition**, in the P4.3.13-audited order: **router** then **battery** (semantically exact; need a NEW licensed LVIS-annotations + COCO per-image CC-BY-2.0/SA importer keeping only COCO license ids 4 & 5), then self-collection for desktop/server/crt_monitor/power_supply/game_console/smartwatch (+ cable general).
3. **Do NOT** re-attempt tv/keyboard promotion or headphones-cap experiments — proven 0-yield (P4.3.12).
4. Hold `is_dataset_v1=false`, `is_released=false` until a human visual-QA pass (currently `NOT_PERFORMED`).

---

## Execution Plan — the four staged commands (run in order, from repo root)

```bash
# STEP 1 — inventory (read-only; writes reports/inventory.json)
intelligence/device_ai/.venv/Scripts/python.exe \
  dataset_acquisition/staging/p4_3_14_existing_data_only_v1/_tooling/inventory.py

# STEP 3+5 — frozen-pipeline promotion of camera (skips the 4 link-rotted classes as NO_SOURCE)
intelligence/device_ai/.venv/Scripts/python.exe \
  dataset_acquisition/staging/p4_3_14_existing_data_only_v1/_tooling/promote_existing.py --all

# STEP 6 — assemble 665 + camera promotions (read-only source, copy-only dest; default: NO cap)
intelligence/device_ai/.venv/Scripts/python.exe \
  dataset_acquisition/training/p4_3_14_existing_data_only_v1/_tooling/build_p4314_dataset.py

# STEP 8+9 — train + eval, ONLY if the assembled dataset changed vs the 665 (else DATASET_UNCHANGED)
dataset_acquisition/.venv/Scripts/python.exe \
  dataset_acquisition/training/p4_3_14_existing_data_only_v1/_tooling/train_yolo11_p4314.py --resume
```

*(In this session, prefix any of the above with `!` to run it in-session, e.g. `! intelligence/device_ai/.venv/Scripts/python.exe …`.)*

**Staged artifacts (all written, none run):**
- `staging/p4_3_14_existing_data_only_v1/_tooling/inventory.py`
- `staging/p4_3_14_existing_data_only_v1/_tooling/promote_existing.py`
- `training/p4_3_14_existing_data_only_v1/_tooling/build_p4314_dataset.py`
- `training/p4_3_14_existing_data_only_v1/_tooling/train_yolo11_p4314.py`
