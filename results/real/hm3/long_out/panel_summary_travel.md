## travel: actor panels (cap-hit = any attempt at the output cap; pre-2026-09-19 ledgers use the summed output tokens)

### travel native, prompt v1, cap 16384

| arm | n | EES | affected F1 | value acc | hit cap | EES hit | EES not hit | legal | collateral | med in | med out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full/verbose | 64 | 0.48 | 0.87 | 0.73 | 0 | — | 0.48 | 0.91 | 0.62 | 6481 | 664 |
| graph_closed/verbose | 64 | 0.33 | 0.80 | 0.73 | 1 | 0.00 | 0.33 | 0.66 | 0.98 | 3024 | 566 |
| graph_seg/verbose | 64 | 0.48 | 0.89 | 0.70 | 0 | — | 0.48 | 0.91 | 0.53 | 3522 | 589 |
- graph_closed/verbose − full/verbose: EES -0.16 [-0.31, +0.00] n=64; affected F1 -0.08 [-0.14, -0.02] n=64; value acc -0.00 [-0.14, +0.14] n=64
- graph_seg/verbose − full/verbose: EES +0.00 [-0.16, +0.14] n=64; affected F1 +0.01 [-0.03, +0.06] n=64; value acc -0.04 [-0.17, +0.10] n=64

### travel native, prompt v2, cap 4096

| arm | n | EES | affected F1 | value acc | hit cap | EES hit | EES not hit | legal | collateral | med in | med out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full/verbose | 64 | 0.55 | 0.82 | 0.78 | 11 | 0.27 | 0.60 | 0.97 | 0.41 | 6866 | 1966 |
| graph_closed/compact | 64 | 0.22 | 0.68 | 0.47 | 8 | 0.12 | 0.23 | 0.95 | 0.42 | 1674 | 1101 |
| graph_closed/verbose | 64 | 0.36 | 0.77 | 0.56 | 5 | 0.20 | 0.37 | 0.91 | 0.45 | 3324 | 1219 |
| bm25_k16/verbose | 64 | 0.34 | 0.51 | 0.57 | 5 | 0.00 | 0.37 | 0.98 | 0.12 | 5132 | 1326 |
| graph_key2/compact | 64 | 0.36 | 0.77 | 0.63 | 8 | 0.00 | 0.41 | 0.94 | 0.55 | 2050 | 1341 |
| graph_key3/compact | 64 | 0.41 | 0.82 | 0.64 | 5 | 0.60 | 0.39 | 0.91 | 0.53 | 2112 | 1415 |
| bm25_k16/compact | 64 | 0.36 | 0.56 | 0.59 | 4 | 0.25 | 0.37 | 0.98 | 0.16 | 2148 | 1546 |
| recency_k16/compact | 64 | 0.31 | 0.57 | 0.59 | 10 | 0.20 | 0.33 | 0.97 | 0.19 | 2156 | 1896 |
- graph_closed/compact − full/verbose: EES -0.33 [-0.47, -0.19] n=64; affected F1 -0.14 [-0.26, -0.03] n=64; value acc -0.31 [-0.46, -0.17] n=64
- graph_closed/verbose − full/verbose: EES -0.19 [-0.33, -0.05] n=64; affected F1 -0.05 [-0.14, +0.04] n=64; value acc -0.22 [-0.35, -0.09] n=64
- graph_key2/compact − graph_closed/compact: EES +0.14 [-0.02, +0.30] n=64; affected F1 +0.09 [-0.03, +0.22] n=64; value acc +0.16 [-0.01, +0.32] n=64
- graph_key2/compact − full/verbose: EES -0.19 [-0.34, -0.05] n=64; affected F1 -0.05 [-0.15, +0.05] n=64; value acc -0.15 [-0.30, -0.01] n=64
- graph_key3/compact − graph_closed/compact: EES +0.19 [+0.05, +0.33] n=64; affected F1 +0.14 [+0.04, +0.24] n=64; value acc +0.17 [+0.04, +0.30] n=64
- bm25_k16/compact − full/verbose: EES -0.19 [-0.33, -0.05] n=64; affected F1 -0.26 [-0.38, -0.15] n=64; value acc -0.19 [-0.33, -0.05] n=64
- recency_k16/compact − full/verbose: EES -0.23 [-0.38, -0.09] n=64; affected F1 -0.25 [-0.37, -0.14] n=64; value acc -0.19 [-0.33, -0.05] n=64

