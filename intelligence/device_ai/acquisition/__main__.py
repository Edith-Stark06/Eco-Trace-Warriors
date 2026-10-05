"""``python -m device_ai.acquisition`` — router-acquisition CLI entry point.

A thin shim over :func:`device_ai.acquisition.cli.acquire_main`; see that module
for the full behaviour and the sub-command reference.
"""

from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    main()
