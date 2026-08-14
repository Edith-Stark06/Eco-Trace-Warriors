# P4.3.6 Expansion — Human Visual-QA Sign-off Package

- Package: `p4-3-6-expansion-human-qa-v1`
- Sprint: P4.3.6
- Source: Open Images V7 (OIDv4_ToolKit)
- Taxonomy version: 1.0.0
- QA status: **QA_PENDING** (nothing auto-accepted; awaiting human decision)
- Total items: 119

## Class mappings

| Source class | Canonical class | Class id | Items |
| --- | --- | --- | --- |
| Laptop | laptop | 0 | 20 |
| Television | television | 7 | 19 |
| Computer keyboard | keyboard | 9 | 20 |
| Computer mouse | mouse | 10 | 20 |
| Camera | camera | 14 | 20 |
| Headphones | headphones | 17 | 20 |

## Removed before QA (frozen DuplicateDetector, threshold 5)

These verified-source samples converted cleanly but are near-duplicates of images already in the p4_3_5 clean candidate, so they were excluded from this package. Source staging was NOT modified.

| Canonical class | Dropped file | Reason |
| --- | --- | --- |
| laptop | `f663d03a10e841bf.jpg` | near-duplicate (min Hamming=1, aHash) of candidate/tablet/d4285391c9dbfbe8.jpg |
| television | `34932ec3bf06d3ef.jpg` | near-duplicate (min Hamming=5) of candidate/tablet/293b420b3319821c.jpg |

## How to review

1. Open each class contact sheet: `camera/contact_sheet.jpg`, `headphones/contact_sheet.jpg`, `keyboard/contact_sheet.jpg`, `laptop/contact_sheet.jpg`, `mouse/contact_sheet.jpg`, `television/contact_sheet.jpg`.
2. Confirm every green box tightly bounds the correct device.
3. Record a decision per item in `signoff_template.json` (`status` -> `QA_ACCEPTED` or `QA_REJECTED`, plus `reviewer`/`review_date`).
4. Only `QA_ACCEPTED` items are eligible for merge into the next candidate.

## Items