### travel native, prompt v2, cap 16384

| arm | n | EES | affected F1 | value acc | hit cap | EES hit | EES not hit | legal | collateral | med in | med out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full/verbose | 64 | 0.64 | 0.84 | 0.77 | 7 | 0.00 | 0.72 | 1.00 | 0.22 | 6840 | 1830 |
| graph_closed/verbose | 64 | 0.28 | 0.78 | 0.52 | 2 | 0.00 | 0.29 | 0.89 | 0.47 | 3324 | 1006 |
| graph_seg/verbose | 64 | 0.42 | 0.82 | 0.68 | 5 | 0.00 | 0.46 | 0.97 | 0.36 | 3874 | 1249 |
- graph_closed/verbose − full/verbose: EES -0.36 [-0.52, -0.22] n=64; affected F1 -0.06 [-0.16, +0.04] n=64; value acc -0.26 [-0.40, -0.12] n=64
- graph_seg/verbose − full/verbose: EES -0.22 [-0.38, -0.06] n=64; affected F1 -0.01 [-0.11, +0.08] n=64; value acc -0.09 [-0.22, +0.05] n=64

### travel 100, prompt v1, cap 16384

| arm | n | EES | affected F1 | value acc | hit cap | EES hit | EES not hit | legal | collateral | med in | med out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full/verbose | 64 | 0.25 | 0.80 | 0.59 | 5 | 0.00 | 0.27 | 0.81 | 0.69 | 26779 | 690 |
| graph_closed/compact | 64 | 0.25 | 0.80 | 0.55 | 2 | 0.00 | 0.26 | 0.66 | 0.98 | 1463 | 636 |
| graph_closed/verbose | 64 | 0.25 | 0.78 | 0.68 | 2 | 0.00 | 0.26 | 0.73 | 0.98 | 3346 | 601 |
| graph_seg/verbose | 64 | 0.33 | 0.84 | 0.60 | 2 | 0.50 | 0.32 | 0.81 | 0.67 | 4016 | 594 |
| graph_key2/verbose | 64 | 0.31 | 0.77 | 0.69 | 1 | 0.00 | 0.32 | 0.81 | 1.12 | 6044 | 641 |
- graph_closed/compact − full/verbose: EES +0.00 [-0.14, +0.14] n=64; affected F1 +0.00 [-0.06, +0.07] n=64; value acc -0.04 [-0.18, +0.09] n=64
- graph_closed/verbose − full/verbose: EES +0.00 [-0.13, +0.12] n=64; affected F1 -0.02 [-0.09, +0.06] n=64; value acc +0.09 [-0.03, +0.20] n=64
- graph_seg/verbose − full/verbose: EES +0.08 [-0.06, +0.22] n=64; affected F1 +0.04 [-0.03, +0.12] n=64; value acc +0.01 [-0.12, +0.15] n=64
- graph_seg/verbose − graph_closed/compact: EES +0.08 [-0.08, +0.23] n=64; affected F1 +0.04 [-0.03, +0.11] n=64; value acc +0.05 [-0.10, +0.20] n=64
- graph_key2/verbose − graph_seg/verbose: EES -0.02 [-0.17, +0.14] n=64; affected F1 -0.07 [-0.14, +0.01] n=64; value acc +0.09 [-0.05, +0.23] n=64
- graph_key2/verbose − full/verbose: EES +0.06 [-0.08, +0.20] n=64; affected F1 -0.02 [-0.10, +0.05] n=64; value acc +0.10 [-0.01, +0.21] n=64

