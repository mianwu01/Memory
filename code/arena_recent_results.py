"""Write a reviewable paired-result report only after full scope validation."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import statistics

from arena_recent_memory import ARMS, ROOT
from arena_recent_report import audit_family


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--base',type=Path,required=True)
    args=parser.parse_args()
    base=args.base.resolve()
    view_path=base/'result_view_manifest.json'
    view=json.loads(view_path.read_text()) if view_path.exists() else None
    if view:
        if view['state']!='complete' or set(view['arm_sources'])!=set(ARMS):
            raise RuntimeError('Incomplete provenance view')
        for arm, source in view['arm_sources'].items():
            if source['protocol_sha256']!=view['original_protocol_sha256']:
                raise RuntimeError('Recovery used a different frozen protocol: '+arm)
            for name, digest in source['e2e_artifact_sha256'].items():
                if hashlib.sha256((base/'e2e'/arm/name).read_bytes()).hexdigest()!=digest:
                    raise RuntimeError('Result view input changed: '+arm+'/'+name)
    audit=audit_family(base)
    if not audit['paired_scope_complete']:
        raise RuntimeError('Refusing to report a paired ranking with incomplete scope')
    scores=json.loads((base/'official_scores.json').read_text())
    rows=[]
    for arm in ARMS:
        result=scores[arm]
        if result.get('error') or set(map(int,result['episode_ids']))!=set(audit['episode_ids']):
            raise RuntimeError('Official evaluator scope mismatch: '+arm)
        usage=audit['arms'][arm]
        row={'arm':arm,'official_metrics':result['metrics']}
        for metric in ['ps','sps','sr']:
            row[metric+'_episode_mean']=statistics.mean(r[metric] for r in result['per_episode'].values())
        row.update(actor_calls=usage['actor']['responses_with_usage'],
            actor_length_responses=usage['actor_finish_reasons'].get('length',0),
            memory_calls=usage['memory']['responses_with_usage'],
            actor_estimated_cny=usage['actor']['estimated_cny'],
            memory_estimated_cny=usage['memory']['estimated_cny'],
            input_tokens=usage['actor']['input_tokens']+usage['memory']['input_tokens'],
            output_tokens=usage['actor']['output_tokens']+usage['memory']['output_tokens'],
            cached_input_tokens=usage['actor']['cached_input_tokens']+usage['memory']['cached_input_tokens'])
        row['estimated_cny']=row['actor_estimated_cny']+row['memory_estimated_cny']
        rows.append(row)
    report={'schema':'memoryarena-recent-results/v1','family':base.name,'episode_ids':audit['episode_ids'],
        'complete':True,'rows':rows,'paired_comparisons':scores['_paired_comparisons'],
        'model':audit['model'],'endpoint':audit['endpoint'],
        'interpretation':'Three reused historical holdout episodes, one retained complete realization per arm/episode; descriptive paired replication with any technical rerun separately disclosed.',
        'new_causal_necessity_proven':False,'real_identifiability_proven':False,
        'currency':'CNY','invoice_verified':False,'estimated_evaluation_cny':sum(r['estimated_cny'] for r in rows)}
    report['original_batch_complete']=not bool(view)
    report['post_freeze_technical_recovery']=bool(view)
    if view:
        report['result_provenance']=view
    by_arm={r['arm']:r for r in rows}
    ours, compact=by_arm['ours'],by_arm['noGcompact']
    comparison={'input_tokens_reduction_percent':100*(1-ours['input_tokens']/compact['input_tokens']),
        'estimated_cny_change_percent':100*(ours['estimated_cny']/compact['estimated_cny']-1),
        'all_episode_ps_sps_sr_tied':all(abs(delta)<1e-10
            for metric in report['paired_comparisons']['ours_minus_noGcompact']['metrics'].values()
            for delta in metric['episode_deltas'].values())}
    report['ours_vs_same_format_control']=comparison
    report['analysis_source_hashes']={name:hashlib.sha256((ROOT/'code'/name).read_bytes()).hexdigest()
        for name in ['arena_recent_results.py','arena_recent_report.py','arena_e2e_score.py']}
    report['protocol_sha256']=hashlib.sha256((base/'protocol.json').read_bytes()).hexdigest()
    (base/'paired_results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    labels={'ours':'Ours','noG':'noG','noGcompact':'noGcompact','bm25':'BM25','full':'Full history',
        'dense':'Dense','summary':'Rolling summary','mem0':'Mem0 OSS','amem':'A-Mem author SDK','lightmem':'LightMem short-round'}
    observation=("Ours 与同格式 noGcompact 的逐 episode PS/SPS/SR 全部持平。"
                 if comparison['all_episode_ps_sps_sr_tied'] else
                 f"Ours / noGcompact 的 episode-mean PS 分别为 {ours['ps_episode_mean']:.2f}% / {compact['ps_episode_mean']:.2f}%。")
    observation+=(f"记录的输入从 {compact['input_tokens']:,} 降至 {ours['input_tokens']:,} tokens，减少 {comparison['input_tokens_reduction_percent']:.2f}%；"
                  f"总费用估算由 ¥{compact['estimated_cny']:.4f} 变为 ¥{ours['estimated_cny']:.4f}（{comparison['estimated_cny_change_percent']:+.2f}%）。")
    text=['# 近期 memory baseline 十臂配对结果','',
        '10 个方法均完成 IDs 111/112/113，使用同一冻结的 TokenRhythm `deepseek-flash` 配置。',
        '', observation,
        f"Ours / noGcompact 的输出为 {ours['output_tokens']:,} / {compact['output_tokens']:,} tokens；费用同时计入各自缓存命中量，输入减少不保证总费用下降。", '',
        '下表为每个 episode 等权的 PS/SPS/SR；这三个 IDs 复用了历史 holdout，结果属于描述性配对复验。',
        '官方 PS 按 person 汇总，原始指标另保存在 `official_scores.json`，与本表等权口径区分。','',
        '| 方法 | PS % | SPS % | SR % | Actor 调用 | Memory 调用 | Actor 元 | Memory 元 | 合计元 |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for r in rows:
        text.append(f"| {labels[r['arm']]} | {r['ps_episode_mean']:.2f} | {r['sps_episode_mean']:.2f} | {r['sr_episode_mean']:.2f} | {r['actor_calls']} | {r['memory_calls']} | {r['actor_estimated_cny']:.4f} | {r['memory_estimated_cny']:.4f} | {r['estimated_cny']:.4f} |")
    if view:
        text += ['', '**技术补跑说明：** 原始 v5 批次有九个完整方法；summary 在 episode 111 第 5 轮响应中途断流。',
            '补跑前另行记录最多两次技术补跑规则，保持冻结代码、模型、参数、IDs 和请求级重试规则不变；',
            'summary 采用首个完整补跑，其余九个方法沿用原始完整结果。补跑后才评分，没有按分数挑选。',
            '因此这是带明确来源记录的完整配对表，原始批次本身仍标记为未完整；不是一轮无中断运行。',
            '本表费用对应被采用的完整结果；原失败尝试及全部补跑另计入项目累计费用，复制的视图不会重复收费。',
            '[逐臂来源、协议与文件 hashes](result_view_manifest.json)']
    text += ['',f"表中完整结果的已记录 usage 估算合计 **¥{report['estimated_evaluation_cny']:.4f}**。",'',
        '费用按未缓存输入 2、缓存输入 0.04、输出 8 元/M token 计算，包含推理和 memory 写入/更新。',
        '它是 usage 估算；失败、重试和中断请求可能没有完整用量，不是平台对账单。上游静态 USD cost 字段未用于本表。','',
        '每个方法使用自己的历史 actor writeback；相同 episode 并不保证相同历史。因此整体方法对比不等同于单条记忆的因果反事实。',
        '这张表不能单独证明真实 latent identifiability 或 causal structure necessity。此前两个 online mitigation 协议的 FAIL 保留。','',
        '开发验证来自不同 transport 修复阶段，未拼成开发排名。正式表的全部方法使用同一个冻结协议。',
        'Mem0 OSS、作者 A-Mem SDK 和 LightMem short-round 为文档列明的实际适配版本，不声称完整复现所有论文配置。','',
        f"Mem0 / LightMem 分别有 {by_arm['mem0']['actor_length_responses']} / {by_arm['lightmem']['actor_length_responses']} 次 actor 响应达到长度上限，随后按共同修复规则处理。",
        '表中表现限定于此模型、decoder、推理方式和 token 预算，不能泛化成这些方法的官方性能排名。','',
        '- [完整数据与逐 episode 配对差](paired_results.json)',
        '- [官方 evaluator 输出](official_scores.json)',
        '- [完整性与 actor/memory 用量审计](usage_integrity_audit.json)',
        '- [冻结协议](protocol.json)',
        '- [开发接口验证来源](development_validation_manifest.json)']
    (base/'results.md').write_text('\n'.join(text)+'\n')
    (base/'usage_integrity_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))
    print(json.dumps({'complete':True,'report':str(base/'results.md'),'estimated_evaluation_cny':report['estimated_evaluation_cny']}))


if __name__=='__main__':
    main()
