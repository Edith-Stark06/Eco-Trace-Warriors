"""Wall-clock timing utilities.

:class:`Timer` is a minimal context manager used to measure how long a phase of
the training lifecycle takes (e.g. total ``training_time`` recorded on a run).
It relies on :func:`time.perf_counter` — a monotonic, high-resolution clock —
so measurements are unaffected by wall-clock adjustments.
"""

from __future__ import annotations

from time import perf_counter
from types import TracebackType


class Timer:
    """Context manager measuring elapsed wall-clock seconds.

    Usage::

        with Timer() as timer:
            do_work()
        print(timer.elapsed)

    The timer may also be reused by calling :meth:`start`/:meth:`stop`
    directly. :attr:`elapsed` reflects the last completed interval, or the
    time since :meth:`start` while running.

    Attributes:
        label: Optional human-readable label for the timed section.
    """

    def __init__(self, label: str = "") -> None:
        self.label = label
        self._start: float | None = None
        self._elapsed: float = 0.0

    def start(self) -> Timer:
        """Begin (or restart) timing.

        Returns:
            This timer, for chaining.
        """
        self._start = perf_counter()
        return self

    def stop(self) -> float:
        """Stop timing and return the elapsed seconds.

        Returns:
            Seconds elapsed since the most recent :meth:`start`.

        Raises:
            RuntimeError: If called before :meth:`start`.
        """
        if self._start is None:
            raise RuntimeError("Timer.stop() called before start().")
        self._elapsed = perf_counter() - self._start
        self._start = None
        return self._elapsed

    @property
    def elapsed(self) -> float:
        """Elapsed seconds: the running interval, or the last completed one."""
        if self._start is not None:
            return perf_counter() - self._start
        return self._elapsed

    @property
    def elapsed_ms(self) -> float:
        """Elapsed time in milliseconds, rounded to three decimals."""
        return round(self.elapsed * 1000.0, 3)

    def __enter__(self) -> Timer:
        """Start the timer on entry."""
        return self.start()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Stop the timer on exit (exceptions are not suppressed)."""
        self.stop()
