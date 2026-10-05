# EcoTrace India -- Dataset Acquisition Final Report (P4.3.10)

**Batch:** `dataset_acquisition/staging/p4_3_10_openimages_multiclass_v1`
**Source:** Open Images V7 (Google) -- CC-BY images only, byte-verified against `OriginalMD5` from the Flickr `OriginalURL`.
**Pipeline:** the frozen, audited `device_ai.acquisition` pipeline (preflight -> license/bbox/semantic gates -> ingest -> provenance -> dedup -> Gate A/B -> automated QA -> 70/20/10 seed-42 split -> promotion).

> **Honesty contract.** Every count below is measured by a frozen component or is reported as `-` / `BLOCKED` / `NOT_BUILT`. QA is AUTOMATED machine adjudication: `visual_verification` and `human_qa` are `NOT_PERFORMED` for every image. Nothing was committed and **Dataset v1 was NOT released** (`is_dataset_v1` / `is_released` remain FALSE).

---

## 1. Per-class results (Open Images V7 -> EcoTrace)

Availability legend: **Selected** = deterministic seed-42 selection from the clean CC-BY unrotated pool; **Verified** = downloaded bytes whose `base64(md5)` matched OI `OriginalMD5` (this equals *downloaded-and-kept* -- only matching bytes are written); **Unavail** = selected but not verifiable (link rot / forbidden / md5 mismatch); **Retained** = images the frozen ingest staged; **Promoted** = AUTO_ACCEPT and promotion-gate VERIFIED.

| Class | id | OI label | Status | Selected | Verified | Unavail | Retained | Boxes | AUTO_ACCEPT | UNVERIFIED | AUTO_REJECT | Promoted | Dedup | Split (tr/va/te) | Provenance | MB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| smartphone | 1 | Mobile phone | WAVE_VALIDATED | 200 | 66 | 134 | 66 | 84 | 35 | 28 | 3 | 35 | 3 | 24/7/4 | 66/66 | 102.4 |
| tablet | 2 | Tablet computer | WAVE_VALIDATED | 52 | 43 | 9 | 43 | 47 | 23 | 13 | 7 | 23 | 7 | 16/4/3 | 43/43 | 67.1 |
| monitor | 5 | Computer monitor | WAVE_VALIDATED | 200 | 137 | 63 | 137 | 181 | 55 | 28 | 54 | 55 | 53 | 38/11/6 | 137/137 | 200.1 |
| television | 7 | Television | BLOCKED_NO_ACCEPTED_IMAGES | 166 | 16 | 150 | 16 | 21 | 0 | 0 | 16 | 0 | 16 | - | 16/16 | 15.1 |
| printer | 8 | Printer | WAVE_VALIDATED | 68 | 54 | 14 | 54 | 55 | 27 | 24 | 3 | 27 | 3 | 18/5/4 | 54/54 | 65.2 |
| keyboard | 9 | Computer keyboard | BLOCKED_NO_ACCEPTED_IMAGES | 200 | 23 | 0 | 23 | 27 | 0 | 0 | 23 | 0 | 23 | - | 23/23 | 42.3 |
| mouse | 10 | Computer mouse | WAVE_VALIDATED | 97 | 78 | 19 | 78 | 88 | 26 | 42 | 10 | 26 | 10 | 18/5/3 | 78/78 | 114.9 |
| camera | 14 | Camera | WAVE_VALIDATED | 200 | 13 | 0 | 13 | 16 | 7 | 6 | 0 | 7 | 0 | 4/1/2 | 13/13 | 13.4 |
| headphones | 17 | Headphones | WAVE_INCOMPLETE | 131 | 6 | 0 | 6 | 6 | 3 | 3 | 0 | 3 | 0 | 2/0/1 | 6/6 | 13.2 |

Per-class machine reports and evidence: `staging/p4_3_10_openimages_multiclass_v1/review/<class>/` (`P4_3_10_<CLASS>_ACQUISITION_REPORT.md`, `automation/run_report.json`, `automation/promotion_evidence.json`, `automation/automated_qa.json`, `automation/split_assignment.json`, `automation/duplicate_evidence.json`, `automation/provenance_manifest.json`).

