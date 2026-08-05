# Device Passport Validation & Integrity Engine (M2.4)

> The **eighth downstream consumer** of the Device Intelligence Engine and the
> fourth component of milestone **M2** — an internal-only, **deterministic
> checker** that consumes the immutable **`DevicePassport`** the passport core
> (M2.3) produced and emits a single, immutable **`PassportIntegrityReport`**. It
> answers two questions about that document: *is it structurally sound?* — by
> re-validating every section against an **external, versioned rule-set** (sections
> present, kinds correct, required object fields present, normalized confidences
> within `[0, 1]`) and reporting the outcome as **ordered errors** and **ordered
> warnings** rather than raising; and *what is its integrity anchor?* — by computing
> a deterministic **SHA-256** hash over the passport's **canonical serialization**
> so any later mutation of the document is detectable by re-hashing. Unlike M2.3
> (which *assembles* the passport), the integrity engine carries **no inference and
> no assembly of its own**: it re-checks a document the pipeline already produced
> and hashes it. It ships **no new endpoint** and leaves the `/predict` API contract
> **unchanged and backward-compatible**.

**Module:** `intelligence/device_ai`
**Milestone:** M2.4 — Device Passport Validation & Integrity Engine
**Status:** implemented; internal-only (no router, no HTTP surface)

---

## Table of contents

