# P2 结果：发现图驱动的 MemoryArena 插件（更新至 2026-08-30）

> 平台：MemoryArena `group_travel_planner`；60 episodes / 401 rounds。
> 代码：`arena_causal_memory.py`、`travel_grace_discovery.py`、`arena_p2_benchmark.py`、`arena_e2e_run.py`、`arena_e2e_inherit.py`、`arena_e2e_score.py`、`arena_e2e_failure_audit.py`。

## 1. 集成方式

插件实现 MemoryArena 的 `add_chunk` / `wrap_user_prompt` 接口，并通过真实 HTTP endpoints `/memory/initialize`、`/memory/add`、`/memory/wrap_user_prompt` 运行。

MemoryArena 没有 LICENSE，因此本项目不 fork、不 vendor、不修改其源码。`arena_serve_causal.py` 只在进程启动时把本仓 factory 注册到上游 `MEMORY_FACTORIES`。外部 checkout 的 `git status --short` 必须为空；本地下载的航班库通过 `.git/info/exclude` 排除。

## 2. 主指标的含义

answerability-at-cost 不调用 LLM，逐轮检查：

- `cell recall`：query 指向的金标来源单元格值是否出现在交给 agent 的上下文中。
- `round solvable`：该轮全部金标依赖是否都在上下文中。
- `avg context tokens` 与 `compression`：上下文开销及相对全历史的比例。

它测量的是任务表现的上游机制，不是官方 PS/SPS/SR。query 中未显式写出的完整行程骨架不一定进入这套 gold，因此不能把该指标直接称为“任务成功率”。

## 3. 完整 answerability-at-cost 结果

| 系统 | cell recall | round solvable | avg context | compression |
|---|---:|---:|---:|---:|
| `causal-noG` | 1.000 | 1.000 | 2487 | 0.824× |
| `causal-learned` | 1.000 | 1.000 | 1558 | 0.516× |
| `long_context` | 0.999 | 0.994 | 3077 | 1.020× |
| `causal-scaffold` | 0.993 | 0.973 | 1896 | 0.628× |
| `causal` | 0.989 | 0.952 | 1045 | 0.346× |
| **`causal-learned-pure`** | **0.962** | **0.845** | **1142** | **0.378×** |
| `bm25` | 0.920 | 0.719 | 1951 | 0.647× |

数据文件：`p2_benchmark_v2_summary.json` 与 `p2_benchmark_pure_summary.json`。

### 3.1 学得图比手工补丁更好

`causal-learned` 使用从 270 个 travel groups 学出的类型级槽位图。它达到 1.000 / 1.000，同时只使用 1558 tokens：

- 相对 no-graph ablation：2487→1558，省 37.4%，不丢 answerability。
- 相对 full history：3077→1558，约 1.98× 更小。
- 相对 hand scaffold：recall 1.000 vs 0.993，tokens 1558 vs 1896，双轴更好。

学到的共享骨架是 `current_city`、`transportation`、`attraction`；`accommodation` 的 copy rate 仅 0.613，不应被手工当作共享骨架。这正好修复了早期 constraint-only rule graph 饿死 travel agent 的原因。

### 3.2 Pure discovery 移除了人名 oracle

`causal-learned` 仍从 query 中读取被点名的人作为 selection seed。`causal-learned-pure` 不使用这个人名 oracle，只依赖学得结构做发现：

- 对 BM25，cell recall `0.962 vs 0.920`，多 4.2 点。
- round solvable `0.845 vs 0.719`，多 12.5 点。
- context `1142 vs 1951`，少 41.5%。

因此 pure discovery 仍在质量与代价两轴同时优于检索 baseline；但它明显低于 seeded learned arm 的 1.000 / 1.000。正确结论是“positive with an oracle gap”，不是“完全消除了 oracle”。

## 4. 官方端到端结果

`arena_e2e_run.py` 固定共同 episode ID、管理 env/memory server 生命周期、支持已有输出跳过；`arena_e2e_score.py` 解析官方 submission JSONL 后调用 MemoryArena evaluator，并附加 usage。

