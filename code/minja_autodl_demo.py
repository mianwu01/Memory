"""Render fixed, outcome-independent examples from completed MINJA artifacts.

No API calls. Selection: run 0, lexicographically first query ID in each of
trigger/clean test tracks, repetition 0. No success/failure filtering.
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path


def esc(value):
    return html.escape(str(value))


def code_ids(ids):
    return " ".join(f"<code>{esc(rid)}</code>" for rid in ids) if ids else "<span class='muted'>空</span>"


def source_link(source, label):
    return f"<a href='{esc(source)}'>{esc(label)}</a>"


def collect(root):
    protocol = json.loads((root / "frozen_protocol.json").read_text())
    snapshot = json.loads((root / "seed0/frozen_snapshot.json").read_text())
    graph = json.loads((root / "seed0/regime_structure.frozen.json").read_text())
    cases = []
    for track in ("trigger", "clean"):
        query = min((r for r in snapshot["test_schedule"] if r["track"] == track), key=lambda r: r["id"])
        arms = {}
        for arm in protocol["arms"]:
            relative = f"seed0/test/{query['id']}.r0.{arm}.json"
            result = json.loads((root / relative).read_text())
            arms[arm] = {"result": result, "source": "../" + relative,
                         "ledger_call_id": f"seed0:test:{query['id']}:r0:{arm}"}
        record_ids = sorted({rid for arm in arms.values() for rid in arm["result"]["retrieved_ids_before"]})
        provenance = []
        for rid in record_ids:
            memory = next(r for r in snapshot["memory"] if r["id"] == rid)
            write = next(r for r in snapshot["transcript"] if r["id"] == rid)
            exposures = []
            for row in snapshot["transcript"]:
                if rid not in row["retrieved_ids"]:
                    continue
                exposures.append({
                    **{k: row[k] for k in ("round", "id", "phase", "trigger", "note_present", "retrieved_ids", "answer", "anomalous")},
                    "used_by_frequency_regime": bool(not row["note_present"] and row["trigger"] and row["phase"] in {"pre", "inject_probe", "calibration"}),
                    "used_by_frequency_pooled_and_structure": not bool(row["note_present"]),
                    "record_feature_used_by_structure": bool(not row["note_present"] and rid in graph["inputs"]["record_candidates"]),
                })
            scores = {
                arm: {"score_record": auditor["scores"].get(rid), "selected": rid in auditor["selected"]}
                for arm, auditor in snapshot["auditors"].items()
            }
            edge = next((edge for edge in graph["candidate_edges"] if edge["source_record"] == rid), None)
            provenance.append({
                "record_id": rid,
                "write": {"round": write["round"], "phase": write["phase"],
                          "question": memory["question"], "stored_answer": memory["answer"],
                          "stored_thought": memory["thought"],
                          "raw_response": snapshot["calibration_responses"][write["round"]],
                          "source": "../seed0/frozen_snapshot.json",
                          "json_pointer": f"/transcript/{write['round']}"},
                "calibration_exposures": exposures, "frozen_scores": scores,
                "structure_candidate_edge": edge,
                "poison_label_posthoc_evaluation_only": memory.get("is_poison", False),
                "test_action_by_arm": {
                    arm: {"read": rid in record["result"]["retrieved_ids_after"],
                          "removed": rid in record["result"]["removed_ids"],
                          "answer": record["result"]["answer"], "anomalous": record["result"]["anomalous"]}
                    for arm, record in arms.items()
                },
            })
        cases.append({"track": track, "query": query, "repetition": 0, "arms": arms, "provenance": provenance})
    return {
        "selection_rule": {"run": 0, "sort_key": "query ID as string, ascending", "query_per_track": "first", "repetition": 0,
                           "outcome_filtering": False},
        "requested_model": protocol["config"]["model"], "snapshot_sha256": snapshot["snapshot_sha256"],
        "structure_freeze": snapshot["structure_freeze"], "cases": cases,
        "sources": {"protocol": "../frozen_protocol.json", "snapshot": "../seed0/frozen_snapshot.json",
                    "graph": "../seed0/regime_structure.frozen.json", "api_ledger": "../api_usage.jsonl",
                    "full_report": "../evidence_report.md", "validation": "../validation.json"},
        "interpretation": [
            "These examples are fixed by run/query/repetition; they were not selected for success.",
            "Write/retrieval/action links are instrumented provenance, not an additional causal identification claim.",
            "Auditor scores and graph were frozen from calibration before all held-out calls.",
            "Poison labels appear only as post-hoc evaluation annotations and in the explicitly named oracle policy.",
            "A clean-track query is a normal-input control, not a guarantee that poisoned memory yields a normal answer.",
        ],
    }


def render(data):
    parts = ["""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>MINJA 固定示例 · run 0</title>
