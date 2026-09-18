"""Fit the existing Travel estimator on history-resolved, train-only requirements."""
from __future__ import annotations

import json
from pathlib import Path
import sys

from faithful_memory import ROOT, environment


def main():
    environment()
    import travel_grace_discovery as discovery
    from datasets import load_dataset
    from travel_implicit import training_rows
    excluded = [101, *range(111, 161)]
    dataset = load_dataset("ZexueHe/memoryarena", "group_travel_planner")
    split = "test" if "test" in dataset else next(iter(dataset))
    raw = [dict(row) for row in dataset[split]]
    train = [r for r in raw if int(r["id"]) not in excluded]
    resolved = training_rows(train, variant="implicit")
    folder = ROOT / "results/development/autodl_20260918/graph"
    folder.mkdir(parents=True, exist_ok=True)
    manifest = {"excluded_episode_ids": excluded, "train_ids": [int(r["id"]) for r in train],
                "n_train": len(train), "source": "history-resolved training requirements; no evaluation outcomes or evaluation queries used for fitting",
                "method": "existing GRACE refinement with PCMCI skeleton; ind encoding, lag<=3, 60 epochs, CPU"}
    (folder / "training_manifest.json").write_text(json.dumps(manifest, indent=2))
    episodes = [discovery.parse_episode(r) for r in resolved]
    discovery.load_episodes = lambda n=None, exclude_ids=None: episodes[:n] if n else episodes
    sys.argv = ["travel_grace_discovery.py", "--spec", "ind", "--export_spec", "ind",
                "--max_epochs", "60", "--exclude_ids", *map(str, excluded),
                "--out", str(folder / "typegraph.json"), "--export", str(folder / "plugin_graph.json")]
    discovery.main()


if __name__ == "__main__":
    main()