按照执行前固定的 `docs/extension-protocol-2026-08-28.md`，四臂都完成共同 episode IDs 1–5，共 37 persons。以下 PS/SPS/SR 全部由 MemoryArena 官方 travel evaluator 计算：

| 系统 | PS | SPS | SR | input tokens | output tokens | cost | duration |
|---|---:|---:|---:|---:|---:|---:|---:|
| `causal-learned-pure` | 0.00% | 84.38% | 0.00% | 712,338 | 338,997 | $5.1708 | 2438.49s |
| `causal-learned` | 0.00% | **96.90%** | 0.00% | **645,660** | 249,397 | **$4.1081** | 1659.42s |
| `bm25` | 10.81% | 80.91% | 0.00% | 1,083,238 | 537,475 | $8.0828 | 3783.08s |
| `long_context` | **16.22%** | 93.21% | 0.00% | 1,386,446 | **166,919** | $5.1353 | **1128.21s** |

配对 episode 统计不把 37 persons 伪装成独立样本：

| 比较 | episode-mean SPS Δ | episode bootstrap 95% | W/T/L | episode-mean PS Δ |
|---|---:|---:|---:|---:|
| pure − BM25 | **+3.47 点** | **[+1.11, +5.83]** | 3/2/0 | −11.19 点 |
| learned − BM25 | **+15.99 点** | **[+8.06, +27.14]** | 5/0/0 | −11.19 点 |
| pure − long context | −8.83 点 | [−17.50, −2.50] | 0/1/4 | −15.36 点 |
| learned − long context | +3.69 点 | [0.00, +8.69] | 2/3/0 | −15.36 点 |

读数：

1. pure 相对 BM25 少 34.2% input、36.9% output、36.0% cost、35.5% duration，同时配对 SPS 高 3.47 点；这把 60-episode answerability 的双轴优势延伸到了官方 constraint metric。
2. seeded learned 的 SPS 最高。相对 long context，它少 53.4% input、成本低 20.0%，SPS 高 3.69 点；但 output 多 49.4%、耗时长 47.1%，且 SPS bootstrap 下界为 0。
3. 完整计划的 PS 给出相反结论：pure/learned 都是 0%，BM25 为 10.81%，long context 为 16.22%。四臂没有任何 group 全员通过，所以 SR 都为 0%。

因此官方 e2e 的正确结论仍是 **mixed**：图方法改善 constraint satisfaction 与输入/成本效率，却没有转化成 person-level full-plan pass。五个 episode 比原先的单 episode 扎实得多，但仍不足以把 SPS 的局部优势外推为总体任务成功率提升。

### 4.1 PS=0 的独立确认性重跑

两个方法臂同时为 0% 看似可疑，因此先审计 run A，再按 `docs/ps-rerun-protocol-2026-08-28.md` 做 run B。模型、IDs 1–5、max steps、memory/env 配置全部不变；run B 使用新输出目录，run A 原样保留，禁止挑选较好一次。

| 系统 | PS A / B | SPS A / B | SR A / B | input A / B | output A / B | cost A / B | duration A / B |
|---|---:|---:|---:|---:|---:|---:|---:|
| pure | 0.00% / 0.00% | 84.38% / 83.01% | 0% / 0% | 712,338 / 682,390 | 338,997 / 390,249 | $5.1708 / $5.6085 | 2438.49s / 2696.06s |
| learned | 0.00% / 0.00% | 96.90% / 91.37% | 0% / 0% | 645,660 / 673,561 | 249,397 / 265,364 | $4.1081 / $4.3375 | 1659.42s / 1834.71s |

同一个官方 evaluator 的逐槽审计：

| 系统 | coverage A / B | unparseable A / B | constraint failures A / B | non-constraint failures A / B |
|---|---:|---:|---:|---:|
| pure | 37/37 / 37/37 | 1 / 1 | 15 / 16 | 306 / 278 |
| learned | 37/37 / 37/37 | 0 / 0 | 3 / 6 | 241 / 239 |

