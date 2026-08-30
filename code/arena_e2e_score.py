"""Score finished end-to-end travel runs with MemoryArena's OWN metrics (PS/SPS/SR).

This is the number the P2 claim still lacks. Everything measured so far is about
the memory CONTEXT (answerability at cost); this measures whether the agent
actually planned the trip correctly, using the benchmark's official evaluator
rather than anything of ours:

    env/env_systems/travel_planner_env/eval.py :: evaluate(submission_path, ...)
      SR   group-level: every traveller in the group passes
      PS   person-level full pass rate
      SPS  data-level average constraint satisfaction rate

Usage (after run_travel.py has written plans):
    python3 code/arena_e2e_score.py                       # scores every arm found
    python3 code/arena_e2e_score.py --arms causal-learned long_context

Only scores arms that actually produced plan files, and prints how many episodes
each arm completed -- because comparing arms at different episode counts is not a
comparison. It refuses to rank arms whose completed-episode sets differ, and says
so, rather than quietly reporting numbers computed on different data.

CPU-only, no API, no network.
"""
from __future__ import annotations

import os as _os
_os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

import argparse
from collections import Counter, defaultdict
import json
import random
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ARENA = REPO / "benchmarks" / "MemoryArena"
E2E = ARENA / "results" / "travel_e2e"


def episodes_done(arm_dir: Path) -> set:
    out = set()
    for f in arm_dir.glob("generated_plan_*.json"):
        m = re.search(r"generated_plan_(.+)\.json$", f.name)
        if m:
            out.add(m.group(1))
    return out


def submission_for(arm_dir: Path, model: str) -> Path:
    """Resolve the JSONL produced by MemoryArena's own ``combine`` step."""
    preferred = arm_dir / "submission" / f"{model}_submission.jsonl"
    if preferred.is_file():
        return preferred
    found = sorted((arm_dir / "submission").glob("*_submission.jsonl"))
    if len(found) == 1:
        return found[0]
    if not found:
        raise FileNotFoundError(f"no submission JSONL under {arm_dir / 'submission'}")
    raise RuntimeError(f"multiple submissions under {arm_dir / 'submission'}; pass --model")


def per_episode_metrics(eval_mod, submission: Path) -> dict:
    """Re-express the official evaluator's exact checks one episode at a time."""
    gt, base_plans, _ = eval_mod.load_ground_truth()
    sub_final = eval_mod.load_submissions(str(submission))
    out = {}
    for data_idx in sorted({k[0] for k in sub_final}):
        person_indices = sorted(k[1] for k in sub_final if k[0] == data_idx)
        full_pass = 0
        constraint_rates = []
        for person_idx in person_indices:
            gt_plan = gt.get((data_idx, person_idx))
            sub_plan = sub_final.get((data_idx, person_idx))
            if eval_mod.check_person_full_pass(gt_plan, sub_plan):
                full_pass += 1
            passed = total = 0
            slots = eval_mod.find_constraint_slots(gt, base_plans, data_idx, person_idx)
            if gt_plan:
                for day in gt_plan:
                    day_idx = day.get("days") or day.get("day")
                    for slot in eval_mod.SLOTS:
                        if (day_idx, slot) in slots:
                            total += 1
                            passed += int(eval_mod.check_slot_pass(
                                gt_plan, sub_plan, day_idx, slot))
            if total:
                constraint_rates.append(passed / total)
        n = len(person_indices)
        out[str(data_idx)] = {
            "n_persons": n,
            "full_pass_persons": full_pass,
            "ps": 100 * full_pass / n if n else 0.0,
            "sps": (100 * sum(constraint_rates) / len(constraint_rates)
                    if constraint_rates else 0.0),
            "sr": 100.0 if n and full_pass == n else 0.0,
        }
    return out


def bootstrap_mean_ci(values: list[float], seed: int, n_boot: int = 10000) -> list[float]:
    """Episode-level nonparametric percentile interval; deterministic for reporting."""
    if not values:
        return [0.0, 0.0]
    rng = random.Random(seed)
    n = len(values)
    samples = sorted(sum(rng.choice(values) for _ in range(n)) / n
                     for _ in range(n_boot))
    return [samples[int(0.025 * (n_boot - 1))],
            samples[int(0.975 * (n_boot - 1))]]


