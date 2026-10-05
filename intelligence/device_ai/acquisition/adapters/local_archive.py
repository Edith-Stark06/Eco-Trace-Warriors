"""Local-archive source adapter — the offline ingestion path.

Wraps a user-supplied directory or archive (``.zip`` / ``.tar`` / ``.tar.gz`` /
``.tgz``) as a :class:`~device_ai.acquisition.adapters.base.SourceAdapter`. It
requires **no network and no credentials**, so ``--mode offline --source`` runs
entirely on local inputs.

The adapter never invents a license: the license comes from an explicit
caller-supplied string (``--license``) or a ``license`` field in a YOLO
``data.yaml``; absent both, the license is empty and the pipeline's license gate
fails closed (``UNVERIFIED``). Archive extraction is guarded against path
traversal ("zip-slip"): any member resolving outside the extraction root aborts
the extraction.
"""

from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path

from ..errors import SourceUnavailableError, UnsupportedFormatError
from ..formats import detect_format
from .base import (
    MECHANISM_LOCAL_ARCHIVE,
    AdapterStatus,
    SourceAdapter,
    SourceCandidate,
)

_ARCHIVE_SUFFIXES = {".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz"}


def _safe_extract_zip(archive: Path, dest: Path) -> None:
    """Extract a zip, rejecting any member that escapes ``dest``."""
    with zipfile.ZipFile(archive) as zf:
        for member in zf.namelist():
            target = (dest / member).resolve()
            if not str(target).startswith(str(dest.resolve())):
                raise UnsupportedFormatError(
                    f"archive member escapes extraction root: {member}"
                )
        zf.extractall(dest)


def _safe_extract_tar(archive: Path, dest: Path) -> None:
    """Extract a tar, rejecting any member that escapes ``dest``."""
    with tarfile.open(archive) as tf:
        root = dest.resolve()
        for member in tf.getmembers():
            target = (dest / member.name).resolve()
            if not str(target).startswith(str(root)):
                raise UnsupportedFormatError(
                    f"archive member escapes extraction root: {member.name}"
                )
        tf.extractall(dest)  # noqa: S202 - members validated against traversal above


class LocalArchiveAdapter(SourceAdapter):
    """Adapter over a local directory or archive (offline, no credentials).

    Args:
        source: Directory or archive path supplied by the operator.
        work_dir: Scratch directory used to extract archives (never the
            protected candidate tree).
        license_raw: Explicit license string asserted for this source (the only
            way a local archive can carry a license; never inferred).
        license_url: Optional supporting license URL.
        source_name: Human-readable dataset name (defaults to the path name).
        publisher: Publisher / contributor, if known.
        source_url: Origin URL, if known.
    """

    name = "local-archive"

    def __init__(
        self,
        source: Path | str,
        *,
        work_dir: Path,
        license_raw: str = "",
        license_url: str = "",
        source_name: str = "",
        publisher: str = "",
        source_url: str = "",
    ) -> None:
        self._source = Path(source)
        self._work_dir = Path(work_dir)
        self._license_raw = license_raw
        self._license_url = license_url
        self._source_name = source_name or self._source.name
        self._publisher = publisher
        self._source_url = source_url

    def availability(self, *, online: bool) -> AdapterStatus:
        """Available whenever the supplied source path exists (no network)."""
        if self._source.exists():
            kind = "directory" if self._source.is_dir() else "archive"
            return AdapterStatus(
                available=True,
                reason=f"local {kind} present: {self._source.as_posix()}",
            )
        return AdapterStatus(
            available=False,
            reason=f"source path does not exist: {self._source.as_posix()}",
            missing_requirements=("input",),
        )

    def _ensure_local_root(self) -> Path:
        """Return a local directory root for the source (extract if needed)."""
        if self._source.is_dir():
            return self._source
        if not self._source.is_file():
            raise SourceUnavailableError(
                f"source is neither a directory nor a file: {self._source.as_posix()}"
            )
        suffixes = {s.lower() for s in self._source.suffixes}
        dest = self._work_dir / (self._source.stem + "_extracted")
        dest.mkdir(parents=True, exist_ok=True)
        if self._source.suffix.lower() == ".zip":
            _safe_extract_zip(self._source, dest)
        elif suffixes & _ARCHIVE_SUFFIXES:
            _safe_extract_tar(self._source, dest)
        else:
            raise UnsupportedFormatError(
                f"unsupported archive type '{self._source.suffix}'; expected a "
                "directory or .zip/.tar/.tar.gz/.tgz archive"
            )
        return dest

    def _resolve_license(self, root: Path) -> str:
        """Return an explicit license string, or empty when none is available.

        Priority: caller-supplied ``license_raw`` > a ``license`` field found in
        a YOLO ``data.yaml``. Never inferred from file contents beyond an
        explicit ``license:`` key.
        """
        if self._license_raw.strip():
            return self._license_raw.strip()
        for yaml_name in ("data.yaml", "data.yml", "dataset.yaml", "dataset.yml"):
            for path in sorted(root.rglob(yaml_name)):
                license_value = _read_yaml_license(path)
                if license_value:
                    return license_value
        return ""

    def discover(self, *, online: bool) -> list[SourceCandidate]:
        """Return a single candidate describing the local source (no download)."""
        status = self.availability(online=online)
        if not status.available:
            # An explicitly requested source that is missing is a hard, reported
            # error (spec §5) rather than a silent empty discovery.
            raise SourceUnavailableError(status.reason)

        root = self._ensure_local_root()
        detected = detect_format(root)
        license_raw = self._resolve_license(root)
        return [
            SourceCandidate(
                name=self._source_name,
                publisher=self._publisher,
                url=self._source_url,
                version="",
                license_raw=license_raw,
                license_url=self._license_url,
                source_class="",  # decided per-label at ingest by the semantic gate
                bbox_available=detected.supported,
                image_identifier="image files under the detected images directory",
                annotation_identifier=(
                    detected.annotations_ref.as_posix()
                    if detected.annotations_ref
                    else ""
                ),
                download_mechanism=MECHANISM_LOCAL_ARCHIVE,
                adapter=self.name,
                local_root=root.as_posix(),
                detail=detected.detail,
            )
        ]

    def materialize(self, candidate: SourceCandidate, *, online: bool) -> Path:
        """Return the local root (already on disk for a local source)."""
        if candidate.local_root:
            return Path(candidate.local_root)
        return self._ensure_local_root()


def _read_yaml_license(path: Path) -> str:
    """Return an explicit ``license`` field from a YAML file, or empty string."""
    try:
        import yaml  # lazy: PyYAML is a project dependency
    except ImportError:
        return ""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if isinstance(data, dict):
        value = data.get("license")
        if isinstance(value, str):
            return value.strip()
    return ""
