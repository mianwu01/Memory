# 同协议 memory-system 检查（先于本轮系统测试）

沿用 `continuation-protocol-2026-09-22.md` 的 6 个冻结测试任务与 actor。
测试前先在 seed 2/dev/000 验证接口，不按 actor 正确率选系统或换 prompt。

旧 `memsys_llm.py` 不能直接代表本次完整系统：它把返回结果回映射到原记录，
而本机 `A-mem` checkout 的 `add_note` 没有调用其 `analyze_content`。
本轮直接使用作者论文实现 `AgenticMemory` 的 `memory_layer.AgenticMemorySystem`，
其中 `MemoryNote(..., llm_controller=...)` 实际生成 metadata，再运行 evolution。
不在旧实验上补写不存在的 metadata 执行。

版本（借用相邻 Memory checkout 中干净的官方源码，只读）：

| 系统 | commit | 路径 / 实际方法 |
|---|---|---|
| Mem0 OSS | c7ee362aff94a369af70f13f2b4f853f6793ff4c | `Memory.add(infer=True)` → `search(top_k=8)` |
| A-Mem paper implementation | 0c8039f28fdcc08189a23c07a3437d9d2482f9c2 | `add_note` → `find_related_memories_raw(k=8)` |
| LightMem | 8449d574df6bae1bdf3314a1564da65e2f37e046 | compression/segmentation/metadata + offline update → retrieve(limit=8) |

每个完整历史 segment 作为一次按序写入，仅包含公开原始 history 记录。
各系统独立 fresh store；都使用同一个本地 MiniLM embedding；LightMem 用
作者 LLMLingua2 meetingbank 模型 CPU 配置。原生系统的返回文本直接放入
actor 的同一 HISTORY 区域，完整 S0 和 query 不变；无 gold、参数、答案回填。

返回上限 8 个系统原生条目，不等于 8 个原始记录或 top-2 segments。分别报告
实际 actor token、写入/检索 token、延迟；这张表是共同 task/actor/interface
下的原生系统变体比较，**不是严格等 token/记录数的优势检验**。严格预算归因
使用主协议中的 matched BM25/recency/wrong/random 对照。

memory model 同为 `DeepSeek-V4-Pro`、禁用 thinking，生成上限统一 16,384。
A-Mem 原始 1,000 上限由传输层提升；作者 prompt、解析、排序、更新逻辑不改。
保留作者传入的 temperature，并记录每次实际参数。actor 输出规则沿用主协议。
没有基础设施或格式重试；技术异常/截断/作者 fallback 记录为无效运行，不当作
算法得 0 分，也不回退到 embedding 假装系统运行成功。解析或建库失败仍保留
写入成本和失败比例。每个系统/episode 的成功 memory output 独立调用 actor 三次。

此处是 HM3 合成历史的 native-output 适配，不是作者原论文 benchmark 复现。
不会把旁边旧 campaign 的分数拼进本轮表；只复用依赖、模型缓存与官方源码。
