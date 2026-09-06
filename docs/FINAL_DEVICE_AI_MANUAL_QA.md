# EcoTrace India — Final Device AI Manual QA

Permanent, auditable record of the manual Device-AI retest performed **after** the finalization pass (`0c16944`). ML experimentation is frozen; this document records observed behavior only — it does not authorize, propose, or precede any further training.

## 1. Purpose

To manually re-verify, one final time before demo/submission, that the frozen production Device AI checkpoint behaves as previously characterized — including its known, already-documented limitations — using a small set of real test images, and to record the exact results permanently for the submission record.

## 2. Test Environment

- Repository: `D:\Documents\Projects\Eco-Trace-Warriors`, branch `develop`, prior commit `0c16944`.
- Device AI service: the running Docker Compose `device-ai` container (`http://localhost:8100`), serving the frozen production checkpoint via its standard `/predict` API — no code, config, threshold, or weight changes were made before, during, or after this test pass.
- Test images: 10 files (see §4), submitted individually via the normal inference API.

## 3. Production Model Identity

Checkpoint SHA256 (unchanged before and after this test pass):
```
c40a4afccacbbde89fce2a3a5fb73467e8614dc09365ea4678b24f7ad9218e92
```

## 4. Test Image Directory

```
C:\Users\Ramana\Pictures\EcoTrace-Test\
```
Files: `laptop.jpg`, `smartphone.jpg`, `monitor.jpg`, `printer.jpg`, `camera.jpg`, `headphones.jpg`, `tablet.jpg`, `multi_object.jpg`, `invalid.txt`, `mouse.jpg`.

## 5. Complete Test 1–10 Table

| # | File | Expected | Actual | Confidence | Verdict |
|---|---|---|---|---|---|
| 1 | laptop.jpg | laptop | laptop | 0.8366 | PASS |
| 2 | smartphone.jpg | smartphone | mouse | 0.7618 | FAIL — wrong class |
| 3 | monitor.jpg | monitor | camera + laptop | 0.5862 / 0.3428 | FAIL — wrong/incomplete class |
| 4 | printer.jpg | printer | printer | 0.8631 | PASS |
| 5 | camera.jpg | camera | camera | 0.9699 | PASS |
| 6 | headphones.jpg | headphones | headphones | 0.8901 | PASS |
| 7 | tablet.jpg | tablet | laptop, then tablet (2 requests) | 0.7511 / 0.5516 | PASS WITH REPEATABILITY CONCERN |
| 8 | multi_object.jpg | multiple device objects | laptop + printer only | 0.953 / 0.348 | FAIL — incomplete multi-object detection |
| 9 | invalid.txt | clean rejection | HTTP 415 UNSUPPORTED_MEDIA_TYPE | n/a | PASS (functional/API) |
| 10 | mouse.jpg | mouse | mouse | 0.9991 | PASS |

## 6. Detailed Results

### TEST 1 — laptop.jpg
- Expected: laptop / Actual: laptop
- Confidence: 0.8366
- Detection: `class_id 0`, `class_name laptop`, bbox `[15,85,326,348]`
- Device type: Laptop
- Inference: 7438.61 ms; PowerShell wall-clock: 8195.7611 ms
- **Verdict: PASS**

### TEST 2 — smartphone.jpg
- Expected: smartphone / Actual: mouse
- Confidence: 0.7618
- Detection: `class_id 5`, `class_name mouse`, bbox `[85,27,521,463]`
- Device type: Mouse
- Inference: 402.73 ms; PowerShell wall-clock: 655.1087 ms
- **Verdict: FAIL — wrong class.** This reproduces the previously observed smartphone → mouse failure documented in prior QA/experimentation phases; not a new defect.

### TEST 3 — monitor.jpg
- Expected: monitor / Actual: camera + laptop
- Detection 1: `class_id 6`, `class_name camera`, confidence 0.5862, bbox `[22,38,214,220]`
- Detection 2: `class_id 0`, `class_name laptop`, confidence 0.3428, bbox `[8,41,215,223]`
- Device type: Camera
- Inference: 320.69 ms; PowerShell wall-clock: 544.7152 ms
- **Verdict: FAIL — wrong/incomplete class detection.** This reproduces the previously observed monitor failure; not a new defect.

### TEST 4 — printer.jpg
- Expected: printer / Actual: printer
- Confidence: 0.8631
- Detection: `class_id 4`, `class_name printer`, bbox `[26,108,491,545]`
- Inference: 625.07 ms; PowerShell wall-clock: 868.0839 ms
- **Verdict: PASS**

### TEST 5 — camera.jpg
- Expected: camera / Actual: camera
- Confidence: 0.9699
- Detection: `class_id 6`, `class_name camera`, bbox `[64,21,419,393]`
- Inference: 484.33 ms; PowerShell wall-clock: 661.3386 ms
- **Verdict: PASS**

### TEST 6 — headphones.jpg
- Expected: headphones / Actual: headphones
- Confidence: 0.8901
- Detection: `class_id 7`, `class_name headphones`, bbox `[125,2,797,777]`
- Inference: 256.16 ms; PowerShell wall-clock: 423.1158 ms
- **Verdict: PASS**

### TEST 7 — tablet.jpg (two consecutive requests against the same image)

