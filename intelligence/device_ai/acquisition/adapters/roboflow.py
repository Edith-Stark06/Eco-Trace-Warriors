"""Roboflow source adapter — fail-closed unless egress + API key present."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from .base import MECHANISM_ROBOFLOW, AdapterUnavailable, SourceCandidate
from .remote_base import RemoteSourceAdapter


class RoboflowAdapter(RemoteSourceAdapter):
    """Acquire a configured Roboflow dataset version (requires ``ROBOFLOW_API_KEY``).

    Discovery yields candidates only for explicitly configured ``coordinates``
    (each needs ``workspace``/``project``/``version``); the adapter never
    searches Roboflow Universe on its own.
    """

    name = "roboflow"
    mechanism = MECHANISM_ROBOFLOW
    required_credentials = ("ROBOFLOW_API_KEY",)

    @classmethod
    def from_env(
        cls,
        *,
        work_dir: Path,
        env: Mapping[str, str] | None = None,
        coordinates: list[dict] | None = None,
    ) -> RoboflowAdapter:
        """Build the adapter from the process environment (or an injected map)."""
        return cls(
            env=env if env is not None else os.environ,
            work_dir=work_dir,
            coordinates=coordinates,
        )

    def _download(self, candidate: SourceCandidate) -> Path:
        """Download the configured Roboflow version in YOLO format.

        Uses the documented public ``roboflow`` SDK. Runs only after the
        availability gate passes; only ever exercised where egress + the API key
        + the ``roboflow`` package are present.
        """
        try:
            from roboflow import Roboflow  # type: ignore[import-not-found]
        except ImportError as exc:
            raise AdapterUnavailable(
                "roboflow SDK not installed (`pip install roboflow`); "
                "cannot download without it"
            ) from exc

        coord = self._coordinate_for(candidate)
        api_key = self._env.get("ROBOFLOW_API_KEY", "")
        dest = self._work_dir / f"roboflow_{candidate.name or 'dataset'}"
        dest.mkdir(parents=True, exist_ok=True)

        rf = Roboflow(api_key=api_key)
        project = rf.workspace(coord["workspace"]).project(coord["project"])
        version = project.version(int(coord["version"]))
        version.download("yolov8", location=str(dest))
        return dest

    def _coordinate_for(self, candidate: SourceCandidate) -> dict:
        """Return the configured coordinate matching a candidate by name."""
        for coord in self._coordinates:
            if str(coord.get("name", "")) == candidate.name:
                return coord
        raise AdapterUnavailable(
            f"no configured Roboflow coordinate for candidate '{candidate.name}'"
        )
