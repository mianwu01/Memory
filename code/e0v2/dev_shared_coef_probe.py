"""Dev-seed (99) probe behind a design decision: with ONE coefficient per edge shared across
regimes, the write and read gates of Regime-GRACE never open (the near-deterministic hold rows
pin the shared weight to zero).  This script trains the hierarchical and independent gate
variants and prints the read gate, its weight and sigma every 10 epochs.  It uses the current
GatedModel (regime-specific coefficients), so it now shows the gates opening; swap ``w[..., kk]``
for a shared ``w`` in gated.py to reproduce the failure.
Usage: python3 code/e0v2/dev_shared_coef_probe.py
"""
import sys, os, math; sys.path.insert(0, "code"); os.environ["E0V2_THREADS"] = "4"
import numpy as np, torch
from e0v2 import scm, gated
cfg = scm.Config(sigma_hold=0.01); X, u, info = scm.generate(cfg, 10000, seed=99)
n = cfg.n; xlag, y, uu, sd = gated._prepare(X, u, 1)
RA = scm.RIDX["read_A"]; m1, y1 = scm.M[0], scm.Y[0]
for tag, kw in [("regime-hier", dict(regime_gates=True, hierarchical=True)),
                ("regime-indep", dict(regime_gates=True, hierarchical=False))]:
    torch.manual_seed(0)
    model = gated.GatedModel(n, 1, scm.K, nonlinear=False, hidden=16, mask=None, use_u_stats=True, **kw)
    lam = 0.167; N = xlag.shape[0]; batch = 256; steps = math.ceil(N / batch)
    opt = torch.optim.Adam(model.parameters(), lr=1e-2)
    print(tag)
    for ep in range(60):
        model.train(); perm = torch.randperm(N); tot = 0
        for s in range(steps):
            idx = perm[s*batch:(s+1)*batch]
            mu, sig = model(xlag[idx], uu[idx])
            nll = (((y[idx]-mu)**2)/(2*sig**2) + torch.log(sig)).sum(1).mean()
            loss = nll + lam/steps*model.l0(); opt.zero_grad(); loss.backward(); opt.step(); tot += loss.item()
        if ep % 10 == 0 or ep == 59:
            model.eval(); g = model.gate_values()
            with torch.no_grad():
                la = model.log_alpha()
                print(f"  ep{ep:3d} loss={tot/steps:.3f} z(m1->y1|readA)={g[m1,0,y1,RA]:.3f} la={la[m1,0,y1,RA]:.2f} "
                      f"w={model.w[m1,0,y1,RA].item():.3f} sig(y1|readA)={math.exp(model.log_sigma[y1,RA].item()):.3f} "
                      f"z(m1->m1|hold)={g[m1,0,m1,scm.RIDX['hold']]:.3f} z(c1->m1|writeA)={g[0,0,m1,1]:.3f} "
                      f"mean z readA row y1={g[:,0,y1,RA].mean():.3f}")
