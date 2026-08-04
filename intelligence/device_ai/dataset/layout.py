"""Dataset filesystem layout and discovery.

:class:`DatasetLayout` resolves the managed dataset sub-directories relative
to a configured root (``DATASET_DIR``) so **no module hardcodes a path**.
Discovery helpers walk a directory for supported images and pair them with
their YOLO ``.txt`` label files.

Everything here is filesystem-only; image decoding and metrics live in the
sibling modules that consume these paths.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from ..configs.settings import ALLOWED_IMAGE_EXTENSIONS, DATASET_SUBDIRS, Settings
from ..utils.file_utils import ensure_directory


@dataclass(frozen=True, slots=True)
class DatasetLayout:
    """Resolve the managed dataset sub-directories under a single root.

    The root comes from :class:`~device_ai.configs.settings.Settings`
    (dependency injection). Each property returns an absolute path; call
    :meth:`ensure` once to create the tree on disk.

    Attributes:
        root: The dataset root directory (``DATASET_DIR``).
    """

    root: Path

    @classmethod
    def from_settings(cls, settings: Settings) -> DatasetLayout:
        """Build a layout from application settings.

        Args:
            settings: The active settings supplying ``dataset_dir``.

        Returns:
            A :class:`DatasetLayout` rooted at ``settings.dataset_dir``.
        """
        return cls(root=settings.dataset_dir)

    def subdir(self, name: str) -> Path:
        """Return the absolute path of a named sub-directory.

        Args:
            name: One of :data:`DATASET_SUBDIRS`.

        Returns:
            The resolved (uncreated) directory path.

        Raises:
            ValueError: If ``name`` is not a known dataset sub-directory.
        """
        if name not in DATASET_SUBDIRS:
            raise ValueError(
                f"Unknown dataset sub-directory '{name}'. "
                f"Expected one of: {', '.join(DATASET_SUBDIRS)}."
            )
        return self.root / name

    @property
    def raw(self) -> Path:
        """Ingested, unmodified source images."""
        return self.root / "raw"

    @property
    def processed(self) -> Path:
        """Images after deterministic preprocessing."""
        return self.root / "processed"

    @property
    def cleaned(self) -> Path:
        """Images remaining after duplicate/quality removal."""
        return self.root / "cleaned"

    @property
    def augmented(self) -> Path:
        """Generated augmentation variants."""
        return self.root / "augmented"

    @property
    def annotations(self) -> Path:
        """Source annotations in their original format."""
        return self.root / "annotations"

    @property
    def labels(self) -> Path:
        """Normalised YOLO ``.txt`` label files."""
        return self.root / "labels"

    @property
    def metadata(self) -> Path:
        """Per-dataset metadata JSON documents."""
        return self.root / "metadata"

    @property
    def quality(self) -> Path:
        """Quality reports (JSON/HTML)."""
        return self.root / "quality"

    @property
    def splits(self) -> Path:
        """Train/val/test split manifests."""
        return self.root / "splits"

    @property
    def exports(self) -> Path:
        """Format exports (YOLO/COCO/VOC)."""
        return self.root / "exports"

    def all_subdirs(self) -> tuple[Path, ...]:
        """Return every managed sub-directory path in declaration order."""
        return tuple(self.root / name for name in DATASET_SUBDIRS)

    def ensure(self) -> DatasetLayout:
        """Create the root and every managed sub-directory if missing.

        Returns:
            This layout, for chaining.
        """
        ensure_directory(self.root)
        for path in self.all_subdirs():
            ensure_directory(path)
        return self


def iter_image_paths(root: Path) -> Iterator[Path]:
    """Yield supported image files beneath ``root`` in sorted order.

    Sorting makes discovery deterministic across platforms, which keeps
    hashing, splitting and reporting reproducible.

    Args:
        root: Directory to scan recursively.

    Yields:
        Absolute paths of files whose extension is in
        :data:`ALLOWED_IMAGE_EXTENSIONS`.
    """
    if not root.exists():
        return
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in ALLOWED_IMAGE_EXTENSIONS:
            yield path


def list_image_paths(root: Path) -> list[Path]:
    """Return all supported image files beneath ``root`` (sorted).

    Args:
        root: Directory to scan recursively.

    Returns:
        A list of image paths.
    """
    return list(iter_image_paths(root))


def relative_path(path: Path, root: Path) -> str:
    """Return ``path`` relative to ``root`` as a POSIX string.

    Falls back to the file name when ``path`` is not located under ``root``
    so callers always receive a stable, serialisable identifier.

    Args:
        path: The file path to relativise.
        root: The base directory.

    Returns:
        A forward-slash relative path (or the bare file name on mismatch).
    """
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def label_path_for(image_path: Path, images_root: Path, labels_root: Path) -> Path:
    """Return the YOLO label path corresponding to an image.

    The label mirrors the image's location relative to ``images_root`` under
    ``labels_root`` with a ``.txt`` suffix::

        images/a/b/dev.jpg  ->  labels/a/b/dev.txt

    Args:
        image_path: Absolute path of the image.
        images_root: Root the image is located under.
        labels_root: Root beneath which labels live.

    Returns:
        The expected label file path (which may not exist).
    """
    rel = relative_path(image_path, images_root)
    return (labels_root / rel).with_suffix(".txt")