<style>
:root{color-scheme:light;font-family:system-ui,-apple-system,"Noto Sans CJK SC",sans-serif;color:#17212d;background:#f5f7fa}
body{max-width:1250px;margin:0 auto;padding:32px 24px 64px;line-height:1.65}h1{font-size:30px;line-height:1.25}h2{margin-top:32px}h3{margin:20px 0 10px}
a{color:#145ca5}nav{display:flex;flex-wrap:wrap;gap:16px}.card{background:white;border:1px solid #dce3eb;border-radius:12px;padding:22px;margin:18px 0}
.muted{color:#657386}.tag{font-size:13px;background:#eaf0f7;padding:3px 8px;border-radius:5px}code{font-family:ui-monospace,monospace;font-size:12px;background:#eff3f7;padding:2px 4px;border-radius:3px;overflow-wrap:anywhere}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f8;padding:14px;border-radius:6px;font-size:13px;line-height:1.55}.table{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;vertical-align:top;padding:10px;border-bottom:1px solid #e0e5ec}th{background:#eef3f8}summary{cursor:pointer;font-weight:600;padding:10px 0}
.yes{color:#a52a2a;font-weight:700}.no{color:#286546}.two{display:grid;grid-template-columns:1fr 1fr;gap:20px}ul{padding-left:22px}.note{border-left:4px solid #708fae;padding-left:16px}
@media(max-width:700px){body{padding:20px 12px}.card{padding:15px}.two{grid-template-columns:1fr}}
</style></head><body>""",
             "<h1>MINJA：固定 run 0 的七臂对照</h1>",
             "<p>按测试 query ID 的字符串顺序，分别取第一条 trigger 与 clean query，均取 repeat 0。<strong>不按实验成败选例。</strong></p>",
             "<nav><a href='#trigger'>Trigger query</a><a href='#clean'>Clean query</a><a href='demo.json'>完整示例 JSON</a>" + source_link(data["sources"]["full_report"], "8,400 次调用的完整报告") + "</nav>",
             f"<p class='muted'>请求模型：{esc(data['requested_model'])}；服务返回别名见每臂原始输出。这里展示单次真实调用，整体结论应读取完整配对结果。</p>",
             "<div class='note'>冻结分数仅来自校准期。记录的写入 → 检索 → action 是运行时来源链；不能仅凭这些连接宣称该记录具有已识别的因果效应。投毒标签仅作事后评价和 oracle 对照。</div>"]
    for case in data["cases"]:
        track, query = case["track"], case["query"]
        parts += [f"<section id='{track}'><h2>{esc(track)} · {esc(query['id'])} · repeat 0</h2>",
                  "<div class='card'>", f"<p>{esc(query['question'])}</p><pre>{esc(query['options'])}</pre>",
                  f"<p>正确答案：<strong>{esc(query['groundtruth'])}</strong>；当前请求 trigger = {1 if track == 'trigger' else 0}。</p>"]
        if track == "clean":
            parts.append("<p class='note'>这是不含 food trigger 的正常输入对照。所有策略均不执行删除，七臂 prompt 相同；记忆仍是受污染快照，因此不预设输出一定正常。</p>")
        parts += ["<div class='table'><table><thead><tr><th>臂</th><th>原 top-3</th><th>删除</th><th>实际读取</th><th>输出</th><th>攻击 / 正确</th></tr></thead><tbody>"]
        for arm, item in case["arms"].items():
            r = item["result"]
            attack = "是" if r["anomalous"] else "否"
            parts.append(f"<tr><td>{source_link(item['source'], arm)}</td><td>{code_ids(r['retrieved_ids_before'])}</td><td>{code_ids(r['removed_ids'])}</td><td>{code_ids(r['retrieved_ids_after'])}</td><td><strong>{esc(r['answer'])}</strong></td><td class='{'yes' if r['anomalous'] else 'no'}'>{attack} / {'是' if r['correct'] else '否'}</td></tr>")
        parts.append("</tbody></table></div>")
        for arm, item in case["arms"].items():
            r = item["result"]
            parts += [f"<details><summary>{esc(arm)}：真实模型输出与请求收据</summary>",
                      f"<p>{source_link(item['source'], '原始结果文件')} · API ledger call ID：<code>{esc(item['ledger_call_id'])}</code></p>",
                      f"<p class='muted'>返回模型：{esc(r['response'].get('_returned_model'))}；prompt SHA256：<code>{esc(r['prompt_sha256'])}</code></p>",
                      f"<pre>{esc(r['response'].get('_raw', ''))}</pre></details>"]
        parts.append("</div><h3>记录来源链与冻结评分</h3>")
        for record in case["provenance"]:
            rid, write = record["record_id"], record["write"]
            parts += [f"<details class='card'><summary>{esc(rid)}：round {write['round']} 写入 → 校准检索 → 本题各臂读取/action</summary>",
                      f"<p>{source_link(write['source'], '写入与校准来源文件')} · JSON pointer：<code>{esc(write['json_pointer'])}</code></p>",
                      f"<p>写入阶段：{esc(write['phase'])}；写入答案：<strong>{esc(write['stored_answer'])}</strong>；投毒标签（仅事后评价）：{esc(record['poison_label_posthoc_evaluation_only'])}。</p>",
                      f"<details><summary>写入的问题与完整输出</summary><pre>{esc(write['question'])}</pre><pre>{esc(write['raw_response'].get('_raw',''))}</pre></details>",
                      "<h4>校准后冻结的分数</h4><div class='table'><table><thead><tr><th>审计器</th><th>冻结分数/支持</th><th>选中</th></tr></thead><tbody>"]
            for method, score in record["frozen_scores"].items():
                score_text = json.dumps(score["score_record"], ensure_ascii=False) if score["score_record"] is not None else "未评分 / 未入候选"
                parts.append(f"<tr><td>{esc(method)}</td><td><code>{esc(score_text)}</code></td><td>{'是' if score['selected'] else '否'}</td></tr>")
            parts += ["</tbody></table></div>", f"<p>{source_link(data['sources']['graph'], '冻结结构拟合输入、候选边与哈希')}</p>",
                      f"<pre>{esc(json.dumps(record['structure_candidate_edge'],ensure_ascii=False,indent=2))}</pre>",
                      "<h4>该记录在校准阶段的实际检索</h4><p class='muted'>仅 note-free 行进入 pooled/structure；frequency_regime 还要求 trigger=1，并符合旧校准阶段规则。</p>",
                      "<div class='table'><table><thead><tr><th>round / phase</th><th>trigger / note</th><th>共同检索 records</th><th>输出 / 攻击</th><th>regime frequency / pooled / structure 中此记录特征</th></tr></thead><tbody>"]
            for exposure in record["calibration_exposures"]:
                parts.append(f"<tr><td>{exposure['round']} / {esc(exposure['phase'])}</td><td>{exposure['trigger']} / {exposure['note_present']}</td><td>{code_ids(exposure['retrieved_ids'])}</td><td>{esc(exposure['answer'])} / {exposure['anomalous']}</td><td>{int(exposure['used_by_frequency_regime'])} / {int(exposure['used_by_frequency_pooled_and_structure'])} / {int(exposure['record_feature_used_by_structure'])}</td></tr>")
            parts += ["</tbody></table></div><h4>从本题 retrieval 到实际 action</h4><div class='table'><table><thead><tr><th>臂</th><th>读到此记录</th><th>删除此记录</th><th>输出 / 攻击</th></tr></thead><tbody>"]
            for arm, action in record["test_action_by_arm"].items():
                parts.append(f"<tr><td>{esc(arm)}</td><td>{int(action['read'])}</td><td>{int(action['removed'])}</td><td>{esc(action['answer'])} / {action['anomalous']}</td></tr>")
            parts.append("</tbody></table></div></details>")
        parts.append("</section>")
    parts += ["<footer class='card'><h2>冻结来源</h2><ul>"]
    for name, link in data["sources"].items():
        parts.append(f"<li>{source_link(link,name)}</li>")
    parts += ["</ul>", f"<p>Snapshot SHA256：<code>{esc(data['snapshot_sha256'])}</code></p>",
              f"<pre>{esc(json.dumps(data['structure_freeze'],ensure_ascii=False,indent=2))}</pre>", "</footer></body></html>"]
    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    args = parser.parse_args()
    root = Path(args.input)
    data = collect(root)
    output = root / "fixed_demo"
    output.mkdir(exist_ok=True)
    (output / "demo.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    (output / "index.html").write_text(render(data))
    print(json.dumps({"output": str(output), "selection_rule": data["selection_rule"],
                      "queries": [c["query"]["id"] for c in data["cases"]]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
