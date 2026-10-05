"""Training artifact filesystem layout (milestone M1.3).

:class:`ArtifactManager` resolves the training artifact sub-directories relative
to a configured root (``ARTIFACT_DIR``) so **no module hardcodes a path**,
mirroring :class:`~device_ai.dataset.layout.DatasetLayout`. The three managed
sub-directories are ``checkpoints`` (trained weights), ``exports`` (converted
formats) and ``reports`` (evaluation JSON/HTML).

Everything here is filesystem-only: it resolves and creates directories and
builds artifact paths. Writing weights or reports is left to the trainer,
exporter and evaluator that consume these paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ...configs.settings import ARTIFACT_SUBDIRS, Settings
from ...utils.file_utils import ensure_directory


@dataclass(frozen=True, slots=True)
class ArtifactManager:
    """Resolve the managed training-artifact sub-directories under one root.

    The root comes from :class:`~device_ai.configs.settings.Settings`
    (dependency injection). Each property returns an absolute path; call
    :meth:`ensure` once to create the tree on disk.

    Attributes:
        root: The artifact root directory (``ARTIFACT_DIR``).
    """

    root: Path

    @classmethod
    def from_settings(cls, settings: Settings) -> ArtifactManager:
        """Build a manager from application settings.

        Args:
            settings: The active settings supplying ``artifact_dir``.

        Returns:
            An :class:`ArtifactManager` rooted at ``settings.artifact_dir``.
        """
        return cls(root=Path(settings.artifact_dir))

    def subdir(self, name: str) -> Path:
        """Return the absolute path of a named sub-directory.

        Args:
            name: One of :data:`ARTIFACT_SUBDIRS`.

        Returns:
            The resolved (uncreated) directory path.

        Raises:
            ValueError: If ``name`` is not a known artifact sub-directory.
        """
        if name not in ARTIFACT_SUBDIRS:
            raise ValueError(
                f"Unknown artifact sub-directory '{name}'. "
                f"Expected one of: {', '.join(ARTIFACT_SUBDIRS)}."
            )
        return self.root / name

    @property
    def checkpoints(self) -> Path:
        """Trained model checkpoints (weights)."""
        return self.root / "checkpoints"

    @property
    def exports(self) -> Path:
        """Exported model artifacts (TorchScript / ONNX / …)."""
        return self.root / "exports"

    @property
    def reports(self) -> Path:
        """Evaluation reports (JSON / HTML)."""
        return self.root / "reports"

    @property
    def registry_file(self) -> Path:
        """Path of the JSON model-registry document at the artifact root."""
        return self.root / "model_registry.json"

    def all_subdirs(self) -> tuple[Path, ...]:
        """Return every managed sub-directory path in declaration order."""
        return tuple(self.root / name for name in ARTIFACT_SUBDIRS)

    def ensure(self) -> ArtifactManager:
        """Create the root and every managed sub-directory if missing.

        Returns:
            This manager, for chaining.
        """
        ensure_directory(self.root)
        for path in self.all_subdirs():
            ensure_directory(path)
        return self

    def checkpoint_path(self, model_name: str, version: str) -> Path:
        """Return the checkpoint path for a model name / version.

        The ``checkpoints`` directory is created if missing so callers can
        write immediately. The file itself is *not* created.

        Args:
            model_name: Logical model name (used in the file stem).
            version: Artifact version (used in the file stem).

        Returns:
            ``<root>/checkpoints/<model_name>-<version>.pt``.
        """
        ensure_directory(self.checkpoints)
        return self.checkpoints / f"{model_name}-{version}.pt"

    def export_path(self, model_name: str, version: str, suffix: str) -> Path:
        """Return an export path for a model name / version / file suffix.

        Args:
            model_name: Logical model name (used in the file stem).
            version: Artifact version (used in the file stem).
            suffix: File extension including the leading dot (e.g. ``".onnx"``).

        Returns:
            ``<root>/exports/<model_name>-<version><suffix>``.
        """
        ensure_directory(self.exports)
        return self.exports / f"{model_name}-{version}{suffix}"

    def report_path(self, model_name: str, version: str, suffix: str) -> Path:
        """Return an evaluation-report path for a model name / version / suffix.

        Args:
            model_name: Logical model name (used in the file stem).
            version: Artifact version (used in the file stem).
            suffix: File extension including the leading dot (e.g. ``".html"``).

        Returns:
            ``<root>/reports/<model_name>-<version><suffix>``.
        """
        ensure_directory(self.reports)
        return self.reports / f"{model_name}-{version}{suffix}"
