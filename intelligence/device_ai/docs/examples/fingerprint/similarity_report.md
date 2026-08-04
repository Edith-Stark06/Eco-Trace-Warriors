# Fingerprint Similarity Evaluation Report

> Illustrative, byte-stable report generated from the deterministic `MockEmbeddingEncoder` (no real CLIP model executed). Regenerate with `python -m device_ai.scripts.gen_fingerprint_examples`.

- **Generated at:** 2026-08-01T12:00:00+00:00
- **Encoder:** clip (mock-clip-1.0.0), dimension 512
- **Default metric:** cosine
- **Match threshold:** 0.85
- **Devices:** laptop_dell, phone_apple, tablet_samsung

## Metric: `cosine`

- Intra-device similarity (same image): **1.0**
- Max inter-device similarity: **0.516686**
- Min inter-device similarity: **0.483186**

| device | laptop_dell | phone_apple | tablet_samsung |
|---|---|---|---|
| **laptop_dell** | 1.0000 | 0.5078 | 0.4832 |
| **phone_apple** | 0.5078 | 1.0000 | 0.5167 |
| **tablet_samsung** | 0.4832 | 0.5167 | 1.0000 |

## Metric: `euclidean`

- Intra-device similarity (same image): **1.0**
- Max inter-device similarity: **0.418337**
- Min inter-device similarity: **0.410207**

| device | laptop_dell | phone_apple | tablet_samsung |
|---|---|---|---|
| **laptop_dell** | 1.0000 | 0.4161 | 0.4102 |
| **phone_apple** | 0.4161 | 1.0000 | 0.4183 |
| **tablet_samsung** | 0.4102 | 0.4183 | 1.0000 |

## Metric: `manhattan`

- Intra-device similarity (same image): **1.0**
- Max inter-device similarity: **0.037593**
- Min inter-device similarity: **0.036366**

| device | laptop_dell | phone_apple | tablet_samsung |
|---|---|---|---|
| **laptop_dell** | 1.0000 | 0.0375 | 0.0364 |
| **phone_apple** | 0.0375 | 1.0000 | 0.0376 |
| **tablet_samsung** | 0.0364 | 0.0376 | 1.0000 |

