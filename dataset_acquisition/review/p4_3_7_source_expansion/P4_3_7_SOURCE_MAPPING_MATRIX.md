# P4.3.7 — Source Mapping Matrix (9 Missing Classes)

**Sprint:** P4.3.7 — Coverage-First Source Expansion (research only)
**Component:** Device Intelligence Engine (DIE) — YOLO Detector (M1.4)
**Date:** 2026-08-15
**Protected HEAD:** `b4604f9`
**Scope:** Source *identification and risk assessment* for the **9 taxonomy
classes with zero images** in the P4.3.5 candidate. This document **downloads
nothing, acquires nothing, merges nothing, releases nothing, and commits
nothing.** It extends the P4.1.4 catalogue (`docs/ai/device_detection_sources.md`)
for the specific classes that block the coverage gate.

---

## 0. Verification status & method limitation (read first)

> **No live web verification was possible in this session** (the environment's
> web-search/fetch tools were unavailable). Consequently **every external-source
> license, bounding-box availability, and image count in this matrix is
> UNCONFIRMED and marked `VERIFY`.** Nothing here may be treated as a cleared
> source. This is deliberate and matches the binding policy in
> `device_detection_sources.md §6` and `device_collection_checklist.md §2`:
> *confirm the license (ML-training + redistribution) and the actual count
> **before** importing; when unclear → exclude.*
>
> The only path graded `SAFE` without external verification is **self-collection**
> (team-owned images, license-clean by construction). Everything else is
> `CONDITIONAL` (verify per dataset / per image) or `REJECT` (semantically unsafe
> mapping — no license can fix a wrong label).

**No fabrication.** No image counts are invented. The catalogue's per-class
volumes are order-of-magnitude planning estimates (see `device_detection_sources.md §1`),
not verified figures, and are omitted here rather than restated as fact.

---

## 1. Recommendation vocabulary

| Verdict | Meaning | May proceed to acquisition (separate, gated sprint)? |
| --- | --- | --- |
| **SAFE** | Semantic match is exact **and** a license-clean, reproducible path exists that needs no external-license gamble (self-collection under team ownership, or an already-approved source). | Yes, under the standard QA gates. |
| **CONDITIONAL** | A plausible source exists, but **at least one** of {license, bbox availability, count, semantic tightness} is UNVERIFIED. Excluded until each is confirmed per dataset / per image. | Only after the row's verification checklist passes. |
| **REJECT** | The only tempting source is an **ambiguous or conflated label** that would mislabel this class or its neighbour. No license can repair a wrong semantic. | No — do not use, at any license. |

**Bounding-box rule (binding):** a source is a *bbox source* only if it ships
real bounding boxes for the target class. Image-classification sets and open
media libraries (Wikimedia/Openverse/Flickr) generally ship **no boxes** — they
are *image* sources that require **manual annotation** before use, and are graded
`CONDITIONAL` on that basis, never assumed to be detection-ready.

---

## 2. Why these 9 are missing (root cause)

The 9 zero-image classes are **exactly** the 9 rows the P4.3.1 acquisition plan
(`dataset_acquisition/manifests/p4_3_1_openimages_acquisition_plan.csv`) marks
`UNMAPPED` / `BLOCKED` — because Open Images V7 (the only wired-up source) has
**no safe boxable label** for them. They are missing by *design of the source
policy*, not by oversight. Closing the coverage gate therefore requires **new
source families** (community detection sets, open media + manual annotation,
self-collection, synthetic balancing), each carrying the verification burden above.

---

## 3. The matrix

Canonical IDs from `load_taxonomy()` (v1.0.0). Multiple candidate rows per class;
the **first tempting-but-unsafe** option is shown explicitly as `REJECT` where one
exists, because naming the trap is part of the task.

### 3.1 `desktop` — ID 3

