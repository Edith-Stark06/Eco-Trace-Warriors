# Device Detection — Dataset Sources

**Sprint:** P4.1.4 — Production Dataset Acquisition
**Component:** Device Intelligence Engine (DIE) — YOLO Detector (milestone M1.4)
**Status:** Active
**Scope:** Source identification only. This document catalogues **candidate public
image sources** for each of the 19 device classes. It does **not** download any
dataset, fetch any weights, or train any model.

---

## 1. Purpose

This is the sourcing catalogue for **Dataset v1.0** of the device detector. For
every class in the canonical taxonomy it lists candidate image sources with their
license, an **indicative** image volume, and the trade-offs that decide how much
weight each source should carry in the collection plan
(`docs/engineering/device_dataset_acquisition.md`).

> **The taxonomy is fixed and code-owned.** The 19 classes and their class-ID
> ordering come from the component profile library
> (`intelligence/device_ai/components/data/components.yaml`), surfaced by
> `dataset/taxonomy.py::load_taxonomy()`. This document does **not** invent or
> reorder classes — it sources images for the classes the code already defines.

> **Counts are estimates to verify at collection time.** Public dataset contents
> change between releases. Every image count below is an **order-of-magnitude
> planning estimate**, not a verified figure. The acquisition checklist
> (`docs/ai/device_collection_checklist.md`) requires the collector to confirm
> the actual count, license, and redistribution terms **before** importing.

> **Production status note (added at finalization):** this catalogue's 19-class
> scope is the correct long-term acquisition target, but the detector currently
> **deployed to production** (`docker_data/device_ai/models/best.pt`, SHA256
> `c40a4afccacbbde89fce2a3a5fb73467e8614dc09365ea4678b24f7ad9218e92`) was trained
> on only 8 of these 19 classes (laptop, smartphone, tablet, monitor, printer,
> mouse, camera, headphones) — the remaining 11 were temporarily dropped from
> the training run for insufficient data, not removed from this catalogue's
> scope. Do not describe the live production detector as covering the full
> 19-class taxonomy; it does not yet.

---

## 2. Canonical classes (class-ID order)

| ID | Class | Primary search terms / aliases (from `components.yaml`) |
| --- | --- | --- |
| 0 | `laptop` | laptop, notebook, ultrabook, notebook computer |
| 1 | `smartphone` | cell phone, mobile phone, smartphone, handset |
| 2 | `tablet` | tablet, slate, iPad-class device |
| 3 | `desktop` | desktop computer, PC, tower, workstation |
| 4 | `server` | server, rack server, blade chassis |
| 5 | `monitor` | monitor, LCD/LED monitor, display, screen |
| 6 | `crt_monitor` | CRT, cathode-ray tube monitor |
| 7 | `television` | TV, smart TV, television |
| 8 | `printer` | printer, inkjet, laser printer, MFP |
| 9 | `keyboard` | computer keyboard |
| 10 | `mouse` | computer mouse |
| 11 | `router` | Wi-Fi router, wireless router, modem, gateway |
| 12 | `power_supply` | power adapter, charger, PSU, power brick |
| 13 | `cable` | USB cable, power cable, wire |
| 14 | `camera` | digital camera, webcam |
| 15 | `game_console` | game console, gaming console |
| 16 | `smartwatch` | smartwatch, wearable, smart watch |
| 17 | `headphones` | headphones, earbuds, earphones, headset |
| 18 | `battery` | battery, battery pack, cell |

---

## 3. Source families (overview)

The catalogue draws from six families, in descending order of preferred reliance:

| Family | Examples | Licence posture | Best for |
| --- | --- | --- | --- |
| **A. Large annotated detection sets** | Open Images V7, Objects365, LVIS, COCO | Permissive (CC-BY / Apache-2.0 on annotations) — **verify per image** | Common classes with existing bounding boxes |
| **B. Community detection sets** | Roboflow Universe, Kaggle e-waste sets | Mixed (CC-BY, CC0, some restrictive) — **verify per dataset** | E-waste-specific framing, rarer classes |
| **C. Open media libraries** | Wikimedia Commons, Openverse, Flickr (CC) | Per-image CC — **verify each** | Filling gaps, licence-clean singles |
| **D. Manufacturer / product imagery** | OEM product pages, spec sheets | **Usually copyrighted — not training-cleared** | Reference only; import **only** with written permission |
| **E. Self-collected** | Team photos, partner e-waste yards | Team-owned (`CC-BY-4.0` / `proprietary`) | Rare/hazardous classes, Indian-context realism |
| **F. Synthetic augmentation** | Compositing, rendered, augmentation pipeline | Derived — inherits source licence | Class balancing, hard-negative generation |

