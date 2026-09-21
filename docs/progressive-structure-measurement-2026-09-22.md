# 文本记忆状态测量与结构诊断：首次拟合前冻结

原生LongContextMemorySystem只有追加文本store，没有四个预先语义命名的数值
状态。因此以下是可重复的**文本投影测量**，不是原生字段SCM，也不等于已满足
Yujia的“有意义记忆结构”。字段可解释性、共享机制、样本量均需另作验收。

## 测量

只用固定开发轨迹的真实memory_entry拟合TF-IDF（英语停用词，单词unigram，
最多4096维，min_df=2，max_df=.98）与4维非负矩阵分解（NNDSVDa，seed22，
max_iter1000）。保存词表、IDF、矩阵、每维top20词及重构误差，不看gold。
每个写入内容投影为非负4维w_t。定义可观测累积状态S_t=sum(w_0..w_t)，同时
保存真实原文snapshot哈希；S不是原文的无损表示，也不称latent causal state。
发现对象为实际write时钟上的增量ΔS_t=w_t，不将重复reader/API编号当时间步。
为诊断外部给定query造成的共同驱动，将w_t对同一冻结投影下的当前query做
ridge(alpha=1)残差化（仅训练fit），发现残差的lag1关联。线性去混杂不保证
因果充分性；主报告同时给未残差化结果，不从名义p值推导完整因果图。

## 拟合与验证

官方Tigramite PCMCI+ / ParCorr，tau_min=tau_max=1，pc_alpha=.05，
max_conds_dim=max_conds_py=max_conds_px=1，BH校正lag1集合到.05。
每task独立数组multiple模式，禁止拼接边界。保存全部p/value/graph。
按trajectory有放回bootstrap20次（seed2200+i），报告边频率；不以频率重新
挑阈值。另用每条轨迹内时间置换（seed2300）作诊断，非充分因果反证。

若native actor资格通过，训练用10–29、冻结测试30–39；开发不进正式fit。
若资格失败，不启动这批额外采集。仍完成用户要求的第三、四关**有界开发诊断**：
对已有dev轨迹拟合/评估并明确in-sample，仅用于检查结构消费及审计可执行性，
不能报成held-out方法成绩。此分支不追加逐题128次LLM discovery；discovery
本身零LLM调用，全部已有轨迹生成成本仍计入。actor失败时不得用这批诊断
抵销资格失败或声称研究完成。

## 固定结构消费者与对照

final query的最大投影维度为seed。discovered允许seed及其lag1祖先对应的
主导topic记录。complete允许所有topic；错误结构用17/29/43置换节点标签。
在eligible记录中统一按BM25(final query, 原始entry)排序。最多两条记录，
每条最多8192 cl100k代理tokens，保留原session时间戳。不足不偷偷补其它topic；
与full的全部原文输入区别单列。BM25使用所有记录，recency选最后两条，
random用同三seed从全部记录选与discovered相同条数；另保存token残差。
追加真正同token上限的BM25/recency/random预算对照，避免用大记录获利。
answer-reuse选BM25最高的原生历史答案，仅作简单对照；query-only不含memory。

完整序列化prompt相同则共享一次响应，所有method→prompt映射保留；共享
响应不是独立重复。三个full重复用于稳定性资格，方法比较主表用repeat0。
所有case都报告；相同输入比例、差异、成本与小样本不确定性必须披露。

### 首次拟合前补充：表示规则与发现边的归因

总是先在dev做一次离线可行性拟合，不因actor分数好而跳过结构消费检查。
增加topic_only：同一投影、同一query seed、空图。它隔离“topic表示/相关性
过滤”本身的作用，避免把没有发现边时的投影检索收益记在discovery名下。
若discovered与complete或topic_only在全部固定dev输入上相同，停止该结构
贡献主张及额外训练/测试大规模采集；仍按用户指示完成已冻结dev第三、四关
对照与干预，报告为开发诊断。如果两者均存在不同输入且actor通过，才执行
10–29训练、30–39测试。以上停止条件先于首次fit和method输出，不按胜负决定。

同时报告逐task去均值后的图作为任务固定效应诊断（短序列去均值也可能引入
偏差，不能当新主结果择优）。主图若由任务间主题差别驱动，bootstrap稳定
也不能证明共享记忆机制；主题top词、轨迹内变异和该诊断必须一起审查。
