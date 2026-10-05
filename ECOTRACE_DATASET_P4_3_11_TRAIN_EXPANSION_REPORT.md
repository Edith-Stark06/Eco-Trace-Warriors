# EcoTrace India -- P4.3.11 Open Images TRAIN-Split Depth Expansion Report

**Batch:** `dataset_acquisition/staging/p4_3_11_openimages_train_expansion_v1`
**Scope:** DEPTH expansion of six classes already acquired in P4.3.10 (headphones, camera, tablet, mouse, printer, smartphone), drawing additional byte-verified CC-BY images from the Open Images V7 **train** split. **This wave adds depth, NOT breadth** -- taxonomy coverage is unchanged at 10/19.
**Source:** Open Images V7 (Google) -- CC-BY images only, byte-verified against `OriginalMD5` from the Flickr `OriginalURL`.
**Pipeline:** the frozen, audited `device_ai.acquisition` pipeline (preflight -> license/bbox/semantic gates -> ingest -> provenance -> dedup -> Gate A/B -> automated QA -> 70/20/10 seed-42 split -> promotion), reused UNCHANGED. Phase D used the ledger-backed, reap-tolerant downloader behind a sustained-RAM + Flickr-DNS launch gate.

> **Honesty contract.** Every count below is measured by a frozen component or read from persisted on-disk evidence, or is reported as `-` / `NOT_BUILT`. QA is AUTOMATED machine adjudication: `visual_verification` and `human_qa` are `NOT_PERFORMED` for every image. Nothing was committed and **Dataset v1 was NOT released** (`is_dataset_v1` / `is_released` remain FALSE).

---

## 1. P4.3.11 per-class funnel (Open Images V7 train split -> EcoTrace)

Legend: **Auth** = LOCKED authorized seed-42 target (never changed, never substituted); **Selected** = the builder's reproduced deterministic selection; **Verified** = downloaded bytes whose `base64(md5)` matched OI `OriginalMD5` (== *downloaded-and-kept*); **Unavail** = selected but not verifiable (link rot / forbidden / md5 mismatch); **Retained** = frozen ingest staged; **Promoted** = AUTO_ACCEPT and promotion-gate VERIFIED.

| Class | id | OI label | Status | Auth | Selected | Verified | Unavail | Retained | Boxes | AUTO_ACCEPT | UNVERIFIED | AUTO_REJECT | Promoted | Dedup | Split (tr/va/te) | Provenance | MB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| headphones | 17 | Headphones | NOT_BUILT | 1046 | 1046 | 180 | 866 | 0 | 0 | 0 | 0 | 0 | 0 | - | - | 0/0 | 0.0 |
| camera | 14 | Camera | NOT_BUILT | 3077 | 3077 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | - | - | 0/0 | 0.0 |
| tablet | 2 | Tablet computer | NOT_BUILT | 242 | 242 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | - | - | 0/0 | 0.0 |
| mouse | 10 | Computer mouse | NOT_BUILT | 249 | 249 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | - | - | 0/0 | 0.0 |
| printer | 8 | Printer | NOT_BUILT | 202 | 202 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | - | - | 0/0 | 0.0 |
| smartphone | 1 | Mobile phone | NOT_BUILT | 606 | 606 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | - | - | 0/0 | 0.0 |

Per-class machine reports & evidence: `staging/p4_3_11_openimages_train_expansion_v1/review/<class>/` (`P4_3_11_<CLASS>_ACQUISITION_REPORT.md`, `automation/run_report.json`, `automation/promotion_evidence.json`, `automation/automated_qa.json`, `automation/split_assignment.json`, `automation/duplicate_evidence.json`, `automation/provenance_manifest.json`).

> **Per-class Markdown header note.** Each per-class report is produced by the frozen P4.3.7 renderer reused unchanged, so its H1 reads "P4.3.7 -- Router Automation Report"; the body correctly reports the actual target class and taxonomy id. This consolidated report is the authoritative P4.3.11 artifact.

## 2. P4.3.11 wave totals

- Authorized seed-42 selection (LOCKED): **5422** (headphones 1046 / camera 3077 / tablet 242 / mouse 249 / printer 202 / smartphone 606). Builder-reproduced selected: **5422**. No ImageID was ever changed or substituted.
- Byte-verified downloaded: **180** | unavailable (link rot / mismatch): **866** | retained by frozen ingest: **0** | staged boxes: **0**
- Automated QA: **0** AUTO_ACCEPT | **0** UNVERIFIED | **0** AUTO_REJECT (`visual_verification` / `human_qa` = NOT_PERFORMED)
- Dedup exclusions (vs protected P4.3.5/6/9 + all P4.3.10 trees + P4.3.11 siblings + self): **0**
- Images **PROMOTED** (AUTO_ACCEPT and promotion-gate VERIFIED): **0** | provenance complete **0/0** | split tr/va/te **0/0/0**
- Classes reaching WAVE_VALIDATED: **0/6** (none); NOT_BUILT (Phase D not converged): headphones, camera, tablet, mouse, printer, smartphone