> Family **D** (manufacturer imagery) is listed for completeness but is
> **out-of-the-box non-permissive**. Product photos are copyrighted and their
> terms almost never permit ML training or redistribution. Treat them as a
> reference for *what a class looks like*, never as importable data, unless a
> signed licence exists. This mirrors the provenance rule in the annotation
> runbook: never relabel a restrictive licence as permissive.

---

## 4. Per-class source catalogue

Each class lists a **primary** source (best coverage/licence) and one or more
**secondary** sources. Volumes are indicative (§1 caveat).

### 4.0 `laptop`
| Source | License | Est. images | Strengths | Weaknesses |
| --- | --- | --- | --- | --- |
| Open Images V7 ("Laptop") | CC-BY 4.0 (images) / Apache-2.0 (annotations) | ~5k+ boxes | Existing bounding boxes; varied scenes | Consumer bias; few e-waste/damaged units |
| Objects365 / LVIS ("laptop") | CC-BY 4.0 | ~few k | Dense scenes, occlusion variety | Label granularity varies |
| COCO ("laptop") | CC-BY 4.0 | ~few k | Well-curated boxes | Only pristine, in-use laptops |
| Self-collected (partner yards) | proprietary / CC-BY-4.0 | target 200+ | Damaged/opened units, Indian context | Manual effort |

### 4.1 `smartphone`
| Source | License | Est. images | Strengths | Weaknesses |
| --- | --- | --- | --- | --- |
| Open Images V7 ("Mobile phone") | CC-BY 4.0 | ~5k+ | Large, boxed | Mostly front-screen consumer shots |
| Objects365 ("cell phone") | CC-BY 4.0 | ~few k | Hands/scenes, scale variety | In-use bias |
| Roboflow Universe (phone detection) | Mixed — verify | varies | Task-specific crops | Licence/quality varies per set |
| Self-collected | proprietary / CC-BY-4.0 | target 200+ | Back covers, damaged, batteries removed | Manual effort |

### 4.2 `tablet`
| Source | License | Est. images | Strengths | Weaknesses |
| --- | --- | --- | --- | --- |
| Open Images V7 ("Tablet computer") | CC-BY 4.0 | ~1–3k | Boxed instances | Confusable with smartphone/monitor |
| LVIS ("tablet") | CC-BY 4.0 | ~hundreds | Occlusion diversity | Sparse |
| Self-collected + Wikimedia (CC) | mixed CC / proprietary | target 150+ | Fills the gap | Manual verification |

### 4.3 `desktop`
| Source | License | Est. images | Strengths | Weaknesses |
| --- | --- | --- | --- | --- |
| Open Images V7 ("Computer / Personal computer") | CC-BY 4.0 | ~1–3k | Tower + all-in-one variety | "Computer" label is broad; needs re-check |
| Objects365 | CC-BY 4.0 | ~hundreds | Office scenes | Monitor/desktop co-occurrence confusion |
| Self-collected | proprietary / CC-BY-4.0 | target 150+ | Opened cases, cabling | Manual effort |

### 4.4 `server` *(under-served — plan for self-collection)*
| Source | License | Est. images | Strengths | Weaknesses |
| --- | --- | --- | --- | --- |
| Wikimedia Commons ("server rack") | CC-BY / CC0 — verify | ~hundreds | Rack/chassis realism | Few tight single-unit boxes |
| Roboflow Universe (datacenter) | Mixed — verify | varies | Some boxed racks | Small, licence-mixed |
| Self-collected (partner ITAD) | proprietary / CC-BY-4.0 | target 100+ | Real decommissioned units | Access-limited |
| Synthetic augmentation | derived | as needed | Balances the class | Domain gap risk |

### 4.5 `monitor`
| Source | License | Est. images | Strengths | Weaknesses |
| --- | --- | --- | --- | --- |
| Open Images V7 ("Computer monitor") | CC-BY 4.0 | ~3k+ | Boxed flat panels | Confusable with TV; on-screen content varies |
| COCO ("tv") *(re-verify class)* | CC-BY 4.0 | ~few k | Many instances | COCO merges TV/monitor — needs relabel |
| Self-collected | proprietary / CC-BY-4.0 | target 150+ | Powered-off, damaged panels | Manual effort |

