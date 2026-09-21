## travel_arena: actor panels (cap-hit = any attempt at the output cap; pre-2026-09-19 ledgers use the summed output tokens)

### travel_arena native, prompt v1, cap 16384

| arm | n | EES | affected F1 | value acc | hit cap | EES hit | EES not hit | legal | collateral | med in | med out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| causal/verbose | 64 | 0.42 | 0.89 | 0.71 | 1 | 0.00 | 0.43 | 0.81 | 0.55 | 3834 | 632 |
| long_context/verbose | 64 | 0.38 | 0.88 | 0.72 | 0 | — | 0.38 | 0.78 | 0.50 | 6911 | 619 |
| bm25/verbose | 64 | 0.06 | 0.46 | 0.41 | 7 | 0.14 | 0.05 | 0.53 | 0.56 | 1866 | 526 |
| bm25_k16/verbose | 64 | 0.28 | 0.58 | 0.55 | 4 | 0.25 | 0.28 | 0.88 | 0.25 | 5021 | 598 |
| amem/verbose | 64 | 0.14 | 0.43 | 0.36 | 5 | 0.20 | 0.14 | 0.64 | 0.44 | 2619 | 584 |
- causal/verbose − long_context/verbose: EES +0.05 [-0.09, +0.17] n=64; affected F1 +0.01 [-0.03, +0.05] n=64; value acc -0.01 [-0.14, +0.12] n=64
- causal/verbose − bm25/verbose: EES +0.36 [+0.23, +0.48] n=64; affected F1 +0.43 [+0.34, +0.52] n=64; value acc +0.30 [+0.14, +0.46] n=64
- causal/verbose − bm25_k16/verbose: EES +0.14 [+0.00, +0.27] n=64; affected F1 +0.30 [+0.21, +0.40] n=64; value acc +0.17 [+0.03, +0.30] n=64
- causal/verbose − amem/verbose: EES +0.28 [+0.14, +0.42] n=64; affected F1 +0.46 [+0.36, +0.56] n=64; value acc +0.36 [+0.21, +0.49] n=64
- amem/verbose − long_context/verbose: EES -0.23 [-0.39, -0.09] n=64; affected F1 -0.45 [-0.55, -0.35] n=64; value acc -0.37 [-0.51, -0.22] n=64
- bm25_k16/verbose − long_context/verbose: EES -0.09 [-0.23, +0.05] n=64; affected F1 -0.29 [-0.40, -0.19] n=64; value acc -0.18 [-0.31, -0.04] n=64

### travel_arena native, prompt v2, cap 16384

| arm | n | EES | affected F1 | value acc | hit cap | EES hit | EES not hit | legal | collateral | med in | med out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| causal/verbose | 64 | 0.62 | 0.81 | 0.73 | 2 | 0.00 | 0.65 | 0.97 | 0.50 | 4120 | 1344 |
| long_context/verbose | 64 | 0.59 | 0.81 | 0.79 | 6 | 0.17 | 0.64 | 0.97 | 0.36 | 7334 | 2053 |
| bm25/verbose | 64 | 0.08 | 0.19 | 0.19 | 7 | 0.14 | 0.07 | 0.77 | 0.28 | 2144 | 1036 |
| bm25_k16/verbose | 64 | 0.30 | 0.56 | 0.58 | 6 | 0.17 | 0.31 | 0.95 | 0.11 | 5306 | 1492 |
| amem/verbose | 64 | 0.11 | 0.28 | 0.32 | 9 | 0.11 | 0.11 | 0.89 | 0.12 | 3020 | 1021 |
- causal/verbose − long_context/verbose: EES +0.03 [-0.09, +0.16] n=64; affected F1 +0.01 [-0.07, +0.09] n=64; value acc -0.06 [-0.17, +0.06] n=64
- causal/verbose − bm25/verbose: EES +0.55 [+0.41, +0.69] n=64; affected F1 +0.63 [+0.52, +0.73] n=64; value acc +0.54 [+0.41, +0.67] n=64
- causal/verbose − bm25_k16/verbose: EES +0.33 [+0.17, +0.48] n=64; affected F1 +0.26 [+0.13, +0.37] n=64; value acc +0.15 [-0.01, +0.30] n=64
- causal/verbose − amem/verbose: EES +0.52 [+0.38, +0.66] n=64; affected F1 +0.53 [+0.42, +0.64] n=64; value acc +0.41 [+0.26, +0.55] n=64
- amem/verbose − long_context/verbose: EES -0.48 [-0.62, -0.34] n=64; affected F1 -0.52 [-0.64, -0.39] n=64; value acc -0.46 [-0.62, -0.30] n=64
- bm25_k16/verbose − long_context/verbose: EES -0.30 [-0.44, -0.16] n=64; affected F1 -0.25 [-0.37, -0.12] n=64; value acc -0.20 [-0.35, -0.06] n=64