这排除了 “0% 来自 submission 缺失或 learned 解析失败” 的解释。learned run B 的 31/37 persons 只错非 constraint slots，6/37 同时错 constraint 与其他 slots；没有任何人 18 个 day/slot values 全过。最接近者 Aaron（ID 3 / person 1）在 run A 与 B 都只错一个非 constraint 的 `day 3 dinner`，但官方 `check_person_full_pass` 是全有或全无，所以仍记失败。pure run B 另有 Mary 的空计划，但其余 36 人也都至少错一槽。

run B−A 的 episode 配对 SPS：pure `−1.37` 点，bootstrap 95% `[−8.10,+4.94]`，W/T/L `2/1/2`；learned `−5.54` 点，`[−11.25,−0.95]`，`0/2/3`。PS 与 SR 则五组全为 ties。正确结论不是“0% 一定是 bug”，而是：**在这个严格 exact-plan PS 下，两个方法臂的 0% 已复现；它和较高 SPS 同时成立，因为 SPS 只看 query-derived constraint slots。**

### 4.2 Post-hoc exploratory repair：只改 query 指定槽位

run B 的 failure audit 进一步给出可操作原因：learned 有 31/37 persons 只错 query 没要求变化的槽位。新 decoder `query-target/base-inheritance-v1` 做三件事：

1. 只从当前 query 解析允许变化的 `(day, slot)`；
2. 这些槽位保留 LLM generation；
3. 其他槽位从公开 base itinerary 原样继承。

runtime 不读取 person gold，也不调用 evaluator 选择值。parser 的离线开发审计使用官方 changed-cell finder，只用于检查漏检：全部 270 groups / 1,869 rounds 中，parsed targets 12,227、official changed cells 10,170、TP 10,170、FN 0、recall 100%。额外 2,057 个是 query 明示、但 gold 恰好等于 base 的目标。由于 parser 已在整个 benchmark 上审计，这不是 unseen confirmatory evaluation。

先对保留的 run B raw generations 做 counterfactual postprocess，不产生新 LLM calls：

| arm | 原 PS | offline inheritance PS | SPS | constraint failures | other-slot failures |
|---|---:|---:|---:|---:|---:|
| pure | 0/37 | 19/37 = 51.35% | 83.01% | 16→16 | 278→13 |
| learned | 0/37 | 27/37 = 72.97% | 91.37% | 6→6 | 239→6 |

这张表只能称为 offline counterfactual。随后两个新 arm 从空目录开始做 fresh online generation：

| arm | PS | SPS | SR | input | output | cost | duration |
|---|---:|---:|---:|---:|---:|---:|---:|
| `causal-learned-pure-inherit` | 30/37 = 81.08% | 90.26% | 0/5 | 312,685 | 270,234 | $3.4841 | 1777.15s |
| `causal-learned-inherit` | **37/37 = 100.00%** | **100.00%** | **5/5 = 100.00%** | 327,525 | 195,083 | $2.7696 | 1236.88s |

统一官方 scorer 独立复核了上述数字。learned−pure 的 episode 配对 PS 差为 `+18.69` 点，bootstrap 95% `[+12.86,+28.33]`，W/T/L `5/0/0`；SPS 差 `+9.74` 点，`[+4.21,+19.58]`，`5/0/0`。

online failure audit：两臂都覆盖 37/37、0 missing、0 unparseable。pure 的 7 个失败 person 共错 13 slots；官方口径为 constraint 12、other 1。other 单例是 Monica 明确要求与 Jasmine 同吃 day-1 dinner，但 Jasmine 的 gold 恰好等于 base，因此官方按“gold 是否偏离 base”没有把它标成 constraint。按 decoder 的 query-explicit 口径，13/13 都是允许变化的 target，继承槽位失败为 0。learned 的 failed slots 为 0。

这个结果说明修复方向有效：inheritance 消除了无关重规划对 exact-plan PS 的惩罚；pure 剩余错误集中在未取回被引用 traveler 后无法求解的 target slots，learned 则通过更完整的相关记忆避免错误级联。边界也同样重要：这是用户质疑后、看过失败模式、在同 IDs 上开发的 exploratory arm。原始四臂与 run B 的负结果不能被覆盖；论文级结论需要冻结 decoder 后在 unseen IDs 上重跑。

### 4.3 Graph-held-out / LLM-e2e-held-out 确认实验

