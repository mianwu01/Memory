# 授权替代的证据隔离修复（新增reader调用前）

原native授权重取condition把实际工具trace和writer的predicted answer一起写入，
这是原生格式，但其中的模型推断不是外部授权事实。已完成的五例中，case6的
writer明确写道检索未证实，仍猜NYU；三次reader又沿用了NYU，官方为Amherst。
0为UNKNOWN/一次截断；1/2/9各3/3正确，并有真实返回文档中的答案字面支持。
原有结果全部保留，不把“调用过授权工具”当作“输出受证据支持”。

对全部原适用五例，新增authorized_evidence_only三次独立读取：仅将原先已经
完成的native工具返回写入记忆，排除所有assistant输出、predicted answer、
推理及搜索query本身；不再检索，不添加gold，不挑文档，不修改工具原文。
原final question、READER、Flash thinking、32768上限、评分保持一致。
记录正确、严格UNKNOWN及UNKNOWN开头诊断、截断和来源支持。

这是在观察到具体污染后追加的通用执行修复，属于开发阶段诊断，不是预注册
主贡献。若它有效，作用来自隔离模型猜测与外部事实；不得归于发现边。若无效
或证据不足，也照实记录，不继续挑案例、改名字或把真实来源标签当安全证明。