### 4.6 `crt_monitor` *(rare + hazardous — plan for self-collection + synthetic)*
| Source | License | Est. images | Strengths | Weaknesses |
| --- | --- | --- | --- | --- |
| Wikimedia Commons ("CRT monitor") | CC-BY / CC0 — verify | ~hundreds | Historically rich | Few detection boxes |
| Roboflow Universe (retro/e-waste) | Mixed — verify | varies | E-waste framing | Small volumes |
| Self-collected (e-waste yards) | proprietary / CC-BY-4.0 | target 100+ | Real disposal context, India | Increasingly scarce hardware |
| Synthetic augmentation | derived | as needed | Class balancing | Domain gap risk |

### 4.7 `television`
| Source | License | Est. images | Strengths | Weaknesses |
| --- | --- | --- | --- | --- |
| Open Images V7 ("Television") | CC-BY 4.0 | ~3k+ | Boxed panels | Merges with monitor visually |
| COCO ("tv") | CC-BY 4.0 | ~few k | Living-room scenes | Merged TV/monitor label |
| Self-collected | proprietary / CC-BY-4.0 | target 150+ | Back panels, CRT TVs | Manual effort |

### 4.8 `printer`
| Source | License | Est. images | Strengths | Weaknesses |
| --- | --- | --- | --- | --- |
| Open Images V7 ("Printer") | CC-BY 4.0 | ~1–3k | Boxed office units | Consumer/inkjet bias |
| Objects365 | CC-BY 4.0 | ~hundreds | Scene variety | Sparse |
| Self-collected | proprietary / CC-BY-4.0 | target 120+ | Laser/MFP, opened units | Manual effort |

### 4.9 `keyboard`
| Source | License | Est. images | Strengths | Weaknesses |
| --- | --- | --- | --- | --- |
| Open Images V7 ("Computer keyboard") | CC-BY 4.0 | ~3k+ | Abundant, boxed | Top-down desk bias |
| COCO ("keyboard") | CC-BY 4.0 | ~few k | Many instances | In-use co-occurrence with laptop |
| Self-collected | proprietary / CC-BY-4.0 | target 100+ | Detached, damaged | Manual effort |

### 4.10 `mouse`
| Source | License | Est. images | Strengths | Weaknesses |
| --- | --- | --- | --- | --- |
| Open Images V7 ("Computer mouse") | CC-BY 4.0 | ~2k+ | Boxed instances | Small object; scale bias |
| COCO ("mouse") | CC-BY 4.0 | ~few k | Many instances | Confusable with living mouse label upstream |
| Self-collected | proprietary / CC-BY-4.0 | target 100+ | Varied shapes | Manual effort |

### 4.11 `router`
| Source | License | Est. images | Strengths | Weaknesses |
| --- | --- | --- | --- | --- |
| Open Images V7 (limited) | CC-BY 4.0 | ~hundreds | Some boxed units | Class not always distinct |
| Roboflow Universe (router/networking) | Mixed — verify | varies | Task-specific | Licence/quality varies |
| Wikimedia Commons | CC-BY / CC0 — verify | ~hundreds | Model variety | Manual boxing |
| Self-collected | proprietary / CC-BY-4.0 | target 120+ | Antennas, modems | Manual effort |

### 4.12 `power_supply` *(under-served — plan for self-collection)*
| Source | License | Est. images | Strengths | Weaknesses |
| --- | --- | --- | --- | --- |
| Roboflow Universe (adapters/PSU) | Mixed — verify | varies | E-waste framing | Small, licence-mixed |
| Wikimedia Commons ("power supply / AC adapter") | CC-BY / CC0 — verify | ~hundreds | Model variety | Few boxes |
| Self-collected | proprietary / CC-BY-4.0 | target 120+ | Bricks, ATX PSUs, chargers | Manual effort |
| Synthetic augmentation | derived | as needed | Balances small object | Domain gap |

### 4.13 `cable` *(under-served — plan for self-collection)*
| Source | License | Est. images | Strengths | Weaknesses |
| --- | --- | --- | --- | --- |
| Wikimedia Commons ("cable / wire") | CC-BY / CC0 — verify | ~hundreds | Type variety | Thin/curved objects hard to box |
| Roboflow Universe (cable detection) | Mixed — verify | varies | Task-specific | Licence varies |
| Self-collected | proprietary / CC-BY-4.0 | target 120+ | Tangled/bundled realism | Boxing effort high |

### 4.14 `camera`
| Source | License | Est. images | Strengths | Weaknesses |
| --- | --- | --- | --- | --- |
| Open Images V7 ("Camera") | CC-BY 4.0 | ~3k+ | Abundant, boxed | DSLR/consumer bias vs webcam |
| Objects365 | CC-BY 4.0 | ~hundreds | Scene variety | Webcams under-represented |
| Self-collected | proprietary / CC-BY-4.0 | target 100+ | Webcams, action cams | Manual effort |

