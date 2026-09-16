# 近期 memory baseline：选择、实现和比较协议

> **2026-09-15：下文是已降级的旧 v5 配置记录，不再是当前实现协议。**
> 当前改为 Mem0 完整 OSS 检索、A-Mem 论文 robust 实现及 LightMem 完整核心；原版 actor、全历史验证仍待完成。
> 请以 [修复记录](faithful-memory-remediation-2026-09-15.md) 和 [当前进展](yujia-progress-2026-09-15.md) 为准。

<!-- recent-memory-completion:start -->
> **完整配对评估已完成：** 十臂均完成 IDs 111/112/113，官方评分与用量完整性检查通过。
> [结果表与逐 episode 比较](../results/real/p2_recent_baselines_tokenrhythm_v5_completed/results.md)；表中完整结果的用量估算 ¥25.3557。
> 新中转探针及全部开发/评估合计估算 ¥46.4821，
> 加旧账单 ¥230 后为 ¥276.4821。缺失用量与 aiaaa 未知费用未计入；不是对账总额。
> 这是三个复用 holdout episodes 的描述性配对复验；不证明 causal necessity 或真实 latent identifiability。
> summary 使用按预先记录的技术恢复规则完成的补跑，其余九臂保留原结果；原始批次的断流失败及费用另行保留。
<!-- recent-memory-completion:end -->
> 当前协议为 TokenRhythm `deepseek-flash`、`p2_recent_baselines_tokenrhythm_v5`。
> 使用流式汇总、共享 2.1 秒请求间隔和有限的 HTTP 错误退避；已打开的中断流不自动重试。
> 开发验证来源见下文；正式十臂比较须全部使用共同 v5 协议。
> [续跑状态](../results/real/p2_recent_baselines_tokenrhythm_v5/recovery_state.json)、
> [测试与预算](tokenrhythm-switch-2026-09-14.md)、[aiaaa 备用接口](aiaaa-relay-2026-09-14.md)。

目标是回应 Yujia “已有 memory 任务的读者认识这些方法”的要求。本次接入三套真实上游实现，
覆盖事实抽取/更新、agentic note evolution 和分层摘要/离线更新；不是把自制检索器改名。
截至 2026-09-14 的仓库版本如下。这里只报告适配后的 MemoryArena 结果，不声称完整复现论文。

