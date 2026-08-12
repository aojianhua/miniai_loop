# Minimal AI Agent

这是一个最小、可独立复制的 Responses API 工具调用循环，只使用 Python 标准库。

## 完整链路

```text
用户请求
  -> agent.cmd / agent.py
  -> agent_runtime.py
  -> POST {base_url}/v1/responses
  -> 模型返回 function_call
  -> tools.py 执行已注册函数
  -> function_call_output 回传模型
  -> 模型返回最终文本
```

目录职责：

- `agent.py`：命令行入口、参数和配置选择。
- `agent_runtime.py`：上游 HTTP 请求、Responses 多轮循环、函数结果回传、错误与轮数限制。
- `tools.py`：工作区文件读写、Python 执行及函数注册；所有文件路径限制在 `workspaces/<名称>/`。
- `contracts/tools.json`：模型可见的函数名称、说明和 JSON Schema。
- `prompts/system_prompt.md`：独立系统提示词。
- `config.example.json`：无密钥的配置模板。
- `tests/test_agent_runtime.py`：不联网验证完整函数调用闭环。

## 运行

上游连接、共享限额 key、模型和推理强度固定在 `fixed_upstream.py` 中，无需创建配置文件。直接运行：

```powershell
.\agent.cmd --workspace demo "创建并测试一个 Python 小工具"
```

`config.local.json` 只用于覆盖超时、最大工具轮数和最大输出 token。`--show-config` 只显示脱敏后的生效配置，不输出 API key。

## 增加工具

每个新工具需要两处匹配的改动：

1. 在 `tools.py` 中实现处理函数，并加入 `WorkspaceTools.handlers()`。
2. 在 `contracts/tools.json` 中加入同名函数及参数 JSON Schema。

例如，处理函数名和 Schema 的 `name` 都是 `query_database`。运行时只分发显式注册的函数，未知函数会作为失败结果回传给模型。业务需要文件、网络、数据库或子进程权限时，应在具体处理函数中单独做参数校验、超时和访问边界，避免把这些权限放进通用循环。

## 验证

```powershell
python -m compileall -q .
python -m unittest discover -s tests -v
python agent.py --show-config
```

单元测试使用假 transport，不会发送真实 API 请求。真正的联网烟雾测试需要有效的上游配置，可能产生 API 费用，因此不由离线测试自动执行。
