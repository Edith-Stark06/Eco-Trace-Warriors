"""Router acquisition CLI shim (Sprint P4.3.7).

The acquisition pipeline lives in the ``device_ai`` package under
``intelligence/`` (``python -m device_ai.acquisition``). This script is the
repository-root convenience entry point, matching the flat ``scripts/``
convention used by the rest of the dataset tooling, and it works from the repo
root without setting ``PYTHONPATH``.

It adds **no** domain logic: argument parsing, the pipeline and the report all
come from :mod:`device_ai.acquisition.cli`. The only thing this shim owns is the
``sys.path`` bootstrap (shared with the P4.2.1 toolkit) so ``import device_ai``
resolves.

Examples:
    python scripts/acquire_router_p437.py --mode auto
    python scripts/acquire_router_p437.py --mode offline \\
        --source path/to/router_dataset.zip --license CC-BY-4.0
    python scripts/acquire_router_p437.py --mode offline \\
        --source path/to/router_dataset --dry-run
    python scripts/acquire_router_p437.py --discover
    python scripts/acquire_router_p437.py --verify

Exit codes match the package CLI: 0 for a completed action (including an
honestly-reported ``BLOCKED`` outcome), 1 for a hard failure, 2 for a usage error.
"""

from __future__ import annotations

import sys

# Reuse the P4.2.1 bootstrap: importing REPO_ROOT prepends ``intelligence/`` to
# ``sys.path`` (idempotently) so ``import device_ai...`` works from the repo root.
from _ecotrace_toolkit import REPO_ROOT  # noqa: F401  (re-exported bootstrap)

from device_ai.acquisition.cli import acquire_main


def main(argv: list[str] | None = None) -> int:
    """Run the acquisition CLI.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv[1:]``).

    Returns:
        The CLI's process exit code.
    """
    return acquire_main(argv if argv is not None else sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
