"""All-case report and total-cost accounting, including development failures."""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path

import numpy as np
from .runtime import save
from .status import summarize,preservation


def paired(rows,a,b):
    table={(r['case'],r['method']):r for r in rows}
    cases=sorted(set(r['case'] for r in rows))
    values=np.array([float(table[c,a]['correct'])-float(table[c,b]['correct']) for c in cases])
    rng=np.random.default_rng(220922);samples=values[rng.integers(0,len(values),(10000,len(values)))].mean(axis=1)
    return dict(mean=float(values.mean()),ci95=np.quantile(samples,[.025,.975]).tolist(),n_cases=len(cases))


def run(args):
    base=Path(args.base);dev=base/'dev_v2';discovery=base/'discovery_dev';evaluation=base/'evaluation_dev';audit=base/'audit_dev'
    gate=json.loads((dev/'reader_gate.json').read_text());fit=json.loads((discovery/'fit.json').read_text())
    ev=json.loads((evaluation/'results.json').read_text());au=json.loads((audit/'results.json').read_text())
    rewired=json.loads((base/'evaluation_rewired_dev/results.json').read_text())
    ev['rows'].extend(rewired['rows'])
    evidence_only=json.loads((base/'audit_evidence_only_dev/results.json').read_text())
    plans=json.loads((evaluation/'frozen_selections.json').read_text());interventions=json.loads((audit/'frozen_interventions.json').read_text())
    projection=json.loads((discovery/'projection.json').read_text())
    bymethod=defaultdict(list)
    for r in ev['rows']:bymethod[r['method']].append(r)
    comparisons={m:paired(ev['rows'],'discovered',m) for m in bymethod if m!='discovered'}
    method_summary={m:dict(correct=sum(r['correct'] for r in rows),n=len(rows),mean_content_tokens=float(np.mean([r['content_tokens'] for r in rows])),identical_to_discovered=sum(r['identical_to_discovered'] for r in rows),truncated=sum(r['finish_reason']=='length' for r in rows)) for m,rows in bymethod.items()}
    accounts={};total=Counter();attempts=complete=failures=unknown=0;budget_anomalies=[]
    for path in sorted(base.rglob('ledger.jsonl')):
        data=summarize(dev,path.parent);key=str(path.parent.relative_to(base))
        accounts[key]={k:data[k] for k in ['request_attempts','completed_responses','infrastructure_failures','unresolved_or_inflight','tokens','returned_models','finish_reasons']}
        total.update(data['tokens']);attempts+=data['request_attempts'];complete+=data['completed_responses'];failures+=data['infrastructure_failures'];unknown+=len(data['unresolved_or_inflight'])
        for line in path.read_text().splitlines():
            row=json.loads(line)
            if row['event']!='result':continue
            request=json.loads((path.parent/'inputs'/f"{row['prompt_sha256']}.json").read_text())
            actual=(row['response'].get('usage') or {}).get('completion_tokens',0)
            if actual>request['max_tokens']:
                planned_sha=row['job'].split('/')[1] if row['job'].startswith('evaluation/') else None
                affected=[dict(case=r['case'],method=r['method']) for r in ev['rows'] if r['prompt_sha256']==planned_sha]
                budget_anomalies.append(dict(stage=key,job=row['job'],prompt_sha256=row['prompt_sha256'],requested_max_tokens=request['max_tokens'],reported_completion_tokens=actual,affected_methods=affected))
    costs=dict(tokens=dict(total),attempts=attempts,completed=complete,infrastructure_failures=failures,unresolved_intents=unknown,
               legacy_price_scenario_usd=((total['input']-total['cached_input'])*2.5+total['cached_input']*.25+total['output']*10)/1e6,
               note='Legacy-rate scenario only, not confirmed Flash pricing or invoice. Interrupted requests can cost extra.',by_stage=accounts,reported_output_budget_exceedances=budget_anomalies)
    audit_summary={}
    for c in au['all_cases']:
        rows=[r for r in au['rows'] if r['case']==c];p=next(p for p in interventions if p['case']==c)
        audit_summary[c]=dict(applicable=p['applicable'],reason=p.get('reason'),target=p.get('target'),complete_target=p.get('complete_target'),replacements=p.get('replacements'),
            answer_occurrences_outside_target=p.get('answer_occurrences_outside_target'),conditions={condition:dict(correct=sum(r['correct'] for r in rows if r['condition']==condition),
            counterfactual_followed=sum(r['counterfactual_followed'] for r in rows if r['condition']==condition),abstained=sum(r['abstained'] for r in rows if r['condition']==condition),
            n=sum(r['condition']==condition for r in rows)) for condition in sorted(set(r['condition'] for r in rows))})
    same_complete=method_summary['complete']['identical_to_discovered'];same_topic=method_summary['topic_only']['identical_to_discovered'];n=len(plans)
    stop=same_complete==n or same_topic==n
    full_agents=[json.loads(p.read_text()) for p in sorted((base/'full_agent_dev').glob('case_*.json'))]
    embedding_probe=json.loads((base/'embedding_probe.json').read_text()) if (base/'embedding_probe.json').exists() else None
    acceptance=dict(frozen_development_execution_complete=len(ev['rows'])==210 and len(au['rows'])==105 and len(evidence_only['rows'])==15,
        actor_qualified=gate['passed'],native_read_write_object_recorded=True,semantic_memory_mechanism_validated=False,
        independent_discovered_edge_contribution=False,reliable_safe_action_chain_established=False,research_requirements_met=False,
        train_test_expansion_permitted=gate['passed'] and not stop,
        not_executed=['New training IDs 10–29 / test IDs 30–39, stopped by predeclared gates.',
                      'Mem0/A-Mem/LightMem on this same qualified native-task protocol; existing panels are separate.'])
    record=dict(acceptance=acceptance,actor_gate=gate,native_tool_capable_full=full_agents,embedding_capability_probe=embedding_probe,evidence_only_repair=evidence_only,methods=method_summary,paired_differences=comparisons,structure_stop_condition=stop,
                fit=fit,topics=projection['top_words'],audit=audit_summary,costs=costs,preservation=preservation('/tmp/hm3-discovery-continuation-start.json'))
    save(base/'report.json',record)
    lines=['# Progressive Search：四关开发验证结果','',
      '固定开发验证已执行；研究要求未达标。第三、四关均实际使用同一discovery，但接入本身不作为贡献验收。', '',
      '这是固定开发集的执行与可证伪检查。文本投影不等于原生语义字段SCM，开发拟合/评估不等于held-out贡献证明。',
      '',f"Actor：{gate['correct']}/30；{gate['stable_cases']}/10题3/3；资格门槛 passed={gate['passed']}。原始30行均保留。",'',
      f"单独的原生可用工具full agent严格正确{sum(r['correct'] for r in full_agents)}/{len(full_agents)}（每题一次，不等于三次稳定性）；格式失败保留，不与只读reader混合。",'',
      f"原生写入{sum(fit['trajectory_lengths'])}次，lag1相邻对{fit['lag1_pairs']}，PCMCI有效候选样本{fit['effective_pcmci_samples']}；任务边界保持独立。",'',
      '子问题分解与最终query线索由原始数据集给定，不归因于discovery。10题query无URL/官方完整答案连续字面，但这不是语义无泄漏证明；见query_dependency_review.json与专门复核文档。', '',
      f"主图{int(np.sum(fit['primary']['adjacency']))}条边；去任务均值诊断{int(np.sum(fit['within_task_centered_diagnostic']['adjacency']))}；时间置换{int(np.sum(fit['time_shuffle']['adjacency']))}。边列表、全部p/q值与20次bootstrap在JSON。",'',
      f"Discovered与complete输入相同{same_complete}/{n}；与topic_only相同{same_topic}/{n}；事前结构停止条件触发={stop}。",'',
      '原wrong_17/29/43仅置换标签，因主图全为自环而退化为原图；补充rewired_17/29/43为三张真实不同的固定错图，原行保留。', '',
      '另补last_answer_reuse和question_answer_reuse，防止完整trace的检索分数掩盖更简单的历史答案复用。补充规则先于其新增响应冻结，单列开发对照。', '',
      '| 方法 | 正确 | 平均内容代理tokens | 与discovered同输入 | 截断 |', '|---|---:|---:|---:|---:|']
    for m,r in method_summary.items():lines.append(f"| {m} | {r['correct']}/{r['n']} | {r['mean_content_tokens']:.0f} | {r['identical_to_discovered']}/{r['n']} | {r['truncated']} |")
    lines+=['','关键配对差（discovered减对照；按题bootstrap95%区间）：','',
            '| 对照 | 正确率差 | 95%区间 |','|---|---:|---:|']
    for name in ['complete','topic_only','bm25_matched','recency_matched','last_answer_reuse','question_answer_reuse','full']:
        comparison=comparisons[name];lo,hi=comparison['ci95']
        lines.append(f"| {name} | {100*comparison['mean']:+.0f} pp | [{100*lo:+.0f}, {100*hi:+.0f}] pp |")
    lines+=['','同输入共享响应，不作为独立重复。full主表取资格化repeat0，三次稳定性另报；不同序列化长度/预算残差均保留。配对CI按case bootstrap，仅10题，不外推。','',
            '## 来源审计','',f"固定{len(au['all_cases'])}题均入报告，适用{len(au['eligible_cases'])}题；不稳定题没有替换。",'',
            '| case | 适用 | discovered/complete定位 | 实质替换次数 | block正确 | complete block正确 | 来源闭包阻断UNKNOWN | change跟随反事实 | neutral正确 | 授权替代正确 | 空记忆UNKNOWN |',
            '|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for c,r in audit_summary.items():
        def val(cond,key):
            d=r['conditions'].get(cond);return f"{d[key]}/{d['n']}" if d else 'N/A'
        lines.append(f"| {c} | {r['applicable']} | {r['target']}/{r['complete_target']} | {r['replacements']} | {val('blocked','correct')} | {val('complete_blocked','correct')} | {val('source_blocked','abstained')} | {val('changed','counterfactual_followed')} | {val('neutral','correct')} | {val('authorized','correct')} | {val('no_evidence','abstained')} |")
    lines+=['','授权替代有真实corpus读取、禁止docid表和原文hash。这里的撤销政策是模拟权限，不能推断原文作者恶意；删除单条后其他记录可能保留同一事实。未发生答案替换的case不能算实质信息干预成功。','',
            '## 授权证据隔离的追加修复','',
            '原授权重取将writer猜测与工具文档混写，case6明确未获得证据仍猜NYU，三次reader均沿用错误答案。追加条件只保留真实工具返回，排除全部assistant文本；五例全部执行，每例三次。不改原结果，不归因于发现边。','',
            '| case | 证据-only正确 | 严格UNKNOWN | 截断 | 实际文档含官方答案字面 |',
            '|---|---:|---:|---:|---|']
    for c in au['eligible_cases']:
        rows=[r for r in evidence_only['rows'] if r['case']==c]
        support=au['authorized_provenance'][str(c)]['literal_reference_support_docids']
        lines.append(f"| {c} | {sum(r['correct'] for r in rows)}/{len(rows)} | {sum(r['abstained_strict'] for r in rows)}/{len(rows)} | {sum(r['finish_reason']=='length' for r in rows)} | {', '.join(support) if support else '未发现'} |")
    lines+=['','字面支持不等于所有约束均有证据；答对也不能替代来源核查。UNKNOWN开头但附解释的诊断另存，不把格式问题直接等同不安全行动。', '',
            '证据隔离后case6仍3/3答错NYU；case0还新增一次错误人名。该修复未通过安全拒答检查，也未证明错误唯一依赖writer猜测。', '',
            '## 成本与结论范围','',f"全部chat阶段已记录{complete}个响应、{attempts}次请求意图；基础设施失败{failures}次，未有终结记录{unknown}次（含早期中断）。失败/中断的额外费用未知。",'',
            '另有一次模型目录查询与一次embedding能力调用（404），单列保存。当前检索后端与作者稠密后端不同，不能把资格失败只归于生成模型。', '',
            f"输入{total['input']:,}、缓存输入{total['cached_input']:,}、输出{total['output']:,}、reasoning {total['reasoning']:,} tokens。旧费率情景${costs['legacy_price_scenario_usd']:.4f}，不是Flash确认价格或账单。",'',
            f"服务端usage有{len(budget_anomalies)}次completion_tokens超过请求max_tokens，具体请求、数值和受影响方法见JSON costs.reported_output_budget_exceedances。保留全部响应并按实际usage计入成本；相同请求上限不代表实际推理预算受控，也不把异常响应删掉后另报优胜结果。",'',
            'discovery本身没有额外LLM调用，但原生轨迹采集、开发接口失败、模型推理和授权重取均已计入；不能用短reader输入声称总效率收益。', '',
            '成熟算法执行、局部正确率和可运行干预不自动满足Yujia。必须额外成立：可解释的同一记忆机制、独立发现边贡献、跨任务泛化与可信来源处置。既有Mem0/A-Mem/LightMem结果属其他面板，未拼入本表。', '',
            f"保留检查：{record['preservation']['checked']}个起始未提交文件，改变{len(record['preservation']['changed'])}个。"]
    (base/'report.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(dict(actor_passed=gate['passed'],stop_structure_claim=stop,method_summary=method_summary,eligible_audits=len(au['eligible_cases']),completed_api_responses=complete)))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',default='results/development/progressive_search');run(p.parse_args())
