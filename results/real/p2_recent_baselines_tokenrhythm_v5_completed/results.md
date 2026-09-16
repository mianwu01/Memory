# 近期 memory baseline 十臂配对结果

10 个方法均完成 IDs 111/112/113，使用同一冻结的 TokenRhythm `deepseek-flash` 配置。

Ours 与同格式 noGcompact 的逐 episode PS/SPS/SR 全部持平。记录的输入从 245,599 降至 123,701 tokens，减少 49.63%；总费用估算由 ¥0.7713 变为 ¥0.8067（+4.59%）。
Ours / noGcompact 的输出为 83,643 / 73,206 tokens；费用同时计入各自缓存命中量，输入减少不保证总费用下降。

下表为每个 episode 等权的 PS/SPS/SR；这三个 IDs 复用了历史 holdout，结果属于描述性配对复验。
官方 PS 按 person 汇总，原始指标另保存在 `official_scores.json`，与本表等权口径区分。

| 方法 | PS % | SPS % | SR % | Actor 调用 | Memory 调用 | Actor 元 | Memory 元 | 合计元 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Ours | 91.67 | 98.57 | 66.67 | 45 | 0 | 0.8067 | 0.0000 | 0.8067 |
| noG | 87.50 | 98.05 | 66.67 | 45 | 0 | 1.2410 | 0.0000 | 1.2410 |
| noGcompact | 91.67 | 98.57 | 66.67 | 44 | 0 | 0.7713 | 0.0000 | 0.7713 |
| BM25 | 79.17 | 92.89 | 33.33 | 41 | 0 | 2.6270 | 0.0000 | 2.6270 |
| Full history | 87.50 | 96.49 | 66.67 | 43 | 0 | 1.1693 | 0.0000 | 1.1693 |
| Dense | 75.00 | 93.75 | 33.33 | 43 | 0 | 2.7451 | 0.0000 | 2.7451 |
| Rolling summary | 87.50 | 96.49 | 66.67 | 44 | 30 | 1.1015 | 0.9838 | 2.0853 |
| Mem0 OSS | 51.39 | 84.16 | 0.00 | 51 | 25 | 4.2888 | 0.3621 | 4.6510 |
| A-Mem author SDK | 81.94 | 95.98 | 33.33 | 40 | 47 | 1.4699 | 1.0087 | 2.4785 |
| LightMem short-round | 36.11 | 67.73 | 0.00 | 50 | 1305 | 5.6232 | 1.1574 | 6.7806 |

**技术补跑说明：** 原始 v5 批次有九个完整方法；summary 在 episode 111 第 5 轮响应中途断流。
补跑前另行记录最多两次技术补跑规则，保持冻结代码、模型、参数、IDs 和请求级重试规则不变；
summary 采用首个完整补跑，其余九个方法沿用原始完整结果。补跑后才评分，没有按分数挑选。
因此这是带明确来源记录的完整配对表，原始批次本身仍标记为未完整；不是一轮无中断运行。
本表费用对应被采用的完整结果；原失败尝试及全部补跑另计入项目累计费用，复制的视图不会重复收费。
[逐臂来源、协议与文件 hashes](result_view_manifest.json)

表中完整结果的已记录 usage 估算合计 **¥25.3557**。

费用按未缓存输入 2、缓存输入 0.04、输出 8 元/M token 计算，包含推理和 memory 写入/更新。
它是 usage 估算；失败、重试和中断请求可能没有完整用量，不是平台对账单。上游静态 USD cost 字段未用于本表。

每个方法使用自己的历史 actor writeback；相同 episode 并不保证相同历史。因此整体方法对比不等同于单条记忆的因果反事实。
这张表不能单独证明真实 latent identifiability 或 causal structure necessity。此前两个 online mitigation 协议的 FAIL 保留。

开发验证来自不同 transport 修复阶段，未拼成开发排名。正式表的全部方法使用同一个冻结协议。
Mem0 OSS、作者 A-Mem SDK 和 LightMem short-round 为文档列明的实际适配版本，不声称完整复现所有论文配置。

Mem0 / LightMem 分别有 8 / 9 次 actor 响应达到长度上限，随后按共同修复规则处理。
表中表现限定于此模型、decoder、推理方式和 token 预算，不能泛化成这些方法的官方性能排名。

- [完整数据与逐 episode 配对差](paired_results.json)
- [官方 evaluator 输出](official_scores.json)
- [完整性与 actor/memory 用量审计](usage_integrity_audit.json)
- [冻结协议](protocol.json)
- [开发接口验证来源](development_validation_manifest.json)
