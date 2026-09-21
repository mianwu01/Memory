"""E1 (length): read-intervention discovery on augmented training histories.  Replays per episode should grow
as log n while the frontier size stays flat.  Output: results/development/hm3/replay/length_<domain>.json"""
from __future__ import annotations
import argparse, json, time
from pathlib import Path
import numpy as np
from .domains import get_domain
from .generate import generate_split
from .scaling import augment_split
from .replay import discover, ExecutorOracle

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--domains", nargs="+", default=["travel", "shopping32"])
    ap.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2])
    ap.add_argument("--n_train", type=int, default=60)
    ap.add_argument("--lengths", nargs="+", default=["native", "100:abcd", "500:abcd"])
    ap.add_argument("--out", default="../results/development/hm3/replay")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    for dom in a.domains:
        d = get_domain(dom)
        res = {}
        for seed in a.seeds:
            train = generate_split(d, seed + 100, "train", a.n_train)
            for L in a.lengths:
                eps = train
                if L != "native":
                    target, mix = L.split(":")
                    eps, _ = augment_split(d, train, int(target), mix, f"train{seed}")
                t0 = time.time()
                sets = discover(d, eps, lambda ep: ExecutorOracle(d, ep))
                ok = [s for s in sets if s["full_ok"]]
                res[f"seed{seed}/{L}"] = {"episodes": len(eps), "full_ok": len(ok),
                                          "n_records": float(np.mean([s["n"] for s in ok])),
                                          "frontier": float(np.mean([len(s["frontier"]) for s in ok])),
                                          "calls": float(np.mean([s["calls"] for s in ok])),
                                          "calls_p90": float(np.percentile([s["calls"] for s in ok], 90)),
                                          "seconds": time.time() - t0}
                print(dom, f"seed{seed}/{L}", res[f"seed{seed}/{L}"], flush=True)
        json.dump(res, open(out / f"length_{dom}.json", "w"), indent=1)

if __name__ == "__main__":
    main()