> **Per-class Markdown header note.** Each per-class `P4_3_10_<CLASS>_ACQUISITION_REPORT.md` is produced by the frozen P4.3.7 report renderer reused unchanged, so its H1 reads "P4.3.7 -- Router Automation Report"; the body correctly reports the actual target class and taxonomy id. This report is the authoritative P4.3.10 artifact.

## 2. Totals

- Mapped OI classes attempted: **9** | WAVE_VALIDATED: **6** (smartphone, tablet, monitor, printer, mouse, camera)
- Selected (seed-42): **1314** | byte-verified downloaded: **436** | unavailable (link rot / mismatch): **389**
- **Unique** source images across all archives: **389** (raw verified sum 436; cross-class overlap 47 -- an OI image carrying boxes for two classes)
- Images retained (frozen ingest): **436** | total staged boxes: **525**
- Automated QA: **176** AUTO_ACCEPT | **144** UNVERIFIED | **116** AUTO_REJECT (`visual_verification` / `human_qa` = NOT_PERFORMED)
- Dedup exclusions (batch images flagged vs protected/sibling/self): **115**
- Images **PROMOTED** (AUTO_ACCEPT and promotion-gate VERIFIED): **176** (cross-class unique by construction)
- Provenance complete: **436/436** | split totals train/val/test: **120/33/23**

## 3. Failures / blockers

- `television`: no staged image reached AUTO_ACCEPT; uncertainty is never converted to acceptance
- `keyboard`: no staged image reached AUTO_ACCEPT; uncertainty is never converted to acceptance
- `headphones`: split: target class absent from: val. Reported exactly as measured - the seed and ratios were not changed and no minimum image count was invented. More real images are required.

## 4. Storage on disk & projection

- P4.3.10 staged (promoted/retained) images: **633.7 MB** (0.619 GB)
- P4.3.10 byte-verified archive working pool: **633.7 MB**
- P4.3.10 batch tree total on disk: **1273.2 MB**
- Protected prior batches (read-only, never modified): **920.4 MB** (P4.3.5 candidate 62.4 MB; P4.3.6 expansion 90.0 MB; P4.3.9 laptop 768.0 MB)
- Grand total (this batch + protected): **2193.6 MB** (2.142 GB) -- far below the **50 GB** ceiling (target ~45 GB).
- Average staged image size: **1488 KB**.
- **ESTIMATE (not a commitment).** Filling all 9 mapped classes to ~200 retained each (~1800 imgs) ~= **2616.1 MB**. A hypothetical full 19-class set at ~200 each (~3800 imgs) ~= **5523.0 MB** (5.39 GB) -- still well under ceiling. Blocked classes have no verified source, so the 19-class figure is a size illustration, not a plan.

## 5. 19-class taxonomy coverage

