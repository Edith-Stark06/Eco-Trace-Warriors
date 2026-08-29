"""Run report rendering — Markdown + JSON, ASCII only.

Renders a :class:`~device_ai.acquisition.pipeline.RunResult` into the report
required by spec §12. Every field is read from the run's stage records; nothing
is defaulted to a flattering value. When a stage did not run, the report says so
(``NOT RUN`` / ``BLOCKED``) rather than printing a zero that could be mistaken
for a measurement.

The renderer also carries the honesty framing the wave needs:

* ``ROUTER WAVE VALIDATION`` is reported separately from ``FULL DATASET RELEASE
  READINESS`` — an ``INCOMPLETE`` coverage verdict for the 19-class taxonomy is
  expected and is not a pipeline failure;
* automated QA acceptance is labelled as resting on structural gates plus
  source-verified bbox semantics, with visual verification ``NOT_PERFORMED``;
* the protected-state section prints measured before/after content hashes.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .pipeline import RunResult

_NOT_RUN = "NOT RUN"


def _stage_detail(result: RunResult, name: str) -> dict[str, object]:
    """Return a stage's detail mapping, or an empty mapping when it did not run."""
    stage = result.stage(name)
    if stage is None:
        return {}
    return stage.detail


def _stage_status(result: RunResult, name: str) -> str:
    """Return a stage's status, or ``NOT RUN``."""
    stage = result.stage(name)
    return stage.status if stage is not None else _NOT_RUN


def _get(mapping: dict[str, object], *keys: str, default: object = None) -> object:
    """Walk nested mappings safely, returning ``default`` when a key is absent."""
    current: object = mapping
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def _count(mapping: dict[str, object], key: str) -> str:
    """Render a count, or ``NOT RUN`` when the stage produced nothing."""
    if not mapping or key not in mapping:
        return _NOT_RUN
    return str(mapping[key])


def _bullet_list(items: list[str], *, empty: str) -> list[str]:
    """Render a Markdown bullet list, or a single line when empty."""
    if not items:
        return [f"- {empty}"]
    return [f"- {item}" for item in items]


def render_json(result: RunResult, *, git_status: str = "") -> str:
    """Render the machine-readable run report.

    Args:
        result: The completed run.
        git_status: Captured ``git status --short`` output (recorded verbatim).

    Returns:
        A deterministic, sorted JSON document ending in a newline.
    """
    payload = result.to_dict()
    payload["git_status_short"] = git_status
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _license_rows(verify_detail: dict[str, object]) -> list[str]:
    """Render one table row per source license decision."""
    verdicts = _get(verify_detail, "verdicts", default=[])
    rows: list[str] = []
    if not isinstance(verdicts, list):
        return rows
    for entry in verdicts:
        if not isinstance(entry, dict):
            continue
        source = entry.get("source", {})
        name = str(_get(source, "name", default="") or _get(source, "adapter", default="?"))
        license_info = entry.get("license", {})
        rows.append(
            "| {name} | {verdict} | {raw} | {normalized} | {reason} |".format(
                name=name,
                verdict=str(_get(license_info, "verdict", default="?")),
                raw=str(_get(license_info, "raw", default="") or "(none)"),
                normalized=str(_get(license_info, "normalized_id", default="") or "-"),
                reason=str(_get(license_info, "reason", default="")),
            )
        )
    return rows


def _semantic_rows(verify_detail: dict[str, object]) -> list[str]:
    """Render one table row per source semantic decision."""
    verdicts = _get(verify_detail, "verdicts", default=[])
    rows: list[str] = []
    if not isinstance(verdicts, list):
        return rows
    for entry in verdicts:
        if not isinstance(entry, dict):
            continue
        source = entry.get("source", {})
        name = str(_get(source, "name", default="") or _get(source, "adapter", default="?"))
        semantic = entry.get("semantic", {})
        accepted = _get(semantic, "accepted_labels", default=[])
        rejected = _get(semantic, "rejected_labels", default=[])
        rows.append(
            "| {name} | {verdict} | {accepted} | {rejected} |".format(
                name=name,
                verdict=str(_get(semantic, "verdict", default="?")),
                accepted=", ".join(str(x) for x in accepted) if accepted else "-",
                rejected=", ".join(str(x) for x in rejected) if rejected else "-",
            )
        )
    return rows


