"""Official UnCLe (NeurIPS 2025) on frozen HM3 randomized read panels.

Imports an external checkout; does not vendor its unlicensed research code.
Uses fixed top-k curves, never its ground-truth-optimized graph threshold.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import importlib.util
import importlib.metadata
import json
import os
import platform
from pathlib import Path
import subprocess
import time

import numpy as np

from .domains import get_domain
from .generate import generate_split
from .grace_logs import pcmci_skeleton
from .read_gate_tcd import empirical_effects, panel
from .replay import ExecutorOracle
from .structure_alignment import matched_records


@contextmanager
def working_directory(path):
    previous = Path.cwd()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(previous)


def main(args):
    import torch
    import tiktoken
    from sklearn.metrics import average_precision_score
    torch.set_num_threads(2)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    checkout = Path(args.checkout).resolve()
    source = checkout / "bin/experimental_utils.py"
    spec = importlib.util.spec_from_file_location("official_uncle", source)
    official = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(official)
    sha = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
    if sha != "820da2a7690e8528ecf8d346cd44545624dfe85b":
        raise ValueError("UnCLe source revision differs from frozen protocol")
    encoding = tiktoken.get_encoding("cl100k_base")
    domain = get_domain("travel")
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    run_dir = out.parent / (out.stem + "_training")
    run_dir.mkdir(parents=True, exist_ok=True)
    result = {"config": vars(args), "source_commit": sha,
              "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
              "runtime": {"python": platform.python_version(),
                          "packages": {p: importlib.metadata.version(p) for p in ("torch", "tsai", "fastai", "tigramite")},
                          "device": torch.cuda.get_device_name(0) if args.device == "cuda" else "cpu"},
              "scope": "fixed-executor randomized read dependence; UnCLe summary scores, not identified lag-1 causal edges", "episodes": []}
    for index, ep in enumerate(generate_split(domain, args.seed, args.split, args.episodes)):
        start = time.monotonic()
        records = [r["rid"] for r in ep.H]
        oracle = ExecutorOracle(domain, ep)
        X, _, outcomes = panel(oracle, records, 512, 20260921+index)
        X = X[1:]
        names = [f"g{i}" for i in range(len(records))] + ["decision_correct"]
        # Exact official entry point, architecture and optimizer; no custom training loop.
        with working_directory(run_dir):
            permutation, parameter = official.run_unicsl(
                X, .0003, args.reconstruction_epochs, args.joint_epochs,
                ep.id, args.device == "cuda", 0, 0, 6, 20, 8)
        arrays = {"uncle_permutation": np.asarray(permutation), "uncle_parameter": np.asarray(parameter)}
        assert all(a.shape == (len(names), len(names)) and np.isfinite(a).all() for a in arrays.values())
        skel = pcmci_skeleton([X], names, 1, pc_alpha=.05, test="gsquared")
        rng = np.random.default_rng(20260921+10000+index)
        effects = empirical_effects(oracle, records, rng.random((64, len(records))) < .8)
        labels = np.asarray(effects) > 0
        methods = {}
        for name, graph in arrays.items():
            scores = graph[:-1, -1]
            ranking = np.argsort(-scores, kind="stable")
            curve = {}
            for k in (2, 4, 8):
                selected = [records[i] for i in ranking[:k]]
                reference = {"objects": sorted(ep.S0.objects), "records": selected}
                controls = {}
                for seed in (17, 29, 43):
                    reads, stats = matched_records(ep, reference, [], seed, encoding)
                    controls[str(seed)] = {"correct": bool(oracle(reads["records"])), "records": reads["records"], **stats}
                curve[str(k)] = {"records": selected, "correct": bool(oracle(selected)), "matched_random": controls}
            methods[name] = {"scores": dict(zip(names[:-1], scores.tolist())),
                             "empirical_effect_AP": float(average_precision_score(labels, scores)) if labels.any() else None,
                             "topk": curve, "full_summary_matrix_cause_effect": graph.tolist()}
        pcmci_reads = [records[i] for i in range(len(records)) if skel[i, -1, 1]]
        row = {"episode": ep.id, "n_records": len(records), "gate_to_record": dict(zip(names[:-1], records)),
               "panel_sha256": hashlib.sha256(X.tobytes()).hexdigest(), "train_success_rate": float(outcomes.mean()),
               "heldout_flip_effects": dict(zip(names[:-1], effects)), "methods": methods,
               "pcmci_g2": {"records": pcmci_reads, "correct": bool(oracle(pcmci_reads)),
                            "spurious_gate_target_edges": int(skel[:, :-1, 1].sum())},
               "seconds": time.monotonic()-start, "unique_executor_contexts": len(oracle.cache)}
        result["episodes"].append(row)
        out.write_text(json.dumps(result, indent=2)+"\n")
        print(json.dumps({"episode": ep.id, "seconds": row["seconds"],
                          "methods": {n: {"ap": m["empirical_effect_AP"], "correct_topk": {k: c["correct"] for k, c in m["topk"].items()}} for n, m in methods.items()},
                          "pcmci_g2": row["pcmci_g2"]}), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--checkout", required=True)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--split", choices=["dev", "test"], default="dev")
    p.add_argument("--episodes", type=int, default=3)
    p.add_argument("--device", choices=["cpu", "cuda"], default="cuda")
    p.add_argument("--reconstruction-epochs", type=int, default=1000)
    p.add_argument("--joint-epochs", type=int, default=2000)
    p.add_argument("--out", default="results/development/hm3/alignment/uncle_dev.json")
    main(p.parse_args())
