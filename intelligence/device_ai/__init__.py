"""Device Intelligence Engine (DIE).

An independent, production-grade AI microservice for the EcoTrace India
platform. It exposes REST APIs consumed by the Express backend and is
responsible for turning device images into structured intelligence
(device type, brand, condition, recoverable materials, carbon score).

This package deliberately ships *pluggable interfaces* and *mock*
implementations for milestone M1.1; real models (YOLO, CLIP, condition,
OCR) are integrated later behind the same interfaces without changing the
service surface.
"""

from __future__ import annotations

__all__ = ["__version__"]

# Semantic version of the service/API contract. Kept in one place so the
# /version endpoint, response payloads and Docker image all agree.
__version__: str = "1.0.0"
