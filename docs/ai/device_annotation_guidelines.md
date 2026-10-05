# Device Annotation Guidelines — Dataset v1.0

**Sprint:** P4.1.6 — Dataset Annotation & Quality Assurance Framework (PART 1)
**Component:** Device Intelligence Engine (DIE) — YOLO Detector (milestone M1.4)
**Status:** Active
**Scope:** The **bounding-box labeling standard** every annotator applies before
YOLO training. It tells an annotator exactly how to draw, class, and flag every
box so the labels are consistent across people and batches. It downloads
nothing, trains nothing, and changes no code or interface.

---

## 1. Purpose

Collection produces validated images (`device_photo_guidelines.md`, Gate A);
annotation turns them into YOLO labels. A detector is only as consistent as its
labels, so this document removes the per-annotator judgement calls: two people
labelling the same image should produce the same boxes, classes, and flags.

It **expands** the labeling standards already fixed in
`docs/engineering/device_detection_annotation.md` §5.3 and
`docs/engineering/device_dataset_acquisition.md` §4 — it does not contradict
them. Where a numeric limit appears, it is **code-owned** and mirrors
`configs/settings.py`; if code and this doc disagree, code wins.

> **Taxonomy is code-owned.** The 19 classes and their IDs (0 = `laptop` …
> 18 = `battery`) come from `components/data/components.yaml` via
> `dataset/taxonomy.py::load_taxonomy()`. Never invent, rename, or reorder a
> class. Confirm the list from code before labelling:
> `python -c "from device_ai.dataset.taxonomy import load_taxonomy as t; print(list(enumerate(t().class_names)))"`.

---

## 2. The Label Contract (recap)

The on-disk contract is unchanged from P4.1.2 and is enforced by
`AnnotationValidator`:

- One YOLO `.txt` per image, **same stem**, in `datasets/labels/`.
- Each line is `class_id cx cy w h`.
- `class_id` — integer `0–18` in taxonomy order.
- `cx cy w h` — box centre and size, **normalised to `[0, 1]`**; `w, h > 0`.
- An **empty** `.txt` is valid and means "true negative — no in-taxonomy device"
  (§10). A **missing** `.txt` means "not yet annotated" — never leave one
  missing for a retained image.

The 19 classes, in ID order:

| ID | Class | ID | Class | ID | Class |
| ---: | --- | ---: | --- | ---: | --- |
| 0 | `laptop` | 7 | `television` | 14 | `camera` |
| 1 | `smartphone` | 8 | `printer` | 15 | `game_console` |
| 2 | `tablet` | 9 | `keyboard` | 16 | `smartwatch` |
| 3 | `desktop` | 10 | `mouse` | 17 | `headphones` |
| 4 | `server` | 11 | `router` | 18 | `battery` |
| 5 | `monitor` | 12 | `power_supply` | | |
| 6 | `crt_monitor` | 13 | `cable` | | |

> This table is a **reading aid**, not a second source of truth. If it ever
> disagrees with `load_taxonomy()`, the code is correct and this table is a bug.

---

## 3. YOLO Bounding-Box Standards

Every box follows the same construction rules regardless of class.

