"""Command-line entry points for the training platform (milestone M1.3).

Three thin CLIs drive the platform, each delegating to a ``*_main`` function
here so the argument parsing and orchestration are unit-testable without a
subprocess:

* ``python -m device_ai.train`` — compose and validate a
  :class:`~device_ai.training.config.RunConfig`, resolve artifact paths, record
  the Git commit and print the **run plan**. By default it does **not** train:
  no concrete trainer ships in M1.3, so a dry run is the honest default.
  ``--trainer <name>`` resolves a trainer from the
  :class:`~device_ai.training.core.registry.TrainerRegistry`; ``--run``
  attempts a real ``fit()`` (only possible once a trainer is registered).
* ``python -m device_ai.evaluate`` — render a registered model's recorded
  metrics into a JSON + HTML evaluation report (with the benchmark placeholder).
* ``python -m device_ai.export`` — attempt to export a registered model to the
  configured formats, honestly reporting ``skipped`` when the backend
  (torch/onnx) is absent.

Every collaborator flows from :class:`~device_ai.configs.settings.Settings` via
dependency injection; ``settings`` is an optional parameter on each ``*_main``
so tests can inject a temporary artifact root.
"""

from __future__ import annotations

import argparse
import inspect
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from ..configs.settings import Settings, get_settings
from ..exceptions import ModelNotFoundError, TrainerNotFoundError
from .config import RunConfig, hydra_available, load_config
from .core.evaluator import Evaluator, build_evaluation_document
from .core.exporter import ExportPlan, export_model
from .core.registry import TrainerRegistry, default_registry
from .registry.artifact_manager import ArtifactManager
from .registry.model_registry import ModelRegistry
from .utils.git_utils import git_commit_hash


def default_config_path() -> Path:
    """Return the path of the packaged ``configs/default.yaml``.

    Returns:
        The absolute path to the default composed configuration shipped with
        the training package.
    """
    return Path(__file__).resolve().parent / "configs" / "default.yaml"


def _resolve_settings(settings: Settings | None) -> Settings:
    """Return the injected settings or the process-wide singleton."""
    return settings if settings is not None else get_settings()


def _collect_overrides(args: argparse.Namespace) -> dict[str, Any]:
    """Build a config-override mapping from parsed CLI flags.

    Only flags the user actually supplied (non-``None``) become overrides, so
    unset flags never clobber file/defaults.

    Args:
        args: The parsed argument namespace.

    Returns:
        A nested overrides mapping suitable for :func:`load_config`.
    """
    training: dict[str, Any] = {}
    if getattr(args, "epochs", None) is not None:
        training["epochs"] = args.epochs
    if getattr(args, "batch_size", None) is not None:
        training["batch_size"] = args.batch_size
    if getattr(args, "device", None) is not None:
        training["device"] = args.device
    if getattr(args, "model_version", None) is not None:
        training["model_version"] = args.model_version

    overrides: dict[str, Any] = {}
    if training:
        overrides["training"] = training
    if getattr(args, "model_name", None) is not None:
        overrides["model_name"] = args.model_name
    if getattr(args, "trainer", None) is not None:
        overrides["trainer"] = args.trainer
    return overrides


# ---------------------------------------------------------------------------
# train
# ---------------------------------------------------------------------------


def build_train_parser() -> argparse.ArgumentParser:
    """Return the argument parser for the ``train`` CLI."""
    parser = argparse.ArgumentParser(
        prog="device_ai.train",
        description="Compose a training run and print its plan (dry run by default).",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to a YAML run config (defaults to the packaged default).",
    )
    parser.add_argument("--trainer", default=None, help="Trainer registry key.")
    parser.add_argument("--model-name", default=None, help="Override model name.")
    parser.add_argument(
        "--model-version", default=None, help="Override artifact version."
    )
    parser.add_argument("--epochs", type=int, default=None, help="Override epochs.")
    parser.add_argument(
        "--batch-size", type=int, default=None, help="Override batch size."
    )
    parser.add_argument("--device", default=None, help="Override device selector.")
    parser.add_argument(
        "--data-config",
        type=Path,
        default=None,
        help="Path to a YOLO data.yaml (required to actually train the detector).",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Attempt a real fit() (requires a registered trainer).",
    )
    return parser


