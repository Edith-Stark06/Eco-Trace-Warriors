# EcoTrace India — P4.3.12 Balanced-Coverage Expansion — Consolidated Report

**Date:** 2026-08-24
**Unit:** `dataset_acquisition/training/p4_3_balanced_coverage_v1/`
**Status flags (held, per constraints):** `is_dataset_v1 = false`, `is_released = false`, no git commit/push.
**Baseline of record for comparison:** the 665-image model (`p4_3_preliminary_baseline_v1/metrics_after.json`).

---

## 0. Executive summary & decision

**Decision: D (with an evidence-based B finding on the balance axis).**

Two independent findings, both established from on-disk evidence, not estimated:

1. **Coverage cannot be expanded without new legitimate downloads (DECISION D).** Of the 11 empty classes, **9 are source-blocked** (no boxable Open Images label clears the unchanged token gate) and **television + keyboard are dedup-blocked** — the frozen duplicate detector rejects **100 %** of both acquired batches because every candidate is an *exact* duplicate of an image already in a protected tree. Decisively, **13 of the 23 keyboard candidates are already promoted in the 665 set under _other_ classes** (5 as `monitor`, 8 as `laptop`). Promoting them would require overriding the frozen dedup gate and would inject the same pixels under contradictory labels — forbidden.

2. **Rebalancing the existing pool does not beat the 665 baseline on the held-out test set (DECISION B territory, negative result).** Two deterministic de-biasing configurations were built and trained (headphones train capped 303→82 and 303→41; val/test held byte-identical). Neither beats the baseline on **test mAP50** (0.630 → 0.512 → 0.472). The one consistent signal is that the previously-suppressed **mouse** class improves under balancing on both splits; but per-class evaluation is dominated by small-sample noise (camera swings 0.021↔0.995 on 1–2 images). The binding constraint is **total data volume and blocked sources**, not the headphones ratio alone.

**Recommendation:** retain the **665 model as the current best preliminary checkpoint**. Do **not** adopt the aggressive equal-cap (regresses test mAP). Do **not** pursue further single-class depth (P4.3.11 lesson) *or* further capping (this experiment) — both merely rearrange a too-small pool. The real unblock is **controlled, licensed NEW acquisition** (see §10), which STEP 3 explicitly deferred and which needs explicit go-ahead + network.

---

## 1. STEP 1 — Audit of the current promoted dataset (665 images, 8 / 19 classes)

Source: `p4_3_preliminary_baseline_v1/dataset/manifest.json` (per-image) and `metrics_after.json` (665-model test metrics). Counts are exact.

| id | class | promoted | train | val | test | test AP50 | test AP50-95 |
|---:|-------|---------:|------:|----:|-----:|----------:|-------------:|
| 0 | laptop | 59 | 41 | 11 | 7 | 0.456 | 0.376 |
| 1 | smartphone | 35 | 24 | 7 | 4 | 0.378 | 0.352 |
| 2 | tablet | 23 | 16 | 4 | 3 | 0.830 | 0.803 |
| 3 | desktop | 0 | 0 | 0 | 0 | — | — |
| 4 | server | 0 | 0 | 0 | 0 | — | — |
| 5 | monitor | 55 | 38 | 11 | 6 | 0.816 | 0.660 |
| 6 | crt_monitor | 0 | 0 | 0 | 0 | — | — |
| 7 | television | 0 | 0 | 0 | 0 | — | — |
| 8 | printer | 27 | 18 | 5 | 4 | 0.856 | 0.467 |
| 9 | keyboard | 0 | 0 | 0 | 0 | — | — |
| 10 | mouse | 26 | 18 | 5 | 3 | 0.395 | 0.389 |
| 11 | router | 0 | 0 | 0 | 0 | — | — |
| 12 | power_supply | 0 | 0 | 0 | 0 | — | — |
| 13 | cable | 0 | 0 | 0 | 0 | — | — |
| 14 | camera | 7 | 4 | 1 | 2 | 0.590 | 0.469 |
| 15 | game_console | 0 | 0 | 0 | 0 | — | — |
| 16 | smartwatch | 0 | 0 | 0 | 0 | — | — |
| 17 | headphones | 433 | 303 | 86 | 44 | 0.719 | 0.456 |
| 18 | battery | 0 | 0 | 0 | 0 | — | — |
| | **TOTAL** | **665** | **462** | **130** | **73** | test mAP50 **0.630** | mAP50-95 **0.497** |

