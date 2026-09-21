## shopping32: actor panels (cap-hit = any attempt at the output cap; pre-2026-09-19 ledgers use the summed output tokens)

### shopping32 native, prompt v2, cap 4096

| arm | n | EES | affected F1 | value acc | hit cap | EES hit | EES not hit | legal | collateral | med in | med out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full/verbose | 64 | 0.48 | 0.69 | 0.78 | 5 | 0.20 | 0.51 | 0.94 | 0.55 | 6718 | 1436 |
| graph_closed/compact | 64 | 0.42 | 0.70 | 0.73 | 5 | 0.20 | 0.44 | 0.94 | 0.52 | 2720 | 1456 |
| graph_closed/verbose | 64 | 0.47 | 0.70 | 0.73 | 6 | 0.50 | 0.47 | 0.94 | 0.55 | 5877 | 1234 |
| bm25_k16/verbose | 64 | 0.44 | 0.66 | 0.75 | 6 | 0.00 | 0.48 | 0.91 | 0.64 | 6718 | 1392 |
| bm25_k16/compact | 64 | 0.47 | 0.70 | 0.76 | 10 | 0.30 | 0.50 | 0.92 | 0.53 | 2963 | 1879 |
| recency_k16/compact | 64 | 0.55 | 0.75 | 0.77 | 7 | 0.29 | 0.58 | 0.94 | 0.42 | 2957 | 1924 |
- graph_closed/compact − full/verbose: EES -0.06 [-0.20, +0.08] n=64; affected F1 +0.01 [-0.09, +0.10] n=64; value acc -0.05 [-0.17, +0.05] n=64
- graph_closed/verbose − full/verbose: EES -0.02 [-0.19, +0.16] n=64; affected F1 +0.01 [-0.10, +0.13] n=64; value acc -0.05 [-0.16, +0.06] n=64
- bm25_k16/compact − full/verbose: EES -0.02 [-0.14, +0.12] n=64; affected F1 +0.01 [-0.08, +0.10] n=64; value acc -0.02 [-0.13, +0.09] n=64
- recency_k16/compact − full/verbose: EES +0.06 [-0.08, +0.20] n=64; affected F1 +0.06 [-0.03, +0.16] n=64; value acc -0.01 [-0.10, +0.09] n=64

### shopping32 100, prompt v1, cap 16384

| arm | n | EES | affected F1 | value acc | hit cap | EES hit | EES not hit | legal | collateral | med in | med out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full/verbose | 64 | 0.48 | 0.69 | 0.77 | 0 | — | 0.48 | 0.89 | 0.45 | 25830 | 621 |
| graph_closed/verbose | 64 | 0.48 | 0.72 | 0.75 | 2 | 0.00 | 0.50 | 0.92 | 0.61 | 7182 | 727 |
| graph_seg/verbose | 64 | 0.50 | 0.77 | 0.85 | 2 | 0.00 | 0.52 | 0.94 | 0.58 | 9860 | 732 |
| frontier_exec/verbose | 64 | 0.56 | 0.86 | 0.90 | 3 | 0.67 | 0.56 | 0.91 | 0.44 | 5860 | 734 |
- frontier_exec/verbose − full/verbose: EES +0.08 [-0.08, +0.23] n=64; affected F1 +0.17 [+0.06, +0.28] n=64; value acc +0.13 [+0.00, +0.25] n=64
- frontier_exec/verbose − graph_seg/verbose: EES +0.06 [-0.06, +0.19] n=64; affected F1 +0.09 [+0.01, +0.17] n=64; value acc +0.05 [-0.04, +0.14] n=64
- graph_closed/verbose − full/verbose: EES +0.00 [-0.16, +0.16] n=64; affected F1 +0.04 [-0.07, +0.14] n=64; value acc -0.02 [-0.14, +0.09] n=64
- graph_seg/verbose − full/verbose: EES +0.02 [-0.12, +0.17] n=64; affected F1 +0.08 [-0.01, +0.18] n=64; value acc +0.08 [-0.03, +0.19] n=64

### shopping32 100, prompt v2, cap 4096

| arm | n | EES | affected F1 | value acc | hit cap | EES hit | EES not hit | legal | collateral | med in | med out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full/verbose | 64 | 0.25 | 0.42 | 0.45 | 38 | 0.08 | 0.50 | 0.98 | 0.36 | 53213 | 4101 |
| graph_closed/compact | 64 | 0.50 | 0.68 | 0.73 | 14 | 0.36 | 0.54 | 0.94 | 0.44 | 3392 | 1856 |
| bm25_k16/compact | 64 | 0.44 | 0.56 | 0.60 | 11 | 0.09 | 0.51 | 0.97 | 0.14 | 4136 | 1310 |
| recency_k16/compact | 64 | 0.39 | 0.53 | 0.55 | 12 | 0.25 | 0.42 | 0.98 | 0.33 | 4159 | 1890 |
- graph_closed/compact − full/verbose: EES +0.25 [+0.11, +0.39] n=64; affected F1 +0.27 [+0.13, +0.40] n=64; value acc +0.28 [+0.13, +0.43] n=64
- bm25_k16/compact − full/verbose: EES +0.19 [+0.05, +0.34] n=64; affected F1 +0.15 [+0.01, +0.28] n=64; value acc +0.16 [+0.02, +0.30] n=64
- recency_k16/compact − full/verbose: EES +0.14 [+0.00, +0.28] n=64; affected F1 +0.11 [-0.03, +0.26] n=64; value acc +0.10 [-0.06, +0.27] n=64

