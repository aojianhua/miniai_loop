已根据 README 的约定补上运行时保护：现在模型可见的 contracts/tools.json 工具名必须和 ToolRegistry 显式注册的 handler 完全匹配，否则启动工具循环前会报清晰错误。
改动位置：
[agent_runtime.py (line 34)](E:/work/EDA-Assistant/miiai/miniai_loop/agent_runtime.py:34)：新增工具名提取与 contract/handler 匹配校验，并在 run_agent 中调用。
[tools.py (line 129)](E:/work/EDA-Assistant/miiai/miniai_loop/tools.py:129)：给 ToolRegistry 增加 tool_names()。
[test_agent_runtime.py (line 76)](E:/work/EDA-Assistant/miiai/miniai_loop/tests/test_agent_runtime.py:76)：补测试，覆盖默认 schema 与 handler 匹配，以及只改一边时失败。

验证已通过：
python -m compileall -q .
python -m unittest discover -s tests -v

test_default_tool_contract_matches_registered_handlers (test_agent_runtime.MinimalAgentTests.test_default_tool_contract_matches_registered_handlers) ... ok
test_function_call_loop_returns_output_to_the_model (test_agent_runtime.MinimalAgentTests.test_function_call_loop_returns_output_to_the_model) ... ok
test_function_tools_must_match_registered_handlers (test_agent_runtime.MinimalAgentTests.test_function_tools_must_match_registered_handlers) ... ok
test_loads_example_tool_contract (test_agent_runtime.MinimalAgentTests.test_loads_example_tool_contract) ... ok
test_registry_dispatches_and_rejects_unknown_tools (test_agent_runtime.MinimalAgentTests.test_registry_dispatches_and_rejects_unknown_tools) ... ok
test_responses_url_variants (test_agent_runtime.MinimalAgentTests.test_responses_url_variants) ... ok
test_round_limit_is_enforced (test_agent_runtime.MinimalAgentTests.test_round_limit_is_enforced) ... ok
test_workspace_tools_reject_escape (test_agent_runtime.MinimalAgentTests.test_workspace_tools_reject_escape) ... ok
test_workspace_tools_write_read_and_run_python (test_agent_runtime.MinimalAgentTests.test_workspace_tools_write_read_and_run_python) ... ok

----------------------------------------------------------------------
Ran 9 tests in 0.056s

OK