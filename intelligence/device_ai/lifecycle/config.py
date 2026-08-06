"""Configuration for the device lifecycle ledger engine (milestone M3.3).

Mirrors the trust, ledger, integrity and passport engines' configs: a small,
frozen, slotted value object holding the lifecycle rules locator, plus a hook to
build it from application settings. Everything that actually shapes a *lifecycle
verdict* — which transitions are legal, which events may start or end a lifecycle
— lives in the external transition-rules file, not here, so the config stays a
thin locator.

Keeping the engine's operational knobs in one immutable object (rather than
scattered literals) is what makes lifecycle validation reproducible and easy to
reason about.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..configs.settings import Settings

#: Default lifecycle-rules locator, relative to the ``device_ai`` package root.
DEFAULT_RULES_PATH = "lifecycle/data/transitions.yaml"


@dataclass(frozen=True, slots=True)
class LifecycleConfig:
    """Tunable configuration for the device lifecycle ledger engine.

    Attributes:
        rules_path: Locator of the external transition-rules file, resolved
            relative to the ``device_ai`` package root when not absolute.
    """

    rules_path: str = DEFAULT_RULES_PATH

    def resolved_rules_path(self, *, package_root: Path) -> Path:
        """Return the absolute lifecycle-rules path.

        Relative :attr:`rules_path` values are resolved against the given
        ``package_root`` (the ``device_ai`` package directory), so the packaged
        rules file is found regardless of the process working directory.

        Args:
            package_root: The ``device_ai`` package directory.

        Returns:
            The absolute path to the lifecycle-rules file.
        """
        candidate = Path(self.rules_path)
        if candidate.is_absolute():
            return candidate
        return package_root / candidate

    @classmethod
    def from_settings(cls, settings: Settings) -> LifecycleConfig:
        """Build a config from application settings.

        Maps the one env-driven knob (the rules locator) onto the config; every
        other field keeps its default (still overridable directly in code).
        Keeping the mapping explicit means adding an env knob is a one-line,
        reviewable change.

        Args:
            settings: The application :class:`~device_ai.configs.settings.Settings`.

        Returns:
            A :class:`LifecycleConfig` reflecting the env settings.
        """
        return cls(rules_path=settings.lifecycle_rules_path)