### 4.15 `game_console` *(under-served — plan for community + self-collection)*
| Source | License | Est. images | Strengths | Weaknesses |
| --- | --- | --- | --- | --- |
| Roboflow Universe (console detection) | Mixed — verify | varies | Task-specific | Licence/quality varies |
| Wikimedia Commons | CC-BY / CC0 — verify | ~hundreds | Model variety | Few boxes |
| Self-collected | proprietary / CC-BY-4.0 | target 100+ | Real units + controllers | Manual effort |

### 4.16 `smartwatch`
| Source | License | Est. images | Strengths | Weaknesses |
| --- | --- | --- | --- | --- |
| Open Images V7 ("Watch") *(re-verify)* | CC-BY 4.0 | ~1–3k | Some boxed | "Watch" merges analog + smart |
| Roboflow Universe (smartwatch) | Mixed — verify | varies | Task-specific | Small volumes |
| Self-collected | proprietary / CC-BY-4.0 | target 100+ | Screen on/off variety | Manual effort |

### 4.17 `headphones`
| Source | License | Est. images | Strengths | Weaknesses |
| --- | --- | --- | --- | --- |
| Open Images V7 ("Headphones") | CC-BY 4.0 | ~2k+ | Boxed instances | Over-ear bias vs earbuds |
| Objects365 | CC-BY 4.0 | ~hundreds | Scene variety | Earbuds under-represented |
| Self-collected | proprietary / CC-BY-4.0 | target 100+ | Earbuds, headsets | Manual effort |

### 4.18 `battery` *(under-served — plan for self-collection + synthetic)*
| Source | License | Est. images | Strengths | Weaknesses |
| --- | --- | --- | --- | --- |
| Roboflow Universe (battery detection) | Mixed — verify | varies | E-waste framing | Licence/quality varies |
| Wikimedia Commons ("battery") | CC-BY / CC0 — verify | ~hundreds | Cell/pack variety | Few boxes; confusable |
| Self-collected | proprietary / CC-BY-4.0 | target 120+ | Li-ion packs, coin cells | Hazard handling; manual |
| Synthetic augmentation | derived | as needed | Balances small object | Domain gap |

---

## 5. Coverage summary & sourcing risk

| Coverage tier | Classes | Primary strategy |
| --- | --- | --- |
| **Well-served** by families A/B | laptop, smartphone, monitor, television, keyboard, mouse, camera, headphones, printer | Lead with Open Images/Objects365/COCO; top up by self-collection |
| **Partially served** | tablet, desktop, router, smartwatch | Mix A/B/C; meaningful self-collection |
| **Under-served** (self-collect + synthetic) | server, crt_monitor, power_supply, cable, game_console, battery | Lead with self-collection + community; use synthetic for balance |

The under-served tier is the **schedule risk** for Dataset v1.0 and is called out
again in the collection strategy and the acquisition checklist.

---

## 6. Licence policy (binding)

1. **Permissive only for import.** Import an image only under a licence that
   permits ML training **and** redistribution (CC-BY, CC0, CC-BY-SA with
   attribution kept, Apache-2.0, public domain, or team-owned). Record the exact
   licence in provenance (`ProvenanceRecord.license`).
2. **Attribution preserved.** For CC-BY/CC-BY-SA, retain author + source URL in
   the collection log so attribution can be reproduced in a release.
3. **No restrictive relabeling.** Never record a restrictive source as
   permissive. When licence is unclear, **exclude**.
4. **Manufacturer imagery excluded** unless a signed licence exists (§3, family D).
5. **Provenance is mandatory.** Every imported image gets a `ProvenanceRecord`
   (source, licence, contributor, collection date, checksum) via
   `ProvenanceCollector` — the same rule enforced in
   `docs/engineering/device_detection_annotation.md`.

---

## 7. Related documents

| Document | Role |
| --- | --- |
| `docs/engineering/device_dataset_acquisition.md` | Collection workflow, QA, lifecycle, release (P4.1.4 PART 8) |
| `docs/ai/device_collection_checklist.md` | Operational checklist for building v1.0 (P4.1.4 PART 6) |
| `docs/engineering/device_detection_annotation.md` | Annotation, review, QA, versioning runbook (P4.1.2) |
| `intelligence/device_ai/components/data/components.yaml` | Canonical taxonomy source of truth |

> **Out of scope for P4.1.4:** no dataset is downloaded, no weights are fetched,
> no model is trained, no inference is implemented, and no API/interface is
> modified. This catalogue plans sourcing; acquisition happens against the
> checklist.
