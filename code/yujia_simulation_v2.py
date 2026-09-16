"""Multi-seed SCM/MLP simulation required by the Yujia experiment storyline.

The benchmark owns the complete data-generating process and typed gold parent
sets.  It compares pooled discovery with a regime-conditioned nonlinear
estimator on linear, nonlinear-MLP and latent-confounded families.  The latent
family is intentionally reported in two ways: observed-only (where the hidden
parent is not identifiable) and a grouped-proxy fallback that turns two noisy
measurements into one controlled variable group.

This is a CPU-only simulation result, not an agent benchmark and not evidence
that latent causal variables were recovered from raw language.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.inspection import permutation_importance


VARIABLES = ("c", "m", "y", "d1", "d2", "p1", "p2")
INDEX = {name: index for index, name in enumerate(VARIABLES)}
REGIME = {"idle": 0, "write": 1, "hold": 2, "read": 3}
FAMILIES = ("linear_observed", "mlp_observed", "mlp_latent")


def generate(
    family: str,
    *,
    episodes: int = 240,
    delta: int = 10,
    seed: int = 0,
) -> dict[str, Any]:
    """Generate independent write-hold-read trajectories with known mechanisms."""

    if family not in FAMILIES:
        raise ValueError(family)
    rng = np.random.default_rng(seed)
    length = delta + 9
    trajectories: list[np.ndarray] = []
    regimes: list[np.ndarray] = []
    latent: list[np.ndarray] = []
    nonlinear = family != "linear_observed"
    has_latent = family == "mlp_latent"

    for _ in range(episodes):
        x = np.zeros((length, len(VARIABLES)), dtype=float)
        h = np.zeros(length, dtype=float)
        u = np.zeros(length, dtype=int)
        write_t, read_t = 4, 4 + delta
        u[write_t] = REGIME["write"]
        u[write_t + 1 : read_t] = REGIME["hold"]
        u[read_t] = REGIME["read"]
        for t in range(length):
            previous = x[t - 1] if t else np.zeros(len(VARIABLES))
            previous_h = h[t - 1] if t else 0.0
            h[t] = 0.72 * previous_h + rng.normal(scale=0.55)
            x[t, INDEX["c"]] = rng.normal()
            x[t, INDEX["d1"]] = 0.64 * previous[INDEX["d1"]] + rng.normal(scale=0.45)
            x[t, INDEX["d2"]] = (
                0.52 * previous[INDEX["d2"]]
                + 0.24 * previous[INDEX["d1"]]
                + rng.normal(scale=0.45)
            )
            x[t, INDEX["p1"]] = h[t] + rng.normal(scale=0.18)
            x[t, INDEX["p2"]] = np.tanh(h[t]) + rng.normal(scale=0.18)

            if t == write_t:
                cue = previous[INDEX["c"]]
                signal = np.tanh(1.35 * cue + 0.35 * cue * cue) if nonlinear else cue
                x[t, INDEX["m"]] = signal + rng.normal(scale=0.06)
            elif write_t < t <= read_t:
                x[t, INDEX["m"]] = 0.96 * previous[INDEX["m"]] + rng.normal(scale=0.025)
            else:
                x[t, INDEX["m"]] = rng.normal()

            if t == read_t:
                memory = previous[INDEX["m"]]
                distractor = previous[INDEX["d1"]]
                if nonlinear:
                    signal = np.tanh(
                        1.15 * memory
                        + 0.70 * distractor
                        + 0.30 * memory * distractor
                    )
                else:
                    signal = memory + 0.55 * distractor
                if has_latent:
                    signal += 0.75 * previous_h
                x[t, INDEX["y"]] = signal + rng.normal(scale=0.08)
            else:
                x[t, INDEX["y"]] = rng.normal()
        trajectories.append(x)
        regimes.append(u)
        latent.append(h)
    return {
        "family": family,
        "trajectories": np.stack(trajectories),
        "regimes": np.stack(regimes),
        "latent": np.stack(latent),
        "gold": {
            "write": ["c"],
            "hold": ["m"],
            "read_observed": ["m", "d1"],
            "read_latent": ["h"] if has_latent else [],
            "read_grouped": ["m", "d1", "h_group"] if has_latent else ["m", "d1"],
        },
    }


def _rows(
    data: dict[str, Any], mechanism: str, *, pooled: bool, grouped: bool
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    trajectories = data["trajectories"]
    regimes = data["regimes"]
    regime_id = REGIME[mechanism]
    target = "y" if mechanism == "read" else "m"
    # Every feature is lagged by one step, so the target's own name is a valid
    # autoregressive parent (the memory hold edge m[t-1] -> m[t]).
    features = list(VARIABLES)
    rows: list[np.ndarray] = []
    targets: list[float] = []
    for trajectory, episode_regimes in zip(trajectories, regimes):
        for t in range(1, len(trajectory)):
            if not pooled and episode_regimes[t] != regime_id:
                continue
            previous = trajectory[t - 1]
            values = [previous[INDEX[name]] for name in features]
            if grouped:
                keep = [index for index, name in enumerate(features) if name not in {"p1", "p2"}]
                values = [values[index] for index in keep] + [
                    0.5 * (previous[INDEX["p1"]] + previous[INDEX["p2"]])
                ]
                names = [features[index] for index in keep] + ["h_group"]
            else:
                names = list(features)
            rows.append(np.asarray(values, dtype=float))
            targets.append(float(trajectory[t, INDEX[target]]))
    return np.stack(rows), np.asarray(targets), names


def _parents(
    design: np.ndarray,
    target: np.ndarray,
    names: list[str],
    *,
    seed: int,
    threshold: float = 0.055,
) -> tuple[set[str], dict[str, float]]:
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(target))
    cut = max(40, int(0.75 * len(order)))
    train, test = order[:cut], order[cut:]
    model = ExtraTreesRegressor(
        n_estimators=96,
        max_depth=7,
        min_samples_leaf=3,
        random_state=seed,
        n_jobs=1,
    )
    model.fit(design[train], target[train])
    importance = permutation_importance(
        model,
        design[test],
        target[test],
        n_repeats=4,
        random_state=seed + 911,
        scoring="neg_mean_squared_error",
        n_jobs=1,
    ).importances_mean
    positive = np.clip(importance, 0.0, None)
    normalized = positive / max(float(positive.sum()), 1e-12)
    scores = {name: float(score) for name, score in zip(names, normalized)}
    return {name for name, score in scores.items() if score >= threshold}, scores


def _score(predicted: Iterable[str], expected: Iterable[str]) -> dict[str, float]:
    predicted, expected = set(predicted), set(expected)
    true_positive = len(predicted & expected)
    precision = true_positive / len(predicted) if predicted else float(not expected)
    recall = true_positive / len(expected) if expected else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def discover(
    data: dict[str, Any], *, pooled: bool, grouped: bool, seed: int
) -> dict[str, Any]:
    mechanism_rows: dict[str, Any] = {}
    predicted_edges: set[str] = set()
    expected_edges: set[str] = set()
    for offset, mechanism in enumerate(("write", "hold", "read")):
        design, target, names = _rows(data, mechanism, pooled=pooled, grouped=grouped)
        parents, scores = _parents(design, target, names, seed=seed + offset)
        expected = set(data["gold"][mechanism if mechanism != "read" else "read_grouped"])
        if mechanism == "read" and not grouped:
            expected = set(data["gold"]["read_observed"])
        predicted_edges.update(f"{parent}->{mechanism}" for parent in parents)
        expected_edges.update(f"{parent}->{mechanism}" for parent in expected)
        mechanism_rows[mechanism] = {
            "rows": len(target),
            "parents": sorted(parents),
            "expected_observable_parents": sorted(expected),
            "scores": scores,
            **_score(parents, expected),
        }
    proxy_false = set(mechanism_rows["read"]["parents"]) & {"p1", "p2"}
    return {
        "pooled": pooled,
        "grouped_proxy": grouped,
        "mechanisms": mechanism_rows,
        "overall_observable": _score(predicted_edges, expected_edges),
        "read_proxy_false_positives": sorted(proxy_false),
        "latent_incident_edges_scored": False,
    }


def run_suite(
    *, seeds: Iterable[int] = range(5), episodes: int = 240, delta: int = 10
) -> dict[str, Any]:
    rows: dict[str, list[dict[str, Any]]] = {family: [] for family in FAMILIES}
    for family in FAMILIES:
        for seed in seeds:
            data = generate(family, episodes=episodes, delta=delta, seed=seed)
            row = {
                "seed": seed,
                "pooled": discover(data, pooled=True, grouped=False, seed=seed + 101),
                "regime_conditioned": discover(
                    data, pooled=False, grouped=False, seed=seed + 211
                ),
            }
            if family == "mlp_latent":
                row["grouped_proxy_fallback"] = discover(
                    data, pooled=False, grouped=True, seed=seed + 307
                )
            rows[family].append(row)

    summary: dict[str, Any] = {}
    for family, family_rows in rows.items():
        summary[family] = {}
        arms = ["pooled", "regime_conditioned"]
        if family == "mlp_latent":
            arms.append("grouped_proxy_fallback")
        for arm in arms:
            f1_values = [row[arm]["overall_observable"]["f1"] for row in family_rows]
            read_values = [row[arm]["mechanisms"]["read"]["f1"] for row in family_rows]
            summary[family][arm] = {
                "overall_f1_mean": float(np.mean(f1_values)),
                "overall_f1_std": float(np.std(f1_values)),
                "read_f1_mean": float(np.mean(read_values)),
                "read_f1_std": float(np.std(read_values)),
                "seeds": len(f1_values),
            }
    return {
        "schema": "yujia-simulation-v2/v1",
        "cpu_only": True,
        "episodes_per_seed": episodes,
        "delta": delta,
        "families": rows,
        "summary": summary,
        "gold_scope": (
            "All observed structural parents and the hidden h parent are generator-owned. "
            "Directed edges incident to unobserved h are not scored as recoverable by the "
            "observed-only estimator; the grouped arm is explicitly a measured-proxy fallback."
        ),
        "claim_boundary": (
            "This validates nonlinear regime-conditioned structure recovery under known DGPs. "
            "It does not establish latent-variable identification or agent-memory utility."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=int, default=240)
    parser.add_argument("--delta", type=int, default=10)
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = run_suite(
        seeds=range(args.seeds), episodes=args.episodes, delta=args.delta
    )
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps(report["summary"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
