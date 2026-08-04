"""``python -m device_ai.export`` — model export CLI entry point.

A thin shim over :func:`device_ai.training.cli.export_main`; see that function
for the full behaviour. Attempts to export a registered model to the configured
deployment formats, honestly reporting ``skipped`` when a backend (torch/onnx)
is not installed.
"""

from __future__ import annotations

import sys

from .training.cli import export_main


def main() -> None:
    """Run the export CLI and exit with its status code."""
    raise SystemExit(export_main(sys.argv[1:]))


if __name__ == "__main__":
    main()
