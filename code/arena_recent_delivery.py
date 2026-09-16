"""Finalize the reviewable September deliverables after all ten arms are scored."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from arena_recent_memory import ROOT


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    args = parser.parse_args()
    base = args.base.resolve()
    # The result writer refuses incomplete scope, API errors and missing scores.
    subprocess.run([sys.executable, str(ROOT / "code/arena_recent_results.py"),
                    "--base", str(base)], cwd=ROOT, check=True)
    subprocess.run([sys.executable, str(ROOT / "code/arena_recent_budget.py")], cwd=ROOT, check=True)
    result = json.loads((base / "paired_results.json").read_text())
    audit = json.loads((base / "usage_integrity_audit.json").read_text())
    budget_path = ROOT / "results/development/tokenrhythm_cumulative_budget_2026_09_14.json"
    budget = json.loads(budget_path.read_text())
    status_path = ROOT / "results/real/yujia_meeting_2026_09_04/delivery_status.json"
    status = json.loads(status_path.read_text())
    status["status"] = "complete_descriptive_paired_evaluation"
    status["deliverables"]["full_paired_baseline_evaluation"] = "complete"
    status["deliverables"]["native_baseline_adapters"] = "all_ten_development_interfaces_validated"
    status["claims"]["new_baseline_ranking_available"] = True
    status["claims"]["new_baseline_interpretation"] = result["interpretation"]
    if result.get('post_freeze_technical_recovery'):
        status['finalization_state'] = status['active_execution_state']
    status["completed_evaluation"] = {
        "family": base.name, "episode_ids": result["episode_ids"], "arms": len(result["rows"]),
        "report": str((base / "results.md").relative_to(ROOT)),
        "estimated_cny": result["estimated_evaluation_cny"], "invoice_verified": False,
        "protocol_sha256": result["protocol_sha256"],
        "actor_calls": sum(r["actor_calls"] for r in result["rows"]),
        "memory_calls": sum(r["memory_calls"] for r in result["rows"]),
        "paired_scope_complete": audit["paired_scope_complete"],
        "post_freeze_technical_recovery": result.get("post_freeze_technical_recovery", False),
        "original_batch_complete": result.get("original_batch_complete", True),
    }
    if 'historical_bboluo_usage_recorded' not in status and 'usage_recorded' in status:
        status['historical_bboluo_usage_recorded']=status['usage_recorded']
    status['usage_recorded']={
        'scope':'selected complete paired results; all attempts billed separately in cumulative budget',
        'actor_calls':sum(r['actor_calls'] for r in result['rows']),
        'memory_llm_calls':sum(r['memory_calls'] for r in result['rows']),
        'input_tokens':sum(r['input_tokens'] for r in result['rows']),
        'output_tokens':sum(r['output_tokens'] for r in result['rows']),
        'invoice_verified':False}
    status['completed_evaluation']['ours_vs_same_format_control']=result['ours_vs_same_format_control']
    status["current_usage_budget"] = str(budget_path.relative_to(ROOT))
    status["current_cost_snapshot"] = {
        k: budget[k] for k in ("snapshot_time", "old_bboluo_spend_user_report",
                              "tokenrhythm_total_logged_estimated_cny",
                              "old_spend_plus_logged_estimate_cny", "aiaaa_unpriced_probe_usage")}
    status["offline_tests"]["recent_transport_wrapper_memory_report"] = 19
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n")

    for name in ("README.md", "docs/HANDOFF.md", "docs/yujia-meeting-delivery-2026-09-14.md",
                 "docs/recent-memory-baselines-2026-09-04.md", "docs/tokenrhythm-switch-2026-09-14.md"):
        path = ROOT / name
        text = path.read_text()
        prefix = "" if name == "README.md" else "../"
        link = prefix + str((base / "results.md").relative_to(ROOT))
        notice = ("<!-- recent-memory-completion:start -->\n"
                  f"> **完整配对评估已完成：** 十臂均完成 IDs 111/112/113，官方评分与用量完整性检查通过。\n"
                  f"> [结果表与逐 episode 比较]({link})；表中完整结果的用量估算 ¥{result['estimated_evaluation_cny']:.4f}。\n"
                  f"> 新中转探针及全部开发/评估合计估算 ¥{budget['tokenrhythm_total_logged_estimated_cny']:.4f}，\n"
                  f"> 加旧账单 ¥230 后为 ¥{budget['old_spend_plus_logged_estimate_cny']:.4f}。缺失用量与 aiaaa 未知费用未计入；不是对账总额。\n"
                  "> 这是三个复用 holdout episodes 的描述性配对复验；不证明 causal necessity 或真实 latent identifiability。\n"
                  "<!-- recent-memory-completion:end -->\n")
        if result.get('post_freeze_technical_recovery'):
            notice = notice.replace('<!-- recent-memory-completion:end -->',
                '> summary 使用按预先记录的技术恢复规则完成的补跑，其余九臂保留原结果；原始批次的断流失败及费用另行保留。\n'
                '<!-- recent-memory-completion:end -->')
        start, end = "<!-- recent-memory-completion:start -->", "<!-- recent-memory-completion:end -->"
        if start in text:
            left, rest = text.split(start, 1)
            _, right = rest.split(end, 1)
            text = left + notice + right.lstrip("\n")
        else:
            title, rest = text.split("\n", 1)
            text = title + "\n\n" + notice + rest
        text = text.replace("现已切换 TokenRhythm 并恢复开发，完整新配对评估尚未完成。",
                            "现已切换 TokenRhythm，完整新配对评估已完成，结果见本页顶部。")
        text = text.replace("本轮尚待收口的必需交付是 **完整的新 baseline 配对结果**；当前认证可用，按续跑状态继续开发、\n冻结、评估与结果填表。",
                            "本轮 **完整的新 baseline 配对结果** 已收口，见本页顶部的结果表与成本。")
        # Development narration remains preserved as explicitly historical context.
        version = result.get('result_provenance', {}).get('original_family', base.name).rsplit('_', 1)[-1]
        text = text.replace(f"已通过的 v2/v3 开发接口不重复运行；LightMem 单独验证 {version}，随后十臂使用共同协议正式评估。",
                            f"开发采用 v2/v3 已通过的接口与 {version} LightMem；十臂正式评估全部使用共同 {version} 协议。")
        text = text.replace(f"开发验证保留 v2/v3 已通过的方法，只对 LightMem 复测 {version}；正式十臂将共同冻结。",
                            f"开发验证采用 v2/v3 已通过的方法与 {version} LightMem；正式十臂共同冻结并完成。")
        path.write_text(text)
    print(json.dumps({"delivery_complete": True, "status": str(status_path), "report": str(base / "results.md")}))


if __name__ == "__main__":
    main()
