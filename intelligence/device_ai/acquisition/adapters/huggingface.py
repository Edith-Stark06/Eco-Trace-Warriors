"""Hugging Face source adapter — fail-closed unless egress is present.

Public Hugging Face datasets need no credentials, only network egress, so this
adapter's sole hard prerequisite is connectivity. An optional token
(``HF_TOKEN`` / ``HUGGINGFACE_TOKEN``) is forwarded when present so gated
datasets also work, but its absence never blocks a public dataset.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from .base import MECHANISM_HUGGINGFACE, AdapterUnavailable, SourceCandidate
from .remote_base import RemoteSourceAdapter


class HuggingFaceAdapter(RemoteSourceAdapter):
    """Acquire a configured Hugging Face dataset repository (requires egress).

    Discovery yields candidates only for explicitly configured ``coordinates``
    (each needs a ``repo_id``); the adapter never searches the Hub on its own.
    """

    name = "huggingface"
    mechanism = MECHANISM_HUGGINGFACE
    required_credentials = ()  # public datasets need no credentials, only network

    @classmethod
    def from_env(
        cls,
        *,
        work_dir: Path,
        env: Mapping[str, str] | None = None,
        coordinates: list[dict] | None = None,
    ) -> HuggingFaceAdapter:
        """Build the adapter from the process environment (or an injected map)."""
        return cls(
            env=env if env is not None else os.environ,
            work_dir=work_dir,
            coordinates=coordinates,
        )

    def _download(self, candidate: SourceCandidate) -> Path:
        """Snapshot the configured dataset repository to local disk.

        Uses the documented public ``huggingface_hub`` SDK. Runs only after the
        availability gate passes; only ever exercised where egress (and the
        ``huggingface_hub`` package) are present.
        """
        try:
            from huggingface_hub import (  # type: ignore[import-not-found]
                snapshot_download,
            )
        except ImportError as exc:
            raise AdapterUnavailable(
                "huggingface_hub not installed (`pip install huggingface_hub`); "
                "cannot download without it"
            ) from exc

        coord = self._coordinate_for(candidate)
        dest = self._work_dir / f"hf_{candidate.name or 'dataset'}"
        dest.mkdir(parents=True, exist_ok=True)
        token = self._env.get("HF_TOKEN") or self._env.get("HUGGINGFACE_TOKEN")

        local = snapshot_download(
            repo_id=coord["repo_id"],
            repo_type="dataset",
            local_dir=str(dest),
            token=token,
        )
        return Path(local)

    def _coordinate_for(self, candidate: SourceCandidate) -> dict:
        """Return the configured coordinate matching a candidate by name."""
        for coord in self._coordinates:
            if str(coord.get("name", "")) == candidate.name:
                return coord
        raise AdapterUnavailable(
            f"no configured Hugging Face coordinate for candidate '{candidate.name}'"
        )