## 3. Cumulative dataset (P4.3.9 laptop + P4.3.10 nine classes + P4.3.11)

All numbers read from each batch's persisted finalization / promotion evidence on disk. Boxes: P4.3.9 = accepted-image boxes; P4.3.10 / P4.3.11 = retained-image staged boxes.

| Batch | Verified images | Promoted images | Boxes | Split (tr/va/te) |
| --- | --- | --- | --- | --- |
| P4.3.9 laptop | 117 | 59 | 74 | 41/11/7 |
| P4.3.10 (9 classes) | 436 | 176 | 525 | 120/33/23 |
| P4.3.11 (6 classes, this wave) | 180 | 0 | 0 | 0/0/0 |
| **Cumulative** | **733** | **235** | **599** | **161/44/30** |

## 4. Failures / blockers (this wave)

- `headphones`: no byte-verified archive present at archives/headphones/images; Phase D has not converged for this class
- `camera`: no byte-verified archive present at archives/camera/images; Phase D has not converged for this class
- `tablet`: no byte-verified archive present at archives/tablet/images; Phase D has not converged for this class
- `mouse`: no byte-verified archive present at archives/mouse/images; Phase D has not converged for this class
- `printer`: no byte-verified archive present at archives/printer/images; Phase D has not converged for this class
- `smartphone`: no byte-verified archive present at archives/smartphone/images; Phase D has not converged for this class

## 5. Storage on disk

- P4.3.11 staged (promoted/retained) images: **0.0 MB**
- P4.3.11 byte-verified archive working pool: **509.4 MB**
- P4.3.11 batch tree total: **1126.7 MB**
- Protected prior trees (read-only, never modified): **2193.6 MB** (P4.3.5 candidate 62.4 MB; P4.3.6 expansion 90.0 MB; P4.3.9 laptop 768.0 MB; P4.3.10 multiclass 1273.2 MB)
- Grand total (this batch + protected): **3320.2 MB** (3.242 GB) -- below the **50 GB** ceiling.

## 6. RAM / DNS operational stats (Phase D launch gate)

- Sustained-RAM + Flickr-DNS launch gate log: `_work/phaseD_run.log`.
- Clean stabilised launches (`STABLE`): **1** | gate-timeout launches (`TIMEOUT`, launched-anyway WARN): **0**
- Flickr DNS-canary failures observed (sick-host signature): **0** | longest single gate wait: **715 s**
- The host's memory-oscillation reaper SIGKILLs long jobs; each reap was recovered by relaunching through the gate. The ledger-backed builder checkpoints every 25 attempts and at exit, and every byte-verified image is preserved on disk, so a reap costs at most the in-flight image -- never verified progress and never the authorized selection.

## 7. 19-class taxonomy coverage (CUMULATIVE -- depth, not breadth)

Coverage is unchanged from P4.3.10: the six P4.3.11 classes are a SUBSET of the nine P4.3.10 classes, so this wave deepens existing classes rather than adding new ones. `Promoted` below is the cumulative per-class total across all batches; `+P4.3.11` marks the depth this wave adds.