### travel 100, prompt v2, cap 4096

| arm | n | EES | affected F1 | value acc | hit cap | EES hit | EES not hit | legal | collateral | med in | med out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full/verbose | 64 | 0.06 | 0.23 | 0.19 | 56 | 0.04 | 0.25 | 0.92 | 0.25 | 58128 | 4101 |
| graph_closed/compact | 64 | 0.34 | 0.78 | 0.55 | 6 | 0.17 | 0.36 | 0.94 | 0.41 | 1740 | 1291 |
| graph_key2/compact | 64 | 0.36 | 0.73 | 0.63 | 22 | 0.18 | 0.45 | 0.92 | 0.56 | 2614 | 2868 |
| graph_key3/compact | 64 | 0.25 | 0.62 | 0.47 | 24 | 0.04 | 0.38 | 0.94 | 0.42 | 3200 | 2954 |
| bm25_k16/compact | 64 | 0.02 | 0.11 | 0.05 | 44 | 0.00 | 0.05 | 0.95 | 0.03 | 8674 | 4101 |
| recency_k16/compact | 64 | 0.09 | 0.26 | 0.25 | 8 | 0.12 | 0.09 | 0.94 | 0.06 | 2279 | 1586 |
- graph_closed/compact − full/verbose: EES +0.28 [+0.16, +0.41] n=64; affected F1 +0.55 [+0.43, +0.66] n=64; value acc +0.37 [+0.24, +0.51] n=64
- graph_key2/compact − graph_closed/compact: EES +0.02 [-0.14, +0.17] n=64; affected F1 -0.04 [-0.16, +0.07] n=64; value acc +0.07 [-0.08, +0.23] n=64
- graph_key2/compact − full/verbose: EES +0.30 [+0.17, +0.42] n=64; affected F1 +0.50 [+0.38, +0.62] n=64; value acc +0.44 [+0.30, +0.58] n=64
- graph_key3/compact − graph_closed/compact: EES -0.09 [-0.25, +0.06] n=64; affected F1 -0.15 [-0.30, -0.02] n=64; value acc -0.08 [-0.25, +0.08] n=64
- bm25_k16/compact − full/verbose: EES -0.05 [-0.11, +0.02] n=64; affected F1 -0.12 [-0.24, -0.00] n=64; value acc -0.14 [-0.25, -0.03] n=64
- recency_k16/compact − full/verbose: EES +0.03 [-0.06, +0.12] n=64; affected F1 +0.03 [-0.10, +0.15] n=64; value acc +0.06 [-0.06, +0.20] n=64

### travel 100, prompt v2, cap 16384

