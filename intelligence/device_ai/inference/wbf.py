"""Weighted Box Fusion (WBF) algorithm for multi-model ensemble inference.

Extracted from the validated P4.13 evaluation suite
(:file:`dataset_acquisition/evaluation/p4_13_tta_ensemble_v1/_tooling/evaluate_p413_complete.py`)
and modularised for production use.  The algorithm is **unchanged** from the
research implementation that achieved the best-in-class OOD mAP50 = 0.3381
(E4_EnsTTA_50_50 configuration).

WBF merges overlapping detections from multiple models by computing a
weighted average of box coordinates and a rescaled confidence score,
producing cleaner bounding boxes than simple NMS.

References
----------
- Solovyev, Kalinin, Golber (2021). *Weighted Boxes Fusion: Ensembling
  Boxes from Different Object Detection Models*. Image and Vision Computing.
"""

from __future__ import annotations

import numpy as np


def box_iou(b1: np.ndarray, b2: np.ndarray) -> np.ndarray:
    """Compute the IoU matrix between two sets of boxes.

    Args:
        b1: Array of shape ``(N, 4)`` in ``(x1, y1, x2, y2)`` format.
        b2: Array of shape ``(M, 4)`` in ``(x1, y1, x2, y2)`` format.

    Returns:
        An ``(N, M)`` IoU matrix.
    """
    if len(b1) == 0 or len(b2) == 0:
        return np.zeros((len(b1), len(b2)), dtype=np.float32)

    x1 = np.maximum(b1[:, 0:1], b2[:, 0:1].T)
    y1 = np.maximum(b1[:, 1:2], b2[:, 1:2].T)
    x2 = np.minimum(b1[:, 2:3], b2[:, 2:3].T)
    y2 = np.minimum(b1[:, 3:4], b2[:, 3:4].T)

    inter = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
    a1 = (b1[:, 2] - b1[:, 0]) * (b1[:, 3] - b1[:, 1])
    a2 = (b2[:, 2] - b2[:, 0]) * (b2[:, 3] - b2[:, 1])
    union = a1[:, None] + a2[None, :] - inter
    return np.where(union > 0, inter / union, 0.0).astype(np.float32)


def weighted_box_fusion(
    boxes_list: list[np.ndarray],
    scores_list: list[np.ndarray],
    labels_list: list[np.ndarray],
    weights: list[float],
    iou_thr: float = 0.55,
    skip_box_thr: float = 0.001,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Fuse detections from multiple models using Weighted Box Fusion.

    All boxes are expected in **normalised** ``(x1, y1, x2, y2)`` coordinates
    (range ``[0, 1]``).

    Args:
        boxes_list: Per-model arrays of shape ``(N_i, 4)``.
        scores_list: Per-model confidence arrays of shape ``(N_i,)``.
        labels_list: Per-model class-index arrays of shape ``(N_i,)``.
        weights: Per-model fusion weights (higher = more influence).
        iou_thr: IoU threshold for clustering overlapping detections.
        skip_box_thr: Minimum score to consider a detection.

    Returns:
        A tuple of ``(fused_boxes, fused_scores, fused_labels)`` where:
        - ``fused_boxes`` has shape ``(K, 4)`` in normalised coordinates.
        - ``fused_scores`` has shape ``(K,)``.
        - ``fused_labels`` has shape ``(K,)`` with integer class indices.
    """
    total_models = len(boxes_list)
    sum_weights = sum(weights)

    out_boxes: list[np.ndarray] = []
    out_scores: list[float] = []
    out_labels: list[int] = []

    # Collect all unique class IDs across models.
    all_classes: set[int] = set()
    for l_arr in labels_list:
        if len(l_arr) > 0:
            all_classes.update(l_arr.tolist())

    for cls_id in all_classes:
        cls_boxes: list[np.ndarray] = []
        cls_scores: list[np.ndarray] = []
        cls_model_idx: list[np.ndarray] = []

        for m_idx in range(total_models):
            if len(boxes_list[m_idx]) == 0:
                continue
            mask = (labels_list[m_idx] == cls_id) & (
                scores_list[m_idx] >= skip_box_thr
            )
            b = boxes_list[m_idx][mask]
            s = scores_list[m_idx][mask]
            if len(b) > 0:
                cls_boxes.append(b)
                cls_scores.append(s)
                cls_model_idx.append(np.full(len(b), m_idx, dtype=int))

        if not cls_boxes:
            continue

        all_boxes = np.concatenate(cls_boxes, axis=0)
        all_scores = np.concatenate(cls_scores, axis=0)
        all_model_idx = np.concatenate(cls_model_idx, axis=0)

        # Sort descending by score.
        order = np.argsort(-all_scores)
        all_boxes = all_boxes[order]
        all_scores = all_scores[order]
        all_model_idx = all_model_idx[order]

        # Greedy clustering: assign each detection to the best-matching
        # existing cluster or start a new one.
        clusters: list[dict[str, list]] = []

        for b, s, m in zip(all_boxes, all_scores, all_model_idx):
            w = weights[int(m)]
            best_iou = 0.0
            best_c_idx = -1

            for c_idx, cluster in enumerate(clusters):
                c_boxes = np.array(cluster["boxes"])
                c_weights = np.array(cluster["weights"])
                c_scores = np.array(cluster["scores"])
                weighted_sum = (c_weights * c_scores)[:, None]
                c_box = np.sum(c_boxes * weighted_sum, axis=0) / np.sum(
                    c_weights * c_scores
                )

                iou = box_iou(b[None, :], c_box[None, :])[0, 0]
                if iou >= iou_thr and iou > best_iou:
                    best_iou = iou
                    best_c_idx = c_idx

            if best_c_idx >= 0:
                clusters[best_c_idx]["boxes"].append(b)
                clusters[best_c_idx]["scores"].append(float(s))
                clusters[best_c_idx]["weights"].append(float(w))
            else:
                clusters.append(
                    {
                        "boxes": [b],
                        "scores": [float(s)],
                        "weights": [float(w)],
                    }
                )

        # Compute the fused box and score for each cluster.
        for cluster in clusters:
            c_boxes = np.array(cluster["boxes"])
            c_weights = np.array(cluster["weights"])
            c_scores = np.array(cluster["scores"])

            weighted_sum = (c_weights * c_scores)[:, None]
            weighted_box = np.sum(c_boxes * weighted_sum, axis=0) / np.sum(
                c_weights * c_scores
            )

            # Confidence rescaled by total model weight coverage.
            weighted_score = float(np.sum(c_weights * c_scores) / sum_weights)

            out_boxes.append(weighted_box)
            out_scores.append(weighted_score)
            out_labels.append(int(cls_id))

    if not out_boxes:
        return (
            np.empty((0, 4), dtype=np.float32),
            np.empty((0,), dtype=np.float32),
            np.empty((0,), dtype=int),
        )

    return (
        np.array(out_boxes, dtype=np.float32),
        np.array(out_scores, dtype=np.float32),
        np.array(out_labels, dtype=int),
    )