### travel_arena 100, prompt v1, cap 16384

| arm | n | EES | affected F1 | value acc | hit cap | EES hit | EES not hit | legal | collateral | med in | med out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| causal/verbose | 64 | 0.50 | 0.92 | 0.73 | 0 | — | 0.50 | 0.89 | 0.39 | 4363 | 638 |
| long_context/verbose | 64 | 0.19 | 0.76 | 0.50 | 2 | 0.00 | 0.19 | 0.88 | 0.78 | 27698 | 594 |
| bm25/verbose | 64 | 0.06 | 0.35 | 0.33 | 16 | 0.00 | 0.08 | 0.56 | 0.52 | 1860 | 596 |
| bm25_k16/verbose | 64 | 0.02 | 0.40 | 0.35 | 18 | 0.00 | 0.02 | 0.61 | 0.45 | 5732 | 771 |
| amem/verbose | 64 | 0.02 | 0.29 | 0.28 | 21 | 0.05 | 0.00 | 0.67 | 0.42 | 2684 | 1799 |
- causal/verbose − long_context/verbose: EES +0.31 [+0.17, +0.44] n=64; affected F1 +0.15 [+0.09, +0.21] n=64; value acc +0.23 [+0.10, +0.36] n=64
- causal/verbose − bm25/verbose: EES +0.44 [+0.30, +0.56] n=64; affected F1 +0.57 [+0.49, +0.65] n=64; value acc +0.40 [+0.27, +0.54] n=64
- causal/verbose − bm25_k16/verbose: EES +0.48 [+0.36, +0.61] n=64; affected F1 +0.51 [+0.42, +0.60] n=64; value acc +0.38 [+0.26, +0.50] n=64
- causal/verbose − amem/verbose: EES +0.48 [+0.36, +0.61] n=64; affected F1 +0.63 [+0.54, +0.71] n=64; value acc +0.45 [+0.32, +0.58] n=64
- amem/verbose − long_context/verbose: EES -0.17 [-0.27, -0.08] n=64; affected F1 -0.48 [-0.57, -0.38] n=64; value acc -0.22 [-0.35, -0.09] n=64
- bm25_k16/verbose − long_context/verbose: EES -0.17 [-0.28, -0.08] n=64; affected F1 -0.36 [-0.46, -0.26] n=64; value acc -0.15 [-0.30, +0.00] n=64

### travel_arena 100, prompt v2, cap 16384

