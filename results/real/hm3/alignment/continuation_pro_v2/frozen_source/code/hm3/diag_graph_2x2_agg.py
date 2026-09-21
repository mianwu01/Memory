import json, sys, collections
for path in sys.argv[1:]:
    d = json.load(open(path)); dom = list(d)[0].split("/")[0]
    conds = ["50", "100", "500", "a100", "b100", "c100", "d100"]
    cells = ["fitN/asrun", "fitA/asrun", "fitN/realonly", "fitA/realonly"]
    print(f"\n#### {dom}: graph EES, mean over seeds (paired episodes; native graph on native episodes = row 0)\n")
    print("| fit / estimates | " + " | ".join(conds) + " |"); print("|---|" + "---:|" * len(conds))
    for c in cells:
        row = []
        for cond in conds:
            vals = [v[c]["ees"] for k, v in d.items() if k.endswith("/" + cond) and c in v]
            row.append(f"{sum(vals)/len(vals):.3f}" if vals else "—")
        print(f"| {c} | " + " | ".join(row) + " |")
    row = []
    for cond in conds:
        vals = [(v["train_dropped"], v["eval_dropped"]) for k, v in d.items() if k.endswith("/" + cond)]
        row.append("/".join(f"{sum(x[i] for x in vals)/len(vals):.1f}" for i in (0, 1)) if vals else "—")
    print("| dropped train/eval (mean) | " + " | ".join(row) + " |")
    nat = collections.OrderedDict()
