"""Offline cumulative usage and development-calibrated budget; never calls an API."""
from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path

from arena_recent_memory import ARMS, ROOT
from arena_recent_report import audit_family, metered_usage


def billable_family_paths(root):
    """A copied result view is evidence, never another set of API charges."""
    for phase in ("development", "real"):
        for base in sorted((Path(root) / "results" / phase).glob("p2_recent_baselines_tokenrhythm_v*")):
            if (base / "protocol.json").exists() and not (base / "result_view_manifest.json").exists():
                yield base


def main():
    development = ROOT / "results/development"
    families = {}
    for base in billable_family_paths(ROOT):
        families[str(base.relative_to(ROOT))] = audit_family(base)
    views = []
    for marker in (ROOT / "results/real").glob("p2_recent_baselines_tokenrhythm_v*/result_view_manifest.json"):
        manifest = json.loads(marker.read_text())
        if manifest.get("state") == "complete" and audit_family(marker.parent)["paired_scope_complete"]:
            views.append(str(marker.parent.relative_to(ROOT)))
    probe_rows = []
    probe_paths = []
    for name in ("tokenrhythm_latency_2026_09_14.json",
                 "tokenrhythm_historical_probe_2026_09_14.json",
                 "tokenrhythm_stream_transport_probe_2026_09_14.json",
                 "tokenrhythm_preheader_recovery_probe_2026_09_14.json"):
        path = development / name
        if not path.exists():
            continue
        probe_paths.append(path)
        # Only each new request's top-level usage, never old_usage or raw_response.
        probe_rows.extend(json.loads(path.read_text())["requests"])
    path = development / "tokenrhythm_rate_limit_probe_2026_09_14.json"
    probe_paths.append(path)
    response = json.loads(path.read_text())["response"]
    if isinstance(response, str):
        response = json.loads(response)
    probe_rows.append({"usage": response.get("usage"),
                       "provider_cost_cny": response.get("cost_cny")})
    probe = metered_usage(probe_rows)
    cohorts = {a: ("v2" if a in ("noGcompact", "mem0", "amem") else
                   "v5" if a == "lightmem" else "v3") for a in ARMS}
    calibrated = {}
    for arm, version in cohorts.items():
        family = "results/development/p2_recent_baselines_tokenrhythm_" + version
        if family not in families:
            continue
        observed = families[family]["arms"][arm]
        if not observed["complete"]:
            continue
        cost = lambda u: (2 * u["input_tokens"] + 8 * u["output_tokens"]) / 1e6
        calibrated[arm] = {
            "development_family": family,
            "development_actor_cny_without_cache": cost(observed["actor"]),
            "development_memory_cny_without_cache": cost(observed["memory"]),
            "evaluation_actor_cny": cost(observed["actor"]) * 22 / 7,
            "evaluation_memory_cny": cost(observed["memory"]) * 25 / 8,
            "observed_actor_calls": observed["actor"]["responses_with_usage"],
            "observed_memory_calls": observed["memory"]["responses_with_usage"],
        }
    dev_cost = sum(d["estimated_cny_all_logged_responses"] for p, d in families.items()
                   if p.startswith("results/development/"))
    eval_cost = sum(d["estimated_cny_all_logged_responses"] for p, d in families.items()
                    if p.startswith("results/real/"))
    report = {
        "schema": "memoryarena-cumulative-budget/v1",
        "snapshot_time": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "currency": "CNY", "invoice_verified": False,
        "evaluation_complete": bool(views) or any(d["paired_scope_complete"] for p, d in families.items()
                                                  if p.startswith("results/real/")),
        "completed_result_views_excluded_from_billing": views,
        "old_bboluo_spend_user_report": 230,
        "tokenrhythm_probe_usage": probe,
        "tokenrhythm_development_estimated_cny": dev_cost,
        "tokenrhythm_evaluation_estimated_cny": eval_cost,
        "tokenrhythm_total_logged_estimated_cny": dev_cost + eval_cost + probe["estimated_cny"],
        "old_spend_plus_logged_estimate_cny": 230 + dev_cost + eval_cost + probe["estimated_cny"],
        "family_usage": {p: {
            "estimated_cny": d["estimated_cny_all_logged_responses"],
            "responses_with_usage": sum(a[k]["responses_with_usage"] for a in d["arms"].values()
                                        for k in ("actor", "memory")),
            "recorded_api_errors": sum(a["recorded_api_errors"] for a in d["arms"].values()),
            "transport_failures_without_usage": sum(a[k]["transport_failures_without_usage"]
                for a in d["arms"].values() for k in ("actor", "memory")),
            "complete_arms": [a for a, r in d["arms"].items() if r["complete"]],
        } for p, d in families.items()},
        "development_calibration": calibrated,
        "forecast_ready": len(calibrated) == len(ARMS),
        "forecast_method": "Per-arm complete development actor cost scaled by 22/7 rounds; memory cost by 25/8 writes. Future cache discount is zero. 30% reserve is a planning choice, not a confidence interval or bound.",
        "limitations": [
            "Includes logged successful usage from all failed/interrupted development versions, not just valid cohorts.",
            "Unlogged SDK retries, interrupted requests and rejected attempts may have additional charges; a zero recorded-error count does not prove no failures.",
            "aiaaa probe pricing remains unknown and is excluded from CNY totals.",
            "One development episode per arm does not estimate task variance; LightMem update growth can be nonlinear.",
            "Historical bboluo CNY 230 is user-reported billed spend, while TokenRhythm amounts are usage estimates.",
            "Live ledgers may grow while a snapshot is read; input hashes are captured after the usage read and become reproducible only once writers stop.",
        ],
    }
    if report["forecast_ready"]:
        forecast = sum(r["evaluation_actor_cny"] + r["evaluation_memory_cny"] for r in calibrated.values())
        report["forecast_full_evaluation_cny"] = forecast
        report["forecast_full_evaluation_with_30pct_reserve_cny"] = forecast * 1.3
        report["planning_whole_round_cny_excluding_unknown_charges"] = (
            230 + dev_cost + probe["estimated_cny"] + max(eval_cost, forecast * 1.3))
    if report["evaluation_complete"]:
        report["remaining_evaluation_cny"] = 0
        if "planning_whole_round_cny_excluding_unknown_charges" in report:
            report["prior_development_calibrated_whole_round_planning_cny"] = report.pop(
                "planning_whole_round_cny_excluding_unknown_charges")
    aiaaa = json.loads((development / "aiaaa_latency_2026_09_14.json").read_text())["requests"]
    report["aiaaa_unpriced_probe_usage"] = {
        "responses_with_usage": sum(bool(r.get("usage")) for r in aiaaa),
        "input_tokens": sum(r.get("usage", {}).get("prompt_tokens", 0) for r in aiaaa),
        "output_tokens": sum(r.get("usage", {}).get("completion_tokens", 0) for r in aiaaa),
        "estimated_cny": None,
    }
    ledgers = [ROOT / p / "protocol.json" for p in families]
    for p in families:
        ledgers.extend((ROOT / p / "e2e").glob("*/*usage.jsonl"))
        ledgers.extend((ROOT / p / "e2e").glob("*/memory_events.jsonl"))
    report["input_sha256"] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in [*probe_paths, *ledgers]}
    target = development / "tokenrhythm_cumulative_budget_2026_09_14.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    lines = ["# 本轮累计用量与预算", "", f"快照时间：{report['snapshot_time']}。", "",
             f"旧 bboluo 用户确认已花 **¥230**；TokenRhythm 已返回的 usage 估算 **¥{report['tokenrhythm_total_logged_estimated_cny']:.4f}**，",
             f"两者相加 **¥{report['old_spend_plus_logged_estimate_cny']:.4f}**。这是账单与用量估算的合计，不是已对账总额。", "",
             "| TokenRhythm 阶段 | 已记录响应 | usage 估算元 |", "|---|---:|---:|",
             f"| 连通性、历史重放、流式与限流探针 | {probe['responses_with_usage']} | {probe['estimated_cny']:.4f} |"]
    for name, row in report["family_usage"].items():
        lines.append(f"| {name.removeprefix('results/')} | {row['responses_with_usage']} | {row['estimated_cny']:.4f} |")
    lines += ["", "包含所有保留的开发版本，即使对应任务失败或中断；不会只计算成功验证的版本。", "",
              "单价为未缓存输入 2、缓存输入 0.04、输出 8 元/M token；输出包含推理。",
              "失败、中断或旧 SDK 隐式重试可能没有返回 usage；aiaaa 四次探针输入 824 / 输出 539 tokens，单价未知，均未混入金额。", ""]
    if report["evaluation_complete"]:
        lines += [f"**本轮配对评估已完成。** 原始评估及所有 summary 技术补跑的已记录费用合计 **¥{eval_cost:.4f}**，",
                  "与上表开发/探针汇总后即为当前整轮用量估算。结果视图只是已生成文件的副本，已排除重复计费。",
                  "缺失 usage 与 aiaaa 未知价格仍需平台对账；不能把它们解释为免费。"]
    elif report["forecast_ready"]:
        lines += [f"用十个方法已完成的开发数据校准后，三 episode 正式评估估算 **¥{forecast:.2f}**；",
                  f"另加 30% 规划预留为 **¥{forecast * 1.3:.2f}**。加旧 ¥230、探针及全部开发后，",
                  f"整轮规划约 **¥{report['planning_whole_round_cny_excluding_unknown_charges']:.2f}**。", "",
                  "计算方式：各方法开发 actor 费用按 22/7 轮放大，memory 费用按 25/8 次写入放大，未来输入不计缓存折扣。",
                  "只观测了一个开发 episode；LightMem 更新可非线性增长，30% 是规划预留，不是置信区间或硬上限。"]
    else:
        lines += [f"已有 {len(calibrated)}/10 个方法完成开发验证；完整开发校准预测待最后一个方法完成。",
                  "此前约 300 元是初始规划，不能当作本轮实测总额或硬上限。"]
    lines += ["", "[逐方法校准、原始计数与来源](../results/development/tokenrhythm_cumulative_budget_2026_09_14.json)",
              "· [公开单价与中转测试](tokenrhythm-switch-2026-09-14.md)", ""]
    (ROOT / "docs/recent-memory-current-budget-2026-09-14.md").write_text("\n".join(lines))
    print(json.dumps({k: v for k, v in report.items() if k in (
        "snapshot_time", "evaluation_complete", "tokenrhythm_total_logged_estimated_cny",
        "old_spend_plus_logged_estimate_cny", "forecast_ready",
        "forecast_full_evaluation_cny", "planning_whole_round_cny_excluding_unknown_charges")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
