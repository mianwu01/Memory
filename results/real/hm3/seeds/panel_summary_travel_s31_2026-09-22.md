## travel: actor panels (cap-hit = any attempt at the output cap; pre-2026-09-19 ledgers use the summed output tokens)

### travel native, prompt v1, cap 16384

| arm | n | EES | affected F1 | value acc | hit cap | EES hit | EES not hit | legal | collateral | med in | med out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full/verbose | 64 | 0.33 | 0.83 | 0.68 | 0 | — | 0.33 | 0.73 | 0.73 | 6654 | 607 |
| graph_seg/verbose | 64 | 0.31 | 0.85 | 0.69 | 1 | 0.00 | 0.32 | 0.77 | 0.73 | 3598 | 574 |
| frontier_exec/verbose | 64 | 0.36 | 0.87 | 0.64 | 2 | 0.00 | 0.37 | 0.86 | 0.47 | 3122 | 587 |
- frontier_exec/verbose − full/verbose: EES +0.03 [-0.09, +0.17] n=64; affected F1 +0.04 [-0.03, +0.10] n=64; value acc -0.04 [-0.18, +0.10] n=64
- frontier_exec/verbose − graph_seg/verbose: EES +0.05 [-0.09, +0.19] n=64; affected F1 +0.02 [-0.03, +0.07] n=64; value acc -0.05 [-0.18, +0.09] n=64
- graph_seg/verbose − full/verbose: EES -0.02 [-0.17, +0.14] n=64; affected F1 +0.02 [-0.03, +0.07] n=64; value acc +0.00 [-0.14, +0.14] n=64

### travel 100, prompt v1, cap 16384

| arm | n | EES | affected F1 | value acc | hit cap | EES hit | EES not hit | legal | collateral | med in | med out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full/verbose | 64 | 0.23 | 0.80 | 0.58 | 4 | 0.00 | 0.25 | 0.77 | 0.86 | 26796 | 615 |
| graph_seg/verbose | 64 | 0.31 | 0.81 | 0.69 | 1 | 0.00 | 0.32 | 0.67 | 0.75 | 3948 | 609 |
| frontier_exec/verbose | 64 | 0.31 | 0.82 | 0.65 | 4 | 0.00 | 0.33 | 0.81 | 0.56 | 5560 | 660 |
- frontier_exec/verbose − full/verbose: EES +0.08 [-0.06, +0.22] n=64; affected F1 +0.02 [-0.06, +0.09] n=64; value acc +0.07 [-0.05, +0.19] n=64
- frontier_exec/verbose − graph_seg/verbose: EES +0.00 [-0.16, +0.16] n=64; affected F1 +0.01 [-0.06, +0.08] n=64; value acc -0.04 [-0.17, +0.09] n=64
- graph_seg/verbose − full/verbose: EES +0.08 [-0.08, +0.23] n=64; affected F1 +0.01 [-0.05, +0.07] n=64; value acc +0.11 [-0.03, +0.24] n=64

### travel c100, prompt v1, cap 16384

| arm | n | EES | affected F1 | value acc | hit cap | EES hit | EES not hit | legal | collateral | med in | med out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full/verbose | 64 | 0.14 | 0.71 | 0.38 | 3 | 0.00 | 0.15 | 0.73 | 1.02 | 26860 | 584 |
| graph_seg/verbose | 64 | 0.34 | 0.84 | 0.64 | 0 | — | 0.34 | 0.75 | 0.75 | 3966 | 594 |
| frontier_exec/verbose | 64 | 0.23 | 0.77 | 0.64 | 2 | 0.00 | 0.24 | 0.69 | 0.92 | 6223 | 638 |
- frontier_exec/verbose − full/verbose: EES +0.09 [-0.03, +0.20] n=64; affected F1 +0.06 [-0.01, +0.13] n=64; value acc +0.26 [+0.14, +0.38] n=64
- frontier_exec/verbose − graph_seg/verbose: EES -0.11 [-0.25, +0.03] n=64; affected F1 -0.07 [-0.13, -0.01] n=64; value acc -0.01 [-0.15, +0.14] n=64
- graph_seg/verbose − full/verbose: EES +0.20 [+0.06, +0.34] n=64; affected F1 +0.13 [+0.06, +0.20] n=64; value acc +0.26 [+0.12, +0.41] n=64

### travel c100, prompt v2, cap 16384

