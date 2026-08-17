# P4.3.7 — Coverage Research (Source Expansion for 9 Missing Classes)

**Sprint:** P4.3.7 — Coverage-First Source Expansion (research only)
**Component:** Device Intelligence Engine (DIE) — YOLO Detector (M1.4)
**Date:** 2026-08-15
**Protected HEAD:** `b4604f9`
**Verdict:** The coverage gate is blocked by **9 taxonomy classes with zero
images**. All nine are `UNMAPPED` in the Open Images pipeline **by design**;
closing the gap needs **new source families** — led by **license-clean
self-collection** (the only `SAFE` path this session), with community/open-media
sources admitted only after per-source verification. **Recommended first class:
`router` (ID 11).**

> **This document acquires nothing.** No download, annotation, candidate change,
> merge, release, or commit. It is research and a gated plan only.

---

## Section 1 — Executive summary

- **State:** 4/19 classes covered (smartphone·1, tablet·2, monitor·5, printer·8);
  **15 missing**. This sprint researches the **9** that were never mappable to the
  wired-up source: desktop·3, server·4, crt_monitor·6, router·11, power_supply·12,
  cable·13, game_console·15, smartwatch·16, battery·18. *(The remaining 6 —
  laptop·0, television·7, keyboard·9, mouse·10, camera·14, headphones·17 — are the
  P4.3.6 `QA_PENDING` expansion, deliberately left unmerged.)*
- **Root cause:** these 9 are exactly the `UNMAPPED`/`BLOCKED` rows of
  `dataset_acquisition/manifests/p4_3_1_openimages_acquisition_plan.csv` — Open
  Images V7 has no safe boxable label for them.
- **Path forward:** self-collection (`SAFE`) leads every class; community sets,
  open media (+ manual annotation), and synthetic are `CONDITIONAL` on the
  verification gate; the six tempting mislabels are `REJECT`.
- **First class:** `router` (§11).

> **Method limitation (integrity note):** web search/fetch were unavailable this
> session, so **no external dataset's license, bbox availability, or count could
> be verified.** Every external source is therefore `CONDITIONAL`/`VERIFY`; none
> is asserted as cleared. This mirrors the repo's binding rule — *confirm before
> import; unclear ⇒ exclude.*

---

## Section 2 — Scope, guardrails, and honoured constraints

**In scope:** taxonomy semantics for the 9 classes; candidate source families +
risk; SAFE/CONDITIONAL/REJECT matrix; prioritisation; a gated, reproducible
acquisition plan; the split-gate constraint; protected-state verification.

**Explicitly honoured constraints (from the task):**

- No "150 images/class" target; no "29-image gap" — both unsupported
  (`P4_3_7_SPLIT_GATE_RECOVERY.md §§9–11`).
- No fabricated counts; no invented class mappings; no forced mapping where none
  is safe.
- No image-classification set treated as a bbox source; no license assumed from a
  hosting page.
- No acquisition, candidate modification, P4.3.6 merge, release, or commit.

---

## Section 3 — Authoritative baseline

- **Taxonomy** (`load_taxonomy()`, v1.0.0, ids 0–18): laptop·0, smartphone·1,
  tablet·2, desktop·3, server·4, monitor·5, crt_monitor·6, television·7,
  printer·8, keyboard·9, mouse·10, router·11, power_supply·12, cable·13, camera·14,
  game_console·15, smartwatch·16, headphones·17, battery·18.
- **Represented in the P4.3.5 candidate (252 img / 358 box / INCOMPLETE):**
  smartphone·1, tablet·2, monitor·5, printer·8. *(A prior note listed these as ids
  0/1/2/5; the correct canonical ids are 1/2/5/8.)*
- **Authoritative gate** (`scripts/audit_dataset_readiness.py`): coverage (all 19
  present + `annotation_completeness == 1.0` + no unlabelled images) and split
  (70/20/10 seed-42, no leakage, every class in each split). **No encoded minimum
  count.**