def _load_builtin_trainers() -> None:
    """Import the built-in trainer packages so they self-register.

    Concrete trainers register themselves on
    :data:`~device_ai.training.core.registry.default_registry` at import time
    (via the ``@default_registry.register(...)`` decorator). Importing them here
    — lazily, right before a trainer key is resolved — keeps ``cli`` free of a
    hard import dependency while guaranteeing keys like ``"yolo"`` are known.
    """
    try:
        from . import detector  # noqa: F401  (import side-effect: registration)
    except ImportError as exc:  # pragma: no cover - defensive; detector is present
        logger.debug("Detector trainer package unavailable: {}", exc)


def _instantiate_trainer(
    trainer_cls: type,
    config: RunConfig,
    settings: Settings,
    args: argparse.Namespace,
) -> Any:
    """Construct a trainer, passing ``data_config`` only when it is supported.

    Different trainers accept different optional keyword arguments (e.g. the
    detector's ``data_config``). The constructor signature is inspected so a
    supplied ``--data-config`` reaches trainers that accept it without breaking
    trainers that do not.

    Args:
        trainer_cls: The resolved trainer class.
        config: The validated run configuration.
        settings: The active application settings.
        args: The parsed CLI namespace (source of optional ``data_config``).

    Returns:
        An instantiated trainer.
    """
    kwargs: dict[str, Any] = {}
    parameters = inspect.signature(trainer_cls).parameters
    data_config = getattr(args, "data_config", None)
    if data_config is not None and "data_config" in parameters:
        kwargs["data_config"] = data_config
    return trainer_cls(config, settings, **kwargs)


def _print_run_plan(config: RunConfig, artifacts: ArtifactManager, commit: str) -> None:
    """Print a human-readable summary of a resolved run plan."""
    plan = {
        "model_name": config.model_name,
        "model_version": config.training.model_version,
        "trainer": config.trainer,
        "experiment_name": config.experiment_name,
        "epochs": config.training.epochs,
        "batch_size": config.training.batch_size,
        "device": config.training.device,
        "dataset_version": config.training.dataset_version,
        "optimizer": config.optimizer.optimizer,
        "learning_rate": config.optimizer.learning_rate,
        "git_commit": commit,
        "hydra_available": hydra_available(),
        "checkpoints_dir": artifacts.checkpoints.as_posix(),
        "reports_dir": artifacts.reports.as_posix(),
    }
    logger.info("Training run plan (dry run — no model is trained in M1.3):")
    print(json.dumps(plan, indent=2, sort_keys=True))


def train_main(
    argv: list[str] | None = None,
    *,
    settings: Settings | None = None,
    registry: TrainerRegistry | None = None,
) -> int:
    """Entry point for ``python -m device_ai.train``.

    Args:
        argv: Argument vector (defaults to ``sys.argv[1:]``).
        settings: Optional injected settings (defaults to the singleton).
        registry: Optional trainer registry (defaults to the shared one).

    Returns:
        A process exit code (``0`` on success, non-zero on error).
    """
    args = build_train_parser().parse_args(argv)
    active = _resolve_settings(settings)
    trainer_registry = registry if registry is not None else default_registry

    config_path = args.config or default_config_path()
    config = load_config(config_path, overrides=_collect_overrides(args))
    artifacts = ArtifactManager.from_settings(active).ensure()
    commit = git_commit_hash()

    if not args.run:
        _print_run_plan(config, artifacts, commit)
        return 0

    _load_builtin_trainers()
    try:
        trainer_cls = trainer_registry.get(config.trainer)
    except TrainerNotFoundError as exc:
        logger.error(str(exc))
        logger.error(
            "Unknown trainer '{}'; register one or run without --run to see "
            "the plan.",
            config.trainer,
        )
        return 1

    trainer = _instantiate_trainer(trainer_cls, config, active, args)
    history = trainer.fit()
    logger.info(
        "Training complete: run={} checkpoint={}",
        history.run_id,
        history.checkpoint_path,
    )
    return 0


