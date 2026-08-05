"""Configuration for the device passport validation & integrity engine (M2.4).

Mirrors the passport, circular and decision-knowledge engines' configs: a small,
frozen, slotted value object holding the rule-set locator and the one operational
knob the engine folds in (the hash algorithm). The locator and the algorithm are
env-driven (via :meth:`IntegrityConfig.from_settings`); everything that actually
shapes *which sections a passport must satisfy and their field/range contract*
lives in the external rule-set, not here, so the config stays a thin locator plus
the hashing knob.

Keeping the engine's operational knobs in one immutable object (rather than
scattered literals) is what keeps the produced integrity report reproducible and
easy to reason about.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..configs.settings import Settings

#: Default validation rule-set locator, relative to the ``device_ai`` root.
DEFAULT_RULES_PATH = "integrity/data/rules.yaml"

#: Default digest algorithm the canonical integrity hash is computed with.
DEFAULT_HASH_ALGORITHM = "sha256"


@dataclass(frozen=True, slots=True)
class IntegrityConfig:
    """Tunable configuration for the passport validation & integrity engine.

    Attributes:
        rules_path: Locator of the external validation rule-set, resolved
            relative to the ``device_ai`` package root when not absolute.
        hash_algorithm: The digest algorithm the canonical integrity hash is
            computed with (any name :func:`hashlib.new` accepts); ``sha256`` by
            default.
    """

    # --- Rule-set locator -------------------------------------------------
    rules_path: str = DEFAULT_RULES_PATH

    # --- Integrity hashing ------------------------------------------------
    hash_algorithm: str = DEFAULT_HASH_ALGORITHM

    def resolved_rules_path(self, *, package_root: Path) -> Path:
        """Return the absolute rule-set path.

        Relative :attr:`rules_path` values are resolved against the given
        ``package_root`` (the ``device_ai`` package directory), so the packaged
        rule-set is found regardless of the process working directory.

        Args:
            package_root: The ``device_ai`` package directory.

        Returns:
            The absolute path to the rule-set file.
        """
        candidate = Path(self.rules_path)
        if candidate.is_absolute():
            return candidate
        return package_root / candidate

    @classmethod
    def from_settings(cls, settings: Settings) -> IntegrityConfig:
        """Build a config from application settings.

        Maps the two env-driven knobs (rule-set locator and hash algorithm) onto
        the config. Keeping the mapping explicit means adding an env knob is a
        one-line, reviewable change.

        Args:
            settings: The application :class:`~device_ai.configs.settings.Settings`.

        Returns:
            An :class:`IntegrityConfig` reflecting the env settings.
        """
        return cls(
            rules_path=settings.integrity_rules_path,
            hash_algorithm=settings.integrity_hash_algorithm,
        )
