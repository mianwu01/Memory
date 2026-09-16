# Baseline 来源与方法验收审查（2026-09-15）

**结论：上游来源和运行完成可确认；实现忠实度、配置充分性与研究要求仅部分满足。**
9/14 完成记录表示固定十臂、三个 episode 的输出和评分完成，不表示论文复现或研究验收全部通过。
本次仅离线读取代码、README、冻结配置和日志，没有新增 API 调用。

## 已核实

| 仓库 | origin | 与冻结协议一致的 HEAD |
|---|---|---|
| MemoryArena | github.com/ZexueHe/MemoryArena.git | `6cd9de14b71915e39ac742a20dc33785e14b6aab` |
| Mem0 | github.com/mem0ai/mem0.git | `c7ee362aff94a369af70f13f2b4f853f6793ff4c` |
| A-Mem SDK | github.com/agiresearch/A-mem.git | `ceffb860f0712bbae97b184d440df62bc910ca8d` |
| LightMem | github.com/zjunlp/LightMem.git | `8449d574df6bae1bdf3314a1564da65e2f37e046` |

四个 checkout 的 git status（包含未跟踪文件）均为空。冻结记录中 11 个代码、图和 embedding 文件哈希均匹配。
适配器从这些 checkout 调用 Mem0 Memory.add/search、A-Mem analyze_content/add_note/search、
LightMem add_memory/retrieve 与 offline update。BM25、full history 加载 MemoryArena 原生类。
Dense、rolling summary 是本项目实现；Ours、noG、noGcompact 是本项目方法及消融。
**十臂不是十个独立外部官方 baseline。**

十臂 agent、task_specific、env 配置逐项相同。每臂均有 3 次初始化、25 次写入和 22 次检索，
IDs 为 111/112/113。Mem0、A-Mem、LightMem 已记录 memory LLM 响应分别为 25、47、1305 次。
这确认真实执行及来源，不等于充分发挥方法能力，也不等于完整校验所有依赖和运行时行为。

## 影响验收的发现

1. **Mem0 功能降级。** [原始日志](../results/real/p2_recent_baselines_tokenrhythm_v5/logs/mem0.log)
   第 29–31 行确认 spaCy 未安装、lemma/full 模型加载失败，以及
   `fastembed not installed - BM25 keyword search disabled`；后续 episode 重复出现该警告。
   上游 `mem0/vector_stores/qdrant.py:102` 存在对应降级分支。
   该结果应限定为依赖受限的 OSS 配置，不能代表完整混合检索或 managed platform。
2. **A-Mem 复现入口与检索路径。** [作者 README](../benchmarks/A-mem/README.md) 第 18 行明确把
   论文复现指向 `https://github.com/WujiangXu/AgenticMemory`；当前使用 agiresearch/A-mem SDK。
   适配确实执行 metadata analysis 与 add_note 内的 process_memory，保留演化调用。
   但 [适配器](../code/arena_recent_memory.py) 第 327 行调用普通 search；
   [上游 search](../benchmarks/A-mem/agentic_memory/memory_system.py) 第 431 行起仅返回 Chroma top-k，
   不遍历 links。不能据此认定论文的关联记忆机制已被充分检验。
3. **LightMem 为 short-round 变体。** [适配器](../code/arena_recent_memory.py) 第 211 行关闭
   pre_compress/topic_segment，保留 metadata、summary、embedding 检索；第 298 行起每次写入后
   构建全库 update queue 并执行 offline consolidation。DeepSeek manager 缺失的更新 helper
   绑定上游 OpenAI manager 原方法。这些开关是上游支持的配置，关闭本身不是伪实现；
   但完整论文设置尚未复现，每轮全量更新对语义与费用的影响也未隔离。
4. **官方评分器配合本地 actor/decoder。** code/arena_e2e_score.py 调用 MemoryArena evaluate()；
   code/arena_e2e_run.py 改写提示词、按 query 过滤工具、让 actor 只输出目标格子，
   再由共同 v3 decoder 从公开 base 补齐其他格子。所有臂共享这些处理，但不是官方默认端到端设置。
   正确名称是“共同 v3 decoder 下的 MemoryArena Travel 对比”。
5. **预算充分性未通过验证。** 本次重算 Mem0/LightMem 的 actor length 次数为 8/9，各有 6 次 repair；
   Ours/noGcompact 均为 0。相同上限不自动意味着充分配置。不能认定低分全由方法导致，
   也不能认定全部由截断导致。

## 对 Yujia 要求的实际覆盖

Setting、变量口径、具体 slide、段落/句子 outline 已有材料；simulation 保持冻结。
增加近期方法的方向已执行，但官方论文路径与功能充分性仍需验收。
外部 memory 新评估仍仅三个复用的 Travel episode；尚未覆盖其他已有 memory 任务，不能支持通用排名。
LoCoMo/LongMemEval 是后续可选例子，转录没有指定必须运行其中哪一个。

Ours 与 noGcompact 的逐 episode PS/SPS/SR 持平，输入减少 49.63%，费用增加 4.59%。
该消融关闭联合选择规则，没有单独隔离 learned edges 和 query 引用解析，结构必要性尚未证实。
具体 demo 是共同历史下的读取内容对比，不是 actor 反事实性能证据。
MINJA 风险案例涉及可观测记忆、实验标签与运行时顺序，不能解释为识别私有意图或看穿撒谎；
两个在线缓解协议的 FAIL 保留。

## 下一轮验收顺序

先补齐 Mem0 所选 OSS 路径的功能依赖；按作者指向核对 A-Mem 论文构建、演化、链接和检索路径；
对照 LightMem 作者脚本确定完整机制和合理更新边界。用可核对的开发例验证实际写入、检索、更新，
再确定预算和 decoder 对照，最后冻结新评估。仅改一个 SDK 调用不能宣称复现通过。

已有 v5 及技术补跑保留为历史配置结果，不覆盖、不混入新版本。
本次审查不启动额外付费实验。当前接受范围是这些具体配置下的小样本结果及有边界的 demo/outline，
不是完整官方复现、充分配置下的排名、跨任务有效性或 causal necessity。
