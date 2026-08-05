"""Configuration for the circular decision engine (milestone M2.2).

Mirrors the decision-knowledge engine's config: a small, frozen, slotted value
object holding the rule-catalogue locator and the handful of tunable knobs the
engine folds in. The catalogue locator is env-driven (via
:meth:`CircularConfig.from_settings`); everything that actually shapes a
*recommendation* — which evidence triggers which action, and the precedence
between rules — lives in the external rule catalogue, not here, so the config
stays a thin locator plus the identity/confidence-projection knobs the engine
needs to turn upstream reports into ``[0, 1]`` signals.

Keeping the engine's operational knobs in one immutable object (rather than
scattered literals) is what makes the circular decision reproducible and easy to
reason about.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..configs.settings import Settings

#: Default rule-catalogue locator, relative to the ``device_ai`` package root.
DEFAULT_RULES_PATH = "circular/data/rules.yaml"


@dataclass(frozen=True, slots=True)
class CircularConfig:
    """Tunable configuration for the circular decision engine.

    Attributes:
        rules_path: Locator of the external rule catalogue, resolved relative to
            the ``device_ai`` package root when not absolute.
        min_confidence: Aggregated confidence at or below which the engine emits
            an operator-facing low-confidence warning on the report. Kept small
            by default so it only flags genuinely weak recommendations; it never
            changes the recommended action (rules do that).
        identity_field_count: Number of identity fields (model, serial, IMEI,
            MAC) the engine normalizes presence against when projecting the
            ``identity_completeness`` signal onto ``[0, 1]``. A device with all
            of them present scores ``1.0``.
    """

    # --- Rule catalogue locator ------------------------------------------
    rules_path: str = DEFAULT_RULES_PATH

    # --- Confidence reporting --------------------------------------------
    min_confidence: float = 0.35

    # --- Identity-completeness projection --------------------------------
    identity_field_count: int = 4

    def resolved_rules_path(self, *, package_root: Path) -> Path:
        """Return the absolute rule-catalogue path.

        Relative :attr:`rules_path` values are resolved against the given
        ``package_root`` (the ``device_ai`` package directory), so the packaged
        catalogue is found regardless of the process working directory.

        Args:
            package_root: The ``device_ai`` package directory.

        Returns:
            The absolute path to the rule-catalogue file.
        """
        candidate = Path(self.rules_path)
        if candidate.is_absolute():
            return candidate
        return package_root / candidate

    @classmethod
    def from_settings(cls, settings: Settings) -> CircularConfig:
        """Build a config from application settings.

        Maps the two operationally-tunable, env-driven knobs onto the config;
        every other field keeps its default (still overridable directly in
        code). Keeping the mapping explicit means adding an env knob is a
        one-line, reviewable change.

        Args:
            settings: The application :class:`~device_ai.configs.settings.Settings`.

        Returns:
            A :class:`CircularConfig` reflecting the env settings.
        """
        return cls(
            rules_path=settings.circular_rules_path,
            min_confidence=settings.circular_min_confidence,
        )
