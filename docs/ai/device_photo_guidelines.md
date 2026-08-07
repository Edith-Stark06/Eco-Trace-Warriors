# Device Photo Guidelines — Dataset v1.0

**Sprint:** P4.1.5 — Production Dataset Collection Workflow (PART 2)
**Component:** Device Intelligence Engine (DIE) — YOLO Detector (milestone M1.4)
**Status:** Active
**Scope:** The **photo quality standard** every collected image is held to. It
tells a contributor how to frame, light, and vary a shot, and it defines exactly
what is **acceptable** and what is **rejected**. It downloads nothing, trains
nothing, and changes no code or interface.

---

## 1. Purpose

A detector generalises only as far as its images vary. This guide makes that
variation deliberate: enough diversity to be robust, enough discipline to stay
labellable. It is the standard behind the contributor self-check in
`device_collection_workflow.md` §5 and the pipeline's Gate A
(`ImageValidator`).

> **Thresholds are code-owned.** Every numeric limit below mirrors
> `configs/settings.py`. If code and this doc disagree, code wins — re-read
> `settings.py` and update this file.

| Property | Limit (from `settings.py`) | Contributor aim |
| --- | --- | --- |
| Short side (min dim) | `≥ 32 px` (hard floor) | `≥ 640 px` |
| Long side (max dim) | `≤ 12000 px` | ≤ 4000 px |
| File size | `≤ 10 MiB` (10 × 1024 × 1024) | 0.5–5 MiB |
| Format | `.jpg / .jpeg / .png / .webp` | `.jpg` |
| Focus (blur) | variance-of-Laplacian `≥ 100.0` | sharp, tap-to-focus |
| Exposure (mean luminance) | in `[40, 220]` | ~90–170 |
| Duplicates | Hamming distance `> 5` from any kept image | visibly distinct |

---

## 2. Camera Angles

Capture each device from a **spread** of viewpoints — never a single canonical
pose. Across a class's images, cover:

- **Front / straight-on** — the label-view a user expects.
- **Three-quarter** (~45°) — the most informative single angle; prioritise it.
- **Top-down** — for flat devices (`keyboard`, `laptop` open, `tablet`,
  `smartphone`, `router`, `mouse`, `battery`).
- **Side / profile** — shows thickness and ports (`laptop`, `monitor`,
  `crt_monitor`, `television`, `game_console`).
- **Rear** — ports, vents, labels (`desktop`, `server`, `power_supply`,
  `printer`, `router`).
- **Low / high** — occasional off-axis shots for robustness.

Rough mix per class: ~40% three-quarter, ~25% front, ~20% top/side, ~15% rear or
off-axis. Rotate the device, not just the camera, so lighting and background
change too.

---

## 3. Lighting

Aim for even, natural light where the device is clearly readable.

- **Preferred:** diffuse daylight or soft indoor light; device evenly lit.
- **Include on purpose (robustness):** some warm/cool casts, mild shadows,
  directional light, mixed indoor/outdoor.
- **Keep mean luminance in `[40, 220]`.** Near-black (`< 40`) and blown-out
  (`> 220`) frames fail Gate A.
- **Avoid:** harsh single-point flash causing hotspots, heavy backlight that
  silhouettes the device, deep shadow hiding the target.

A small share of dim or high-contrast shots is fine **if the device stays
identifiable** — flag them `difficult` rather than discarding.

---

## 4. Distance & Framing

- The target device should fill roughly **50–90%** of the frame — large enough to
  read detail, with a margin so the whole object is inside the frame.
- **Do not crop** the device at the edges unless the shot is a deliberate
  partial/occluded example.
- Vary distance across a class: some tight detail shots, some with context.
- Keep tiny parts (a `cable`, a `battery`) at least **8 × 8 px** in the frame;
  below that they cannot be annotated reliably. Prefer them much larger.
- Avoid extreme wide shots where the device is a speck — those add background,
  not signal.

---

## 5. Background

- **Vary the background** across a class — plain desk, cluttered bench, floor,
  shelf, outdoor surface. A model trained on one background overfits to it.
