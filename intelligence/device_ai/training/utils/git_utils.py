"""Git provenance helpers.

Every training run records the exact source revision it was produced from so a
model in the registry can be traced back to code. Resolution is best-effort:
outside a Git checkout (or when Git is unavailable) the helpers degrade to a
stable ``"unknown"`` sentinel rather than raising, keeping training runnable in
minimal containers.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

#: Returned when a commit cannot be resolved (no repo / git missing / error).
UNKNOWN_COMMIT = "unknown"


def _run_git(args: list[str], *, cwd: Path) -> str | None:
    """Run a ``git`` command and return its stripped stdout, or ``None``.

    Any failure — Git not installed, not a repository, non-zero exit — results
    in ``None`` so callers can fall back gracefully.

    Args:
        args: Arguments following the ``git`` executable.
        cwd: Working directory the command runs in.

    Returns:
        The command's stripped standard output, or ``None`` on any error.
    """
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    output = completed.stdout.strip()
    return output or None


def git_commit_hash(*, cwd: Path | None = None, short: bool = True) -> str:
    """Return the current Git commit hash, or ``"unknown"`` when unavailable.

    Args:
        cwd: Directory to resolve the repository from; defaults to the current
            working directory.
        short: When ``True`` return the abbreviated hash, else the full SHA.

    Returns:
        The commit hash, or :data:`UNKNOWN_COMMIT` if it cannot be determined.
    """
    directory = cwd or Path.cwd()
    args = ["rev-parse", "--short", "HEAD"] if short else ["rev-parse", "HEAD"]
    return _run_git(args, cwd=directory) or UNKNOWN_COMMIT


def git_is_dirty(*, cwd: Path | None = None) -> bool:
    """Return whether the working tree has uncommitted changes.

    A dirty tree is worth recording alongside a run so a model's provenance
    is not silently attributed to a clean commit. Returns ``False`` when the
    repository state cannot be determined.

    Args:
        cwd: Directory to resolve the repository from; defaults to CWD.

    Returns:
        ``True`` if tracked files have uncommitted modifications.
    """
    directory = cwd or Path.cwd()
    status = _run_git(["status", "--porcelain"], cwd=directory)
    return bool(status)
