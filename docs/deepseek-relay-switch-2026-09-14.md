# DeepSeek 中转切换与延迟检查（2026-09-14）

> 历史 bboluo 记录：当前已切换按量 TokenRhythm，本页未来报价/路由不再适用。
> 旧已花 230 保留；最新见 [TokenRhythm 测试与预算](tokenrhythm-switch-2026-09-14.md)。

新运行使用 `https://bboluo.com/v1`，模型保持 `deepseek-v4-flash`。新凭据只保存在
Git 忽略、权限为 `0600` 的 `deepseek_apikey.md`；历史冻结 protocol/result 不修改。

统一启动入口：

```bash
python3 code/run_with_local_deepseek.py -- python3 <实验脚本> <参数>
```

Wrapper 支持当前中转凭据格式，并同时覆盖 `OPENAI_API_KEY`、`DEEPSEEK_API_KEY`、
`OPENAI_BASE_URL`、`OPENAI_API_BASE`、`DEEPSEEK_BASE_URL`，避免旧环境变量使凭据和路由
错配。MemoryArena 的上游配置用 `setdefault` 读取路由，故 wrapper 设置优先；AgentPoison
和四任务 runner 的默认地址已更新，MINJA 的默认回退地址也已更新。更换路由后使用新
结果目录，不能把新调用追加到旧冻结实验中。

## 本次检查

新中转 `/models` 返回 HTTP 200，列出 `deepseek-v4-flash`、`deepseek-v4-pro`、
`deepseek-v4.1-flash`。本次所有生成请求均请求并返回 `deepseek-v4-flash`。

| 检查 | 成功 | 首个答案内容中位数 | 总耗时中位数 |
|---|---:|---:|---:|
| 固定 JSON 输出，关闭 thinking | 3/3 | 2.44 秒 | 2.75 秒 |
| 结构化行程更新，默认 thinking | 3/3 | 3.39 秒 | 3.47 秒 |
| SDK 非流式工具调用 | 1/1 | 未测 | 2.72 秒（单次） |

默认 thinking 组首个推理或答案 token 的中位数为 2.30 秒。六条流式请求全部得到预期
JSON 值；工具调用正确返回 `lookup_city(city="Shanghai")`。均为单并发、零重试。

旧直连的同时间探针返回 HTTP 402，因此没有完成实时两路对照。用于该探针的旧凭据
临时副本已经删除；未把旧凭据发送给中转。

## 历史相同请求对照

在新调用前固定选择 dev v9 的每任务第一个 development episode、oracle/full 两臂，共
8 条请求。重建 prompt hash 与 2026-08-31 记录逐条一致，模型、temperature、max_tokens、
response_format 和 seed 保持一致。新请求通过 SDK 非流式接口执行，零重试；8/8 输出
满足语义合同，完整 post-state 也全部正确。

| 指标 | 历史直连 | 当前中转 |
|---|---:|---:|
| 总耗时中位数 | 7.43 秒 | 5.98 秒 |
| 八条累计 API 耗时 | 65.11 秒 | 52.88 秒 |
| input tokens | 17,275 | 16,691 |
| output tokens（含推理） | 6,818 | 9,330 |

8 条中 6 条更快，2 条更慢。中位数下降约 19.5%，累计耗时下降约 18.8%。这支持本次
小样本下未观察到整体变慢，不能解释为中转必然加速：对照来自不同时段，服务负载、
缓存和输出长度不同；本次历史重放复用一个 SDK client，历史 runner 为每条请求创建
client，连接复用也可能影响差异。尚未测高并发、长上下文或完整多步 agent。

## 验证与原始记录

- 88 项离线 benchmark 测试通过；凭据格式、旧路由覆盖、显式 override、文件权限与
  Git 排除检查通过；MINJA 默认路由和 override 检查通过。
- 重建历史总体审计与保存版本一致。
- [流式与工具调用记录](../results/development/deepseek_relay_latency_2026_09_14.json)
- [历史相同 prompt 重放记录](../results/development/deepseek_relay_historical_probe_2026_09_14.json)

本次为 API 连通性、接口兼容性和延迟检查，不属于新的 confirmatory benchmark run。