| ID | Class | Candidate source | Source class | License | BBox? | Semantic match | Risk | Recommendation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 3 | desktop | Open Images V7 | "Computer" / "Personal computer" | annotations CC-BY-4.0; images per-image Flickr (VARY) | Yes (broad) | **Poor** — label conflates tower + all-in-one + the *monitor*; boxes frequently bound the display, not the chassis | Poisons `desktop` **and** `monitor` (ID 5) | **REJECT** |
| 3 | desktop | Objects365 / LVIS | candidate cat. e.g. "computer box"/"desktop computer" (unconfirmed) | `VERIFY` (annotations CC-BY-4.0 typical; images Flickr terms) | `VERIFY` | Conditional — only if a *tower/chassis-specific* category exists | Category may not exist; may inherit the same monitor-conflation | **CONDITIONAL** |
| 3 | desktop | Roboflow Universe / Kaggle | "desktop"/"PC tower"/"e-waste" sets | `VERIFY` per dataset | `VERIFY` | Conditional — inspect samples for chassis-only boxes | License/provenance often unclear | **CONDITIONAL** |
| 3 | desktop | **Self-collection** (partner yards, offices) | tower / all-in-one chassis | team-owned (CC-BY-4.0 / proprietary) | Manual annotation | **Exact** — box the chassis, exclude the monitor | Manual effort; enforce guideline "box tower, not screen" | **SAFE** |

### 3.2 `server` — ID 4

| ID | Class | Candidate source | Source class | License | BBox? | Semantic match | Risk | Recommendation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 4 | server | Open Images V7 | — | — | No | none | No boxable class | **REJECT** (no source) |
| 4 | server | Roboflow Universe (datacenter/rack) | "server"/"rack"/"blade" | `VERIFY` per dataset | `VERIFY` | Conditional — many box a whole rack row, not one unit | License mixed; single-unit boxes scarce | **CONDITIONAL** |
| 4 | server | Wikimedia Commons ("server rack") | image only | per-image CC (`VERIFY`) | No (manual) | Good for realism | No boxes; wide shots | **CONDITIONAL** |
| 4 | server | **Self-collection** (partner ITAD) | rack / blade / tower server | team-owned | Manual annotation | **Exact** — real decommissioned units | Access-limited; hazard low | **SAFE** |
| 4 | server | Synthetic augmentation | rendered / composited | derived (inherits source) | Generated | Balancing only | Domain gap; keep ≤ ~20% (checklist §5) | **CONDITIONAL** (support only) |

### 3.3 `crt_monitor` — ID 6

| ID | Class | Candidate source | Source class | License | BBox? | Semantic match | Risk | Recommendation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 6 | crt_monitor | Open Images V7 | "Computer monitor" | annotations CC-BY-4.0; images Flickr (VARY) | Yes | **None** — cannot distinguish CRT from flat panel; would corrupt `monitor` (ID 5) too | Poisons both monitor classes | **REJECT** |
| 6 | crt_monitor | Roboflow Universe (retro / e-waste) | "CRT"/"CRT monitor" | `VERIFY` per dataset | `VERIFY` | Conditional — must exclude CRT **televisions** (ID 7) | Small volumes; CRT-TV/CRT-monitor confusion | **CONDITIONAL** |
| 6 | crt_monitor | Wikimedia Commons ("CRT monitor") | image only | per-image CC (`VERIFY`) | No (manual) | Good — historically rich | No boxes; scarce hardware | **CONDITIONAL** |
| 6 | crt_monitor | **Self-collection** (e-waste yards, India) | CRT computer monitor | team-owned | Manual annotation | **Exact** — real disposal context | Hardware increasingly scarce; bulky | **SAFE** |
| 6 | crt_monitor | Synthetic augmentation | rendered | derived | Generated | Balancing only | Domain gap; ≤ ~20% | **CONDITIONAL** (support only) |

### 3.4 `router` — ID 11

| ID | Class | Candidate source | Source class | License | BBox? | Semantic match | Risk | Recommendation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 11 | router | Open Images V7 | (none distinct) | — | No | none reliable | No distinct boxable class | **REJECT** (no source) |
| 11 | router | Roboflow Universe (networking) | "router"/"modem"/"gateway" | `VERIFY` per dataset | `VERIFY` | Good if present — routers/modems/gateways are in-class per aliases | License/quality varies; exclude set-top boxes | **CONDITIONAL** |
| 11 | router | Wikimedia Commons | image only | per-image CC (`VERIFY`) | No (manual) | Good model variety | No boxes | **CONDITIONAL** |
| 11 | router | **Self-collection** (homes/offices) | Wi-Fi router / modem / gateway | team-owned | Manual annotation | **Exact** — ubiquitous, easy access | Confusable with set-top boxes — enforce guideline | **SAFE** |

