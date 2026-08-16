"""Pipeline orchestrator — discover to report, honest at every step.

Runs the full P4.3.7 sequence for a single taxonomy class:

    preflight -> connectivity -> discover -> license/semantic/bbox gates ->
    acquire (materialise) -> annotation conversion + staging -> provenance ->
    frozen deduplication -> frozen Gate A/B validation -> automated QA ->
    frozen split -> readiness audit -> report

**Modes.** ``online`` requires egress; ``offline`` never probes the network and
ingests a caller-supplied local archive/directory; ``auto`` performs exactly one
connectivity probe and takes whichever path that single result allows. The probe
is never retried.

**Execution-order note.** Deduplication runs immediately before the frozen
Gate A/Gate B pass because automated QA consumes the duplicate verdict. Both
stages are read-only over the staged tree, so this ordering cannot change either
result; the validation stage record is emitted from that single frozen-gate pass
rather than from a second, redundant one.

**Non-fabrication.** Every stage that cannot proceed records a ``BLOCKED_*``
status and the exact reason. No image, count, license, provenance value or QA
verdict is ever invented, and the readiness audit is called, not simulated. A
run with no source reports ``BLOCKED_NO_SOURCE`` and stops.

**Protected data.** ``dataset_acquisition/candidate/p4_3_5_dataset_v1_candidate``
(P4.3.5) and ``dataset_acquisition/staging/p4_3_6_expansion_v1`` (P4.3.6) are
opened read-only for deduplication and are fingerprinted before and after the
run; the report carries both fingerprints so "unchanged" is a measurement, not a
claim.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .adapters import (
    AdapterUnavailable,
    HuggingFaceAdapter,
    KaggleAdapter,
    LocalArchiveAdapter,
    RoboflowAdapter,
    SourceAdapter,
    SourceCandidate,
)
from .config import AcquisitionConfig
from .dedup import run_dedup
from .errors import SourceUnavailableError, UnsupportedFormatError
from .formats import detect_format, distinct_source_labels, parse_annotations
from .gates import SourceVerdict, summarize_verdicts, verify_source
from .ingest import IngestOutcome, ingest_source
from .network import SKIPPED_OFFLINE, ConnectivityResult, check_connectivity
from .preflight import (
    PreflightResult,
    compare_fingerprints,
    fingerprint_tree,
    run_preflight,
)
from .provenance_model import build_manifest_dict
from .qa import QAOutcome, run_automated_qa
from .splitting import SplitOutcome, run_split

# Modes.
MODE_AUTO = "auto"
MODE_ONLINE = "online"
MODE_OFFLINE = "offline"
MODES = (MODE_AUTO, MODE_ONLINE, MODE_OFFLINE)

# Overall run statuses (stable, machine-readable).
STATUS_PREFLIGHT_FAILED = "PREFLIGHT_FAILED"
STATUS_BLOCKED_NO_SOURCE = "BLOCKED_NO_SOURCE"
STATUS_BLOCKED_NO_VERIFIED_SOURCE = "BLOCKED_NO_VERIFIED_SOURCE"
STATUS_BLOCKED_UNSUPPORTED_FORMAT = "BLOCKED_UNSUPPORTED_FORMAT"
STATUS_BLOCKED_NO_ACCEPTED_IMAGES = "BLOCKED_NO_ACCEPTED_IMAGES"
STATUS_WAVE_INCOMPLETE = "WAVE_INCOMPLETE"
STATUS_WAVE_VALIDATED = "WAVE_VALIDATED"
STATUS_DRY_RUN_OK = "DRY_RUN_OK"
STATUS_DRY_RUN_FAILED = "DRY_RUN_FAILED"

# Stage verdicts.
OK = "OK"
BLOCKED = "BLOCKED"
SKIPPED = "SKIPPED"
FAILED = "FAILED"
INCOMPLETE = "INCOMPLETE"


@dataclass(frozen=True, slots=True)
class Stage:
    """One executed pipeline stage.

    Attributes:
        name: Stable stage identifier.
        status: :data:`OK`, :data:`BLOCKED`, :data:`SKIPPED`, :data:`FAILED` or
            :data:`INCOMPLETE`.
        summary: One-line, ASCII outcome.
        detail: Structured evidence for the report.
    """

    name: str
    status: str
    summary: str
    detail: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Return a primitive-only, JSON-serialisable mapping."""
        return {
            "name": self.name,
            "status": self.status,
            "summary": self.summary,
            "detail": self.detail,
        }


