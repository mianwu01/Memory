"""E0 v2 synthetic memory system.

Observed variables (index layout is fixed, see ``Config.var_names``):

    c1..c4   cues (fresh noise every step)
    m1..m4   memory slots
    y1, y2   readouts
    q1, q2   query context (fresh noise every step)
    d1..dN   distractors, a stable VAR(1) that never depends on the regime

Regime label u_t (observed, one per step):

    idle     memory slots are reset to noise (expiry); nothing is read
    write_A  c1(t-1) -> m1(t),  c2(t-1) -> m2(t);   slots 3,4 hold
    write_B  c3(t-1) -> m3(t),  c4(t-1) -> m4(t);   slots 1,2 hold
    hold     m_i(t) = m_i(t-1) + sigma_hold * eps   for every slot
    read_A   y1(t) = 1.0 m1(t-1) + 0.8 m3(t-1) + 0.5 q1(t-1) + eps;  all slots hold
    read_B   y2(t) = 0.8 m2(t-1) + 1.0 m4(t-1) + 0.5 q2(t-1) + eps;  all slots hold

Every cross-variable mechanism is lag 1, so nothing in the ground truth is
contemporaneous.  The schedule inside an episode is random: an idle prefix, a
write of a random type, optionally a second write (which overwrites when it
repeats the type), a hold of random length, a read of random type, optionally a
second read.  The ground truth is the table

    coef[i, lag-1, j, u]  =  a_ijl * g_ijl(u)

and an edge is "gated" exactly when that row is non-zero in some regimes and
zero in others.  ``mechanism="mlp"`` replaces the write and read maps by fixed
random tanh networks with the same parent sets; the gate table is then binary.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List, Tuple

import numpy as np

REGIMES = ["idle", "write_A", "write_B", "hold", "read_A", "read_B"]
RIDX = {r: k for k, r in enumerate(REGIMES)}
K = len(REGIMES)
LIVE = ("write_A", "write_B", "hold", "read_A", "read_B")

C = (0, 1, 2, 3)
M = (4, 5, 6, 7)
Y = (8, 9)
Q = (10, 11)
D0 = 12
WRITE_SLOTS = {"write_A": (0, 1), "write_B": (2, 3)}
# read regime -> (readout index, {slot: coef}, {query: coef})
READ_SPEC = {"read_A": (0, {0: 1.0, 2: 0.8}, {0: 0.5}),
             "read_B": (1, {1: 0.8, 3: 1.0}, {1: 0.5})}
MECH_SEED = 12345          # fixed mechanism parameters for mechanism="mlp"


@dataclass
class Config:
    n_dist: int = 20
    sigma_hold: float = 0.01
    sigma_write: float = 0.05
    sigma_read: float = 0.1
    sigma_dist: float = 0.5
    idle_range: Tuple[int, int] = (1, 3)
    delta_range: Tuple[int, int] = (3, 15)     # hold length before a read
    gap_range: Tuple[int, int] = (1, 8)        # hold length between two writes / reads
    p_second_write: float = 0.5
    p_second_read: float = 0.3
    mechanism: str = "linear"                  # "linear" | "mlp"
    dist_self: float = 0.5
    dist_cross: float = 0.3

    @property
    def n(self) -> int:
        return 12 + self.n_dist

    def var_names(self) -> List[str]:
        return ([f"c{i + 1}" for i in range(4)] + [f"m{i + 1}" for i in range(4)]
                + ["y1", "y2", "q1", "q2"] + [f"d{i + 1}" for i in range(self.n_dist)])

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- #
# schedule
# --------------------------------------------------------------------------- #
def sample_episode(rng: np.random.Generator, cfg: Config) -> List[str]:
    def U(rg):
        return int(rng.integers(rg[0], rg[1] + 1))
    seq = ["idle"] * U(cfg.idle_range)
    seq.append(str(rng.choice(["write_A", "write_B"])))
    if rng.random() < cfg.p_second_write:
        seq += ["hold"] * U(cfg.gap_range)
        seq.append(str(rng.choice(["write_A", "write_B"])))
    seq += ["hold"] * U(cfg.delta_range)
    seq.append(str(rng.choice(["read_A", "read_B"])))
    if rng.random() < cfg.p_second_read:
        seq += ["hold"] * U(cfg.gap_range)
        seq.append(str(rng.choice(["read_A", "read_B"])))
    return seq


def sample_schedule(rng: np.random.Generator, cfg: Config, T: int) -> Tuple[np.ndarray, int]:
    labels: List[int] = []
    n_ep = 0
    while len(labels) < T:
        labels += [RIDX[r] for r in sample_episode(rng, cfg)]
        n_ep += 1
    return np.asarray(labels[:T], dtype=np.int64), n_ep


# --------------------------------------------------------------------------- #
# distractor VAR(1) and MLP mechanisms
# --------------------------------------------------------------------------- #
def distractor_matrix(cfg: Config) -> np.ndarray:
    """A[src, dst] for the distractor block: self persistence plus d_{k+1} -> d_k."""
    A = np.zeros((cfg.n_dist, cfg.n_dist))
    for k in range(cfg.n_dist):
        A[k, k] = cfg.dist_self
        if k % 2 == 1:
            A[k, k - 1] = cfg.dist_cross
    return A


class _MLP:
    """Fixed random tanh network f: R^p -> R with unit output scale."""

    def __init__(self, rng, p, hidden=8, gain=1.5):
        self.W1 = rng.normal(size=(p, hidden)) * gain / np.sqrt(p)
        self.b1 = rng.normal(size=hidden) * 0.5
        self.W2 = rng.normal(size=hidden) / np.sqrt(hidden)
        z = rng.normal(size=(4000, p))
        out = np.tanh(z @ self.W1 + self.b1) @ self.W2
        self.mu, self.sd = out.mean(), out.std() + 1e-8

    def __call__(self, x):
        return (np.tanh(x @ self.W1 + self.b1) @ self.W2 - self.mu) / self.sd


def mlp_mechanisms(cfg: Config):
    rng = np.random.default_rng(MECH_SEED)
    return {"write": [_MLP(rng, 1) for _ in range(4)],
            "read_A": _MLP(rng, 3), "read_B": _MLP(rng, 3)}


# --------------------------------------------------------------------------- #
# generator
# --------------------------------------------------------------------------- #
def generate(cfg: Config, T: int, seed: int):
    """Return X [T, n], u [T] (regime index), and schedule info."""
    rng = np.random.default_rng(seed)
    n = cfg.n
    u, n_ep = sample_schedule(rng, cfg, T)
    A = distractor_matrix(cfg)
    D = slice(D0, D0 + cfg.n_dist)
    mlp = mlp_mechanisms(cfg) if cfg.mechanism == "mlp" else None
    X = np.zeros((T, n))
    X[0] = rng.normal(size=n)
    for t in range(1, T):
        p = X[t - 1]
        r = REGIMES[u[t]]
        x = rng.normal(size=n)                      # every variable starts as fresh noise
        x[D] = p[D] @ A + cfg.sigma_dist * x[D]
        if r != "idle":
            written = WRITE_SLOTS.get(r, ())
            for s in range(4):
                if s in written:
                    src = p[C[s]]
                    val = mlp["write"][s](np.array([[src]]))[0] if mlp else src
                    x[M[s]] = val + cfg.sigma_write * x[M[s]]
                else:
                    x[M[s]] = p[M[s]] + cfg.sigma_hold * x[M[s]]
            if r in READ_SPEC:
                yi, ms, qs = READ_SPEC[r]
                if mlp:
                    inp = np.array([[p[M[s]] for s in sorted(ms)] + [p[Q[qi]] for qi in sorted(qs)]])
                    val = mlp[r](inp)[0]
                else:
                    val = sum(a * p[M[s]] for s, a in ms.items()) + sum(a * p[Q[qi]] for qi, a in qs.items())
                x[Y[yi]] = val + cfg.sigma_read * x[Y[yi]]
        X[t] = x
    info = {"n_episodes": n_ep,
            "regime_counts": {r: int((u == k).sum()) for r, k in RIDX.items()},
            "p_read": float(np.isin(u, [RIDX["read_A"], RIDX["read_B"]]).mean())}
    return X, u, info


# --------------------------------------------------------------------------- #
# ground truth
# --------------------------------------------------------------------------- #
def ground_truth(cfg: Config):
    """coef[i, 0, j, u] for lag 1 (lag axis has length 1) and an edge-type map."""
    n = cfg.n
    coef = np.zeros((n, 1, n, K))
    etype: Dict[Tuple[int, int, int], str] = {}
    for s in range(4):
        wr = "write_A" if s < 2 else "write_B"
        coef[C[s], 0, M[s], RIDX[wr]] = 1.0
        etype[(C[s], M[s], 1)] = "write"
        for r in LIVE:
            if r != wr:
                coef[M[s], 0, M[s], RIDX[r]] = 1.0
        etype[(M[s], M[s], 1)] = "hold"
    for r, (yi, ms, qs) in READ_SPEC.items():
        for s, a in ms.items():
            coef[M[s], 0, Y[yi], RIDX[r]] = a
            etype[(M[s], Y[yi], 1)] = "read"
        for qi, a in qs.items():
            coef[Q[qi], 0, Y[yi], RIDX[r]] = a
            etype[(Q[qi], Y[yi], 1)] = "read"
    A = distractor_matrix(cfg)
    for src in range(cfg.n_dist):
        for dst in range(cfg.n_dist):
            if A[src, dst] != 0:
                coef[D0 + src, 0, D0 + dst, :] = A[src, dst]
                etype[(D0 + src, D0 + dst, 1)] = "distractor"
    if cfg.mechanism == "mlp":
        # only the gate is defined; mark active cells with 1.0
        for (i, j, l), t in etype.items():
            if t in ("write", "read"):
                coef[i, l - 1, j, :] = (coef[i, l - 1, j, :] != 0).astype(float)
    return coef, etype


def memory_targets(cfg: Config) -> np.ndarray:
    """Boolean mask over variables: the memory system's own targets (slots + readouts)."""
    mask = np.zeros(cfg.n, bool)
    mask[list(M) + list(Y)] = True
    return mask


if __name__ == "__main__":
    cfg = Config()
    X, u, info = generate(cfg, 10000, seed=0)
    coef, etype = ground_truth(cfg)
    print(info)
    print("true edges:", len(etype), {t: sum(1 for v in etype.values() if v == t)
                                       for t in ("write", "hold", "read", "distractor")})
    print("true cells:", int((coef != 0).sum()))
