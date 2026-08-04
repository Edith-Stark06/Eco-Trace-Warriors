# Component Intelligence Engine (M1.9)

> The second **downstream consumer** of the Device Intelligence Engine: an
> internal-only, **deterministic inference engine** that turns the immutable
> `DeviceContext` produced by the **fusion engine** (M1.7) and the
> `RecoverabilityReport` produced by the **recoverability engine** (M1.8) into an
> explainable **`ComponentReport`** — the likely internal electronic components of
> the device, each with a **presence confidence**, plus a single **overall
> confidence** and ordered human-readable reasoning and warnings. Unlike M1.8's
> in-code profile table, its knowledge lives in an **external, versioned
> YAML/JSON catalogue** so the component library is data, not logic. It ships
> **no new endpoint** and leaves the `/predict` API contract **unchanged and
> backward-compatible**.

**Module:** `intelligence/device_ai`
**Milestone:** M1.9 — Component Intelligence Engine
**Status:** implemented; internal-only (no router, no HTTP surface)

---

## Table of contents

1. [Scope](#scope)
2. [Architecture](#architecture)
3. [Domain models](#domain-models)
4. [The external component catalogue](#the-external-component-catalogue)
5. [Profile library & loader](#profile-library--loader)
6. [Inference engine](#inference-engine)
7. [Presence confidence](#presence-confidence)
8. [Overall confidence](#overall-confidence)
9. [Configuration](#configuration)
10. [Testing](#testing)
11. [Integration guide](#integration-guide)
12. [Worked examples](#worked-examples)
13. [Backward compatibility](#backward-compatibility)
14. [Design rationale](#design-rationale)

---

## Scope

M1.9 is the **second** component to consume the fusion engine's output, and the
first to also consume the recoverability engine's. Fusion (M1.7) produces an
immutable `DeviceContext`; recoverability (M1.8) turns that into a
`RecoverabilityReport`; the component engine answers the next question: *"given
what we now know about this device and how recoverable it is, which internal
electronic components is it likely to contain?"* Every component the engine
lists is derived from **four deterministic signals**, never from learned models:

| # | Signal | Source | Effect on the report |
|---|---|---|---|
| 1 | **Device-type profile** | external `components.yaml` catalogue | Seeds the candidate component list and each component's **base likelihood** (a prior). |
| 2 | **OCR identity completeness** | `context.model` / `.serial_number` / `.imei` / `.mac_address` | A component that declares a matching `implied_by` signal gets a small presence-confidence bonus (a serial corroborates a mainboard, an IMEI a cellular modem, a MAC a Wi-Fi module). |
| 3 | **Recoverability hazard** | `recoverability.hazard_level` | A **hazardous** component gets a presence bonus when the device's assessed hazard is a concrete (non-`NONE`/`UNKNOWN`) level — the two engines agree. |
| 4 | **Fusion confidence & conflicts** | `context.confidence` / `.has_conflicts` + profile familiarity | Blended with the recoverability confidence into the **overall** confidence, then damped for an unrecognized device type and for fusion conflicts. |

**Explicitly in scope**

- `ComponentReport` — the normalized, immutable component inventory.
- An **external, versioned** component-profile catalogue (YAML/JSON) with a
  strict loader that validates aggressively and fails with a typed error.
- A pure `ComponentInferenceEngine` fold (catalogue prior → bounded
  corroboration bonuses → clamp/round → min-presence floor; blended/damped
  overall confidence).
- An injected `ComponentService` orchestration facade.

**Explicitly out of scope** (do **not** implement in M1.9): Material Intelligence,
Carbon Intelligence, blockchain anchoring and the Digital Device Passport. The
engine is **internal only** — no router is mounted, `application.py` is untouched,
and the `/predict` response schema is **unchanged**.

**Key input constraint.** As with recoverability, `DeviceContext` exposes only
**identity** attributes (device type, brand, model, serial/IMEI/MAC) plus
aggregate `confidence`, `conflicts`/`has_conflicts` and provenance. The component
engine derives its inventory from the device-type catalogue and those four
signals **only** — it never re-derives a component list from raw images, models,
or material composition.

## Architecture

The engine is a **pure domain layer** with the same shape as `fusion/` and
`recoverability/`: frozen slotted dataclasses, stateless engines, and an injected
service. It imports the fusion `DeviceContext`, the recoverability
`RecoverabilityReport` and the settings `Settings` **only under `TYPE_CHECKING`**,
so there is no runtime coupling and no import cycle — both upstream reports are
passed in, never reached into. The one runtime dependency it does take on the
recoverability layer is the `HazardLevel` enum (needed to test the hazard signal).

```
     fusion engine (M1.7) ─► DeviceContext ──┐
                                             │
 recoverability engine (M1.8) ─► Recoverability│Report ─┐
                                             │          │
            ┌──────────── components/ (internal) ───────▼──────────┐
            │  service.py  ComponentService.analyze(ctx, recov)     │
            │        │            │              │                  │
            │        ▼            ▼              ▼                  │
            │  profiles.py    inference.py   config.py             │
            │  load_library   ComponentInfer  ComponentConfig      │
            │  profile_for    enceEngine      (weights + locator)  │
            │  (external      (prior + bounded                     │
            │   YAML/JSON,    corroboration, clamp,                │
            │   validated)    min-presence floor,                  │
            │                 blended/damped overall)              │
            │        └────────────┬─────────────┘                  │
            │                     ▼                                │
            │      models.py  ComponentReport (frozen)             │
            │      ComponentCategory · InferredComponent           │
            └──────────────────────────────────────────────────────┘
                                  ▼
        downstream AI (M1.10+ material/carbon/passport) — never /predict
```

Layering (dependencies point downward, never upward):

```
fusion/ · recoverability/   (M1.7/M1.8 — produce the immutable inputs)
   ↓  (TYPE_CHECKING only; both reports are passed in)
components/  (models.py + profiles.py + config.py + inference.py + service.py)
   ↓
exceptions · configs   (cross-cutting foundations)
```

The package contains **no HTTP imports, no FastAPI, and its only I/O is reading
the catalogue file once at service construction.** After that, `analyze()` is a
pure function of its inputs except for the injected clock (which defaults to UTC
`now` and can be replaced or disabled for determinism).

## Domain models

`components/models.py` defines the vocabulary that makes an inventory auditable.

### `ComponentCategory`

```python
class ComponentCategory(str, Enum):
    BATTERY = "battery"
    CIRCUIT_BOARD = "circuit_board"
    PROCESSOR = "processor"
    MEMORY = "memory"
    STORAGE = "storage"
    DISPLAY = "display"
    CONNECTIVITY = "connectivity"
    INPUT = "input"
    CAMERA = "camera"
    SENSOR = "sensor"
    POWER = "power"
    AUDIO = "audio"
    OPTICS = "optics"
    OPTICAL_MEDIA = "optical_media"
    CABLING = "cabling"
    HOUSING = "housing"
    OTHER = "other"
```

A `str` enum so members serialize directly to their wire value **and** can be
constructed from a catalogue string (`ComponentCategory("circuit_board")`). This
enum is the **single source of truth** the external catalogue is validated
against on load — a catalogue entry naming a category outside this set is
rejected. `ComponentCategory.values()` returns every wire value in declaration
order (used in the loader's error messages).

### `InferredComponent`

One internal component the engine believes is present:

```python
@dataclass(frozen=True, slots=True)
class InferredComponent:
    name: str
    category: ComponentCategory
    presence_confidence: float      # in [0, 1]
    hazardous: bool
    recoverable: bool
    reason: str                     # how the presence confidence was derived

    def to_dict(self) -> dict[str, object]: ...
```

### `ComponentReport`

The normalized, immutable inventory produced by the service:

```python
@dataclass(frozen=True, slots=True)
class ComponentReport:
    device_type: str
    components: tuple[InferredComponent, ...]   # catalogue order
    overall_confidence: float                   # in [0, 1]
    reasoning: tuple[str, ...]                   # ordered
    warnings: tuple[str, ...]                    # operator cautions (may be empty)
    eco_id: str = ""                            # carried over from the context
    engine_version: str = ""
    profile_version: str = ""                   # catalogue version
    created_at: datetime | None = None

    @property
    def component_count(self) -> int: ...
    @property
    def hazardous_components(self) -> tuple[InferredComponent, ...]: ...
    @property
    def recoverable_components(self) -> tuple[InferredComponent, ...]: ...
    def to_dict(self) -> dict[str, object]: ...
```

Like every domain object, the report is frozen and slotted — attempting to mutate
it raises `FrozenInstanceError`. The `hazardous_components` /
`recoverable_components` projections let downstream code partition the inventory
without re-scanning it.

## The external component catalogue

The component knowledge lives in an **external** file
(`components/data/components.yaml` by default), **not** in Python. This is a
deliberate departure from M1.8's hand-curated in-code profile table: the
component catalogue is **data, not logic**, so it can be reviewed, extended or
corrected without touching (or redeploying) the engine code. The loader validates
it on read, so a malformed catalogue never silently degrades the engine.

The file has four top-level keys:

```yaml
version: "1.0.0"           # stamped onto every report as profile provenance
aliases:                   # synonym -> canonical device type
  cell_phone: smartphone
  pc: desktop
  crt: crt_monitor
  # …47 aliases total
unknown:                   # conservative fallback for unrecognized types
  notes: >-
    Unrecognized device type. Only generic components common to most
    electronics are inferred, at low likelihood; a human should confirm …
  components:
    - { name: Outer enclosure / housing, category: housing, base_likelihood: 0.80 }
    - { name: Printed circuit board,     category: circuit_board, base_likelihood: 0.70 }
    - { name: Internal wiring / connectors, category: cabling, base_likelihood: 0.55 }
profiles:                  # canonical device type -> profile
  laptop:
    notes: Modular portable computer; battery, mainboard, display and storage.
    components:
      - name: Lithium-ion battery pack
        category: battery
        base_likelihood: 0.97
        hazardous: true
        recoverable: true
      - name: Mainboard (motherboard)
        category: circuit_board
        base_likelihood: 0.99
        implied_by: [serial_number]
      # …
```

Each component entry carries: `name`, `category` (a `ComponentCategory` wire
value), `base_likelihood` (a prior in `[0, 1]`), optional `hazardous`/`recoverable`
flags (default `false`/`true`), an optional `implied_by` list of identity signals
(`model` / `serial_number` / `imei` / `mac_address`), and optional `notes`
(provenance, not used in scoring).

The shipped catalogue covers the **same 19 device classes** as the recoverability
profile table — laptop, smartphone, tablet, desktop, server, monitor,
crt_monitor, television, printer, keyboard, mouse, router, power_supply, cable,
camera, game_console, smartwatch, headphones, battery — plus **47 synonym
aliases** that mirror the recoverability engine's alias set, so a device type
resolved by one engine resolves identically in the other. Hazardous components
are deliberately flagged (laptop/phone/tablet/camera/smartwatch/headphones
batteries; CRT leaded glass and phosphor; TV/printer backlight lamps and fuser;
power-supply capacitors), which is what lets the hazard signal corroborate them.

## Profile library & loader

`components/profiles.py` owns the small, strict loader that turns the catalogue
file into validated, immutable value objects.

```python
@dataclass(frozen=True, slots=True)
class ComponentSpec:
    name: str
    category: ComponentCategory
    base_likelihood: float          # prior in [0, 1]
    hazardous: bool = False
    recoverable: bool = True
    implied_by: tuple[str, ...] = ()   # model/serial_number/imei/mac_address
    notes: str = ""

@dataclass(frozen=True, slots=True)
class ComponentProfile:
    device_type: str
    components: tuple[ComponentSpec, ...]   # catalogue order
    known: bool = True                      # False only for the unknown fallback
    notes: str = ""

@dataclass(frozen=True, slots=True)
class ComponentProfileLibrary:
    version: str
    profiles: dict[str, ComponentProfile]   # keyed by normalized canonical type
    aliases: dict[str, str]                 # synonym -> canonical (both normalized)
    unknown: ComponentProfile               # conservative fallback

    def profile_for(self, device_type: str) -> ComponentProfile: ...
```

`profile_for(device_type)` resolves a (possibly messy) device type exactly as the
recoverability engine does: `_normalize` collapses internal whitespace to single
underscores and casefolds (`"  CRT  Monitor "` → `crt_monitor`), the alias map is
consulted, then the canonical profile is looked up. Anything unrecognized falls
back to a copy of the conservative `unknown` profile **stamped with the
caller-supplied label** for provenance (`replace(self.unknown,
device_type=device_type.strip())`).

`load_library(path)` reads the file (YAML, or JSON when the suffix is `.json`),
then **validates aggressively**, raising a typed `ComponentProfileError` on any
structural problem:

- the file must exist, parse, and be a mapping (not empty, not a list);
- `version` must be a non-empty string;
- `profiles` must be a non-empty mapping, and every profile must list **at least
  one** component;
- every component needs a non-empty `name`, a `category` that is a valid
  `ComponentCategory`, and a **numeric** `base_likelihood` in `[0, 1]` (a `bool`
  is explicitly rejected — `True` is not a likelihood);
- every `implied_by` entry must be one of the four allowed signal names;
- every `aliases` value must point at a **real** canonical profile;
- the `unknown` fallback must be present.

Because validation happens once, at load, the rest of the engine can treat the
library as trusted, immutable data.

## Inference engine

`components/inference.py` — `ComponentInferenceEngine(config)` is the
deterministic core that turns a `DeviceContext`, its `RecoverabilityReport` and
the resolved `ComponentProfile` into a normalized `ComponentReport`. It does **no
learned inference**: every number is a catalogue prior adjusted by explicit,
documented corroboration rules, so the output is fully predictable and
self-explaining. All numeric outputs are clamped to `[0, 1]` and rounded to
**six decimals** (`_SCORE_PRECISION = 6`), matching the fusion and recoverability
engines so the three engines' numbers compose cleanly.

`infer(context, recoverability, profile, *, profile_version="",
engine_version="", created_at=None)` folds the profile into a report in three
stages: per-component **presence confidence** (with the min-presence floor),
report-level **overall confidence**, and ordered **reasoning & warnings**.

## Presence confidence

Each component starts at its catalogue `base_likelihood` (a prior) and gains at
most two small, bounded, additive bonuses:

```
presence = base_likelihood
         + identity_corroboration_bonus   (if any implied_by signal is present)
         + hazard_corroboration_bonus     (if the component is hazardous AND the
                                           device's assessed hazard is concrete)
presence = clamp_round(presence)          # to [0, 1], 6 decimals
drop the component if presence <= min_presence_confidence
```

- **Identity corroboration.** A component declares the identity signals that imply
  it (`implied_by: [serial_number]` on a mainboard). If *any* of those signals is
  present in the fused context, the component gains `identity_corroboration_bonus`
  (default `+0.05`). A non-matching signal (a serial present, but the component is
  implied by IMEI) contributes **nothing** — corroboration is signal-specific.
- **Hazard corroboration.** A component flagged `hazardous: true` gains
  `hazard_corroboration_bonus` (default `+0.05`) when the recoverability report's
  `hazard_level` is a **concrete** level (`LOW`/`MEDIUM`/`HIGH`). `NONE` and
  `UNKNOWN` do **not** corroborate: `NONE` is a positive "no hazard" finding and
  `UNKNOWN` is "insufficient evidence" — neither is a positive hazard signal that
  should raise a hazardous component's presence.
- **Min-presence floor.** After clamping, any component at or below
  `min_presence_confidence` (default `0.05`) is dropped as too unlikely to report.
  The comparison is inclusive (`<=`), so a component exactly at the floor is
  dropped — asserted by the tests.

Every component carries a `reason` string assembled from the same steps
("Catalogue prior 97% for a 'laptop' device. Hazardous part consistent with the
assessed device hazard (+5%)."), so each number is self-explaining.

## Overall confidence

`_overall_confidence` blends the two upstream confidences and then damps the
result multiplicatively:

```
blended = context.confidence × (1 − w) + recoverability.confidence × w
          where w = recoverability_confidence_weight  (default 0.50)
if not profile.known:      blended ×= unknown_type_confidence_factor  (0.50)
if context.has_conflicts:  blended ×= conflict_confidence_factor      (0.85)
overall = clamp_round(blended)
```

The two upstream confidences are **blended** (a weighted average, so the
component inventory's confidence reflects both how sure fusion was about the
device *and* how sure recoverability was about its assessment), then damped for an
**unrecognized device type** (a generic fallback inventory is inherently less
trustworthy) and for **fusion conflicts** (contested identity undermines the
inventory). The two damping signals are independent multiplicative factors, so
they **compound** — an unknown, conflicted device is damped more than either
alone.

The report-level `reasoning` records the profile used (and how many candidates
met the floor), which identity signals corroborated components, and the
recoverability blend; `warnings` flags an **unrecognized device type** ("the
component inventory is generic and should be confirmed manually") and **fusion
conflicts** ("component inference confidence is reduced"). Both lists are built in
a fixed order so the report reads top-to-bottom as the inventory was assembled.

## Configuration

`components/config.py` — `ComponentConfig` is a frozen dataclass and the **single
source of truth** for every tunable number and locator the engine reads. No
threshold is hardcoded in the inference engine or the loader; behaviour is
adjusted in exactly one place.

| Field | Default | Meaning |
|---|---|---|
| `profiles_path` | `components/data/components.yaml` | Locator of the external catalogue (YAML/JSON), resolved against the package root when relative. |
| `min_presence_confidence` | `0.05` | Presence confidence at/below which a component is dropped. |
| `identity_corroboration_bonus` | `0.05` | Presence boost when an `implied_by` identity signal is present. |
| `hazard_corroboration_bonus` | `0.05` | Presence boost for a hazardous component when the device hazard is concrete. |
| `unknown_type_confidence_factor` | `0.50` | Overall-confidence multiplier for an unrecognized device type. |
| `conflict_confidence_factor` | `0.85` | Overall-confidence multiplier when the fused context reported conflicts. |
| `recoverability_confidence_weight` | `0.50` | Weight blending the recoverability confidence into the overall confidence. |

`resolved_profiles_path(package_root=…)` anchors a relative `profiles_path` to the
`device_ai` package directory, so the packaged catalogue is found regardless of
the process working directory. `ComponentConfig.from_settings(settings)` maps the
**two operationally-tunable, env-driven** knobs (`COMPONENT_PROFILES_PATH`,
`COMPONENT_MIN_PRESENCE_CONFIDENCE`) onto the config; every other field keeps its
default (still overridable directly in code). `ComponentConfig()` is always valid,
so tests and callers can tweak any field by keyword.

The only new failure type is `ComponentError` (in `exceptions.py`), a
`DeviceAIError` subclass with `code="COMPONENT_ERROR"` and `http_status=500`, plus
its subclass `ComponentProfileError` (`code="COMPONENT_PROFILE_ERROR"`,
`http_status=422`) raised by the loader. Because the engine is internal-only,
these surface to the orchestrating code as typed exceptions, not through the HTTP
error envelope.

## Testing

All M1.9 tests run in the **base environment** with hand-built frozen inputs — no
images, no models, no fusion run (an injected `_CLOCK` makes `created_at`
deterministic). Only the profile tests and the end-to-end service tests read the
shipped catalogue from disk; the inference tests use a small hand-built profile.
From `intelligence/device_ai`:

```bash
pytest tests/test_component_*.py -q
```

- **`tests/test_component_profiles.py`** — the external catalogue and its loader:
  the shipped file's structure and invariants (every `base_likelihood` a valid
  `[0, 1]` probability, every category valid, every alias pointing at a real
  profile), coverage parity with the recoverability profile table, normalized /
  alias-aware / unknown-fallback lookups preserving the caller label, loader
  validation against hand-written good/bad `tmp_path` catalogues (missing version,
  empty profiles, unknown category, out-of-range/boolean likelihood, unknown
  `implied_by`, dangling alias, missing `unknown`), JSON parity, and the
  `from_settings` mapping.
- **`tests/test_component_inference.py`** — the deterministic fold against a small
  hand-built profile and inputs: presence confidence starting from the prior,
  clamp/round (a prior + bonus over `1.0` pins to `1.0`), identity corroboration
  (matching signal boosts, non-matching signal does not), hazard corroboration
  (concrete hazard boosts a hazardous part, `UNKNOWN` does not), the min-presence
  floor dropping at-or-below components, the overall-confidence blend (`0.8`/`0.4`
  at weight `0.5` → `0.6`), unknown-type and conflict damping, and the ordered
  reasoning/warnings.
- **`tests/test_component_service.py`** — end-to-end `analyze()` against the
  shipped catalogue across the required scenarios: an identifiable laptop (battery
  + board present, hazardous/recoverable partitions non-empty), a hazardous CRT
  (hazardous tube listed), an unknown device (generic fallback + review warning), a
  conflicted context (damped confidence + warning); plus determinism (`to_dict`
  equal for identical input), provenance carry-over (eco_id / engine_version /
  profile_version / injected clock), JSON shape, report immutability, and an
  injected custom library/config.

## Integration guide

The component engine is a **library**, wired by construction — there is nothing to
mount and no endpoint to call. A future orchestrator chains it onto fusion and
recoverability like this:

```python
from device_ai.fusion import FusionEngine
from device_ai.recoverability import RecoverabilityService
from device_ai.components import ComponentService

# 1. Fuse the perception engines into an immutable context (M1.7).
context = FusionEngine().fuse_modules(
    detection=detector.detect(images),                 # M1.4 DetectionResult
    fingerprint=fingerprint_service.generate(images),  # M1.5 DeviceFingerprint
    ocr=ocr_service.extract(images),                   # M1.6 OCRExtraction
)

# 2. Assess its recoverability (M1.8).
recoverability = RecoverabilityService().assess(context)

# 3. Infer its internal components (M1.9). All collaborators are injected, so the
#    service is constructible as-is or with a fixed clock / custom config /
#    pre-loaded library. The external catalogue is loaded once at construction.
report = ComponentService().analyze(context, recoverability)

report.device_type            # "laptop"
report.components             # tuple[InferredComponent, …] in catalogue order
report.hazardous_components   # only the hazardous parts (e.g. the battery)
report.overall_confidence     # e.g. 0.9
report.reasoning              # ordered, human-readable explanations
report.warnings               # operator-facing cautions (may be empty)
report.to_dict()              # fully serializable
```

To tune operationally (e.g. a stricter presence floor, or an alternate
catalogue), build the service with a settings-driven config:

```python
from device_ai.configs.settings import get_settings
from device_ai.components import ComponentConfig, ComponentService

config  = ComponentConfig.from_settings(get_settings())
service = ComponentService(config=config)
```

A pre-loaded library can be injected directly (bypassing disk I/O), which is how
the tests exercise the engine against a bespoke catalogue.

## Worked examples

### Identifiable laptop — full inventory, high confidence

A fused laptop with model + serial + MAC, `confidence=0.9`, whose recoverability
assessment flags a `MEDIUM` hazard (embedded battery):

```python
report = ComponentService(clock=lambda: CLOCK).analyze(context, recoverability)
report.to_dict()
```

```json
{
  "eco_id": "ET-2026-1A2B3C4D",
  "device_type": "laptop",
  "components": [
    { "name": "Lithium-ion battery pack", "category": "battery",
      "presence_confidence": 1.0, "hazardous": true, "recoverable": true,
      "reason": "Catalogue prior 97% for a 'laptop' device. Hazardous part consistent with the assessed device hazard (+5%)." },
    { "name": "Mainboard (motherboard)", "category": "circuit_board",
      "presence_confidence": 1.0, "hazardous": false, "recoverable": true,
      "reason": "Catalogue prior 99% for a 'laptop' device. Corroborated by the device's serial number (+5%)." },
    { "name": "CPU / processor", "category": "processor", "presence_confidence": 0.99, "…": "…" },
    { "name": "RAM module", "category": "memory", "presence_confidence": 0.95, "…": "…" },
    { "name": "SSD / hard-disk storage", "category": "storage", "presence_confidence": 1.0,
      "reason": "Catalogue prior 95% for a 'laptop' device. Corroborated by the device's serial number (+5%)." },
    { "name": "LCD/LED display panel", "category": "display", "presence_confidence": 0.97, "…": "…" },
    { "name": "Wi-Fi / Bluetooth module", "category": "connectivity", "presence_confidence": 0.95,
      "reason": "Catalogue prior 90% for a 'laptop' device. Corroborated by the device's MAC address (+5%)." },
    { "name": "Keyboard & trackpad assembly", "category": "input", "presence_confidence": 0.93, "…": "…" }
  ],
  "component_count": 8,
  "overall_confidence": 0.9,
  "reasoning": [
    "Component profile for 'laptop' lists 8 candidate component(s); 8 met the presence-confidence floor.",
    "Identity signals present (model, serial number, MAC address) corroborated the components they imply.",
    "Recoverability assessment (action 'refurbish', hazard 'medium', confidence 0.90) was blended into the overall confidence."
  ],
  "warnings": [],
  "engine_version": "1.0.0",
  "profile_version": "1.0.0",
  "created_at": "2026-08-01T12:00:00+00:00"
}
```

The battery's prior `0.97` plus the `+0.05` hazard bonus clamps to `1.0`; the
mainboard, storage and Wi-Fi module each gain `+0.05` from their matching identity
signals. Overall confidence is the `0.9`/`0.9` blend, undamped (known type, no
conflicts).

### CRT monitor — hazardous parts surfaced

A `"CRT monitor"` (normalized to `crt_monitor`) lists its intrinsically hazardous
tube and phosphor:

```
Cathode-ray tube (leaded glass)   1.0   hazardous
Phosphor coating                  1.0   hazardous
Flyback transformer / HV board    1.0   hazardous
Deflection yoke (copper)          0.9
```

Each hazardous part's high prior plus the hazard-corroboration bonus (the CRT's
recoverability hazard is `HIGH`) pins it to `1.0`, so `report.hazardous_components`
surfaces exactly the parts that drive hazardous handling downstream.

### Unknown device — generic fallback, damped, warned

A `"teleporter"` is not in the catalogue, so the conservative `unknown` fallback
is used and the overall confidence is halved:

```json
{
  "device_type": "teleporter",
  "components": [
    { "name": "Outer enclosure / housing", "presence_confidence": 0.8 },
    { "name": "Printed circuit board",      "presence_confidence": 0.7 },
    { "name": "Internal wiring / connectors","presence_confidence": 0.55 }
  ],
  "overall_confidence": 0.3825,
  "warnings": [
    "Unrecognized device type; the component inventory is generic and should be confirmed manually."
  ]
}
```

Only generic components are inferred; the overall confidence blends fusion's
`0.9` with recoverability's own (already unknown-damped) `0.63` → `0.765`, then the
unknown-type factor halves it (`0.765 × 0.50 = 0.3825`), and the operator is told
to confirm the device manually.

## Backward compatibility

The `/predict` contract is **completely unchanged**. M1.9 mounts **no router**,
adds **no endpoint**, and does not touch `application.py`, the `/predict`
pipeline, or any existing schema. The component engine is imported and used only
where a future orchestrator chooses to — it is invisible to every current caller.

The two new environment variables are **opt-in** with defaults that reproduce the
reference behaviour (`COMPONENT_PROFILES_PATH=components/data/components.yaml`,
`COMPONENT_MIN_PRESENCE_CONFIDENCE=0.05`), so an existing deployment that sets
neither behaves exactly as before. The full pre-existing test suite (including the
`/predict` backward-compatibility guards from M1.4–M1.8) passes unchanged
alongside the new M1.9 tests.

## Design rationale

**Why an external catalogue instead of an in-code table?** M1.8 curates its
profiles in Python because they are small, closely coupled to the rule logic, and
few. The component catalogue is different: it is **pure reference data** —
per-device component lists with priors and flags — that domain experts (not
engineers) will want to review, extend and correct as new device classes appear.
Storing it as a versioned YAML/JSON file makes those edits a data change, not a
code change or redeploy, and stamping its `version` onto every report keeps the
provenance auditable. The strict loader is the price of that flexibility: it fails
loudly on a malformed catalogue rather than silently degrading.

**Why priors + bounded corroboration instead of a learned model?** The spec
requires the engine to run in the base environment with zero weights, to be
deterministic, and to explain itself. A catalogue prior adjusted by small,
documented, additive bonuses is a pure, auditable function of its inputs, and
every emitted number carries the human-readable `reason` that produced it. The
corroboration bonuses are deliberately **small and bounded** so evidence *nudges*
a prior rather than overwhelming it — a serial number makes a mainboard slightly
more certain, it does not invent one.

**Why does `UNKNOWN` hazard not corroborate?** The hazard signal exists to let two
independent engines *agree*: if recoverability found a concrete hazard, a
catalogue component flagged hazardous is more likely to actually be the source.
`NONE` is a positive "no hazard here" finding and `UNKNOWN` is "we could not tell"
— neither is positive evidence *for* a hazardous component, so neither raises its
presence. This mirrors the recoverability engine's own rule that `UNKNOWN` never
masks a concrete hazard finding.

**Why blend the two upstream confidences and then damp multiplicatively?** The
component inventory's trustworthiness depends on both how sure fusion was about
the device *and* how sure recoverability was about its assessment, so a weighted
**blend** of the two is the honest base. The unknown-type and conflict signals are
independent reasons to trust the inventory *less*, and multiplicative factors let
them **compound** — an unknown, conflicted device is more doubtful than either
signal alone — at the same 6-decimal precision the fusion and recoverability
engines use, so the three engines' numbers compose cleanly.

**Why `TYPE_CHECKING`-only imports of `DeviceContext`, `RecoverabilityReport` and
`Settings`?** The domain layer must not couple to the fusion, recoverability or
settings modules at runtime (that would create import cycles and drag transitive
dependencies into a pure component). Typing both upstream reports under
`TYPE_CHECKING` and passing them in mirrors the M1.7/M1.8 precedent and keeps
`components/` importable on its own. (The single runtime import — the
`HazardLevel` enum — is unavoidable: the engine must compare against its members
to test the hazard signal.)

**Why an injected service + clock + library?** `ComponentService` wires config +
library + inference into the single `analyze(context, recoverability)` operation
downstream code depends on. Every collaborator is injected, so the whole engine is
exercised deterministically in tests with a hand-built context and report — no
fusion run, no models — a `clock=None` keeps the report a pure function of its
inputs when timestamps are not wanted, and an injected library lets the tests run
the engine against a bespoke catalogue without touching disk.

---

_Part of **EcoTrace India** — IEEE YESIST 2026. See the module
[`README.md`](../../README.md) and the platform-wide `docs/engineering/`
standards._
