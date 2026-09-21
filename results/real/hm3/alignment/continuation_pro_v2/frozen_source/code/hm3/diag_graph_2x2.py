"""Diagnostic panel for P2: graph EES under {native-fit, condition-fit} x {as-run estimates, real-record-only estimates}.
Real-only estimates use the ground-truth foreign rid prefix and are a diagnostic, never a method arm."""
import sys, json; sys.path.insert(0, "code")
from hm3.domains import get_domain
from hm3.generate import generate_split
from hm3.learners import LearnedGraph
from hm3.run_det import evaluate_learner
from hm3.scaling import augment_split
from hm3.run_scaling import CONDITIONS
dom_name, out = sys.argv[1], sys.argv[2]; seeds = [int(s) for s in sys.argv[3:]]
domain = get_domain(dom_name); orig = domain.infer_params
def real_only(H, S0, prov=None):
    H2 = [r for r in H if not str(r.get("rid", "")).startswith("x")]
    return orig(H2, S0, prov) if prov is not None else orig(H2, S0)
res = {}
for seed in seeds:
    train0 = generate_split(domain, seed, "train", 200); eval0 = generate_split(domain, seed, "dev", 60)
    gN = LearnedGraph(); gN.fit(domain, train0)
    base = {r["episode"]: r["ees"] for r in evaluate_learner(domain, gN, eval0)["rows"]}
    for cond, (target, mix) in CONDITIONS.items():
        if cond == "native": continue
        trainA, st = augment_split(domain, train0, target, mix, f"train{seed}"); evalA, se = augment_split(domain, eval0, target, mix, f"dev{seed}")
        gA = LearnedGraph(); gA.fit(domain, trainA)
        cell = {"train_dropped": st["dropped"], "eval_dropped": se["dropped"]}
        for est_mode in ("asrun", "realonly"):
            domain.infer_params = orig if est_mode == "asrun" else real_only
            if est_mode == "realonly":
                gNr = LearnedGraph(); gNr.fit(domain, train0); gAr = LearnedGraph(); gAr.fit(domain, trainA)
            else:
                gNr, gAr = gN, gA
            for fit_name, g in (("fitN", gNr), ("fitA", gAr)):
                rows = {r["episode"]: r["ees"] for r in evaluate_learner(domain, g, evalA)["rows"]}
                paired = [(base[e], rows[e]) for e in rows if e in base]
                cell[f"{fit_name}/{est_mode}"] = {"ees": sum(b for _, b in paired) / len(paired), "n": len(paired),
                                                  "T->F": sum(1 for a, b in paired if a and not b), "F->T": sum(1 for a, b in paired if b and not a)}
            domain.infer_params = orig
        res[f"{dom_name}/seed{seed}/{cond}"] = cell
        print(f"{dom_name}/seed{seed}/{cond:5s} drop(train,eval)=({st['dropped']},{se['dropped']}) " + " ".join(f"{k} {v['ees']:.3f}(-{v['T->F']}/+{v['F->T']})" for k, v in cell.items() if isinstance(v, dict)), flush=True)
        json.dump(res, open(out, "w"), indent=1)
