# Device Lifecycle Ledger Engine (M3.3)

> The **third component of milestone M3**, and the first to model a device's
> *complete history* rather than a single passport verdict. The lifecycle engine
> is an internal-only, **deterministic device-history builder**: it accepts an
> ordered sequence of immutable **`LifecycleEvent`** objects (registered → in use
> → collected → … → disposed), validates that ordering against an **external,
> versioned state machine**, and composes the result into an immutable
> **`LifecycleRecord`**. It sits *above* the M3.1 blockchain ledger core — where
> the ledger core chains passport *verdicts*, this engine chains a device's
> *history* — and ties into the ledger **through the M3.2 backend abstraction**
> for anchoring and correlation, depending only on the injected
> **`LedgerService`** façade and never on a concrete store.
>
> Like M3.1/M3.2 it carries **no inference and no evidence collection of its
> own**. Its state machine (which event-type transitions are legal, which events
> may begin a lifecycle, and — via an empty successor set — which end one) lives
> in an external YAML/JSON file behind a strict validating loader; its validation
> is deterministic and its serialization canonical, so the same events always
> yield byte-identical output (modulo optional timestamps). It ships **no
> endpoint** and leaves the `/predict` API contract **unchanged and
> backward-compatible**.

**Module:** `intelligence/device_ai`
**Milestone:** M3.3 — Device Lifecycle Ledger Engine
**Status:** implemented; internal-only (no router, no HTTP surface)

---

## Table of contents