@dataclass
class RunResult:
    """The complete outcome of one pipeline run.

    Attributes:
        mode_requested: The mode the operator asked for.
        mode_effective: The mode actually taken after the connectivity probe.
        dry_run: Whether the run wrote nothing.
        status: Overall run status.
        blockers: Exact blocking reasons (empty when none).
        stages: Every executed stage, in execution order.
        started_at: ISO-8601 UTC start timestamp.
        config: The layout used.
    """

    mode_requested: str
    mode_effective: str
    dry_run: bool
    started_at: str
    config: AcquisitionConfig
    status: str = STATUS_BLOCKED_NO_SOURCE
    blockers: list[str] = field(default_factory=list)
    stages: list[Stage] = field(default_factory=list)

    def stage(self, name: str) -> Stage | None:
        """Return the named stage record, or ``None`` when it did not run."""
        for entry in self.stages:
            if entry.name == name:
                return entry
        return None

    def add(
        self,
        name: str,
        status: str,
        summary: str,
        detail: dict[str, object] | None = None,
    ) -> Stage:
        """Append a stage record and return it."""
        entry = Stage(name=name, status=status, summary=summary, detail=detail or {})
        self.stages.append(entry)
        return entry

    def to_dict(self) -> dict[str, object]:
        """Return a primitive-only, JSON-serialisable mapping."""
        return {
            "sprint": "P4.3.7",
            "target_class": self.config.target_class,
            "wave_id": self.config.wave_id,
            "started_at": self.started_at,
            "mode_requested": self.mode_requested,
            "mode_effective": self.mode_effective,
            "dry_run": self.dry_run,
            "status": self.status,
            "blockers": list(self.blockers),
            "stage_status": {s.name: s.status for s in self.stages},
            "stages": [s.to_dict() for s in self.stages],
            "paths": {
                "staging_root": self.config.staging_root.as_posix(),
                "images_root": self.config.images_root.as_posix(),
                "labels_root": self.config.labels_root.as_posix(),
                "evidence_dir": self.config.evidence_dir.as_posix(),
                "report_path": self.config.report_path.as_posix(),
            },
        }


@dataclass(frozen=True, slots=True)
class LocalSourceSpec:
    """Operator-supplied description of a local source.

    Attributes:
        path: Directory or archive to ingest.
        license_raw: Explicit license string. Absent => the license gate reports
            ``UNVERIFIED`` and the source is not ingested. Never inferred.
        license_url: Optional supporting license URL.
        name: Dataset name (defaults to the path name).
        publisher: Publisher / contributor, if known.
        url: Origin URL, if known.
    """

    path: Path
    license_raw: str = ""
    license_url: str = ""
    name: str = ""
    publisher: str = ""
    url: str = ""


def _utc_now() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


def _credentials_status(env: Mapping[str, str]) -> dict[str, object]:
    """Report credential presence by **name only** — values are never read out.

    Args:
        env: Environment mapping to inspect.

    Returns:
        A primitive-only mapping naming, per remote adapter, which required
        credentials are present and which are missing. No secret is ever
        included, logged or written.
    """
    adapters: dict[str, object] = {}
    for name, keys in (
        ("roboflow", RoboflowAdapter.required_credentials),
        ("kaggle", KaggleAdapter.required_credentials),
        ("huggingface", HuggingFaceAdapter.required_credentials),
    ):
        present = sorted(key for key in keys if env.get(key))
        missing = sorted(key for key in keys if not env.get(key))
        adapters[name] = {
            "required": sorted(keys),
            "present": present,
            "missing": missing,
            "satisfied": not missing,
        }
    optional = ["HF_TOKEN", "HUGGINGFACE_TOKEN"]
    return {
        "note": "credential names only; no secret value is ever read out or stored",
        "adapters": adapters,
        "optional_present": sorted(key for key in optional if env.get(key)),
    }