| arm | n | EES | affected F1 | value acc | hit cap | EES hit | EES not hit | legal | collateral | med in | med out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full/verbose | 64 | 0.20 | 0.42 | 0.33 | 45 | 0.07 | 0.53 | 0.94 | 0.16 | 70003 | 16389 |
| graph_closed/compact | 64 | 0.25 | 0.77 | 0.45 | 6 | 0.00 | 0.28 | 0.91 | 0.41 | 1764 | 1250 |
| graph_closed/verbose | 64 | 0.36 | 0.76 | 0.64 | 1 | 0.00 | 0.37 | 0.95 | 0.45 | 3612 | 1128 |
| graph_seg/verbose | 64 | 0.36 | 0.73 | 0.64 | 12 | 0.17 | 0.40 | 0.98 | 0.48 | 4428 | 1496 |
| graph_key2/compact | 64 | 0.36 | 0.72 | 0.62 | 16 | 0.06 | 0.46 | 0.94 | 0.59 | 2582 | 2806 |
| graph_key2/verbose | 64 | 0.38 | 0.65 | 0.60 | 17 | 0.06 | 0.49 | 0.91 | 0.50 | 6678 | 3018 |
| bm25_k16/compact | 64 | 0.06 | 0.29 | 0.25 | 34 | 0.06 | 0.07 | 0.78 | 0.17 | 20728 | 16389 |
- graph_closed/compact − full/verbose: EES +0.05 [-0.09, +0.19] n=64; affected F1 +0.36 [+0.20, +0.51] n=64; value acc +0.13 [-0.02, +0.28] n=64
- graph_closed/verbose − full/verbose: EES +0.16 [+0.00, +0.31] n=64; affected F1 +0.35 [+0.21, +0.48] n=64; value acc +0.31 [+0.16, +0.45] n=64
- graph_seg/verbose − full/verbose: EES +0.16 [+0.03, +0.28] n=64; affected F1 +0.31 [+0.17, +0.46] n=64; value acc +0.31 [+0.17, +0.45] n=64
- graph_seg/verbose − graph_closed/compact: EES +0.11 [-0.03, +0.25] n=64; affected F1 -0.04 [-0.16, +0.08] n=64; value acc +0.19 [+0.04, +0.33] n=64
- graph_key2/compact − graph_closed/compact: EES +0.11 [-0.03, +0.25] n=64; affected F1 -0.05 [-0.15, +0.05] n=64; value acc +0.17 [+0.04, +0.30] n=64
- graph_key2/verbose − graph_seg/verbose: EES +0.02 [-0.14, +0.17] n=64; affected F1 -0.08 [-0.21, +0.06] n=64; value acc -0.04 [-0.20, +0.12] n=64
- graph_key2/verbose − full/verbose: EES +0.17 [+0.03, +0.31] n=64; affected F1 +0.23 [+0.07, +0.39] n=64; value acc +0.27 [+0.11, +0.42] n=64
- graph_key2/compact − full/verbose: EES +0.16 [+0.02, +0.30] n=64; affected F1 +0.31 [+0.18, +0.44] n=64; value acc +0.30 [+0.17, +0.43] n=64
- bm25_k16/compact − full/verbose: EES -0.14 [-0.25, -0.03] n=64; affected F1 -0.13 [-0.26, +0.01] n=64; value acc -0.08 [-0.22, +0.09] n=64

### travel c100, prompt v1, cap 16384

| arm | n | EES | affected F1 | value acc | hit cap | EES hit | EES not hit | legal | collateral | med in | med out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full/verbose | 63 | 0.14 | 0.71 | 0.41 | 3 | 0.00 | 0.15 | 0.75 | 0.92 | 26844 | 597 |
| graph_closed/compact | 63 | 0.16 | 0.73 | 0.48 | 2 | 0.00 | 0.16 | 0.68 | 1.16 | 1463 | 647 |
| graph_closed/verbose | 63 | 0.32 | 0.81 | 0.68 | 2 | 0.00 | 0.33 | 0.67 | 0.89 | 3346 | 603 |
| graph_seg/verbose | 63 | 0.33 | 0.80 | 0.58 | 3 | 0.00 | 0.35 | 0.76 | 0.83 | 4048 | 599 |
| graph_key2/verbose | 63 | 0.25 | 0.74 | 0.63 | 3 | 0.00 | 0.27 | 0.71 | 1.10 | 5968 | 621 |
- graph_closed/compact − full/verbose: EES +0.02 [-0.11, +0.14] n=63; affected F1 +0.01 [-0.08, +0.10] n=63; value acc +0.07 [-0.07, +0.21] n=63
- graph_closed/verbose − full/verbose: EES +0.17 [+0.03, +0.32] n=63; affected F1 +0.10 [+0.02, +0.17] n=63; value acc +0.28 [+0.13, +0.42] n=63
- graph_seg/verbose − full/verbose: EES +0.19 [+0.06, +0.32] n=63; affected F1 +0.09 [+0.01, +0.16] n=63; value acc +0.18 [+0.04, +0.31] n=63
- graph_seg/verbose − graph_closed/compact: EES +0.17 [+0.03, +0.32] n=63; affected F1 +0.07 [-0.02, +0.16] n=63; value acc +0.11 [-0.02, +0.24] n=63
- graph_key2/verbose − graph_seg/verbose: EES -0.08 [-0.22, +0.06] n=63; affected F1 -0.06 [-0.13, +0.02] n=63; value acc +0.05 [-0.07, +0.17] n=63
- graph_key2/verbose − full/verbose: EES +0.11 [+0.00, +0.22] n=63; affected F1 +0.03 [-0.05, +0.11] n=63; value acc +0.23 [+0.12, +0.34] n=63

