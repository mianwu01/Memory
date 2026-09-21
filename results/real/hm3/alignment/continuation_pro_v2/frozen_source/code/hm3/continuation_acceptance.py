"""Chinese item-by-item acceptance page; reads completed or partial artifacts."""
import json
from pathlib import Path


def generate():
    root = Path("results/real/hm3/alignment/continuation_pro_v2")
    r = json.loads((root / "report.json").read_text())
    cost = json.loads((root / "cost_audit.json").read_text())
    native = r["native_systems"]
    all_native_finished = all(c["status"]["status"] != "pending" and
                              (c["status"]["status"] != "completed" or c["actor_attempts"] == 3)
                              for cells in native.values() for c in cells)
    completed = r["actor_rows"] == 1020 and all_native_finished
    audit_passed = sum(x["source_audit_diagnostic_rule_passed"] for x in r["episodes"])
    full_stable = sum(x["results"].get("full") == {"n": 3, "correct": 3} for x in r["episodes"])
    a = r["arms"]
    fmt = lambda x: "缺失" if x is None else f"{100*x:+.1f} pp"
    t = ["# 9/22 继续执行：逐项验收与未解决问题", "",
         f"**本轮执行{'已结束' if completed else '仍在进行'}；尚未达到 Yujia 的完整研究要求。** "
         "本页优先于旧方法叙事，但不撤销 9/21 的负结果。全部工作在本地完成，未联系 Yujia。", "",
         "已完整阅读交接指定的三份对齐文档、总报告和 UnCLe 报告，并核对原始结果："
         "旧 GRACE-open/parser 的 1,531/1,531 完整输入等同 complete；旧随机 gate 的 "
         "12/12 个 outcome-parent 集合由 PCMCI-G² 单独复现，正确数仍为 11/12。没有重跑这些实验。", "",
         "## 新实验回答什么", "",
         "固定请求 DeepSeek-V4-Pro（主面板返回 ID 为 DeepSeek-V4-Pro-0813，另有 1 次小写 "
         "deepseek-v4-pro-0813，原样留档）、v1/verbose、16,384 输出上限、"
         "temperature 0、关闭 thinking。使用新 Travel seeds 70/71/72，各前两个 episode。"
         "这是**合成 HM3 上的真实 LLM actor**，不是原生真实 MemoryArena 任务。", "",
         "每个完整历史 segment 是一个可见性 gate；每 episode 128 次随机 gate 请求。"
         "PCMCI+ / G² 只允许已知随机化设计下 gate→正确性的候选边。主选读为固定 top-2 "
         "segment 排名，不称已识别 causal parents。独立三次验证覆盖 full、query-only、"
         "BM25、recency、三错误结构、三匹配随机集合和来源干预。", "",
         "| 逐项要求 | 本轮实际完成 | 验收判断 |", "|---|---|---|",
         "| 变量、样本、时间步、场景 | 原字段状态面板与 segment read-gate 分开定义；保存具体面板 | 定义已澄清；没有默认认可主线转向 |",
         "| 成熟 discovery | 沿用 PCMCI+ / G²；不再堆算法名称 | 接入完成，不能代替结构贡献 |",
         "| 恢复可靠结构 | 检查原状态样本量；在实际 actor 上拟合 outcome 依赖并独立验证选读与来源干预 | 未证明完整原轨迹图可靠恢复；没有完整父节点独立 flip reference |",
         "| 同一结构改善记忆 | 新 episode、同 actor/state/prompt/output，含严格记录数与代理 token 控制 | 见配对结果；未建立真实任务或摊销后的总效率优势 |",
         f"| 正确输出来源审计 | 6 个外部固定来源场景全部保留；full 稳定正确 {full_stable}/6，完整诊断规则通过 {audit_passed}/6 | 诊断规则通过也不等于成熟可信审计；安全替代工具仍缺 |",
         "| 代表性 memory systems | 实际调用 Mem0、A-Mem paper、LightMem；保留原生返回文本、成本和错误 | 同任务/接口小表已执行；原生 top-8 不等 token，不能写成严格同预算优势 |", "",
         "## Actor 结果与结构归因", "",
         "| 方法 | 正确 / 已完成调用 | 完整 episode | 平均记录数 |", "|---|---:|---:|---:|"]
    for name in ["learned_top2", "full", "bm25_matched", "recency_matched", "query_only"]:
        x = a.get(name, {})
        count = x.get("mean_records")
        count_text = f"{count:.2f}" if count is not None else "缺失"
        t.append(f"| {name} | {x.get('correct_calls',0)}/{x.get('completed_calls',0)} | {x.get('complete_episodes',0)}/6 | {count_text} |")
    t += ["", "| top-2 减去对照 | 配对 episode | 差值 | 95% 区间 |", "|---|---:|---:|---|"]
    for name in ["full", "bm25_matched", "recency_matched", "random_within_episode_mean", "wrong_within_episode_mean"]:
        c = r["paired_comparisons"].get(name, {})
        ci = c.get("ci95")
        t.append(f"| {name} | {c.get('paired_episodes',0)} | {fmt(c.get('delta'))} | {'['+fmt(ci[0])+', '+fmt(ci[1])+']' if ci else '缺失'} |")
    t += ["", "重复先在 episode 内平均；随机/错误图的三个对照也先在 episode 内平均。"
          "区间只在三个固定 seed 内重采样 episode，不能当作一般环境或模型总体区间。", "",
          "首例 `travel-s70-test-000` 只有两个 segment，所以 top-2 与 full **完整输入相同**。"
          "即使两臂正确数不同，也只能说明输出波动，不能归于 discovery。其他重合与完整"
          "序列化 token 残差保存在 report.json。", "",
          "原轨迹面板有 57–60 个数值字段，只有 2–7 个 segment 转移；更不能把不同对象、"
          "不同隐藏规则的 episode 直接拼成同一平稳轨迹。因此本轮没有用这些短面板硬拟合"
          "字段 SCM，也没有把 read-gate 的试验 lag 冒充原记忆时间。", "",
          "## 正确输出审计与安全处置", "",
          f"6 个固定案例中 full 三次全正确为 {full_stable}/6；同时满足来源 edge、full 3/3、"
          f"中性干预 3/3、阻断及改值均最多 1/3 的案例为 {audit_passed}/6。每例全表见机器报告。"
          "没有按结果替换 case。来源权限是外部受控设定，不推断恶意或隐藏思想。", "",
          "冻结的 +15 分钟干预同时平移历史时间值，可能保留 pickup−arrival 等差值规则；"
          "因此改值后不变不证明没有来源依赖。full 本身不稳定已足以使预期演示不成立。", "",
          "HM3 没有独立授权检索工具。已执行来源阻断，只保留其他授权日志；abstain 是建议"
          "的后续控制规则，本轮未实现并独立验证安全控制器。不把同内容改标签算作安全替代。"
          "此处没有提供完整可信审计闭环。", "",
          "## 系统比较：实际执行及失败", "",
          "| 系统 | memory 成功完成 | actor 正确 / 完成 | 无效执行（不混成 actor 0 分） |",
          "|---|---:|---:|---|"]
    for system, cells in native.items():
        invalid = [f"{c['episode']}: {c['status'].get('error_type',c['status']['status'])}"
                   for c in cells if c["status"]["status"] != "completed"]
        t.append(f"| {system} | {sum(c['status']['status']=='completed' for c in cells)}/6 | "
                 f"{sum(c['correct'] for c in cells)}/{sum(c['actor_calls'] for c in cells)} | {'; '.join(invalid) or '无'} |")
    t += ["", "Mem0 使用 infer=True；没有用 raw embedding 冒充完整系统。A-Mem 使用论文实现，"
          "实际生成 metadata 和运行 evolution；只修复缺失的 Python `re` 导入。LightMem 实际"
          "启用 compression、segmentation、metadata 与 offline update 入口；空提取结果保留。"
          "原生系统输出不回映射成原始记录。写入/检索请求、快照、输出和异常均留档。", "",
          "两次 native 无效执行首先由服务异常触发：A-Mem 第 5 次写入请求返回 HTTP 400，"
          "随后作者异常处理触发 UnboundLocalError；LightMem 首次请求出现 APIConnectionError，"
          "随后 usage=None 的处理触发 AttributeError。它们不构成算法效果的负证据。", "",
          "完整输入审计另修复了 episode JSON 键顺序造成的共享 S0 排列差异。最终表使用"
          "actor_v2：system/state/query 与主实验逐字一致，复用全部既有 native memory output；"
          "旧 actor 结果单独留档并计费，不混入最终表。", "",
          "A-Mem 的 k=8 还会展开链接邻居；三系统的条目不等于原始记录。小样本合成事务任务"
          "上的这些数字不能外推为系统的一般优劣，也不替代原生真实任务的公平比较。", "",
          "## 成本、复现与保留工作", ""]
    dc = r["discovery_cost"]
    ct = cost["totals"]
    t += [f"discovery 本身使用 {dc['fresh_training_calls']} 个完成的训练请求，"
          f"{dc['training_input_tokens']:,} 输入 / {dc['training_output_tokens']:,} 输出 tokens。"
          "没有跨 episode 摊销，不能只报告选读阶段少几个 tokens 而声称总效率提高。", "",
          f"本轮全部新调用（含开发、无效运行及系统写入，排除缓存复用）有 {ct['fresh_responses']} "
          f"个已记账响应，{ct['input_tokens']:,} 输入 / {ct['output_tokens']:,} 输出 tokens。"
          f"按旧费率情景折算 ${ct['legacy_rate_scenario_usd']:.4f}，**这不是 Pro 实际价格或供应商账单**；"
          "失败/在途请求可能另计。历史约 $27.35 的旧费率统计没有拼入本轮费用。", "",
          "120 秒 timeout 的旧 attempt 保留。300 秒版本只复用成功返回（包括答错）的响应，"
          "失败恢复独立记录；没有重跑已有成功调用。起始 67 个未提交文件的 SHA-256 校验另存"
          "preservation_check.json；不 commit、不 reset、不删除旧结果。", "",
          "主要入口：", "",
          "```bash", "PYTHONPATH=code python3 -B -m unittest hm3.test_continuation hm3.test_structure_alignment",
          "PYTHONPATH=code python3 -B -m hm3.continuation_report",
          "PYTHONPATH=code python3 -B -m hm3.continuation_artifacts",
          "PYTHONPATH=code python3 -B -m hm3.continuation_acceptance", "```", "",
          "报告重建不发 API。原请求输入、模型参数、返回 ID、usage、异常、代码 hash、依赖版本"
          "和冻结源代码均已保存。API 密钥没有写入这些材料。", "",
          "- [机器报告](../results/real/hm3/alignment/continuation_pro_v2/report.md)",
          "- [全部数值与配对结果](../results/real/hm3/alignment/continuation_pro_v2/report.json)",
          "- [结构及全部冻结审计案例](../results/real/hm3/alignment/continuation_pro_v2/structure_and_audit.svg)",
          "- [成本与失败请求](../results/real/hm3/alignment/continuation_pro_v2/cost_audit.json)",
          "- [冻结主协议](continuation-protocol-2026-09-22.md)",
          "- [系统协议](continuation-memory-systems-2026-09-22.md)",
          "- [A-Mem 执行修复](continuation-amem-adapter-2026-09-22.md)",
          "- [完整序列化修复](continuation-serialization-repair-2026-09-22.md)", "",
          "## 仍需解决的科学问题", "",
          "本轮不支持把“接入算法”“有一个正数”或“native baseline 跑过”作为完成标准。"
          "原轨迹内 observable memory state 的可靠结构、代表性真实 agent 收益、稳定且可执行"
          "的正确输出来源审计，仍需接在同一方法上。", "",
          "目前不据此把主线替换成 read-gate。若继续原主线，需要有足够有效转移且能够独立"
          "验证机制的实际记忆轨迹；若收窄为 policy read dependence，需要明确承认这是不同"
          "科学对象，并解决 oracle 标签、逐任务拟合成本和安全替代接口。上述选择仅作本地"
          "讨论准备，不代表 Yujia 已同意。", ""]
    Path("docs/continuation-results-2026-09-22.md").write_text("\n".join(t))


if __name__ == "__main__":
    generate()