按执行前冻结的 `docs/yujia-confirmatory-protocol-2026-08-29.md`，测试固定为 IDs 101–110，四臂统一使用 `query-target/base-inheritance-v1`。GRACE 类型图和 persistence statistics 只用其余 260 groups：13 条 learned edges，precision `1.000`、recall `0.433`、F1 `0.605`。图文件明确记录 `excluded_episode_ids=[101,...,110]`。

| arm | PS | SPS | SR | input | output | cost | duration |
|---|---:|---:|---:|---:|---:|---:|---:|
| pure graph | **67/73 = 91.78%** | **98.19%** | **60%** | **858,445** | 663,528 | $8.7814 | 4068.41s |
| noG | 65/73 = 89.04% | 97.97% | **60%** | 1,006,049 | 619,642 | **$8.7115** | 3848.87s |
| BM25 | 55/73 = 75.34% | 90.24% | 10% | 1,965,551 | 1,131,231 | $16.2262 | 7066.50s |
| long context | 63/73 = 86.30% | 96.25% | 30% | 3,165,105 | **493,654** | $12.8493 | **3014.27s** |

按 episode 配对，而不是把 73 persons 当作独立样本：

| comparison | PS Δ / bootstrap 95% / W-T-L | SPS Δ / bootstrap 95% / W-T-L | SR Δ / bootstrap 95% / W-T-L |
|---|---|---|---|
| pure − BM25 | **+16.55 / [+9.17,+25.24] / 8-2-0** | **+7.95 / [+5.04,+10.84] / 9-1-0** | +50.00 / [+20.00,+80.00] / 5-5-0 |
| pure − long | +5.18 / [+0.00,+10.54] / 3-7-0 | +1.94 / [+0.16,+4.60] / 4-6-0 | +30.00 / [+0.00,+60.00] / 3-7-0 |
| pure − noG | +1.90 / [−6.13,+11.90] / 2-6-2 | +0.22 / [−1.13,+1.56] / 2-6-2 | 0.00 / [−40.00,+40.00] / 2-6-2 |

冻结判断必须拆开：

1. **pure 相对 BM25 的主判断通过。** PS episode mean 为正且 W>L；pure 还少 56.3% input、41.3% output、45.9% cost、42.4% duration。
2. **graph 相对 noG 的次级判断失败。** PS 没有损失（反而 `+1.90` 点），满足“不损失超过 5 点”；但 input 只减少 `14.7%`，低于冻结的 `30%`。pure 的 output、cost、duration还分别多 7.1%、0.8%、5.7%，不能把它写成 graph 全面提效。
3. pure 相对 long context 在 PS/SPS 上为正，input 少 72.9%、cost 低 31.7%；但 output 多 34.4%、duration 多 35.0%。这仍是多轴 trade-off，不是所有成本维度占优。

执行边界：第一次 long-context 运行在 8/10 后因交互进程中断；plan 文件完整，但 upstream 尚未写出 usage。该目录保留为 `long-context-inherit-holdout-interrupted-8of10`，不参与评分。随后在查看 long-context 分数前，以同一参数从空正式目录完整重跑 10/10；预先承诺只采用这个完整 run，避免二选一。正式 submission 覆盖 10 groups / 73 persons，usage 也覆盖同一组集。

这仍不是 pristine untouched benchmark：IDs 101–110 对图学习和 LLM e2e 均 held out，但旧 query-target parser 曾用 evaluator-derived changed cells 审计全部 270 groups。正确表述是 **graph-held-out / LLM-e2e-held-out confirmation**。

### 4.4 新轮：compact query-ancestry v3，IDs 111–120

旧轮 pure/noG 的 API input 为 858,445 / 1,006,049，只减少 14.67%。对保存轨迹做不调用
LLM、不读取 person gold/evaluator 的组成审计后，原因不是 graph 没有减少 memory：pure/noG
repeated memory context 已从 1,200,004 chars 降到 584,635 chars；但共享 system/base/tool
schema、query 以及同一 episode 内增长的 ReAct/tool-result history 仍占主要开销，context
只占 pure/noG proxy input 的 19.1% / 32.2%。因此单纯继续缩短旧 serialization 很难把 API
input 降幅从 14.7% 推过 30%。

