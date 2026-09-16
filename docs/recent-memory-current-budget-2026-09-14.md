# 本轮累计用量与预算

> **2026-09-15 更新：** 旧 ¥276.482109 保留为基数；完整实现修复新增已记录 ¥44.03236976，累计 ¥320.51447876。
> aiaaa 与 TokenRhythm 均已余额不足，正式新实验尚未启动。未知用量/价格未对账。
> 当前账本见 [faithful_remediation_usage.json](../results/development/faithful_remediation_usage.json)，下文是旧快照。

快照时间：2026-09-14T19:56:00+08:00。

旧 bboluo 用户确认已花 **¥230**；TokenRhythm 已返回的 usage 估算 **¥46.4821**，
两者相加 **¥276.4821**。这是账单与用量估算的合计，不是已对账总额。

| TokenRhythm 阶段 | 已记录响应 | usage 估算元 |
|---|---:|---:|
| 连通性、历史重放、流式与限流探针 | 20 | 0.1148 |
| development/p2_recent_baselines_tokenrhythm_v1 | 58 | 2.1026 |
| development/p2_recent_baselines_tokenrhythm_v2 | 107 | 5.1912 |
| development/p2_recent_baselines_tokenrhythm_v3 | 173 | 7.2773 |
| development/p2_recent_baselines_tokenrhythm_v4 | 766 | 3.2085 |
| development/p2_recent_baselines_tokenrhythm_v5 | 720 | 2.9044 |
| real/p2_recent_baselines_tokenrhythm_v5 | 1793 | 23.5981 |
| real/p2_recent_baselines_tokenrhythm_v5_summary_recovery_1 | 74 | 2.0853 |

包含所有保留的开发版本，即使对应任务失败或中断；不会只计算成功验证的版本。

单价为未缓存输入 2、缓存输入 0.04、输出 8 元/M token；输出包含推理。
失败、中断或旧 SDK 隐式重试可能没有返回 usage；aiaaa 四次探针输入 824 / 输出 539 tokens，单价未知，均未混入金额。

**本轮配对评估已完成。** 原始评估及所有 summary 技术补跑的已记录费用合计 **¥25.6833**，
与上表开发/探针汇总后即为当前整轮用量估算。结果视图只是已生成文件的副本，已排除重复计费。
缺失 usage 与 aiaaa 未知价格仍需平台对账；不能把它们解释为免费。

[逐方法校准、原始计数与来源](../results/development/tokenrhythm_cumulative_budget_2026_09_14.json)
· [公开单价与中转测试](tokenrhythm-switch-2026-09-14.md)