### shopping32 100, prompt v2, cap 16384

| arm | n | EES | affected F1 | value acc | hit cap | EES hit | EES not hit | legal | collateral | med in | med out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full/verbose | 64 | 0.42 | 0.51 | 0.49 | 25 | 0.12 | 0.62 | 1.00 | 0.39 | 27058 | 5424 |
| graph_closed/compact | 64 | 0.41 | 0.69 | 0.71 | 2 | 0.00 | 0.42 | 0.95 | 0.56 | 3242 | 1600 |
| graph_closed/verbose | 64 | 0.55 | 0.69 | 0.70 | 4 | 0.00 | 0.58 | 0.98 | 0.55 | 7524 | 1495 |
| graph_seg/verbose | 64 | 0.34 | 0.61 | 0.74 | 13 | 0.15 | 0.39 | 0.95 | 0.77 | 10560 | 1850 |
| graph_key2/compact | 64 | 0.41 | 0.57 | 0.66 | 21 | 0.00 | 0.60 | 0.95 | 0.48 | 6185 | 4292 |
- graph_closed/compact − full/verbose: EES -0.02 [-0.19, +0.16] n=64; affected F1 +0.17 [+0.03, +0.32] n=64; value acc +0.22 [+0.06, +0.38] n=64
- graph_closed/verbose − full/verbose: EES +0.12 [-0.03, +0.28] n=64; affected F1 +0.17 [+0.03, +0.31] n=64; value acc +0.20 [+0.05, +0.36] n=64
- graph_seg/verbose − full/verbose: EES -0.08 [-0.23, +0.06] n=64; affected F1 +0.10 [-0.04, +0.23] n=64; value acc +0.25 [+0.10, +0.40] n=64
- graph_seg/verbose − graph_closed/compact: EES -0.06 [-0.20, +0.08] n=64; affected F1 -0.08 [-0.20, +0.05] n=64; value acc +0.03 [-0.10, +0.16] n=64
- graph_key2/compact − graph_closed/compact: EES +0.00 [-0.17, +0.17] n=64; affected F1 -0.12 [-0.25, +0.01] n=64; value acc -0.06 [-0.20, +0.08] n=64
- graph_key2/compact − full/verbose: EES -0.02 [-0.17, +0.14] n=64; affected F1 +0.06 [-0.10, +0.21] n=64; value acc +0.16 [+0.00, +0.32] n=64

### shopping32 500, prompt v1, cap 16384

| arm | n | EES | affected F1 | value acc | hit cap | EES hit | EES not hit | legal | collateral | med in | med out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full/verbose | 64 | 0.52 | 0.73 | 0.77 | 2 | 1.00 | 0.50 | 0.92 | 0.38 | 103192 | 546 |
| graph_closed/verbose | 64 | 0.48 | 0.70 | 0.78 | 1 | 0.00 | 0.49 | 0.88 | 0.70 | 7189 | 702 |
| graph_seg/verbose | 64 | 0.36 | 0.68 | 0.74 | 2 | 0.00 | 0.37 | 0.83 | 0.75 | 10290 | 708 |
| frontier_exec/verbose | 64 | 0.56 | 0.77 | 0.86 | 2 | 0.00 | 0.58 | 0.88 | 0.59 | 6128 | 712 |
- frontier_exec/verbose − full/verbose: EES +0.05 [-0.09, +0.19] n=64; affected F1 +0.04 [-0.05, +0.13] n=64; value acc +0.10 [-0.01, +0.20] n=64
- frontier_exec/verbose − graph_seg/verbose: EES +0.20 [+0.03, +0.38] n=64; affected F1 +0.09 [-0.02, +0.20] n=64; value acc +0.12 [+0.01, +0.23] n=64
- graph_closed/verbose − full/verbose: EES -0.03 [-0.16, +0.09] n=64; affected F1 -0.03 [-0.12, +0.06] n=64; value acc +0.02 [-0.10, +0.13] n=64
- graph_seg/verbose − full/verbose: EES -0.16 [-0.31, +0.00] n=64; affected F1 -0.05 [-0.14, +0.05] n=64; value acc -0.02 [-0.15, +0.09] n=64