把 full-plan generation 改成 query-target delta serialization 的离线 proxy 后，graph/noG
proxy input 为 1,802,959 / 2,641,822 chars，预计减少 31.75%。该 proxy 只用于定位开销；
正式验收仍只采用 API 返回的 token usage。

冻结前只在 development IDs 101–103 比较候选。v2/8k 虽减少 49.8% input，但 graph/noG
PS 只有 28.57/42.86；v2/32k 的 PS 为 71.43/85.71，input 只减少 5.76%；thinking-disabled
graph PS=0，因此均淘汰。最后冻结的 `query-target/base-inheritance-v3` 只向 LLM 发送
query-explicit target cells、被引用 earlier traveler 的 learned ancestors、compact trip
scaffold 与 target-cell base location cue；不发送历史 raw trace/scratchpad/tool-result 副本
或完整 base plan。其 development graph/noG 结果为：

| arm | PS | SPS | SR | API input | output | cost | API duration |
|---|---:|---:|---:|---:|---:|---:|---:|
| query-ancestry graph | 22/22 = 100% | 100% | 100% | 174,283 | 105,043 | $1.4861 | 658.06s |
| noG | 21/22 = 95.45% | 99.32% | 66.67% | 275,629 | 123,383 | $1.9229 | 772.56s |

graph 相对 noG input 减少 36.77%，episode-mean PS `+4.76` 点，W/T/L `1/2/0`。这只是
development candidate selection，不计入正式通过。

正式协议在 `docs/p2-p3-next-round-preregistration-2026-08-30.md`，机器 manifest 为
`results/real/p2_compact_v3/frozen_protocol.json`。held-out IDs 固定为 111–120，四臂顺序
pure/noG/BM25/long-context，共享 model、v3 decoder、max steps、env、tools 与 episode order。
GRACE graph 和 persistence statistics 只用其余 260 episodes：13 edges，P/R/F1
`1.000/0.433/0.605`，persistent slots 为 current_city/transportation/attraction；typegraph
与 plugin graph 都明确排除 111–120 且 SHA 与 manifest 相符。

这里的 pure 是协议标签，准确名称是 **query-ancestry graph**：它从可见 query 中解析
traveler reference，再取 learned slot ancestors，不是旧 fully name-free pure。与 noG 的
差异是 graph selection + compact serialization 的 bundled intervention，不能把 token 差
只归因于 adjacency mask。旧 parser 已用 evaluator 审计全部 270 groups，所以这一轮只能
称为新的 **LLM-e2e / graph-held-out** 边界，不是 pristine untouched benchmark。

四臂全部一次完成 10/10；统一 scorer、冻结 manifest、config SHA、graph/typegraph SHA、
episode/usage coverage 和实际 runtime 审计均通过，四臂 ledger 均为 0 malformed / 0 missing。
正式结果为：

| arm | PS | SPS | SR | calls | input / output | estimated cost | API / wall duration |
|---|---:|---:|---:|---:|---:|---:|---:|
| query-ancestry graph（pure 标签） | 62/66 = **93.94%** | **99.35%** | 7/10 = 70% | 132 | **434,162 / 321,216** | **$4.2976** | 2,062.87s / 2,071.42s |
| noG | **63/66 = 95.45%** | **99.48%** | **8/10 = 80%** | 135 | 718,215 / 331,166 | $5.1072 | 2,142.08s / 2,149.88s |
| BM25 | 48/66 = 72.73% | 91.91% | 3/10 = 30% | 133 | 1,458,020 / 1,166,215 | $15.3072 | 7,894.49s / 7,904.54s |
| long context | 61/66 = 92.42% | 98.70% | **8/10 = 80%** | **125** | 2,064,625 / **303,546** | $8.1970 | **1,894.82s / 1,902.81s** |

episode-mean paired delta（点）/ 10,000 次 episode bootstrap 95% / W-T-L：

