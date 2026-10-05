"""Kaggle source adapter — fail-closed unless egress + Kaggle credentials present."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from .base import MECHANISM_KAGGLE, AdapterUnavailable, SourceCandidate
from .remote_base import RemoteSourceAdapter


class KaggleAdapter(RemoteSourceAdapter):
    """Acquire a configured Kaggle dataset (requires ``KAGGLE_USERNAME`` + ``KAGGLE_KEY``).

    Discovery yields candidates only for explicitly configured ``coordinates``
    (each needs a ``dataset`` slug ``owner/name``); the adapter never searches
    Kaggle on its own.
    """

    name = "kaggle"
    mechanism = MECHANISM_KAGGLE
    required_credentials = ("KAGGLE_USERNAME", "KAGGLE_KEY")

    @classmethod
    def from_env(
        cls,
        *,
        work_dir: Path,
        env: Mapping[str, str] | None = None,
        coordinates: list[dict] | None = None,
    ) -> KaggleAdapter:
        """Build the adapter from the process environment (or an injected map)."""
        return cls(
            env=env if env is not None else os.environ,
            work_dir=work_dir,
            coordinates=coordinates,
        )

    def _download(self, candidate: SourceCandidate) -> Path:
        """Download and unzip the configured Kaggle dataset.

        Uses the documented public ``kaggle`` SDK. Runs only after the
        availability gate passes; only ever exercised where egress + credentials
        + the ``kaggle`` package are present.
        """
        try:
            from kaggle.api.kaggle_api_extended import (  # type: ignore[import-not-found]
                KaggleApi,
            )
        except ImportError as exc:
            raise AdapterUnavailable(
                "kaggle SDK not installed (`pip install kaggle`); "
                "cannot download without it"
            ) from exc

        coord = self._coordinate_for(candidate)
        dest = self._work_dir / f"kaggle_{candidate.name or 'dataset'}"
        dest.mkdir(parents=True, exist_ok=True)

        api = KaggleApi()
        api.authenticate()
        api.dataset_download_files(coord["dataset"], path=str(dest), unzip=True)
        return dest

    def _coordinate_for(self, candidate: SourceCandidate) -> dict:
        """Return the configured coordinate matching a candidate by name."""
        for coord in self._coordinates:
            if str(coord.get("name", "")) == candidate.name:
                return coord
        raise AdapterUnavailable(
            f"no configured Kaggle coordinate for candidate '{candidate.name}'"
        )