### shopping32 500, prompt v2, cap 4096

| arm | n | EES | affected F1 | value acc | hit cap | EES hit | EES not hit | legal | collateral | med in | med out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full/verbose | 64 | 0.30 | 0.46 | 0.46 | 40 | 0.15 | 0.54 | 0.95 | 0.34 | 205949 | 4101 |
| graph_closed/compact | 64 | 0.55 | 0.75 | 0.80 | 5 | 0.20 | 0.58 | 0.95 | 0.53 | 3314 | 1712 |
| bm25_k16/compact | 64 | 0.27 | 0.34 | 0.28 | 13 | 0.15 | 0.29 | 0.98 | 0.05 | 4782 | 1124 |
| recency_k16/compact | 64 | 0.41 | 0.54 | 0.62 | 10 | 0.20 | 0.44 | 0.95 | 0.36 | 5108 | 1513 |
- graph_closed/compact − full/verbose: EES +0.25 [+0.14, +0.38] n=64; affected F1 +0.29 [+0.17, +0.41] n=64; value acc +0.35 [+0.21, +0.48] n=64
- bm25_k16/compact − full/verbose: EES -0.03 [-0.17, +0.11] n=64; affected F1 -0.12 [-0.27, +0.03] n=64; value acc -0.17 [-0.33, -0.02] n=64
- recency_k16/compact − full/verbose: EES +0.11 [-0.06, +0.27] n=64; affected F1 +0.08 [-0.08, +0.24] n=64; value acc +0.16 [+0.00, +0.32] n=64

### shopping32 500, prompt v2, cap 16384

| arm | n | EES | affected F1 | value acc | hit cap | EES hit | EES not hit | legal | collateral | med in | med out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full/verbose | 64 | 0.30 | 0.51 | 0.57 | 26 | 0.00 | 0.50 | 0.97 | 0.62 | 106099 | 6602 |
| graph_closed/compact | 64 | 0.50 | 0.65 | 0.64 | 7 | 0.29 | 0.53 | 0.97 | 0.34 | 3314 | 1976 |
| graph_closed/verbose | 64 | 0.47 | 0.66 | 0.71 | 6 | 0.00 | 0.52 | 0.97 | 0.62 | 7532 | 1491 |
| graph_seg/verbose | 64 | 0.53 | 0.68 | 0.74 | 7 | 0.00 | 0.60 | 1.00 | 0.50 | 11136 | 1892 |
| graph_key2/compact | 64 | 0.44 | 0.64 | 0.66 | 12 | 0.08 | 0.52 | 0.95 | 0.55 | 7955 | 4464 |
- graph_closed/compact − full/verbose: EES +0.20 [+0.05, +0.36] n=64; affected F1 +0.14 [-0.00, +0.27] n=64; value acc +0.07 [-0.09, +0.23] n=64
- graph_closed/verbose − full/verbose: EES +0.17 [+0.05, +0.31] n=64; affected F1 +0.15 [+0.02, +0.28] n=64; value acc +0.14 [-0.02, +0.29] n=64
- graph_seg/verbose − full/verbose: EES +0.23 [+0.08, +0.39] n=64; affected F1 +0.16 [+0.03, +0.30] n=64; value acc +0.17 [+0.02, +0.33] n=64
- graph_seg/verbose − graph_closed/compact: EES +0.03 [-0.12, +0.19] n=64; affected F1 +0.03 [-0.10, +0.16] n=64; value acc +0.10 [-0.04, +0.23] n=64
- graph_key2/compact − graph_closed/compact: EES -0.06 [-0.20, +0.09] n=64; affected F1 -0.01 [-0.14, +0.12] n=64; value acc +0.02 [-0.12, +0.18] n=64
- graph_key2/compact − full/verbose: EES +0.14 [+0.02, +0.28] n=64; affected F1 +0.12 [-0.01, +0.26] n=64; value acc +0.09 [-0.06, +0.26] n=64

### shopping32: same arm across prompt / cap (paired on episodes)

- 100 full: v2/4096 − v2/16384: -0.17 [-0.31, -0.03] n=64
- 100 full: v2/4096 − v1/16384: -0.23 [-0.39, -0.06] n=64
- 100 full: v2/16384 − v1/16384: -0.06 [-0.22, +0.09] n=64
- 100 graph_closed: v2/4096 − v2/16384: +0.09 [-0.05, +0.23] n=64
- 500 full: v2/4096 − v2/16384: +0.00 [-0.14, +0.14] n=64
- 500 full: v2/4096 − v1/16384: -0.22 [-0.38, -0.06] n=64
- 500 full: v2/16384 − v1/16384: -0.22 [-0.39, -0.05] n=64
- 500 graph_closed: v2/4096 − v2/16384: +0.05 [-0.09, +0.20] n=64