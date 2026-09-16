# aiaaa 备用中转检查（2026-09-14）

> **2026-09-15 更新：** 当前默认开发路由已切换 aiaaa / deepseek-v4-flash-0731，正确关闭 memory 推理需要 `reasoning_effort=none`。
> 当前生成接口返回 403 `INSUFFICIENT_BALANCE`，实验已停止；下文保留早期探针，不代表此刻可用。
> 参见 [最新进展](yujia-progress-2026-09-15.md)。

用户授权 TokenRhythm 和 aiaaa 两个中转均可使用。aiaaa 认证与 4 次生成检查通过，
当前完整实验继续使用 TokenRhythm；一个运行内不自动切换到不同中转/模型。

配置：`https://aiaaa.cc/v1`，chat 路径 `/chat/completions`。
`/v1/models` 返回四个模型：`deepseek-v4-flash-0731`、`deepseek-v4-pro-0813`、
`deepseek-v4-flash-vision-exp`、`deepseek-v4.1-flash`。
本次选择并实际返回 **deepseek-v4-flash-0731**；它与 TokenRhythm 的 `deepseek-flash`
为不同请求别名，未验证后端等价。

| 检查 | 结果 | 单次完整耗时 |
|---|---|---:|
| 固定 JSON，禁用 thinking | 值正确、流式 usage 正常 | 2.32 秒 |
| 结构化行程，默认 thinking | 值正确、含 reasoning usage | 4.97 秒 |
| SDK 工具调用 | 正确调用 lookup_city | 2.69 秒 |
| 工具结果回传 + JSON 答案 | 正确 city/country | 1.67 秒 |

零重试、单并发；每个生成场景仅一个样本，不构成稳定速度排名。总计输入 **824**、
输出 **539** tokens。尚未取得公开价格或后台账单，不能套用 TokenRhythm 单价，费用待核对。
公开首页跳转登录页；未登录账户，也未使用管理接口。已向用户询问计价信息。

凭据保存为 Git 忽略、0600 权限的 `.tmp/aiaaa.env`。需要独立测试/运行时：

```bash
python3 code/run_with_local_deepseek.py --key-file .tmp/aiaaa.env -- <命令>
```

若用于完整比较，需指定新的 result family，例如 `--family p2_recent_baselines_aiaaa_v1`；
模型/路由将记录在 protocol。当前 TokenRhythm 结果不能与此路由的部分结果拼表。

- [认证和模型列表](../results/development/aiaaa_models_probe_2026_09_14.json)
- [四次生成与用量](../results/development/aiaaa_latency_2026_09_14.json)

2026-09-14 补充：未附带凭据读取 `/api/pricing` 与 `/api/status`，两者均 404，仍不能核实单价；此检查没有生成调用。记录见 `results/development/aiaaa_public_pricing_probe_2026_09_14.json`。
