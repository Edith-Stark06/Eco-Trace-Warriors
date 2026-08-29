# P4.6 Class-Balanced Loss Ablation Training Plan

## Experiment Goal
Isolate the effect of class-balanced loss on model performance while keeping all other training parameters identical to P4.4.2.

## Class Distribution (P4.4.2 Training)
- laptop: 179
- smartphone: 176
- tablet: 19
- monitor: 52
- printer: 19
- mouse: 25
- camera: 157
- headphones: 360

## Weighting Strategy
Using Effective Number of Samples (Cui et al., 2019) with β = 0.9999:
- Formula: w_i = (1-β) / (1-β^n_i) where n_i is sample count for class i
- Normalized so that mean weight = 1

Calculated weights:
- laptop: 0.2433
- smartphone: 0.2475
- tablet: 2.2743
- monitor: 0.8324
- printer: 2.2743
- mouse: 1.7290
- camera: 0.2771
- headphones: 0.1221

## Implementation Approach
Ultralytics v8.4.118 supports native class weighting through the `model.class_weights` attribute.
The v8DetectionLoss automatically uses these weights if present in the model.

## Changes from P4.4.2 Trainer
1. Added class weight calculation and assignment before training
2. All other parameters kept identical:
   - epochs=50
   - imgsz=512
   - batch=8
   - device=cpu
   - workers=0
   - seed=42
   - optimizer=AdamW(auto)
   - augmentation parameters
   - dataset (byte-identical copy)
   - model architecture (yolo11n.pt)

## Evaluation Plan
1. Train P4.6 model for 50 epochs
2. Evaluate best checkpoint on:
   - P4.4.2 validation set
   - P4.4.2 test set
   - P4.5 real-world evaluation set (if above succeed)
3. Compare with P4.4.2 baseline

## Data Safety
- P4.6 uses byte-identical copy of P4.4.2 dataset_working
- No modifications to original P4.4.0, P4.4.1, P4.4.2, P4.4.3, or P4.5 data
- Model checkpoints stored in separate P4.6 directory