| arm | n | EES | affected F1 | value acc | hit cap | EES hit | EES not hit | legal | collateral | med in | med out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full/verbose | 64 | 0.09 | 0.37 | 0.17 | 40 | 0.00 | 0.25 | 0.88 | 0.27 | 69379 | 16389 |
| graph_seg/verbose | 64 | 0.59 | 0.86 | 0.71 | 6 | 0.17 | 0.64 | 0.97 | 0.20 | 4360 | 1490 |
| frontier_exec/verbose | 64 | 0.38 | 0.74 | 0.53 | 13 | 0.08 | 0.45 | 0.94 | 0.20 | 6774 | 2855 |
- frontier_exec/verbose − full/verbose: EES +0.28 [+0.16, +0.41] n=64; affected F1 +0.37 [+0.25, +0.49] n=64; value acc +0.36 [+0.23, +0.49] n=64
- frontier_exec/verbose − graph_seg/verbose: EES -0.22 [-0.38, -0.06] n=64; affected F1 -0.12 [-0.25, -0.01] n=64; value acc -0.18 [-0.34, -0.03] n=64
- graph_seg/verbose − full/verbose: EES +0.50 [+0.36, +0.64] n=64; affected F1 +0.50 [+0.37, +0.62] n=64; value acc +0.54 [+0.43, +0.66] n=64

### travel 500, prompt v1, cap 16384

| arm | n | EES | affected F1 | value acc | hit cap | EES hit | EES not hit | legal | collateral | med in | med out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full/verbose | 64 | 0.08 | 0.73 | 0.42 | 8 | 0.00 | 0.09 | 0.70 | 0.78 | 122530 | 646 |
| graph_seg/verbose | 64 | 0.39 | 0.86 | 0.71 | 1 | 0.00 | 0.40 | 0.80 | 0.47 | 4145 | 655 |
| frontier_exec/verbose | 64 | 0.17 | 0.82 | 0.51 | 2 | 0.00 | 0.18 | 0.75 | 0.83 | 16698 | 621 |
- frontier_exec/verbose − full/verbose: EES +0.09 [+0.03, +0.17] n=64; affected F1 +0.09 [+0.03, +0.16] n=64; value acc +0.10 [+0.02, +0.18] n=64
- frontier_exec/verbose − graph_seg/verbose: EES -0.22 [-0.36, -0.09] n=64; affected F1 -0.04 [-0.10, +0.03] n=64; value acc -0.20 [-0.32, -0.08] n=64
- graph_seg/verbose − full/verbose: EES +0.31 [+0.19, +0.44] n=64; affected F1 +0.13 [+0.06, +0.22] n=64; value acc +0.30 [+0.19, +0.41] n=64

### travel 500, prompt v2, cap 16384

| arm | n | EES | affected F1 | value acc | hit cap | EES hit | EES not hit | legal | collateral | med in | med out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full/verbose | 64 | 0.09 | 0.34 | 0.23 | 46 | 0.04 | 0.22 | 0.86 | 0.34 | 258092 | 16389 |
| graph_seg/verbose | 64 | 0.42 | 0.78 | 0.59 | 9 | 0.11 | 0.47 | 0.94 | 0.23 | 4560 | 1353 |
| frontier_exec/verbose | 64 | 0.27 | 0.52 | 0.42 | 32 | 0.03 | 0.50 | 0.86 | 0.20 | 31130 | 16304 |
- frontier_exec/verbose − full/verbose: EES +0.17 [+0.06, +0.28] n=64; affected F1 +0.18 [+0.04, +0.31] n=64; value acc +0.19 [+0.06, +0.31] n=64
- frontier_exec/verbose − graph_seg/verbose: EES -0.16 [-0.33, +0.02] n=64; affected F1 -0.26 [-0.40, -0.12] n=64; value acc -0.17 [-0.33, -0.01] n=64
- graph_seg/verbose − full/verbose: EES +0.33 [+0.19, +0.47] n=64; affected F1 +0.44 [+0.30, +0.56] n=64; value acc +0.36 [+0.21, +0.50] n=64

### travel: same arm across prompt / cap (paired on episodes)

- c100 full: v2/16384 − v1/16384: -0.05 [-0.12, +0.03] n=64
- 500 full: v2/16384 − v1/16384: +0.02 [-0.06, +0.09] n=64
