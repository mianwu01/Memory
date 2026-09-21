# 给 Yujia：方法重做后的一页（2026-09-22）

> **状态修正：这是待论证的方法转向草案，不能视为 Yujia 已认可的新主线。**
> 以下“观测分布不能识别”、通用 O(k log n)、Shopping v2 准确率及将
> graph_seg 数字归给新方法的表述均暂停使用。最新定义与决定规则见
> `structure-alignment-protocol-2026-09-21.md`；实际新增对照见 alignment 结果目录。

上一页（`docs/yujia-causal-bridge-2026-09-20.md`）回答了"结构能否由成熟的 causal discovery 得到"。这一页回答审稿人会问的下一个问题："方法是什么，'causal' 落在哪里"。

## 一句话

记忆系统对**自己的读取**做干预：把已记录的 episode 重放，只让一部分记录可见，看决策是否仍正确；自适应消元在 O(k log n) 次重放内找到最小充分读集（formulation 里的 causal frontier 限制到 carrier）。这不需要 faithfulness——干预在读取上，写入过程是确定性的也无妨（这正是 9/20 扫描里 PCMCI+/GRACE 剪掉中介边的原因，命题 1）。一个 parser-free 的类型级 frontier 模型把重放摊销到测试时；后向追责用同一原语（干净替换重放 + 结构顺序前缀搜索）。

图：`results/real/hm3/figures/method_schematic.pdf`（日志 → 屏蔽重放 → 最小读集 → frontier 模型 → 前向读 / 后向定位；观测式发现作为对照虚线）。

## 形式化对象与两个命题（正文 `docs/paper-draft-method-2026-09-21.md`）

- π-frontier：S ⊆ H 充分 ⇔ c(π(S₀, I, S)) = 1；最小充分集 F^π。单调使用假设下 F^π 由重放识别。
- 命题 1：写入是父节点的确定函数时（agent 日志皆如此），观测分布对机制图不 faithful，任何 CI 方法至少剪掉链上一条边。9/20 扫描是它的实例。
- 命题 2：单调使用下，F^π 由重放 oracle 识别，ddmin 用 O(|F| log n) 次重放返回最小充分集；不单调时返回 1-minimal 集，界相同。

## 四条主张与数字

**1. 读取干预识别结构，观测检验不能。** 执行器 frontier 2–3 条记录，14 次重放（18 条候选）；类型投影对干预式骨架 precision 1.0（缺的一条边是没有隐藏策略、无需读取的 stay→activity）。同一批日志上 PCMCI+ recall 0.4、Shopping 上空图。**LLM 自己的重放**（多数票 k=3，187 个 episode，两种 prompt）恢复同样四条边，precision 1.0；LLM 的 frontier 与执行器只重叠 0.26–0.48——LLM 靠 stay 自己的 txn 记录（0.84 个/episode）而执行器靠 flight 干预记录（0.03）。frontier 是 actor-specific 的（图 `frontier_composition.pdf`）。

**2. 读 frontier 让记忆随历史不增长，并抵御冲突证据。** 重放次数 15 → 22 → 27（18 → 100 → 500 条），frontier 大小 2.7 → 3.0 不变（dev 与 test seeds 一致，图 `replay_length.pdf`）。三个 test seed 的 actor 面板（v1，n = 190–192）：结构 − 全历史 +0.13 [+0.04, +0.21] / +0.16 [+0.08, +0.24] / +0.21 [+0.14, +0.29]（100 / 冲突 100 / 500），每个 seed 同号；token 4k 对 27k–123k。v2 prompt 三 seed 复制（9/22 完成）：+0.37 [+0.29, +0.46] / +0.35 [+0.27, +0.43]（冲突 100 / 500，n = 190），每个 seed 同号。parser-free 的重放拟合选择器 − 全历史：v1 冲突下 +0.11 [+0.04, +0.18]，其余持平；v2 下 +0.24 [+0.15, +0.33] / +0.16 [+0.08, +0.24]（冲突 100 / 500，seeds 31/32），但比 parser 版低 0.15–0.21；Shopping 上它是三臂中最好的（500 条：比全历史 +0.25 [+0.11, +0.39]，v2），把 Shopping 从"只有成本主张"变成准确率主张。

**3. 同一原语反向定位肇事记录。** Travel 四个长度：结构顺序中位数 1–2 次重放（均 2.5–3.6）；历史顺序 8 → 13 → 18（log n）；BM25 对异常 4–13。Shopping：native 上 BM25 与结构相当（3–4 vs 4），500 条上结构 2–6 vs 18。图 `replay_localise.pdf`。

**4. 边界，如实写。** (a) 摊销是弱环：parser-free 模型在 Travel 500 条为达到 recall ≥ 0.96 要读 12–80 条（同 key 的 c 型干扰在分类特征上不可分），actor 层比 parser 版低 0.17；Shopping 不过度选择。(b) 从 LLM 自己的重放拟合的选择器（55–73 个含噪 episode）还不如执行器重放拟合的（200 个精确 episode）：0.16–0.21，负结果。(c) DeepSeek-V4-Flash 温度 0 三次同样调用在 7/12（v1）个 episode 上自相矛盾，所以 LLM oracle 必须投票；全历史通过率 29–39%，限制了可标注的 episode。(d) native 长度下读全历史更好（v2）。

## 措辞

"causal" 指 do(read)（记忆系统自己执行的干预）和受控仿真 E0；观测式恢复的边称 temporal dependency structure，作为对照保留。

## 到 9/25

9/22 已完成：v2 prompt 三 seed 复制、500 条格补齐、表冻结（状态页 §4.9）；实验节按新方法重写（Tables 1–9、消融表、边界节）；附录（协议、prompt、成本，`docs/paper-draft-appendix-2026-09-22.md`）；内审记录（`docs/paper-internal-review-2026-09-22.md`）。9/23–25：按内审条目做文字终稿。所有实验的入口：`docs/full-status-method-experiments-paper-2026-09-21.md`。