| arm | n | EES | affected F1 | value acc | hit cap | EES hit | EES not hit | legal | collateral | med in | med out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| causal/verbose | 64 | 0.52 | 0.81 | 0.80 | 7 | 0.29 | 0.54 | 0.88 | 0.67 | 4797 | 1542 |
| long_context/verbose | 64 | 0.22 | 0.40 | 0.32 | 35 | 0.06 | 0.41 | 0.98 | 0.14 | 70517 | 16389 |
| bm25/verbose | 64 | 0.05 | 0.16 | 0.19 | 16 | 0.00 | 0.06 | 0.77 | 0.23 | 2132 | 1140 |
| bm25_k16/verbose | 64 | 0.06 | 0.19 | 0.21 | 28 | 0.00 | 0.11 | 0.88 | 0.09 | 6123 | 3890 |
| amem/verbose | 64 | 0.06 | 0.14 | 0.12 | 17 | 0.00 | 0.09 | 0.81 | 0.19 | 2962 | 1154 |
- causal/verbose − long_context/verbose: EES +0.30 [+0.14, +0.44] n=64; affected F1 +0.41 [+0.28, +0.53] n=64; value acc +0.48 [+0.35, +0.62] n=64
- causal/verbose − bm25/verbose: EES +0.47 [+0.33, +0.59] n=64; affected F1 +0.65 [+0.55, +0.74] n=64; value acc +0.61 [+0.47, +0.75] n=64
- causal/verbose − bm25_k16/verbose: EES +0.45 [+0.31, +0.58] n=64; affected F1 +0.62 [+0.52, +0.72] n=64; value acc +0.59 [+0.45, +0.72] n=64
- causal/verbose − amem/verbose: EES +0.45 [+0.31, +0.58] n=64; affected F1 +0.66 [+0.56, +0.76] n=64; value acc +0.68 [+0.55, +0.79] n=64
- amem/verbose − long_context/verbose: EES -0.16 [-0.27, -0.05] n=64; affected F1 -0.26 [-0.40, -0.12] n=64; value acc -0.19 [-0.32, -0.07] n=64
- bm25_k16/verbose − long_context/verbose: EES -0.16 [-0.27, -0.05] n=64; affected F1 -0.22 [-0.36, -0.07] n=64; value acc -0.11 [-0.25, +0.04] n=64

### travel_arena c100, prompt v1, cap 16384

| arm | n | EES | affected F1 | value acc | hit cap | EES hit | EES not hit | legal | collateral | med in | med out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| causal/verbose | 64 | 0.34 | 0.87 | 0.67 | 1 | 0.00 | 0.35 | 0.78 | 0.48 | 4206 | 622 |
| long_context/verbose | 64 | 0.22 | 0.77 | 0.37 | 3 | 0.00 | 0.23 | 0.91 | 0.56 | 27778 | 652 |
| bm25/verbose | 64 | 0.06 | 0.31 | 0.09 | 24 | 0.04 | 0.07 | 0.67 | 0.36 | 2068 | 706 |
| bm25_k16/verbose | 64 | 0.02 | 0.37 | 0.23 | 22 | 0.05 | 0.00 | 0.72 | 0.39 | 5846 | 1274 |
- causal/verbose − long_context/verbose: EES +0.12 [-0.02, +0.27] n=64; affected F1 +0.10 [+0.02, +0.18] n=64; value acc +0.30 [+0.17, +0.44] n=64
- causal/verbose − bm25/verbose: EES +0.28 [+0.16, +0.41] n=64; affected F1 +0.55 [+0.44, +0.65] n=64; value acc +0.58 [+0.44, +0.70] n=64
- causal/verbose − bm25_k16/verbose: EES +0.33 [+0.20, +0.45] n=64; affected F1 +0.50 [+0.41, +0.59] n=64; value acc +0.45 [+0.31, +0.58] n=64
- bm25_k16/verbose − long_context/verbose: EES -0.20 [-0.31, -0.09] n=64; affected F1 -0.40 [-0.51, -0.30] n=64; value acc -0.14 [-0.26, -0.02] n=64

### travel_arena c100, prompt v2, cap 16384

| arm | n | EES | affected F1 | value acc | hit cap | EES hit | EES not hit | legal | collateral | med in | med out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| causal/verbose | 64 | 0.42 | 0.75 | 0.63 | 10 | 0.10 | 0.48 | 0.91 | 0.39 | 4810 | 1648 |
| long_context/verbose | 64 | 0.16 | 0.37 | 0.26 | 36 | 0.03 | 0.32 | 0.91 | 0.27 | 69416 | 16389 |
| bm25/verbose | 64 | 0.05 | 0.12 | 0.14 | 21 | 0.00 | 0.07 | 0.84 | 0.16 | 2343 | 1534 |
| bm25_k16/verbose | 64 | 0.03 | 0.11 | 0.09 | 31 | 0.00 | 0.06 | 0.88 | 0.12 | 6464 | 5141 |
- causal/verbose − long_context/verbose: EES +0.27 [+0.12, +0.41] n=64; affected F1 +0.38 [+0.25, +0.51] n=64; value acc +0.38 [+0.25, +0.51] n=64
- causal/verbose − bm25/verbose: EES +0.38 [+0.23, +0.52] n=64; affected F1 +0.64 [+0.50, +0.76] n=64; value acc +0.49 [+0.35, +0.63] n=64
- causal/verbose − bm25_k16/verbose: EES +0.39 [+0.27, +0.52] n=64; affected F1 +0.64 [+0.53, +0.75] n=64; value acc +0.54 [+0.43, +0.66] n=64
- bm25_k16/verbose − long_context/verbose: EES -0.12 [-0.22, -0.03] n=64; affected F1 -0.26 [-0.39, -0.14] n=64; value acc -0.16 [-0.28, -0.05] n=64

