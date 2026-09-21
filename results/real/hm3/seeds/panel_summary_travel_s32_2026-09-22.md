## travel: actor panels (cap-hit = any attempt at the output cap; pre-2026-09-19 ledgers use the summed output tokens)

### travel native, prompt v1, cap 16384

| arm | n | EES | affected F1 | value acc | hit cap | EES hit | EES not hit | legal | collateral | med in | med out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full/verbose | 64 | 0.45 | 0.86 | 0.78 | 2 | 0.00 | 0.47 | 0.81 | 0.55 | 6540 | 633 |
| graph_seg/verbose | 64 | 0.41 | 0.86 | 0.63 | 2 | 0.00 | 0.42 | 0.89 | 0.52 | 3578 | 592 |
| frontier_exec/verbose | 64 | 0.36 | 0.85 | 0.60 | 2 | 0.50 | 0.35 | 0.84 | 0.58 | 3106 | 606 |
- frontier_exec/verbose − full/verbose: EES -0.09 [-0.27, +0.08] n=64; affected F1 -0.00 [-0.06, +0.06] n=64; value acc -0.18 [-0.33, -0.03] n=64
- frontier_exec/verbose − graph_seg/verbose: EES -0.05 [-0.19, +0.09] n=64; affected F1 -0.01 [-0.09, +0.07] n=64; value acc -0.03 [-0.18, +0.11] n=64
- graph_seg/verbose − full/verbose: EES -0.05 [-0.20, +0.11] n=64; affected F1 +0.00 [-0.07, +0.08] n=64; value acc -0.15 [-0.27, -0.03] n=64

### travel 100, prompt v1, cap 16384

| arm | n | EES | affected F1 | value acc | hit cap | EES hit | EES not hit | legal | collateral | med in | med out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full/verbose | 63 | 0.22 | 0.76 | 0.68 | 5 | 0.00 | 0.24 | 0.84 | 0.76 | 26631 | 651 |
| graph_seg/verbose | 63 | 0.46 | 0.87 | 0.78 | 1 | 1.00 | 0.45 | 0.86 | 0.60 | 3956 | 641 |
| frontier_exec/verbose | 63 | 0.29 | 0.83 | 0.68 | 2 | 0.00 | 0.30 | 0.78 | 0.70 | 5439 | 611 |
- frontier_exec/verbose − full/verbose: EES +0.06 [-0.06, +0.21] n=63; affected F1 +0.07 [+0.00, +0.13] n=63; value acc +0.01 [-0.12, +0.13] n=63
- frontier_exec/verbose − graph_seg/verbose: EES -0.17 [-0.35, +0.00] n=63; affected F1 -0.04 [-0.09, +0.02] n=63; value acc -0.10 [-0.21, +0.02] n=63
- graph_seg/verbose − full/verbose: EES +0.24 [+0.08, +0.40] n=63; affected F1 +0.10 [+0.04, +0.17] n=63; value acc +0.10 [-0.03, +0.23] n=63

### travel c100, prompt v1, cap 16384

| arm | n | EES | affected F1 | value acc | hit cap | EES hit | EES not hit | legal | collateral | med in | med out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full/verbose | 63 | 0.21 | 0.76 | 0.47 | 4 | 0.00 | 0.22 | 0.86 | 0.83 | 26728 | 563 |
| graph_seg/verbose | 63 | 0.30 | 0.85 | 0.72 | 0 | — | 0.30 | 0.76 | 0.71 | 3890 | 580 |
| frontier_exec/verbose | 63 | 0.32 | 0.76 | 0.67 | 5 | 0.00 | 0.34 | 0.78 | 0.75 | 5673 | 597 |
- frontier_exec/verbose − full/verbose: EES +0.11 [-0.02, +0.24] n=63; affected F1 -0.00 [-0.08, +0.07] n=63; value acc +0.19 [+0.08, +0.31] n=63
- frontier_exec/verbose − graph_seg/verbose: EES +0.02 [-0.13, +0.16] n=63; affected F1 -0.09 [-0.16, -0.03] n=63; value acc -0.05 [-0.16, +0.06] n=63
- graph_seg/verbose − full/verbose: EES +0.10 [-0.03, +0.22] n=63; affected F1 +0.09 [+0.03, +0.15] n=63; value acc +0.25 [+0.13, +0.36] n=63