### travel c100, prompt v2, cap 4096

| arm | n | EES | affected F1 | value acc | hit cap | EES hit | EES not hit | legal | collateral | med in | med out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full/verbose | 63 | 0.08 | 0.22 | 0.16 | 52 | 0.04 | 0.27 | 0.92 | 0.25 | 57477 | 4101 |
| graph_closed/compact | 63 | 0.32 | 0.74 | 0.60 | 9 | 0.22 | 0.33 | 0.92 | 0.56 | 1791 | 1444 |
- graph_closed/compact − full/verbose: EES +0.24 [+0.11, +0.37] n=63; affected F1 +0.52 [+0.39, +0.64] n=63; value acc +0.44 [+0.29, +0.58] n=63

### travel c100, prompt v2, cap 16384

| arm | n | EES | affected F1 | value acc | hit cap | EES hit | EES not hit | legal | collateral | med in | med out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full/verbose | 63 | 0.19 | 0.33 | 0.22 | 38 | 0.03 | 0.44 | 0.97 | 0.16 | 68761 | 16389 |
| graph_closed/compact | 63 | 0.32 | 0.72 | 0.52 | 7 | 0.00 | 0.36 | 0.87 | 0.48 | 1738 | 1454 |
| graph_closed/verbose | 63 | 0.43 | 0.75 | 0.64 | 3 | 0.00 | 0.45 | 0.98 | 0.25 | 3634 | 1154 |
| graph_seg/verbose | 63 | 0.41 | 0.76 | 0.65 | 10 | 0.20 | 0.45 | 0.98 | 0.49 | 4298 | 1324 |
| graph_key2/compact | 63 | 0.33 | 0.71 | 0.48 | 18 | 0.11 | 0.42 | 0.94 | 0.29 | 2572 | 3131 |
| graph_key2/verbose | 63 | 0.35 | 0.61 | 0.52 | 20 | 0.05 | 0.49 | 0.97 | 0.33 | 6678 | 5855 |
- graph_closed/compact − full/verbose: EES +0.13 [-0.02, +0.27] n=63; affected F1 +0.38 [+0.24, +0.52] n=63; value acc +0.30 [+0.14, +0.45] n=63
- graph_closed/verbose − full/verbose: EES +0.24 [+0.10, +0.38] n=63; affected F1 +0.42 [+0.30, +0.55] n=63; value acc +0.42 [+0.25, +0.57] n=63
- graph_seg/verbose − full/verbose: EES +0.22 [+0.08, +0.37] n=63; affected F1 +0.43 [+0.30, +0.56] n=63; value acc +0.43 [+0.31, +0.56] n=63
- graph_seg/verbose − graph_closed/compact: EES +0.10 [-0.06, +0.25] n=63; affected F1 +0.05 [-0.07, +0.16] n=63; value acc +0.13 [-0.01, +0.27] n=63
- graph_key2/compact − graph_closed/compact: EES +0.02 [-0.14, +0.17] n=63; affected F1 -0.01 [-0.12, +0.12] n=63; value acc -0.04 [-0.21, +0.12] n=63
- graph_key2/verbose − graph_seg/verbose: EES -0.06 [-0.21, +0.08] n=63; affected F1 -0.15 [-0.28, -0.02] n=63; value acc -0.13 [-0.28, +0.02] n=63
- graph_key2/verbose − full/verbose: EES +0.16 [+0.00, +0.32] n=63; affected F1 +0.28 [+0.14, +0.43] n=63; value acc +0.30 [+0.15, +0.44] n=63
- graph_key2/compact − full/verbose: EES +0.14 [+0.02, +0.27] n=63; affected F1 +0.38 [+0.24, +0.51] n=63; value acc +0.25 [+0.11, +0.40] n=63

