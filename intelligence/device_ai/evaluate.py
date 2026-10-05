"""``python -m device_ai.evaluate`` — model evaluation CLI entry point.

A thin shim over :func:`device_ai.training.cli.evaluate_main`; see that function
for the full behaviour. Renders a registered model's recorded metrics into a
JSON + self-contained HTML evaluation report.
"""

from __future__ import annotations

import sys

from .training.cli import evaluate_main


def main() -> None:
    """Run the evaluation CLI and exit with its status code."""
    raise SystemExit(evaluate_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
