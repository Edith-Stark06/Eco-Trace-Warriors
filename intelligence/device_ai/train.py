"""``python -m device_ai.train`` — training-run CLI entry point.

A thin shim over :func:`device_ai.training.cli.train_main`; see that function
for the full behaviour. By default this composes and validates a run
configuration and prints the run plan **without training** (no concrete trainer
ships in milestone M1.3).
"""

from __future__ import annotations

import sys

from .training.cli import train_main


def main() -> None:
    """Run the training CLI and exit with its status code."""
    raise SystemExit(train_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