def paired_comparisons(rep: dict) -> dict:
    """Paired episode deltas for registered method/baseline comparisons."""
    out = {}
    pairs = [(method, baseline)
             for method in ("causal-learned-pure", "causal-learned")
             for baseline in ("bm25", "long_context")]
    pairs.append(("causal-learned-inherit", "causal-learned-pure-inherit"))
    pairs.extend([
        ("causal-learned-pure-inherit-holdout", "causal-noG-inherit-holdout"),
        ("causal-learned-pure-inherit-holdout", "bm25-inherit-holdout"),
        ("causal-learned-pure-inherit-holdout", "long-context-inherit-holdout"),
    ])
    for pair_idx, (method, baseline) in enumerate(pairs):
        if method not in rep or baseline not in rep:
            continue
        left = rep[method].get("per_episode", {})
        right = rep[baseline].get("per_episode", {})
        ids = sorted(set(left) & set(right), key=int)
        if not ids:
            continue
        metrics = {}
        for metric_idx, metric in enumerate(("ps", "sps", "sr")):
            delta = [float(left[i][metric]) - float(right[i][metric]) for i in ids]
            metrics[metric] = {
                "episode_deltas": dict(zip(ids, delta)),
                "mean_delta_points": sum(delta) / len(delta),
                "bootstrap_95": bootstrap_mean_ci(
                    delta, seed=1000 + pair_idx * 10 + metric_idx),
                "wins": sum(x > 1e-12 for x in delta),
                "ties": sum(abs(x) <= 1e-12 for x in delta),
                "losses": sum(x < -1e-12 for x in delta),
            }
        out[f"{method}_minus_{baseline}"] = {
            "episode_ids": ids, "n_episodes": len(ids), "metrics": metrics,
        }
    return out


def repeat_comparisons(rep: dict, reference: dict) -> dict:
    """Compare a fresh ``*-rerun`` arm with its preserved run-A result."""
    out = {}
    for rerun, current in rep.items():
        if rerun.startswith("_") or not rerun.endswith("-rerun"):
            continue
        original = rerun.removesuffix("-rerun")
        prior = reference.get(original)
        if not prior or "metrics" not in current or "metrics" not in prior:
            continue

        current_eps = current.get("per_episode") or {}
        prior_eps = prior.get("per_episode") or {}
        ids = sorted(set(current_eps) & set(prior_eps), key=int)
        metrics = {}
        for metric_idx, metric in enumerate(("ps", "sps", "sr")):
            deltas = [float(current_eps[i][metric]) - float(prior_eps[i][metric])
                      for i in ids]
            current_value = float(current["metrics"][metric])
            prior_value = float(prior["metrics"][metric])
            metrics[metric] = {
                "run_a": prior_value,
                "run_b": current_value,
                "overall_delta_points": current_value - prior_value,
                "episode_deltas": dict(zip(ids, deltas)),
                "episode_mean_delta_points": (
                    sum(deltas) / len(deltas) if deltas else None),
                "episode_bootstrap_95": (
                    bootstrap_mean_ci(deltas, seed=2000 + metric_idx)
                    if deltas else None),
                "wins": sum(x > 1e-12 for x in deltas),
                "ties": sum(abs(x) <= 1e-12 for x in deltas),
                "losses": sum(x < -1e-12 for x in deltas),
            }

        usage = {}
        for key in ("total_input_tokens", "total_output_tokens", "total_cost",
                    "duration_seconds"):
            a_value = (prior.get("usage") or {}).get(key)
            b_value = (current.get("usage") or {}).get(key)
            if a_value is not None and b_value is not None:
                usage[key] = {
                    "run_a": a_value,
                    "run_b": b_value,
                    "delta": b_value - a_value,
                }

        out[f"{rerun}_minus_{original}"] = {
            "run_a_arm": original,
            "run_b_arm": rerun,
            "run_a_episode_ids": prior.get("episode_ids") or [],
            "run_b_episode_ids": current.get("episode_ids") or [],
            "common_episode_ids": ids,
            "same_episode_set": (set(prior.get("episode_ids") or []) ==
                                 set(current.get("episode_ids") or [])),
            "metrics": metrics,
            "usage": usage,
        }
    return out


def usage_with_coverage(raw: dict | None, prior: dict | None,
                        episode_ids: set[str]) -> dict | None:
    """Merge incremental usage when the upstream runner skipped existing plans.

    ``run_travel.py`` overwrites usage_stats.json even when some generated plans
    are skipped, so a resume contains only the newly-run episodes.  The previous
    scored result records the older coverage and is the only safe source for
    adding those counters back.
    """
    if raw is None:
        return None
    current = dict(raw)
    prior_ids = set((prior or {}).get("episode_ids") or [])
    prior_usage = (prior or {}).get("usage") or {}
    if prior_ids == episode_ids and prior_usage:
        return dict(prior_usage)
    if prior_ids and prior_ids < episode_ids and prior_usage:
        for key in ("total_input_tokens", "total_output_tokens", "total_cost",
                    "duration_seconds"):
            current[key] = float(current.get(key, 0)) + float(prior_usage.get(key, 0))
        current["total_input_tokens"] = int(current["total_input_tokens"])
        current["total_output_tokens"] = int(current["total_output_tokens"])
        current["duration_seconds"] = round(current["duration_seconds"], 2)
        current["duration_minutes"] = round(current["duration_seconds"] / 60, 2)
        current["aggregation"] = "previous scored coverage + resumed incremental run"
    current["covered_episode_ids"] = sorted(episode_ids, key=int)
    return current


