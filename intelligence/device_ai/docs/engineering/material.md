# Material Intelligence Engine (M1.10)

> The third **downstream consumer** of the Device Intelligence Engine: an
> internal-only, **deterministic inference engine** that turns the immutable
> `DeviceContext` produced by the **fusion engine** (M1.7), the
> `RecoverabilityReport` produced by the **recoverability engine** (M1.8) and the
> `ComponentReport` produced by the **component engine** (M1.9) into an
> explainable **`MaterialReport`** — the recoverable and hazardous materials the
> device is made of, each with an **estimated mass** and **confidence** plus the
> **source components** it was derived from, and device-level **recoverable /
> hazardous weight** totals with ordered human-readable reasoning and warnings.
> Like the component engine, its knowledge lives in an **external, versioned
> YAML/JSON catalogue** so the material library is data, not logic. It ships **no
> new endpoint** and leaves the `/predict` API contract **unchanged and
> backward-compatible**.

**Module:** `intelligence/device_ai`
**Milestone:** M1.10 — Material Intelligence Engine
**Status:** implemented; internal-only (no router, no HTTP surface)

---

## Table of contents

1. [Scope](#scope)
2. [Architecture](#architecture)
3. [Domain models](#domain-models)
4. [The external material catalogue](#the-external-material-catalogue)
5. [Profile library & loader](#profile-library--loader)
6. [Inference engine](#inference-engine)
7. [Mass & confidence](#mass--confidence)
8. [Overall confidence](#overall-confidence)
9. [Configuration](#configuration)
10. [Testing](#testing)
11. [Integration guide](#integration-guide)
12. [Worked examples](#worked-examples)
13. [Backward compatibility](#backward-compatibility)
14. [Design rationale](#design-rationale)

---

## Scope

M1.10 is the **third** engine to consume the fusion engine's output, and the
first to consume the component engine's. Fusion (M1.7) produces an immutable
`DeviceContext`; recoverability (M1.8) turns that into a `RecoverabilityReport`;
the component engine (M1.9) infers a `ComponentReport`; the material engine
answers the next question: *"given the components this device is likely to
contain and how recoverable it is, which materials — and how much of each — can
be recovered from it, and which need hazardous handling?"* Every material the
engine lists is derived from **four deterministic signals**, never from learned
models:

| # | Signal | Source | Effect on the report |
|---|---|---|---|
| 1 | **Device-type profile** | external `materials.yaml` catalogue | Seeds the candidate material list and each material's **nominal mass** (grams) and recovery/hazard flags. |
| 2 | **Component inventory** | `components.components` (the M1.9 `ComponentReport`) | A material is **listed only when at least one of its `source_components` is present**; the strongest present source's **presence confidence** scales the material's own confidence. |
| 3 | **Recoverability confidence & hazard** | `recoverability.confidence` / `.hazard_level` | The recoverability confidence is **blended** into the overall confidence; a concrete assessed hazard raises an operator warning. |
| 4 | **Fusion confidence & conflicts** | `context.confidence` / `.has_conflicts` + profile familiarity | Blended with the recoverability confidence into the **overall** confidence, then damped for an unrecognized device type and for fusion conflicts. |

**Explicitly in scope**

- `MaterialReport` — the normalized, immutable material breakdown with per-material
  mass/confidence/source-components and device-level recoverable/hazardous weight
  totals.
- An **external, versioned** material-profile catalogue (YAML/JSON) with a strict
  loader that validates aggressively and fails with a typed error.
- A pure `MaterialInferenceEngine` fold (catalogue nominal mass → source-component
  gating → presence-scaled confidence → min-confidence floor; blended/damped
  overall confidence; recoverable/hazardous weight sums).
- An injected `MaterialService` orchestration facade.

**Explicitly out of scope** (do **not** implement in M1.10): Carbon Intelligence,
blockchain anchoring, the Digital Device Passport and market-value estimation.
The engine is **internal only** — no router is mounted, `application.py` is
untouched, and the `/predict` response schema is **unchanged**.

**Key input constraint.** The material engine consumes only the **public
surfaces** of the three upstream reports: `context.confidence` /
`.has_conflicts` / `.device_type` / `.eco_id`, `recoverability.confidence` /
`.hazard_level` / `.recommended_action`, and the `components.components`
inventory. It never re-derives a material list from raw images, models or
identity fields — the device-type catalogue and those signals **only**.

## Architecture

The engine is a **pure domain layer** with the same shape as `fusion/`,
`recoverability/` and `components/`: frozen slotted dataclasses, stateless
engines, and an injected service. It imports the fusion `DeviceContext`, the
recoverability `RecoverabilityReport`, the component `ComponentReport` and the
settings `Settings` **only under `TYPE_CHECKING`**, so there is no runtime
coupling and no import cycle — all three upstream reports are passed in, never
reached into past their public surface. The two runtime dependencies it does take
are the `HazardLevel` enum (to phrase the hazard warning) and the
`ComponentCategory` enum (the vocabulary the catalogue's `source_components` are
validated against — the cross-engine link).

```
       fusion engine (M1.7) ─► DeviceContext ───────────┐
                                                         │
   recoverability engine (M1.8) ─► RecoverabilityReport ─┤
                                                         │
        component engine (M1.9) ─► ComponentReport ──────┤
                                                         │
          ┌──────────── materials/ (internal) ──────────▼──────────────┐
          │  service.py  MaterialService.analyze(ctx, recov, comps)     │
          │        │            │              │                        │
          │        ▼            ▼              ▼                        │
          │  profiles.py    inference.py   config.py                   │
          │  load_library   MaterialInfer  MaterialConfig              │
          │  profile_for    enceEngine     (weights + locator)         │
          │  (external      (nominal mass +                            │
          │   YAML/JSON,    source-gated presence                      │
          │   validated)    confidence, clamp,                         │
          │                 min-confidence floor,                      │
          │                 blended/damped overall,                    │
          │                 recoverable/hazardous sums)                │
          │        └────────────┬─────────────┘                        │
          │                     ▼                                      │
          │      models.py  MaterialReport (frozen)                    │
          │      MaterialCategory · RecoveredMaterial                  │
          └────────────────────────────────────────────────────────────┘
                                ▼
       downstream AI (M1.11+ carbon/passport/market-value) — never /predict
```

Layering (dependencies point downward, never upward):

```
fusion/ · recoverability/ · components/   (M1.7–M1.9 — produce the immutable inputs)
   ↓  (TYPE_CHECKING only; all three reports are passed in)
materials/  (models.py + profiles.py + config.py + inference.py + service.py)
   ↓
exceptions · configs   (cross-cutting foundations)
```

The package contains **no HTTP imports, no FastAPI, and its only I/O is reading
the catalogue file once at service construction.** After that, `analyze()` is a
pure function of its inputs except for the injected clock (which defaults to UTC
`now` and can be replaced or disabled for determinism).

## Domain models

`materials/models.py` defines the vocabulary that makes a breakdown auditable.

### `MaterialCategory`

```python
class MaterialCategory(str, Enum):
    FERROUS_METAL = "ferrous_metal"
    NON_FERROUS_METAL = "non_ferrous_metal"
    PRECIOUS_METAL = "precious_metal"
    CRITICAL_MATERIAL = "critical_material"
    RARE_EARTH = "rare_earth"
    PLASTIC = "plastic"
    GLASS = "glass"
    CERAMIC = "ceramic"
    BATTERY_MATERIAL = "battery_material"
    HAZARDOUS = "hazardous"
    OTHER = "other"
```

A `str` enum so members serialize directly to their wire value **and** can be
constructed from a catalogue string (`MaterialCategory("precious_metal")`). This
enum is the **single source of truth** the external catalogue is validated
against on load — a catalogue entry naming a category outside this set is
rejected. `MaterialCategory.values()` returns every wire value in declaration
order (used in the loader's error messages).

### `RecoveredMaterial`

One material the engine estimates is recoverable from the device:

```python
@dataclass(frozen=True, slots=True)
class RecoveredMaterial:
    name: str
    category: MaterialCategory
    mass_g: float                       # catalogue nominal, never scaled
    confidence: float                   # in [0, 1]
    recoverable: bool
    hazardous: bool
    source_components: tuple[str, ...]  # present ComponentCategory wire values
    reason: str                         # how the estimate was derived

    def to_dict(self) -> dict[str, object]: ...
```

`source_components` holds the component-category wire values that were **actually
present** in the consumed `ComponentReport` and drove this material's inclusion
(empty for unconditional structural materials).

### `MaterialReport`

The normalized, immutable breakdown produced by the service:

```python
@dataclass(frozen=True, slots=True)
class MaterialReport:
    device_type: str
    materials: tuple[RecoveredMaterial, ...]   # catalogue order
    total_mass_g: float
    recoverable_mass_g: float                  # Σ mass of recoverable materials
    hazardous_mass_g: float                    # Σ mass of hazardous materials
    overall_confidence: float                  # in [0, 1]
    reasoning: tuple[str, ...]                   # ordered
    warnings: tuple[str, ...]                    # operator cautions (may be empty)
    eco_id: str = ""                            # carried over from the context
    engine_version: str = ""
    profile_version: str = ""                   # catalogue version
    created_at: datetime | None = None

    @property
    def material_count(self) -> int: ...
    @property
    def recoverable_materials(self) -> tuple[RecoveredMaterial, ...]: ...
    @property
    def hazardous_materials(self) -> tuple[RecoveredMaterial, ...]: ...
    def to_dict(self) -> dict[str, object]: ...
```

Like every domain object, the report is frozen and slotted — attempting to mutate
it raises `FrozenInstanceError`. The `recoverable_materials` /
`hazardous_materials` projections let downstream code partition the breakdown
without re-scanning it. Note that `recoverable_mass_g` and `hazardous_mass_g` are
**independent** partitions of `total_mass_g`, not a two-way split: a material can
be both hazardous *and* recoverable (or neither), so the two sums may overlap and
need not add up to the total.

## The external material catalogue

The material knowledge lives in an **external** file
(`materials/data/materials.yaml` by default), **not** in Python — the same
deliberate choice as the M1.9 component catalogue. The material catalogue is
**data, not logic**, so it can be reviewed, extended or corrected by domain
experts without touching (or redeploying) the engine code. The loader validates
it on read, so a malformed catalogue never silently degrades the engine.

The file has four top-level keys:

```yaml
version: "1.0.0"           # stamped onto every report as profile provenance
aliases:                   # synonym -> canonical device type (mirrors M1.9)
  cell_phone: smartphone
  pc: desktop
  crt: crt_monitor
  # …47 aliases total
unknown:                   # conservative fallback for unrecognized types
  notes: >-
    Unrecognized device type. Only generic structural materials common to most
    electronics are estimated, at low confidence; a human should confirm …
  materials:
    - { name: Mixed plastics (enclosure), category: plastic, mass_g: 150,
        recoverable: true, hazardous: false, source_components: [] }
    - { name: Mixed ferrous metal, category: ferrous_metal, mass_g: 80,
        source_components: [] }
    - { name: Mixed circuit-board material, category: other, mass_g: 40,
        source_components: [] }
profiles:                  # canonical device type -> profile
  laptop:
    notes: Portable computer; battery, mainboard, display, chassis.
    materials:
      - name: Aluminium / magnesium chassis
        category: non_ferrous_metal
        mass_g: 500
        recoverable: true
        hazardous: false
        source_components: []           # structural / unconditional
      - name: Lithium (battery cells)
        category: battery_material
        mass_g: 45
        recoverable: true
        hazardous: true
        source_components: [battery]    # listed only if a battery is present
      # …
```

Each material entry carries: `name`, `category` (a `MaterialCategory` wire
value), `mass_g` (a **non-negative nominal mass in grams**), optional
`recoverable`/`hazardous` flags (default `true`/`false`), a `source_components`
list of **`ComponentCategory` wire values** (from the M1.9 vocabulary — an empty
list marks a structural/unconditional material), and optional `notes`
(provenance, not used in scoring).

The shipped catalogue covers the **same 19 device classes** as the component and
recoverability profile tables — laptop, smartphone, tablet, desktop, server,
monitor, crt_monitor, television, printer, keyboard, mouse, router, power_supply,
cable, camera, game_console, smartwatch, headphones, battery — plus the **same
synonym aliases**, so a device type resolved by one engine resolves identically
in all three. Hazardous materials are deliberately flagged (CRT leaded funnel
glass, barium panel glass and phosphor; battery lithium, cobalt and electrolyte;
solder lead; TV backlight mercury; printer toner), which is what lets the
recoverable/hazardous weight split and the `hazardous_materials` projection carry
real meaning.

## Profile library & loader

`materials/profiles.py` owns the small, strict loader that turns the catalogue
file into validated, immutable value objects.

```python
@dataclass(frozen=True, slots=True)
class MaterialSpec:
    name: str
    category: MaterialCategory
    mass_g: float                       # nominal grams, >= 0
    recoverable: bool = True
    hazardous: bool = False
    source_components: tuple[str, ...] = ()   # ComponentCategory wire values
    notes: str = ""

@dataclass(frozen=True, slots=True)
class MaterialProfile:
    device_type: str
    materials: tuple[MaterialSpec, ...]   # catalogue order
    known: bool = True                    # False only for the unknown fallback
    notes: str = ""

@dataclass(frozen=True, slots=True)
class MaterialProfileLibrary:
    version: str
    profiles: dict[str, MaterialProfile]  # keyed by normalized canonical type
    aliases: dict[str, str]               # synonym -> canonical (both normalized)
    unknown: MaterialProfile              # conservative fallback

    def profile_for(self, device_type: str) -> MaterialProfile: ...
```

`profile_for(device_type)` resolves a (possibly messy) device type exactly as the
component and recoverability engines do: `_normalize` collapses internal
whitespace to single underscores and casefolds (`"  CRT  Monitor "` →
`crt_monitor`), the alias map is consulted, then the canonical profile is looked
up. Anything unrecognized falls back to a copy of the conservative `unknown`
profile **stamped with the caller-supplied label** for provenance
(`replace(self.unknown, device_type=device_type.strip())`).

`load_library(path)` reads the file (YAML, or JSON when the suffix is `.json`),
then **validates aggressively**, raising a typed `MaterialProfileError` on any
structural problem:

- the file must exist, parse, and be a mapping (not empty, not a list);
- `version` must be a non-empty string;
- `profiles` must be a non-empty mapping, and every profile must list **at least
  one** material;
- every material needs a non-empty `name`, a `category` that is a valid
  `MaterialCategory`, and a **numeric, non-negative** `mass_g` (a `bool` is
  explicitly rejected — `True` is not a mass);
- every `source_components` entry must be a valid `ComponentCategory` wire value
  (`_ALLOWED_SOURCE_COMPONENTS = frozenset(ComponentCategory.values())`);
- every `aliases` value must point at a **real** canonical profile;
- the `unknown` fallback must be present.

Because validation happens once, at load, the rest of the engine can treat the
library as trusted, immutable data.

## Inference engine

`materials/inference.py` — `MaterialInferenceEngine(config)` is the deterministic
core that turns a `DeviceContext`, its `RecoverabilityReport`, its
`ComponentReport` and the resolved `MaterialProfile` into a normalized
`MaterialReport`. It does **no learned inference**: every number is a catalogue
nominal or an explicit, documented arithmetic combination of the inputs, so the
output is fully predictable and self-explaining.

The fold has **two independent axes** (per the design decision):

- **Mass** is the catalogue nominal (`mass_g`), rounded to three decimals
  (`_MASS_PRECISION = 3`) but **never clamped** to `[0, 1]` — masses are physical
  quantities, not probabilities — and **never scaled by confidence**.
- **Confidence** is derived separately, clamped to `[0, 1]` and rounded to **six
  decimals** (`_SCORE_PRECISION = 6`, matching the fusion, recoverability and
  component engines so all four engines' confidences compose cleanly).

`infer(context, recoverability, components, profile, *, profile_version="",
engine_version="", created_at=None)` folds the profile into a report in three
stages: per-material **mass & confidence** (with source-component gating and the
min-confidence floor), device-level **weight totals** and **overall confidence**,
and ordered **reasoning & warnings**.

## Mass & confidence

The engine first builds a `category → strongest presence_confidence` map from the
consumed component inventory (a device may list several components in one
category; the material that draws on that category is conditioned by the
most-present of them). Then each catalogue material is folded:

```
if spec.source_components:                       # conditional material
    matched = { c: presence[c] for c in spec.source_components if c present }
    if not matched:  drop the material           # no source component present
    source_presence = max(matched.values())      # strongest present source
else:                                            # structural / unconditional
    source_presence = 1.0

mass       = round(spec.mass_g, 3)               # nominal, never scaled/clamped
confidence = clamp_round(source_presence × overall_confidence)   # [0,1], 6 dp
drop the material if confidence <= min_material_confidence
```

- **Source-component gating.** A conditional material (`source_components:
  [battery]`) is listed **only if** at least one of its declared source
  components is present in the `ComponentReport`. This is what makes the
  per-device tables genuinely *use the component inventory* rather than emitting a
  fixed list: no battery detected ⇒ no battery materials reported.
- **Presence-scaled confidence.** The material's confidence is the strongest
  present source's `presence_confidence` **times** the overall inventory
  confidence. This enforces the invariant that **no single material is more
  certain than the overall estimate**, and a weakly-present source yields a
  proportionally weaker material.
- **Unconditional (structural) materials.** A material with empty
  `source_components` (a chassis, an enclosure) is always present with
  `source_presence = 1.0`, so its confidence equals the overall confidence.
- **Min-confidence floor.** After clamping, any material at or below
  `min_material_confidence` (default `0.05`) is dropped as too unlikely to report.
  The comparison is inclusive (`<=`), so a material exactly at the floor is
  dropped — asserted by the tests.

Every material carries a `reason` string assembled from the same steps ("Derived
from present component(s) battery (strongest presence 100%); confidence scaled by
the overall estimate confidence 90%."), so each number is self-explaining.

The device-level weight totals are then simple sums over the surviving materials:
`total_mass_g` over all, `recoverable_mass_g` over those flagged `recoverable`,
`hazardous_mass_g` over those flagged `hazardous` (each rounded to three
decimals). Because the two flags are independent, a material can contribute to
both sums, one, or neither.

## Overall confidence

`_overall_confidence` blends the two upstream confidences and then damps the
result multiplicatively — identical to the component engine, so the two reports'
confidences are directly comparable:

```
blended = context.confidence × (1 − w) + recoverability.confidence × w
          where w = recoverability_confidence_weight  (default 0.50)
if not profile.known:      blended ×= unknown_type_confidence_factor  (0.50)
if context.has_conflicts:  blended ×= conflict_confidence_factor      (0.85)
overall = clamp_round(blended)
```

The two upstream confidences are **blended** (a weighted average, so the material
breakdown's confidence reflects both how sure fusion was about the device *and*
how sure recoverability was about its assessment), then damped for an
**unrecognized device type** (a generic fallback breakdown is inherently less
trustworthy) and for **fusion conflicts** (contested identity undermines the
breakdown). The two damping signals are independent multiplicative factors, so
they **compound** — an unknown, conflicted device is damped more than either
alone.

The report-level `reasoning` records the profile used (and how many candidates
were supported by the inventory and cleared the floor), the nominal-mass /
presence-scaled-confidence rule, and the recoverability blend; `warnings` flags
an **unrecognized device type** ("the material breakdown is generic and should be
confirmed manually"), a **concrete assessed hazard** ("hazardous materials must
be handled through a dedicated stream"), **fusion conflicts** ("material estimate
confidence is reduced") and an **empty breakdown** ("no materials could be
estimated from the component inventory"). All lists are built in a fixed order so
the report reads top-to-bottom as the breakdown was assembled.

## Configuration

`materials/config.py` — `MaterialConfig` is a frozen dataclass and the **single
source of truth** for every tunable number and locator the engine reads. No
threshold is hardcoded in the inference engine or the loader; behaviour is
adjusted in exactly one place.

| Field | Default | Meaning |
|---|---|---|
| `profiles_path` | `materials/data/materials.yaml` | Locator of the external catalogue (YAML/JSON), resolved against the package root when relative. |
| `min_material_confidence` | `0.05` | Material confidence at/below which a material is dropped. |
| `unknown_type_confidence_factor` | `0.50` | Overall-confidence multiplier for an unrecognized device type. |
| `conflict_confidence_factor` | `0.85` | Overall-confidence multiplier when the fused context reported conflicts. |
| `recoverability_confidence_weight` | `0.50` | Weight blending the recoverability confidence into the overall confidence. |

`resolved_profiles_path(package_root=…)` anchors a relative `profiles_path` to the
`device_ai` package directory, so the packaged catalogue is found regardless of
the process working directory. `MaterialConfig.from_settings(settings)` maps the
**two operationally-tunable, env-driven** knobs (`MATERIAL_PROFILES_PATH`,
`MATERIAL_MIN_CONFIDENCE`) onto the config; every other field keeps its default
(still overridable directly in code). `MaterialConfig()` is always valid, so tests
and callers can tweak any field by keyword.

The only new failure type is `MaterialError` (in `exceptions.py`), a
`DeviceAIError` subclass with `code="MATERIAL_ERROR"` and `http_status=500`, plus
its subclass `MaterialProfileError` (`code="MATERIAL_PROFILE_ERROR"`,
`http_status=422`) raised by the loader. Because the engine is internal-only,
these surface to the orchestrating code as typed exceptions, not through the HTTP
error envelope.

## Testing

All M1.10 tests run in the **base environment** with hand-built frozen inputs — no
images, no models, no fusion run (an injected `_CLOCK` makes `created_at`
deterministic). Only the profile tests and the end-to-end service tests read the
shipped catalogue from disk; the inference tests use a small hand-built profile.
From `intelligence/device_ai`:

```bash
pytest tests/test_material_*.py -q
```

- **`tests/test_material_profiles.py`** — the external catalogue and its loader:
  the shipped file's structure and invariants (every `mass_g` non-negative, every
  category valid, every `source_components` entry a valid `ComponentCategory`,
  every alias pointing at a real profile), coverage parity with the component
  profile table, hazardous materials present in the CRT and battery profiles,
  normalized / alias-aware / unknown-fallback lookups preserving the caller label,
  loader validation against hand-written good/bad `tmp_path` catalogues (missing
  file, malformed YAML, missing version, unknown category, negative/non-numeric
  mass, bad `source_component`, dangling alias, missing `unknown`, empty
  materials list), JSON parity, and the `from_settings` mapping.
- **`tests/test_material_inference.py`** — the deterministic fold against a small
  hand-built profile and inputs: nominal mass passed through unscaled by
  confidence, source-component gating (a material dropped when no source component
  is present), unconditional materials always present, the strongest source's
  presence driving confidence, the min-confidence floor dropping at-or-below
  materials, the overall-confidence blend (`0.8`/`0.4` at weight `0.5` → `0.6`),
  unknown-type and conflict damping, the recoverable/hazardous weight split, and
  the ordered reasoning/warnings (unknown type, conflict, hazard, empty
  breakdown).
- **`tests/test_material_service.py`** — end-to-end `analyze()` against the shipped
  catalogue (inputs built by actually running `RecoverabilityService` and
  `ComponentService` over a hand-built context) across the required scenarios: an
  identifiable laptop (materials listed, recoverable/hazardous weight > 0, every
  material's confidence ≤ overall), a hazardous CRT (leaded glass surfaced,
  hazardous weight > 0), an unknown device (generic fallback + review warning +
  damped confidence), a conflicted context (damped confidence + warning); plus
  determinism (`to_dict` equal for identical input), provenance carry-over (eco_id
  / engine_version / profile_version / injected clock), JSON shape, report
  immutability, and an injected custom library/config.

## Integration guide

The material engine is a **library**, wired by construction — there is nothing to
mount and no endpoint to call. A future orchestrator chains it onto fusion,
recoverability and components like this:

```python
from device_ai.fusion import FusionEngine
from device_ai.recoverability import RecoverabilityService
from device_ai.components import ComponentService
from device_ai.materials import MaterialService

# 1. Fuse the perception engines into an immutable context (M1.7).
context = FusionEngine().fuse_modules(
    detection=detector.detect(images),                 # M1.4 DetectionResult
    fingerprint=fingerprint_service.generate(images),  # M1.5 DeviceFingerprint
    ocr=ocr_service.extract(images),                   # M1.6 OCRExtraction
)

# 2. Assess its recoverability (M1.8) and infer its components (M1.9).
recoverability = RecoverabilityService().assess(context)
components      = ComponentService().analyze(context, recoverability)

# 3. Estimate its recoverable materials (M1.10). All collaborators are injected,
#    so the service is constructible as-is or with a fixed clock / custom config /
#    pre-loaded library. The external catalogue is loaded once at construction.
report = MaterialService().analyze(context, recoverability, components)

report.device_type            # "laptop"
report.materials              # tuple[RecoveredMaterial, …] in catalogue order
report.hazardous_materials    # only the hazardous materials (e.g. battery cells)
report.recoverable_mass_g     # grams of recoverable material
report.hazardous_mass_g       # grams needing hazardous handling
report.overall_confidence     # e.g. 0.9
report.reasoning              # ordered, human-readable explanations
report.warnings               # operator-facing cautions (may be empty)
report.to_dict()              # fully serializable
```

To tune operationally (e.g. a stricter confidence floor, or an alternate
catalogue), build the service with a settings-driven config:

```python
from device_ai.configs.settings import get_settings
from device_ai.materials import MaterialConfig, MaterialService

config  = MaterialConfig.from_settings(get_settings())
service = MaterialService(config=config)
```

A pre-loaded library can be injected directly (bypassing disk I/O), which is how
the tests exercise the engine against a bespoke catalogue.

## Worked examples

_All numbers below are produced by actually running the engine chain
(`RecoverabilityService` → `ComponentService` → `MaterialService`) with a fixed
clock; they are not hand-computed._

### Identifiable laptop — full breakdown, high confidence

A fused laptop with model + serial + MAC, `confidence=0.9`, whose recoverability
assessment flags a `MEDIUM` hazard (embedded battery). Its component inventory
lists the battery, mainboard, processor, memory, storage, display and Wi-Fi
module, so every conditional material is supported:

```python
report = MaterialService(clock=lambda: CLOCK).analyze(context, recoverability, components)
report.to_dict()
```

```json
{
  "eco_id": "ET-2026-1A2B3C4D",
  "device_type": "laptop",
  "materials": [
    { "name": "Aluminium / magnesium chassis", "category": "non_ferrous_metal",
      "mass_g": 500.0, "confidence": 0.9, "recoverable": true, "hazardous": false,
      "source_components": [],
      "reason": "Structural material assumed present regardless of the component inventory; confidence is the overall estimate confidence 90%." },
    { "name": "Lithium (battery cells)", "category": "battery_material",
      "mass_g": 45.0, "confidence": 0.9, "recoverable": true, "hazardous": true,
      "source_components": ["battery"],
      "reason": "Derived from present component(s) battery (strongest presence 100%); confidence scaled by the overall estimate confidence 90%." },
    { "name": "Cobalt (cathode)", "category": "critical_material", "mass_g": 30.0,
      "confidence": 0.9, "recoverable": true, "hazardous": true, "source_components": ["battery"], "…": "…" },
    { "name": "Copper (traces, windings, wiring)", "category": "non_ferrous_metal",
      "mass_g": 90.0, "confidence": 0.9, "source_components": ["circuit_board", "connectivity"], "…": "…" },
    { "name": "Gold (connector & board plating)", "category": "precious_metal",
      "mass_g": 0.2, "confidence": 0.9, "source_components": ["circuit_board", "processor"], "…": "…" },
    { "name": "Display glass", "category": "glass", "mass_g": 120.0,
      "confidence": 0.873, "source_components": ["display"],
      "reason": "Derived from present component(s) display (strongest presence 97%); confidence scaled by the overall estimate confidence 90%." }
    /* …Silver, FR-4 substrate, silicon dies, steel fasteners… */
  ],
  "material_count": 10,
  "total_mass_g": 1071.7,
  "recoverable_mass_g": 1071.7,
  "hazardous_mass_g": 75.0,
  "overall_confidence": 0.9,
  "reasoning": [
    "Material profile for 'laptop' lists 10 candidate material(s); 10 were supported by the component inventory and cleared the confidence floor.",
    "Estimated masses are catalogue nominal values; each material's confidence is the strongest presence of its source components scaled by the overall estimate confidence.",
    "Recoverability assessment (action 'refurbish', hazard 'medium', confidence 0.90) was blended into the overall confidence."
  ],
  "warnings": [
    "Device carries an assessed hazard; hazardous materials must be handled through a dedicated stream."
  ],
  "engine_version": "1.0.0",
  "profile_version": "1.0.0",
  "created_at": "2026-08-01T12:00:00+00:00"
}
```

Every material's mass is the catalogue nominal, unscaled. Most materials sit at
the overall `0.9` because their source components are present at full confidence;
the display glass is scaled to `0.9 × 0.97 = 0.873` because the display component
was itself only `97%` present. The hazardous weight (`75 g` — lithium `45` +
cobalt `30`) is the sum of the two battery materials; every material here is also
recoverable, so `recoverable_mass_g` equals `total_mass_g`.

### CRT monitor — hazardous leaded glass surfaced

A `"CRT monitor"` (normalized to `crt_monitor`), whose recoverability hazard is
`HIGH`, surfaces its intrinsically hazardous glass:

```
Leaded funnel glass    6000 g   hazardous, non-recoverable   (source: display)
Panel (barium) glass   4000 g   hazardous, non-recoverable   (source: display)
Phosphor coating         15 g   hazardous, non-recoverable   (source: other)
Copper (yoke & wiring)  500 g   recoverable                  (source: other, circuit_board)
Steel shadow mask …    2500 g   recoverable                  (structural)
Enclosure plastics     2000 g   recoverable                  (structural)
```

The breakdown totals `15015 g`, of which `hazardous_mass_g = 10015 g` (the leaded
funnel glass, barium panel glass and phosphor) and `recoverable_mass_g = 5000 g`
(copper, steel, plastics). `report.hazardous_materials` surfaces exactly the
parts that drive hazardous handling downstream, and the operator warning fires
because the assessed hazard is concrete.

### Unknown device — generic fallback, damped, warned

A `"teleporter"` is not in the catalogue, so the conservative `unknown` fallback
(three unconditional structural materials) is used and the overall confidence is
halved:

```json
{
  "device_type": "teleporter",
  "materials": [
    { "name": "Mixed plastics (enclosure)", "mass_g": 150.0, "confidence": 0.3825, "source_components": [] },
    { "name": "Mixed ferrous metal",        "mass_g": 80.0,  "confidence": 0.3825, "source_components": [] },
    { "name": "Mixed circuit-board material","mass_g": 40.0,  "confidence": 0.3825, "source_components": [] }
  ],
  "material_count": 3,
  "total_mass_g": 270.0,
  "recoverable_mass_g": 270.0,
  "hazardous_mass_g": 0.0,
  "overall_confidence": 0.3825,
  "warnings": [
    "Unrecognized device type; the material breakdown is generic and should be confirmed manually."
  ]
}
```

Only generic structural materials are estimated; the overall confidence blends
fusion's `0.9` with recoverability's own (already unknown-damped) `0.63` →
`0.765`, then the unknown-type factor halves it (`0.765 × 0.50 = 0.3825`), and the
operator is told to confirm the device manually. Because the structural materials
are unconditional, each inherits that overall confidence directly.

## Backward compatibility

The `/predict` contract is **completely unchanged**. M1.10 mounts **no router**,
adds **no endpoint**, and does not touch `application.py`, the `/predict`
pipeline, or any existing schema. The material engine is imported and used only
where a future orchestrator chooses to — it is invisible to every current caller.

The two new environment variables are **opt-in** with defaults that reproduce the
reference behaviour (`MATERIAL_PROFILES_PATH=materials/data/materials.yaml`,
`MATERIAL_MIN_CONFIDENCE=0.05`), so an existing deployment that sets neither
behaves exactly as before. The full pre-existing test suite (including the
`/predict` backward-compatibility guards from M1.4–M1.9) passes unchanged
alongside the new M1.10 tests.

## Design rationale

**Why per-device-type nominal masses instead of deriving mass from components?**
The consumed `ComponentReport` carries a *presence confidence* for each component,
not a mass — it answers "is there a battery?", not "how many grams?". A credible
mass estimate therefore needs a reference table, and the honest place for that is
a per-device-type catalogue of nominal masses curated by domain experts. Tying
each catalogue material to the **component categories** that imply it is what
keeps the estimate faithful to *this* device: the table supplies the mass, but
the actual component inventory decides which materials are listed and how
confident each is. A laptop with no detected battery reports no battery
materials.

**Why nominal mass with a *separate* confidence instead of scaling mass by
confidence?** Mass and certainty are different quantities. A laptop battery
weighs ~45 g whether the engine is 50% or 99% sure it is present — scaling the
mass by confidence would invent a "45 g × 0.5 = 22.5 g battery" that exists in no
physical device and would corrupt the recoverable/hazardous weight totals
operators rely on. Keeping `mass_g` at the catalogue nominal and expressing
uncertainty in a **separate** `confidence` field means the weight totals stay
physically meaningful while the confidence still tells the operator how much to
trust them.

**Why gate materials on source-component presence?** It is the mechanism that
makes the per-device tables genuinely *consume* the M1.9 inventory rather than
emit a fixed list. Gating on presence (and scaling confidence by the strongest
present source) means the two engines stay consistent — a material can only be as
certain as the component it is recovered from — and the breakdown shrinks
honestly for a stripped or partially-detected device.

**Why an external catalogue instead of an in-code table?** The same reasoning as
M1.9: the material catalogue is **pure reference data** — per-device material
lists with nominal masses, recovery/hazard flags and source-component links —
that domain experts (not engineers) will want to review, extend and correct as
new device classes and material data appear. Storing it as a versioned YAML/JSON
file makes those edits a data change, not a code change or redeploy, and stamping
its `version` onto every report keeps the provenance auditable. The strict loader
is the price of that flexibility: it fails loudly on a malformed catalogue rather
than silently degrading.

**Why blend the two upstream confidences and then damp multiplicatively?** This is
deliberately identical to the component engine so the two reports' confidences are
directly comparable. The breakdown's trustworthiness depends on both how sure
fusion was about the device *and* how sure recoverability was about its
assessment, so a weighted **blend** is the honest base; the unknown-type and
conflict signals are independent reasons to trust the breakdown *less*, and
multiplicative factors let them **compound**, at the same 6-decimal precision the
upstream engines use.

**Why `TYPE_CHECKING`-only imports of the three upstream reports and `Settings`?**
The domain layer must not couple to the fusion, recoverability, component or
settings modules at runtime (that would create import cycles and drag transitive
dependencies into a pure engine). Typing all three upstream reports under
`TYPE_CHECKING` and passing them in mirrors the M1.7–M1.9 precedent and keeps
`materials/` importable on its own. (The two runtime imports — the `HazardLevel`
and `ComponentCategory` enums — are unavoidable: the engine must phrase the hazard
warning against `HazardLevel`'s members and validate the catalogue's
`source_components` against `ComponentCategory`'s.)

**Why an injected service + clock + library?** `MaterialService` wires config +
library + inference into the single `analyze(context, recoverability, components)`
operation downstream code depends on. Every collaborator is injected, so the whole
engine is exercised deterministically in tests with hand-built inputs — no fusion
run, no models — a `clock=None` keeps the report a pure function of its inputs
when timestamps are not wanted, and an injected library lets the tests run the
engine against a bespoke catalogue without touching disk.

---

_Part of **EcoTrace India** — IEEE YESIST 2026. See the module
[`README.md`](../../README.md) and the platform-wide `docs/engineering/`
standards._
