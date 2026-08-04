# OCR Parser Evaluation Report

> Illustrative, byte-stable report generated from the deterministic mock OCR backend and parser (no real EasyOCR/OpenCV executed). Regenerate with `python -m device_ai.scripts.gen_ocr_examples`.

- **Generated at:** 2026-08-01T12:00:00+00:00
- **Engine:** ocr (mock-ocr-m16-1.0.0)
- **Cases:** 4
- **Fields evaluated:** 10
- **Overall accuracy:** 1.0
- **Mean field confidence:** 0.89092

## Per-field accuracy

| field | accuracy |
|---|---|
| `barcode` | 1.0000 |
| `imei` | 1.0000 |
| `mac_address` | 1.0000 |
| `manufacturer` | 1.0000 |
| `model` | 1.0000 |
| `qr_code` | 1.0000 |
| `serial_number` | 1.0000 |

## Cases

### `clean_label`

| field | expected | extracted | correct | confidence |
|---|---|---|---|---|
| `manufacturer` | Dell | Dell | ✅ | 0.9310 |
| `model` | XPS 15 | XPS 15 | ✅ | 0.8075 |
| `serial_number` | ABC12345 | ABC12345 | ✅ | 0.8370 |

### `imei_and_mac`

| field | expected | extracted | correct | confidence |
|---|---|---|---|---|
| `imei` | 490154203237518 | 490154203237518 | ✅ | 0.9261 |
| `mac_address` | 00:1A:2B:3C:4D:5E | 00:1A:2B:3C:4D:5E | ✅ | 0.8536 |

### `barcode_mined_serial`

| field | expected | extracted | correct | confidence |
|---|---|---|---|---|
| `manufacturer` | Lenovo | Lenovo | ✅ | 0.8740 |
| `qr_code` | SNXY98765 | SNXY98765 | ✅ | 1.0000 |
| `serial_number` | SNXY98765 | SNXY98765 | ✅ | 0.7000 |

### `barcode_mined_imei`

| field | expected | extracted | correct | confidence |
|---|---|---|---|---|
| `barcode` | 490154203237518 | 490154203237518 | ✅ | 1.0000 |
| `imei` | 490154203237518 | 490154203237518 | ✅ | 0.9800 |

