"""Real visual encoder backed by OpenCLIP (milestone M1.5).

:class:`CLIPEncoder` implements the existing
:class:`~device_ai.inference.predictor.EmbeddingEncoder` contract with a real
`open-clip-torch <https://github.com/mlfoundations/open_clip>`_ model, so the
fingerprinting engine gets genuine semantic embeddings while the rest of the
service (and the ``/predict`` contract) is untouched — wiring it in is a
dependency-injection concern only.

Design, consistent with the M1.4 detector adapter:

* **Optional backend, honest degradation.** ``open-clip-torch``/``torch`` are
  heavy, optional dependencies (``requirements-models.txt``). Their import is
  guarded; in the base environment (or when no artifact resolves) the encoder
  is simply *not ready* and never fabricates an embedding.
* **Everything injectable.** The per-image encode step is injectable
  (``encode_fn``) so the pooling/normalization logic is unit-testable with a
  tiny fake — no weights, no torch, no GPU.
* **No hardcoded paths.** The weights location is resolved from configuration
  by the caller (see :func:`device_ai.api.dependencies.get_fingerprint_encoder`)
  and injected.

The OpenCLIP-present code paths (importing the backend and running a real
model) are marked ``# pragma: no cover``: no backend is installed in the test
environment, so they never run there. The pooling/normalization and the
not-ready guard are covered via an injected fake ``encode_fn``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from loguru import logger

from ..exceptions import EncoderNotReadyError
from ..preprocessing.image_loader import LoadedImage
from .predictor import EmbeddingEncoder, EmbeddingVector, l2_normalize

#: Per-image raw embeddings returned by the backend/fake (one row per image).
RawEmbeddings = Sequence[Sequence[float]]

#: Callable that maps a batch of images to their raw per-image embeddings.
EncodeFn = Callable[[list[LoadedImage]], Any]

#: Artifact file names tried, in order, when ``weights_path`` is a directory.
_WEIGHTS_CANDIDATES: tuple[str, ...] = ("open_clip_pytorch_model.bin", "model.pt")


def _import_open_clip() -> Any | None:
    """Return the ``open_clip`` module, or ``None`` when unavailable."""
    try:  # pragma: no cover - open-clip-torch is not installed in the base env
        import open_clip
    except ImportError:
        return None
    return open_clip  # pragma: no cover


def _import_torch() -> Any | None:
    """Return the ``torch`` module, or ``None`` when unavailable."""
    try:  # pragma: no cover - torch is not installed in the base env
        import torch
    except ImportError:
        return None
    return torch  # pragma: no cover


def _as_list(value: Any) -> list[Any]:
    """Normalise a tensor/array/sequence into a plain list.

    Torch tensors expose ``tolist``; test fakes pass plain nested lists. Both
    are handled without importing torch.

    Args:
        value: A tensor, array or sequence.

    Returns:
        A plain Python list of the values.
    """
    to_list = getattr(value, "tolist", None)
    if callable(to_list):
        result: list[Any] = to_list()
        return result
    return list(value)


class CLIPEncoder(EmbeddingEncoder):
    """OpenCLIP-backed implementation of the :class:`EmbeddingEncoder` contract.

    The encoder runs CLIP image encoding over the batch, mean-pools the
    per-image embeddings into a single vector and L2-normalizes it — the same
    single-vector-per-request shape the mock encoder produces, so fingerprints
    are comparable across the mock → real transition.

    Args:
        weights_path: Location of the model artifact. May point directly at a
            checkpoint file, or at a directory containing a known artifact file
            name. When it does not resolve, the configured ``pretrained`` tag is
            used instead (which the real backend would download). Ignored when
            ``encode_fn`` is supplied.
        model_name: OpenCLIP architecture name (e.g. ``"ViT-B-32"``).
        pretrained: OpenCLIP pretrained-weights tag used when no local artifact
            resolves.
        dimension: Expected embedding dimensionality (used only for the
            defensive empty-batch fallback).
        device: Optional torch device string (e.g. ``"cuda"``); ``None`` keeps
            the model on its default device.
        encode_fn: Optional injected per-batch encode callable returning raw
            per-image embeddings. When given, the backend is not loaded and the
            encoder is immediately ready (used by tests).
    """

    name = "clip"

    def __init__(
        self,
        *,
        weights_path: Path | None = None,
        model_name: str = "ViT-B-32",
        pretrained: str = "laion2b_s34b_b79k",
        dimension: int = 512,
        device: str | None = None,
        encode_fn: EncodeFn | None = None,
    ) -> None:
        self._weights_path = weights_path
        self._model_name = model_name
        self._pretrained = pretrained
        self._dimension = dimension
        self._device = device
        self.version = f"openclip-{model_name.lower()}-1.0.0"
        if encode_fn is not None:
            self._encode_fn: EncodeFn | None = encode_fn
        else:
            self._encode_fn = self._build_backend(weights_path)

    # -- Readiness --------------------------------------------------------

    @property
    def is_ready(self) -> bool:
        """Whether a backend/encode function is loaded and can serve."""
        return self._encode_fn is not None

    # -- Loading ----------------------------------------------------------

    @staticmethod
    def _resolve_weights(weights_path: Path | None) -> Path | None:
        """Resolve ``weights_path`` to a concrete artifact file, if present.

        Args:
            weights_path: A file path, a directory to search, or ``None``.

        Returns:
            The resolved artifact file path, or ``None`` when nothing exists.
        """
        if weights_path is None:
            return None
        if weights_path.is_file():
            return weights_path
        if weights_path.is_dir():
            for candidate_name in _WEIGHTS_CANDIDATES:
                candidate = weights_path / candidate_name
                if candidate.is_file():
                    return candidate
        return None

    def _build_backend(self, weights_path: Path | None) -> EncodeFn | None:
        """Build the OpenCLIP encode function, degrading honestly.

        Returns ``None`` (leaving the encoder not-ready) when the backend is
        not installed or the model cannot be constructed — never raising, so
        the caller can fall back to the mock encoder.

        Args:
            weights_path: File or directory locating the model artifact.

        Returns:
            A per-batch encode callable, or ``None`` on any failure.
        """
        open_clip = _import_open_clip()
        torch = _import_torch()
        if open_clip is None or torch is None:
            logger.warning(
                "open-clip-torch/torch not installed; CLIP encoder not loaded."
            )
            return None
        return self._load_model(open_clip, torch, weights_path)  # pragma: no cover

    def _load_model(  # pragma: no cover - requires optional open-clip/torch
        self,
        open_clip: Any,
        torch: Any,
        weights_path: Path | None,
    ) -> EncodeFn | None:
        """Construct the real OpenCLIP model and return an encode closure.

        Args:
            open_clip: The imported ``open_clip`` module.
            torch: The imported ``torch`` module.
            weights_path: File or directory locating a local artifact, if any.

        Returns:
            A per-batch encode callable, or ``None`` when construction fails.
        """
        resolved = self._resolve_weights(weights_path)
        pretrained = str(resolved) if resolved is not None else self._pretrained
        try:
            model, _, preprocess = open_clip.create_model_and_transforms(
                self._model_name, pretrained=pretrained
            )
            model.eval()
            if self._device:
                model = model.to(self._device)
        except Exception as exc:  # noqa: BLE001 - degrade to mock on any error
            logger.warning("Failed to load OpenCLIP model: {}", exc)
            return None
        logger.info(
            "Loaded OpenCLIP encoder '{}' (pretrained='{}').",
            self._model_name,
            pretrained,
        )

        def encode(images: list[LoadedImage]) -> Any:
            batch = torch.stack([preprocess(img.image) for img in images])
            if self._device:
                batch = batch.to(self._device)
            with torch.no_grad():
                features = model.encode_image(batch)
            return features.cpu()

        return encode

    # -- Inference --------------------------------------------------------

    def embed(self, images: list[LoadedImage]) -> EmbeddingVector:
        """Return the L2-normalized, batch-pooled CLIP embedding for a batch.

        Args:
            images: Validated, decoded images for a single request.

        Returns:
            A unit-length :class:`EmbeddingVector`.

        Raises:
            EncoderNotReadyError: If no backend is loaded (``is_ready`` False).
        """
        if self._encode_fn is None:
            raise EncoderNotReadyError(
                "OpenCLIP encoder has no model loaded.",
                details={"weights_path": str(self._weights_path)},
            )
        raw = self._encode_fn(images)
        return self._aggregate(raw)

    def _aggregate(self, raw: Any) -> EmbeddingVector:
        """Mean-pool per-image embeddings and L2-normalize the result.

        Args:
            raw: Per-image raw embeddings (a tensor or nested sequence).

        Returns:
            A unit-length :class:`EmbeddingVector`.
        """
        matrix = [[float(value) for value in _as_list(row)] for row in _as_list(raw)]
        if not matrix:
            zeros = tuple(0.0 for _ in range(self._dimension))
            return EmbeddingVector(
                values=zeros, dimension=self._dimension, normalized=True
            )
        dimension = len(matrix[0])
        pooled = tuple(
            sum(row[index] for row in matrix) / len(matrix)
            for index in range(dimension)
        )
        normalized = l2_normalize(pooled)
        return EmbeddingVector(
            values=normalized, dimension=len(normalized), normalized=True
        )