def build_adapters(
    *,
    local: LocalSourceSpec | None,
    work_dir: Path,
    env: Mapping[str, str],
    coordinates: Mapping[str, list[dict]] | None,
) -> list[SourceAdapter]:
    """Assemble the adapter set for this run (local first, then remotes).

    Args:
        local: Operator-supplied local source, if any.
        work_dir: Scratch directory for extraction/downloads.
        env: Environment mapping consulted for credentials.
        coordinates: Explicitly configured remote coordinates by adapter name.

    Returns:
        The ordered adapter list.
    """
    coords = coordinates or {}
    adapters: list[SourceAdapter] = []
    if local is not None:
        adapters.append(
            LocalArchiveAdapter(
                local.path,
                work_dir=work_dir,
                license_raw=local.license_raw,
                license_url=local.license_url,
                source_name=local.name,
                publisher=local.publisher,
                source_url=local.url,
            )
        )
    adapters.append(
        RoboflowAdapter.from_env(
            work_dir=work_dir, env=env, coordinates=list(coords.get("roboflow", []))
        )
    )
    adapters.append(
        KaggleAdapter.from_env(
            work_dir=work_dir, env=env, coordinates=list(coords.get("kaggle", []))
        )
    )
    adapters.append(
        HuggingFaceAdapter.from_env(
            work_dir=work_dir, env=env, coordinates=list(coords.get("huggingface", []))
        )
    )
    return adapters


def discover(
    adapters: list[SourceAdapter], *, online: bool
) -> tuple[list[SourceCandidate], dict[str, object]]:
    """Run discovery across every adapter, recording each one's availability.

    Args:
        adapters: The adapter set.
        online: Whether egress is available this run.

    Returns:
        ``(candidates, adapter_statuses)``. An adapter that fails closed
        contributes its exact reason and no candidate.
    """
    candidates: list[SourceCandidate] = []
    statuses: dict[str, object] = {}
    for adapter in adapters:
        status = adapter.availability(online=online)
        entry: dict[str, object] = dict(status.to_dict())
        if not status.available:
            entry["candidates"] = 0
            statuses[adapter.name] = entry
            continue
        try:
            found = adapter.discover(online=online)
        except (AdapterUnavailable, SourceUnavailableError, UnsupportedFormatError) as exc:
            entry["available"] = False
            entry["reason"] = f"{type(exc).__name__}: {exc}"
            entry["candidates"] = 0
            statuses[adapter.name] = entry
            continue
        candidates.extend(found)
        entry["candidates"] = len(found)
        statuses[adapter.name] = entry
    return candidates, statuses


def read_source_labels(
    candidate: SourceCandidate,
) -> tuple[list[str] | None, object, str]:
    """Read a materialised candidate's declared class labels.

    Args:
        candidate: The candidate to inspect. When it carries a ``local_root`` the
            labels are read from its real annotations; otherwise its declared
            ``source_class`` is used.

    Returns:
        ``(labels, detected_format, error)``. ``labels`` is ``None`` when the
        source is not on local disk yet or its format is unsupported, in which
        case ``error`` states exactly why.
    """
    if not candidate.local_root:
        declared = candidate.source_class.strip()
        return ([declared] if declared else None), None, ""
    root = Path(candidate.local_root)
    detected = detect_format(root)
    if not detected.supported:
        return None, detected, detected.detail
    try:
        annotations = parse_annotations(detected, root)
    except (ValueError, OSError) as exc:
        return None, detected, f"{type(exc).__name__}: {exc}"
    return distinct_source_labels(annotations), detected, ""


