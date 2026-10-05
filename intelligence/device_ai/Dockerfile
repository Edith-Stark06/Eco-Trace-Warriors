# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Device Intelligence Engine (DIE) — production image
#
# Multi-stage, slim Python base, non-root runtime user and a container
# healthcheck hitting /health. Only the core runtime dependencies are
# installed; heavy model packages are added in a later milestone via
# requirements-models.txt.
# ---------------------------------------------------------------------------

FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /wheels

# Build wheels for the core dependencies so the final stage installs fast
# and without a compiler toolchain.
COPY requirements.txt .
RUN pip wheel --wheel-dir /wheels -r requirements.txt


FROM python:3.12-slim AS runtime

# --- Runtime environment ---
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HOST=0.0.0.0 \
    PORT=8100 \
    MODEL_DIR=/app/models \
    UPLOAD_DIR=/app/uploads \
    ARTIFACT_DIR=/app/artifacts \
    MLRUNS_DIR=/app/mlruns \
    EXPERIMENT_TRACKER=json \
    LOG_LEVEL=INFO

# curl is used by the container healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# --- Non-root user ---
RUN groupadd --system appgroup \
    && useradd --system --gid appgroup --create-home --home-dir /home/appuser appuser

WORKDIR /app

# Install pre-built wheels from the builder stage.
COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

# Detector runtime: torch/ultralytics back the real YOLO detector. Installed
# from the index rather than the wheelhouse above, which holds only the core
# dependencies. Without these the service finds no usable backend and serves
# the deterministic mock detector regardless of the checkpoint provisioned
# under MODEL_DIR.
#
# ultralytics depends on the GUI build of opencv-python, which overwrites the
# headless `cv2` and then fails to import against this slim base (no libxcb).
# Both builds expose the same API, so drop the GUI one and restore the pinned
# headless build last. The constraint keeps that pin in requirements-detector.txt
# rather than duplicating it here.
COPY requirements-detector.txt .
RUN pip install -r requirements-detector.txt \
    && pip uninstall -y opencv-python \
    && pip install --force-reinstall --no-deps \
       -c requirements-detector.txt opencv-python-headless

# Copy the application package into an importable location.
# The service is imported as `device_ai.app:app`.
COPY . /app/device_ai

# Ensure writable runtime directories exist and are owned by the app user.
# `artifacts` holds training checkpoints/exports/reports and `mlruns` holds
# experiment-tracking runs (milestone M1.3).
RUN mkdir -p /app/models /app/uploads /app/artifacts /app/mlruns \
    && chown -R appuser:appgroup /app

USER appuser

EXPOSE 8100

# Container healthcheck — fails the container if /health is unreachable.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl --fail http://localhost:8100/health || exit 1

# `device_ai` is a top-level package on /app (which is the WORKDIR and on
# sys.path), so `device_ai.app:app` resolves correctly.
CMD ["uvicorn", "device_ai.app:app", "--host", "0.0.0.0", "--port", "8100"]