### travel d100, prompt v2, cap 4096

| arm | n | EES | affected F1 | value acc | hit cap | EES hit | EES not hit | legal | collateral | med in | med out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full/verbose | 64 | 0.48 | 0.71 | 0.69 | 28 | 0.14 | 0.75 | 0.91 | 0.38 | 27349 | 3685 |
| graph_closed/compact | 64 | 0.27 | 0.71 | 0.61 | 4 | 0.25 | 0.27 | 0.88 | 0.55 | 1670 | 1108 |
- graph_closed/compact − full/verbose: EES -0.22 [-0.38, -0.06] n=64; affected F1 +0.01 [-0.11, +0.12] n=64; value acc -0.08 [-0.22, +0.08] n=64

### travel 500, prompt v1, cap 16384

| arm | n | EES | affected F1 | value acc | hit cap | EES hit | EES not hit | legal | collateral | med in | med out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full/verbose | 63 | 0.16 | 0.72 | 0.41 | 5 | 0.00 | 0.17 | 0.73 | 0.81 | 123218 | 593 |
| graph_closed/compact | 63 | 0.29 | 0.80 | 0.58 | 2 | 0.00 | 0.30 | 0.65 | 0.81 | 1465 | 692 |
| graph_closed/verbose | 63 | 0.25 | 0.80 | 0.67 | 2 | 0.00 | 0.26 | 0.68 | 0.92 | 3379 | 633 |
| graph_seg/verbose | 63 | 0.33 | 0.80 | 0.65 | 2 | 0.00 | 0.34 | 0.75 | 0.92 | 4124 | 614 |
| graph_key2/verbose | 63 | 0.19 | 0.78 | 0.61 | 1 | 0.00 | 0.19 | 0.79 | 0.97 | 6764 | 640 |
- graph_closed/compact − full/verbose: EES +0.13 [+0.00, +0.25] n=63; affected F1 +0.09 [+0.01, +0.17] n=63; value acc +0.17 [+0.03, +0.31] n=63
- graph_closed/verbose − full/verbose: EES +0.10 [-0.03, +0.22] n=63; affected F1 +0.09 [+0.00, +0.17] n=63; value acc +0.27 [+0.13, +0.40] n=63
- graph_seg/verbose − full/verbose: EES +0.17 [+0.03, +0.32] n=63; affected F1 +0.09 [+0.00, +0.17] n=63; value acc +0.24 [+0.13, +0.36] n=63
- graph_seg/verbose − graph_closed/compact: EES +0.05 [-0.08, +0.17] n=63; affected F1 -0.00 [-0.06, +0.06] n=63; value acc +0.07 [-0.06, +0.20] n=63
- graph_key2/verbose − graph_seg/verbose: EES -0.14 [-0.29, +0.00] n=63; affected F1 -0.02 [-0.08, +0.04] n=63; value acc -0.04 [-0.18, +0.10] n=63
- graph_key2/verbose − full/verbose: EES +0.03 [-0.11, +0.16] n=63; affected F1 +0.06 [-0.03, +0.15] n=63; value acc +0.20 [+0.07, +0.32] n=63

### travel 500, prompt v2, cap 4096

