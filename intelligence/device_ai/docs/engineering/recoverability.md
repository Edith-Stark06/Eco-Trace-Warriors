# Recoverability Intelligence Engine (M1.8)

> The first **downstream consumer** of the Device Intelligence Engine: an
> internal-only, **deterministic rule engine** that turns the immutable
> `DeviceContext` produced by the **fusion engine** (M1.7) into an explainable
> **`RecoverabilityReport`** — normalized repairability / reusability /
> recyclability scores, a hazard level, an aggregated confidence and a
> recommended end-of-life action, each backed by ordered human-readable
> reasoning and warnings. It ships **no new endpoint** and leaves the `/predict`
> API contract **unchanged and backward-compatible**.

**Module:** `intelligence/device_ai`
**Milestone:** M1.8 — Recoverability Intelligence Engine
**Status:** implemented; internal-only (no router, no HTTP surface)

---

## Table of contents

1. [Scope](#scope)
2. [Architecture](#architecture)
3. [Domain models](#domain-models)
4. [Device profiles](#device-profiles)
5. [Rule engine](#rule-engine)
6. [Scoring & confidence aggregation](#scoring--confidence-aggregation)
7. [Recommended-action decision table](#recommended-action-decision-table)
8. [Configuration](#configuration)
9. [Testing](#testing)
10. [Integration guide](#integration-guide)
11. [Worked examples](#worked-examples)
12. [Backward compatibility](#backward-compatibility)
13. [Design rationale](#design-rationale)

---

## Scope

M1.8 is the first component that **consumes** the fusion engine's output. Fusion
(M1.7) produces an immutable `DeviceContext`; recoverability answers the next
question: *"given what we now know about this device, what should happen to it at
end of life?"* Every disposition the engine advises is derived from **four
deterministic signals**, never from learned models:

| # | Signal | Source | Effect on the report |
|---|---|---|---|
| 1 | **Device-type profile** | `profiles.py` knowledge table | Seeds baseline repairability / reusability / recyclability + intrinsic hazard + battery flag. |
| 2 | **Identity completeness** | `context.model` / `.serial_number` / `.imei` | Raises reuse & repair when present (trackable, wipeable, parts identifiable); warns when absent. |
| 3 | **Hazard escalation** | profile `hazard` + battery flag | Raises the hazard floor (CRT leaded glass, standalone batteries → `HIGH`; embedded batteries → `MEDIUM`). |
| 4 | **Fusion confidence & conflicts** | `context.confidence` / `.has_conflicts` | Damps the report confidence; can force `MANUAL_REVIEW`. |

**Explicitly in scope**

- `RecoverabilityReport` — the normalized, immutable outcome.
- A modular `Rule` set emitting uniform, additive `RuleOutcome`s.
- A pure `ScoringEngine` fold (summed/clamped dimensions, hazard max,
  product-of-factors confidence, decision table).
- An injected `RecoverabilityService` orchestration facade.

**Explicitly out of scope** (do **not** implement in M1.8): Material Intelligence,
Carbon Intelligence, blockchain anchoring, the Digital Device Passport, and
**learned** damage classification. The engine is **internal only** — no router is
mounted, `application.py` is untouched, and the `/predict` response schema is
**unchanged**.

**Key input constraint.** `DeviceContext` exposes only **identity** attributes
(device type, brand, model, serial/IMEI/MAC) plus aggregate `confidence`,
`conflicts`/`has_conflicts` and provenance. It carries **no condition and no
material** fields (those are out-of-scope M1.9 concerns). The recoverability
engine therefore derives its assessment from the four signals above **only** —
never from condition or material composition.

## Architecture

The engine is a **pure domain layer** with the same shape as `fusion/`,
`fingerprint/` and `ocr/`: frozen slotted dataclasses, stateless engines, and an
injected service. It imports the fusion `DeviceContext` **only under
`TYPE_CHECKING`** (and the settings `Settings` likewise), so there is no runtime
coupling and no import cycle — the context is passed in, never reached into.

```
             fusion engine (M1.7) — an immutable DeviceContext
                                   │
                                   ▼
            ┌──────────── recoverability/ (internal) ─────────────┐
            │  service.py  RecoverabilityService.assess(context)   │
            │        │          │           │                      │
            │        ▼          ▼           ▼                      │
            │   profiles.py  rules.py   scoring.py                 │
            │   profile_for  RuleEngine  ScoringEngine             │
            │   (device-type  (7 rules,  (fold: summed deltas,     │
            │    table +      ordered)   max hazard, product of    │
            │    aliases)                confidence factors,       │
            │                           decision table)            │
            │        └──────────┬──────────┘                       │
            │                   ▼                                  │
            │     models.py  RecoverabilityReport (frozen)         │
            │     HazardLevel · RecommendedAction · RuleOutcome    │
            └──────────────────────────────────────────────────────┘
                                   ▼
              downstream AI (M1.9+ material/carbon) — never /predict
```

Layering (dependencies point downward, never upward):

```
fusion/      (M1.7 — produces the immutable DeviceContext)
   ↓  (TYPE_CHECKING only; the context is passed in)
recoverability/  (models.py + profiles.py + rules.py + scoring.py + service.py)
   ↓
exceptions · configs   (cross-cutting foundations)
```

The package contains **no HTTP imports, no FastAPI, no I/O**. `assess()` is a
pure function of its inputs except for the injected clock (which defaults to UTC
`now` and can be replaced or disabled for determinism).

## Domain models

`recoverability/models.py` defines the vocabulary that makes an assessment
auditable.

### `HazardLevel`

```python
class HazardLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"
```

A `str` enum so members serialize directly to their wire value. Severity
combines through the module-level `_HAZARD_ORDER` table and the
`max_hazard(*levels)` helper — never by definition order. `UNKNOWN` sits just
above `NONE` (it signals "needs review") but **never masks** a concrete
`LOW`/`MEDIUM`/`HIGH` finding; `None` entries (a rule asserting no hazard floor)
are ignored.

### `RecommendedAction`

```python
class RecommendedAction(str, Enum):
    REFURBISH = "refurbish"
    REPAIR = "repair"
    RECYCLE = "recycle"
    HAZARDOUS_DISPOSAL = "hazardous_disposal"
    MANUAL_REVIEW = "manual_review"
```

Member order is **not** semantic — the scoring engine selects the action from an
explicit decision table (below).

### `RuleOutcome`

The uniform, additive contribution one rule makes. Because every rule speaks
this single language, rules stay small and reorderable and the scoring engine
stays purely arithmetic:

```python
@dataclass(frozen=True, slots=True)
class RuleOutcome:
    rule: str                      # machine-readable name of the emitting rule
    reason: str                    # human-readable explanation (always set)
    repairability_delta: float = 0.0
    reusability_delta: float = 0.0
    recyclability_delta: float = 0.0
    hazard_floor: HazardLevel | None = None
    confidence_factor: float = 1.0
    warning: str | None = None
    force_action: RecommendedAction | None = None

    def to_dict(self) -> dict[str, object]: ...
```

### `RecoverabilityReport`

The normalized, immutable outcome produced by the service:

```python
@dataclass(frozen=True, slots=True)
class RecoverabilityReport:
    device_type: str
    repairability: float          # in [0, 1]
    reusability: float            # in [0, 1]
    recyclability: float          # in [0, 1]
    hazard_level: HazardLevel
    confidence: float             # in [0, 1]
    recommended_action: RecommendedAction
    reasoning: tuple[str, ...]    # ordered reasons, in rule order
    warnings: tuple[str, ...]     # ordered operator cautions (may be empty)
    eco_id: str = ""              # carried over from the context
    engine_version: str = ""
    created_at: datetime | None = None

    def to_dict(self) -> dict[str, object]: ...
```

Like every domain object, the report is frozen and slotted — attempting to
mutate it raises `FrozenInstanceError`.

## Device profiles

`recoverability/profiles.py` holds the deterministic, hand-curated knowledge the
engine has about a **class** of device before it looks at any specific unit.

```python
@dataclass(frozen=True, slots=True)
class DeviceProfile:
    device_type: str              # canonical type (or caller label for unknown)
    repairability: float          # baseline ease-of-repair in [0, 1]
    reusability: float            # baseline fitness-for-reuse in [0, 1]
    recyclability: float          # baseline material-recovery in [0, 1]
    hazard: HazardLevel           # intrinsic hazard (independent of battery)
    has_battery: bool             # class typically embeds a battery
    known: bool = True            # False only for the unknown fallback
    notes: str = ""               # rationale for the baseline (provenance)
```

The `_DEFAULT_PROFILES` table covers **19 curated classes** — laptop, smartphone,
tablet, desktop, server, monitor, crt_monitor, television, printer, keyboard,
mouse, router, power_supply, cable, camera, game_console, smartwatch, headphones,
battery — each with deliberate, documented baselines (never learned) and a
human-readable `notes` rationale. The table is intentionally small, explicit and
value-only so it can be audited and extended without touching the rules or
scoring. Representative values:

| Type | Repair | Reuse | Recycle | Hazard | Battery |
|---|---|---|---|---|---|
| laptop | 0.75 | 0.80 | 0.85 | LOW | yes |
| desktop | 0.85 | 0.75 | 0.88 | NONE | no |
| crt_monitor | 0.20 | 0.15 | 0.45 | **HIGH** | no |
| battery | 0.10 | 0.10 | 0.70 | **HIGH** | yes |
| cable | 0.30 | 0.55 | 0.90 | NONE | no |

Every score lies in `[0, 1]` — asserted by the tests. Lookups go through
`profile_for(device_type)`, which is case/whitespace-insensitive and understands
~40 synonyms (`"Laptop Computer"` → laptop, `"cell phone"` → smartphone, `"PC"` →
desktop, `"CRT"` → crt_monitor, …). Anything unrecognized falls back to a copy of
the conservative `_UNKNOWN_PROFILE` (0.30 / 0.30 / 0.40, `hazard=UNKNOWN`,
`known=False`) **stamped with the caller-supplied label** for provenance — which
the `UnknownDeviceRule` turns into a manual-review recommendation.

## Rule engine

`recoverability/rules.py` implements the engine's *signals* as small, independent
`Rule`s. Each reads the fused context plus its resolved profile, applies
threshold/weight logic (always reading values from the injected
`RecoverabilityConfig`, never hardcoding them) and reports zero or more uniform
`RuleOutcome`s. Rules are pure: they mutate nothing and depend only on their
inputs, so they are deterministic and independently testable.

```python
class Rule(ABC):
    name: str = "rule"

    @abstractmethod
    def evaluate(self, context: DeviceContext, profile: DeviceProfile,
                 config: RecoverabilityConfig) -> list[RuleOutcome]: ...
```

The reference rule set runs in a fixed order (matters only for stable
reasoning/warning output):

| Order | Rule | Emits when | Outcome |
|---|---|---|---|
| 1 | `BaselineProfileRule` | always | Seeds the three scores + hazard floor from the profile baseline. |
| 2 | `IdentityCompletenessRule` | any of model/serial/IMEI present | `+reuse` / `+repair` bonuses; reason lists which fields. |
| | | none present | `−reuse` penalty + **warning** (confirm provenance before reuse). |
| 3 | `BatteryHazardRule` | profile `has_battery` | Hazard floor `MEDIUM` (configurable) + `−recycle` penalty. |
| 4 | `HighHazardDisposalRule` | profile hazard `HIGH` (CRT, battery) | Hazard floor `HIGH` + **forces** `HAZARDOUS_DISPOSAL`. |
| 5 | `ConflictPenaltyRule` | `context.has_conflicts` | `×0.80` confidence factor + **warning** (verify identity). |
| 6 | `LowConfidenceRule` | `context.confidence < 0.50` | `×0.60` factor + **forces** `MANUAL_REVIEW` + **warning**. |
| 7 | `UnknownDeviceRule` | `not profile.known` | `×0.70` factor + **forces** `MANUAL_REVIEW` + **warning**. |

`RuleEngine(rules=DEFAULT_RULES)` runs every rule in order and concatenates its
outcomes; the rule set is **injectable**, so a caller can extend, replace or
reorder the assessment logic without touching the scoring engine — the scoring
engine only ever sums deltas, takes the most severe hazard floor, multiplies
confidence factors and reads forced actions.

## Scoring & confidence aggregation

`recoverability/scoring.py` — `ScoringEngine(config)` is the deterministic fold
that turns the flat outcome list into a normalized report. It does **no domain
reasoning of its own**; every judgement lives in a rule, so its job is pure
arithmetic:

- **Dimensions.** Each score is `clamp_round(Σ deltas)` over that dimension,
  clamped to `[0, 1]` and rounded to **six decimals** — the same
  `_SCORE_PRECISION = 6` the fusion engine uses, so the two engines' numbers
  compose cleanly. (The baseline rule contributes the profile baseline as its
  first delta, so the fold naturally starts from the profile.)
- **Hazard.** `max_hazard(*floors)` — the most severe hazard floor any rule
  asserted, with `UNKNOWN` never masking a concrete finding.
- **Confidence aggregation.** The context's own aggregate confidence is scaled by
  **every** rule's multiplicative `confidence_factor`:

  ```
  confidence = clamp_round(context.confidence × Π factorᵢ)
  ```

  Independent damping signals therefore **compound** — a conflicted context that
  is also low-confidence is damped more than either signal alone. A factor of
  `1.0` leaves confidence unchanged.
- **Explanations.** `reasoning` and `warnings` are collected from the outcomes in
  rule order, so the report reads top-to-bottom as the assessment was built.

## Recommended-action decision table

`ScoringEngine._decide_action` selects the action from an **explicit, ordered
table** — the order encodes the engine's priorities, most binding first:

```
1. hazard_level is HIGH            → HAZARDOUS_DISPOSAL
   OR any outcome forces HAZARDOUS_DISPOSAL
2. any outcome forces MANUAL_REVIEW → MANUAL_REVIEW
3. reusability ≥ refurbish_min_reusability (0.65)  → REFURBISH
4. repairability ≥ repair_min_repairability (0.55) → REPAIR
5. recyclability ≥ recycle_min_recyclability (0.45)→ RECYCLE
6. otherwise                        → MANUAL_REVIEW
```

Boundaries are inclusive (`≥`), so a reusability of exactly `0.65` recommends
`REFURBISH` — asserted by the tests. The `HIGH`-hazard override beats a forced
manual review, and a forced disposal beats the score ladder; safety always wins
over scores.

## Configuration

`recoverability/config.py` — `RecoverabilityConfig` is a frozen dataclass and the
**single source of truth** for every tunable number the engine reads. No
threshold is hardcoded in the rules or the scoring engine; behaviour is adjusted
in exactly one place.

| Field | Default | Meaning |
|---|---|---|
| `refurbish_min_reusability` | `0.65` | Reusability at/above which → `REFURBISH`. |
| `repair_min_repairability` | `0.55` | Repairability at/above which → `REPAIR`. |
| `recycle_min_recyclability` | `0.45` | Recyclability at/above which → `RECYCLE`. |
| `low_confidence_threshold` | `0.50` | Fused confidence below which review is forced. |
| `identity_repair_bonus` | `0.10` | Repairability added when model/serial/IMEI present. |
| `identity_reuse_bonus` | `0.10` | Reusability added when identity is complete. |
| `missing_identity_reuse_penalty` | `0.15` | Reusability removed when no identity field at all. |
| `battery_recyclability_penalty` | `0.10` | Recyclability removed for battery separation. |
| `battery_hazard_floor_enabled` | `True` | Battery raises the hazard floor to `MEDIUM`. |
| `conflict_confidence_factor` | `0.80` | Confidence multiplier on fusion conflicts. |
| `low_confidence_factor` | `0.60` | Confidence multiplier when confidence is below threshold. |
| `unknown_device_confidence_factor` | `0.70` | Confidence multiplier for unrecognized types. |

`RecoverabilityConfig.from_settings(settings)` maps the **four
operationally-tunable, env-driven** thresholds onto the config; every other field
keeps its default (still overridable directly in code). `RecoverabilityConfig()`
is always valid, so tests and callers can tweak any field by keyword.

The only new failure type is `RecoverabilityError` (in `exceptions.py`), a
`DeviceAIError` subclass with `code="RECOVERABILITY_ERROR"` and
`http_status=500`. Because the engine is internal-only, this surfaces to the
orchestrating code as a typed exception, not through the HTTP error envelope.

## Testing

All M1.8 tests run in the **base environment** with hand-built frozen
`DeviceContext`s — no images, no models, no fusion run, no filesystem (an
injected `_CLOCK` makes `created_at` deterministic). From
`intelligence/device_ai`:

```bash
pytest tests/test_recoverability_*.py -q
```

- **`tests/test_recoverability_profiles.py`** — the knowledge table: canonical
  lookup, case/whitespace insensitivity, synonym aliases, the unknown fallback
  preserving the caller label, empty-type fallback, the invariants that every
  score is a valid `[0, 1]` probability and every alias points at a real key,
  HIGH-hazard classes flagged (CRT, battery), immutability.
- **`tests/test_recoverability_rules.py`** — each rule in isolation against a
  hand-built context, asserting exactly the outcome it should emit (score deltas,
  hazard floor, confidence factor, forced action, warning) and that it stays
  **silent** when its trigger is absent; plus the `RuleEngine` running all rules
  in order, accepting a custom rule set, and being deterministic.
- **`tests/test_recoverability_scoring.py`** — dimension folding (summed /
  clamped / rounded — `0.1 + 0.2 == 0.3`), hazard max, confidence aggregation
  (product of factors, compounding), and **every** branch of the
  recommended-action decision table (HIGH-hazard override beats forced review;
  refurbish boundary inclusive; MANUAL_REVIEW fallthrough).
- **`tests/test_recoverability_service.py`** — end-to-end `assess()` across a
  healthy identifiable laptop (REFURBISH + MEDIUM hazard), a hazardous CRT
  (HAZARDOUS_DISPOSAL + HIGH), a standalone battery, a conflicted context
  (damped confidence + warning), a low-confidence context (forced MANUAL_REVIEW),
  partial identity (warning) and an unknown device (MANUAL_REVIEW + UNKNOWN
  hazard); plus determinism (`to_dict` equal for identical input), provenance
  carry-over (eco_id / engine_version / created_at), JSON shape, report
  immutability and custom-config exposure.

## Integration guide

The recoverability engine is a **library**, wired by construction — there is
nothing to mount and no endpoint to call. A future orchestrator chains it onto
fusion like this:

```python
from device_ai.fusion import FusionEngine
from device_ai.recoverability import RecoverabilityService

# 1. Fuse the perception engines into an immutable context (M1.7).
context = FusionEngine().fuse_modules(
    detection=detector.detect(images),                 # M1.4 DetectionResult
    fingerprint=fingerprint_service.generate(images),  # M1.5 DeviceFingerprint
    ocr=ocr_service.extract(images),                   # M1.6 OCRExtraction
)

# 2. Assess its recoverability (M1.8). All collaborators are injected, so
#    the service is constructible as-is or with a fixed clock / custom config.
report = RecoverabilityService().assess(context)

report.device_type           # "laptop"
report.reusability           # e.g. 0.9
report.hazard_level          # HazardLevel.MEDIUM
report.recommended_action    # RecommendedAction.REFURBISH
report.reasoning             # ordered, human-readable explanations
report.warnings              # operator-facing cautions (may be empty)
report.to_dict()             # fully serializable
```

To tune operationally (e.g. require a higher reuse bar), build the service with
a settings-driven config:

```python
from device_ai.configs.settings import get_settings
from device_ai.recoverability import RecoverabilityConfig, RecoverabilityService

config  = RecoverabilityConfig.from_settings(get_settings())
service = RecoverabilityService(config=config)
```

## Worked examples

### Identifiable laptop — recommends refurbish

A fused laptop with model + serial, `confidence=0.9`:

```python
report = RecoverabilityService().assess(context)
report.to_dict()
```

```json
{
  "eco_id": "ET-2026-1A2B3C4D",
  "device_type": "laptop",
  "repairability": 0.85,
  "reusability": 0.9,
  "recyclability": 0.75,
  "hazard_level": "medium",
  "confidence": 0.9,
  "recommended_action": "refurbish",
  "reasoning": [
    "Device-type profile for 'laptop' establishes baseline recoverability: repairability 75%, reusability 80%, recyclability 85%.",
    "Identity is complete (model, serial number): the device is trackable, wipeable and its parts identifiable, improving repair and reuse prospects.",
    "Device class carries a battery: it must be handled and transported as hazardous and the battery separated before material recovery."
  ],
  "warnings": [],
  "engine_version": "1.0.0",
  "created_at": "2026-08-01T12:00:00+00:00"
}
```

`0.75 + 0.10` repairability and `0.80 + 0.10` reusability (identity bonuses);
recyclability `0.85 − 0.10` (battery separation); hazard floor `MEDIUM` from the
battery. Reusability `0.90 ≥ 0.65` → `REFURBISH`.

### CRT monitor — forces hazardous disposal

```json
{
  "eco_id": "ET-2026-1A2B3C4D",
  "device_type": "crt_monitor",
  "repairability": 0.3,
  "reusability": 0.25,
  "recyclability": 0.45,
  "hazard_level": "high",
  "confidence": 0.9,
  "recommended_action": "hazardous_disposal",
  "reasoning": [
    "Device-type profile for 'crt_monitor' establishes baseline recoverability: repairability 20%, reusability 15%, recyclability 45%.",
    "Identity is complete (model): the device is trackable, wipeable and its parts identifiable, improving repair and reuse prospects.",
    "'crt_monitor' carries an intrinsic high hazard (e.g. leaded glass, phosphors, live cells) and must be disposed of through the hazardous waste stream."
  ],
  "warnings": [],
  "engine_version": "1.0.0",
  "created_at": "2026-08-01T12:00:00+00:00"
}
```

The `HIGH` hazard floor short-circuits the ladder: even the `+0.10` identity
bonuses cannot route this device anywhere but the hazardous waste stream.

### Missing identity — warns the operator

A laptop with no model/serial/IMEI:

```json
{
  "eco_id": "ET-2026-1A2B3C4D",
  "device_type": "laptop",
  "repairability": 0.75,
  "reusability": 0.65,
  "recyclability": 0.75,
  "hazard_level": "medium",
  "confidence": 0.9,
  "recommended_action": "refurbish",
  "warnings": [
    "Missing identity: model, serial number and IMEI are all unknown. Confirm provenance before reuse."
  ]
}
```

`0.80 − 0.15` reusability from the missing-identity penalty (`0.65` still clears
the refurbish floor), and the operator is told to confirm provenance before
reuse.

### Low confidence — refuses to guess

The same laptop at `confidence=0.2`:

```json
{
  "repairability": 0.85,
  "reusability": 0.9,
  "recyclability": 0.75,
  "hazard_level": "medium",
  "confidence": 0.12,
  "recommended_action": "manual_review",
  "warnings": [
    "Low fused confidence; manual review required before disposition."
  ]
}
```

Scores are untouched, but the confidence is damped `0.2 × 0.6 = 0.12` and the
engine **forces** `MANUAL_REVIEW` — it never guesses a disposition on weak
evidence.

## Backward compatibility

The `/predict` contract is **completely unchanged**. M1.8 mounts **no router**,
adds **no endpoint**, and does not touch `application.py`, the `/predict`
pipeline, or any existing schema. The recoverability engine is imported and used
only where a future orchestrator chooses to — it is invisible to every current
caller.

The four new environment variables are **opt-in** with defaults that reproduce
the reference behaviour (`RECOVERABILITY_REFURBISH_MIN_REUSABILITY=0.65`,
`RECOVERABILITY_REPAIR_MIN_REPAIRABILITY=0.55`,
`RECOVERABILITY_RECYCLE_MIN_RECYCLABILITY=0.45`,
`RECOVERABILITY_LOW_CONFIDENCE_THRESHOLD=0.50`), so an existing deployment that
sets none of them behaves exactly as before. The full pre-existing test suite
(including the `/predict` backward-compatibility guards from M1.4–M1.7) passes
unchanged alongside the 59 new M1.8 tests.

## Design rationale

**Why rules instead of a learned classifier?** The spec requires the engine to
run in the base environment with zero weights, to be deterministic, and to
explain itself. Rules are pure, auditable functions of their inputs; a learned
damage classifier is explicitly out of scope. The rule set is also
**extensible** — a future material or condition signal joins by adding one small
`Rule`, with no change to the scoring fold.

**Why a uniform `RuleOutcome`?** The scoring engine folds outcomes by summing
deltas, taking the most severe hazard floor, multiplying confidence factors and
reading forced actions — it never branches on which rule fired. That uniform,
additive contribution is what keeps rules modular and the scoring engine pure
and fully predictable.

**Why `max_hazard` with `UNKNOWN` ranked just above `NONE`?** An unknown hazard
must demand review (hence above `NONE`) but must never mask an evidenced
`LOW`/`MEDIUM`/`HIGH` floor (a known hazard always wins over uncertainty). The
`_HAZARD_ORDER` table makes that rank explicit and testable instead of relying on
enum definition order.

**Why multiply confidence factors rather than average them?** Independent damping
signals should compound: a conflicted context that is also low-confidence is
*more* uncertain than either signal alone, and a product expresses exactly that.
Fusion already models the *raising* side (noisy-OR agreement); recoverability
models the *damping* side, and the two compose cleanly at the same 6-decimal
precision.

**Why an explicit ordered decision table instead of a score?** The disposition
must be explainable ("hazard is HIGH, so it is hazardous waste") and safe by
construction (safety overrides always beat the score ladder). Encoding that as a
documented, tested, ordered table — with `HIGH` hazard first and manual review as
the honest fallthrough — makes the priority explicit and reviewable, and keeps
the boundary thresholds configurable in one place.

**Why `TYPE_CHECKING`-only imports of `DeviceContext` and `Settings`?** The
domain layer must not couple to the fusion or settings modules at runtime (that
would create import cycles and drag transitive dependencies into a pure
component). Typing the context under `TYPE_CHECKING` and passing it in mirrors
the M1.7 fusion precedent and keeps `recoverability/` importable on its own.

**Why an injected service + clock?** `RecoverabilityService` wires config +
rules + scoring into the single `assess(context)` operation downstream code
depends on. Every collaborator is injected, so the whole engine is exercised
deterministically in tests with a hand-built context — no fusion run, no models,
no filesystem — and a `clock=None` keeps the report a pure function of its
inputs when timestamps are not wanted.

---

_Part of **EcoTrace India** — IEEE YESIST 2026. See the module
[`README.md`](../../README.md) and the platform-wide `docs/engineering/`
standards._
