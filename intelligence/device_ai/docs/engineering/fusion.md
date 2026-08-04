# Multi-Modal Device Intelligence Fusion Engine (M1.7)

> The **fusion layer** of the Device Intelligence Engine: an internal-only engine
> that merges the outputs of the **detector** (M1.4), the **fingerprint** engine
> (M1.5) and the **OCR** engine (M1.6) into a single, normalized, **immutable**
> `DeviceContext`. It aggregates confidence across heterogeneous evidence, detects
> conflicts between modules (e.g. a detected device type that disagrees with an
> OCR-read identity), and produces one canonical device view for downstream AI —
> **without changing the `/predict` API contract and without exposing any new
> endpoint**.

**Module:** `intelligence/device_ai`
**Milestone:** M1.7 — Multi-Modal Fusion Engine
**Status:** implemented; internal-only (no router, no HTTP surface)

---

## Table of contents

1. [Scope](#scope)
2. [Architecture](#architecture)
3. [Evidence abstraction](#evidence-abstraction)
4. [Attribute space](#attribute-space)
5. [Evidence builders](#evidence-builders)
6. [The `DeviceContext` model](#the-devicecontext-model)
7. [Fusion engine](#fusion-engine)
8. [Confidence aggregation](#confidence-aggregation)
9. [Conflict detection](#conflict-detection)
10. [Configuration](#configuration)
11. [Testing](#testing)
12. [Integration guide](#integration-guide)
13. [Worked examples](#worked-examples)
14. [Backward compatibility](#backward-compatibility)
15. [Design rationale](#design-rationale)

---

## Scope

M1.7 adds a **fusion layer** on top of the three perception engines already in the
service. Each of those engines answers a narrow question in isolation:

| Engine | Milestone | Answers |
|---|---|---|
| Detector | M1.4 | *what kind of device is this, and roughly which brand?* |
| Fingerprint | M1.5 | *what stable identity/provenance does the embedding carry?* |
| OCR | M1.6 | *what text identity is printed on it (brand, model, serial, IMEI, MAC)?* |

Those answers **overlap** (all three can assert a brand) and can **disagree** (the
detector says "Laptop" while OCR reads a phone's IMEI). The fusion engine is the
component that reconciles them: it maps every module's native output onto a shared
**attribute space**, combines the per-attribute confidences, resolves a single
winning value per attribute, records any disagreement as a first-class
**`Conflict`**, and emits an immutable `DeviceContext` that downstream AI
(recoverability, material, carbon — future milestones) can consume as *the* device
view.

**Explicitly in scope**

- `DeviceContext` — the unified, immutable device model.
- `Evidence` / `Claim` — the abstraction each engine contributes.
- `FusionEngine` — merges detection + fingerprint + OCR evidence.
- Cross-module confidence aggregation and conflict detection.

**Explicitly out of scope** (do **not** implement in M1.7): Recoverability AI,
Material Intelligence, Carbon Intelligence, blockchain anchoring, the Digital
Device Passport. The fusion engine is **internal only** — no router is mounted,
`application.py` is untouched, and the `/predict` response schema is **unchanged**.

## Architecture

The fusion engine is a **pure domain layer**. It reuses the frozen result objects
the three engines already produce (`DetectionResult`, `DeviceFingerprint`,
`OCRExtraction` / `OCRIdentity`) and **imports them only under `TYPE_CHECKING`** —
so the fusion package has no runtime coupling to `inference/`, `fingerprint/` or
`ocr/`, and nothing is duplicated.

```
        ┌──────────── perception engines (M1.4 / M1.5 / M1.6) ────────────┐
        │  Detector          Fingerprint            OCR                     │
        │  DetectionResult   DeviceFingerprint      OCRExtraction/Identity  │
        └──────┬──────────────────┬───────────────────────┬───────────────┘
               │                  │                        │
               ▼                  ▼                        ▼      (build evidence)
        ┌───────────────────────── fusion/ (internal) ─────────────────────┐
        │  from_detection()   from_fingerprint()   from_ocr()/from_ocr_    │
        │        │                  │               identity()             │
        │        └───────────┬──────┴───────────────────┬──────────────────┘
        │                    ▼                           ▼                  │
        │              Evidence(source, module, confidence, claims=(…))     │
        │                    │  Claim(attribute, value, confidence, source) │
        │                    ▼                                              │
        │   FusionEngine.fuse(evidence) / fuse_modules(detection,…)         │
        │        _resolve_attributes():                                     │
        │          group claims by attribute → group by normalized value    │
        │          noisy-OR per value · support-share damping · winner      │
        │          conflicted = (≥2 distinct value-groups)                  │
        │                    ▼                                              │
        │   DeviceContext (frozen):                                         │
        │     eco_id, fingerprint, attributes(ResolvedAttribute…),          │
        │     confidence, evidence(…), conflicts(Conflict…),                │
        │     source_hashes, engine_version, created_at                     │
        └──────────────────────────────────────────────────────────────────┘
                                   ▼
                    downstream AI (future milestones) — never /predict
```

Layering (dependencies point downward, never upward):

```
inference/ · fingerprint/ · ocr/     (perception engines — produce result objects)
   ↓  (TYPE_CHECKING only; builders import lazily at call time)
fusion/                              (models.py + engine.py — pure domain)
   ↓
exceptions · utils/configs           (cross-cutting foundations)
```

The fusion package contains **no HTTP imports, no FastAPI, no I/O**. It is a set of
frozen dataclasses plus a stateless engine, exactly like the `fingerprint/` and
`ocr/` domain layers.

## Evidence abstraction

Every engine contributes to fusion through one uniform abstraction: an `Evidence`
record carrying zero or more `Claim`s. This is the seam that lets heterogeneous
modules be compared on equal footing.

```python
class EvidenceKind(str, Enum):
    DETECTION = "detection"
    FINGERPRINT = "fingerprint"
    OCR = "ocr"


@dataclass(frozen=True, slots=True)
class Claim:
    attribute: FusionAttribute   # what is being asserted (device_type, brand, …)
    value: str                   # the asserted value ("Laptop", "Dell", …)
    confidence: float            # this module's confidence in [0, 1]
    source: EvidenceKind         # which engine asserted it

    @property
    def key(self) -> str:
        """Case/whitespace-normalized value for grouping equal claims."""
        return " ".join(self.value.split()).casefold()


@dataclass(frozen=True, slots=True)
class Evidence:
    source: EvidenceKind
    module_name: str             # "detector" | "clip"/"fingerprint" | "ocr"
    module_version: str
    confidence: float            # module-level confidence
    claims: tuple[Claim, ...] = ()

    def claim_for(self, attribute: FusionAttribute) -> Claim | None: ...
    def to_dict(self) -> dict[str, object]: ...
```

A `Claim` is a single `(attribute, value, confidence)` assertion tagged with its
`source`. Its `key` property normalizes case and internal whitespace so that
`"Dell"`, `"dell"` and `" Dell "` all collapse to the same group during
resolution — agreement across modules is detected on **meaning**, not on exact
bytes.

## Attribute space

All modules are projected onto one shared enumeration. The declaration order is
also the **resolution/output order**, so a `DeviceContext`'s attributes are always
listed deterministically:

```python
class FusionAttribute(str, Enum):
    DEVICE_TYPE = "device_type"
    BRAND = "brand"
    MODEL = "model"
    SERIAL_NUMBER = "serial_number"
    IMEI = "imei"
    MAC_ADDRESS = "mac_address"

    @classmethod
    def values(cls) -> tuple[FusionAttribute, ...]:
        return tuple(cls)
```

The mapping onto this space is where "detector *brand*", "OCR *manufacturer*" and
"fingerprint *brand*" are recognized as the **same attribute** — the precondition
for cross-module agreement and conflict detection.

| `FusionAttribute` | Detector | Fingerprint | OCR |
|---|---|---|---|
| `DEVICE_TYPE` | `device_type` | `device_type` (provenance) | — |
| `BRAND` | `brand` | `brand` / identity `manufacturer` | `MANUFACTURER` field |
| `MODEL` | — | identity `model` | `MODEL` field |
| `SERIAL_NUMBER` | — | identity `serial_number` | `SERIAL_NUMBER` field |
| `IMEI` | — | identity `imei` | `IMEI` field |
| `MAC_ADDRESS` | — | identity `mac_address` | `MAC_ADDRESS` field |

## Evidence builders

`fusion/models.py` provides pure builder functions — one per engine — that turn a
frozen result object into an `Evidence` record. Each **drops placeholder values**
(`""`, `"unknown"`, `"n/a"`, `"none"`, and the detector's `"Unknown"` brand) at
build time, so spurious claims never reach resolution and never manufacture a
conflict.

```python
def from_detection(result: DetectionResult) -> Evidence
def from_fingerprint(fingerprint: DeviceFingerprint) -> Evidence
def from_ocr(extraction: OCRExtraction) -> Evidence
def from_ocr_identity(identity: OCRIdentity, *, confidence: float = 0.80,
                      module_name: str = "ocr", module_version: str = "") -> Evidence
```

- **`from_detection`** — emits `DEVICE_TYPE` and `BRAND` claims at the detection's
  own `result.confidence`; skips the `"Unknown"` brand placeholder and any empty
  device type. `module_name="detector"`.
- **`from_fingerprint`** — surfaces the fingerprint's carried `device_type` / `brand`
  **provenance** plus any identity fields, each at a fixed low
  `_FINGERPRINT_PROVENANCE_CONFIDENCE = 0.50` (provenance is a weak signal, not a
  fresh reading). Brand is de-duplicated so an explicit `brand` wins over an
  identity `manufacturer`. Module confidence is the mean of its claims (or `1.0`
  when it carries none).
- **`from_ocr`** — maps each `ExtractedField` onto its attribute
  (`MANUFACTURER→BRAND`, `MODEL→MODEL`, `SERIAL_NUMBER`, `IMEI`, `MAC_ADDRESS`)
  using **that field's own confidence**; `QR_CODE` / `BARCODE` field types are
  ignored (they are transport, not identity). Module confidence is the mean of the
  mapped claim confidences.
- **`from_ocr_identity`** — maps the small `OCRIdentity` projection's non-empty
  fields at a single shared confidence (default `0.80`), for callers that already
  hold an identity rather than a full extraction.

## The `DeviceContext` model

The engine's output is a single frozen, slotted value object — immutable by
construction, safe to share across downstream consumers:

```python
@dataclass(frozen=True, slots=True)
class ResolvedAttribute:
    attribute: FusionAttribute
    value: str
    confidence: float                     # aggregated, in [0, 1]
    sources: tuple[EvidenceKind, ...]      # which engines supported the winner
    conflicted: bool = False

    @property
    def agreed(self) -> bool:              # >1 source AND not conflicted
        return len(self.sources) > 1 and not self.conflicted


@dataclass(frozen=True, slots=True)
class Conflict:
    attribute: FusionAttribute
    resolved_value: str                    # the value fusion chose
    claims: tuple[Claim, ...]              # every competing claim (ranked)

    @property
    def sources(self) -> tuple[EvidenceKind, ...]: ...


@dataclass(frozen=True, slots=True)
class DeviceContext:
    eco_id: str
    fingerprint: str
    attributes: tuple[ResolvedAttribute, ...]
    confidence: float                      # mean of resolved-attribute confidences
    evidence: tuple[Evidence, ...]         # full provenance (every contribution)
    conflicts: tuple[Conflict, ...]
    source_hashes: tuple[str, ...]
    engine_version: str
    created_at: datetime | None = None

    def get(self, attribute: FusionAttribute) -> ResolvedAttribute | None: ...
    def value_of(self, attribute: FusionAttribute) -> str: ...
    def confidence_of(self, attribute: FusionAttribute) -> float: ...

    # Convenience accessors
    @property
    def device_type(self) -> str: ...
    @property
    def brand(self) -> str: ...
    @property
    def model(self) -> str: ...
    @property
    def serial_number(self) -> str: ...
    @property
    def imei(self) -> str: ...
    @property
    def mac_address(self) -> str: ...

    @property
    def has_conflicts(self) -> bool: ...
    def to_dict(self) -> dict[str, object]: ...
```

`DeviceContext` keeps **both** the resolved view (`attributes`) *and* the full
`evidence` trail, so any downstream decision is auditable back to the module that
produced it. Because every field is a frozen dataclass or an immutable tuple,
attempting to mutate a context raises `FrozenInstanceError`.

## Fusion engine

`fusion/engine.py` — `FusionEngine`, a stateless orchestrator with two entry
points and an injected clock (so `created_at` is deterministic in tests):

```python
FUSION_ENGINE_VERSION = "1.0.0"


class FusionEngine:
    def __init__(self, *, engine_version: str = FUSION_ENGINE_VERSION,
                 clock: Callable[[], datetime] | None = None) -> None: ...

    def fuse(self, evidence: Iterable[Evidence], *, eco_id: str = "",
             fingerprint: str = "", source_hashes: tuple[str, ...] = ()) -> DeviceContext:
        """Pure core: merge already-built Evidence into a DeviceContext."""

    def fuse_modules(self, *, detection: DetectionResult | None = None,
                     fingerprint: DeviceFingerprint | None = None,
                     ocr: OCRExtraction | None = None,
                     source_hashes: tuple[str, ...] = ()) -> DeviceContext:
        """Convenience: build Evidence from raw module results, then fuse()."""
```

- **`fuse(evidence, …)`** is the pure core: it takes any iterable of `Evidence`
  and resolves it. An empty iterable yields an **empty context** (no attributes,
  `confidence = 0.0`, no conflicts) rather than an error — "missing evidence" is a
  valid, well-defined state.
- **`fuse_modules(detection=…, fingerprint=…, ocr=…)`** is the ergonomic wrapper
  the orchestrator uses: it calls the appropriate builder for each non-`None`
  result, carries `eco_id` / `fingerprint` from the `DeviceFingerprint` when
  present, and falls back to the fingerprint's `source_hashes` when the caller does
  not supply its own. Any subset of the three modules may be provided.

Internally, `_resolve_attributes` iterates `FusionAttribute` in declaration order;
for each attribute it gathers every matching `Claim`, groups them by `claim.key`,
computes a combined confidence per value group (noisy-OR), selects the winning
group by a **total ordering**, and — when more than one distinct value group exists
— records a `Conflict`. This makes fusion **deterministic**: identical evidence
always resolves to an identical `DeviceContext`.

## Confidence aggregation

Fusion combines confidences across **heterogeneous** evidence with two composable
rules, both clamped and rounded to `_CONFIDENCE_PRECISION = 6` decimals inside
`[0, 1]`.

**1. Agreement → noisy-OR.** Independent sources asserting the *same* value
reinforce each other:

```python
def _noisy_or(confidences):
    product = 1.0
    for c in confidences:
        product *= (1.0 - clamp(c))
    return 1.0 - product          # 1 − Π(1 − cᵢ)
```

Two independent `0.8` claims combine to `1 − (0.2 × 0.2) = 0.96` — higher than
either alone. Agreement raises confidence, exactly as intended.

**2. Disagreement → support-share damping.** When several *different* values
compete for one attribute, the winner's confidence is scaled by its **share** of
the total combined confidence:

```
combined[value] = noisy_or(confidences of all claims for that value)
support_share    = combined[winner] / Σ combined[value]
confidence       = clamp_round(combined[winner] × support_share)
```

A lone dissenting module drags the winner **below** its raw confidence — the
context honestly reflects that the modules did not agree. With no dissent
(`support_share = 1.0`) the value passes through the noisy-OR result unchanged.

**3. Context-level confidence.** `DeviceContext.confidence` is the **mean** of the
resolved-attribute confidences (`0.0` when there are none) — a single normalized
number summarizing how strong and how consistent the fused evidence was.

## Conflict detection

An attribute is **conflicted** when, after value-normalization, two or more
*distinct* value groups claim it — e.g. the detector inferring a `Laptop` device
type whose brand disagrees with an OCR-read manufacturer, or two modules reading
different serials. The engine:

1. Selects a winner via `_select_winner`, ranked by
   `(combined_confidence, claim_count, module_order)` — a total order, so ties
   break deterministically (more supporting claims win; then earlier module order).
2. Sets `ResolvedAttribute.conflicted = True` and damps its confidence by support
   share (above), so a contested attribute is never over-confident.
3. Emits a `Conflict(attribute, resolved_value, claims)` capturing **every**
   competing claim, sorted by `(-confidence, source order)`, for full auditability.

`DeviceContext.has_conflicts` and `.conflicts` expose the disagreements to
downstream consumers, which can choose to trust, re-image, or escalate.

## Configuration

**None.** M1.7 introduces **no new environment variables and no settings changes**.
The fusion engine is a pure, in-process domain component with only two tunable
constants, both defined in code:

| Constant | Value | Meaning |
|---|---|---|
| `FUSION_ENGINE_VERSION` | `"1.0.0"` | Stamped onto every `DeviceContext` for provenance. |
| `_CONFIDENCE_PRECISION` | `6` | Decimal places all fused confidences round to. |
| `_FINGERPRINT_PROVENANCE_CONFIDENCE` | `0.50` | Weight of fingerprint-carried provenance claims. |
| `_OCR_IDENTITY_DEFAULT_CONFIDENCE` | `0.80` | Default weight for `from_ocr_identity`. |

The only failure type is `FusionError` (in `exceptions.py`), a `DeviceAIError`
subclass with `code="FUSION_ERROR"` and `http_status=500`. Because the engine is
internal-only, this surfaces to the orchestrating code as a typed exception, not
through the HTTP error envelope.

## Testing

All M1.7 tests run in the **base environment** with directly constructed frozen
result objects — no images, no backends, no clock (an injected `_FIXED_CLOCK` makes
`created_at` deterministic). From `intelligence/device_ai`:

```bash
pytest tests/test_fusion_models.py tests/test_fusion_engine.py -q
```

- **`tests/test_fusion_models.py`** — the domain layer: `FusionAttribute` ordering;
  `Claim.key` case/whitespace normalization and `to_dict` shape; every builder
  (`from_detection` maps type+brand and drops the `"Unknown"`/empty placeholders;
  `from_ocr` maps identity fields at per-field confidence and ignores QR/barcode
  field types; `from_ocr_identity` maps present fields at a shared confidence and
  yields nothing when empty; `from_fingerprint` surfaces provenance at the fixed
  low confidence, merges identity without duplicating brand, and carries no claims
  when there is no provenance); `ResolvedAttribute.agreed`/`to_dict`; `Conflict`
  sources/`to_dict`; `DeviceContext` accessors, `to_dict`, and **immutability**.
- **`tests/test_fusion_engine.py`** — the engine across all four required
  scenarios:
  - **Agreement** — two `0.8` claims fuse to `0.96` (noisy-OR), `agreed=True`,
    `conflicted=False`; full three-module agreement via `fuse_modules` lists all
    three sources.
  - **Disagreement** — a competing brand records a `Conflict`, the winner is the
    higher-confidence value, and its confidence is damped below its raw value; the
    spec's *device-type-vs-OCR-identity* conflict is detected.
  - **Partial evidence** — OCR-only, and detection+fingerprint-without-OCR, both
    resolve correctly; `source_hashes` fall back to the fingerprint's and can be
    overridden.
  - **Missing evidence** — an empty iterable and all-`None` `fuse_modules` both
    yield an empty context (`confidence=0.0`, no attributes, no conflicts).
  - Plus: aggregate confidence = mean of resolved attributes; confidence is bounded
    to `[0, 1]`; attributes come out in declaration order; fusion is deterministic
    for identical input; the engine stamps its version and optional clock; and full
    evidence provenance is preserved on the context.

## Integration guide

The fusion engine is a **library**, wired by construction — there is nothing to
mount and no endpoint to call. A future orchestrator combines the three engines
like this:

```python
from device_ai.fusion import FusionEngine

engine = FusionEngine()  # optionally FusionEngine(clock=...) for a fixed timestamp

detection   = detector.detect(images)             # M1.4 DetectionResult
fingerprint = fingerprint_service.generate(images)  # M1.5 DeviceFingerprint
extraction  = ocr_service.extract(images)         # M1.6 OCRExtraction

context = engine.fuse_modules(
    detection=detection,
    fingerprint=fingerprint,
    ocr=extraction,
)

# One canonical, immutable device view for downstream AI:
context.device_type          # e.g. "Laptop"
context.brand                # e.g. "Dell"
context.confidence           # aggregate confidence in [0, 1]
context.has_conflicts        # True if any attribute was contested
context.to_dict()            # fully serializable (attributes + evidence + conflicts)
```

Any subset of the three arguments may be `None`; the engine fuses whatever is
present. To fuse pre-built evidence directly (e.g. from a new future engine), call
`engine.fuse([...Evidence])`.

## Worked examples

### Full agreement

Detector, fingerprint and OCR all indicate a Dell laptop:

```python
context = engine.fuse_modules(detection=det, fingerprint=fp, ocr=ocr)

context.value_of(FusionAttribute.BRAND)        # "Dell"
context.get(FusionAttribute.BRAND).sources     # (DETECTION, FINGERPRINT, OCR)
context.get(FusionAttribute.BRAND).agreed      # True
context.get(FusionAttribute.BRAND).confidence  # ↑ boosted by noisy-OR
context.has_conflicts                          # False
```

### Detected type vs. OCR identity conflict

The detector reads the chassis as a `Laptop`, but OCR extracts a phone IMEI and a
different manufacturer:

```python
context = engine.fuse_modules(detection=det_laptop, ocr=ocr_phone)

context.has_conflicts                          # True
conflict = context.conflicts[0]
conflict.attribute                             # FusionAttribute.BRAND
conflict.resolved_value                        # the higher-confidence brand
conflict.sources                               # (DETECTION, OCR) — both recorded
context.get(FusionAttribute.BRAND).confidence  # damped below the raw winner
```

### `to_dict()` shape (abridged)

```json
{
  "eco_id": "ET-2026-1A2B3C4D",
  "fingerprint": "a3f5e8d2…",
  "confidence": 0.842716,
  "attributes": [
    { "attribute": "device_type", "value": "Laptop", "confidence": 0.96,
      "sources": ["detection", "fingerprint"], "conflicted": false, "agreed": true },
    { "attribute": "brand", "value": "Dell", "confidence": 0.734,
      "sources": ["detection", "ocr"], "conflicted": true, "agreed": false }
  ],
  "conflicts": [
    { "attribute": "brand", "resolved_value": "Dell",
      "sources": ["detection", "ocr"],
      "claims": [
        { "attribute": "brand", "value": "Dell", "confidence": 0.9, "source": "detection" },
        { "attribute": "brand", "value": "HP",   "confidence": 0.6, "source": "ocr" }
      ] }
  ],
  "evidence": [ "…full per-module provenance…" ],
  "source_hashes": ["9a3c…"],
  "engine_version": "1.0.0",
  "created_at": "2026-08-01T12:00:00+00:00"
}
```

## Backward compatibility

The `/predict` contract is **completely unchanged**. M1.7 mounts **no router**,
adds **no endpoint**, and does not touch `application.py`, the `/predict` pipeline,
or any existing schema. The fusion engine is imported and used only where a future
orchestrator chooses to — it is invisible to every current caller.

The full pre-existing test suite (including the `/predict` backward-compatibility
guards from M1.4–M1.6) passes unchanged alongside the new fusion tests.

## Design rationale

**Why an `Evidence`/`Claim` abstraction instead of merging result objects
directly?** The three engines return *different* frozen shapes (`DetectionResult`,
`DeviceFingerprint`, `OCRExtraction`). Comparing them directly would hardwire the
fusion logic to every module's internal structure and duplicate mapping code. A
uniform `Evidence`→`Claim` projection lets the engine reason about
`(attribute, value, confidence, source)` tuples generically — and lets a **future**
engine join fusion just by providing a builder, with zero change to the resolver.

**Why `TYPE_CHECKING`-only imports of the module results?** The domain layer must
not couple to `inference/`, `fingerprint/` or `ocr/` at runtime (that would create
import cycles and drag heavy transitive dependencies into a pure component). Typing
the builders under `TYPE_CHECKING` and importing the concrete types lazily inside
the builder bodies mirrors the M1.6 fingerprint-identity seam precedent and keeps
`fusion/` importable on its own.

**Why noisy-OR + support-share rather than a simple average or a max?** Averaging
would *punish* agreement (two confident, agreeing modules would average to their
mean, not exceed it); a plain max would ignore dissent entirely. Noisy-OR models
independent corroboration (agreement *raises* confidence), while support-share
damping models contention (disagreement *lowers* it) — the two behaviors the spec
requires, composed into one bounded, monotonic score.

**Why a total ordering for winner selection?** Determinism is a hard requirement:
the same evidence must always yield the same `DeviceContext` (for reproducible
tests, caching, and future blockchain anchoring). Ranking by
`(combined_confidence, claim_count, module_order)` is a strict total order, so
there is never an ambiguous tie.

**Why keep the full `evidence` trail on the context?** Downstream AI and audits
need to trace any resolved value back to the module(s) that asserted it. Retaining
the complete provenance (not just the winners) makes every `DeviceContext`
self-explaining and is the foundation for the future Digital Device Passport.

**Why immutable?** A `DeviceContext` is shared across multiple downstream
consumers; a frozen, slotted dataclass guarantees no consumer can mutate a shared
device view, which keeps the fused result trustworthy as it flows through the
pipeline.

---

_Part of **EcoTrace India** — IEEE YESIST 2026. See the module
[`README.md`](../../README.md) and the platform-wide `docs/engineering/`
standards._