| arm | n | EES | affected F1 | value acc | hit cap | EES hit | EES not hit | legal | collateral | med in | med out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full/verbose | 63 | 0.13 | 0.30 | 0.30 | 58 | 0.10 | 0.40 | 0.81 | 0.40 | 250597 | 4101 |
| graph_closed/compact | 63 | 0.37 | 0.79 | 0.61 | 10 | 0.20 | 0.40 | 0.89 | 0.43 | 1782 | 1279 |
| graph_key2/compact | 63 | 0.24 | 0.52 | 0.46 | 35 | 0.23 | 0.25 | 0.90 | 0.56 | 7627 | 4101 |
| graph_key3/compact | 63 | 0.24 | 0.50 | 0.48 | 42 | 0.14 | 0.43 | 0.97 | 0.38 | 10457 | 4101 |
| bm25_k16/compact | 63 | 0.02 | 0.22 | 0.15 | 42 | 0.00 | 0.05 | 0.89 | 0.08 | 8889 | 4101 |
| recency_k16/compact | 63 | 0.03 | 0.17 | 0.19 | 10 | 0.10 | 0.02 | 0.95 | 0.13 | 2329 | 1679 |
- graph_closed/compact − full/verbose: EES +0.24 [+0.10, +0.38] n=63; affected F1 +0.48 [+0.35, +0.61] n=63; value acc +0.30 [+0.15, +0.45] n=63
- graph_key2/compact − graph_closed/compact: EES -0.13 [-0.27, +0.02] n=63; affected F1 -0.27 [-0.41, -0.13] n=63; value acc -0.15 [-0.30, +0.01] n=63
- graph_key2/compact − full/verbose: EES +0.11 [-0.02, +0.24] n=63; affected F1 +0.21 [+0.08, +0.35] n=63; value acc +0.16 [+0.02, +0.30] n=63
- graph_key3/compact − graph_closed/compact: EES -0.13 [-0.29, +0.03] n=63; affected F1 -0.29 [-0.42, -0.15] n=63; value acc -0.12 [-0.27, +0.03] n=63
- bm25_k16/compact − full/verbose: EES -0.11 [-0.21, -0.03] n=63; affected F1 -0.09 [-0.20, +0.03] n=63; value acc -0.15 [-0.27, -0.03] n=63
- recency_k16/compact − full/verbose: EES -0.10 [-0.19, -0.02] n=63; affected F1 -0.13 [-0.23, -0.03] n=63; value acc -0.11 [-0.24, +0.02] n=63

### travel 500, prompt v2, cap 16384

| arm | n | EES | affected F1 | value acc | hit cap | EES hit | EES not hit | legal | collateral | med in | med out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full/verbose | 63 | 0.11 | 0.33 | 0.28 | 50 | 0.04 | 0.38 | 0.89 | 0.37 | 260795 | 16389 |
| graph_closed/compact | 63 | 0.29 | 0.73 | 0.63 | 4 | 0.00 | 0.31 | 0.92 | 0.48 | 1770 | 1263 |
| graph_closed/verbose | 63 | 0.40 | 0.81 | 0.60 | 5 | 0.00 | 0.43 | 0.95 | 0.30 | 3654 | 1357 |
| graph_seg/verbose | 63 | 0.56 | 0.83 | 0.74 | 4 | 0.50 | 0.56 | 0.97 | 0.56 | 4443 | 1398 |
| graph_key2/compact | 63 | 0.24 | 0.59 | 0.54 | 22 | 0.05 | 0.34 | 0.87 | 0.56 | 2941 | 3687 |
| graph_key2/verbose | 63 | 0.29 | 0.63 | 0.64 | 19 | 0.05 | 0.39 | 0.97 | 0.60 | 7772 | 3215 |
| bm25_k16/compact | 63 | 0.03 | 0.20 | 0.19 | 36 | 0.00 | 0.07 | 0.81 | 0.13 | 21037 | 16389 |
- graph_closed/compact − full/verbose: EES +0.17 [+0.05, +0.30] n=63; affected F1 +0.41 [+0.27, +0.54] n=63; value acc +0.35 [+0.19, +0.50] n=63
- graph_closed/verbose − full/verbose: EES +0.29 [+0.14, +0.43] n=63; affected F1 +0.49 [+0.35, +0.61] n=63; value acc +0.32 [+0.17, +0.47] n=63
- graph_seg/verbose − full/verbose: EES +0.44 [+0.30, +0.57] n=63; affected F1 +0.51 [+0.39, +0.62] n=63; value acc +0.46 [+0.33, +0.59] n=63
- graph_seg/verbose − graph_closed/compact: EES +0.27 [+0.08, +0.44] n=63; affected F1 +0.10 [-0.02, +0.21] n=63; value acc +0.12 [-0.04, +0.26] n=63
- graph_key2/compact − graph_closed/compact: EES -0.05 [-0.21, +0.11] n=63; affected F1 -0.14 [-0.27, -0.02] n=63; value acc -0.09 [-0.24, +0.07] n=63
- graph_key2/verbose − graph_seg/verbose: EES -0.27 [-0.41, -0.11] n=63; affected F1 -0.20 [-0.33, -0.08] n=63; value acc -0.11 [-0.26, +0.05] n=63
- graph_key2/verbose − full/verbose: EES +0.17 [+0.05, +0.30] n=63; affected F1 +0.30 [+0.17, +0.44] n=63; value acc +0.36 [+0.20, +0.50] n=63
- graph_key2/compact − full/verbose: EES +0.13 [-0.02, +0.25] n=63; affected F1 +0.27 [+0.11, +0.42] n=63; value acc +0.26 [+0.10, +0.42] n=63
- bm25_k16/compact − full/verbose: EES -0.08 [-0.17, +0.02] n=63; affected F1 -0.13 [-0.26, +0.00] n=63; value acc -0.09 [-0.22, +0.04] n=63

