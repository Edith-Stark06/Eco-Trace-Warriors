"""The forecasting LSTM (P10.1).

``torch`` is an optional, heavy dependency in this project — exactly like the
YOLO detector and the OpenCLIP encoder (``requirements-detector.txt`` /
``requirements-models.txt``; see ``inference/clip_encoder.py``'s docstring
for the established pattern this file mirrors). Its import is guarded so the
base environment (and this service's own default test environment, which
does not install torch) never fails to import this module — it simply
reports :func:`torch_available` as ``False`` and the forecasting service
degrades to ``MODEL_BACKEND_UNAVAILABLE`` rather than crashing or fabricating
a prediction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

try:  # pragma: no cover - exercised only where torch is installed (Docker image)
    import torch
    from torch import nn

    _TORCH_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised in the base/test environment
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]
    _TORCH_AVAILABLE = False

if TYPE_CHECKING:  # pragma: no cover - type-checking only, no runtime import cost
    import torch as _torch


def torch_available() -> bool:
    """Return whether the optional torch backend is importable here."""
    return _TORCH_AVAILABLE


#: A small LSTM sized for a prototype-scale daily time series (per-task
#: guidance: "do NOT over-engineer the neural network"). One recurrent layer
#: with a small hidden size, followed by a single dense output — exactly the
#: pipeline diagram: lookback window -> LSTM -> Dense(1) -> next-day value.
if _TORCH_AVAILABLE:

    class LSTMForecastNet(nn.Module):  # type: ignore[misc]
        """Single-layer LSTM + linear head predicting the next day's weight.

        Args:
            hidden_size: LSTM hidden state width (``FORECAST_LSTM_UNITS``).
            num_layers: Number of stacked LSTM layers (default: 1 — a
                prototype-scale model needs no more).
        """

        def __init__(self, hidden_size: int = 32, num_layers: int = 1) -> None:
            super().__init__()
            self.hidden_size = hidden_size
            self.num_layers = num_layers
            self.lstm = nn.LSTM(
                input_size=1,
                hidden_size=hidden_size,
                num_layers=num_layers,
                batch_first=True,
            )
            self.head = nn.Linear(hidden_size, 1)

        def forward(self, x: _torch.Tensor) -> _torch.Tensor:
            """Predict the next value from a batch of lookback windows.

            Args:
                x: Tensor of shape ``(batch, lookback, 1)``.

            Returns:
                Tensor of shape ``(batch,)`` — the predicted next scaled value.
            """
            out, _ = self.lstm(x)
            last_hidden = out[:, -1, :]
            return self.head(last_hidden).squeeze(-1)

else:  # pragma: no cover - exercised only in the base/test environment

    class LSTMForecastNet:  # type: ignore[no-redef]
        """Placeholder used only to type-hint call sites when torch is absent."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError(
                "LSTMForecastNet requires torch, which is not installed. "
                "Call torch_available() before constructing this class."
            )