| arm | 来源与固定版本 | 实际配置 / 边界 |
|---|---|---|
| Mem0 OSS | [mem0ai/mem0](https://github.com/mem0ai/mem0), `c7ee362aff94a369af70f13f2b4f853f6793ff4c`, package 2.0.20, Apache-2.0 | native `Memory.add/search`；事实抽取、增删改；Qdrant local；HF CPU embedding；top 5。不是需要 MEM0_API_KEY 的 managed MemoryClient；可选 spaCy / fastembed 不安装，使用 native vector 路径 |
| A-Mem author SDK | [agiresearch/A-mem](https://github.com/agiresearch/A-mem), `ceffb860f0712bbae97b184d440df62bc910ca8d`, MIT | native `analyze_content`→`add_note`→evolution，Chroma，`search(k=5)`；SDK README 将论文复现另指向 WujiangXu/AgenticMemory，因此此处明确称作者 SDK variant |
| LightMem short-round | [zjunlp/LightMem](https://github.com/zjunlp/LightMem), `8449d574df6bae1bdf3314a1564da65e2f37e046`, MIT；README 标为 ICLR 2026 | native metadata + text summary，embedding index/Qdrant，top 5；每个已完成 round 作 offline consolidation boundary；不开 precompression/topic segmentation，因为输入已按 travel round 分段；不等同于长对话论文中的完整 LLMLingua 配置 |
| Rolling AR summary | 本仓明确实现 | 每次只用上次 summary 与新写入记录生成下一份 summary；最多 4096 cl100k tokens；超过预算先再压缩一次，仍超长则确定性截断并记账 |
| Dense | 本仓明确实现 | all-MiniLM-L6-v2 cosine，top 5；同 BM25 的 2048-token chunk 单位 |
| BM25 | MemoryArena 原 `RAGMemorySystem` | 原生 BM25，top 3，2048-token chunks；保持历史默认，未把 k 调到最佳成绩 |
| Full context | MemoryArena 原 `LongContextMemorySystem` | 原生 120k token 上限；实际是否触顶可从 context 日志检查 |
| Ours | 本仓 compact-v3 selector | 冻结 `ind` 图、query 引用解析、紧凑 ancestor rows、共同 v3 decoder |
| noG | 历史结构槽位对照 | 保留所有历史槽位，旧 full-plan 序列化；与 ours 同时存在选择和格式差异 |
| noGcompact | 本轮新增消融 | 与 ours 同 constructor 配置，仅 `ablate_graph=True`，同紧凑表示/公开 scaffold/decoder；衡量关闭选择规则的效果，不单独区分图边与 query 解析 |

Mem0 的社区采用度、A-Mem 的 agentic-memory 定位以及 LightMem 的近期发表/维护是选择理由，
不是它们在本任务更有效的证据。没有把 ReasoningBank、MemGPT/Letta 或 LongMemEval 伪列为已跑结果。
当前外部 memory 任务主要是 MemoryArena travel；MINJA/AgentPoison 用于审计，不能代替新的跨任务 memory 分数。

## 模型与适配

当前所有 LLM 调用经 `https://tokenrhythm.studio/v1` 使用 `deepseek-flash`，CPU-only。
旧 bboluo `deepseek-v4-flash` 开发记录独立保留，不与新路由结果拼接。
三套 native baseline 和 dense 使用相同的
`sentence-transformers/all-MiniLM-L6-v2` CPU 模型，384 维；不把 BM25 假装成 semantic embedding。
各上游 embedding 实现可能自行规范化/截断，保留其原有行为。

Actor 共用 v3 decoder、default thinking、32768 completion cap、12 ReAct steps。
Memory metadata 调用统一 disabled thinking、8192 cap；若返回 length，最多一次 16384 cap
重试并计入成本。A-Mem 的 JSON-schema 请求转换为 JSON-object 传输，将原 schema 明示给模型，
并本地验证类型。没有删除其 metadata/evolution prompt。

开发发现 LightMem 的 DeepSeek manager 没有实现 offline update 所调用的 `_call_update_llm`，
而 native OpenAI manager 有同样接口。适配器绑定 **上游 OpenAI manager 的原方法**，仍调用
DeepSeek manager 的 `generate_response` 与本次 relay，不重写更新算法。保留这一适配差异。
A-Mem SDK 的 neighbor bookkeeping 和 `search` 行为原样保留，不能从此配置推断论文最强性能。

每 arm 独立进程、episode 顺序执行、每 episode 新 store。A-Mem 原构造器会 reset Chroma，
因此不能在同一进程并行多个 episode。Qdrant 路径使用每个实例独有目录，禁止复用其他项目目录。
上游源码不修改；依赖安装在 `.tmp/memory-baselines-venv`，不改变全局 Python 环境。
用户指定的 `grpo-pilot` 用于后续交互命令；正在执行的这一轮保留原隔离环境。
两者 transformers 版本不同，且 grpo-pilot 缺少 native baseline 依赖，不能在冻结轮中切换。

## 冻结与报告口径

开发 ID 101 只用于接口、格式、检索和记账适配。评估预先固定为 **111、112、113**，
即既有图 holdout 的前 3 个 IDs；不按新分数选例。每 arm 一次 API 实现。旧 direct DeepSeek
结果不能并入本次 relay 表。这是小样本描述性复验，不是全新的 confirmatory split。

开发接口验证来自多个只修复传输的阶段：noGcompact / Mem0 / A-Mem 用 v2，
ours / noG / BM25 / full / dense / summary 用 v3，LightMem 用 v5。
共同的 task-specific 配置须完全相同，源码/协议/config hashes 记录到开发验证 manifest。
这些开发结果不拼成排名。通过全部接口检查后，十臂正式评估均全新运行共同 v5。

`code/arena_recent_suite.py --phase evaluation --freeze` 以独占创建方式保存协议、ID、模型、
图和代码 hash。正式执行发现代码变化会拒绝继续；需要新版本才能改方法。生成计划完整后使用
官方 evaluator。表中必须包含所有冻结 arms，失败/空结果不能悄悄从 common set 中删除。

`memory_events.jsonl` 记录 write/retrieve 原文、实例/episode/round、LLM usage 与时延；
`llm_call_usage.jsonl` 记录 actor。比较成本只用对应完成实例；开发/失败/中断调用的开销另计，
不把它们删除。旧 bboluo 按 2 元/次、截至认证中断已花 230 元是用户确认的历史费用，
见 [按次预算](recent-memory-flat-call-budget.md)。当前 TokenRhythm 按未缓存输入 2、
缓存输入 0.04、输出 8 元/M token 汇总，包含推理；以
[累计用量快照](../results/development/tokenrhythm_cumulative_budget_2026_09_14.json) 更新规划。
新路由 usage 估算不是后台对账金额，缺失用量/重试与 aiaaa 未知单价另行注明。
并行运行的各 arm wall time 受共享 CPU / relay 负载影响；阶段耗时可解释，不能用来证明厂商普遍速度排名。

## 复现

三套上游按表中 commit checkout 到 `benchmarks/mem0`、`benchmarks/A-mem`、
`benchmarks/LightMem`。依赖只在隔离环境中安装（以已有项目 torch/transformers 环境为基础）：

```bash
python3 -m venv --system-site-packages .tmp/memory-baselines-venv
.tmp/memory-baselines-venv/bin/python -m pip install -r code/requirements-recent-memory.txt
.tmp/memory-baselines-venv/bin/python -m pip install --no-deps ./benchmarks/mem0
```

CPU embedding 本地目录为 `.tmp/models/all-MiniLM-L6-v2`，使用 Hugging Face 的
`snapshot_download('sentence-transformers/all-MiniLM-L6-v2', local_dir=...)` 下载
`*.json, *.txt, *.safetensors, 1_Pooling/*`；评估冻结时记录权重、config 和 tokenizer hash。
当前实际依赖版本另存 `results/development/p2_recent_baselines_v1/dependencies.json`。
不要安装 LightMem 的整套 GPU 环境。开发通过且已冻结后执行评估：

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=code \
  .tmp/memory-baselines-venv/bin/python code/run_with_local_deepseek.py -- \
  .tmp/memory-baselines-venv/bin/python code/arena_recent_suite.py --phase evaluation
```

密钥只由 ignored 的本地 wrapper 注入，不写进 protocol/config/result。
完整结果见 `results/real/p2_recent_baselines_tokenrhythm_v5_completed/results.md`，逐臂来源及 summary 技术补跑见同目录 manifest。原始 v5 批次的失败记录保持不变。
