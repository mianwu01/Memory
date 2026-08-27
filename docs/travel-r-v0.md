# Travel-R v0:把依赖从当前 query 移回历史(2026-08-20)

> 承 `t0-results.md` §5 路径 2;脚本 `code/travel_r.py`(复用 T0 解析器)。
> 目标:使 travel 满足 C1(无 query 时 oracle)——依赖必须从历史轨迹中获取。

## 1. 变换 R1(前瞻式搬移)

对每条依赖句(target 轮 t 引用 source 轮 P):

- target 轮的原句替换为**指针**:"For {slot} on the {day} day, follow the arrangement
  that was announced for me earlier in the trip."(不含任何 source 信息);
- 原句改写为第三人称"Planning note",**追加到 source 轮 P 的 query**(随 P 轮写入记忆):
  例:Bart 原句 "…at least 20% more than Emma's first-day stay" → Emma 轮新增
  "Planning note: On the second day, Bart is looking for accommodation that costs
  at least 20% more than **my** first-day stay, is rated higher, …"。

全量:6,829 条依赖句全部搬移(5,393 条自足句原样保留);指针 0 条退化为泛化形式。
叙事许可:相当于"团队协调人把后续旅客的要求提前留言给相关旅客"——DGP 改动已声明。

## 2. 审计结果

| 审计 | 结果 | 读法 |
|---|---|---|
| A1:变换后当前 query 可解析出的依赖 | **1 / 6,829(0.01%)** | **C1 达成**:实例 DAG 不再是当前 query 的函数 |
| A2:BM25@3 召回 gold source 轮 | 0.893 | 但随机基线 @3 = **0.711**(候选池仅 ~4.5 块) |
| A3:历史中 mask 掉 target 姓名后 BM25@3 | 0.871 | 自名捷径只值 **-0.02** |
| 随机基线 @5 | 0.919 | 池太小,任何检索都"接近解决" |

## 3. 诚实结论

- **结构轴修复成功**:query 时 oracle 消失(A1),依赖只能从历史块中读出;
  且"读出"需要**写入时组织**(planning note 在 source 轮写入,消费在若干轮之后)——
  这正是 write–hold–read 的 write 侧被真正启用。
- **难度轴仍未达标(C4)**:每 episode 仅 5–8 块,随机 @3 已 0.71,BM25 只比随机高
  0.18,mask 姓名几乎无损——不是因为检索聪明,是因为池小。**travel-R v0 满足 C1,
  不满足 C4。** 加硬路线(v1,按成本排序):
  1. **拼长历史**:把多个 episode 的块并入同一记忆池(池 ×10,随机基线塌到 ~0.07);
  2. **注入干扰 note**:同名异事、过期覆盖(顺带引入 knowledge-update 结构);
  3. **R2 去名化**:note 不点名 target,改多跳描述("将与 Emma 同住的那位旅客,
     其第二日住宿须…")——单跳检索无法定位,必须先解析中间指涉。R2 只需改
    `third_person()` 的姓名替换分支,生成器骨架已就绪。
- 产物:`travel_r_rows.json`(schema 与原数据一致,answers 不变,可直接喂
  `data_loader.py` 同款流程)。

## 4. 与 E0 的关系

travel-R 的 (X_t^i, u_t) 现在有了真实语义:note 写入 = write 事件,块驻留 = hold,
指针轮消费 = read。E0 v0 已证明这类门控结构**必须**用 u_t 才能发现(blind 全盲)——
travel-R 上 u_t 可从块类型(note / plan / pointer)直接标注,两条线在 v1 汇合。
