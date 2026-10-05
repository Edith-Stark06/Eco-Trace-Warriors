# Phase 5.5 — Controlled Conservative Training Report

## 1. Objective

Run exactly one controlled YOLO11n training experiment using the Phase 5.4 "Conservative" scale-filtered candidate, to test whether removing the most extreme small-object examples from the Phase 5.2 COCO expansion reduces the regression observed in P5.2, under an otherwise byte-identical recipe to the Phase 4.4/v8 controlled baseline.

## 2. Exact Hypothesis

"Consistent with the scale-shift hypothesis" (H1 from Phase 5.3): if object-scale mismatch was a material contributor to P5.2's regression, training on a scale-filtered subset of the same expansion pool should recover some or all of the lost performance relative to V8, particularly for laptop, smartphone, and mouse. This experiment isolates only the scale-filtering intervention — it does **not** control for the visual/context domain shift (Phase 5.3 Analysis 3/6/7) also implicated as a contributing factor, which remains present in whichever added images survive the filter.

## 3. Pre-flight Gates

All 19 gates passed before training was authorized to proceed:

| # | Gate | Result |
|---|---|---|
| 1 | Git branch = develop | PASS |
| 2 | Git working tree clean | PASS |
| 3 | E:\Ecotrace Dataset exists | PASS |
| 4 | Production checkpoint hash = `c40a4afc...` | PASS |
| 5 | Phase 5.4 Conservative candidate exists | PASS |
| 6/7 | Train images/labels = 863/863 | PASS |
| 8 | Val = 164 | PASS |
| 9 | Test = 92 | PASS |
| 10 | Taxonomy exact 8-class match | PASS |
| 11 | No unauthorized classes | PASS (0) |
| 12 | Zero corrupt images | PASS (0, per Phase 5.4 integrity report) |
| 13 | Zero invalid annotations | PASS (0) |
| 14 | No train/val/test leakage | PASS (0/0/0) |
| 15 | Val/test byte-identical to frozen P4.4.2 copies | PASS (both True) |
| 16 | Candidate 1 provenance intact | PASS (336/336 manifest records, 100 selected: 75/17/8) |
| 17 | Candidate not being written to | PASS (read-only access; candidate folder re-verified untouched after a metadata-file mistake was caught and reverted — see Section 4) |
| 18 | Kaggle credentials exist (not printed) | PASS (`kaggle config view` showed username only) |
| 19 | Kaggle GPU environment available | PASS (existing T4 notebook reachable, status COMPLETE from prior run) |

## 4. Dataset Identity

- Candidate: Phase 5.4 "Conservative" (`D:\Ecotrace-Audit\phase5_4_filtered_candidates\candidate_conservative\dataset`)
- Uploaded as a **new private** Kaggle dataset: `edithstark/ecotrace-p442-conservative-v1` (not modifying the authoritative `edithstark/ecotrace-p442-yolo11n-gpu-v1`)
- **Note**: my first attempt to prepare the upload wrote a `dataset-metadata.json` directly into the candidate's own dataset folder, which would have altered that Phase 5.4 artifact. This was caught before uploading, the file was removed, and the dataset was instead staged in a separate copy (`D:\Ecotrace-Audit\phase5_5_kaggle_upload\dataset\`), leaving the Phase 5.4 candidate folder untouched (re-verified: 863/164/92 counts unchanged after the fix).

## 5. Dataset Counts

Train=863 (763 original + 100 added: 75 laptop, 17 smartphone, 8 mouse), Val=164, Test=92 — confirmed both before upload and again in-log by Ultralytics' own dataset resolver during the run: `Split counts match Phase 2 exactly: {'train': 863, 'val': 164, 'test': 92}`.

## 6. Dataset Integrity

Inherited from Phase 5.4's independently-computed integrity report for this exact candidate: 0 corrupt images, 0 invalid labels, 0 unauthorized classes, 0 leakage across all split pairs, val/test byte-identical to source. Not re-run from scratch this phase (the candidate was not modified since), but re-confirmed present/unchanged (863/164/92 counts) immediately before and after the Kaggle run.

## 7. Kaggle Environment

- Kernel: `edithstark/notebook0bbb1ac713`, **version 10**
- GPU: 2× Tesla T4 (training used `device=0`, single GPU only)
- Python 3.12.13, PyTorch 2.10.0+cu128, CUDA 12.8
- Ultralytics **8.4.141** — explicitly pinned and hard-verified in-log (`ultralytics version pin CONFIRMED: 8.4.141`), matching V8 exactly

## 8. Exact Training Recipe