1. [Scope](#scope)
2. [Architecture](#architecture)
3. [Domain models](#domain-models)
4. [The external validation rule-set](#the-external-validation-rule-set)
5. [Rule-set loader](#rule-set-loader)
6. [The deterministic validator](#the-deterministic-validator)
7. [The integrity hash](#the-integrity-hash)
8. [Validation status — a transparent verdict](#validation-status--a-transparent-verdict)
9. [Deterministic serialization](#deterministic-serialization)
10. [Configuration](#configuration)
11. [Testing](#testing)
12. [Integration guide](#integration-guide)
13. [Worked examples](#worked-examples)
14. [Backward compatibility](#backward-compatibility)
15. [Design rationale](#design-rationale)

---

## Scope

M2.4 is the **eighth** component to consume the fusion engine's output (transitively,
via the passport), and the first that **judges** an existing document rather than
producing a new analysis or composition. The passport core (M2.3) assembles the
upstream reports into an immutable `DevicePassport`; the integrity engine answers
the next question: *"is this passport structurally sound, and what is its
tamper-evident hash?"* It consumes **one** input — the passport — and reads only its
public serialized surface (`to_dict()` / `to_json()`):

| # | Input | Source | What the engine does with it |
|---|---|---|---|
| 1 | **Device passport** | `passport.to_dict()` (13 sections) | re-validate every section against the rule-set → ordered errors/warnings + per-section outcomes |
| 1 | **Device passport** | `passport.to_json()` (canonical bytes) | hash with SHA-256 → the canonical integrity anchor |
| 1 | **Device passport** | `passport.metadata.schema_version`, `passport.passport_version` | echo the observed versions onto the report |

**The report includes exactly the seven required fields** (plus provenance):

| Requirement | Report field |
|---|---|
| Validation Status | `status` (`valid` / `valid_with_warnings` / `invalid`) |
| Canonical Hash | `canonical_hash` (+ `hash_algorithm`) |
| Schema Version | `schema_version` (observed on the passport metadata) |
| Passport Version | `passport_version` (the passport's own structural version) |
| Checked Sections | `checked_sections` (one `CheckedSection` per rule-set section) |
| Ordered Warnings | `warnings` (ordered, de-duplicated soft cautions) |
| Ordered Errors | `errors` (ordered, de-duplicated structural errors) |

**Explicitly in scope**

- `PassportIntegrityReport` — the immutable verdict-plus-anchor document with the
  seven required fields, provenance and an optional timestamp.
- An **external, versioned** validation rule-set (YAML/JSON) with a strict loader
  that validates aggressively and fails with a typed error.
- A pure `PassportIntegrityValidator` (validate every section → hash the canonical
  serialization).
- A deterministic **SHA-256** integrity hash over the canonical passport bytes.
- An injected `IntegrityService` orchestration façade.

**Explicitly out of scope** (do **not** implement in M2.4): **blockchain
anchoring**, **digital signatures**, **QR codes**, **CBOR** encoding, **ownership
history**, **lifecycle events**, **database persistence** and **REST endpoints**.
The engine is a **checker**, not a new inference — no field is a score it invented,
and no field is a currency amount. The engine is **internal only** — no router is
mounted, `application.py` is untouched, and the `/predict` response schema is
**unchanged**.

**Key asymmetry.** A malformed **rule-set** *raises* (a `PassportIntegrityRuleError`
at load time — it is an engine fault); a malformed **passport** is *reported* as
ordered errors on the produced report (it is the very data the engine was asked to
judge, never a reason to crash). This is the opposite of the passport core, whose
`validate_passport` raises on a bad passport — because there the passport is the
core's own output, whereas here the passport is untrusted input.

## Architecture

The engine is a **pure domain layer** with the same shape as `passport/`,
`circular/` and `environmental/`: frozen slotted dataclasses, a stateless
validator, and an injected service. It imports the `DevicePassport` type **only
under `TYPE_CHECKING`**, so there is no runtime coupling and no import cycle — the
passport is passed in, never reached into past its public serialized surface. The
one runtime dependency it takes is the shared `hash_bytes` helper.

```
        passport core (M2.3) ─► DevicePassport ────────────────────┐
                                                                   │
      ┌──────────────── integrity/ (internal) ─────────────────────▼──────────┐
      │  service.py   IntegrityService.validate(passport)                      │
      │        │             │              │                                  │
      │        ▼             ▼              ▼                                  │
      │   rules.py     validator.py    config.py                              │
      │  load_rules    PassportIntegrity IntegrityConfig                      │
      │  IntegrityRuleSet Validator      (rule-set locator +                  │
      │  (external      (validate →      hash_algorithm)                      │
      │   YAML/JSON,     hash)                                                │
      │   validated)        │                                                │
      │   models.py  PassportIntegrityReport (frozen) · CheckedSection ·      │
      │              ValidationStatus                                         │
      └───────────────────────────────────────────────────────────────────────┘
                                ▼
       downstream (M2.5+ blockchain / QR / anchor) — never /predict
```

Layering (dependencies point downward, never upward):

```
passport/  (M2.3 — produces the immutable DevicePassport input)
   ↓  (TYPE_CHECKING only; the passport is passed in)
integrity/  (models.py + rules.py + config.py + validator.py + service.py)
   ↓
exceptions · configs · utils/hashing   (cross-cutting foundations)
```

The package contains **no HTTP imports, no FastAPI, and its only I/O is reading the
rule-set file once at service construction.** After that, `validate()` is a pure
function of its input except for the injected clock (which defaults to UTC `now` and
can be replaced or disabled for determinism).

## Domain models

`integrity/models.py` defines the vocabulary of the report. Each is a small, frozen,
slotted dataclass with its own `to_dict()` so the report serializes deterministically.

### `ValidationStatus`

A `str` enum with three states ordered by severity:

| Value | Meaning |
|---|---|
| `valid` | Every checked section passed and no caution was raised. |
| `valid_with_warnings` | No error was found, but at least one soft caution was raised (e.g. an optional section absent). |
| `invalid` | At least one structural error was found; the passport does not satisfy its rule-set. |

`ValidationStatus.values()` returns the wire values in declaration order.

### `CheckedSection`

One record per rule-set section — the audit trail of the verdict:

| Field | Meaning |
|---|---|
| `name` | The section name. |
| `kind` | The declared section kind (`string` / `object` / `array`). |
| `present` | Whether the section was present in the passport payload. |
| `valid` | Whether the section satisfied every applicable check. |

### `PassportIntegrityReport`

The immutable verdict-plus-anchor — a frozen slotted dataclass:

| Field | Meaning |
|---|---|
| `passport_id` | The id of the passport that was checked (provenance). |
| `status` | The overall `ValidationStatus` verdict. |
| `canonical_hash` | Hex digest of the passport's canonical serialization. |
| `hash_algorithm` | The digest algorithm used (e.g. `sha256`). |
| `schema_version` | The schema version observed on the passport metadata. |
| `passport_version` | The passport's own structural version. |
| `checked_sections` | One `CheckedSection` per rule-set section, in declaration order. |
| `warnings` | Ordered, de-duplicated soft cautions. |
| `errors` | Ordered, de-duplicated structural errors (empty when valid). |
| `rules_version` | Version of the external validation rule-set used. |
| `engine_version` | Version of the integrity engine that produced this. |
| `created_at` | UTC timestamp (or `None` when constructed without a clock). |

Convenience API: `is_valid` (True for `valid` and `valid_with_warnings`),
`checked_count`, `warning_count`, `error_count`. `to_dict()` renders a fully
JSON-serializable payload in a **fixed** key order; `to_json()` renders a
**canonical** serialization (see [Deterministic serialization](#deterministic-serialization)).

## The external validation rule-set

The engine's validation contract lives **outside the code** in
`integrity/data/rules.yaml` — a versioned rule-set that is **data, not logic**, so
*which sections a passport must contain, the shape and ranges of each, and which are
optional* can be reviewed and versioned independently of the passport schema as the
passport evolves without touching or redeploying the validator.

Top-level keys:

| Key | Meaning |
|---|---|
| `version` | Semantic version string, stamped onto every produced report as its `rules_version`. |
| `sections` | Mapping of section name → `{ kind, [fields], [confidence_fields], [required] }`. Order is the check/report order. |

A section's `kind` is one of `string`, `object` (a mapping that must contain every
name in its `fields` list) or `array`. `confidence_fields` (object sections only)
names the subset of `fields` whose values must be numeric and within `[0, 1]`.
`required` (default `true`) marks a section mandatory: a missing **required** section
is an **error**; a missing **optional** section is a **warning**.

The shipped rule-set declares the **thirteen** passport sections — three strings, eight
objects and two arrays — with `fingerprint_summary` marked **optional** (the passport
core emits an all-empty but present fingerprint section when no fingerprint is
available, so in practice it is always present; the optional flag documents that it
is not an identity requirement). It holds **no scoring weights, no thresholds and no
policy** — only shape, ranges and required/optional.

## Rule-set loader

`integrity/rules.py` turns the rule-set file into validated, immutable value objects,
and owns the **fixed vocabulary** the rule-set is validated against:

- **`SectionKind`** — the three legal section kinds (`string`, `object`, `array`).
- **`SectionRule`** — one section's contract: its `name`, `kind`, `fields`,
  `confidence_fields` and `required` flag.
- **`IntegrityRuleSet`** — the whole loaded rule-set: its `version` and the ordered
  sections. Convenience API: `section_count`, `section_names`, `section(name)`.

`load_rules(path)` reads YAML (or JSON, by suffix), then **validates aggressively**,
raising a typed `PassportIntegrityRuleError` on any structural problem:

- file missing / unparseable / not a mapping / empty;
- missing or empty `version`;
- no `sections`, `sections` not a mapping, or an empty `sections` mapping;
- an unknown section `kind`;
- an object section with no `fields`, a null/`non-list` `fields`, or a duplicate
  field name;
- a `confidence_fields` entry not present in the section's own `fields`;
- a non-object section that nonetheless declares `fields`;
- a non-boolean `required` flag.

The vocabulary (`SectionKind`, `SectionRule`) is **re-declared** in `integrity/`
rather than imported from `passport.schema`, so the integrity engine owns its own
contract and the two evolve independently even though they describe the same document.

## The deterministic validator

`integrity/validator.py` holds the deterministic check. `validate(...)` has two
independent halves, and there is **no model and no inference** — given the same
passport and rule-set it always produces the same report (modulo the optional
timestamp):

1. **Validate** every rule-set section against the passport's `to_dict()`, recording
   a `CheckedSection` per section and appending an ordered **error** (a required
   section missing, a wrong kind, a missing object field, an out-of-range or boolean
   confidence) or a soft **warning** (an optional section absent). Errors and warnings
   are **de-duplicated in order**. A malformed passport is **never raised** — it is
   reported.
2. **Hash** the passport's canonical JSON (`to_json()`) with the configured algorithm
   (SHA-256 by default), giving a fixed-length hex digest that changes if any byte of
   the document changes. An **unsupported algorithm** is the one thing that raises here
   — a `PassportIntegrityError`, since it is an engine misconfiguration, not bad data.

The confidence check reuses the passport-core convention: a value is a valid
confidence iff it is an `int`/`float` (never a `bool`) within `[0, 1]`.

## The integrity hash

The integrity hash is a **content anchor** — a full SHA-256 hex digest (64 characters)
over the passport's **canonical** serialization:

```
canonical_hash = sha256( passport.to_json().encode("utf-8") )   # full hex digest
```

Because `to_json()` is canonical (sorted keys, fixed separators, `ensure_ascii=False`)
and the passport is itself a deterministic function of its inputs, the hash is a **pure
function of the document's content**. Two consequences follow by construction:

- **Tamper-evident.** Any later mutation of any passport field changes the canonical
  bytes and therefore the hash, so a consumer can detect tampering by re-hashing.
- **Stable & reproducible.** The same passport always yields the same hash, on any
  service instance, at any time — the property a future anchor/QR layer needs.

The hash is stamped onto the report **even when the passport is invalid** — it anchors
whatever document was actually checked, so an invalid passport is still identifiable.

## Validation status — a transparent verdict

The engine derives **no score of its own**. The overall `status` is a transparent
function of the accrued errors and warnings:

```
status = invalid                if errors
         valid_with_warnings    elif warnings
         valid                  otherwise
```

An operator can re-derive the verdict by hand from the ordered `errors` and `warnings`
lists carried on the same report. `is_valid` is `True` for both `valid` and
`valid_with_warnings` — a passport with only soft cautions is still structurally sound.

## Deterministic serialization

`PassportIntegrityReport.to_json()` renders a **canonical** JSON serialization: keys
are sorted (`sort_keys=True`), non-ASCII is preserved (`ensure_ascii=False`) and
separators are fixed, so the same report always serializes to the exact same bytes.
Because `to_dict()` is itself a pure function of the inputs, the **only** source of
variation is the optional `created_at` timestamp. Passing `indent=` pretty-prints while
staying canonical; the default emits the most compact canonical form.

## Configuration

`IntegrityConfig` (frozen slotted) holds the rule-set locator and the hash algorithm,
so the config stays a thin locator plus one knob — everything that shapes *which
sections a passport must satisfy* lives in the external rule-set:

| Field | Default | Meaning |
|---|---|---|
| `rules_path` | `integrity/data/rules.yaml` | Rule-set locator, resolved against the package root when relative. |
| `hash_algorithm` | `sha256` | Digest algorithm the canonical integrity hash is computed with. |

The two env-driven knobs are mapped via `IntegrityConfig.from_settings(settings)`:

| Env var | Field |
|---|---|
| `INTEGRITY_RULES_PATH` | `rules_path` |
| `INTEGRITY_HASH_ALGORITHM` | `hash_algorithm` |

The typed exceptions added for this engine are `PassportIntegrityError`
(`PASSPORT_INTEGRITY_ERROR`, 500) and its loader subclass `PassportIntegrityRuleError`
(`PASSPORT_INTEGRITY_RULE_ERROR`, 422). `PassportIntegrityError` also surfaces an
unsupported-algorithm misconfiguration at `validate()` time.

## Testing

Three test modules under `tests/`, all offline (no images, no models; only the external
rule-set/schema/catalogues are read from disk):

- **`test_integrity_rules.py`** — the shipped rule-set's structure and invariants (13
  sections, the required section names, `fingerprint_summary` optional, object sections
  carry fields, confidence fields declared), and the loader's validation on hand-written
  good/bad rule-sets in `tmp_path` (missing file, empty, missing version, missing / empty
  sections, unknown kind, object section with null / empty fields, a confidence field not
  in the section's fields, a string section with fields, a non-boolean `required`, a
  duplicate field, JSON parsing), plus the `SectionRule.to_dict` / `SectionKind.values`
  value objects.
- **`test_integrity_validator.py`** — the deterministic check against hand-built passports
  and rule-sets: the happy path (valid, hashed), one checked-section record per rule,
  provenance stamping, the SHA-256 hash (hex, fixed length, deterministic, tamper-changed,
  present even when invalid), the unsupported-algorithm engine fault, the three verdict
  states (valid / valid-with-warnings via an optional section / invalid), every
  structural-error kind (wrong string/array/object kind, missing object field, out-of-range
  and boolean confidence, missing required section) and de-duplicated ordered errors.
- **`test_integrity_service.py`** — end-to-end `validate(...)` against the **shipped**
  rule-set, with the passport built by actually running the recoverability, component,
  material, environmental, decision-knowledge, circular and passport engines over a
  hand-built `DeviceContext` plus a real `DeviceFingerprint`: a well-formed passport
  (valid, 64-hex SHA-256, 13 checked sections), the echoed schema/passport versions, the
  default rule-set load, a no-fingerprint passport (still valid — the section is present
  but empty), provenance/version stamping, the injected clock, determinism, hash stability
  across service instances, tamper-detection, injected config / `from_settings` mapping,
  a `sha512` override flowing into a 128-char digest, the no-monetary-field invariant and
  immutability.

The three modules add **51** new tests, all passing; the module is `ruff`-, `black`- and
`isort`-clean and adds **zero** `mypy` errors.

## Integration guide

The engine is consumed **directly** (no HTTP). Orchestrating code builds the passport
(M2.3) and hands it to `IntegrityService.validate`:

```python
from device_ai.passport import PassportService
from device_ai.integrity import IntegrityService, ValidationStatus

# 1. Compose the device passport (M2.3) from the upstream reports.
passport = PassportService().build(context, decision, materials, environmental, fingerprint)

# 2. Validate & hash it (M2.4). Every collaborator is injected, so the service is
#    constructible as-is or with a fixed clock / custom config / pre-loaded rule-set.
#    The external rule-set is loaded once at construction.
report = IntegrityService().validate(passport)

if report.status is ValidationStatus.INVALID:
    for error in report.errors:      # ordered, de-duplicated structural errors
        log.error("passport %s: %s", report.passport_id, error)

anchor = report.canonical_hash       # SHA-256 hex — tamper-evident content anchor
payload = report.to_dict()           # JSON-serializable verdict
canonical = report.to_json()         # deterministic bytes
```

For **deterministic** use (tests, reproducible pipelines) construct the service with
`clock=None` (drops the timestamp, making the report a pure function of its input) and/or
inject a hand-built `IntegrityRuleSet` or a custom `IntegrityConfig`.

## Worked examples

### A well-formed passport — valid, hashed

A passport assembled by the M2.3 core validates cleanly: every one of the thirteen
sections is present, of the right kind, with all required fields and in-range
confidences, so the `status` is `valid`, `errors` is empty, and `canonical_hash` is the
64-character SHA-256 of the passport's canonical JSON. The `schema_version` and
`passport_version` are echoed from the passport, and each `CheckedSection` records
`present=True, valid=True`.

### A tampered passport — the hash moves

Mutating any field of the passport (say its `eco_id`) changes the canonical bytes, so
re-validating the tampered document yields a **different** `canonical_hash`. A consumer
that stored the original hash detects the tampering by comparing. If the mutation also
breaks the structure (e.g. a confidence pushed above `1.0`), the `status` flips to
`invalid` and the offending section is named in `errors`.

### An invalid passport — reported, not raised

If a passport is missing a required section or carries an out-of-range confidence, the
engine does **not** raise — it returns a report with `status = invalid`, the offending
sections marked `valid=False`, and one ordered error per problem. The `canonical_hash` is
still computed, so even a broken passport is anchored and identifiable.

## Backward compatibility

M2.4 is **purely additive** and **internal-only**:

- **No endpoint, no router, no schema change.** `application.py` and the `/predict`
  request/response contract are untouched; the only new symbols are the `integrity/`
  package, two `Settings` fields and two typed exceptions.
- **No change to any upstream engine.** The engine consumes the existing public serialized
  surface of the M2.3 `DevicePassport` and adds nothing to it.
- **External rule-set.** The validation contract is data in `integrity/data/rules.yaml`,
  versioned independently of the code and of the passport schema.

## Design rationale

- **A checker, not an inference.** The engine's job is to judge and anchor a document the
  pipeline already produced. Making it a **pure checker** — re-validating structure and
  hashing canonical bytes, deriving no score — keeps the verdict faithful and lets an
  operator re-derive it by hand from the ordered errors/warnings.
- **Report, don't raise, on bad data.** A malformed passport is the engine's *input*, so it
  is reported as ordered errors — never a crash. Only a malformed *rule-set* (an engine
  fault) raises. This asymmetry is deliberate and is the inverse of the passport core,
  whose validator raises on its own output.
- **Contract is data, not logic.** *Which sections a passport must contain and their
  field/range shape* is a contract that evolves; keeping it in an external, versioned,
  strictly-validated rule-set — separate from the passport schema — lets the check evolve
  independently and fail loudly on a malformed rule-set.
- **Content-addressed integrity.** A SHA-256 over canonical bytes gives every passport a
  reproducible, tamper-evident anchor — the property a future blockchain/QR layer needs,
  without implementing any of that here.
- **Deterministic and injectable.** Like every engine before it, the check is a pure
  function and every collaborator is constructor-injected with a sensible default, so
  production wires nothing while tests inject a rule-set, clock or config at will.