### 3.5 `power_supply` — ID 12

| ID | Class | Candidate source | Source class | License | BBox? | Semantic match | Risk | Recommendation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 12 | power_supply | Open Images V7 | "Power plugs and sockets" | annotations CC-BY-4.0; images Flickr (VARY) | Yes | **None** — a wall socket/plug is **not** a PSU/charger/brick | Semantic corruption | **REJECT** |
| 12 | power_supply | Roboflow Universe (adapters/PSU) | "adapter"/"charger"/"PSU" | `VERIFY` per dataset | `VERIFY` | Conditional — must exclude bare cables (ID 13) and batteries/power-banks (ID 18) | License mixed; overlap with battery/cable | **CONDITIONAL** |
| 12 | power_supply | Wikimedia Commons ("AC adapter") | image only | per-image CC (`VERIFY`) | No (manual) | Good model variety | No boxes | **CONDITIONAL** |
| 12 | power_supply | **Self-collection** | laptop brick / ATX PSU / charger | team-owned | Manual annotation | **Exact** — box the brick, not the cable | Small object; power-bank↔battery ambiguity — enforce guideline | **SAFE** |

### 3.6 `cable` — ID 13

| ID | Class | Candidate source | Source class | License | BBox? | Semantic match | Risk | Recommendation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 13 | cable | Open Images V7 | (generic "Cable" senses) | — | No reliable | Ambiguous — "cable" senses (cable car, wire fence) leak in generic sources | Off-domain contamination | **REJECT** (no clean source) |
| 13 | cable | Roboflow Universe (cable detection) | "cable"/"wire"/"cord" | `VERIFY` per dataset | `VERIFY` | Conditional — inspect for USB/power/data cords specifically | License varies; thin objects hard to box | **CONDITIONAL** |
| 13 | cable | Wikimedia Commons ("USB cable"/"power cord") | image only | per-image CC (`VERIFY`) | No (manual) | Good type variety | No boxes; boxing thin/curved objects is hard | **CONDITIONAL** |
| 13 | cable | **Self-collection** | USB / power / HDMI cables, bundles | team-owned | Manual annotation | **Exact** — tangled/bundled realism | High boxing effort; low box quality on thin objects | **SAFE** |

### 3.7 `game_console` — ID 15

| ID | Class | Candidate source | Source class | License | BBox? | Semantic match | Risk | Recommendation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 15 | game_console | Open Images V7 | "Joystick"/"Remote control"/"Toy" | annotations CC-BY-4.0 | Yes | **None** — a controller/remote/toy is **not** the console body | Mislabels controllers as consoles | **REJECT** |
| 15 | game_console | Roboflow Universe (console detection) | "console"/"PlayStation"/"Xbox"/"Switch" | `VERIFY` per dataset | `VERIFY` | Conditional — confirm boxes are the console unit | License/quality varies | **CONDITIONAL** |
| 15 | game_console | Wikimedia Commons | image only | per-image CC (`VERIFY`) | No (manual) | Good model variety | No boxes | **CONDITIONAL** |
| 15 | game_console | **Self-collection** | console units (+ optional controllers as `difficult`) | team-owned | Manual annotation | **Exact** — real units | Access moderate; define controller policy up front | **SAFE** |

### 3.8 `smartwatch` — ID 16