| comparison | PS | SPS | SR |
|---|---:|---:|---:|
| pure − noG | **−1.43 / [−4.29,0.00] / 0-9-1** | −0.13 / [−0.39,0.00] / 0-9-1 | −10.00 / [−30.00,0.00] / 0-9-1 |
| pure − BM25 | **+19.80 / [+10.04,+29.70] / 7-3-0** | **+7.44 / [+3.27,+12.09] / 7-3-0** | +40.00 / [+10.00,+70.00] / 4-6-0 |
| pure − long | +1.07 / [−4.29,+7.50] / 1-8-1 | +0.65 / [−0.39,+2.34] / 1-8-1 | −10.00 / [−30.00,0.00] / 0-9-1 |

冻结判断是两个条件的合取：pure−noG episode-mean PS 为 `−1.43` 点，没有超过允许的
5 点损失；API input 从 718,215 降到 434,162，减少 **39.55%**，超过要求的 30%。因此
这一轮的 graph/noG 正式判断是 **`pass=true` / PASS**。这是新轮正结果，不回写旧轮
IDs 101–110 的 14.7% input 次级条件失败。

成本轴也完整保留：pure 相对 noG 少 3.0% output、15.9% estimated cost、3.7% API
duration；相对 BM25 少 70.2% input、72.5% output、71.9% cost、73.9% duration；相对
long context 少 79.0% input、47.6% cost，但 output 多 5.8%、duration 慢 8.9%。BM25 有
6 次 `finish_reason=length`，统一冻结 repair path 产生 4 次 repair call；这些 episode 没有
删除或重跑。每个 episode 的 calls/input/output/cost/API duration 与覆盖范围保存在
`results/real/p2_compact_v3/round_summary.json` 的 `arms.*.usage.per_episode`，正式
scorer 输入和逐 episode 指标保存在同目录 `e2e_scores.json`。

## 5. 方法本体回归

`regime_grace.py` 的 E0 回归在 σ∈{0,0.01,0.1} 均得到：

| blind | additive u-as-node | regime-conditioned |
|---:|---:|---:|
| 0/2 | 0/2 | **2/2，且均标记 GATED** |

门控边是“父变量系数随 regime 变化”的乘性结构，把 regime 作为普通加性节点不能表达该结构。该 gated 标记在 P3 中直接被防御 gate 消费。

## 6. 复现

机制评测需要先启动 memory server：

```bash
python3 code/arena_serve_causal.py --port 8123
python3 code/arena_p2_benchmark.py \
  --server http://127.0.0.1:8123 --episodes 60 \
  --systems causal-noG causal-learned long_context \
            causal-scaffold causal bm25 \
  --out results/real/p2_benchmark_v2.csv
python3 code/arena_p2_benchmark.py \
  --server http://127.0.0.1:8123 --episodes 60 \
  --systems causal-learned-pure \
  --out results/real/p2_benchmark_pure.csv
```

端到端共同 episode（固定协议为 IDs 1–5）：

```bash
python3 code/arena_e2e_run.py \
  --config results/real/e2e/travel_causal-learned-pure.json \
  --ids 1 2 3 4 5 --start_servers
python3 code/arena_e2e_run.py \
  --config results/real/e2e/travel_causal-learned.json \
  --ids 1 2 3 4 5 --start_servers
python3 code/arena_e2e_run.py \
  --config results/real/e2e/travel_bm25.json \
  --ids 1 2 3 4 5 --start_servers
python3 code/arena_e2e_run.py \
  --config results/real/e2e/travel_long_context.json \
  --ids 1 2 3 4 5 --start_servers
python3 code/arena_e2e_score.py \
  --arms causal-learned-pure causal-learned bm25 long_context
```

确认性 run B 与 failure audit：

```bash
python3 code/arena_e2e_run.py \
  --config results/real/e2e/travel_causal-learned-pure-rerun.json \
  --ids 1 2 3 4 5 --start_servers
python3 code/arena_e2e_run.py \
  --config results/real/e2e/travel_causal-learned-rerun.json \
  --ids 1 2 3 4 5 --start_servers
python3 code/arena_e2e_score.py \
  --arms causal-learned-pure-rerun causal-learned-rerun \
  --out results/real/e2e_scores_rerun.json \
  --reference results/real/e2e_scores.json
python3 code/arena_e2e_failure_audit.py \
  --arms causal-learned-pure causal-learned bm25 long_context \
         causal-learned-pure-rerun causal-learned-rerun \
  --out results/real/e2e_failure_audit.json
```

