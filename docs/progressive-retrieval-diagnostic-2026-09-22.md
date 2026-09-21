# 稠密检索修复可行性检查

本轮原生核心adapter使用全量100195文档SQLite BM25，明确不同于作者默认的
OpenAISearcher；开发失败不能单独归于Flash能力。

只读核查发现作者公开索引在joanna690/websearch-embeddings（本地保存tree和
revision于.tmp/progressive_search/native_embedding_tree.json），四个FAISS分片
合计约616MB，有id_map。构建脚本硬编码text-embedding-3-small，搜索器默认却是
text-embedding-ada-002：仅维数相同不保证编码空间匹配，不能拿默认名直接使用。

对已授权的同一autodl endpoint做一次模型目录查询（39个advertised模型，未列
embedding模型），及一次text-embedding-3-small通用文本调用，返回404
NotFoundError，未恢复重试。请求与脱敏结果保存在embedding_capability.json及
embedding_probe.json。没有向其它供应商发送此密钥，没有猜测索引编码匹配，
没有换主生成模型。该检查不是新的任务实验，也没有改变正在跑的冻结BM25组。

后续若统一稠密后端，应先验证索引/编码模型一致，再单独重做开发资格化；
不能把已发生的BM25失败删掉，或把稠密结果与BM25方法行直接拼成结构效应。
