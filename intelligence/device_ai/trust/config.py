"""Configuration for the trust & provenance engine (milestone M2.5).

Mirrors the circular, integrity and decision-knowledge engines' configs: a
small, frozen, slotted value object holding the trust-catalogue locator and the
handful of projection knobs the engine folds in. The catalogue locator and the
low-trust floor are env-driven (via :meth:`TrustConfig.from_settings`);
everything that actually shapes a *trust verdict* — how the four sub-axes are
weighted, and the score thresholds that map onto each trust level — lives in the
external trust catalogue, not here, so the config stays a thin locator plus the
axis-projection knobs the engine needs to turn upstream reports into ``[0, 1]``
sub-axis values.

Keeping the engine's operational knobs in one immutable object (rather than
scattered literals) is what makes the trust verdict reproducible and easy to
reason about.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..configs.settings import Settings

#: Default trust-catalogue locator, relative to the ``device_ai`` package root.
DEFAULT_RULES_PATH = "trust/data/rules.yaml"


@dataclass(frozen=True, slots=True)
class TrustConfig:
    """Tunable configuration for the trust & provenance engine.

    Attributes:
        rules_path: Locator of the external trust catalogue, resolved relative
            to the ``device_ai`` package root when not absolute.
        min_trust_score: Aggregated trust score at or below which the engine
            emits an operator-facing low-trust warning on the report. It never
            changes the trust level (the catalogue thresholds do that); it only
            flags a genuinely weak verdict for attention.
        identity_field_count: Number of strong identity fields (model, serial,
            IMEI, MAC) the engine normalizes presence against when projecting
            the ``identity_confidence`` axis onto ``[0, 1]``. A passport with
            all of them present scores full identity completeness.
        integrity_warning_penalty: Per-warning penalty subtracted from the
            integrity axis when the integrity report carries soft cautions (a
            valid-with-warnings passport is slightly less trustworthy than a
            clean one). Clamped so the axis never falls below ``0``.
    """

    # --- Trust catalogue locator -----------------------------------------
    rules_path: str = DEFAULT_RULES_PATH

    # --- Trust reporting --------------------------------------------------
    min_trust_score: float = 0.4

    # --- Identity-confidence projection -----------------------------------
    identity_field_count: int = 4

    # --- Integrity-confidence projection ----------------------------------
    integrity_warning_penalty: float = 0.1

    def resolved_rules_path(self, *, package_root: Path) -> Path:
        """Return the absolute trust-catalogue path.

        Relative :attr:`rules_path` values are resolved against the given
        ``package_root`` (the ``device_ai`` package directory), so the packaged
        catalogue is found regardless of the process working directory.

        Args:
            package_root: The ``device_ai`` package directory.

        Returns:
            The absolute path to the trust-catalogue file.
        """
        candidate = Path(self.rules_path)
        if candidate.is_absolute():
            return candidate
        return package_root / candidate

    @classmethod
    def from_settings(cls, settings: Settings) -> TrustConfig:
        """Build a config from application settings.

        Maps the two env-driven knobs (catalogue locator and low-trust floor)
        onto the config; every other field keeps its default (still overridable
        directly in code). Keeping the mapping explicit means adding an env knob
        is a one-line, reviewable change.

        Args:
            settings: The application :class:`~device_ai.configs.settings.Settings`.

        Returns:
            A :class:`TrustConfig` reflecting the env settings.
        """
        return cls(
            rules_path=settings.trust_rules_path,
            min_trust_score=settings.trust_min_score,
        )