- **One box per visible instance.** Never merge two devices of the same class
  (two laptops in a pile → two boxes), and never split one device into parts
  (a laptop's screen + base is **one** `laptop` box).
- **Axis-aligned only.** YOLO boxes are upright rectangles; there is no rotation
  field. For a tilted device, draw the tightest upright box that contains its
  visible extent.
- **Include integral, attached parts; exclude detached accessories.** A laptop's
  hinge and screen are part of the `laptop`; a charger lying next to it is a
  separate `power_supply` box, and a mouse beside it is a separate `mouse` box.
- **Normalised coordinates.** `cx, cy` are the box centre and `w, h` its size,
  each divided by the image width/height into `[0, 1]`. The annotation tool
  emits these; never hand-edit them into an unnormalised range.
- **Never exceed the frame.** A box is clamped to `[0, 1]`; a coordinate outside
  that range is a `COORD_OUT_OF_RANGE` error in `AnnotationValidator`.
- **Positive area.** `w > 0` and `h > 0` always; a zero-area box is a
  `NON_POSITIVE_SIZE` error.

---

## 4. Tight Bounding Boxes

The box **hugs the visible extent** of the device — no slack, no clipping.

- The four edges each touch the outermost visible pixel of the device on that
  side. A margin of background inside the box teaches the model to include
  background; clipping the device teaches it to cut off real objects.
- **Aim for ≤ ~2–3 px of slack** on each edge at full resolution. Consistency
  matters more than any exact pixel count — draw every box the same way.
- Include thin protrusions that are part of the device (a router's antenna, a
  laptop's open lid) inside the box; they define the true extent.
- Do **not** pad the box to a "nice" square. A `cable` is long and thin; its box
  is long and thin.
- Systematic looseness or tightness is a review-catchable defect
  (`bounding_box_stats` in `AnnotationStatisticsCalculator` surfaces boxes that
  are implausibly large or small for their class).

---

## 5. Partial Visibility

A device is *partially visible* when another object hides part of it but it is
not cut by the image border (border cases are **truncation**, §6).

- **Label it when ≥ ~40% of the device is visible** and its class is still
  unambiguous. This mirrors the collection visibility rule
  (`device_photo_guidelines.md` §6).
- **Box only the pixels you can see.** Do not extrapolate the box over the hidden
  part — YOLO learns from what is in the box, and a box drawn over background the
  model cannot see is label noise.
- Below ~40% visible, or when the class is no longer certain, **skip the
  instance** (it becomes background) — do not guess.

> **Consistency note.** §5 (partial visibility) and §7 (occlusion) share the same
> "box the visible extent, ≥ ~40% to label" rule. The difference from the older
> acquisition runbook wording is deliberate and stated in §7.

---

## 6. Truncation (frame edge)

A device is *truncated* when the **image border** cuts it off.

- **Label a truncated device** if ≥ ~40% of its body is in-frame; box only the
  in-frame portion.
- The box edge that meets the image border sits **on** the border
  (coordinate `0.0` or `1.0`), never past it.
- If < ~40% of the device is in-frame, skip it — a sliver at the edge is not
  reliably classifiable and adds noise.
- Truncation and occlusion can co-occur (a device both behind another object and
  running off-frame); apply both rules — box the visible, in-frame pixels only.

---

## 7. Occlusion

*Occlusion* is when another object in the scene covers part of the target device.

- **Visibility threshold:** label an occluded device when **≥ ~40% is visible**;
  box the **visible extent only**.
- **Do not guess the hidden part.** Earlier collection wording
  (`device_photo_guidelines.md` §6) spoke of "the box covers the whole device,
  including the hidden part's expected extent". For **v1.0 labelling the
  authoritative rule is the acquisition runbook's**
  (`device_dataset_acquisition.md` §4.1): **box the visible extent, do not
  extrapolate.** Annotate to the runbook rule; the guideline's intent (label the
  device even when occluded) is preserved, only the box's reach changes.
- **Overlapping devices get separate boxes** — see §8.
- Flag heavy-but-labelled occlusion with `occluded` in the annotation tracking
  (§13) so QA can sample it separately.

---

## 8. Overlapping Devices

When two or more in-taxonomy devices overlap or touch:

- **Draw a separate, tight box for each device** — never one merged box around
  the group. Two phones stacked on a desk are two `smartphone` boxes.
- **Boxes may overlap.** YOLO fully supports overlapping boxes; the correct
  labelling of a mouse resting on a laptop is a `mouse` box and a `laptop` box
  that overlap, each tight to its own device.
- **Occlusion between the two** is resolved per §7: each device is boxed to its
  own visible extent, and either may fall below the ~40% rule independently.
- Do not let one device's box "borrow" area from the other — each box hugs only
  its own device's pixels.

---

## 9. Multiple Instances

Scenes with many devices (e-waste piles, repair benches) are **encouraged** —
they raise labels-per-image and match deployment.

- **One box per distinguishable instance**, even for many of the same class
  (a bin of 20 phones → up to 20 `smartphone` boxes, as far as individuals are
  separable).
- **Label every in-taxonomy device** that meets the visibility rule (§5/§7).
  An unlabelled visible positive teaches the model to suppress real detections —
  the single most damaging annotation error.
- **Mixed-class scenes are valuable** (laptop + power_supply + mouse): they teach
  co-occurrence. Label each class present.
- **Dense, individually-indistinguishable piles:** box the clearly separable
  units at the front, leave the ambiguous mass **unboxed**, and flag the image
  `difficult` (§11). Do not draw guesswork boxes into a blur of devices.
- The **filename names one primary class** only
  (`device_collection_workflow.md` §6); the extra devices live in the labels, not
  the filename.

---

## 10. Tiny Objects

Small classes (`mouse`, `battery`, `cable`, earbuds under `headphones`) are in
scope even when small in the frame.

- A box must be **≥ 8×8 px** and the device visually identifiable at that size.
- Below 8×8 px, **skip the instance** — it adds label noise. Prefer a **closer
  capture** of the tiny class over boxing an unidentifiable speck.
- Keep the box tight even when tiny; a 10-px `battery` still gets an ~10-px box,
  not a padded 40-px one.

---

## 11. Difficult Examples

Motion-blurred, low-light, reflective-screen, heavily-cluttered, or strongly
occluded images are **kept** when the target device is still confidently
identifiable — they improve robustness.

- Label them normally (tight boxes, correct class) and **flag the image
  `difficult`** in `annotation_progress.csv` / `image_inventory.csv` so QA can
  sample them separately and so a "clean-only" evaluation slice can be
  reconstructed.
- If the target device is **not** confidently identifiable, **exclude the image**
  and log the reason — never guess a class to avoid a blank.
- A `difficult` flag is a signal for extra QA attention, **not** a lower bar for
  box quality: boxes on `difficult` images meet the same tightness and class
  rules.

---

## 12. Ignored Objects

Some things in a frame are **deliberately not boxed**. Being explicit prevents an
annotator from treating an omission as a mistake.

- **Out-of-taxonomy objects** — anything not one of the 19 classes (furniture,
  people, tools, packaging, food) is **never boxed**. It is background.
- **Sub-~40%-visible or sub-8×8-px instances** — skipped per §5–§7 and §10; they
  are background, not labels.
- **The ambiguous mass in a dense pile** — left unboxed per §9, image flagged
  `difficult`.
- **Reflections, screen images, printed pictures of devices** — a photo *of* a
  laptop on a monitor is not a `laptop`; do not box the depicted device. Box the
  physical `monitor` if the monitor itself is the in-taxonomy device.
- These skipped regions become **background** for the detector — that is correct
  and intended, not an annotation gap. `AnnotationValidator` does not flag them;
  only genuinely missing label **files** are gaps.

---

## 13. Negative Images (true negatives)

A *negative image* contains **no in-taxonomy device**.

- It gets an **empty** `.txt` label file (same stem, zero lines) — **not** a
  missing file. This is how the pipeline distinguishes "no devices here" from
  "not yet annotated" (`annotation_completeness`).
- Flag the image `negative` in tracking (§14).
- **Target ~5–10% negatives** across the dataset
  (`device_dataset_acquisition.md` §4.7): plain backgrounds, non-electronic
  clutter, and — most valuable — **hard negatives** (a book resembling a
  `tablet`, a lunchbox resembling a `game_console`, a black rectangle resembling
  a `monitor`).
- Hard negatives are the highest-value negatives; prioritise them for classes
  prone to false positives (`tablet`, `monitor`/`television`, `battery`).

---

## 14. Labeling Consistency

Consistency across annotators and batches is the property this document exists to
guarantee. It is what §11 review and the QA metrics
(`quality_assurance.md`) measure.

- **Same taxonomy, always.** Resolve class from `components.yaml` and its
  **alias hints** (e.g. `charger → power_supply`, `tv → television`,
  `crt → crt_monitor`). Never invent a class; when genuinely unclassifiable,
  exclude the image and log it.
- **Resolve the common confusions the same way every time:**
  - `monitor` vs `television` — a `television` has an integrated tuner/stand and
    is typically larger; a `monitor` is a computer display. Use the alias hints
    and size cues.
  - `tablet` vs `smartphone` — resolve by physical size; a large-screen slate is
    a `tablet`, a hand-sized handset is a `smartphone`.
  - `power_supply` vs `cable` — a brick/adapter body is `power_supply`; a bare
    lead with no converter body is `cable`.
- **Same box style, always.** Tight to the visible extent (§4), one box per
  instance (§3), visible extent only under occlusion/truncation (§6–§7).
- **Same flags, always.** `difficult` / `occluded` / `multi_object` / `negative`
  applied by the same rules (§11, §13) so QA sampling is comparable across
  batches.
- **When unsure, escalate — do not improvise.** An unresolved class or box
  question goes to the reviewer / QA lead per `annotation_review_manual.md`,
  and the resolution is recorded so the next annotator applies it identically.

---

## 15. Quick Annotator Checklist

Before submitting a batch, confirm for **every** image:

- [ ] Every in-taxonomy device ≥ ~40% visible and ≥ 8×8 px has exactly one tight
      box (§3–§10).
- [ ] No merged boxes, no split boxes, no boxes over hidden/extrapolated pixels.
- [ ] Every class id is `0–18` and matches the canonical taxonomy (§2).
- [ ] Coordinates normalised `[0, 1]`; `w, h > 0`; nothing past the frame edge.
- [ ] Out-of-taxonomy / too-small / too-occluded objects left **unboxed** (§12).
- [ ] Negative images have an **empty** `.txt`, not a missing file (§13).
- [ ] `difficult` / `occluded` / `multi_object` / `negative` flags set per §11/§13.
- [ ] `AnnotationValidator` run locally and clean (annotator self-check).

---

## 16. Related Documents

| Document | Role |
| --- | --- |
| `docs/ai/annotation_review_manual.md` | Review roles, conflict resolution, escalation (PART 2) |
| `docs/ai/quality_assurance.md` | Measurable QA metrics + thresholds (PART 3) |
| `docs/ai/device_photo_guidelines.md` | Image quality standard feeding annotation (P4.1.5) |
| `docs/ai/dataset_review_workflow.md` | Two-stage human review (P4.1.5) |
| `docs/engineering/device_detection_annotation.md` | Label contract + tooling (P4.1.2) |
| `docs/engineering/device_dataset_acquisition.md` | Authoritative annotation rules §4 (P4.1.4) |
| `components/data/components.yaml` | Canonical 19-class taxonomy (code-owned) |

> **Out of scope for P4.1.6:** no training, YOLO execution, model evaluation,
> OpenCLIP, OCR, or model/dataset downloads. This document governs how boxes are
> drawn, not how a model is trained.