| ID | Class | Candidate source | Source class | License | BBox? | Semantic match | Risk | Recommendation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 16 | smartwatch | Open Images V7 | "Watch" | annotations CC-BY-4.0; images Flickr (VARY) | Yes | **Ambiguous** — "Watch" merges analog + smart; imports analog watches as smartwatch | Semantic corruption | **REJECT** |
| 16 | smartwatch | Roboflow Universe (smartwatch) | "smartwatch"/"smart watch" | `VERIFY` per dataset | `VERIFY` | Good if present — screen/band specific | Small volumes; license varies | **CONDITIONAL** |
| 16 | smartwatch | Wikimedia Commons | image only | per-image CC (`VERIFY`) | No (manual) | Good | No boxes | **CONDITIONAL** |
| 16 | smartwatch | **Self-collection** | smartwatches, screen on/off | team-owned | Manual annotation | **Exact** — exclude analog watches | Easy consumer access | **SAFE** |

### 3.9 `battery` — ID 18

| ID | Class | Candidate source | Source class | License | BBox? | Semantic match | Risk | Recommendation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 18 | battery | Open Images V7 | (none) | — | No | none | No boxable class | **REJECT** (no source) |
| 18 | battery | Roboflow Universe (battery/e-waste) | "battery"/"cell"/"li-ion" | `VERIFY` per dataset | `VERIFY` | Conditional — exclude power-banks that are `power_supply` (ID 12) | License varies; polysemy in web sources | **CONDITIONAL** |
| 18 | battery | Wikimedia Commons ("battery") | image only | per-image CC (`VERIFY`) | No (manual) | Good cell/pack variety | No boxes; "battery" polysemy | **CONDITIONAL** |
| 18 | battery | **Self-collection** | AA/AAA, coin cells, Li-ion packs | team-owned | Manual annotation | **Exact** — real recycling context | Hazard handling; small object | **SAFE** |
| 18 | battery | Synthetic augmentation | rendered | derived | Generated | Balancing only | Domain gap; ≤ ~20% | **CONDITIONAL** (support only) |

---

## 4. Summary by verdict

| Verdict | Rows (source options) | Classes where it is the **lead** path |
| --- | --- | --- |
| **SAFE** | 9 (one self-collection lead per class) | all 9 (self-collection) |
| **CONDITIONAL** | community sets, open media, large sets, synthetic | scale-up / depth on all 9 (pending per-source verification) |
| **REJECT** | the 6 named false mappings + 3 "no source" | see §5 |

### 4.1 Dangerous false mappings — do NOT use (the task's explicit hazard list)

| Class (ID) | Trap label | Why REJECT |
| --- | --- | --- |
| desktop (3) | generic "Computer" / "Personal computer" | conflates tower + all-in-one + **monitor**; boxes the screen |
| crt_monitor (6) | "Computer monitor" | indistinguishable from flat-panel `monitor` (ID 5) |
| power_supply (12) | "Power plugs and sockets" | wall socket/plug ≠ PSU/charger |
| game_console (15) | generic "game controller"/"joystick"/"remote"/"toy" | controller/remote ≠ console body |
| smartwatch (16) | generic "Watch" | merges analog + smart wristwatches |
| battery (18) | generic "battery" web senses | polysemy (artillery/legal/drum "battery"); confusable |

`server (4)`, `router (11)`, `cable (13)`, `battery (18)` additionally have **no
boxable Open Images source at all** — they cannot be topped up from the wired-up
pipeline and depend entirely on `CONDITIONAL` community/open-media sources
(verified) or `SAFE` self-collection.

---

## 5. What this matrix does **not** authorise

- It does **not** approve any specific external dataset — every `CONDITIONAL` row
  is gated on the verification checklist in the acquisition plan
  (`P4_3_7_ACQUISITION_PLAN.md §4`).
- It does **not** download, acquire, annotate, merge, or release anything.
- It does **not** revive the unsupported "150 images/class" target or any
  "29-image gap" (see `P4_3_7_SPLIT_GATE_RECOVERY.md §§9–11`). Depth is governed
  by the **per-split presence** requirement, not a fixed count.

> Cross-references: `P4_3_7_COVERAGE_RESEARCH.md` (full research, 12 sections),
> `P4_3_7_ACQUISITION_PLAN.md` (prioritised, gated plan),
> `docs/ai/device_detection_sources.md §6` (binding license policy),
> `docs/ai/device_collection_checklist.md` (operational runbook).