1. [Scope](#scope)
2. [Architecture](#architecture)
3. [Domain models](#domain-models)
4. [The external transition rules](#the-external-transition-rules)
5. [Rules loader](#rules-loader)
6. [The deterministic engine](#the-deterministic-engine)
7. [Validation and the state machine](#validation-and-the-state-machine)
8. [Incremental appends](#incremental-appends)
9. [Deterministic serialization](#deterministic-serialization)
10. [The service façade](#the-service-façade)
11. [Ledger integration through the backend abstraction (M3.2)](#ledger-integration-through-the-backend-abstraction-m32)
12. [Configuration](#configuration)
13. [Testing](#testing)
14. [Integration guide](#integration-guide)
15. [Worked examples](#worked-examples)
16. [Backward compatibility](#backward-compatibility)
17. [Design rationale](#design-rationale)

---

## Scope

M3.3 is the **third** component of milestone M3 and the first to build a
**complete device history** over the pipeline's output rather than a single
tamper-evident snapshot. The passport core (M2.3) assembles the upstream reports
into an immutable `DevicePassport`; the integrity engine (M2.4) confirms it is
structurally sound; the trust engine (M2.5) grades how much it can be trusted;
the ledger core (M3.1) anchors those verdicts in a hash-chain; the lifecycle
engine answers the next question: *"what is the ordered, validated history of
this device — from registration to disposal — and is that history a legal path
through the lifecycle?"* It consumes only lifecycle **events** a caller records
and validates their ordering against an external state machine — never any raw
image, model or upstream report.

Each `LifecycleEvent` captures *what* happened (a `LifecycleEventType`) and
optionally *who* recorded it, *where*, a free-form note and *when*; the engine
orders them, checks the sequence against the state machine, and composes them
into an immutable `LifecycleRecord`. Any illegal ordering is *reported* as
`is_valid == False` on the record — never raised.

**Explicitly in scope**

- Three frozen, slotted domain models — `LifecycleEventType`, `LifecycleEvent`,
  `LifecycleRecord` — each with deterministic `to_dict`/`to_json`.
- An **external, versioned** transition-rules file (YAML/JSON) with a strict
  loader that validates aggressively and fails with a typed error, plus its two
  value objects `LifecycleTransition` and `LifecycleRuleSet`.
- A pure `LifecycleEngine` (`validate` → `build_record` → `can_append`) with
  deterministic state-machine validation.
- An injected `LifecycleService` orchestration façade that stamps provenance and
  ties into the ledger **through the injected `LedgerService`** for anchoring and
  correlation (`is_anchored` / `anchored_chain` / `anchored_ids`).

**Explicitly out of scope** (do **not** implement in M3.3): **Hyperledger
Fabric**, **chaincode**, **smart contracts**, **REST endpoints**, **networking**,
**GPS tracking**, **event streaming**, **QR scanning**, **wallets** and
**digital signatures**. The engine is a **local, in-memory data structure**, not
a tracking system — it models device history and validates it against external
rules, behind a pluggable ledger anchor, and nothing more. It is **internal
only** — no router is mounted, `application.py` is untouched, and the `/predict`
response schema is **unchanged**.

**Key asymmetry.** A malformed **rules file** *raises* (a `LifecycleRuleError` at
load time — it is an engine fault). An illegal *event ordering* — a non-initial
genesis event, an undeclared transition, or an event after a terminal one — is
never raised; it is *reported* as `is_valid == False` on the produced record (and
by `validate()` / `can_append()` returning `False`), because judging that
ordering is exactly the job the engine was asked to do. This mirrors the
M2.4/M2.5/M3.1 asymmetry: only the engine's own policy file can crash it.

## Architecture

The engine is a **pure domain layer** with the same shape as `trust/`,
`integrity/`, `passport/` and `ledger/`: frozen slotted dataclasses, a stateless
engine, an external policy file behind a strict loader, and an injected service.
It imports the ledger's `Blockchain` type **only under `TYPE_CHECKING`**, so
there is no heavyweight runtime coupling and no import cycle — the ledger is
reached only through the injected `LedgerService` façade.

```
   caller records LifecycleEvent objects ────────────────────┐
                                                              │
   ┌──────────────── lifecycle/ (internal) ────────────────────▼──────────┐
   │  service.py   LifecycleService.event / build / append /              │
   │        │            can_append / is_anchored / anchored_chain        │
   │        ▼             ▼              ▼                                 │
   │  config.py       engine.py     rules.py (external YAML/JSON)         │
   │  LifecycleConfig LifecycleEngine load_rules → LifecycleRuleSet       │
   │  (rules locator) (validate →     (LifecycleTransition per event,     │
   │                   build_record →  initial + terminal events,         │
   │                   can_append)     validated on load)                 │
   │   models.py  LifecycleRecord (frozen) · LifecycleEvent ·             │
   │              LifecycleEventType                                      │
   └─────────────────────────────────────┬──────────────────────────────────┘
                                          ▼
             injected LedgerService (M3.1) → LedgerBackend (M3.2)
             for anchoring / correlation — never /predict
```

Layering (dependencies point downward, never upward):

```
ledger/ (M3.1 chain + M3.2 backend)   (anchors the device's passport verdicts)
   ↑  (via the injected LedgerService façade; Blockchain under TYPE_CHECKING)
lifecycle/  (models.py + rules.py + config.py + engine.py + service.py)
   ↓
exceptions · configs   (cross-cutting foundations)
```

The package contains **no HTTP imports, no FastAPI, and its only I/O is reading
the rules file once at service construction.** After that, every engine method is
a pure function of its inputs except for the injected clock (which defaults to
UTC `now` and can be replaced or disabled for determinism).

## Domain models

`lifecycle/models.py` defines the vocabulary of a device's history. Each is a
small, frozen, slotted dataclass with its own `to_dict()`/`to_json()` so a record
serializes deterministically.

### `LifecycleEventType`

The **fixed vocabulary** of lifecycle stages a device can move through — a
`str, Enum` so members serialize to their wire value directly and can be
constructed from a rules-file string. It is the single source of truth the
external transition rules are validated against on load: a rules file naming an
event type outside this set is rejected.

| Member | Wire value | Meaning |
|---|---|---|
| `REGISTERED` | `registered` | Passport first minted — the genesis event. |
| `IN_USE` | `in_use` | In service during its useful life. |
| `COLLECTED` | `collected` | Handed to a collector for end-of-life handling. |
| `IN_TRANSIT` | `in_transit` | Moving between facilities. |
| `ASSESSED` | `assessed` | Graded at a facility. |
| `REFURBISHED` | `refurbished` | Restored to use or resale (a second life). |
| `RECYCLED` | `recycled` | Materials recovered. |
| `DISPOSED` | `disposed` | End-of-life — the terminal event. |

The `values()` classmethod returns every wire value in declaration order (used by
the loader's error messages). The legal *transitions* between these stages are
policy, defined in the external rules file — this enum only fixes the vocabulary.

### `LifecycleEvent`

One immutable event — the atomic unit a record is built from:

| Field | Meaning |
|---|---|
| `event_type` | The `LifecycleEventType` this event represents (required). |
| `actor` | Optional party that recorded it (operator, facility). Empty when unknown. |
| `location` | Optional free-text location label. Empty when unknown — **no GPS tracking**. |
| `note` | Optional free-form annotation. Empty when none. |
| `occurred_at` | UTC timestamp, or `None` when built without a clock. |

Only `event_type` is required, so a caller can record a bare state transition or
a fully annotated one.

### `LifecycleRecord`

The immutable, ordered history the engine produces and the service hands to the
ledger for anchoring:

| Field | Meaning |
|---|---|
| `device_id` | Id of the device whose lifecycle this captures (typically the passport id). |
| `events` | The ordered lifecycle events, from the genesis event onward. |
| `is_valid` | Whether the sequence is a legal path through the state machine. |
| `event_count` | Number of events in the record. |
| `current_state` | Wire value of the latest event's type, or `None` when empty. |
| `engine_version` | Version of the lifecycle engine that produced this. |
| `rules_version` | Version of the external transition-rules file used. |
| `created_at` | UTC timestamp, or `None` when built without a clock. |

Convenience properties `is_empty` (no events) and `event_types` (the ordered
wire values) let callers read the history without reaching into each event. Every
object's `to_dict()` renders a fully JSON-serializable payload in a **fixed** key
order; `to_json()` renders a **canonical** serialization (see
[Deterministic serialization](#deterministic-serialization)).

## The external transition rules

The engine's state machine lives **outside the code** in
`lifecycle/data/transitions.yaml` — a versioned file that is **policy, not
logic**, so *which lifecycle transitions are legal, which events may start a
lifecycle, and which end it* can be reviewed, tuned or corrected without touching
or redeploying the engine.

Top-level keys:

| Key | Meaning |
|---|---|
| `version` | Semantic version string of the rules document (required, non-empty; stamped onto every record). |
| `initial_events` | The event types a lifecycle may legally begin with (required, non-empty list of known types, no duplicates). |
| `transitions` | A mapping from each event type to its ordered list of legal successor event types. |

Every `LifecycleEventType` must appear **exactly once** as a `transitions` key.
An empty successor list marks a **terminal** event (a lifecycle end); at least
one terminal event is required so a lifecycle can end. The shipped rules encode
this e-waste state machine:

```
registered ─► in_use ─► collected ─┬─► in_transit ─┬─► assessed ─┬─► refurbished ─┬─► in_use
     │           │                 │               │            │                └─► recycled
     └───────────┴──► collected ◄──┘               └─► collected └─► recycled ─► disposed (terminal)
                                                                 └─► disposed (terminal)
```

`registered` is the sole initial event; `disposed` is the sole terminal event; a
fork at `assessed` (refurbish / recycle / dispose) and a legal loop
(`refurbished → in_use`) model a device's real second-life paths. The file holds
**no validation logic** — only the transitions.

## Rules loader

`lifecycle/rules.py` turns the rules file into two validated, immutable value
objects:

- **`LifecycleTransition`** — one event type's allowed successor set (`source` +
  ordered `targets`), with an `is_terminal` property (empty targets), an
  `allows(target)` predicate and `to_dict`.
- **`LifecycleRuleSet`** — the whole loaded state machine (`version`, the
  per-event `transitions` in canonical order, and the `initial_events`), with
  `terminal_events`, `transition_for(source)`, `is_initial(event_type)`,
  `allows(source, target)` and `to_dict`.

`load_rules(path)` reads YAML (or JSON, by suffix), then **validates
aggressively**, raising a typed `LifecycleRuleError` (carrying
`details={"path": …}`) on any structural problem:

- file missing / unparseable / not a mapping / empty;
- missing or empty `version`;
- a missing `transitions` mapping, or one that is empty;
- an event-type key or target outside the fixed vocabulary (a typo becomes a
  load-time error, not a silent drop);
- an event type declared more than once, or **any** event type missing (every
  type must declare its successors, empty for terminal);
- a self-transition or a duplicate target within a successor set;
- **no** terminal event (a state machine that cannot end);
- a missing/empty `initial_events` list, an unknown initial event, or a duplicate.

The transitions are returned in **canonical event-type declaration order** for a
stable, reproducible rule set regardless of the file's key order.

## The deterministic engine

`lifecycle/engine.py` holds the `LifecycleEngine` — a stateless class with **no
model and no new inference**. Given the same events and rules it always produces
the same record (modulo the optional timestamp). Its API:

| Method | What it does |
|---|---|
| `validate(events, rules)` | Returns whether the ordered sequence is a legal path (see [Validation](#validation-and-the-state-machine)). |
| `build_record(device_id, events, rules, *, rules_version="", engine_version="", created_at=None)` | Validates, then snapshots the events into an immutable `LifecycleRecord` with the verdict, event count, current state and provenance. |
| `can_append(record, next_event, rules)` | Incremental predicate: whether `next_event` may legally extend `record` (see [Incremental appends](#incremental-appends)). |

`build_record` never raises on a rejected sequence — it returns a record with
`is_valid == False` so callers can inspect *why* it failed rather than catch an
exception. `current_state` is the latest event's wire value, or `None` for an
empty record.

## Validation and the state machine

`validate(events, rules)` returns whether the sequence is a legal path and
performs exactly three checks (an empty sequence is trivially valid — an empty
lifecycle):

1. **Initial event** — the first event's type must be a declared initial
   (genesis) event (`rules.is_initial(...)`).
2. **Legal transitions** — for each adjacent pair, the successor's type must be a
   declared successor of its predecessor
   (`rules.transition_for(previous).allows(current)`).
3. **Terminal respected** — a terminal event (empty successor set) admits nothing
   after it, so any event following it fails check 2. An undeclared source (only
   possible with a hand-built partial rule set in a test) never permits.

Any failure returns `False`; `build_record` stores that verdict in
`LifecycleRecord.is_valid`. A registered → assessed jump (skipping the required
intermediate stages) or an event after `disposed` are both rejected, while the
full `registered → in_use → collected → assessed → recycled → disposed` path and
the `refurbished → in_use` loop are accepted.

## Incremental appends

`can_append(record, next_event, rules)` is the predicate for building a lifecycle
one event at a time without re-validating the whole history:

- an **empty** record accepts any **initial** (genesis) event
  (`rules.is_initial(...)`);
- a **non-empty** record accepts an event only when it is a declared successor of
  the record's **current (latest)** event type (`rules.allows(last, next)`) — so
  nothing may follow a terminal event.

The service's `append(record, event)` composes a *fresh* record from the existing
events plus the new one (re-running full validation), so an illegal append is
reflected as `is_valid == False` on the result and the original record is never
mutated.

## Deterministic serialization

Every model's `to_json()` renders a **canonical** JSON serialization: keys are
sorted (`sort_keys=True`), non-ASCII is preserved (`ensure_ascii=False`) and
separators are fixed, so the same object always serializes to the exact same
bytes. Because each `to_dict()` is a pure function of the inputs, the **only**
source of variation is the optional timestamp. Passing `indent=` pretty-prints
while staying canonical; the default emits the most compact canonical form.
Building the same record twice with `clock=None` yields two byte-identical
records — which is what makes a lifecycle history auditable and reproducible, and
what lets the ledger anchor it deterministically.

## The service façade

`lifecycle/service.py` holds `LifecycleService` — the thin, injectable façade
over the engine. Like every service before it, **every collaborator is
constructor-injected with a sensible default**, so production wires nothing while
tests inject a hand-built rule set, a fixed clock, a custom engine or a specific
ledger. The rules are loaded **exactly once**, at construction, and held
immutably.

| Constructor argument | Default | Purpose |
|---|---|---|
| `config` | `LifecycleConfig()` | The rules locator. |
| `rules` | loaded from `config` | The validated `LifecycleRuleSet`. |
| `engine` | `LifecycleEngine()` | The validation engine. |
| `ledger` | `LedgerService()` | The M3.1/M3.2 ledger façade for anchoring. |
| `clock` | `_utc_now` | Callable returning the current time; `None` omits timestamps. |
| `engine_version` | `LIFECYCLE_ENGINE_VERSION` (`"1.0.0"`) | Version stamped onto every record. |

Its API:

| Method | What it does |
|---|---|
| `event(event_type, *, actor="", location="", note="")` | Factory for a single event, stamping the service's clock (or `None`). |
| `build(device_id, events)` | Validates and composes a `LifecycleRecord`, stamping engine/rules versions and an optional timestamp. |
| `append(record, event)` | Returns a new record with `event` appended and re-validated (never mutates the original). |
| `can_append(record, event)` | Whether `event` may legally extend `record`. |

Constructing the service with `clock=None` drops every timestamp, making each
produced record a **pure function of its inputs** — ideal for tests and
reproducible pipelines.

## Ledger integration through the backend abstraction (M3.2)

The lifecycle engine models a device's *history*; the M3.1 ledger core anchors a
passport's *verdicts*. The service ties the two together **through the ledger's
backend abstraction** — it depends only on the injected `LedgerService`, whose
storage and blockchain operations go through the technology-agnostic
`LedgerBackend` protocol (M3.2). So it can confirm a device's passport chain is
anchored, list anchored chains and load one to correlate it with a lifecycle
history, **without ever touching a concrete store**:

| Method | Delegates to | Returns |
|---|---|---|
| `is_anchored(chain_id)` | `ledger.exists(chain_id)` | Whether the ledger holds that chain. |
| `anchored_chain(chain_id)` | `ledger.load(chain_id)` | The stored `Blockchain`, or `None`. |
| `anchored_ids()` | `ledger.list_ids()` | Every chain id the ledger currently holds. |

Because the service depends only on the `LedgerService` façade (and it, in turn,
only on the `LedgerBackend` protocol), this works **identically** across the
memory, mock-Fabric and mock-Ethereum backends — swapping the ledger technology
never touches the lifecycle service. The service is **internal-only**: it exposes
no HTTP surface, performs no inference, no networking, no GPS tracking and no
persistence of its own.

## Configuration

`lifecycle/config.py` defines `LifecycleConfig`, a frozen, slotted value object
holding the one operational knob — the rules locator:

| Field | Default | Meaning |
|---|---|---|
| `rules_path` | `"lifecycle/data/transitions.yaml"` | Locator of the external rules file. |

`resolved_rules_path(package_root=…)` resolves a relative `rules_path` against
the `device_ai` package root, so the packaged rules file is found regardless of
the process working directory (an absolute path is used as-is).
`LifecycleConfig.from_settings(settings)` maps the one env-driven knob
(`settings.lifecycle_rules_path`) onto the config, mirroring the
trust/integrity/passport/ledger pattern. The corresponding
`Settings.lifecycle_rules_path` field defaults to the same packaged path, so no
environment variable is required to run the engine.

## Testing

Four test modules under `tests/`, all offline (no images, no models; only the
external rules file is read from disk) — **68** tests total, all passing:

- **`test_lifecycle_models.py`** (**14** tests) — the three value objects: the
  event-type wire values and `values()` ordering, fixed `to_dict` key order and
  values, `occurred_at`/`created_at` `None` serialization, canonical
  sorted-compact `to_json`, the `is_empty`/`event_types` properties, immutability
  of the frozen dataclasses, and the **no GPS/networking/streaming surface**
  invariant.
- **`test_lifecycle_rules.py`** (**25** tests) — the shipped rules load and
  validate (version, every event type declared once in canonical order, the
  `registered` initial event, the `disposed` terminal event, expected
  transitions, JSON round-trip), plus ~18 malformed-rules rejection cases built
  on a `_valid_mapping()` baseline and a `_write` JSON helper (missing file,
  empty, non-mapping root, missing version/transitions/initial_events, incomplete
  transitions, unknown key/target, self-transition, duplicate target, no terminal
  event, empty/duplicate/unknown initial events, non-list targets), the typed
  error's `code`/`path`, and the `LifecycleTransition` helpers.
- **`test_lifecycle_engine.py`** (**13** tests) — a hand-built `LifecycleRuleSet`
  (independent of the shipped YAML) drives `validate` (empty, single genesis,
  non-initial first, valid linear path, illegal transition, event after terminal,
  refurbish loop), `build_record` (provenance stamping, invalid-path-is-data,
  empty-is-valid-empty) and `can_append` (empty requires initial, follows current
  state, false after terminal).
- **`test_lifecycle_service.py`** (**16** tests) — the injectable façade against
  the **shipped** rules: config resolution (default/relative/absolute), default
  rule-loading and injected ledger, the clock-stamped/clockless `event` factory,
  `build`/`append`/`can_append`, clockless determinism (byte-identical
  `to_json`), append not mutating the original, and **ledger integration through
  the backend abstraction** — reporting absence for unknown ids and seeing a
  chain anchored via a `MockEthereumLedgerBackend` (built offline by a
  `_anchor_a_chain` helper that hand-crafts a passport/integrity/trust artefact).

The four modules add **68** tests, all passing; the module is `ruff`-, `black`-
and `isort`-clean and adds **zero** `mypy` errors.

## Integration guide

The engine is consumed **directly** (no HTTP). Orchestrating code records
lifecycle events as a device moves through its stages and hands them to the
`LifecycleService`:

```python
from device_ai.lifecycle import LifecycleEventType, LifecycleService

E = LifecycleEventType
svc = LifecycleService()                       # loads the shipped rules once

# Record a device's history as events accrue. The event() factory stamps the
# service clock; pass actor/location/note to annotate.
events = [
    svc.event(E.REGISTERED, actor="mint"),
    svc.event(E.IN_USE),
    svc.event(E.COLLECTED, location="Bengaluru hub"),
    svc.event(E.ASSESSED),
    svc.event(E.RECYCLED),
    svc.event(E.DISPOSED),
]
record = svc.build("ET-PP-0000000001", events)
assert record.is_valid                          # legal path through the state machine
assert record.current_state == "disposed"

payload = record.to_dict()                       # JSON-serializable history
canonical = record.to_json()                     # deterministic bytes
```

For an **incremental** build, `can_append(record, event)` guards each step and
`append(record, event)` returns a fresh, re-validated record without mutating the
original. For **deterministic** use (tests, reproducible pipelines) construct the
service with `clock=None` (drops the timestamp, making each record a pure function
of its inputs) and/or inject a hand-built `LifecycleRuleSet`, a custom
`LifecycleEngine` or a specific `LedgerService`.

### Correlating with an anchored chain

Once a device's passport chain is anchored on the ledger (M3.1/M3.2), the
lifecycle service correlates a history with it **through the injected ledger
façade** — never a concrete store:

```python
from device_ai.ledger import LedgerService, MockFabricLedgerBackend
from device_ai.lifecycle import LifecycleService

ledger = LedgerService(backend=MockFabricLedgerBackend())
svc = LifecycleService(ledger=ledger)            # depends only on the LedgerService

# … a passport chain is built and saved elsewhere, yielding a chain_id …
if svc.is_anchored(chain_id):
    chain = svc.anchored_chain(chain_id)         # the stored Blockchain, or None
    all_ids = svc.anchored_ids()                 # every anchored chain id
```

Swapping the backend (`MemoryLedgerBackend` → `MockFabricLedgerBackend` →
`MockEthereumLedgerBackend` → a future real anchor) never touches the lifecycle
service — the `is_anchored`/`anchored_chain`/`anchored_ids` surface is invariant.

## Worked examples

### A valid linear history

`svc.build(device_id, [registered, in_use, collected, assessed, recycled,
disposed])` validates each transition against the state machine and returns a
`LifecycleRecord` with `is_valid == True`, `event_count == 6`, `current_state ==
"disposed"` and the engine/rules versions stamped in. Its `to_json()` is
byte-identical across builds when the service is clockless.

### An illegal ordering — reported, not raised

`svc.build(device_id, [in_use])` begins with a non-initial event, so `validate`
returns `False` and the record carries `is_valid == False` (its `current_state`
is still `"in_use"` — the record is faithful to its input). Likewise appending
`assessed` straight after `registered`, or any event after `disposed`, yields
`is_valid == False`. The engine **never raises** on a rejected ordering —
reporting it is the guarantee the engine exists to provide.

### The refurbish loop — a legal second life

`svc.build(device_id, [registered, collected, assessed, refurbished, in_use])`
exercises the fork at `assessed` and the loop `refurbished → in_use`. Both are
declared transitions, so the record is valid and `current_state == "in_use"` — a
device back in service after refurbishment.

### A malformed rules file — an engine fault

If the external rules file omits an event type's transition, names an unknown
event, declares a self-transition or has no terminal event, `load_rules` (called
once at service construction) **raises** a `LifecycleRuleError` carrying the
offending `path` and a `LIFECYCLE_RULE_ERROR` code. This is the only way the
engine crashes — a malformed *policy* is an engine fault, unlike a malformed
*history*, which is data.

## Backward compatibility

M3.3 is **purely additive** and **internal-only**:

- **No endpoint, no router, no schema change.** `application.py` and the
  `/predict` request/response contract are untouched; the only new symbols are the
  `lifecycle/` package and two typed exceptions (`LifecycleError`,
  `LifecycleRuleError`).
- **No change to any upstream engine.** The engine consumes only lifecycle events
  a caller records and reaches the ledger solely through the existing
  `LedgerService` public surface — it adds nothing to M2.3/M2.4/M2.5/M3.1/M3.2.
- **One additive setting.** `Settings.lifecycle_rules_path` defaults to the
  packaged rules path, so no environment variable is required; the engine's policy
  is data in `lifecycle/data/transitions.yaml`, versioned independently of the
  code.

## Design rationale

- **A historian, not a tracker.** The engine's job is to model and validate a
  device's ordered history, not to *observe* it. There is no GPS, no event
  streaming, no QR scanning — a caller records events and the engine judges their
  ordering. That keeps M3.3 small, deterministic and fully unit-testable, and
  leaves real-world capture to the systems that own it.
- **Report illegal histories, raise engine faults.** A non-initial genesis event,
  an undeclared transition or an event after a terminal one is the engine's
  *input* to judge, so it is reported as `is_valid == False` — never a crash. Only
  a malformed *rules file* (an engine fault) raises. This asymmetry mirrors the
  M2.4/M2.5/M3.1 checkers.
- **Determinism is the point.** Canonical serialization and pure validation mean
  the same events always yield a byte-identical record — which is what lets the
  ledger anchor a history reproducibly and what makes the tests exact.
- **Policy is data, not logic.** The legal transitions, initial and terminal
  events are exactly what gets tuned as the lifecycle model evolves; keeping them
  in an external, versioned, strictly-validated file lets the policy change
  independently and fail loudly on a malformed file.
- **Deterministic and injectable.** Like every engine before it, the engine is a
  pure function and every collaborator is constructor-injected with a sensible
  default, so production wires nothing while tests inject a rule set, clock,
  engine or ledger at will.
- **Depend on the ledger façade, not a store.** The service references only the
  injected `LedgerService` (which itself depends only on the `LedgerBackend`
  protocol), so the ledger *technology* is a swappable implementation detail — the
  lifecycle engine never learns whether a chain lives in memory, mock Fabric, mock
  Ethereum or a future real anchor.