---

## Section 4 — Taxonomy semantics for the 9 missing classes

Definitions from `components/data/components.yaml` aliases (surfaced in
`device_detection_sources.md §2`) and the plan CSV's `notes`. For each: what the
box **is**, and the neighbours it must **not** absorb.

| ID | Class | Include (positive) | Exclude (must NOT be boxed as this) |
| --- | --- | --- | --- |
| 3 | desktop | Tower cases, all-in-one desktop chassis, workstation towers (the *computer unit*) | The attached **monitor** (5); **laptop** (0); **server** rack (4) |
| 4 | server | Rack-mount / blade / tower **servers**, single-unit chassis; datacenter racks | **desktop** tower (3); **router** (11); whole-room wide shots with no tight unit box |
| 6 | crt_monitor | **CRT computer monitors** (deep bulky back) | **Flat-panel monitor** (5); **CRT television** (7 — a CRT TV is a TV) |
| 11 | router | Wi-Fi **routers**, modems, gateways (with/without antennas) | **Set-top / TV boxes**; **server** (4); network attached storage |
| 12 | power_supply | Power **adapters/chargers**, laptop **bricks**, ATX **PSUs** | The **cable** itself (13); wall **socket/plug**; **battery**/power-bank (18) |
| 13 | cable | USB / power / HDMI / data **cables, cords, wires** | The **charger brick** (12); the device connector housing |
| 15 | game_console | **Console units** (stationary + handheld consoles) | **Controllers/joysticks/remotes** (unless kept as `difficult`); toys; set-top boxes |
| 16 | smartwatch | **Smartwatches** (screen + band, smart wearables) | **Analog/quartz wristwatches**; non-smart bands with no screen |
| 18 | battery | **Batteries/cells/packs** (AA/AAA, coin, Li-ion packs) | The device it powers; the **charger** (12); (power-banks are borderline → see 12) |

---

## Section 5 — Dangerous false mappings (do NOT use)

The high-risk conflations that would silently corrupt a class or its neighbour —
`REJECT` regardless of license:

| Class (ID) | Trap | Consequence |
| --- | --- | --- |
| desktop (3) | generic "Computer"/"Personal computer" | boxes the **monitor**, not the tower → poisons desktop **and** monitor·5 |
| crt_monitor (6) | "Computer monitor" | can't separate CRT from flat panel → poisons crt_monitor **and** monitor·5 |
| power_supply (12) | "Power plugs and sockets" | a wall socket/plug is **not** a PSU/charger |
| game_console (15) | generic controller/joystick/remote/"toy" | a controller is **not** the console body |
| smartwatch (16) | generic "Watch" | merges **analog + smart** wristwatches |
| battery (18) | generic "battery" web senses | polysemy (artillery/legal/drum) + confusable small object |

Additionally, `server·4`, `router·11`, `cable·13`, `battery·18` have **no boxable
Open Images source at all** — they cannot be topped up from the wired pipeline.

---

## Section 6 — Source families & license reality

Families (from `device_detection_sources.md §3`), with the honest license posture:

- **A. Large detection sets** (Open Images, Objects365, LVIS, COCO): may carry
  boxes, but **image licenses are per-image Flickr terms that VARY** (only the
  *annotations* are typically CC-BY-4.0). Even for the MAPPED classes the plan CSV
  records `images=per-image-Flickr(VARY-verify)`. Relevant category presence + the
  underlying image license must be **verified** — `CONDITIONAL`.
- **B. Community sets** (Roboflow Universe, Kaggle): e-waste-specific framing and
  rarer classes, but **license and provenance vary per dataset** — `CONDITIONAL`.
- **C. Open media** (Wikimedia/Openverse/Flickr-CC): per-image CC, but generally
  **no bounding boxes** → image source needing **manual annotation** —
  `CONDITIONAL`.
- **D. Manufacturer imagery:** copyrighted, training-uncleared — **excluded**
  without a signed license.
