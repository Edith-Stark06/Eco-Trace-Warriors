"""Configuration for the decision knowledge engine (milestone M2.1).

Mirrors the environmental engine's config: a small, frozen, slotted value object
holding the knowledge-catalogue locator and the one tunable operational knob the
inference engine folds in. Both fields are env-driven (via
:meth:`DecisionConfig.from_settings`); everything that actually shapes a score —
the per-dimension signal weights and the normalization constants — lives in the
external knowledge catalogue, not here, so the config stays a thin locator plus
filter.

Keeping the engine's operational knobs in one immutable object (rather than
scattered literals) is what makes the decision evidence reproducible and easy to
reason about.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..configs.settings import Settings

#: Default knowledge-catalogue locator, relative to the ``device_ai`` package root.
DEFAULT_KNOWLEDGE_PATH = "decision/data/knowledge.yaml"


@dataclass(frozen=True, slots=True)
class DecisionConfig:
    """Tunable configuration for the decision knowledge engine.

    Attributes:
        knowledge_path: Locator of the external knowledge catalogue, resolved
            relative to the ``device_ai`` package root when not absolute.
        min_confidence: Confidence at or below which an upstream confidence source
            is treated as carrying no usable signal — its weight is dropped from
            the overall-confidence blend so a near-zero upstream confidence does
            not silently anchor the result. Kept small by default so it only
            excludes genuinely absent evidence.
    """

    # --- Knowledge catalogue locator -------------------------------------
    knowledge_path: str = DEFAULT_KNOWLEDGE_PATH

    # --- Confidence filtering --------------------------------------------
    min_confidence: float = 0.05

    def resolved_knowledge_path(self, *, package_root: Path) -> Path:
        """Return the absolute knowledge-catalogue path.

        Relative :attr:`knowledge_path` values are resolved against the given
        ``package_root`` (the ``device_ai`` package directory), so the packaged
        catalogue is found regardless of the process working directory.

        Args:
            package_root: The ``device_ai`` package directory.

        Returns:
            The absolute path to the knowledge-catalogue file.
        """
        candidate = Path(self.knowledge_path)
        if candidate.is_absolute():
            return candidate
        return package_root / candidate

    @classmethod
    def from_settings(cls, settings: Settings) -> DecisionConfig:
        """Build a config from application settings.

        Maps the two operationally-tunable, env-driven knobs onto the config.
        Keeping the mapping explicit means adding an env knob is a one-line,
        reviewable change.

        Args:
            settings: The application :class:`~device_ai.configs.settings.Settings`.

        Returns:
            A :class:`DecisionConfig` reflecting the env settings.
        """
        return cls(
            knowledge_path=settings.decision_knowledge_path,
            min_confidence=settings.decision_min_confidence,
        )
