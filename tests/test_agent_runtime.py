from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent_runtime import AgentConfig, AgentError, load_function_tools, responses_url, run_agent  # noqa: E402
from tools import ToolRegistry, WORKSPACES_ROOT, WorkspaceTools  # noqa: E402


class FakeTransport:
    def __init__(self) -> None:
        self.requests: list[dict] = []

    def create(self, payload: dict) -> dict:
        self.requests.append(payload)
        if len(self.requests) == 1:
            return {
                "output": [
                    {"type": "reasoning", "id": "rs_1", "summary": []},
                    {
                        "type": "function_call",
                        "id": "fc_1",
                        "call_id": "call_1",
                        "name": "echo",
                        "arguments": json.dumps({"text": "hello"}),
                    },
                ]
            }
        return {
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "done"}],
                }
            ]
        }


class MinimalAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = AgentConfig(
            base_url="https://example.test/v1",
            api_key="secret",
            model="test-model",
            max_tool_rounds=3,
        )

    def test_responses_url_variants(self) -> None:
        self.assertEqual("https://api.openai.com/v1/responses", responses_url("https://api.openai.com"))
        self.assertEqual("https://host/v1/responses", responses_url("https://host/v1"))
        self.assertEqual("https://host/v1/responses", responses_url("https://host/v1/responses"))

    def test_loads_example_tool_contract(self) -> None:
        tools = load_function_tools()
        self.assertEqual(
            ["echo", "list_files", "read_text_file", "write_text_file", "run_python"],
            [tool["name"] for tool in tools],
        )
        self.assertEqual("function", tools[0]["type"])

    def test_registry_dispatches_and_rejects_unknown_tools(self) -> None:
        registry = ToolRegistry({"add": lambda left, right: left + right})
        self.assertEqual({"ok": True, "result": 5}, registry.execute("add", {"left": 2, "right": 3}))
        self.assertFalse(registry.execute("missing", {})["ok"])

    def test_function_call_loop_returns_output_to_the_model(self) -> None:
        transport = FakeTransport()
        answer = run_agent(
            "repeat hello",
            self.config,
            ToolRegistry(),
            transport=transport,
            system_prompt="test prompt",
        )
        self.assertEqual("done", answer)
        second_input = transport.requests[1]["input"]
        self.assertIn("reasoning", {item.get("type") for item in second_input})
        outputs = [item for item in second_input if item.get("type") == "function_call_output"]
        self.assertEqual("call_1", outputs[0]["call_id"])
        self.assertEqual({"ok": True, "result": {"text": "hello"}}, json.loads(outputs[0]["output"]))

    def test_round_limit_is_enforced(self) -> None:
        class EndlessTransport:
            def create(self, payload: dict) -> dict:
                return {
                    "output": [
                        {
                            "type": "function_call",
                            "call_id": "again",
                            "name": "echo",
                            "arguments": "{}",
                        }
                    ]
                }

        config = AgentConfig("https://example.test", "", "test", max_tool_rounds=1)
        with self.assertRaisesRegex(AgentError, "max_tool_rounds=1"):
            run_agent("loop", config, ToolRegistry(), transport=EndlessTransport(), system_prompt="test")

    def test_workspace_tools_write_read_and_run_python(self) -> None:
        WORKSPACES_ROOT.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=WORKSPACES_ROOT) as temp_dir:
            tools = WorkspaceTools(Path(temp_dir))
            tools.write_text_file("hello.py", "print('hello')\n")
            self.assertEqual("print('hello')\n", tools.read_text_file("hello.py")["content"])
            result = tools.run_python(["hello.py"])
            self.assertEqual(0, result["returncode"])
            self.assertEqual("hello", result["stdout"].strip())

    def test_workspace_tools_reject_escape(self) -> None:
        WORKSPACES_ROOT.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=WORKSPACES_ROOT) as temp_dir:
            tools = WorkspaceTools(Path(temp_dir))
            with self.assertRaisesRegex(ValueError, "escapes workspace"):
                tools.write_text_file("../outside.txt", "no")


if __name__ == "__main__":
    unittest.main()
