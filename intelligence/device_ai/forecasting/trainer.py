"""Training, evaluation and recursive prediction for the forecasting LSTM (P10.1).

Chronological (never shuffled-across-the-split) train/validation split, real
RMSE/MAE/MAPE on the held-out tail, and multi-step recursive forecasting.
Requires torch — callers must check :func:`~.model.torch_available` first;
see that module's docstring for why the dependency is optional.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .model import LSTMForecastNet, torch_available
from .models import EvaluationMetrics
from .preprocessing import MinMaxScaler, make_sliding_windows

#: Minimum sliding-window samples reserved for training / validation before a
#: chronological split is considered meaningful at all. Combined with the
#: lookback window by the service layer to derive the overall minimum-history
#: requirement (Settings.forecast_min_history_days is the other, coarser floor).
MIN_TRAIN_SAMPLES = 10
MIN_VAL_SAMPLES = 5

#: Fraction of sliding-window samples held out (chronologically, from the
#: end) for validation.
VAL_FRACTION = 0.2


@dataclass(frozen=True, slots=True)
class TrainedForecastArtifact:
    """Everything needed to persist a trained model and later run inference.

    Attributes:
        state_dict: The trained ``LSTMForecastNet``'s ``state_dict()``.
        scaler: The fitted :class:`~.preprocessing.MinMaxScaler`.
        hidden_size: LSTM hidden width the model was built with.
        lookback: Lookback window (days) the model was trained on.
        last_window: The most recent ``lookback`` real (unscaled) values —
            the seed used to recursively forecast future days.
        evaluation: Real chronological holdout metrics.
    """

    state_dict: dict[str, object]
    scaler: MinMaxScaler
    hidden_size: int
    lookback: int
    last_window: np.ndarray
    evaluation: EvaluationMetrics


def train_lstm_forecaster(
    series: np.ndarray,
    *,
    lookback: int,
    epochs: int,
    batch_size: int,
    hidden_size: int,
    learning_rate: float = 1e-3,
    seed: int = 42,
) -> TrainedForecastArtifact:
    """Train a small LSTM on a dense daily series and evaluate it honestly.

    The split is chronological: the last ``VAL_FRACTION`` of sliding-window
    samples (by time, never shuffled across the boundary) are held out for
    validation; only the training portion is shuffled batch-to-batch, which
    is standard practice and does not leak future information — the
    train/validation boundary itself is never crossed.

    Args:
        series: Dense, zero-filled daily values (see :func:`build_daily_series`).
        lookback: Days of history the model conditions on.
        epochs: Training epochs (full passes over the training windows).
        batch_size: Mini-batch size.
        hidden_size: LSTM hidden width.
        learning_rate: Adam learning rate.
        seed: RNG seed for reproducibility.

    Returns:
        The trained model's weights, fitted scaler, and real evaluation metrics.

    Raises:
        RuntimeError: If torch is not installed (call :func:`torch_available` first).
        ValueError: If ``series`` has too few points to form a train+val split.
    """
    if not torch_available():
        raise RuntimeError("train_lstm_forecaster requires torch, which is absent.")

    import torch  # local import: guarded module-level import lives in .model

    torch.manual_seed(seed)

    scaler = MinMaxScaler().fit(series)
    scaled = scaler.transform(series)
    x, y = make_sliding_windows(scaled, lookback)

    n_samples = len(x)
    if n_samples < MIN_TRAIN_SAMPLES + MIN_VAL_SAMPLES:
        raise ValueError(
            f"Need at least {MIN_TRAIN_SAMPLES + MIN_VAL_SAMPLES} sliding-window "
            f"samples to train and evaluate; got {n_samples}."
        )

    n_val = max(MIN_VAL_SAMPLES, int(round(n_samples * VAL_FRACTION)))
    n_val = min(n_val, n_samples - MIN_TRAIN_SAMPLES)
    n_train = n_samples - n_val

    x_train, y_train = x[:n_train], y[:n_train]
    x_val, y_val = x[n_train:], y[n_train:]

    model = LSTMForecastNet(hidden_size=hidden_size)
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
    loss_fn = torch.nn.MSELoss()

    x_train_t = torch.tensor(x_train, dtype=torch.float32).unsqueeze(-1)
    y_train_t = torch.tensor(y_train, dtype=torch.float32)

    generator = torch.Generator().manual_seed(seed)
    model.train()
    for _epoch in range(epochs):
        permutation = torch.randperm(n_train, generator=generator)
        for start in range(0, n_train, batch_size):
            batch_idx = permutation[start : start + batch_size]
            optimizer.zero_grad()
            prediction = model(x_train_t[batch_idx])
            loss = loss_fn(prediction, y_train_t[batch_idx])
            loss.backward()
            optimizer.step()

    model.eval()
    with torch.no_grad():
        x_val_t = torch.tensor(x_val, dtype=torch.float32).unsqueeze(-1)
        pred_val_scaled = model(x_val_t).numpy()

    pred_val = scaler.inverse_transform(pred_val_scaled)
    actual_val = scaler.inverse_transform(y_val)

    rmse = float(np.sqrt(np.mean((pred_val - actual_val) ** 2)))
    mae = float(np.mean(np.abs(pred_val - actual_val)))
    nonzero = actual_val != 0
    if bool(np.any(nonzero)):
        errors = pred_val[nonzero] - actual_val[nonzero]
        pct_errors = np.abs(errors / actual_val[nonzero])
        mape = float(np.mean(pct_errors) * 100)
    else:
        mape = None

    evaluation = EvaluationMetrics(
        rmse=rmse,
        mae=mae,
        mape=mape,
        train_samples=int(n_train),
        val_samples=int(n_val),
    )

    return TrainedForecastArtifact(
        state_dict={k: v.clone() for k, v in model.state_dict().items()},
        scaler=scaler,
        hidden_size=hidden_size,
        lookback=lookback,
        last_window=series[-lookback:].copy(),
        evaluation=evaluation,
    )


def predict_horizon(
    *,
    state_dict: dict[str, object],
    hidden_size: int,
    scaler: MinMaxScaler,
    last_window: np.ndarray,
    horizon: int,
) -> np.ndarray:
    """Recursively forecast ``horizon`` future days from the trained model.

    Each predicted day is fed back in as input for the next step (a standard
    recursive multi-step strategy for a single-step-trained LSTM). Predicted
    weights are clipped at zero — a physical quantity of recycled e-waste
    cannot be negative.

    Args:
        state_dict: Trained model weights (:attr:`TrainedForecastArtifact.state_dict`).
        hidden_size: LSTM hidden width the weights were trained with.
        scaler: The fitted scaler used at training time.
        last_window: The most recent ``lookback`` real (unscaled) values.
        horizon: Number of future days to predict.

    Returns:
        A 1-D array of ``horizon`` predicted weights, in kilograms.

    Raises:
        RuntimeError: If torch is not installed.
    """
    if not torch_available():
        raise RuntimeError("predict_horizon requires torch, which is not installed.")

    import torch

    model = LSTMForecastNet(hidden_size=hidden_size)
    model.load_state_dict(state_dict)
    model.eval()

    window = list(scaler.transform(last_window))
    lookback = len(last_window)
    predictions: list[float] = []

    with torch.no_grad():
        for _ in range(horizon):
            recent = window[-lookback:]
            x = torch.tensor([recent], dtype=torch.float32).unsqueeze(-1)
            next_scaled = float(model(x).item())
            predictions.append(next_scaled)
            window.append(next_scaled)

    unscaled = scaler.inverse_transform(np.asarray(predictions, dtype=np.float64))
    clipped: np.ndarray = np.clip(unscaled, a_min=0.0, a_max=None)
    return clipped