exploratory inheritance parser audit、fresh online arms 与统一评分：

```bash
python3 code/arena_e2e_inherit.py --validate_targets
python3 code/arena_e2e_run.py \
  --config results/real/e2e/travel_causal-learned-pure-inherit.json \
  --ids 1 2 3 4 5 --start_servers
python3 code/arena_e2e_run.py \
  --config results/real/e2e/travel_causal-learned-inherit.json \
  --ids 1 2 3 4 5 --start_servers
python3 code/arena_e2e_score.py \
  --arms causal-learned-pure-inherit causal-learned-inherit \
  --out results/real/e2e_scores_inherit_online.json
python3 code/arena_e2e_failure_audit.py \
  --arms causal-learned-pure-inherit causal-learned-inherit \
  --out results/real/e2e_failure_audit_inherit_online.json
```

compact-v3 正式矩阵的离线重评分与冻结审计（不调用 LLM）：

```bash
python3 code/arena_e2e_score.py \
  --e2e_dir results/real/p2_compact_v3/e2e \
  --model deepseek-v4-flash \
  --arms query-ancestry-v3-heldout-111-120 \
         noG-v3-heldout-111-120 \
         bm25-v3-heldout-111-120 \
         long-context-v3-heldout-111-120 \
  --pairs \
    query-ancestry-v3-heldout-111-120:noG-v3-heldout-111-120 \
    query-ancestry-v3-heldout-111-120:bm25-v3-heldout-111-120 \
    query-ancestry-v3-heldout-111-120:long-context-v3-heldout-111-120 \
  --out results/real/p2_compact_v3/e2e_scores.json
python3 code/arena_p2_round_summary.py \
  --input results/real/p2_compact_v3/e2e_scores.json \
  --pure query-ancestry-v3-heldout-111-120 \
  --nog noG-v3-heldout-111-120 \
  --bm25 bm25-v3-heldout-111-120 \
  --long-context long-context-v3-heldout-111-120 \
  --expected-ids 111 112 113 114 115 116 117 118 119 120 \
  --graph results/real/p2_compact_v3/travel_learned_graph_holdout_111_120.json \
  --configs \
    results/real/p2_compact_v3/configs/travel_query-ancestry-v3-heldout-111-120.json \
    results/real/p2_compact_v3/configs/travel_noG-v3-heldout-111-120.json \
    results/real/p2_compact_v3/configs/travel_bm25-v3-heldout-111-120.json \
    results/real/p2_compact_v3/configs/travel_long-context-v3-heldout-111-120.json \
  --protocol-document docs/p2-p3-next-round-preregistration-2026-08-30.md \
  --out results/real/p2_compact_v3/round_summary.json
```

Travel 需要 `clean_Flights_2022.csv`；当前本地文件 SHA256 为 `8dafdb0e3f8b79ce599a1e612a772865295bc226b46e5fb278368f7255b11cee`。

## 7. 诚实边界

1. 60-episode 表是 answerability-at-cost，不是 LLM 在环的总体任务成功率。
2. 官方 e2e 每次有 5 个共同 episode；确认性 run B 复现了两个方法臂 PS=0%。inheritance fresh online 得到 pure 81.08%、learned 100%，但它是同 IDs 上的 post-hoc repair，不可替换原结果或宣称已在 unseen 数据上确认。
3. pure discovery 去掉了 query 人名 seed，但 travel query 本身仍点名许多约束；此环境不能证明发现对所有记忆任务都必要。
4. `long_context` 略高于 1.0 compression 是格式开销；任何声称超过信息上界的结果都应先排查编码或计数 bug。
5. compact-v3 在新的 LLM-e2e / graph-held-out IDs 111–120 上通过 graph/noG 验收，但它同时改变 selection 与 serialization，不能把全部 39.55% input reduction 识别为 graph adjacency 的单独因果效应；旧 parser 的全量 evaluator 审计也意味着这不是 pristine untouched benchmark。
