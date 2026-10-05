"""Trainer discovery registry for the training platform (milestone M1.3).

:class:`TrainerRegistry` maps a short string key (e.g. ``"mock"``, and in future
``"yolo"`` / ``"clip"``) to a trainer class, so a run configuration can select
its trainer by name and the CLI can instantiate it without importing every
implementation. Registration is via the :meth:`TrainerRegistry.register`
decorator factory, mirroring the extensible, decoupled patterns used elsewhere
in the engine.

The registry stores classes, not instances, and never constructs a trainer
itself — construction (with injected collaborators) is the caller's job. No
trainer implementation is registered in this milestone; the tests register a
``MockTrainer`` to exercise the machinery.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from ...exceptions import TrainerNotFoundError

#: A registered value is any class; kept unconstrained so this module need not
#: import :class:`BaseTrainer` (avoiding an import cycle with ``trainer.py``).
T = TypeVar("T", bound=type)


class TrainerRegistry:
    """A name → trainer-class registry with decorator-based registration.

    Instances are self-contained (no global mutable state), so tests and callers
    can build an isolated registry. A module-level :data:`default_registry` is
    provided for the common case of a single shared registry.
    """

    def __init__(self) -> None:
        self._trainers: dict[str, type] = {}

    def register(self, name: str) -> Callable[[T], T]:
        """Return a class decorator that registers a trainer under ``name``.

        Usage::

            @registry.register("mock")
            class MockTrainer(BaseTrainer):
                ...

        Args:
            name: The unique key the trainer is selected by.

        Returns:
            A decorator that records the class and returns it unchanged.

        Raises:
            ValueError: If ``name`` is empty or already registered.
        """
        key = name.strip()
        if not key:
            raise ValueError("Trainer name must be a non-empty string.")
        if key in self._trainers:
            raise ValueError(f"Trainer '{key}' is already registered.")

        def decorator(cls: T) -> T:
            self._trainers[key] = cls
            return cls

        return decorator

    def get(self, name: str) -> type:
        """Return the trainer class registered under ``name``.

        Args:
            name: The trainer key to look up.

        Returns:
            The registered trainer class.

        Raises:
            TrainerNotFoundError: If ``name`` is not registered.
        """
        try:
            return self._trainers[name]
        except KeyError as exc:
            available = ", ".join(sorted(self._trainers)) or "(none)"
            raise TrainerNotFoundError(
                f"No trainer registered as '{name}'. Available: {available}.",
                details={"name": name, "available": sorted(self._trainers)},
            ) from exc

    def names(self) -> tuple[str, ...]:
        """Return the sorted keys of every registered trainer."""
        return tuple(sorted(self._trainers))

    def __contains__(self, name: object) -> bool:
        """Return whether ``name`` is a registered trainer key."""
        return name in self._trainers

    def __len__(self) -> int:
        """Return the number of registered trainers."""
        return len(self._trainers)


#: Shared registry used by the CLI when no explicit registry is injected.
default_registry = TrainerRegistry()