### travel_arena 500, prompt v1, cap 16384

| arm | n | EES | affected F1 | value acc | hit cap | EES hit | EES not hit | legal | collateral | med in | med out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| causal/verbose | 64 | 0.34 | 0.85 | 0.71 | 1 | 0.00 | 0.35 | 0.78 | 0.62 | 4378 | 630 |
| long_context/verbose | 64 | 0.14 | 0.76 | 0.45 | 10 | 0.00 | 0.17 | 0.81 | 0.61 | 126778 | 608 |
| bm25/verbose | 64 | 0.03 | 0.33 | 0.23 | 14 | 0.07 | 0.02 | 0.66 | 0.42 | 2064 | 658 |
| bm25_k16/verbose | 64 | 0.05 | 0.33 | 0.30 | 18 | 0.06 | 0.04 | 0.72 | 0.36 | 5760 | 805 |
- causal/verbose − long_context/verbose: EES +0.20 [+0.08, +0.33] n=64; affected F1 +0.09 [+0.02, +0.17] n=64; value acc +0.26 [+0.15, +0.37] n=64
- causal/verbose − bm25/verbose: EES +0.31 [+0.19, +0.44] n=64; affected F1 +0.52 [+0.42, +0.62] n=64; value acc +0.47 [+0.33, +0.61] n=64
- causal/verbose − bm25_k16/verbose: EES +0.30 [+0.19, +0.42] n=64; affected F1 +0.52 [+0.42, +0.62] n=64; value acc +0.40 [+0.27, +0.54] n=64
- bm25_k16/verbose − long_context/verbose: EES -0.09 [-0.19, -0.02] n=64; affected F1 -0.43 [-0.52, -0.32] n=64; value acc -0.14 [-0.27, -0.02] n=64

### travel_arena 500, prompt v2, cap 16384

| arm | n | EES | affected F1 | value acc | hit cap | EES hit | EES not hit | legal | collateral | med in | med out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| causal/verbose | 64 | 0.56 | 0.85 | 0.76 | 3 | 0.00 | 0.59 | 0.89 | 0.34 | 4645 | 1540 |
| long_context/verbose | 64 | 0.08 | 0.35 | 0.30 | 51 | 0.00 | 0.38 | 0.89 | 0.41 | 268878 | 16389 |
| bm25/verbose | 64 | 0.05 | 0.14 | 0.16 | 18 | 0.00 | 0.07 | 0.88 | 0.14 | 2344 | 1156 |
| bm25_k16/verbose | 64 | 0.02 | 0.06 | 0.06 | 27 | 0.00 | 0.03 | 0.86 | 0.14 | 6380 | 3924 |
- causal/verbose − long_context/verbose: EES +0.48 [+0.34, +0.62] n=64; affected F1 +0.51 [+0.39, +0.62] n=64; value acc +0.46 [+0.31, +0.60] n=64
- causal/verbose − bm25/verbose: EES +0.52 [+0.38, +0.66] n=64; affected F1 +0.71 [+0.60, +0.81] n=64; value acc +0.60 [+0.46, +0.73] n=64
- causal/verbose − bm25_k16/verbose: EES +0.55 [+0.42, +0.67] n=64; affected F1 +0.79 [+0.71, +0.87] n=64; value acc +0.69 [+0.57, +0.81] n=64
- bm25_k16/verbose − long_context/verbose: EES -0.06 [-0.14, +0.02] n=64; affected F1 -0.29 [-0.40, -0.17] n=64; value acc -0.23 [-0.35, -0.12] n=64

### travel_arena: same arm across prompt / cap (paired on episodes)