| # | Class | File | Boxes | WxH | Blurry | Preview | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | laptop | `00767fb6565581c6.jpg` | 1 | 768x1024 | yes | `laptop/previews/qa01_00767fb6565581c6.jpg` | QA_PENDING |
| 2 | laptop | `00b1a3014b6d62a1.jpg` | 2 | 1024x768 | no | `laptop/previews/qa02_00b1a3014b6d62a1.jpg` | QA_PENDING |
| 3 | laptop | `0171ad35f1651698.jpg` | 1 | 1024x768 | no | `laptop/previews/qa03_0171ad35f1651698.jpg` | QA_PENDING |
| 4 | laptop | `14587a599414300c.jpg` | 5 | 1024x683 | no | `laptop/previews/qa04_14587a599414300c.jpg` | QA_PENDING |
| 5 | laptop | `190cc7b67a9c450c.jpg` | 1 | 1024x680 | no | `laptop/previews/qa05_190cc7b67a9c450c.jpg` | QA_PENDING |
| 6 | laptop | `1f2c4a9277907198.jpg` | 3 | 1024x683 | no | `laptop/previews/qa06_1f2c4a9277907198.jpg` | QA_PENDING |
| 7 | laptop | `29cad80c5bb8ef66.jpg` | 1 | 1024x768 | no | `laptop/previews/qa07_29cad80c5bb8ef66.jpg` | QA_PENDING |
| 8 | laptop | `350358911f3842de.jpg` | 1 | 1024x768 | no | `laptop/previews/qa08_350358911f3842de.jpg` | QA_PENDING |
| 9 | laptop | `38eff60d1aefddf3.jpg` | 2 | 1024x768 | no | `laptop/previews/qa09_38eff60d1aefddf3.jpg` | QA_PENDING |
| 10 | laptop | `4642b8dade65b547.jpg` | 5 | 1024x683 | no | `laptop/previews/qa10_4642b8dade65b547.jpg` | QA_PENDING |
| 11 | laptop | `4f9e2b95c779cb86.jpg` | 1 | 1024x683 | no | `laptop/previews/qa11_4f9e2b95c779cb86.jpg` | QA_PENDING |
| 12 | laptop | `52ebe809668cd8fb.jpg` | 1 | 679x1024 | no | `laptop/previews/qa12_52ebe809668cd8fb.jpg` | QA_PENDING |
| 13 | laptop | `7323935a99cd80c5.jpg` | 1 | 1024x683 | no | `laptop/previews/qa13_7323935a99cd80c5.jpg` | QA_PENDING |
| 14 | laptop | `79182035199f2b58.jpg` | 1 | 1024x1024 | yes | `laptop/previews/qa14_79182035199f2b58.jpg` | QA_PENDING |
| 15 | laptop | `936a6d462e9d4873.jpg` | 1 | 1024x768 | no | `laptop/previews/qa15_936a6d462e9d4873.jpg` | QA_PENDING |
| 16 | laptop | `ac7e045453c729aa.jpg` | 1 | 1024x768 | no | `laptop/previews/qa16_ac7e045453c729aa.jpg` | QA_PENDING |
| 17 | laptop | `bc3873e0c9ada07c.jpg` | 1 | 1024x768 | yes | `laptop/previews/qa17_bc3873e0c9ada07c.jpg` | QA_PENDING |
| 18 | laptop | `ca77666f682b922f.jpg` | 1 | 1024x680 | yes | `laptop/previews/qa18_ca77666f682b922f.jpg` | QA_PENDING |
| 19 | laptop | `d07df89600fdda6f.jpg` | 1 | 1024x683 | no | `laptop/previews/qa19_d07df89600fdda6f.jpg` | QA_PENDING |
| 20 | laptop | `e850cbfc139cbf51.jpg` | 3 | 768x1024 | no | `laptop/previews/qa20_e850cbfc139cbf51.jpg` | QA_PENDING |
| 21 | television | `07defa25281b15c4.jpg` | 1 | 1024x681 | yes | `television/previews/qa01_07defa25281b15c4.jpg` | QA_PENDING |
| 22 | television | `0ac854a215464b09.jpg` | 1 | 1024x768 | yes | `television/previews/qa02_0ac854a215464b09.jpg` | QA_PENDING |
| 23 | television | `0b35c0ed157b4ca4.jpg` | 1 | 1024x768 | no | `television/previews/qa03_0b35c0ed157b4ca4.jpg` | QA_PENDING |
| 24 | television | `0c62dcc3e2acf40f.jpg` | 4 | 1024x1024 | yes | `television/previews/qa04_0c62dcc3e2acf40f.jpg` | QA_PENDING |
| 25 | television | `0ffb3c07045c167a.jpg` | 2 | 1024x765 | no | `television/previews/qa05_0ffb3c07045c167a.jpg` | QA_PENDING |
| 26 | television | `106a464c1209d3a6.jpg` | 1 | 1024x768 | no | `television/previews/qa06_106a464c1209d3a6.jpg` | QA_PENDING |
| 27 | television | `2c9b26ec123bdccd.jpg` | 5 | 1024x768 | no | `television/previews/qa07_2c9b26ec123bdccd.jpg` | QA_PENDING |
| 28 | television | `3b515a2960c79812.jpg` | 1 | 1024x768 | no | `television/previews/qa08_3b515a2960c79812.jpg` | QA_PENDING |
| 29 | television | `4aa44871b9b6585e.jpg` | 1 | 1024x768 | no | `television/previews/qa09_4aa44871b9b6585e.jpg` | QA_PENDING |
| 30 | television | `563d755665772681.jpg` | 1 | 1024x810 | yes | `television/previews/qa10_563d755665772681.jpg` | QA_PENDING |
| 31 | television | `678d0f6b7ada3d1f.jpg` | 1 | 1024x683 | no | `television/previews/qa11_678d0f6b7ada3d1f.jpg` | QA_PENDING |
| 32 | television | `76eb9c86052909bc.jpg` | 1 | 768x1024 | no | `television/previews/qa12_76eb9c86052909bc.jpg` | QA_PENDING |
| 33 | television | `95a12fd157c6502e.jpg` | 1 | 1024x768 | no | `television/previews/qa13_95a12fd157c6502e.jpg` | QA_PENDING |
| 34 | television | `9e9612ea86fa4982.jpg` | 10 | 683x1024 | no | `television/previews/qa14_9e9612ea86fa4982.jpg` | QA_PENDING |
| 35 | television | `a3176a302f865f19.jpg` | 1 | 683x1024 | no | `television/previews/qa15_a3176a302f865f19.jpg` | QA_PENDING |
| 36 | television | `a51101ec8f1ddb8b.jpg` | 1 | 1024x678 | no | `television/previews/qa16_a51101ec8f1ddb8b.jpg` | QA_PENDING |
| 37 | television | `e99a5edb33322253.jpg` | 1 | 1024x683 | no | `television/previews/qa17_e99a5edb33322253.jpg` | QA_PENDING |
| 38 | television | `f155f857d552e57b.jpg` | 1 | 1024x768 | no | `television/previews/qa18_f155f857d552e57b.jpg` | QA_PENDING |
| 39 | television | `fc800bbdaad28067.jpg` | 9 | 1024x1024 | no | `television/previews/qa19_fc800bbdaad28067.jpg` | QA_PENDING |
| 40 | keyboard | `00f186cc78e9d697.jpg` | 1 | 1024x768 | no | `keyboard/previews/qa01_00f186cc78e9d697.jpg` | QA_PENDING |
| 41 | keyboard | `0b5ef17e3c01ac99.jpg` | 2 | 1024x768 | yes | `keyboard/previews/qa02_0b5ef17e3c01ac99.jpg` | QA_PENDING |
| 42 | keyboard | `21140251f6675d3a.jpg` | 1 | 1024x683 | no | `keyboard/previews/qa03_21140251f6675d3a.jpg` | QA_PENDING |
| 43 | keyboard | `2398cc31dbb29d35.jpg` | 1 | 1024x768 | no | `keyboard/previews/qa04_2398cc31dbb29d35.jpg` | QA_PENDING |
| 44 | keyboard | `2ce393f639aafea7.jpg` | 1 | 1024x768 | no | `keyboard/previews/qa05_2ce393f639aafea7.jpg` | QA_PENDING |
| 45 | keyboard | `362e1ab5cb798298.jpg` | 1 | 1024x683 | no | `keyboard/previews/qa06_362e1ab5cb798298.jpg` | QA_PENDING |
| 46 | keyboard | `3964b8d7456c0cc8.jpg` | 2 | 1024x768 | no | `keyboard/previews/qa07_3964b8d7456c0cc8.jpg` | QA_PENDING |
| 47 | keyboard | `53081e7dd2a033dc.jpg` | 1 | 1024x1024 | no | `keyboard/previews/qa08_53081e7dd2a033dc.jpg` | QA_PENDING |
| 48 | keyboard | `55d6ba1a035196d6.jpg` | 1 | 1024x1024 | yes | `keyboard/previews/qa09_55d6ba1a035196d6.jpg` | QA_PENDING |
| 49 | keyboard | `6e503380ea195c1c.jpg` | 2 | 1024x768 | no | `keyboard/previews/qa10_6e503380ea195c1c.jpg` | QA_PENDING |
| 50 | keyboard | `72ea3c2746f8a103.jpg` | 1 | 1024x768 | no | `keyboard/previews/qa11_72ea3c2746f8a103.jpg` | QA_PENDING |
| 51 | keyboard | `8b1dfd2843af36d8.jpg` | 1 | 1024x768 | no | `keyboard/previews/qa12_8b1dfd2843af36d8.jpg` | QA_PENDING |
| 52 | keyboard | `8f786b29df7a337a.jpg` | 1 | 1024x704 | no | `keyboard/previews/qa13_8f786b29df7a337a.jpg` | QA_PENDING |
| 53 | keyboard | `9a9944579aca4507.jpg` | 1 | 1024x683 | no | `keyboard/previews/qa14_9a9944579aca4507.jpg` | QA_PENDING |
| 54 | keyboard | `9ff5c43ad942f775.jpg` | 1 | 1024x742 | no | `keyboard/previews/qa15_9ff5c43ad942f775.jpg` | QA_PENDING |
| 55 | keyboard | `aa6e96626e55c21e.jpg` | 1 | 1024x768 | no | `keyboard/previews/qa16_aa6e96626e55c21e.jpg` | QA_PENDING |
| 56 | keyboard | `acaf2a8ebc3415c7.jpg` | 1 | 1024x683 | no | `keyboard/previews/qa17_acaf2a8ebc3415c7.jpg` | QA_PENDING |
| 57 | keyboard | `acf24a6b0b601675.jpg` | 1 | 1024x683 | yes | `keyboard/previews/qa18_acf24a6b0b601675.jpg` | QA_PENDING |
| 58 | keyboard | `d7600d60f635288b.jpg` | 1 | 1024x768 | no | `keyboard/previews/qa19_d7600d60f635288b.jpg` | QA_PENDING |
| 59 | keyboard | `e5a32c0baa07ab72.jpg` | 2 | 1024x683 | no | `keyboard/previews/qa20_e5a32c0baa07ab72.jpg` | QA_PENDING |
| 60 | mouse | `005b6a1ed4f99c55.jpg` | 1 | 1024x683 | yes | `mouse/previews/qa01_005b6a1ed4f99c55.jpg` | QA_PENDING |
| 61 | mouse | `0cdddef82583b7ba.jpg` | 1 | 1024x683 | no | `mouse/previews/qa02_0cdddef82583b7ba.jpg` | QA_PENDING |
| 62 | mouse | `0f126a8a40a3ecfc.jpg` | 1 | 768x768 | no | `mouse/previews/qa03_0f126a8a40a3ecfc.jpg` | QA_PENDING |
| 63 | mouse | `132eed56e77c3762.jpg` | 1 | 1024x680 | no | `mouse/previews/qa04_132eed56e77c3762.jpg` | QA_PENDING |
| 64 | mouse | `1975fe305200674b.jpg` | 1 | 1024x768 | yes | `mouse/previews/qa05_1975fe305200674b.jpg` | QA_PENDING |
| 65 | mouse | `1af719ca7dc88e51.jpg` | 1 | 1024x680 | no | `mouse/previews/qa06_1af719ca7dc88e51.jpg` | QA_PENDING |
| 66 | mouse | `1c7f705b5ad303af.jpg` | 1 | 1024x669 | no | `mouse/previews/qa07_1c7f705b5ad303af.jpg` | QA_PENDING |
| 67 | mouse | `284cc91d96ef8927.jpg` | 1 | 1024x768 | no | `mouse/previews/qa08_284cc91d96ef8927.jpg` | QA_PENDING |
| 68 | mouse | `2cb2705309ea4c2d.jpg` | 1 | 1024x680 | no | `mouse/previews/qa09_2cb2705309ea4c2d.jpg` | QA_PENDING |
| 69 | mouse | `324f9aab6ff2d5bb.jpg` | 1 | 1024x630 | yes | `mouse/previews/qa10_324f9aab6ff2d5bb.jpg` | QA_PENDING |
| 70 | mouse | `34c304b9dbee3e54.jpg` | 6 | 1024x1024 | no | `mouse/previews/qa11_34c304b9dbee3e54.jpg` | QA_PENDING |
| 71 | mouse | `4561a031dc3cc746.jpg` | 1 | 1024x680 | yes | `mouse/previews/qa12_4561a031dc3cc746.jpg` | QA_PENDING |
| 72 | mouse | `478c66a97e599671.jpg` | 1 | 1024x768 | no | `mouse/previews/qa13_478c66a97e599671.jpg` | QA_PENDING |
| 73 | mouse | `727f6a2497619ff9.jpg` | 1 | 1024x575 | yes | `mouse/previews/qa14_727f6a2497619ff9.jpg` | QA_PENDING |
| 74 | mouse | `78d418ca6d35157d.jpg` | 1 | 1024x768 | no | `mouse/previews/qa15_78d418ca6d35157d.jpg` | QA_PENDING |
| 75 | mouse | `a3381077de807443.jpg` | 1 | 1024x768 | no | `mouse/previews/qa16_a3381077de807443.jpg` | QA_PENDING |
| 76 | mouse | `d5da64ee9237f8ae.jpg` | 1 | 1020x768 | no | `mouse/previews/qa17_d5da64ee9237f8ae.jpg` | QA_PENDING |
| 77 | mouse | `eb14ab3441142b64.jpg` | 1 | 1024x765 | no | `mouse/previews/qa18_eb14ab3441142b64.jpg` | QA_PENDING |
| 78 | mouse | `f61fd0b27706d88b.jpg` | 1 | 1024x685 | yes | `mouse/previews/qa19_f61fd0b27706d88b.jpg` | QA_PENDING |
| 79 | mouse | `f9c6fff205ae88be.jpg` | 1 | 1024x680 | yes | `mouse/previews/qa20_f9c6fff205ae88be.jpg` | QA_PENDING |
| 80 | camera | `00ce5a5ea4837634.jpg` | 1 | 1024x678 | no | `camera/previews/qa01_00ce5a5ea4837634.jpg` | QA_PENDING |
| 81 | camera | `0ff8df5af194c762.jpg` | 1 | 1024x689 | no | `camera/previews/qa02_0ff8df5af194c762.jpg` | QA_PENDING |
| 82 | camera | `2c8aa44265ff2999.jpg` | 1 | 681x1024 | no | `camera/previews/qa03_2c8aa44265ff2999.jpg` | QA_PENDING |
| 83 | camera | `2f2d6c102b578468.jpg` | 1 | 1024x768 | no | `camera/previews/qa04_2f2d6c102b578468.jpg` | QA_PENDING |
| 84 | camera | `32cc3656bbab3e67.jpg` | 1 | 1024x680 | no | `camera/previews/qa05_32cc3656bbab3e67.jpg` | QA_PENDING |
| 85 | camera | `50ef1255ee41604a.jpg` | 1 | 1024x576 | no | `camera/previews/qa06_50ef1255ee41604a.jpg` | QA_PENDING |
| 86 | camera | `56e3fa15dd17341c.jpg` | 1 | 1024x681 | yes | `camera/previews/qa07_56e3fa15dd17341c.jpg` | QA_PENDING |
| 87 | camera | `587f0c2c8953f51a.jpg` | 1 | 1024x678 | no | `camera/previews/qa08_587f0c2c8953f51a.jpg` | QA_PENDING |
| 88 | camera | `62f04ce24af2325b.jpg` | 1 | 1024x1024 | no | `camera/previews/qa09_62f04ce24af2325b.jpg` | QA_PENDING |
| 89 | camera | `66edaca7bff99323.jpg` | 1 | 1024x683 | no | `camera/previews/qa10_66edaca7bff99323.jpg` | QA_PENDING |
| 90 | camera | `6a925f1385e2c081.jpg` | 1 | 1024x682 | no | `camera/previews/qa11_6a925f1385e2c081.jpg` | QA_PENDING |
| 91 | camera | `9a07a578de148516.jpg` | 1 | 1024x683 | no | `camera/previews/qa12_9a07a578de148516.jpg` | QA_PENDING |
| 92 | camera | `abd64befaf563521.jpg` | 2 | 1024x768 | yes | `camera/previews/qa13_abd64befaf563521.jpg` | QA_PENDING |
| 93 | camera | `c854b06cfa74390b.jpg` | 1 | 1024x711 | no | `camera/previews/qa14_c854b06cfa74390b.jpg` | QA_PENDING |
| 94 | camera | `ccf81e11ab485354.jpg` | 1 | 1024x679 | yes | `camera/previews/qa15_ccf81e11ab485354.jpg` | QA_PENDING |
| 95 | camera | `d1f4bc82f53d01e0.jpg` | 1 | 1024x682 | yes | `camera/previews/qa16_d1f4bc82f53d01e0.jpg` | QA_PENDING |
| 96 | camera | `d924533f790ccb69.jpg` | 1 | 1024x683 | no | `camera/previews/qa17_d924533f790ccb69.jpg` | QA_PENDING |
| 97 | camera | `e82e8e3dadc061ae.jpg` | 1 | 730x1024 | no | `camera/previews/qa18_e82e8e3dadc061ae.jpg` | QA_PENDING |
| 98 | camera | `f3081a1ca53f57ab.jpg` | 1 | 1024x659 | no | `camera/previews/qa19_f3081a1ca53f57ab.jpg` | QA_PENDING |
| 99 | camera | `f63214b1d0a7a840.jpg` | 1 | 1024x680 | yes | `camera/previews/qa20_f63214b1d0a7a840.jpg` | QA_PENDING |
| 100 | headphones | `0209221ebb2ecb97.jpg` | 1 | 1024x683 | no | `headphones/previews/qa01_0209221ebb2ecb97.jpg` | QA_PENDING |
| 101 | headphones | `03f5c7a11e1c343a.jpg` | 1 | 1024x685 | yes | `headphones/previews/qa02_03f5c7a11e1c343a.jpg` | QA_PENDING |
| 102 | headphones | `0737a40eb72e18f9.jpg` | 1 | 1024x680 | yes | `headphones/previews/qa03_0737a40eb72e18f9.jpg` | QA_PENDING |
| 103 | headphones | `0b46826c2cc1f5f7.jpg` | 1 | 1024x1024 | yes | `headphones/previews/qa04_0b46826c2cc1f5f7.jpg` | QA_PENDING |
| 104 | headphones | `102717fb3afc170a.jpg` | 2 | 769x1024 | yes | `headphones/previews/qa05_102717fb3afc170a.jpg` | QA_PENDING |
| 105 | headphones | `144f3db06baf3f85.jpg` | 1 | 1024x768 | yes | `headphones/previews/qa06_144f3db06baf3f85.jpg` | QA_PENDING |
| 106 | headphones | `1b48ff7f6210d390.jpg` | 1 | 1024x768 | yes | `headphones/previews/qa07_1b48ff7f6210d390.jpg` | QA_PENDING |
| 107 | headphones | `2024b40f3c27068f.jpg` | 1 | 553x1024 | no | `headphones/previews/qa08_2024b40f3c27068f.jpg` | QA_PENDING |
| 108 | headphones | `39b89b43221ae839.jpg` | 1 | 1024x575 | yes | `headphones/previews/qa09_39b89b43221ae839.jpg` | QA_PENDING |
| 109 | headphones | `3a5596c993144cda.jpg` | 1 | 683x1024 | yes | `headphones/previews/qa10_3a5596c993144cda.jpg` | QA_PENDING |
| 110 | headphones | `3c90135e0537483b.jpg` | 1 | 1024x768 | yes | `headphones/previews/qa11_3c90135e0537483b.jpg` | QA_PENDING |
| 111 | headphones | `3e5cb9dc27219731.jpg` | 3 | 678x1024 | no | `headphones/previews/qa12_3e5cb9dc27219731.jpg` | QA_PENDING |
| 112 | headphones | `570b786fa047b915.jpg` | 1 | 1024x899 | no | `headphones/previews/qa13_570b786fa047b915.jpg` | QA_PENDING |
| 113 | headphones | `6fefdcf7f72bfd09.jpg` | 2 | 576x1024 | no | `headphones/previews/qa14_6fefdcf7f72bfd09.jpg` | QA_PENDING |
| 114 | headphones | `8395ba66dcf68177.jpg` | 1 | 1024x683 | yes | `headphones/previews/qa15_8395ba66dcf68177.jpg` | QA_PENDING |
| 115 | headphones | `887d3b3f275be0c1.jpg` | 1 | 1024x678 | yes | `headphones/previews/qa16_887d3b3f275be0c1.jpg` | QA_PENDING |
| 116 | headphones | `8e8d7e8afa74811f.jpg` | 1 | 768x1024 | no | `headphones/previews/qa17_8e8d7e8afa74811f.jpg` | QA_PENDING |
| 117 | headphones | `c5de186420965532.jpg` | 2 | 1024x1024 | yes | `headphones/previews/qa18_c5de186420965532.jpg` | QA_PENDING |
| 118 | headphones | `e4e2643e4bd72ca4.jpg` | 2 | 1024x683 | yes | `headphones/previews/qa19_e4e2643e4bd72ca4.jpg` | QA_PENDING |
| 119 | headphones | `e6dabfb27f4d737c.jpg` | 1 | 1024x768 | yes | `headphones/previews/qa20_e6dabfb27f4d737c.jpg` | QA_PENDING |
