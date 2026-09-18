"""Dev-seed (99) lambda selection for the gate arms: held-out NLL over lambda scales.
Output kept in results/e0v2/dev/lambda_select_seed99.log; the design doc froze scale 0.5.
Usage: E0V2_PYLIB=<pylib> python3 code/e0v2/dev_lambda_select.py
"""
import sys, os; sys.path.insert(0, "code"); os.environ["E0V2_THREADS"] = "3"
import numpy as np
from e0v2 import scm, metrics, gated
cfg = scm.Config(sigma_hold=0.01); X, u, info = scm.generate(cfg, 10000, seed=99)
truth, etype = scm.ground_truth(cfg); mem = scm.memory_targets(cfg)
for mode, hier in [("regime", False), ("pooled", True), ("per_regime", True)]:
    for scale in (0.125, 0.25, 0.5, 1.0, 2.0):
        est = gated.fit_gated(X, u, mode=mode, hierarchical=hier, lambda_scale=scale, seed=0, holdout_frac=0.2)
        ev = metrics.evaluate(truth, etype, est, mem)
        print(f"{est.name:20s} scale={scale:<5} lam={est.info['lambda_l0']:.4f} val_nll={est.info.get('val_nll', float('nan')):8.3f} "
              f"{est.info['runtime_s']:5.1f}s edge F1={ev['edge']['F1']:.3f} cell F1={ev['cell']['F1']:.3f} cell_mem F1={ev['cell_mem']['F1']:.3f} "
              f"(P={ev['cell_mem']['P']:.2f} R={ev['cell_mem']['R']:.2f}) read_cell={ev['recall_cell_read']} dist_cell={ev['recall_cell_distractor']} fp_cells={ev['cell']['fp']}", flush=True)