| id | Class | Coverage | Cumulative promoted | Note |
| --- | --- | --- | --- | --- |
| 0 | laptop | ACQUIRED (P4.3.9) | 59 | acquired in the separate P4.3.9 Open Images V7 laptop batch (staging/p4_3_9_openimages_laptop_v1); not re-run by this batch |
| 1 | smartphone | ACQUIRED (P4.3.10 + P4.3.11 depth) | 35 (35 + 0 P4.3.11) | P4.3.11 wave status: NOT_BUILT |
| 2 | tablet | ACQUIRED (P4.3.10 + P4.3.11 depth) | 23 (23 + 0 P4.3.11) | P4.3.11 wave status: NOT_BUILT |
| 3 | desktop | BLOCKED_NO_SOURCE | 0 | no Open Images V7 boxable class denotes a desktop computer distinct from its monitor/keyboard/mouse components; no verified 1:1 public bbox source |
| 4 | server | BLOCKED_NO_SOURCE | 0 | no Open Images V7 boxable class denotes a server; no verified public bbox source in scope |
| 5 | monitor | ACQUIRED (P4.3.10) | 55 | covered at val+test depth; not deepened by P4.3.11 |
| 6 | crt_monitor | BLOCKED_NO_SOURCE | 0 | Open Images V7 'Computer monitor' does not distinguish CRT from flat-panel; mapping it to crt_monitor would fabricate a distinction the source label does not make |
| 7 | television | ACQUIRED (P4.3.10) | 0 | covered at val+test depth; not deepened by P4.3.11 |
| 8 | printer | ACQUIRED (P4.3.10 + P4.3.11 depth) | 27 (27 + 0 P4.3.11) | P4.3.11 wave status: NOT_BUILT |
| 9 | keyboard | ACQUIRED (P4.3.10) | 0 | covered at val+test depth; not deepened by P4.3.11 |
| 10 | mouse | ACQUIRED (P4.3.10 + P4.3.11 depth) | 26 (26 + 0 P4.3.11) | P4.3.11 wave status: NOT_BUILT |
| 11 | router | BLOCKED_NO_SOURCE | 0 | out of Open Images scope; handled by the separate P4.3.7 router pipeline, which reports BLOCKED_NO_SOURCE (no verified public router bbox source) |
| 12 | power_supply | BLOCKED_NO_SOURCE | 0 | no Open Images V7 boxable class denotes a power supply unit; no verified public bbox source in scope |
| 13 | cable | BLOCKED_NO_SOURCE | 0 | no Open Images V7 boxable class denotes an e-waste cable 1:1; no verified public bbox source in scope |
| 14 | camera | ACQUIRED (P4.3.10 + P4.3.11 depth) | 7 (7 + 0 P4.3.11) | P4.3.11 wave status: NOT_BUILT |
| 15 | game_console | BLOCKED_NO_SOURCE | 0 | no Open Images V7 boxable class denotes a game console 1:1; no verified public bbox source in scope |
| 16 | smartwatch | BLOCKED_NO_SOURCE | 0 | Open Images V7 'Watch' denotes analog/wrist watches, not smartwatches; mapping would be an unsupported inference |
| 17 | headphones | ACQUIRED (P4.3.10 + P4.3.11 depth) | 3 (3 + 0 P4.3.11) | P4.3.11 wave status: NOT_BUILT |
| 18 | battery | BLOCKED_NO_SOURCE | 0 | no Open Images V7 boxable class denotes a battery 1:1; no verified public bbox source in scope |

- Classes with acquired public data: **10 / 19** (laptop via P4.3.9 + nine P4.3.10 classes; P4.3.11 deepened six of them).
- Classes BLOCKED_NO_SOURCE: **9 / 19** (no verified 1:1 public Open Images bbox source in scope; reasons above).
- Thin classes (<50 cumulative promoted): `television` (0), `keyboard` (0), `headphones` (3), `camera` (7), `tablet` (23), `mouse` (26), `printer` (27), `smartphone` (35).
- Classes with >=100 cumulative promoted: none.

## 8. Protected-tree integrity & frozen-code changes

- All protected trees byte-identical before/after every P4.3.11 run: **True** (P4.3.5 candidate, P4.3.6 expansion, P4.3.9 laptop, and every P4.3.10 `acquired/<class>` tree are fingerprinted by the frozen preflight/protected-state stages; each completed P4.3.11 sibling is also protected when the next class runs).
- **Frozen code / taxonomy changes by P4.3.11: NONE.** This wave adds only additive tooling under the batch `_tooling/` directory plus per-class evidence and this report. The acquisition pipeline, semantic gate, license allowlist, dedup/split/promotion engines, and the 19-class taxonomy are imported UNCHANGED (the P4.3.10 authorized `Mobile phone -> smartphone` synonym is reused as-is, not extended).

## 9. YOLO11 training readiness -- exact remaining blockers

- **Cumulative promoted set: 235 images across 10/19 classes** (laptop + nine OI classes), 70/20/10 seed-42 split, every image a verbatim source byte copy with a YOLO label at the frozen taxonomy id and full provenance.
- **Sufficient to BEGIN** a preliminary / proof-of-concept multi-class YOLO11 detector over the 10 covered classes. **NOT sufficient for a production 19-class model.** Exact blockers before production training:
  1. **9/19 classes have no data** (BLOCKED_NO_SOURCE: `desktop`, `server`, `crt_monitor`, `router`, `power_supply`, `cable`, `game_console`, `smartwatch`, `battery`) -- each needs a verified 1:1 public bbox source or self-collection; none is invented here.
  2. **Thin classes need depth**: `television` (0 promoted), `keyboard` (0 promoted), `headphones` (3 promoted), `camera` (7 promoted), `tablet` (23 promoted), `mouse` (26 promoted), `printer` (27 promoted), `smartphone` (35 promoted) -- grow toward the per-class target before relying on them.
  3. **Human QA is still NOT_PERFORMED**: all verdicts are automated machine adjudication. A human sign-off is required before any `is_dataset_v1` / `is_released` transition.
  4. **Release build not assembled**: a training run must merge these promoted waves with the protected P4.3.5/P4.3.6 batches and re-run the whole-dataset readiness gate (coverage + per-split presence across all 19 classes).
- **Not released, not committed.** `is_dataset_v1` / `is_released` remain FALSE.