### travel: same arm across prompt / cap (paired on episodes)

- native full: v2/4096 − v2/16384: -0.09 [-0.22, +0.05] n=64
- native full: v2/4096 − v1/16384: +0.06 [-0.11, +0.23] n=64
- native full: v2/16384 − v1/16384: +0.16 [+0.00, +0.31] n=64
- 100 full: v2/4096 − v2/16384: -0.14 [-0.27, -0.02] n=64
- 100 full: v2/4096 − v1/16384: -0.19 [-0.31, -0.06] n=64
- 100 full: v2/16384 − v1/16384: -0.05 [-0.19, +0.09] n=64
- 100 graph_closed: v2/4096 − v2/16384: +0.09 [-0.05, +0.23] n=64
- 100 graph_closed: v2/4096 − v1/16384: +0.09 [-0.05, +0.23] n=64
- 100 graph_closed: v2/16384 − v1/16384: +0.00 [-0.14, +0.14] n=64
- 100 graph_key2: v2/4096 − v2/16384: +0.00 [-0.12, +0.12] n=64
- c100 full: v2/4096 − v2/16384: -0.11 [-0.22, +0.00] n=63
- c100 full: v2/4096 − v1/16384: -0.06 [-0.16, +0.03] n=63
- c100 full: v2/16384 − v1/16384: +0.05 [-0.08, +0.17] n=63
- c100 graph_closed: v2/4096 − v2/16384: +0.00 [-0.16, +0.16] n=63
- c100 graph_closed: v2/4096 − v1/16384: +0.16 [+0.00, +0.30] n=63
- c100 graph_closed: v2/16384 − v1/16384: +0.16 [-0.02, +0.32] n=63
- 500 full: v2/4096 − v2/16384: +0.02 [-0.08, +0.11] n=63
- 500 full: v2/4096 − v1/16384: -0.03 [-0.14, +0.08] n=63
- 500 full: v2/16384 − v1/16384: -0.05 [-0.16, +0.06] n=63
- 500 graph_closed: v2/4096 − v2/16384: +0.08 [-0.08, +0.24] n=63
- 500 graph_closed: v2/4096 − v1/16384: +0.08 [-0.08, +0.24] n=63
- 500 graph_closed: v2/16384 − v1/16384: +0.00 [-0.17, +0.16] n=63
- 500 graph_key2: v2/4096 − v2/16384: +0.00 [-0.13, +0.13] n=63