# ---------------------------------------------------------------------------
# evaluate
# ---------------------------------------------------------------------------


def build_evaluate_parser() -> argparse.ArgumentParser:
    """Return the argument parser for the ``evaluate`` CLI."""
    parser = argparse.ArgumentParser(
        prog="device_ai.evaluate",
        description="Render a registered model's metrics into a JSON+HTML report.",
    )
    parser.add_argument("--model-name", required=True, help="Registered model name.")
    parser.add_argument(
        "--model-version",
        default="latest",
        help="Model version, or 'latest' (default).",
    )
    return parser


def evaluate_main(
    argv: list[str] | None = None,
    *,
    settings: Settings | None = None,
    clock: Any = None,
) -> int:
    """Entry point for ``python -m device_ai.evaluate``.

    Args:
        argv: Argument vector (defaults to ``sys.argv[1:]``).
        settings: Optional injected settings.
        clock: Optional zero-argument time factory (injected for tests).

    Returns:
        A process exit code (``0`` on success, non-zero when the model is
        unknown).
    """
    args = build_evaluate_parser().parse_args(argv)
    active = _resolve_settings(settings)
    now = (clock or datetime.now)()

    registry = ModelRegistry.from_settings(active)
    artifacts = ArtifactManager.from_settings(active).ensure()
    try:
        record = registry.resolve(args.model_name, args.model_version)
    except ModelNotFoundError as exc:
        logger.error(str(exc))
        return 1

    document = build_evaluation_document(
        model_name=record.name,
        model_version=record.version,
        metrics=record.metrics,
        confusion=None,
        class_names=None,
        generated_at=now,
        dataset_version=record.dataset_version,
    )
    json_path = artifacts.report_path(record.name, record.version, ".json")
    html_path = artifacts.report_path(record.name, record.version, ".html")
    json_path.write_text(
        json.dumps(document, indent=2, sort_keys=True), encoding="utf-8"
    )
    html_path.write_text(Evaluator().to_html(document), encoding="utf-8")
    logger.info("Wrote evaluation report: {} and {}", json_path, html_path)
    return 0


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------


def build_export_parser() -> argparse.ArgumentParser:
    """Return the argument parser for the ``export`` CLI."""
    parser = argparse.ArgumentParser(
        prog="device_ai.export",
        description="Export a registered model to deployment formats.",
    )
    parser.add_argument("--model-name", required=True, help="Registered model name.")
    parser.add_argument(
        "--model-version",
        default="latest",
        help="Model version, or 'latest' (default).",
    )
    parser.add_argument(
        "--formats",
        default="pytorch,torchscript,onnx",
        help="Comma-separated export formats to attempt.",
    )
    return parser


def export_main(
    argv: list[str] | None = None,
    *,
    settings: Settings | None = None,
) -> int:
    """Entry point for ``python -m device_ai.export``.

    In the base environment (no torch/onnx) every format is reported as
    ``skipped`` rather than silently producing nothing.

    Args:
        argv: Argument vector (defaults to ``sys.argv[1:]``).
        settings: Optional injected settings.

    Returns:
        A process exit code (``0`` on success, non-zero when the model is
        unknown).
    """
    args = build_export_parser().parse_args(argv)
    active = _resolve_settings(settings)

    registry = ModelRegistry.from_settings(active)
    artifacts = ArtifactManager.from_settings(active).ensure()
    try:
        record = registry.resolve(args.model_name, args.model_version)
    except ModelNotFoundError as exc:
        logger.error(str(exc))
        return 1

    formats = tuple(fmt.strip() for fmt in args.formats.split(",") if fmt.strip())
    plan = ExportPlan(model_name=record.name, version=record.version, formats=formats)
    # No model object is loaded (weights are not deserialised in M1.3); the
    # exporters honestly skip when their backend is unavailable.
    records = export_model(model=None, plan=plan, exports_dir=artifacts.exports)
    for outcome in records:
        logger.info(
            "Export {}: {} {}",
            outcome.export_format,
            outcome.status,
            outcome.location or outcome.message,
        )
    return 0