def call_usage_with_coverage(path: Path, episode_ids: set[str]) -> dict | None:
    """Aggregate v2's append-only, per-call API ledger by completed episode.

    A killed run can leave a partial attempt in the ledger.  Each resume gets a
    fresh timestamp-prefixed session ID, so for every completed episode we keep
    only its latest attempt.  This prevents an interrupted partial attempt from
    being silently charged twice while retaining exact call-level coverage.
    """
    if not path.is_file():
        return None
    attempts = defaultdict(list)
    malformed = 0
    for line_number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        episode = str(event.get("episode_id"))
        attempt = str(event.get("attempt_id") or "")
        if episode not in episode_ids or not attempt:
            continue
        attempts[(episode, attempt)].append(event)

    def attempt_order(attempt: str) -> tuple[int, str]:
        session = attempt.rsplit(":", 1)[0]
        prefix = session.split("-", 1)[0]
        return (int(prefix) if prefix.isdigit() else -1, session)

    per_episode = {}
    selected_attempts = {}
    for episode in sorted(episode_ids, key=int):
        candidates = [attempt for ep, attempt in attempts if ep == episode]
        if not candidates:
            continue
        selected = max(candidates, key=attempt_order)
        selected_attempts[episode] = selected
        rows = attempts[(episode, selected)]
        per_episode[episode] = {
            "calls": len(rows),
            "input_tokens": sum(int(row.get("input_tokens", 0)) for row in rows),
            "output_tokens": sum(int(row.get("output_tokens", 0)) for row in rows),
            "cost": sum(float(row.get("cost", 0.0)) for row in rows),
            "api_duration_seconds": sum(
                float(row.get("duration_seconds", 0.0)) for row in rows),
            "message_chars": sum(int(row.get("message_chars", 0)) for row in rows),
            "tool_schema_chars": sum(
                int(row.get("tool_schema_chars", 0)) for row in rows),
            "rounds_covered": sorted({
                int(row["round_idx"]) for row in rows
                if row.get("round_idx") is not None
            }),
            "persons_covered": sorted({
                str(row["person"]) for row in rows if row.get("person")
            }),
            "thinking_modes": sorted({
                str(row.get("thinking_mode", "default")) for row in rows
            }),
            "returned_models": sorted({
                str(row.get("returned_model")) for row in rows
                if row.get("returned_model")
            }),
            "repair_calls": sum(bool(row.get("repair_reason")) for row in rows),
            "finish_reasons": dict(Counter(
                str(row.get("finish_reason") or "unknown") for row in rows)),
        }
    covered = set(per_episode)
    return {
        "schema": "memoryarena-llm-call-usage-summary/v1",
        "source": str(path),
        "aggregation": "latest append-only attempt for each completed episode",
        "covered_episode_ids": sorted(covered, key=int),
        "missing_completed_episode_ids": sorted(episode_ids - covered, key=int),
        "malformed_ledger_lines": malformed,
        "selected_attempts": selected_attempts,
        "per_episode": per_episode,
        "calls": sum(item["calls"] for item in per_episode.values()),
        "total_input_tokens": sum(
            item["input_tokens"] for item in per_episode.values()),
        "total_output_tokens": sum(
            item["output_tokens"] for item in per_episode.values()),
        "total_cost": sum(item["cost"] for item in per_episode.values()),
        "api_duration_seconds": sum(
            item["api_duration_seconds"] for item in per_episode.values()),
        "thinking_modes": sorted({
            mode for item in per_episode.values()
            for mode in item["thinking_modes"]
        }),
        "returned_models": sorted({
            model for item in per_episode.values()
            for model in item["returned_models"]
        }),
        "repair_calls": sum(item["repair_calls"] for item in per_episode.values()),
        "finish_reasons": dict(Counter(
            reason for item in per_episode.values()
            for reason, count in item["finish_reasons"].items()
            for _ in range(count))),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", nargs="*", default=None)
    ap.add_argument("--e2e_dir", default=str(E2E))
    ap.add_argument("--model", default="deepseek-v4-flash")
    ap.add_argument("--out", default="results/real/e2e_scores.json")
    ap.add_argument("--reference", default=None,
                    help="preserved score JSON to compare against (for run A/B reruns)")
    ap.add_argument(
        "--pairs", nargs="*", default=[], metavar="METHOD:BASELINE",
        help="additional paired comparisons, e.g. compact-v2-dev:noG-v2-dev")
    a = ap.parse_args()

    output_path = REPO / a.out
    try:
        previous_report = json.load(open(output_path))
    except Exception:
        previous_report = {}

    e2e = Path(a.e2e_dir).resolve()
    if not e2e.exists():
        print(f"no end-to-end output at {e2e} — run_travel.py has not produced plans yet")
        return
    arms = a.arms or sorted(d.name for d in e2e.iterdir()
                            if d.is_dir() and d.name != "logs")
    if not arms:
        print(f"{e2e} exists but contains no arm directories")
        return

    done = {arm: episodes_done(e2e / arm) for arm in arms if (e2e / arm).exists()}
    print("completed episodes per arm:")
    for arm, eps in done.items():
        print(f"  {arm:24s} {len(eps)}")
    nonempty = {k: v for k, v in done.items() if v}
    if not nonempty:
        print("\nNothing to score: every arm completed 0 episodes.")
        print("(An episode only counts once run_travel.py writes its generated_plan_*.json.)")
        return
    common = set.intersection(*nonempty.values()) if len(nonempty) > 1 else next(iter(nonempty.values()))
    if len(nonempty) > 1 and any(len(v) != len(common) for v in nonempty.values()):
        print(f"\n!! arms completed DIFFERENT episode sets (common={len(common)}).")
        print("   Scores below are per-arm on that arm's own episodes and are NOT")
        print("   directly comparable. Re-run to a common episode set before ranking.")

    sys.path.insert(0, str(ARENA))
    os_cwd = Path.cwd()
    try:
        _os.chdir(ARENA)
        from env.env_systems.travel_planner_env import eval as official_eval
        evaluate = official_eval.evaluate
    except Exception as exc:
        print(f"could not import MemoryArena's evaluator: {exc}")
        _os.chdir(os_cwd)
        return

    rep = {}
    for arm, eps in nonempty.items():
        print(f"\n=== {arm}  ({len(eps)} episodes) ===")
        try:
            submission = submission_for(e2e / arm, a.model)
            res = evaluate(str(submission), model_name=a.model, memory_system=arm)
            usage_path = e2e / arm / "stats_results" / "usage_stats.json"
            raw_usage = json.load(open(usage_path)) if usage_path.is_file() else None
            usage = usage_with_coverage(raw_usage, previous_report.get(arm), set(eps))
            call_usage = call_usage_with_coverage(
                e2e / arm / "llm_call_usage.jsonl", set(eps))
            rep[arm] = {"n_episodes": len(eps), "episode_ids": sorted(eps),
                        "submission": str(submission), "metrics": res,
                        "usage": usage,
                        "call_usage": call_usage,
                        "per_episode": per_episode_metrics(official_eval, submission)}
        except Exception as exc:
            print(f"  evaluator failed: {exc}")
            rep[arm] = {"n_episodes": len(eps), "error": str(exc)}
    _os.chdir(os_cwd)

    rep["_paired_comparisons"] = paired_comparisons(rep)
    for pair_index, specification in enumerate(a.pairs):
        if ":" not in specification:
            raise ValueError(f"invalid --pairs value {specification!r}; expected METHOD:BASELINE")
        method, baseline = specification.split(":", 1)
        if method not in rep or baseline not in rep:
            raise ValueError(f"pair references an unscored arm: {specification}")
        left = rep[method].get("per_episode", {})
        right = rep[baseline].get("per_episode", {})
        ids = sorted(set(left) & set(right), key=int)
        metrics = {}
        for metric_index, metric in enumerate(("ps", "sps", "sr")):
            delta = [float(left[i][metric]) - float(right[i][metric]) for i in ids]
            metrics[metric] = {
                "episode_deltas": dict(zip(ids, delta)),
                "mean_delta_points": sum(delta) / len(delta) if delta else None,
                "bootstrap_95": bootstrap_mean_ci(
                    delta, seed=3000 + pair_index * 10 + metric_index) if delta else None,
                "wins": sum(value > 1e-12 for value in delta),
                "ties": sum(abs(value) <= 1e-12 for value in delta),
                "losses": sum(value < -1e-12 for value in delta),
            }
        rep["_paired_comparisons"][f"{method}_minus_{baseline}"] = {
            "episode_ids": ids, "n_episodes": len(ids), "metrics": metrics,
        }
    if a.reference:
        reference_path = Path(a.reference)
        if not reference_path.is_absolute():
            reference_path = REPO / reference_path
        reference = json.load(open(reference_path))
        rep["_repeat_comparisons"] = repeat_comparisons(rep, reference)
        rep["_reference"] = str(reference_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    json.dump(rep, open(output_path, "w"), indent=1, default=str)
    print(f"\nwrote {output_path}")


if __name__ == "__main__":
    main()
