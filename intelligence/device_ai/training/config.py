"""Typed run configuration for the AI training platform (milestone M1.3).

Every training run is described by a single, validated :class:`RunConfig`
composed of an :class:`OptimizerConfig` and a :class:`TrainingConfig`. The
models are Pydantic v2 value objects — immutable, primitive-only and trivially
serialisable — so a run's exact configuration can be embedded verbatim in an
experiment record, a model-registry entry or an evaluation report.

Configuration is loaded from YAML via :func:`load_config`. The loader supports
a Hydra-compatible ``defaults`` list so ``configs/default.yaml`` can *compose*
``training.yaml`` and ``optimizer.yaml`` without any heavy dependency:
``PyYAML`` — the only new base requirement — is sufficient. When ``hydra-core``
is installed (see ``requirements-models.txt``) the same ``defaults`` syntax is
directly compatible with a full Hydra pipeline; :func:`hydra_available` reports
whether that optional backend is present.

Nothing here trains a model. These objects only *describe* a run.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..exceptions import ConfigError

# ``hydra-core`` is an optional, uninstalled model dependency. Its presence is
# detected once at import time; the light-weight PyYAML loader below mirrors
# Hydra's ``defaults`` composition semantics so runs work with or without it.
try:  # pragma: no cover - exercised only when the optional dep is installed
    import hydra  # noqa: F401

    _HYDRA_AVAILABLE = True
except ImportError:
    _HYDRA_AVAILABLE = False


def hydra_available() -> bool:
    """Return whether the optional ``hydra-core`` backend is importable.

    Returns:
        ``True`` when Hydra is installed, ``False`` in the base environment.
    """
    return _HYDRA_AVAILABLE


class OptimizerConfig(BaseModel):
    """Optimisation hyper-parameters for a training run.

    Attributes:
        optimizer: Optimiser identifier (e.g. ``"adamw"``, ``"sgd"``).
        learning_rate: Base learning rate; strictly positive.
        weight_decay: L2 weight-decay coefficient; non-negative.
        momentum: Momentum term for SGD-style optimisers; non-negative.
        scheduler: Learning-rate schedule (``"none"``/``"step"``/``"cosine"``).
        warmup_epochs: Epochs of linear warm-up before the schedule; ``0``
            disables warm-up.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    optimizer: str = Field(default="adamw", description="Optimiser identifier.")
    learning_rate: float = Field(
        default=1e-3, gt=0.0, description="Base learning rate (> 0)."
    )
    weight_decay: float = Field(
        default=0.0, ge=0.0, description="L2 weight-decay coefficient (>= 0)."
    )
    momentum: float = Field(
        default=0.9, ge=0.0, description="Momentum for SGD-style optimisers (>= 0)."
    )
    scheduler: str = Field(
        default="cosine", description="Learning-rate schedule identifier."
    )
    warmup_epochs: int = Field(
        default=0, ge=0, description="Linear warm-up epochs before the schedule."
    )


class TrainingConfig(BaseModel):
    """Core training-loop hyper-parameters for a run.

    Attributes:
        batch_size: Images per optimisation step; at least 1.
        epochs: Number of full passes over the training set; at least 1.
        device: Target device (``"auto"``/``"cpu"``/``"cuda"``); resolution of
            ``"auto"`` happens at run time, never here.
        mixed_precision: Whether automatic mixed precision is requested.
        workers: Data-loader worker processes; non-negative.
        seed: RNG seed for deterministic, reproducible runs.
        image_size: Square input resolution in pixels; at least 1.
        dataset_version: Dataset snapshot label to train against (``"latest"``
            resolves to the newest registered version at run time).
        model_version: Semantic version tag stamped onto produced artifacts.
        early_stopping_patience: Epochs without validation improvement before
            stopping; ``0`` disables early stopping.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", protected_namespaces=())

    batch_size: int = Field(default=16, ge=1, description="Images per step (>= 1).")
    epochs: int = Field(default=100, ge=1, description="Training epochs (>= 1).")
    device: str = Field(default="auto", description="Target device selector.")
    mixed_precision: bool = Field(
        default=False, description="Request automatic mixed precision."
    )
    workers: int = Field(default=4, ge=0, description="Data-loader workers (>= 0).")
    seed: int = Field(default=42, ge=0, description="Deterministic RNG seed.")
    image_size: int = Field(
        default=640, ge=1, description="Square input resolution in pixels."
    )
    dataset_version: str = Field(
        default="latest", description="Dataset snapshot label to train against."
    )
    model_version: str = Field(
        default="1.0.0", description="Semantic version stamped onto artifacts."
    )
    early_stopping_patience: int = Field(
        default=0,
        ge=0,
        description="Epochs without improvement before stopping (0 disables).",
    )


class RunConfig(BaseModel):
    """The complete, validated description of one training run.

    A :class:`RunConfig` is the single object threaded through the training
    lifecycle — the trainer, experiment tracker, model registry and evaluator
    all read from it — so a run is fully reproducible from its serialised form.

    Attributes:
        model_name: Logical model name (registry key, e.g. ``"device-detector"``).
        trainer: :class:`~device_ai.training.core.registry.TrainerRegistry`
            key selecting which trainer implementation runs.
        experiment_name: Grouping label for the experiment tracker.
        training: Core training-loop hyper-parameters.
        optimizer: Optimisation hyper-parameters.
        tags: Free-form string metadata attached to the run.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", protected_namespaces=())

    model_name: str = Field(
        default="device-detector", description="Logical model / registry name."
    )
    trainer: str = Field(default="mock", description="Trainer registry key.")
    experiment_name: str = Field(
        default="die-training", description="Experiment grouping label."
    )
    training: TrainingConfig = Field(
        default_factory=TrainingConfig, description="Training-loop hyper-parameters."
    )
    optimizer: OptimizerConfig = Field(
        default_factory=OptimizerConfig, description="Optimisation hyper-parameters."
    )
    tags: dict[str, str] = Field(
        default_factory=dict, description="Free-form run metadata."
    )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable, primitive-only view of the run config.

        Returns:
            A nested mapping suitable for embedding in run/registry records.
        """
        return self.model_dump(mode="json")


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` onto ``base`` (override wins).

    Nested mappings are merged key-by-key; every other value type is replaced
    wholesale. Neither input is mutated.

    Args:
        base: The lower-priority mapping.
        override: The higher-priority mapping.

    Returns:
        A new merged mapping.
    """
    merged = dict(base)
    for key, value in override.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _deep_merge(existing, value)
        else:
            merged[key] = value
    return merged


