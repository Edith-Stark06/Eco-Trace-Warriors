"""Unit tests for the Weighted Box Fusion (WBF) module.

Tests coordinate IoU computation, single-box passthrough, multi-box fusion,
empty inputs, multi-class separation, and weight scaling.
"""

from __future__ import annotations

import numpy as np
import pytest

from device_ai.inference.wbf import box_iou, weighted_box_fusion


def test_box_iou_perfect_overlap() -> None:
    """IoU of identical boxes is 1.0."""
    b1 = np.array([[0.1, 0.1, 0.5, 0.5]], dtype=np.float32)
    b2 = np.array([[0.1, 0.1, 0.5, 0.5]], dtype=np.float32)
    iou = box_iou(b1, b2)
    assert iou.shape == (1, 1)
    assert pytest.approx(float(iou[0, 0]), 1e-5) == 1.0


def test_box_iou_disjoint() -> None:
    """IoU of non-overlapping boxes is 0.0."""
    b1 = np.array([[0.0, 0.0, 0.2, 0.2]], dtype=np.float32)
    b2 = np.array([[0.5, 0.5, 0.8, 0.8]], dtype=np.float32)
    iou = box_iou(b1, b2)
    assert pytest.approx(float(iou[0, 0]), 1e-5) == 0.0


def test_box_iou_empty_inputs() -> None:
    """Empty inputs produce a correctly shaped zero matrix."""
    b1 = np.empty((0, 4), dtype=np.float32)
    b2 = np.array([[0.1, 0.1, 0.5, 0.5]], dtype=np.float32)
    assert box_iou(b1, b2).shape == (0, 1)
    assert box_iou(b2, b1).shape == (1, 0)


def test_wbf_empty_inputs() -> None:
    """WBF handles empty box lists gracefully without error."""
    boxes_list = [np.empty((0, 4), dtype=np.float32), np.empty((0, 4), dtype=np.float32)]
    scores_list = [np.empty((0,), dtype=np.float32), np.empty((0,), dtype=np.float32)]
    labels_list = [np.empty((0,), dtype=int), np.empty((0,), dtype=int)]
    weights = [0.5, 0.5]

    f_boxes, f_scores, f_labels = weighted_box_fusion(
        boxes_list, scores_list, labels_list, weights
    )
    assert len(f_boxes) == 0
    assert len(f_scores) == 0
    assert len(f_labels) == 0


def test_wbf_single_model_passthrough() -> None:
    """WBF with a single model returns the original detection rescaled."""
    boxes = [np.array([[0.1, 0.1, 0.5, 0.5]], dtype=np.float32)]
    scores = [np.array([0.9], dtype=np.float32)]
    labels = [np.array([0], dtype=int)]
    weights = [1.0]

    f_boxes, f_scores, f_labels = weighted_box_fusion(
        boxes, scores, labels, weights
    )
    assert len(f_boxes) == 1
    assert pytest.approx(f_scores[0], 1e-4) == 0.9
    assert f_labels[0] == 0
    np.testing.assert_allclose(f_boxes[0], [0.1, 0.1, 0.5, 0.5], atol=1e-4)


def test_wbf_two_model_concordant_fusion() -> None:
    """Overlapping detections of the same class fuse into a weighted average."""
    # Model A: [0.1, 0.1, 0.5, 0.5], score=0.8, weight=1.0
    # Model B: [0.12, 0.12, 0.52, 0.52], score=0.8, weight=1.0
    boxes_list = [
        np.array([[0.1, 0.1, 0.5, 0.5]], dtype=np.float32),
        np.array([[0.12, 0.12, 0.52, 0.52]], dtype=np.float32),
    ]
    scores_list = [
        np.array([0.8], dtype=np.float32),
        np.array([0.8], dtype=np.float32),
    ]
    labels_list = [
        np.array([0], dtype=int),
        np.array([0], dtype=int),
    ]
    weights = [1.0, 1.0]

    f_boxes, f_scores, f_labels = weighted_box_fusion(
        boxes_list, scores_list, labels_list, weights, iou_thr=0.5
    )

    assert len(f_boxes) == 1
    assert f_labels[0] == 0
    # Weighted average should be exactly the midpoint: (0.1+0.12)/2 = 0.11, etc.
    expected_box = np.array([0.11, 0.11, 0.51, 0.51], dtype=np.float32)
    np.testing.assert_allclose(f_boxes[0], expected_box, atol=1e-4)
    # Score: (1.0*0.8 + 1.0*0.8) / 2.0 = 0.8
    assert pytest.approx(f_scores[0], 1e-4) == 0.8


def test_wbf_distinct_classes_do_not_fuse() -> None:
    """Overlapping detections of DIFFERENT classes are NOT merged."""
    boxes_list = [
        np.array([[0.1, 0.1, 0.5, 0.5]], dtype=np.float32),
        np.array([[0.1, 0.1, 0.5, 0.5]], dtype=np.float32),
    ]
    scores_list = [
        np.array([0.9], dtype=np.float32),
        np.array([0.85], dtype=np.float32),
    ]
    labels_list = [
        np.array([0], dtype=int),  # Class 0: laptop
        np.array([1], dtype=int),  # Class 1: smartphone
    ]
    weights = [0.5, 0.5]

    f_boxes, f_scores, f_labels = weighted_box_fusion(
        boxes_list, scores_list, labels_list, weights, iou_thr=0.5
    )

    assert len(f_boxes) == 2
    assert set(f_labels.tolist()) == {0, 1}
