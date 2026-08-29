"""``python -m device_ai.acquisition`` — the router-acquisition CLI.

Follows the repository's existing CLI conventions: ``argparse``, a testable
``*_main(argv)`` function, and a thin ``__main__`` shim (mirroring
``python -m device_ai.train`` / ``.evaluate`` / ``.export``).

Sub-commands::

    python -m device_ai.acquisition run --mode auto
    python -m device_ai.acquisition run --mode offline --source <archive> \\
        --license CC-BY-4.0
    python -m device_ai.acquisition run --mode offline --source <dir> --dry-run
    python -m device_ai.acquisition discover [--source <archive>]
    python -m device_ai.acquisition verify  [--source <archive>]
    python -m device_ai.acquisition report

``--mode``/``--source``/``--dry-run`` are also accepted directly on the top-level
parser, so the spec's flag-style invocations work as well::

    python -m device_ai.acquisition --mode auto
    python -m device_ai.acquisition --mode offline --source <archive>
    python -m device_ai.acquisition --discover
    python -m device_ai.acquisition --verify
    python -m device_ai.acquisition --run
    python -m device_ai.acquisition --report

**Readiness auditor resolution.** The repository's authoritative freeze gate is
``scripts/audit_dataset_readiness.py`` (the script layer). The domain pipeline
never imports it; this composition root resolves it by file path and injects it,
so the audit that runs is the real one rather than a re-implementation. If it
cannot be resolved the readiness stage reports ``UNAVAILABLE`` with the exact
reason — a verdict is never simulated.

Exit codes:
    0: the requested action completed (including an honest ``BLOCKED`` outcome
       that was correctly reported).
    1: the run produced a hard failure (preflight mismatch, split defect,
       protected-tree change, or a readiness/audit error).
    2: usage error.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from .config import AcquisitionConfig, TargetClass, repo_root
from .gates import summarize_verdicts, verify_source
from .network import check_connectivity
from .pipeline import (
    FAILED,
    MODE_AUTO,
    MODE_OFFLINE,
    MODES,
    STATUS_PREFLIGHT_FAILED,
    STATUS_WAVE_INCOMPLETE,
    STATUS_WAVE_VALIDATED,
    LocalSourceSpec,
    RunResult,
    build_adapters,
    read_source_labels,
    run_pipeline,
)
from .pipeline import discover as discover_sources
from .report import render_json, render_markdown

_EXIT_OK = 0
_EXIT_FAILED = 1
_EXIT_USAGE = 2

# Statuses that mean "the tooling worked and told the truth", even when no data
# could be acquired. Only hard defects exit non-zero.
_HARD_FAILURE_STATUSES = frozenset({STATUS_PREFLIGHT_FAILED})


def resolve_readiness_audit() -> tuple[Callable[..., dict] | None, str]:
    """Locate the repository's authoritative readiness audit.

    The audit lives in the script layer (``scripts/audit_dataset_readiness.py``)
    and composes the frozen gates. It is loaded by path — never re-implemented —
    so the verdict this pipeline reports is the repository's own.

    Returns:
        ``(callable, detail)``. The callable is ``None`` when resolution failed,
        with ``detail`` carrying the exact reason.
    """
    scripts_dir = repo_root() / "scripts"
    module_path = scripts_dir / "audit_dataset_readiness.py"
    if not module_path.is_file():
        return None, f"readiness audit not found at {module_path.as_posix()}"

    # The audit script imports its siblings by bare name (the repo's script-layer
    # convention), so the scripts directory must be importable.
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    try:
        from importlib import util

        spec = util.spec_from_file_location("audit_dataset_readiness", module_path)
        if spec is None or spec.loader is None:
            return None, f"could not build an import spec for {module_path.as_posix()}"
        module = util.module_from_spec(spec)
        spec.loader.exec_module(module)
        audit = getattr(module, "audit", None)
    except Exception as exc:  # noqa: BLE001 - report, never fabricate a verdict
        return None, f"readiness audit failed to import: {type(exc).__name__}: {exc}"
    if audit is None or not callable(audit):
        return None, "audit_dataset_readiness.audit is missing or not callable"
    return audit, f"loaded from {module_path.as_posix()}"


def capture_git_status(*, root: Path | None = None) -> str:
    """Return ``git status --short`` output, or an explanatory placeholder.

    Args:
        root: Repository root (defaults to the detected root).

    Returns:
        The captured output verbatim, or a short note when git is unavailable.
    """
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["git", "status", "--short"],
            cwd=str(root or repo_root()),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"(git status unavailable: {type(exc).__name__}: {exc})"
    if completed.returncode != 0:
        return f"(git status exited {completed.returncode}: {completed.stderr.strip()})"
    return completed.stdout


def _load_coordinates(path: Path | None) -> dict[str, list[dict]]:
    """Load explicitly configured remote coordinates from a JSON file.

    Args:
        path: JSON file mapping adapter name -> list of coordinate mappings.

    Returns:
        The parsed mapping, or an empty mapping when no file was supplied.

    Raises:
        SystemExit: When the file is unreadable or malformed (a usage error —
            never silently treated as "no coordinates").
    """
    if path is None:
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"error: could not read --coordinates {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(
            f"error: --coordinates {path} must be a JSON object keyed by adapter name"
        )
    result: dict[str, list[dict]] = {}
    for key, value in data.items():
        if not isinstance(value, list):
            raise SystemExit(
                f"error: --coordinates entry '{key}' must be a list of objects"
            )
        result[str(key)] = [item for item in value if isinstance(item, dict)]
    return result


def _local_spec(args: argparse.Namespace) -> LocalSourceSpec | None:
    """Build the local-source spec from parsed arguments, if one was supplied."""
    if args.source is None:
        return None
    return LocalSourceSpec(
        path=Path(args.source),
        license_raw=args.license or "",
        license_url=args.license_url or "",
        name=args.source_name or "",
        publisher=args.publisher or "",
        url=args.source_url or "",
    )


def _resolve_target(args: argparse.Namespace) -> TargetClass | None:
    """Resolve ``--target-class`` (name or id) against the frozen taxonomy.

    Returns ``None`` when the flag was not supplied (the router default applies).

    Raises:
        ValueError: When the supplied class name/id does not resolve.
    """
    token = getattr(args, "target_class", None)
    if token is None:
        return None
    return TargetClass.parse(str(token))


def _config(args: argparse.Namespace) -> AcquisitionConfig:
    """Build the run layout, honouring the target class and path overrides."""
    root = Path(args.repo_root) if args.repo_root else None
    target = _resolve_target(args)
    if target is None:
        config = AcquisitionConfig.default(root=root)
    else:
        config = AcquisitionConfig.for_target(target, root=root)
    if args.report_out or args.json_out or args.staging_root:
        from dataclasses import replace

        config = replace(
            config,
            report_path=Path(args.report_out) if args.report_out else config.report_path,
            json_report_path=(
                Path(args.json_out) if args.json_out else config.json_report_path
            ),
            staging_root=(
                Path(args.staging_root) if args.staging_root else config.staging_root
            ),
        )
    return config


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    """Attach the arguments shared by every sub-command."""
    parser.add_argument(
        "--mode",
        choices=MODES,
        default=MODE_AUTO,
        help=(
            "auto (default): one connectivity probe decides; online: require "
            "egress; offline: never probe, ingest --source only."
        ),
    )
    parser.add_argument(
        "--target-class",
        default=None,
        help=(
            "Taxonomy class to acquire, by name (e.g. laptop) or id (e.g. 0). "
            "Defaults to 'router'. Validated against components.yaml; an unknown "
            "name or out-of-range id fails cleanly without acquiring anything."
        ),
    )
    parser.add_argument(
        "--source",
        default=None,
        help=(
            "Local dataset directory or archive (.zip/.tar/.tar.gz/.tgz) to "
            "ingest. Required for offline acquisition."
        ),
    )
    parser.add_argument(
        "--license",
        default=None,
        help=(
            "Explicit license string asserted for --source (e.g. CC-BY-4.0). "
            "Never inferred: without it the license gate reports UNVERIFIED and "
            "nothing is ingested."
        ),
    )
    parser.add_argument(
        "--license-url", default=None, help="Supporting license URL for --source."
    )
    parser.add_argument(
        "--source-name", default=None, help="Dataset name recorded in provenance."
    )
    parser.add_argument(
        "--publisher", default=None, help="Publisher/contributor recorded in provenance."
    )
    parser.add_argument(
        "--source-url", default=None, help="Origin URL recorded in provenance."
    )
    parser.add_argument(
        "--coordinates",
        type=Path,
        default=None,
        help=(
            "JSON file of explicitly configured remote source coordinates keyed "
            "by adapter name. Remote adapters discover nothing without it (they "
            "never crawl a public catalogue)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Validate the whole pipeline (dependencies, frozen components, paths, "
            "configuration, report rendering) without writing production or "
            "staging data."
        ),
    )
    parser.add_argument(
        "--repo-root", default=None, help="Repository root override (testing)."
    )
    parser.add_argument(
        "--staging-root", default=None, help="Staged batch root override (testing)."
    )
    parser.add_argument(
        "--report-out", default=None, help="Markdown report destination override."
    )
    parser.add_argument(
        "--json-out", default=None, help="JSON run-report destination override."
    )
    parser.add_argument(
        "--no-write-report",
        action="store_true",
        help="Render the report to stdout without writing it to disk.",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="python -m device_ai.acquisition",
        description=(
            "Automated, offline-capable single-class dataset acquisition for the "
            "EcoTrace device-detection taxonomy (P4.3.7, target class: router). "
            "Never fabricates data: with no verifiable source it reports BLOCKED."
        ),
    )
    # Flag-style action selectors (equivalent to the sub-commands).
    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--run", action="store_true", help="Run the full pipeline (same as `run`)."
    )
    action.add_argument(
        "--discover",
        action="store_true",
        help="Discover candidate sources only (same as `discover`).",
    )
    action.add_argument(
        "--verify",
        action="store_true",
        help="Discover and verify sources without acquiring (same as `verify`).",
    )
    action.add_argument(
        "--report",
        action="store_true",
        help="Re-render the report from the last JSON run report (same as `report`).",
    )
    _add_common_arguments(parser)

    subparsers = parser.add_subparsers(dest="command")
    for name, help_text in (
        ("run", "Run the full acquisition pipeline."),
        ("discover", "Discover candidate sources without downloading."),
        ("verify", "Discover and verify sources without acquiring."),
        ("report", "Re-render the Markdown report from the last JSON run report."),
    ):
        sub = subparsers.add_parser(name, help=help_text, description=help_text)
        _add_common_arguments(sub)
    return parser


def _resolve_command(args: argparse.Namespace) -> str:
    """Return the requested command, resolving flag-style selectors."""
    if args.command:
        return str(args.command)
    for flag in ("discover", "verify", "report", "run"):
        if getattr(args, flag, False):
            return flag
    return "run"


def _emit_reports(
    result: RunResult, args: argparse.Namespace, *, git_status: str
) -> None:
    """Write and/or print the Markdown + JSON reports."""
    markdown = render_markdown(result, git_status=git_status)
    payload = render_json(result, git_status=git_status)
    if not args.no_write_report and not result.dry_run:
        result.config.report_path.parent.mkdir(parents=True, exist_ok=True)
        result.config.report_path.write_text(markdown, encoding="utf-8")
        result.config.json_report_path.parent.mkdir(parents=True, exist_ok=True)
        result.config.json_report_path.write_text(payload, encoding="utf-8")
        print(f"report written: {result.config.report_path.as_posix()}")
        print(f"run report written: {result.config.json_report_path.as_posix()}")
    else:
        print(markdown)


def _exit_code(result: RunResult) -> int:
    """Map a run outcome to a process exit code."""
    if result.status in _HARD_FAILURE_STATUSES:
        return _EXIT_FAILED
    for name in ("protected_state", "readiness", "split"):
        stage = result.stage(name)
        if stage is not None and stage.status == FAILED:
            return _EXIT_FAILED
    return _EXIT_OK


def _discover_only(args: argparse.Namespace, *, verify: bool) -> int:
    """Run discovery (and optionally verification) without acquiring anything."""
    config = _config(args)
    connectivity = check_connectivity(offline=(args.mode == MODE_OFFLINE))
    adapters = build_adapters(
        local=_local_spec(args),
        work_dir=config.work_dir,
        env=os.environ,
        coordinates=_load_coordinates(args.coordinates),
    )
    config.work_dir.mkdir(parents=True, exist_ok=True)
    candidates, statuses = discover_sources(adapters, online=connectivity.online)

    payload: dict[str, object] = {
        "mode": args.mode,
        "network": connectivity.to_dict(),
        "adapters": statuses,
        "candidate_count": len(candidates),
        "candidates": [c.to_dict() for c in candidates],
    }
    if verify:
        verdicts = []
        for candidate in candidates:
            labels, _, error = read_source_labels(candidate)
            verdict = verify_source(candidate, labels=labels)
            if error:
                from dataclasses import replace

                verdict = replace(
                    verdict, reasons=(*verdict.reasons, f"format: {error}")
                )
            verdicts.append(verdict)
        payload["verification"] = summarize_verdicts(verdicts)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return _EXIT_OK


def _report_only(args: argparse.Namespace) -> int:
    """Re-render the Markdown report from a previously written JSON run report."""
    config = _config(args)
    if not config.json_report_path.is_file():
        print(
            f"error: no run report at {config.json_report_path.as_posix()}; "
            "run the pipeline first (nothing is fabricated)",
            file=sys.stderr,
        )
        return _EXIT_USAGE
    payload = json.loads(config.json_report_path.read_text(encoding="utf-8"))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return _EXIT_OK


def acquire_main(argv: list[str] | None = None) -> int:
    """Entry point for the acquisition CLI.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv[1:]``).

    Returns:
        A process exit code (see the module docstring).
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    command = _resolve_command(args)

    try:
        _resolve_target(args)
    except ValueError as exc:
        print(f"error: invalid --target-class: {exc}", file=sys.stderr)
        return _EXIT_USAGE

    if command == "discover":
        return _discover_only(args, verify=False)
    if command == "verify":
        return _discover_only(args, verify=True)
    if command == "report":
        return _report_only(args)

    if args.mode == MODE_OFFLINE and args.source is None:
        print(
            "error: --mode offline requires --source <archive|directory>; "
            "no local source means STATUS=BLOCKED_NO_SOURCE and nothing to run",
            file=sys.stderr,
        )
        return _EXIT_USAGE
    if args.source is not None and not Path(args.source).exists():
        print(f"error: --source does not exist: {args.source}", file=sys.stderr)
        return _EXIT_USAGE

    audit, audit_detail = resolve_readiness_audit()
    if audit is None:
        print(f"warning: readiness audit unavailable - {audit_detail}", file=sys.stderr)

    config = _config(args)
    result = run_pipeline(
        config=config,
        mode=args.mode,
        local_source=_local_spec(args),
        coordinates=_load_coordinates(args.coordinates),
        dry_run=args.dry_run,
        readiness_audit=audit,
    )
    git_status = capture_git_status(
        root=Path(args.repo_root) if args.repo_root else None
    )
    _emit_reports(result, args, git_status=git_status)

    print(f"status: {result.status}")
    for blocker in result.blockers:
        print(f"blocker: {blocker}")
    if result.status == STATUS_WAVE_VALIDATED:
        print(
            "note: ROUTER WAVE VALIDATION only - this is not a full-dataset "
            "release readiness verdict, and nothing was committed or released."
        )
    elif result.status == STATUS_WAVE_INCOMPLETE:
        print(
            "note: the wave ran end to end but the split gate did not pass; the "
            "seed and ratios were not changed and no minimum was invented."
        )
    return _exit_code(result)


def main() -> None:
    """Run the acquisition CLI and exit with its status code."""
    raise SystemExit(acquire_main(sys.argv[1:]))