**Imbalance diagnosis (confirms the user's finding):** headphones = **303 / 462 = 65.6 %** of training. Five populated classes have ≤ 24 train images; camera has 4.

---

## 2. STEP 2 — Coverage blockers for the 11 empty classes (verified against evidence)

### 2a. Nine classes are source-blocked (no safe boxable Open Images label)
`desktop, server, crt_monitor, router, power_supply, cable, game_console, smartwatch, battery` — none has a boxable OI label that clears the **unchanged** frozen token gate (`device_ai.acquisition.semantics`). This matches the P4.3.1 mapping and the P4.3.7 source research: they are missing *by design of the source policy*, not oversight. Acquiring them means a *different licensed source* (self-collection or a verified external set), which is out of scope for a no-download controlled run.

### 2b. Television + keyboard are dedup-blocked (the decisive new finding)
Both classes **do** have safe boxable OI labels (`Television /m/07c52`, `Computer keyboard /m/01m2v`) and P4.3.10 acquired images for them with `cc-by` provenance. However, the **frozen duplicate detector** (evidence in `staging/p4_3_10_openimages_multiclass_v1/review/{television,keyboard}/automation/duplicate_evidence.json`) flags **the entire batch**:

- **television: 16 / 16** flagged as `batch_duplicates`.
- **keyboard: 23 / 23** flagged.

Filtering the pair list to batch-involving pairs shows every candidate is an **exact (distance-0) duplicate** of an image already present in a protected tree. Two kinds of match:

1. **Cross-class contamination** — the identical Open Images ImageID was already acquired under **monitor**: e.g. `monitor_00010_1296dd4bddd64817` ≡ `television_00000_1296dd4bddd64817`; `monitor_00017_1f5cf6e96f0e0690` ≡ `keyboard_00002_1f5cf6e96f0e0690` (14 such tv, 8 such kb).
2. **Same-class re-acquisition** — other tv/kb ImageIDs already sit in `_qa_kept/…` and `openimages_{tv,kb}_v1` protected trees.

**Killer check against the promoted set:** intersecting the batch ImageIDs with the 665 manifest's `imageid` field:

- **keyboard: 13 of 23 candidate ImageIDs are already promoted** in the 665 set — **5 as `monitor [train]`, 8 as `laptop [train/val]`** (e.g. `16bb316c7c76b5a5` is already trained as *laptop*). Promoting the keyboard batch would place identical pixels under two labels and risk train/val leakage.
- television: 0 of 16 are in the 665 set, but all 16 still duplicate protected images, so promotion still requires overriding the 16/16 frozen-dedup rejection.

**Why an earlier "8 tv / 13 kb AUTO_ACCEPT" reading was wrong:** running `run_automated_qa` **without** feeding the frozen dedup output into `duplicate_paths` skips the duplicate check. Fed honestly, all candidates carry the `flagged by the frozen duplicate detector` reason → `AUTO_REJECT` → **0 promotable**. The frozen gate is correct; overriding it is forbidden ("do not weaken gates", "no cross-sibling duplicate contamination", "do not modify frozen dedup behavior").

**Conclusion:** a **no-new-download expansion can add zero classes.** Coverage stays **8 / 19**.

---

## 3. STEP 3 — No download; cap derived from populated classes
No images were downloaded. Per the instruction to use populated classes to size a training cap (and *not* a "200/class" target), the training caps were derived directly from the audit: the largest **naturally-collected** class train count is **laptop = 41**, and the second-largest is monitor = 38. These define the two de-biasing points below.

---

## 4. STEP 4 — Balanced De-biasing Policy v1 (deterministic, documented before acquisition)

- **Rule:** no class may contribute more than `CAP_TRAIN` **training** images. Only headphones (303) ever exceeds the caps considered.
- **Two points evaluated:** `CAP_TRAIN = 82` (≈ 2× second-place; moderate de-bias) and `CAP_TRAIN = 41` (= largest natural class; parity de-bias).
- **Determinism:** seed = 42; per over-cap class, filenames are sorted and a single `random.Random(42)` draws the retained subset. Identical output on every run.
- **No leakage:** VAL and TEST are copied **byte-identical** to the 665 baseline (verified with `diff -r`), so the comparison isolates a single variable — training composition. Removing train images cannot introduce leakage; the frozen splitter already made splits disjoint.
- **No gate touched, nothing fabricated:** the balanced sets are a **recomposition of already-promoted, already-QA'd, already-split images** from the 665 set. No QA / semantic / dedup / promotion / provenance code is invoked or altered.

---

## 5. STEP 5 — Prioritisation
The only classes acquirable without a new source were television and keyboard (they have OI labels + existing cc-by images). They were prioritised first and then **eliminated by the frozen dedup** (§2b). The remaining 9 require a different licensed source → deferred to §10. No further class was reachable in a no-download run.

---

## 6. STEP 6 — "Acquisition": none new; controlled recomposition only
No new images entered the pipeline. In line with "acquire only the required depth / reuse already verified images", the balanced datasets reuse the exact promoted 665 images, selected deterministically. Byte integrity is inherited from the 665 set (each file `shutil.copy2`-copied; the 665 manifest already records `sha256` per image and `sha256_matches_evidence`). Protected trees were read-only throughout.

---

## 7. STEP 7 — Rebuilt datasets

| dataset | train | val | test | headphones train | headphones train share |
|---------|------:|----:|-----:|-----------------:|-----------------------:|
| 665 baseline | 462 | 130 | 73 | 303 | 65.6 % |
| `dataset_cap82` | 241 | 130 | 73 | 82 | 34.0 % |
| `dataset` (cap41) | 200 | 130 | 73 | 41 | 20.5 % |

- Per-class train after cap (both sets): all non-headphones classes **unchanged** (laptop 41, monitor 38, smartphone 24, mouse 18, printer 18, tablet 16, camera 4); only headphones is subsampled.
- Dropped headphones train ImageIDs are recorded in each `manifest.json` (`dropped_train_imageids`): 221 (cap82), 262 (cap41).
- Duplicate counts / QA dispositions: inherited from the 665 promoted set (all AUTO_ACCEPT / PROMOTED); no new QA run was needed because no new images were introduced. Provenance completeness is 100 % (carried from the promoted manifest).
- Zeros: 11 classes remain at 0 (unchanged; see §2).

---

## 8. STEP 8 — Training (identical config)
`yolo11n.pt`, `imgsz=512`, `batch=8`, `seed=42`, `device=cpu`, `epochs=50`, `patience=20` — the same methodology as the 665 "after" model. Both runs completed all 50 epochs on CPU.
- `runs/p43_balanced_cap82_yolo11n/` → `metrics_cap82.json`
- `runs/p43_balanced_yolo11n/` → `metrics.json` (copied to `metrics_cap41.json`)

---

## 9. STEP 9 — Evaluation: 665 baseline vs cap82 vs cap41 (same held-out sets)

### TEST (73 images)
| metric | base665 (462) | cap82 (241) | cap41 (200) |
|--------|-----:|-----:|-----:|
| **mAP50** | **0.630** | 0.512 | 0.472 |
| **mAP50-95** | **0.497** | 0.388 | 0.362 |
| precision | 0.713 | 0.351 | 0.625 |
| recall | 0.500 | 0.687 | 0.419 |

**Per-class AP50 (TEST):**
| class | base665 | cap82 | cap41 | note |
|-------|-----:|-----:|-----:|------|
| mouse | 0.395 | **0.451** | **0.446** | ↑ under both — the one consistent balance signal |
| headphones | 0.719 | 0.634 | 0.503 | ↓ monotonic with cap (expected, 87 % train cut at cap41) |
| monitor | 0.816 | 0.834 | 0.793 | ~flat |
| laptop | 0.456 | 0.489 | 0.400 | noisy |
| camera | 0.590 | 0.373 | 0.021 | **noise** (2 test imgs; train unchanged at 4) |
| tablet | 0.830 | 0.450 | 0.423 | **noise** (3 test imgs; opposite sign on val) |
| printer | 0.856 | 0.582 | 0.825 | **noise** (non-monotonic) |
| smartphone | 0.378 | 0.284 | 0.361 | **noise** (non-monotonic) |

### VAL (130 images)
| metric | base665 | cap82 | cap41 |
|--------|-----:|-----:|-----:|
| **mAP50** | 0.517 | **0.617** | 0.477 |
| **mAP50-95** | 0.410 | **0.514** | 0.367 |
| precision | 0.574 | 0.467 | 0.696 |
| recall | 0.460 | 0.664 | 0.406 |

On VAL, **cap82 beats the baseline** (mAP50 +0.100, mAP50-95 +0.104) with a large mouse gain (0.435→0.675) — but this is inflated by camera 0.995 on a **single** val image. The split disagreement (cap82 best on val, baseline best on test) is itself evidence that the evaluation is noise-dominated at these class sizes.

**Attention items requested:**
- **mouse regression:** partially recovered by balancing (the clearest positive signal), consistent with the headphones-dominance hypothesis — but on a 3-test/5-val-image base.
- **headphones:** gains are given back proportionally to the cut; still the strongest small-set class.
- **monitor / printer:** monitor stable; printer swings are small-sample noise.
- **new classes:** none exist to evaluate (coverage blocked).

---

## 10. STEP 10 — Decision & path forward

**Coverage axis → D.** Missing classes are source-blocked (9) or dedup-blocked (tv, kb). Honestly documented above. Alternative *legitimate* sources are required:
1. **9 source-blocked classes:** self-collection (license-clean by construction) or a verified external boxed set (Objects365/LVIS/Roboflow) — each needs per-source license + bbox + count verification before ingestion.
2. **television / keyboard:** acquire **fresh ImageIDs not already present in any protected tree** so the frozen dedup passes; the currently-staged batches are unusable (100 % duplicates).
3. **Thin populated classes** (camera 7, tablet 23, mouse 26, smartphone 35): raise them so evaluation stops being noise-dominated.

**Balance axis → B (negative).** Rebalancing was tried at two points; neither beats the 665 baseline on the decisive test set. Aggressive parity capping (cap41) over-corrects (discards real headphones signal, adds none elsewhere). Moderate capping (cap82) helps on val but not test. **The 665 model remains the best test-mAP checkpoint and is the recommended current model.**

**Do next (requires explicit go-ahead + network — deferred here):** a single *controlled* acquisition wave that (a) adds fresh, license-verified, dedup-clean images for 1–2 currently-thin classes and, if a licensed source is confirmed, 1–2 of the source-blocked classes; (b) re-runs the full frozen pipeline (QA → dedup → promotion → split); (c) retrains once and re-evaluates. This attacks the true constraint (volume + coverage) rather than reshuffling a fixed pool.

---

## Constraints honored (attestation)
- Frozen QA / semantic / dedup / promotion / provenance behavior **not modified** — `git diff` confirms this task edited **no** file under `intelligence/device_ai/acquisition/`; the pre-existing `M` set there is byte-for-byte the session-start snapshot from prior P4.3.x work and was not exercised by the balance experiment.
- Protected P4.3.5 / P4.3.6 / P4.3.9 / P4.3.10 trees **untouched** (read-only; `git status` shows no changes under them).
- No image or label fabricated; no gate weakened; no ImageID substituted; provenance preserved (carried from the promoted manifest).
- `is_dataset_v1 = false`, `is_released = false`. **No git commit or push.** HEAD unchanged at `48b4217`.

## Files created (all under `dataset_acquisition/training/p4_3_balanced_coverage_v1/`)
- `_tooling/build_balanced_dataset.py` — deterministic balanced-dataset builder (`--cap`, `--out`).
- `_tooling/train_yolo11_balanced.py` — training driver (`--data`, `--metrics` overrides).
- `_tooling/compare_balanced.py`, `_tooling/compare_three_way.py` — evaluation comparators.
- `dataset/` (cap41), `dataset_cap82/` — balanced datasets (val/test byte-identical to baseline).
- `manifest.json` in each dataset dir — policy + dropped-ImageID provenance.
- `metrics.json` / `metrics_cap41.json`, `metrics_cap82.json` — model metrics.
- `runs/…` — Ultralytics run artifacts (gitignored).