- **Include realistic e-waste context:** devices among cables, on repair benches,
  in bins/piles — this matches deployment conditions.
- Avoid backgrounds that camouflage the device (black laptop on a black desk)
  unless deliberately flagged `difficult`.
- Keep any other in-taxonomy devices in the background **honest** — they will be
  annotated too (see §7).

---

## 6. Occlusions

- **Some occlusion is desirable** — devices partially behind others, in bags,
  under cables, hand-held. It teaches robustness.
- **Annotatability rule:** keep an occluded instance only if **≥ 40% of the
  device is visible** and its class is still unambiguous. Below that, drop it or
  flag `difficult`.
- Label the **full extent** of a partially-occluded device at annotation time
  (the box covers the whole device, including the hidden part's expected extent),
  per the acquisition runbook's annotation guidelines.
- Do not stage impossible occlusions (e.g. only a corner visible) as normal
  images — they inflate label noise.

---

## 7. Multiple Objects

- Multi-device scenes are **encouraged** — they mirror real e-waste piles and
  raise labels-per-image.
- **Every** in-taxonomy device in the frame that meets the visibility rule (§6)
  **must be annotated** — no unlabelled positives, or the model learns to
  suppress real detections.
- The **filename names one primary class** (§6 of the workflow doc); the extra
  devices are captured in the annotation labels, not the filename.
- Keep scenes labellable: a dozen overlapping tiny devices is not worth the label
  effort — prefer 2–5 clearly separable devices per multi-object shot.

---

## 8. Acceptable Quality — checklist

An image is **acceptable** when all hold:

- [ ] Target device clearly identifiable and in-taxonomy.
- [ ] Short side `≥ 32 px` (aim `≥ 640 px`); long side `≤ 12000 px`.
- [ ] File `≤ 10 MiB`; format `.jpg/.jpeg/.png/.webp`.
- [ ] In focus (variance-of-Laplacian `≥ 100.0`).
- [ ] Exposure mean luminance in `[40, 220]`.
- [ ] Not a near-duplicate (perceptual-hash Hamming `> 5`) of a kept image.
- [ ] Every visible in-taxonomy device is annotatable (`≥ 40%` visible).
- [ ] No un-cleared sensitive data (serials, faces, account screens).

### Acceptable examples
- Three-quarter shot of a laptop on a cluttered bench, sharp, daylight.
- Top-down of a keyboard + mouse + cable, all clearly separable.
- Rear of a desktop tower showing ports, mild shadow, `difficult`-flagged.

---

## 9. Rejected Quality — checklist

An image is **rejected at source** when any hold:

- [ ] Device unidentifiable or out-of-taxonomy.
- [ ] Short side `< 32 px`, or file `> 10 MiB`, or unsupported format.
- [ ] Motion/soft blur below the focus threshold and **not** a deliberate
      `difficult` sample.
- [ ] Near-black (`< 40`) or blown-out (`> 220`) so the device is unreadable.
- [ ] Exact/near duplicate of an already-kept image.
- [ ] Primary device cropped so heavily its class is ambiguous (`< 40%` visible).
- [ ] Contains un-cleared personal/sensitive data.
- [ ] Watermarks, heavy filters, or synthetic overlays that misrepresent the
      device.

### Rejected examples
- Blurry phone snapshot where the model name is unreadable.
- A laptop 20 px wide in a wide room shot.
- Screenshot of a product page (licence + realism both fail).
- A device photo showing a legible serial number with no consent.

---

## 10. Related Documents

| Document | Role |
| --- | --- |
| `docs/ai/device_collection_workflow.md` | Phases, contributor path, naming, upload (PART 1) |
| `docs/ai/dataset_review_workflow.md` | Review/approval/rejection (PART 4) |
| `docs/ai/dataset_readiness_checklist.md` | v1.0 readiness gate (PART 5) |
| `docs/engineering/device_dataset_acquisition.md` | Gate A/B thresholds, annotation guidelines |
| `configs/settings.py` | Source of every numeric threshold above |

> **Out of scope for P4.1.5:** no training, YOLO, OpenCLIP, OCR, or model/dataset
> downloads. This guide governs image quality only.