### travel c100, prompt v2, cap 16384

| arm | n | EES | affected F1 | value acc | hit cap | EES hit | EES not hit | legal | collateral | med in | med out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full/verbose | 63 | 0.13 | 0.29 | 0.21 | 42 | 0.00 | 0.38 | 0.92 | 0.22 | 69383 | 16389 |
| graph_seg/verbose | 63 | 0.52 | 0.71 | 0.63 | 12 | 0.00 | 0.65 | 0.97 | 0.35 | 4345 | 1580 |
| frontier_exec/verbose | 63 | 0.32 | 0.66 | 0.53 | 16 | 0.00 | 0.43 | 0.94 | 0.27 | 6119 | 3577 |
- frontier_exec/verbose − full/verbose: EES +0.19 [+0.06, +0.32] n=63; affected F1 +0.37 [+0.22, +0.52] n=63; value acc +0.32 [+0.16, +0.48] n=63
- frontier_exec/verbose − graph_seg/verbose: EES -0.21 [-0.37, -0.05] n=63; affected F1 -0.05 [-0.16, +0.07] n=63; value acc -0.10 [-0.25, +0.05] n=63
- graph_seg/verbose − full/verbose: EES +0.40 [+0.25, +0.54] n=63; affected F1 +0.42 [+0.27, +0.56] n=63; value acc +0.42 [+0.28, +0.57] n=63

### travel 500, prompt v1, cap 16384

| arm | n | EES | affected F1 | value acc | hit cap | EES hit | EES not hit | legal | collateral | med in | med out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full/verbose | 63 | 0.24 | 0.77 | 0.54 | 11 | 0.18 | 0.25 | 0.75 | 0.81 | 123118 | 673 |
| graph_seg/verbose | 63 | 0.38 | 0.86 | 0.68 | 1 | 0.00 | 0.39 | 0.78 | 0.65 | 4039 | 590 |
| frontier_exec/verbose | 63 | 0.22 | 0.79 | 0.52 | 2 | 0.00 | 0.23 | 0.70 | 0.86 | 14752 | 654 |
- frontier_exec/verbose − full/verbose: EES -0.02 [-0.13, +0.11] n=63; affected F1 +0.02 [-0.04, +0.07] n=63; value acc -0.02 [-0.11, +0.07] n=63
- frontier_exec/verbose − graph_seg/verbose: EES -0.16 [-0.30, -0.02] n=63; affected F1 -0.07 [-0.13, -0.00] n=63; value acc -0.16 [-0.28, -0.04] n=63
- graph_seg/verbose − full/verbose: EES +0.14 [+0.00, +0.29] n=63; affected F1 +0.08 [+0.02, +0.15] n=63; value acc +0.14 [+0.02, +0.27] n=63

### travel 500, prompt v2, cap 16384

| arm | n | EES | affected F1 | value acc | hit cap | EES hit | EES not hit | legal | collateral | med in | med out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full/verbose | 63 | 0.13 | 0.37 | 0.31 | 42 | 0.07 | 0.24 | 0.86 | 0.32 | 256601 | 16389 |
| graph_seg/verbose | 63 | 0.41 | 0.77 | 0.65 | 13 | 0.08 | 0.50 | 0.97 | 0.43 | 4370 | 1525 |
| frontier_exec/verbose | 63 | 0.27 | 0.58 | 0.49 | 20 | 0.00 | 0.40 | 0.87 | 0.44 | 17967 | 7317 |
- frontier_exec/verbose − full/verbose: EES +0.14 [+0.02, +0.27] n=63; affected F1 +0.21 [+0.06, +0.35] n=63; value acc +0.18 [+0.03, +0.33] n=63
- frontier_exec/verbose − graph_seg/verbose: EES -0.14 [-0.30, +0.02] n=63; affected F1 -0.19 [-0.32, -0.05] n=63; value acc -0.16 [-0.30, -0.02] n=63
- graph_seg/verbose − full/verbose: EES +0.29 [+0.14, +0.43] n=63; affected F1 +0.40 [+0.26, +0.52] n=63; value acc +0.35 [+0.19, +0.50] n=63

### travel: same arm across prompt / cap (paired on episodes)

- c100 full: v2/16384 − v1/16384: -0.08 [-0.19, +0.03] n=63
- 500 full: v2/16384 − v1/16384: -0.11 [-0.24, +0.02] n=63