- **E. Self-collection:** team-owned, license-clean **by construction**, real
  Indian e-waste context — **`SAFE`**, and the only path needing no external
  verification to start.
- **F. Synthetic:** derived license; **balancing only**, ≤ ~20% per class.

**Binding license test (sources §6):** import only under a license permitting ML
training **and** redistribution; preserve attribution; never relabel restrictive
as permissive; **unclear ⇒ exclude**; provenance mandatory.

---

## Section 7 — Per-class source assessment (summary)

Full rows in `P4_3_7_SOURCE_MAPPING_MATRIX.md §3`. Lead path + best scale-up:

| ID | Class | SAFE lead | CONDITIONAL scale-up (verify) | REJECT trap |
| --- | --- | --- | --- | --- |
| 3 | desktop | self-collect (box tower, not screen) | Objects365/LVIS *(cat?)*, Roboflow | generic "Computer" |
| 4 | server | self-collect (partner ITAD) + synthetic | Roboflow datacenter, Wikimedia+manual | — (no OID source) |
| 6 | crt_monitor | self-collect (e-waste yards) + synthetic | Roboflow retro/e-waste, Wikimedia+manual | "Computer monitor" |
| 11 | router | self-collect (homes/offices) | Roboflow networking, Wikimedia+manual | — (no OID source) |
| 12 | power_supply | self-collect (bricks/PSUs) | Roboflow adapters, Wikimedia+manual | "Power plugs and sockets" |
| 13 | cable | self-collect (bundles) | Roboflow cable, Wikimedia+manual | generic "cable" senses |
| 15 | game_console | self-collect (units) | Roboflow console, Wikimedia+manual | controller/joystick/remote |
| 16 | smartwatch | self-collect | Roboflow smartwatch, Wikimedia+manual | generic "Watch" |
| 18 | battery | self-collect + synthetic | Roboflow battery, Wikimedia+manual | generic "battery" senses |

---

## Section 8 — Prioritisation

Criteria (detailed in `P4_3_7_ACQUISITION_PLAN.md §2`): license-safety,
semantic cleanliness, split-presence risk, physical access/effort/hazard;
coverage impact is equal (+1) across all nine, so it is only a tie-breaker.

**Waves:** (1) router·11, smartwatch·16 — easy, clean, license-safe; (2)
desktop·3, power_supply·12 — common but confusion-prone; (3) cable·13, battery·18
— abundant but hard/hazardous to annotate; (4) server·4, crt_monitor·6,
game_console·15 — scarce/access-limited. Rationale: build the new-source QA loop
on the safest class first, defer the scarce/hazardous tier.

---

## Section 9 — Split-gate constraint & depth guidance

Every added class must satisfy `_split_gate` (70/20/10, seed 42, global shuffle):
**no leakage**, no near-duplicate of one physical item across splits (dedup Hamming
≤ 5 against the protected candidate **and** within the new batch), and
**per-split presence** (in train, val **and** test).

**Depth (engineering guidance, not a gate, not 150):** per-split presence is
emergent from a global shuffle. In this repo, ~20 samples **failed** the test
slice (P4.3.6 `laptop`), while a 5-sample class landing in all three was a
**seed accident, not a floor**. Target enough accepted, deduped samples that the
~10% test slice expects ≥1 with margin — comfortably **above the ~20 that
failed** (order of a few tens) — then validate **empirically** against
`_split_gate`. If a class misses a slice, collect more of that class; never reseed
or change the ratios.

---

## Section 10 — Protected-state verification (read-only)

Captured this session:

```
$ git rev-parse --short HEAD
b4604f9

$ git diff --stat
(empty — no tracked modifications)

$ git status --short
?? dataset_acquisition/review/p4_3_4_multiclass_qa_v1/automated_acceptance_log.json
?? dataset_acquisition/review/p4_3_4_multiclass_qa_v1/human_review_log.jsonl
?? dataset_acquisition/review/p4_3_4_multiclass_qa_v1/signoff_template.backup_20260811_225544.json
?? dataset_acquisition/review/p4_3_4_multiclass_qa_v1/signoff_template.before_auto_accept.json
?? dataset_acquisition/review/p4_3_7_source_expansion/
?? dataset_acquisition/review/tmp_duplicate_review_p435/
?? scripts/_build_p435_labels.py
?? scripts/auto_accept_multiclass_qa_p434.py
?? scripts/review_multiclass_qa_p434.py
?? tmp_settings.py
?? tmp_splitter.py
```

| Protected item | Expected | Verified |
| --- | --- | --- |
| HEAD | `b4604f9` | ✅ |
| Tracked modifications | none | ✅ empty `diff --stat` |
| P4.3.5 candidate | 252 img / 358 box / INCOMPLETE | ✅ not touched |
| P4.3.6 expansion | 119 `QA_PENDING`, unmerged | ✅ not merged, not modified |
| Merge / release / commit | none | ✅ none |

The only new entry vs session start is the untracked
`dataset_acquisition/review/p4_3_7_source_expansion/` (this sprint's three
research docs + the Task-1 recovery report). All other untracked files pre-existed
and are not mine. **Nothing was committed.**

---

## Section 11 — Recommendation: acquire `router` (ID 11) first

**Why router:**

1. **License-safety / reproducibility (highest):** routers are ubiquitous, so
   **self-collection** yields a license-clean batch **immediately**, with **no
   external-license verification needed to start** — the only `SAFE` path this
   session can guarantee.
2. **Semantic cleanliness:** a router/modem/gateway is visually distinct; its only
   external trap is a `REJECT` label, so leading with self-collection avoids
   ambiguity entirely (guideline: exclude set-top boxes).
3. **Split-presence & effort:** compact, single-object framing is **easy to box**
   (unlike cable·13) and **non-hazardous** (unlike battery·18, crt_monitor·6),
   making it straightforward to gather enough for reliable per-split presence.
4. **Access:** far easier to source than server·4, crt_monitor·6, or
   game_console·15.
5. **Process value:** it lets the team validate the **entire new-source →
   provenance → Gate A/B → dedup → split-presence** loop on an *easy, safe* class
   before committing effort to the scarce/hazardous tier.

**Immediate next steps (when a separate acquisition sprint is approved):**
self-collect router images (Indian context) → import via `ProvenanceCollector` →
Gate A/B → dedup vs the protected candidate → confirm `_split_gate` per-split
presence. In parallel, run the §4 verification gate on any candidate Roboflow
networking dataset to decide whether it can safely scale depth.

---

## Section 12 — Non-actions, risks, and next steps

**Non-actions (honoured):** no acquisition, no candidate change, no P4.3.6 merge,
no release, no commit, no "150"/"29-gap", no threshold/seed weakening.

**Risks:**

- **External verification debt** — every `CONDITIONAL` source still needs live
  license/bbox/count checks; until then only self-collection is actionable.
- **Under-served tier** (server, crt_monitor, power_supply, cable, game_console,
  battery) remains the schedule risk (sources §5); expect heavy self-collection +
  synthetic.
- **Coverage is necessary but not sufficient** — even at 19/19 present, the split
  gate must still pass per class, and manual sign-off (freeze policy §4) remains.

**Next steps:** (1) approve an acquisition sprint starting with `router`; (2)
run §4 verification on shortlisted community datasets; (3) re-audit after each
class to confirm coverage + `_split_gate`; (4) decide the P4.3.6 merge separately.

> Companion docs: `P4_3_7_SOURCE_MAPPING_MATRIX.md`,
> `P4_3_7_ACQUISITION_PLAN.md`, `P4_3_7_SPLIT_GATE_RECOVERY.md`;
> policy: `docs/ai/device_detection_sources.md`,
> `docs/ai/device_collection_checklist.md`,
> `docs/ai/dataset_v1_freeze_policy.md`.