Confirmed via the Ultralytics `engine/trainer:` args dump, byte-identical to V8/v8 except the `data=` path (which necessarily differs — it points at this dataset's own runtime YAML):

`model=yolo11n.pt, epochs=50, patience=20, batch=8, imgsz=512, device=0, workers=2, cache=False, seed=42, deterministic=True, amp=False` — optimizer, augmentation, lr0/lrf, and every other Ultralytics default were left untouched.

## 9. Training Result

- Epochs completed: 50/50 (no early stop)
- Best epoch: 34 (of 50), val mAP50-95 = 0.4118
- Training duration: 1095.9s (~18.3 min)
- Kernel status: COMPLETE

## 10. Validation Metrics

precision 0.5593, recall 0.5606, mAP50 0.5794, mAP50-95 0.4100

## 11. Test Metrics

precision 0.4670, recall 0.6930, mAP50 0.5439, mAP50-95 0.4011

## 12. Per-Class Metrics

| Class | AP50 | AP50-95 | Precision | Recall |
|---|---:|---:|---:|---:|
| laptop | 0.4060 | 0.2964 | 0.346 | 0.571 |
| smartphone | 0.4698 | 0.4205 | 0.242 | 1.000 |
| tablet | 0.3895 | 0.3805 | 0.372 | 0.667 |
| monitor | 0.7478 | 0.5976 | 0.938 | 0.600 |
| printer | 0.6450 | 0.3660 | 0.551 | 0.628 |
| mouse | 0.3050 | 0.2940 | 0.246 | 0.667 |
| camera | 0.6732 | 0.4210 | 0.415 | 0.681 |
| headphones | 0.7145 | 0.4325 | 0.624 | 0.729 |

## 13. V8 Comparison

| Metric | V8 | P5.5 Conservative | Delta |
|---|---:|---:|---:|
| Precision | 0.5569 | 0.4670 | −0.0899 |
| Recall | 0.5857 | 0.6930 | +0.1073 |
| mAP50 | 0.6364 | 0.5439 | **−0.0925** |
| mAP50-95 | 0.4903 | 0.4011 | **−0.0893** |
| Laptop AP50 | 0.4335 | 0.4060 | −0.0275 |
| Smartphone AP50 | 0.4258 | 0.4698 | **+0.0440** |
| Mouse AP50 | 0.4411 | 0.3050 | −0.1361 |
| Tablet AP50 | 0.7310 | 0.3895 | **−0.3415** |
| Monitor AP50 | 0.8240 | 0.7478 | −0.0762 |
| Printer AP50 | 0.7109 | 0.6450 | −0.0659 |
| Camera AP50 | 0.8421 | 0.6732 | −0.1689 |
| Headphones AP50 | 0.6827 | 0.7145 | +0.0318 |

**Important, unexpected finding**: classes that received *zero* added data (tablet, monitor, printer, camera) all regressed relative to V8 — most severely tablet (−0.34). Only two of the three target classes moved in the hoped-for direction (smartphone improved past V8; laptop stayed nearly flat, a large recovery from P5.2's collapse); mouse regressed substantially versus V8, despite improving versus P5.2.

## 14. P5.2 Comparison

| Metric | P5.2 (full 336) | P5.5 Conservative (100) | 
|---|---:|---:|
| mAP50 | 0.5015 | 0.5439 (+0.0424, partial recovery) |
| mAP50-95 | 0.3707 | 0.4011 (+0.0304) |
| Laptop AP50 | 0.2017 | 0.4060 (+0.2043, large recovery) |
| Smartphone AP50 | 0.3256 | 0.4698 (+0.1442, recovers past V8) |
| Mouse AP50 | 0.2325 | 0.3050 (+0.0725, partial recovery, still below V8) |

Conservative is unambiguously better than P5.2 on every headline metric and all three target classes — but "better than the rejected P5.2 experiment" is not the bar; the bar is V8 (Section 13), against which the result is a net regression.

## 15. Confusion-Pair Analysis (frozen test set, re-extracted per-instance, not inferred)

Directly requested pairs:

| Pair | P5.2 count | P5.5 count | Detail (P5.5) |
|---|---:|---:|---|
| laptop → smartphone | 4 (all wrong_class) | 3 (2 wrong_class + 1 localization_and_class) | conf 0.73–0.93, IoU 0.32–0.95 |
| tablet → smartphone | 1 | **3** (all 3 tablet test instances) | conf 0.76–0.97, IoU 0.95–0.98 |
| printer → smartphone | 1 | 1 (persists) | conf 0.90 (up from 0.56), IoU 0.97 |
| smartphone → headphones | 1 | **0** (smartphone's error is now →camera) | conf 0.26, IoU 0.85 |
| mouse → headphones | 1 | **0** (mouse's error is now →smartphone) | conf 0.84 (up from 0.35), IoU 0.77 |

**The single most important diagnostic finding**: laptop→smartphone confusion did *not* meaningfully decrease (4→3, still present at high confidence/IoU), and **tablet→smartphone confusion got worse** — all three tablet test instances are now misclassified as smartphone (vs. 1 of 3 in P5.2, where the other two were called laptop instead). This fully explains tablet's −0.34 AP50 drop in Section 13. "Smartphone" remains a strong attractor label for other rectangular-screened-device classes in this checkpoint — scale-filtering the smartphone training examples did not resolve this, and by one reading made it more concentrated (mouse's own confusion shifted from headphones to smartphone at much higher confidence: 0.35→0.84).

## 16. Checkpoint Hashes

- best.pt: `1cf5fffd395d58238e5ce3b5c2f9f911963e93f2cb69df8bd49a90dc26012614`
- last.pt: `f210ac28feeacbfd234e865f24a3242fbc2b34382a28eafc57dcd5c0e75e4469`

Both remain purely experimental, on Kaggle and in the local scratchpad only — never copied toward any production path.

## 17. Interpretation

The result is **consistent with** object-scale shift being a real, partial contributor to P5.2's regression — laptop and smartphone both improved substantially relative to P5.2, and smartphone even exceeded V8. But scale-filtering alone did not recover overall performance to V8's level, mouse remains below V8, and — most tellingly — the confusion-pair evidence shows the "smartphone attractor" problem (Phase 5.4 Section 10/12) persisted and, for tablet, intensified. This points at the uncontrolled visual/context domain shift (Phase 5.3's H2/H3, edge density +76%, brightness −14% vs. original) as a still-active factor that Conservative's scale-only filter does not address. **This experiment does not establish causality beyond itself** — it is one controlled run, one seed, one filtering strategy.

## 18. Decision Classification

**B. MIXED.**

Two of three target classes moved favorably relative to P5.2 (and smartphone favorably relative to V8 too), but mouse remains below V8, overall mAP50/mAP50-95 are materially below V8, and a class untouched by the expansion (tablet) regressed sharply due to a confusion effect that got worse, not better. Per the decision principles given, this cannot be called CLEAR IMPROVEMENT (a materially regressed non-target class rules that out) and is better characterized than NO RECOVERY or REGRESSION (real, substantial improvement over P5.2 did occur, and smartphone genuinely improved past V8).

## 19. Causality Limitations

This experiment isolates only the scale-filtering intervention. It does not control for: visual/context domain shift (brightness, edge density, framing — still present in whichever added images survive scale filtering), the specific 50/50/50 vs. non-uniform class composition question, or run-to-run seed variance (only one seed was tested here, unlike the AMP/version isolation experiments in Phase 4.3/4.4 which specifically tested reproducibility). The correct statement is: **"Conservative scale-filtering is consistent with partially explaining the smartphone/laptop-specific portion of the P5.2 regression, but does not fully explain it, and does not by itself resolve the broader confusion pattern."** Not: "scale shift caused the regression."

## 20. Safety Confirmation

- Production checkpoint unchanged: `c40a4afccacbbde89fce2a3a5fb73467e8614dc09365ea4678b24f7ad9218e92` (re-verified before and after)
- `E:\Ecotrace Dataset` unchanged (no modified files)
- Phase 4.2 staging unchanged (703 files, same as before)
- Phase 5.1 dataset unchanged (1099/164/92)
- Phase 5.2 checkpoint unchanged: `34302d2ca1e50888c877b055f3e0b6b9a4cf98ed4c520ae9f13fbef2b336784d`
- Phase 5.4 Conservative candidate unchanged (863/164/92, re-verified after the metadata-file mistake was caught and corrected)
- No production Device AI files changed
- No unauthorized taxonomy changes
- Experimental weights (P5.5 best.pt/last.pt) remain disposable, on Kaggle/local scratchpad only — never promoted, never copied toward any production path

## 21. Git State

- Branch: `develop`
- Before this phase: clean, HEAD `1cd3d0c`
- This phase's only repo change: `intelligence/device_ai/training/kaggle/p442_gpu_v1/train_p442_gpu.py` (refactored `EXPANDED_DATASET_MODE` into a general `DATASET_VARIANT` selector adding the `"conservative"` option — flags are back at resting state: `DRY_RUN=True`, `AMP_ISOLATION_MODE=False`, `PINNED_ULTRALYTICS_VERSION=None`, `DATASET_VARIANT="original"`) plus this report file.
- No datasets, weights, or credentials staged or committed.
- Not yet committed at the time of writing — commit/push are handled after this report is delivered, per instructions not to push without separate confirmation.

## 22. Recommendation for Next Phase

**INVESTIGATE.**

The Conservative filter (H1: scale) delivered a real but incomplete recovery, and the confusion-pair evidence points squarely at an unresolved class-conditional confusion problem centered on "smartphone" as an attractor label — a problem that scale-filtering did not fix and, for tablet, made more concentrated. Before running another training experiment with a different dataset composition, it would be more informative to specifically investigate *why* the model's smartphone decision boundary is so easily triggered by other rectangular-screened devices (laptop/tablet/printer/monitor) — e.g. by inspecting the actual confused images visually, checking whether this pattern also exists in the original V8/production checkpoints on a broader sample, or examining feature-level similarity between these classes — rather than immediately proposing a new filtered/rebalanced dataset variant on the same untested assumption. This is a recommendation only; no further training or investigation was started in this phase.
