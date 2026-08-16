"""Shared scaffolding for remote (networked) source adapters.

Remote adapters (Roboflow, Kaggle, Hugging Face) share one safety contract:

* they are **unavailable** unless egress *and* every required credential are
  present — checked by :meth:`RemoteSourceAdapter.availability`;
* they **never crawl or fabricate**: discovery yields candidates only for
  *explicitly configured coordinates*. With none configured (the default), an
  available adapter simply returns an empty list;
* :meth:`discover` and :meth:`materialize` raise
  :class:`~device_ai.acquisition.adapters.base.AdapterUnavailable` (a fail-closed
  signal the pipeline records and continues past) whenever prerequisites are
  unmet.

The vendor-SDK download in each concrete adapter's :meth:`_download` runs only
after the availability gate passes and the SDK import succeeds; any failure is
converted to :class:`AdapterUnavailable`. That live path requires a networked
environment with credentials and the vendor package installed — it is
intentionally never reached in an offline run.
"""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Mapping
from pathlib import Path

from .base import (
    AdapterStatus,
    AdapterUnavailable,
    SourceAdapter,
    SourceCandidate,
)


class RemoteSourceAdapter(SourceAdapter):
    """Base for network-backed adapters with fail-closed prerequisites.

    Args:
        env: Environment mapping consulted for credentials (injected for tests;
            defaults to ``os.environ`` in the concrete adapters' factories).
        work_dir: Scratch directory for downloads.
        coordinates: Explicitly configured source targets. Each mapping supplies
            candidate metadata (``name``/``publisher``/``url``/``version``/
            ``license_raw``/``license_url``/``source_class``). Empty by default —
            an available adapter with no coordinates discovers nothing (it never
            searches a public catalogue on its own).
    """

    #: Download-mechanism identifier for candidates (overridden per adapter).
    mechanism: str = "remote"

    #: Environment variable names that must all be present for credentials.
    required_credentials: tuple[str, ...] = ()

    #: Whether the adapter needs egress at all (all remotes do).
    requires_network: bool = True

    def __init__(
        self,
        *,
        env: Mapping[str, str],
        work_dir: Path,
        coordinates: list[dict] | None = None,
    ) -> None:
        self._env = env
        self._work_dir = Path(work_dir)
        self._coordinates = coordinates or []

    def _missing_credentials(self) -> tuple[str, ...]:
        """Return required credential keys that are absent/empty in the env."""
        return tuple(
            key for key in self.required_credentials if not self._env.get(key)
        )

    def availability(self, *, online: bool) -> AdapterStatus:
        """Fail-closed check: needs egress and every required credential."""
        missing: list[str] = []
        if self.requires_network and not online:
            missing.append("network")
        missing.extend(self._missing_credentials())
        if missing:
            need = ", ".join(missing)
            return AdapterStatus(
                available=False,
                reason=(
                    f"{self.name} unavailable: missing {need}; "
                    "fail closed (no guessing, no fabrication)"
                ),
                missing_requirements=tuple(sorted(missing)),
            )
        return AdapterStatus(
            available=True,
            reason=f"{self.name} prerequisites satisfied (network + credentials)",
        )

    def discover(self, *, online: bool) -> list[SourceCandidate]:
        """Build candidates from configured coordinates (no download).

        Raises:
            AdapterUnavailable: When network/credentials are missing.
        """
        status = self.availability(online=online)
        if not status.available:
            raise AdapterUnavailable(status.reason)
        candidates: list[SourceCandidate] = []
        for coord in self._coordinates:
            candidates.append(
                SourceCandidate(
                    name=str(coord.get("name", "")),
                    publisher=str(coord.get("publisher", "")),
                    url=str(coord.get("url", "")),
                    version=str(coord.get("version", "")),
                    license_raw=str(coord.get("license_raw", "")),
                    license_url=str(coord.get("license_url", "")),
                    source_class=str(coord.get("source_class", "")),
                    bbox_available=bool(coord.get("bbox_available", False)),
                    image_identifier=str(coord.get("image_identifier", "")),
                    annotation_identifier=str(coord.get("annotation_identifier", "")),
                    download_mechanism=self.mechanism,
                    adapter=self.name,
                    detail=str(coord.get("detail", "")),
                )
            )
        return candidates

    def materialize(self, candidate: SourceCandidate, *, online: bool) -> Path:
        """Download the candidate to local disk via the vendor SDK.

        Raises:
            AdapterUnavailable: When prerequisites are unmet, the vendor SDK is
                not installed, or the download fails. The pipeline records the
                exact reason and continues.
        """
        status = self.availability(online=online)
        if not status.available:
            raise AdapterUnavailable(status.reason)
        try:
            return self._download(candidate)
        except AdapterUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001 - any SDK failure -> fail closed
            raise AdapterUnavailable(
                f"{self.name} download failed: {type(exc).__name__}: {exc}"
            ) from exc

    @abstractmethod
    def _download(self, candidate: SourceCandidate) -> Path:
        """Vendor-specific download; return the local root. Never fabricates."""