def _protected_rows(protected_detail: dict[str, object]) -> list[str]:
    """Render the measured protected-tree comparison rows."""
    trees = _get(protected_detail, "trees", default=[])
    rows: list[str] = []
    if not isinstance(trees, list):
        return rows
    for tree in trees:
        if not isinstance(tree, dict):
            continue
        before = str(tree.get("content_hash_before", ""))
        after = str(tree.get("content_hash_after", ""))
        rows.append(
            "| {label} | {exists} | {files} | {images} | {labels} | {before} | "
            "{after} | {verdict} |".format(
                label=str(tree.get("label", "?")),
                exists=str(tree.get("exists", "?")),
                files=str(tree.get("file_count_after", "?")),
                images=str(tree.get("image_count", "?")),
                labels=str(tree.get("label_count", "?")),
                before=before[:12] or "-",
                after=after[:12] or "-",
                verdict="UNCHANGED" if tree.get("unchanged") else "CHANGED",
            )
        )
    return rows


def render_markdown(result: RunResult, *, git_status: str = "") -> str:
    """Render the human-readable automation report.

    Args:
        result: The completed run.
        git_status: Captured ``git status --short`` output (recorded verbatim).

    Returns:
        An ASCII Markdown document.
    """
    preflight = _stage_detail(result, "preflight")
    network = _stage_detail(result, "network")
    credentials = _stage_detail(result, "credentials")
    discover = _stage_detail(result, "discover")
    verify = _stage_detail(result, "verify")
    ingest = _stage_detail(result, "annotation_conversion")
    provenance = _stage_detail(result, "provenance")
    validation = _stage_detail(result, "validation")
    dedup = _stage_detail(result, "deduplication")
    qa = _stage_detail(result, "automated_qa")
    split = _stage_detail(result, "split")
    readiness = _stage_detail(result, "readiness")
    protected = _stage_detail(result, "protected_state")
    frozen = _get(preflight, "frozen_values", default={})
    frozen_map = frozen if isinstance(frozen, dict) else {}
    header_class_id = frozen_map.get(
        "target_class_id", frozen_map.get("router_class_id", "UNVERIFIED")
    )
    observed_class_id = frozen_map.get(
        "target_class_id", frozen_map.get("router_class_id", _NOT_RUN)
    )

    lines: list[str] = [
        "# P4.3.7 — Router Automation Report",
        "",
        (
            f"**Sprint:** P4.3.7 — automated single-class acquisition "
            f"({result.config.target_class}, taxonomy id {header_class_id})"
        ),
        "**Component:** Device Intelligence Engine (DIE) — YOLO Detector (M1.4)",
        f"**Run started:** {result.started_at}",
        f"**Wave id:** `{result.config.wave_id}`",
        f"**Overall status:** **{result.status}**",
        "",
        "> **Honesty contract.** Every number below is measured by a frozen "
        "component or is reported as `NOT RUN` / `BLOCKED` / `UNVERIFIED`. No "
        "image, count, license, provenance value or QA verdict is inferred, and "
        "no dataset was released or committed by this run.",
        "",
        "---",
        "",
        "## 1. Execution mode",
        "",
        f"- Mode requested: `{result.mode_requested}`",
        f"- Mode effective: `{result.mode_effective}`",
        f"- Dry run: `{result.dry_run}`",
        "",
        "## 2. Network status",
        "",
        f"- Status: **{_get(network, 'status', default=_NOT_RUN)}**",
        f"- Probe attempted: `{_get(network, 'probed', default=False)}`",
        f"- Target: `{_get(network, 'target', default='') or '-'}`",
        f"- Detail: {_get(network, 'detail', default='-')}",
        "- Retry policy: a single probe, never retried.",
        "",
        "## 3. Credentials status (names only, no secrets)",
        "",
        "| Adapter | Required | Present | Missing | Satisfied |",
        "| --- | --- | --- | --- | --- |",
    ]

    adapters = _get(credentials, "adapters", default={})
    if isinstance(adapters, dict) and adapters:
        for name in sorted(adapters):
            entry = adapters[name]
            if not isinstance(entry, dict):
                continue
            lines.append(
                "| {name} | {req} | {present} | {missing} | {ok} |".format(
                    name=name,
                    req=", ".join(str(x) for x in entry.get("required", [])) or "-",
                    present=", ".join(str(x) for x in entry.get("present", [])) or "-",
                    missing=", ".join(str(x) for x in entry.get("missing", [])) or "-",
                    ok=str(entry.get("satisfied", False)),
                )
            )
    else:
        lines.append(f"| - | - | - | - | {_NOT_RUN} |")

    lines.extend(
        [
            "",
            "No credential *value* is read out, logged or written anywhere by this "
            "pipeline; only the presence of a variable name is recorded.",
            "",
            "## 4. Sources discovered / verified / rejected",
            "",
            f"- Discovered: {_count(discover, 'candidate_count')}",
            f"- Verified (accepted): {_count(verify, 'accepted')}",
            f"- Rejected: {_count(verify, 'rejected')}",
            f"- Unverified: {_count(verify, 'unverified')}",
            "",
            "### Adapter availability",
            "",
            "| Adapter | Available | Candidates | Reason |",
            "| --- | --- | --- | --- |",
        ]
    )
    adapter_statuses = _get(discover, "adapters", default={})
    if isinstance(adapter_statuses, dict) and adapter_statuses:
        for name in sorted(adapter_statuses):
            entry = adapter_statuses[name]
            if not isinstance(entry, dict):
                continue
            lines.append(
                "| {name} | {available} | {count} | {reason} |".format(
                    name=name,
                    available=str(entry.get("available", "?")),
                    count=str(entry.get("candidates", 0)),
                    reason=str(entry.get("reason", "")),
                )
            )
    else:
        lines.append(f"| - | - | - | {_NOT_RUN} |")

    lines.extend(
        [
            "",
            "## 5. License decisions",
            "",
            "Licenses are **never inferred**: an absent or unrecognised license is "
            "`UNVERIFIED`, and a non-commercial / no-derivatives / proprietary "
            "license is `REJECTED`.",
            "",
            "| Source | Verdict | Raw license | Normalised | Reason |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    license_rows = _license_rows(verify)
    lines.extend(license_rows or [f"| - | {_NOT_RUN} | - | - | no source verified |"])

    lines.extend(
        [
            "",
            "## 6. Semantic decisions",
            "",
            "A source label clears the gate only when it **explicitly** denotes "
            "`router`. Ambiguous labels (`modem/router`, `gateway`, `switch`, "
            "`access point`, `set-top box`, `networking device`, generic "
            "electronics) are rejected, and classification-only labels are never "
            "promoted to bbox labels.",
            "",
            "| Source | Verdict | Accepted labels | Rejected labels |",
            "| --- | --- | --- | --- |",
        ]
    )
    semantic_rows = _semantic_rows(verify)
    lines.extend(semantic_rows or [f"| - | {_NOT_RUN} | - | - |"])

    lines.extend(
        [
            "",
            "## 7. Images discovered / retained / rejected",
            "",
            f"- Source images discovered: {_count(ingest, 'images_discovered')}",
            f"- Images retained (staged): {_count(ingest, 'images_retained')}",
            f"- Images rejected: {_count(ingest, 'images_rejected')}",
            f"- Boxes discovered: {_count(ingest, 'boxes_discovered')}",
            f"- Boxes dropped by the per-box semantic gate: "
            f"{_count(ingest, 'boxes_semantically_rejected')}",
            f"- Boxes dropped by geometry validation: "
            f"{_count(ingest, 'boxes_geometry_rejected')}",
            f"- Boxes staged: {_count(ingest, 'boxes_staged')}",
            "",
            "### Rejection reasons",
            "",
        ]
    )
    rejection_counts = _get(ingest, "rejection_counts", default={})
    if isinstance(rejection_counts, dict) and rejection_counts:
        lines.extend(
            f"- `{code}`: {count}" for code, count in sorted(rejection_counts.items())
        )
    else:
        lines.append(f"- {_NOT_RUN} (no ingestion performed)")

    lines.extend(
        [
            "",
            "## 8. Provenance completeness",
            "",
            f"- Records: {_count(provenance, 'total_records')}",
            f"- Complete: {_count(provenance, 'complete_records')}",
            f"- Incomplete: {_count(provenance, 'incomplete_records')}",
            f"- Manifest written: {_count(provenance, 'written')}",
            f"- Manifest path: `{_get(provenance, 'path', default='-')}`",
            "",
            "Mandatory per-image fields: SHA-256, original filename, source "
            "dataset, source identifier, source class, taxonomy class + id, "
            "license evidence, import timestamp.",
            "",
            "## 9. Annotation counts and validation",
            "",
            f"- Validation status: **{_stage_status(result, 'validation')}**",
            f"- Frozen Gate A (ImageValidator) valid: "
            f"{_get(qa, 'gate_a_valid', default=_NOT_RUN)}",
            f"- Frozen Gate B (AnnotationValidator) valid: "
            f"{_get(qa, 'gate_b_valid', default=_NOT_RUN)}",
            f"- Total boxes in staged labels: {_count(qa, 'total_boxes')}",
            f"- Class histogram: {_get(qa, 'class_counts', default=_NOT_RUN)}",
            f"- Gate B detail: {_get(validation, 'gate_b', default=_NOT_RUN)}",
            "",
            "## 10. Duplicate results (frozen detector, unmodified)",
            "",
            f"- Status: **{_get(dedup, 'status', default=_NOT_RUN)}**",
            f"- Hamming threshold: {_get(dedup, 'hamming_threshold', default=_NOT_RUN)} "
            "(read from settings; never changed by this pipeline)",
            f"- Protected images scanned (read-only): "
            f"{_count(dedup, 'protected_scanned')}",
            f"- New images scanned: {_count(dedup, 'batch_scanned')}",
            f"- New images flagged as duplicates: "
            f"{_count(dedup, 'num_batch_duplicates')}",
            f"- Ordering: {_get(dedup, 'ordering', default='-')}",
            f"- Detail: {_get(dedup, 'detail', default='-')}",
            "",
            "## 11. Automated QA results",
            "",
            f"- Status: **{_get(qa, 'status', default=_NOT_RUN)}**",
            f"- AUTO_ACCEPT: {_count(qa, 'auto_accepted')}",
            f"- AUTO_REJECT: {_count(qa, 'auto_rejected')}",
            f"- UNVERIFIED: {_count(qa, 'unverified')}",
            f"- Visual verification: "
            f"**{_get(qa, 'visual_verification', default=_NOT_RUN)}**",
            f"- Human QA: **{_get(qa, 'human_qa', default=_NOT_RUN)}**",
            f"- Basis: {_get(qa, 'basis', default='-')}",
            "",
            "Uncertainty is never converted to acceptance: an image automation "
            "cannot adjudicate is held `UNVERIFIED` and is **excluded** from the "
            "accepted set that is split and audited.",
            "",
            "## 12. Train / validation / test split",
            "",
            f"- Status: **{_get(split, 'status', default=_NOT_RUN)}**",
            f"- Splitter: {_get(split, 'splitter', default='-')}",
            f"- Ratios: {_get(split, 'ratios', default=_NOT_RUN)} (frozen)",
            f"- Seed: {_get(split, 'seed', default=_NOT_RUN)} (frozen)",
            f"- Counts: {_get(split, 'counts', default=_NOT_RUN)}",
            f"- Deterministic: {_get(split, 'deterministic', default=_NOT_RUN)}",
            f"- Disjoint: {_get(split, 'disjoint', default=_NOT_RUN)}",
            f"- Complete: {_get(split, 'complete', default=_NOT_RUN)}",
            "",
            "### Split gate — target class presence",
            "",
            f"- Present per split: {_get(split, 'class_present', default=_NOT_RUN)}",
            f"- Target-class boxes per split: "
            f"{_get(split, 'class_box_counts', default=_NOT_RUN)}",
            f"- Minimum per class: {_get(split, 'minimum_per_class', default='-')}",
            f"- Detail: {_get(split, 'detail', default='-')}",
            "",
            "## 13. Coverage and readiness",
            "",
            f"- Scope: **{_get(readiness, 'scope', default='ROUTER_WAVE_VALIDATION')}**",
            f"- Explicitly *not*: {_get(readiness, 'not', default='-')}",
            f"- Readiness stage status: **{_stage_status(result, 'readiness')}**",
            f"- Audit overall: "
            f"**{_get(readiness, 'report', 'overall', default=_get(readiness, 'status', default=_NOT_RUN))}**",
            f"- Gate states: "
            f"{_get(readiness, 'report', 'gate_states', default=_NOT_RUN)}",
            "",
            f"{_get(readiness, 'note', default='')}",
            "",
            "## 14. Exact blockers",
            "",
        ]
    )
    lines.extend(_bullet_list(list(result.blockers), empty="none"))

    lines.extend(
        [
            "",
            "## 15. Protected-state verification (measured)",
            "",
            "P4.3.5 (`candidate/p4_3_5_dataset_v1_candidate`) and P4.3.6 "
            "(`staging/p4_3_6_expansion_v1`) are opened **read-only** and "
            "fingerprinted before and after the run.",
            "",
            f"- All protected trees unchanged: "
            f"**{_get(protected, 'all_unchanged', default=_NOT_RUN)}**",
            "",
            "| Tree | Exists | Files | Images | Labels | Hash before | Hash after | Verdict |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    protected_rows = _protected_rows(protected)
    lines.extend(
        protected_rows or [f"| - | - | - | - | - | - | - | {_NOT_RUN} |"]
    )

    lines.extend(
        [
            "",
            "## 16. Frozen configuration actually observed",
            "",
            "| Value | Observed |",
            "| --- | --- |",
            f"| taxonomy version | {frozen_map.get('taxonomy_version', _NOT_RUN)} |",
            f"| taxonomy classes | {frozen_map.get('num_classes', _NOT_RUN)} |",
            f"| `{result.config.target_class}` class id | {observed_class_id} |",
            f"| split ratios | {frozen_map.get('split_ratios', _NOT_RUN)} |",
            f"| split seed | {frozen_map.get('split_seed', _NOT_RUN)} |",
            f"| duplicate Hamming threshold | "
            f"{frozen_map.get('duplicate_hamming_threshold', _NOT_RUN)} |",
            "",
            "None of these were written by this pipeline; they are read from the "
            "frozen taxonomy and settings and asserted before any data is touched.",
            "",
            "## 17. Stage ledger",
            "",
            "| # | Stage | Status | Summary |",
            "| --- | --- | --- | --- |",
        ]
    )
    for index, stage in enumerate(result.stages, start=1):
        lines.append(f"| {index} | {stage.name} | {stage.status} | {stage.summary} |")

    trees = _get(protected, "trees", default=[])
    tree_verdicts: dict[str, str] = {}
    if isinstance(trees, list):
        for tree in trees:
            if isinstance(tree, dict):
                tree_verdicts[str(tree.get("label", ""))] = (
                    "no" if tree.get("unchanged") else "YES - INVESTIGATE"
                )
    frozen_unchanged = "yes" if _stage_status(result, "preflight") == "OK" else _NOT_RUN

    lines.extend(
        [
            "",
            "## 18. Git status",
            "",
            "```",
            (git_status.rstrip() or "(not captured)"),
            "```",
            "",
            "- Committed: **no** (this pipeline never commits)",
            "- Released: **no** (this pipeline never releases)",
            f"- P4.3.5 modified: **{tree_verdicts.get('p4_3_5_candidate', _NOT_RUN)}** "
            "(measured by content-hash comparison)",
            f"- P4.3.6 modified: **{tree_verdicts.get('p4_3_6_expansion', _NOT_RUN)}** "
            "(measured by content-hash comparison)",
            f"- Taxonomy / split ratios / split seed / duplicate threshold observed "
            f"to match the frozen contract: **{frozen_unchanged}** "
            "(asserted by preflight; never written by this pipeline)",
            "",
        ]
    )
    return "\n".join(lines)