def _read_yaml(path: Path) -> dict[str, Any]:
    """Parse a YAML file into a mapping, raising :class:`ConfigError` on failure.

    Args:
        path: The YAML file to read.

    Returns:
        The parsed mapping (an empty file yields ``{}``).

    Raises:
        ConfigError: If the file is missing, unparseable, or not a mapping.
    """
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}", details={"path": str(path)})
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:  # malformed YAML
        raise ConfigError(
            f"Failed to parse YAML config '{path}': {exc}",
            details={"path": str(path)},
        ) from exc
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError(
            f"Config root must be a mapping, got {type(raw).__name__}: {path}",
            details={"path": str(path)},
        )
    return raw


def _compose(raw: dict[str, Any], *, base_dir: Path) -> dict[str, Any]:
    """Resolve a Hydra-compatible ``defaults`` list into a single mapping.

    Each entry ``name`` in the ``defaults`` list loads ``<base_dir>/<name>.yaml``
    and places its contents under the key ``name`` (mirroring Hydra config
    groups). Remaining top-level keys are then merged on top, so an explicit
    override in the composing file wins over a default group.

    Args:
        raw: The parsed top-level config mapping.
        base_dir: Directory used to resolve relative ``defaults`` entries.

    Returns:
        The composed mapping ready for :class:`RunConfig` validation.

    Raises:
        ConfigError: If ``defaults`` is malformed or references a missing file.
    """
    defaults = raw.get("defaults", [])
    if not isinstance(defaults, list):
        raise ConfigError(
            "The 'defaults' key must be a list of config-group names.",
            details={"got": type(defaults).__name__},
        )

    composed: dict[str, Any] = {}
    for name in defaults:
        if not isinstance(name, str):
            raise ConfigError(
                "Each 'defaults' entry must be a config-group name (string).",
                details={"got": repr(name)},
            )
        group = _read_yaml(base_dir / f"{name}.yaml")
        composed[name] = _deep_merge(composed.get(name, {}), group)

    rest = {key: value for key, value in raw.items() if key != "defaults"}
    return _deep_merge(composed, rest)


def load_config(
    path: str | Path,
    *,
    overrides: dict[str, Any] | None = None,
) -> RunConfig:
    """Load and validate a :class:`RunConfig` from a YAML file.

    The file may compose reusable groups via a Hydra-compatible ``defaults``
    list (see :func:`_compose`). An optional ``overrides`` mapping is deep-merged
    last, letting callers (e.g. the CLI) patch individual fields.

    Args:
        path: Path to the YAML config file.
        overrides: Optional mapping deep-merged on top of the file contents.

    Returns:
        A validated :class:`RunConfig`.

    Raises:
        ConfigError: If the file is missing/malformed or fails validation.
    """
    config_path = Path(path)
    raw = _read_yaml(config_path)
    merged = _compose(raw, base_dir=config_path.parent)
    if overrides:
        merged = _deep_merge(merged, overrides)
    try:
        return RunConfig.model_validate(merged)
    except ValidationError as exc:
        raise ConfigError(
            f"Invalid training configuration in '{config_path}': {exc}",
            details={"path": str(config_path)},
        ) from exc