**First request:**
- Expected: tablet / Actual: laptop
- Confidence: 0.7511
- Detection: `class_id 0`, `class_name laptop`
- Inference: 934.4 ms; PowerShell wall-clock: 1126.433 ms
- Verdict: FAIL — wrong class

**Second, immediate request (same image, no changes in between):**
- Expected: tablet / Actual: tablet
- Confidence: 0.5516
- Detection: `class_id 2`, `class_name tablet`, bbox `[110,170,1868,1224]`
- Inference: 334.42 ms; PowerShell wall-clock: 447.2592 ms
- Verdict: PASS

**Final documentation for Test 7: PASS WITH REPEATABILITY CONCERN.**

> Two consecutive requests using the same tablet image produced different top-class predictions without an intervening code, configuration, dataset, or model change: first Laptop (0.7511), then Tablet (0.5516). This is recorded as an observed inference repeatability anomaly. It is not treated as evidence of model improvement.

The first (Laptop) result is not hidden — both requests are documented above in full.

### TEST 8 — multi_object.jpg
- Expected: multiple device objects / Actual: laptop + printer only
- Detection 1: `class_id 0`, `class_name laptop`, confidence 0.953, bbox `[26,93,242,286]`
- Detection 2: `class_id 4`, `class_name printer`, confidence 0.348, bbox `[25,316,242,489]`
- Inference: 347.35 ms; PowerShell wall-clock: 539.196 ms
- **Verdict: FAIL — incomplete multi-object detection.** The source image visibly contains multiple device categories, but the detector returned only two detections.

### TEST 9 — invalid.txt
- Input: `invalid.txt`, content type `text/plain`
- Expected: clean rejection / Actual: HTTP 415
- Error: `UNSUPPORTED_MEDIA_TYPE`
- Message: "Unsupported media type. Allowed types: image/jpeg, image/png, image/webp."
- Request ID: `558e4c600564446ea57bfc6dbd3790ad`
- Latency: 217.1456 ms
- **Verdict: PASS.** This is a functional/API validation PASS, not a model-quality result.

### TEST 10 — mouse.jpg
- Expected: mouse / Actual: mouse
- Confidence: 0.9991
- Detection: `class_id 5`, `class_name mouse`, bbox `[170,282,1368,1054]`
- Inference: 233.06 ms; PowerShell wall-clock: 607.5358 ms
- **Verdict: PASS**

## 7. Tablet Repeatability Anomaly

See Test 7 (§6) in full. Recorded honestly, with both requests documented, as an observed inference repeatability anomaly on identical input under an unchanged model/config — not interpreted as improvement, drift, or evidence of anything beyond what was directly observed.

## 8. Functional/API Results

Test 9 (invalid.txt) confirms the API's upload validation correctly rejects an unsupported media type with a clean, typed error (`UNSUPPORTED_MEDIA_TYPE`, HTTP 415) rather than a crash or an ambiguous 500 — consistent with the validator behavior already documented in `FINALIZATION_AUDIT.md`.

## 9. Model-Quality Limitations (reconfirmed, not new)

This manual pass reconfirms, on real images, the model-quality limitations already established and documented across the project's prior experimentation history (Phase 4.4–5.6): confusion between visually similar device classes (smartphone misclassified as mouse; monitor misclassified as camera/laptop; tablet unstable between laptop and tablet), and incomplete detection on multi-object scenes. None of these are new findings — they are consistent with, and reproduce, previously observed failure modes. No attempt was made to explain, retrain around, or fix these in this phase.

## 10. Final Interpretation

Of 8 valid single-object tests, 5 passed cleanly (laptop, printer, camera, headphones, mouse), 2 failed with a wrong top class (smartphone, monitor), and 1 passed on a second attempt after an inconsistent first attempt (tablet). The multi-object test failed to return complete detections. The invalid-input test passed as a functional/API check. These results are consistent with the already-known, already-documented limitations of the frozen production model — they do not reveal a new defect requiring action, and no action was taken.

## 11. Scope Statement

**This is a small manual sanity suite of 10 images, not a statistical accuracy benchmark.** No aggregate accuracy, precision, recall, or mAP figure should be inferred from it, and none is presented here. It exists solely to spot-check that the frozen production service behaves consistently with its already-documented characteristics immediately before demo/submission.

## 12. No Production Changes

**No production model changes were made during this testing.** No weights, thresholds, inference code, or Device AI configuration were modified before, during, or after this test pass. The production checkpoint SHA256 was verified identical before and after (see §3 and the commit's own safety verification).

## 13. ML Remains Frozen

**ML experimentation remains frozen.** This document is a QA record only. It does not propose, authorize, or precede any further training, dataset acquisition, threshold tuning, or model change. Per explicit instruction, no retraining is suggested as a result of this phase.

## Summary

- Valid single-object tests:
  - Laptop: PASS
  - Smartphone: FAIL
  - Monitor: FAIL
  - Printer: PASS
  - Camera: PASS
  - Headphones: PASS
  - Tablet: PASS WITH REPEATABILITY CONCERN
  - Mouse: PASS
- Multi-object: FAIL — incomplete detection
- Invalid input: PASS — HTTP 415

Manual sanity-suite outcome (not an accuracy figure): 6 of 8 valid single-object tests passed (including the repeatability-flagged tablet case), 1 multi-object test failed, 1 functional/API test passed.