| id | Class | Coverage | Note |
| --- | --- | --- | --- |
| 0 | laptop | ACQUIRED (P4.3.9) | acquired in the separate P4.3.9 Open Images V7 laptop batch (staging/p4_3_9_openimages_laptop_v1); not re-run by this batch |
| 1 | smartphone | WAVE_VALIDATED | 35 promoted / 66 retained; split VERIFIED |
| 2 | tablet | WAVE_VALIDATED | 23 promoted / 43 retained; split VERIFIED |
| 3 | desktop | BLOCKED_NO_SOURCE | no Open Images V7 boxable class denotes a desktop computer distinct from its monitor/keyboard/mouse components; no verified 1:1 public bbox source |
| 4 | server | BLOCKED_NO_SOURCE | no Open Images V7 boxable class denotes a server; no verified public bbox source in scope |
| 5 | monitor | WAVE_VALIDATED | 55 promoted / 137 retained; split VERIFIED |
| 6 | crt_monitor | BLOCKED_NO_SOURCE | Open Images V7 'Computer monitor' does not distinguish CRT from flat-panel; mapping it to crt_monitor would fabricate a distinction the source label does not make |
| 7 | television | BLOCKED_NO_ACCEPTED_IMAGES | 0 promoted / 16 retained; split - |
| 8 | printer | WAVE_VALIDATED | 27 promoted / 54 retained; split VERIFIED |
| 9 | keyboard | BLOCKED_NO_ACCEPTED_IMAGES | 0 promoted / 23 retained; split - |
| 10 | mouse | WAVE_VALIDATED | 26 promoted / 78 retained; split VERIFIED |
| 11 | router | BLOCKED_NO_SOURCE | out of Open Images scope; handled by the separate P4.3.7 router pipeline, which reports BLOCKED_NO_SOURCE (no verified public router bbox source) |
| 12 | power_supply | BLOCKED_NO_SOURCE | no Open Images V7 boxable class denotes a power supply unit; no verified public bbox source in scope |
| 13 | cable | BLOCKED_NO_SOURCE | no Open Images V7 boxable class denotes an e-waste cable 1:1; no verified public bbox source in scope |
| 14 | camera | WAVE_VALIDATED | 7 promoted / 13 retained; split VERIFIED |
| 15 | game_console | BLOCKED_NO_SOURCE | no Open Images V7 boxable class denotes a game console 1:1; no verified public bbox source in scope |
| 16 | smartwatch | BLOCKED_NO_SOURCE | Open Images V7 'Watch' denotes analog/wrist watches, not smartwatches; mapping would be an unsupported inference |
| 17 | headphones | WAVE_INCOMPLETE | 3 promoted / 6 retained; split CLASS_ABSENT_FROM_SPLIT |
| 18 | battery | BLOCKED_NO_SOURCE | no Open Images V7 boxable class denotes a battery 1:1; no verified public bbox source in scope |

- Classes with acquired public data: **7 / 19** (laptop via P4.3.9 + this batch's WAVE_VALIDATED classes).
- Classes BLOCKED_NO_SOURCE: **9 / 19** (no verified 1:1 public Open Images bbox source in scope; reasons above).

## 6. Protected data

- All protected trees byte-identical before/after every run: **True** (P4.3.5 candidate, P4.3.6 expansion, and the P4.3.9 laptop batch are fingerprinted by the frozen preflight/protected-state stages; each already-acquired sibling is also protected when the next class runs). Sizes are itemised in section 4.

## 7. YOLO11 readiness assessment

- Every staged image is a verbatim source byte copy (staged SHA-256 == source `OriginalMD5`) with a YOLO label at the frozen taxonomy id and full provenance; the promoted set is 70/20/10 seed-42 split.
- **Assessment: sufficient to BEGIN a preliminary / proof-of-concept multi-class YOLO11 detector** over the 6 WAVE_VALIDATED class(es) here plus the P4.3.9 laptop wave. It is **NOT** sufficient for a production 19-class model: only 7/19 classes have public data and per-class depth is modest.
- Depth: classes with >=100 promoted: none; thin classes (<50 promoted, grow before relying on them): `camera` (7), `tablet` (23), `mouse` (26), `printer` (27), `smartphone` (35).
- This is a per-class **wave validation**, not full-dataset release readiness: a release build must merge these promoted waves with the protected P4.3.5/P4.3.6 batches and re-run the whole-dataset readiness gate.
- **Not released, not committed.** Human sign-off is still required before any `is_dataset_v1` / `is_released` transition.

## 8. Next recommended acquisition

1. **Grow thin validated classes toward the ~200 target** by adding the Open Images V7 *train*-split bbox metadata (this batch used only val+test, which caps the pool): lowest promoted first -> `camera` (7), `tablet` (23), `mouse` (26), `printer` (27), `smartphone` (35).
2. **Do NOT attempt the 9 BLOCKED_NO_SOURCE classes** (`desktop`, `server`, `crt_monitor`, `router`, `power_supply`, `cable`, `game_console`, `smartwatch`, `battery`) until a verified 1:1 public bbox source exists for each; no source is invented and none is currently verified in scope.
3. Every expansion must re-run this same frozen pipeline (license + semantic + geometry + dedup + QA + split + promotion); no gate is weakened and no human-review status is fabricated.
