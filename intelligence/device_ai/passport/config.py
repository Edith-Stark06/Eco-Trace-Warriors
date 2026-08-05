"""Configuration for the device passport core (milestone M2.3).

Mirrors the circular and decision-knowledge engines' configs: a small, frozen,
slotted value object holding the schema locator and the one presentation knob the
builder folds in. The schema locator and the passport version are env-driven (via
:meth:`PassportConfig.from_settings`); everything that actually shapes the
passport's *structure* — which sections it must contain and their field/range
contract — lives in the external schema, not here, so the config stays a thin
locator plus version.

Keeping the builder's operational knobs in one immutable object (rather than
scattered literals) is what keeps the assembled passport reproducible and easy to
reason about.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..configs.settings import Settings

#: Default schema locator, relative to the ``device_ai`` package root.
DEFAULT_SCHEMA_PATH = "passport/data/schema.yaml"

#: Default passport version stamped onto every produced passport.
DEFAULT_PASSPORT_VERSION = "1.0.0"


@dataclass(frozen=True, slots=True)
class PassportConfig:
    """Tunable configuration for the device passport core.

    Attributes:
        schema_path: Locator of the external passport schema, resolved relative
            to the ``device_ai`` package root when not absolute.
        passport_version: Semantic version stamped onto every produced passport
            (its :attr:`~device_ai.passport.models.DevicePassport.passport_version`),
            bumped when the passport's structure changes.
        max_reasoning: Maximum number of composed reasoning entries kept on a
            passport. A presentation cap so the document stays bounded; the
            builder emits the most salient entries first and drops the overflow.
        max_warnings: Maximum number of composed warnings kept on a passport
            (same rationale as ``max_reasoning``).
    """

    # --- Schema locator ---------------------------------------------------
    schema_path: str = DEFAULT_SCHEMA_PATH

    # --- Passport identity ------------------------------------------------
    passport_version: str = DEFAULT_PASSPORT_VERSION

    # --- Presentation caps ------------------------------------------------
    max_reasoning: int = 32
    max_warnings: int = 32

    def resolved_schema_path(self, *, package_root: Path) -> Path:
        """Return the absolute schema path.

        Relative :attr:`schema_path` values are resolved against the given
        ``package_root`` (the ``device_ai`` package directory), so the packaged
        schema is found regardless of the process working directory.

        Args:
            package_root: The ``device_ai`` package directory.

        Returns:
            The absolute path to the schema file.
        """
        candidate = Path(self.schema_path)
        if candidate.is_absolute():
            return candidate
        return package_root / candidate

    @classmethod
    def from_settings(cls, settings: Settings) -> PassportConfig:
        """Build a config from application settings.

        Maps the two env-driven knobs (schema locator and passport version) onto
        the config; the presentation caps keep their defaults (still overridable
        directly in code). Keeping the mapping explicit means adding an env knob
        is a one-line, reviewable change.

        Args:
            settings: The application :class:`~device_ai.configs.settings.Settings`.

        Returns:
            A :class:`PassportConfig` reflecting the env settings.
        """
        return cls(
            schema_path=settings.passport_schema_path,
            passport_version=settings.passport_version,
        )