def run_pipeline(
    *,
    config: AcquisitionConfig,
    mode: str = MODE_AUTO,
    local_source: LocalSourceSpec | None = None,
    coordinates: Mapping[str, list[dict]] | None = None,
    dry_run: bool = False,
    env: Mapping[str, str] | None = None,
    probe: Callable[[], bool] | None = None,
    readiness_audit: Callable[..., dict] | None = None,
    timestamp: str | None = None,
    settings: object | None = None,
) -> RunResult:
    """Execute the acquisition pipeline end to end.

    Args:
        config: Filesystem layout and target identity.
        mode: ``auto``, ``online`` or ``offline``.
        local_source: Operator-supplied local archive/directory, if any.
        coordinates: Explicitly configured remote source coordinates, keyed by
            adapter name. Remote adapters discover nothing without them.
        dry_run: Validate the whole pipeline without writing production or
            staging data.
        env: Environment mapping for credential checks (defaults to ``os.environ``).
        probe: Injected connectivity probe (defaults to a single TCP connect).
        readiness_audit: Injected readiness auditor
            ``(images_root=, labels_root=) -> dict``. When absent the readiness
            stage reports ``UNAVAILABLE`` with the exact reason rather than
            simulating a verdict.
        timestamp: Injected ISO-8601 UTC timestamp (defaults to now) so runs are
            reproducible in tests.
        settings: Optional injected settings (defaults to ``get_settings()``).

    Returns:
        A :class:`RunResult` carrying every stage record and the overall status.
    """
    started = timestamp or _utc_now()
    environ = env if env is not None else os.environ
    result = RunResult(
        mode_requested=mode,
        mode_effective=mode,
        dry_run=dry_run,
        started_at=started,
        config=config,
    )

    # ---------------------------------------------------------------- preflight
    preflight = run_preflight(config, settings=settings)
    result.add(
        "preflight",
        OK if preflight.passed else FAILED,
        (
            "frozen taxonomy, split ratios/seed, duplicate threshold and every "
            "frozen component verified"
            if preflight.passed
            else "frozen-contract verification failed: "
            + ", ".join(check.name for check in preflight.failures)
        ),
        preflight.to_dict(),
    )
    if not preflight.passed:
        result.status = STATUS_PREFLIGHT_FAILED
        result.blockers = [
            f"{check.name}: {check.detail or check.verdict}"
            for check in preflight.failures
        ]
        return result

    taxonomy_id = int(preflight.frozen_values.get("router_class_id", -1))
    num_classes = int(preflight.frozen_values.get("num_classes", 0))

    # ------------------------------------------------------------- connectivity
    connectivity = check_connectivity(
        offline=(mode == MODE_OFFLINE),
        **({"probe": probe} if probe is not None else {}),
    )
    online = connectivity.online
    result.mode_effective = (
        MODE_OFFLINE if (mode == MODE_OFFLINE or not online) else MODE_ONLINE
    )
    result.add(
        "network",
        OK if connectivity.status != SKIPPED_OFFLINE else SKIPPED,
        f"network status: {connectivity.status} (single probe, never retried)",
        connectivity.to_dict(),
    )

    if mode == MODE_ONLINE and not online:
        result.status = STATUS_BLOCKED_NO_SOURCE
        result.blockers = [
            "--mode online was requested but the single connectivity probe "
            f"reported {connectivity.status}; no network acquisition is possible. "
            "Re-run with --mode offline --source <archive> to ingest a local dataset."
        ]
        result.add(
            "credentials",
            SKIPPED,
            "skipped: online mode blocked before any credential was consulted",
            {"note": "no secret is ever read out or stored"},
        )
        _finalize_protected(result, config, preflight)
        return result

    # -------------------------------------------------------------- credentials
    credentials = _credentials_status(environ)
    result.add(
        "credentials",
        OK,
        "credential presence recorded by name only (no secret is ever read out)",
        credentials,
    )

    # ----------------------------------------------------------------- discover
    adapters = build_adapters(
        local=local_source, work_dir=config.work_dir, env=environ, coordinates=coordinates
    )
    if not dry_run:
        config.work_dir.mkdir(parents=True, exist_ok=True)
    candidates, adapter_statuses = discover(adapters, online=online)
    result.add(
        "discover",
        OK if candidates else BLOCKED,
        f"{len(candidates)} candidate source(s) discovered across "
        f"{len(adapters)} adapter(s)",
        {
            "candidate_count": len(candidates),
            "adapters": adapter_statuses,
            "candidates": [c.to_dict() for c in candidates],
        },
    )

    if not candidates:
        result.status = STATUS_BLOCKED_NO_SOURCE
        result.blockers = _no_source_blockers(
            adapter_statuses, local_source=local_source, connectivity=connectivity
        )
        _finalize_protected(result, config, preflight)
        return result

    # ------------------------------------------------------------------- verify
    verdicts: list[SourceVerdict] = []
    materialized: list[tuple[SourceVerdict, Path, object]] = []
    for candidate in candidates:
        adapter = next(a for a in adapters if a.name == candidate.adapter)
        local_root: Path | None = None
        if candidate.local_root:
            local_root = Path(candidate.local_root)
        elif online:
            try:
                local_root = adapter.materialize(candidate, online=online)
            except AdapterUnavailable:
                local_root = None
        if local_root is not None:
            candidate = _with_root(candidate, local_root)

        labels, detected, error = read_source_labels(candidate)
        verdict = verify_source(candidate, labels=labels)
        if error:
            verdict = _append_reason(verdict, f"format: {error}")
        verdicts.append(verdict)
        if verdict.accepted and local_root is not None and detected is not None:
            materialized.append((verdict, local_root, detected))

    verification = summarize_verdicts(verdicts)
    accepted_sources = [v for v in verdicts if v.accepted]
    result.add(
        "verify",
        OK if accepted_sources else BLOCKED,
        f"{len(accepted_sources)} source(s) cleared the license + bbox + semantic "
        f"gates; {verification['rejected']} rejected, "
        f"{verification['unverified']} unverified",
        verification,
    )

    if not accepted_sources:
        result.status = STATUS_BLOCKED_NO_VERIFIED_SOURCE
        result.blockers = [
            f"{v.candidate.name or v.candidate.adapter}: {'; '.join(v.reasons)}"
            for v in verdicts
        ] or ["no source cleared the verification gates"]
        _finalize_protected(result, config, preflight)
        return result

    if not materialized:
        result.status = STATUS_BLOCKED_UNSUPPORTED_FORMAT
        result.blockers = [
            "verified source(s) could not be read from local disk in a supported "
            "annotation format (YOLO / COCO / Pascal VOC)"
        ]
        _finalize_protected(result, config, preflight)
        return result

    # ------------------------------------ acquire + annotation conversion/ingest
    ingest = _ingest_all(
        materialized,
        config=config,
        taxonomy_id=taxonomy_id,
        timestamp=started,
        dry_run=dry_run,
    )
    result.add(
        "acquire",
        OK,
        f"{len(materialized)} verified source(s) materialised on local disk",
        {
            "sources": [
                {
                    "name": verdict.candidate.name,
                    "adapter": verdict.candidate.adapter,
                    "download_mechanism": verdict.candidate.download_mechanism,
                    "local_root": root.as_posix(),
                    "format": getattr(detected, "format_name", ""),
                }
                for verdict, root, detected in materialized
            ]
        },
    )
    result.add(
        "annotation_conversion",
        OK if ingest.images_retained else BLOCKED,
        (
            f"{ingest.images_retained} image(s) staged with {ingest.boxes_staged} "
            f"router box(es) at taxonomy id {taxonomy_id}; "
            f"{ingest.images_rejected} source image(s) rejected"
        ),
        ingest.to_dict(),
    )

    # --------------------------------------------------------------- provenance
    provenance_payload = build_manifest_dict(
        ingest.provenance, target_class=config.target_class, import_timestamp=started
    )
    provenance_complete = (
        ingest.provenance_complete == len(ingest.provenance) and bool(ingest.provenance)
    )
    if not dry_run and ingest.provenance:
        config.evidence_dir.mkdir(parents=True, exist_ok=True)
        config.provenance_path.write_text(
            json.dumps(provenance_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    result.add(
        "provenance",
        OK if provenance_complete else BLOCKED,
        (
            f"{ingest.provenance_complete}/{len(ingest.provenance)} provenance "
            "record(s) carry every mandatory field"
        ),
        {
            "written": bool(not dry_run and ingest.provenance),
            "path": config.provenance_path.as_posix(),
            "total_records": provenance_payload["total_records"],
            "complete_records": provenance_payload["complete_records"],
            "incomplete_records": provenance_payload["incomplete_records"],
            "fields": [
                "checksum_sha256",
                "original_filename",
                "source_dataset",
                "source_identifier",
                "source_class",
                "taxonomy_class",
                "taxonomy_id",
                "license_id",
                "import_timestamp",
            ],
        },
    )

    if dry_run:
        result.status = STATUS_DRY_RUN_OK
        result.add(
            "dry_run",
            OK,
            (
                f"dry run complete: {ingest.images_retained} image(s) would be "
                "staged; nothing was written"
            ),
            {"writes_performed": 0},
        )
        _finalize_protected(result, config, preflight)
        return result

    if not ingest.staged:
        result.status = STATUS_BLOCKED_NO_ACCEPTED_IMAGES
        result.blockers = [
            "no source image survived the per-box semantic gate and geometry "
            "validation; nothing was staged"
        ]
        _finalize_protected(result, config, preflight)
        return result

    # -------------------------------------------------------------- dedup + QA
    dedup = run_dedup(
        batch_images_root=config.images_root,
        protected_roots=config.protected_roots,
        settings=settings,
    )
    result.add(
        "deduplication",
        OK,
        (
            f"frozen detector (Hamming <= {dedup.hamming_threshold}) flagged "
            f"{dedup.num_batch_duplicates} new image(s); protected data scanned "
            "read-only and first"
        ),
        dedup.to_dict(),
    )

    qa = run_automated_qa(
        images_root=config.images_root,
        labels_root=config.labels_root,
        taxonomy_id=taxonomy_id,
        num_classes=num_classes,
        duplicate_paths=dedup.batch_duplicates,
        settings=settings,
    )
    result.add(
        "validation",
        OK if (qa.gate_a_valid and qa.gate_b_valid) else INCOMPLETE,
        (
            f"frozen Gate A image validation: {'valid' if qa.gate_a_valid else 'issues'}; "
            f"frozen Gate B annotation validation: "
            f"{'valid' if qa.gate_b_valid else 'issues'}"
        ),
        {
            "gate_a": qa.gate_a_summary,
            "gate_b": qa.gate_b_summary,
            "validators": [
                "device_ai.dataset.image_validation.ImageValidator (frozen)",
                "device_ai.dataset.validator.AnnotationValidator (frozen)",
            ],
            "note": (
                "emitted from the single frozen-gate pass that also produced the "
                "automated QA decisions"
            ),
        },
    )
    result.add(
        "automated_qa",
        OK if qa.accepted else BLOCKED,
        (
            f"{len(qa.accepted)} AUTO_ACCEPT, {len(qa.rejected)} AUTO_REJECT, "
            f"{len(qa.unverified)} UNVERIFIED (visual verification NOT_PERFORMED)"
        ),
        qa.to_dict(),
    )

    if not qa.accepted:
        result.status = STATUS_BLOCKED_NO_ACCEPTED_IMAGES
        result.blockers = [
            "no staged image reached AUTO_ACCEPT; uncertainty is never converted "
            "to acceptance"
        ]
        _write_evidence(config, result, qa=qa, dedup=dedup, split=None)
        _finalize_protected(result, config, preflight)
        return result

    # -------------------------------------------------------------------- split
    split = run_split(
        list(qa.accepted),
        labels_root=config.labels_root,
        taxonomy_id=taxonomy_id,
        num_classes=num_classes,
        settings=settings,
    )
    result.add(
        "split",
        OK if split.verified else INCOMPLETE,
        (
            f"frozen splitter {list(split.ratios)} seed {split.seed}: "
            f"{split.counts}; {split.detail}"
        ),
        split.to_dict(),
    )

    # ---------------------------------------------------------------- readiness
    result.add(*_readiness_stage(config, readiness_audit))

    # ------------------------------------------------------------------ outcome
    result.status = (
        STATUS_WAVE_VALIDATED if split.verified else STATUS_WAVE_INCOMPLETE
    )
    if not split.verified:
        result.blockers = [f"split: {split.detail}"]

    _write_evidence(config, result, qa=qa, dedup=dedup, split=split)
    _finalize_protected(result, config, preflight)
    return result


def _with_root(candidate: SourceCandidate, root: Path) -> SourceCandidate:
    """Return a copy of ``candidate`` carrying a materialised local root."""
    from dataclasses import replace

    return replace(candidate, local_root=root.as_posix())


def _append_reason(verdict: SourceVerdict, reason: str) -> SourceVerdict:
    """Return a copy of ``verdict`` with one more recorded reason."""
    from dataclasses import replace

    return replace(verdict, reasons=(*verdict.reasons, reason))


def _no_source_blockers(
    adapter_statuses: dict[str, object],
    *,
    local_source: LocalSourceSpec | None,
    connectivity: ConnectivityResult,
) -> list[str]:
    """Explain, per adapter, exactly why no source was discovered."""
    blockers: list[str] = []
    if local_source is None:
        blockers.append(
            "no local source supplied (--source); offline acquisition needs a "
            "local dataset directory or archive"
        )
    blockers.append(f"network: {connectivity.status} - {connectivity.detail}")
    for name, status in sorted(adapter_statuses.items()):
        if isinstance(status, dict):
            blockers.append(f"{name}: {status.get('reason', 'no candidates')}")
    return blockers


def _ingest_all(
    materialized: list[tuple[SourceVerdict, Path, object]],
    *,
    config: AcquisitionConfig,
    taxonomy_id: int,
    timestamp: str,
    dry_run: bool,
) -> IngestOutcome:
    """Ingest every verified, materialised source into one staged batch."""
    combined = IngestOutcome(dry_run=dry_run)
    for verdict, root, detected in materialized:
        annotations = parse_annotations(detected, root)  # type: ignore[arg-type]
        outcome = ingest_source(
            annotations,
            detected=detected,  # type: ignore[arg-type]
            images_root=config.images_root,
            labels_root=config.labels_root,
            source_dataset=verdict.candidate.name or verdict.candidate.adapter,
            source_url=verdict.candidate.url,
            publisher=verdict.candidate.publisher,
            license_decision=verdict.license_decision,
            taxonomy_class=config.target_class,
            taxonomy_id=taxonomy_id,
            import_timestamp=timestamp,
            dry_run=dry_run,
        )
        combined = IngestOutcome(
            staged=[*combined.staged, *outcome.staged],
            provenance=[*combined.provenance, *outcome.provenance],
            rejections=[*combined.rejections, *outcome.rejections],
            images_discovered=combined.images_discovered + outcome.images_discovered,
            boxes_discovered=combined.boxes_discovered + outcome.boxes_discovered,
            boxes_semantically_rejected=(
                combined.boxes_semantically_rejected
                + outcome.boxes_semantically_rejected
            ),
            boxes_geometry_rejected=(
                combined.boxes_geometry_rejected + outcome.boxes_geometry_rejected
            ),
            boxes_staged=combined.boxes_staged + outcome.boxes_staged,
            source_format=combined.source_format or outcome.source_format,
            dry_run=dry_run,
        )
    return combined


def _readiness_stage(
    config: AcquisitionConfig, readiness_audit: Callable[..., dict] | None
) -> tuple[str, str, str, dict[str, object]]:
    """Run the injected readiness audit over the staged wave (never simulated)."""
    scope = {
        "scope": "ROUTER_WAVE_VALIDATION",
        "not": "FULL_DATASET_RELEASE_READINESS",
        "note": (
            "This audit covers the router wave in isolation. Coverage is expected "
            "to report INCOMPLETE because the 19-class taxonomy is not yet covered "
            "by this batch; that is a coverage fact, not a pipeline failure. The "
            "protected P4.3.5/P4.3.6 batches are not merged by this pipeline."
        ),
    }
    if readiness_audit is None:
        return (
            "readiness",
            SKIPPED,
            "readiness audit not injected; no verdict simulated",
            {
                **scope,
                "status": "UNAVAILABLE",
                "reason": (
                    "no readiness auditor was injected into the pipeline; the "
                    "audit was neither run nor simulated"
                ),
            },
        )
    try:
        report = readiness_audit(
            images_root=config.images_root, labels_root=config.labels_root
        )
    except Exception as exc:  # noqa: BLE001 - report, never fabricate a verdict
        return (
            "readiness",
            FAILED,
            f"readiness audit raised {type(exc).__name__}",
            {**scope, "status": "ERROR", "reason": f"{type(exc).__name__}: {exc}"},
        )
    overall = str(report.get("overall", "UNKNOWN"))
    return (
        "readiness",
        OK if overall in {"READY", "INCOMPLETE"} else INCOMPLETE,
        f"readiness audit over the router wave: {overall}",
        {**scope, "report": report},
    )


def _write_evidence(
    config: AcquisitionConfig,
    result: RunResult,
    *,
    qa: QAOutcome | None,
    dedup: object | None,
    split: SplitOutcome | None,
) -> None:
    """Write the per-stage JSON evidence files into the review directory."""
    config.evidence_dir.mkdir(parents=True, exist_ok=True)
    payloads: dict[str, object] = {}
    if qa is not None:
        payloads["automated_qa.json"] = qa.to_dict()
    if dedup is not None and hasattr(dedup, "to_dict"):
        payloads["duplicate_evidence.json"] = dedup.to_dict()  # type: ignore[attr-defined]
    if split is not None:
        payloads["split_assignment.json"] = split.to_dict()
    for name, payload in payloads.items():
        (config.evidence_dir / name).write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


def _finalize_protected(
    result: RunResult, config: AcquisitionConfig, preflight: PreflightResult
) -> None:
    """Re-fingerprint protected trees and record whether they changed."""
    after = [fingerprint_tree(label, root) for label, root in config.protected_roots]
    comparison = compare_fingerprints(preflight.fingerprints, after)
    unchanged = bool(comparison["all_unchanged"])
    result.add(
        "protected_state",
        OK if unchanged else FAILED,
        (
            "protected P4.3.5 / P4.3.6 trees byte-identical before and after"
            if unchanged
            else "PROTECTED TREE CHANGED - investigate immediately"
        ),
        comparison,
    )
