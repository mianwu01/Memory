# 第二个 session 的任务单（2026-09-18，共享工作区）

分工：本 session（API + provenance）负责 `code/`、API shard 结果与文档；**第二个 session 只跑确定性
CPU 任务并只提交结果文件**。两边都在分支 `claude/hm3-handoff-2026-09-18`；提交前 `git pull --rebase`。

## 环境

```bash
cd /mnt/cpfs/epic-user/yangboxue-20260612/opsd/Memory
export PYLIB=/mnt/cpfs/epic-user/yangboxue-20260612/opsd/claude_persist/tmp/claude-20043/-mnt-cpfs-epic-user-yangboxue-20260612-opsd-Memory/aa111f6d-b918-45ce-bc18-326170fa9a1b/scratchpad/pylib2
export PYTHONPATH=$PYLIB:code
export OMP_NUM_THREADS=4
```

`pylib2` 含 torch 2.14 CPU、scikit-learn 1.9、joblib、openai、socksio。系统 python3 没有这些包。

## 任务 A：HM3 scaling 的确定性 dev 面板（最高优先级）

设计：`docs/hm3-history-scaling-design-2026-09-18.md`。两个领域可并行两个进程：

```bash
for D in travel shopping32; do
  nohup python3 -m hm3.run_scaling --domains $D --seeds 0 1 2 \
    --conditions native 50 100 500 a100 b100 c100 d100 --split dev \
    --learners exact_kv source_union source_regime knn superset program program_reg graph graph_pooled \
               rh_oracle oracle retrieval_k8 retrieval_k16 recency_k16 bm25_k16 graph_select wrong_select_1 wrong_select_2 wrong_select_3 \
    --out results/development/hm3/scaling/det_dev_$D.json > results/development/hm3/scaling/det_dev_$D.log 2>&1 &
done
```

已知耗时（travel，train 200）：graph 1–3 s；program 7 s（native）→ 12 s（100）→ 500 档明显更慢
（>10 min）；program_reg 5–21 s；gnn_est 25–30 s；augment 500 档 16 s。黑盒 `flat`/`flat_est`/`gnn`/
`gnn_est` 不在主面板内；若 CPU 充裕，另跑一次 `--seeds 0 --conditions native 500 --learners flat flat_est gnn gnn_est`
到 `det_dev_blackbox_$D.json`。runner 可中断重跑：已完成的 (domain, seed, condition) 会跳过。

汇总：`python3 -m hm3.run_scaling --summarize results/development/hm3/scaling/det_dev_travel.json`。
把两个领域的表贴到 `docs/hm3-history-scaling-results-2026-09-18.md` 的"dev"一节（文件由本 session 创建，
若尚不存在就新建），并按设计 §5 逐条判 P1–P4。

## 任务 B：test 面板（dev 完成并判定后）

```bash
for D in travel shopping32; do
  nohup python3 -m hm3.run_scaling --domains $D --seeds 30 31 32 --train_seed_offset 100 --split test \
    --conditions native 50 100 500 \
    --learners exact_kv source_union source_regime knn superset program program_reg graph graph_pooled \
               rh_oracle oracle retrieval_k8 retrieval_k16 recency_k16 bm25_k16 graph_select wrong_select_1 wrong_select_2 wrong_select_3 \
    --out results/real/hm3/scaling/det_test_$D.json > results/real/hm3/scaling/det_test_$D.log 2>&1 &
done
```

## 任务 C：E0 v2 补齐（较低优先级，CPU 空闲时）

```bash
PYTHONPATH=$PYLIB nohup bash code/e0v2/run_all.sh > results/e0v2/chain.log 2>&1 &
```

已知问题：`grace_official` 与 `pcmci` 两个外部臂因旧 pylib 的 numba 0.67 与 pylib2 的 numpy 不兼容而
ImportError；它们的错误行会写进 `results/e0v2/e0a.jsonl`，重跑前需要删掉含 `"error"` 的行。修复办法是
在 pylib2 里装一个与其 numpy 匹配的 numba（`pip3 install --target $PYLIB numba`），再只跑这两个臂。

## 提交范围

第二个 session 只提交：`results/development/hm3/scaling/`、`results/real/hm3/scaling/det_test_*.json`、
`results/e0v2/`、以及结果文档里自己写的表格。不要改 `code/`；发现 bug 在文档里记下来。

## 2026-09-18 晚补充：selection ladder 臂（代码已提交，`git pull --rebase` 后可用）

`bm25_k16`（BM25 top-16 → restricted_est → 执行器）、`graph_select`（沿学得 skeleton 读取 → 同一执行器）、
`wrong_select_1/2/3`（沿三个固定重接线的 skeleton 读取 → 同一执行器）。dev seed 0 的快速结果：Travel
graph_select 三档全 1.000（reads 11–12 持平），wrong_select 0.60 / 0.03 / 0.03，bm25_k16 0.95 → 0.03 → 0.03，
recency_k16 0.97 → 0.52 → 0.37；Shopping 的 cart 两跳内全连通，wrong_select_1/2 与 graph_select 读到同一集合，
该对照在 Shopping 无区分力（如实报告）。旧的 `wrong_graph_k`（majority 沿错误拓扑）继承 superset 的
collateral 失败，EES 恒为 0，只放附录，不进主表。已完成的 (domain, seed, condition) 会被跳过，所以对已有的
det_dev_*.json 追加这些臂需要删掉对应 entry 的 `complete` 标记，或写到新文件 `det_dev_ladder_$D.json`。

## 2026-09-19 凌晨补充：Shopping 增广的丢弃率修正（需要重跑 Shopping 的 50/100/500 条件）

`augment_split` 在 5 次重试都失败后改为把全部外来 segment 放在真实历史之前再验证一次（`fallback_no_interleave`，
统计里记录次数）。原因：Shopping 的 promo strictness witness 由 segment 之后的 cart 状态推出，只有在整条历史
里才会出现，逐 segment 的插入检查看不到；test seed 30 在 500 档原来丢弃 27%，修正后 64/64 保留（17 个
episode 走 fallback）。**请 `git pull --rebase` 后删除 `det_dev_shopping32.json`、`det_dev_ladder_shopping32.json`
里 key 以 `/50`、`/100`、`/500`、`/b100`、`/c100`、`/d100` 结尾的 entry（或直接换新文件名重跑这些条件）**；
Travel 不受影响（丢弃率 0–2%）。
