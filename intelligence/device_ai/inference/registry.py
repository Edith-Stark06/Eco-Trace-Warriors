"""Model registry: configuration-driven artifact resolution.

Real model adapters must never hardcode file paths (``CLAUDE.md`` → AI
Rules). The registry resolves the on-disk location of a versioned artifact
from the configured ``MODEL_DIR`` and reports availability. In milestone
M1.1 no artifacts exist yet, so the registry primarily serves as the
future integration point and lets ``/health`` report the model directory
state.

Expected on-disk convention (documented for future work)::

    <MODEL_DIR>/<component>/<component>-<semver>/model.<ext>

e.g. ``models/detector/detector-1.2.0/model.onnx``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    """A reference to a (possibly not-yet-present) model artifact.

    Attributes:
        component: Logical component name (e.g. ``"detector"``).
        version: Semantic version of the artifact.
        path: Resolved directory expected to contain the artifact.
        exists: Whether the resolved path currently exists on disk.
    """

    component: str
    version: str
    path: Path
    exists: bool


class ModelRegistry:
    """Resolve and report on versioned model artifacts under ``model_dir``.

    Args:
        model_dir: Root directory containing per-component artifact folders.
    """

    def __init__(self, model_dir: Path) -> None:
        self._model_dir = model_dir

    @property
    def model_dir(self) -> Path:
        """The configured model root directory."""
        return self._model_dir

    def resolve(self, component: str, version: str) -> ArtifactRef:
        """Resolve the expected artifact location for a component/version.

        Args:
            component: Logical component name (e.g. ``"detector"``).
            version: Semantic version string.

        Returns:
            An :class:`ArtifactRef` describing the expected path and whether
            it currently exists.
        """
        path = self._model_dir / component / f"{component}-{version}"
        return ArtifactRef(
            component=component,
            version=version,
            path=path,
            exists=path.exists(),
        )

    def is_available(self) -> bool:
        """Whether the configured model directory exists.

        Returns:
            ``True`` if ``model_dir`` is present on disk.
        """
        return self._model_dir.exists()
