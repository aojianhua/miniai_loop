"""Small OpenAI-compatible Responses API loop with function calling."""

from __future__ import annotations

import copy
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "config.local.json"
DEFAULT_PROMPT = ROOT / "prompts" / "system_prompt.md"
DEFAULT_TOOLS = ROOT / "contracts" / "tools.json"


class AgentError(RuntimeError):
    """Raised for configuration, transport, or orchestration failures."""


class ResponsesTransport(Protocol):
    def create(self, payload: dict[str, Any]) -> dict[str, Any]: ...


class ToolExecutor(Protocol):
    def execute(self, name: str, arguments: dict[str, Any]) -> Any: ...


@dataclass(frozen=True)
class AgentConfig:
    base_url: str
    api_key: str
    model: str
    timeout_s: float = 120.0
    max_tool_rounds: int = 12
    max_output_tokens: int = 4096
    reasoning_effort: str = "medium"

    def public_dict(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url,
            "api_key_configured": bool(self.api_key),
            "model": self.model,
            "timeout_s": self.timeout_s,
            "max_tool_rounds": self.max_tool_rounds,
            "max_output_tokens": self.max_output_tokens,
            "reasoning_effort": self.reasoning_effort,
        }


def load_config(path: Path | None = None) -> AgentConfig:
    config_path = (path or DEFAULT_CONFIG).resolve()
    raw: dict[str, Any] = {}
    if config_path.is_file():
        loaded = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise AgentError(f"LLM config must be a JSON object: {config_path}")
        raw = loaded
    elif path is not None:
        raise AgentError(f"LLM config does not exist: {config_path}")

    return AgentConfig(
        base_url=str(
            raw.get("base_url")
            or os.environ.get("AI_AGENT_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
            or "https://api.openai.com"
        ).rstrip("/"),
        api_key=str(
            raw.get("api_key")
            or os.environ.get("AI_AGENT_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or ""
        ),
        model=str(
            raw.get("model")
            or os.environ.get("AI_AGENT_MODEL")
            or os.environ.get("OPENAI_MODEL")
            or "gpt-5.6"
        ),
        timeout_s=float(raw.get("timeout_s", 120)),
        max_tool_rounds=int(raw.get("max_tool_rounds", 12)),
        max_output_tokens=int(raw.get("max_output_tokens", 4096)),
        reasoning_effort=str(raw.get("reasoning_effort", "medium")),
    )


def responses_url(base_url: str) -> str:
    base = base_url.strip().rstrip("/")
    if base.endswith("/responses"):
        return base
    if base.endswith("/v1") or base.endswith("/api/codex") or base.endswith("/backend-api/codex"):
        return base + "/responses"
    return base + "/v1/responses"


class HttpResponsesTransport:
    def __init__(self, config: AgentConfig):
        self.config = config

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "minimal-ai-agent/1.0",
        }
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        request = urllib.request.Request(
            responses_url(self.config.base_url),
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_s) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")[:2000]
            raise AgentError(f"Responses API HTTP {error.code}: {body}") from error
        except urllib.error.URLError as error:
            raise AgentError(f"Responses API connection failed: {error}") from error

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as error:
            raise AgentError(f"Responses API returned non-JSON data: {raw[:500]!r}") from error
        if not isinstance(parsed, dict):
            raise AgentError("Responses API returned a non-object response")
        if parsed.get("error"):
            raise AgentError(f"Responses API error: {parsed['error']}")
        return parsed


def load_function_tools(path: Path = DEFAULT_TOOLS) -> list[dict[str, Any]]:
    contract = json.loads(path.read_text(encoding="utf-8"))
    rows = contract.get("tools") if isinstance(contract, dict) else None
    if not isinstance(rows, list):
        raise AgentError(f"Invalid tool contract: {path}")

    tools: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise AgentError(f"Each tool contract must be an object: {path}")
        try:
            name = str(row["name"])
        except KeyError as error:
            raise AgentError(f"Tool contract has no name: {path}") from error
        tools.append(
            {
                "type": "function",
                "name": name,
                "description": str(row.get("description", "")),
                "parameters": copy.deepcopy(row.get("parameters", {"type": "object"})),
                "strict": bool(row.get("strict", False)),
            }
        )
    return tools


def extract_output_text(response: dict[str, Any]) -> str:
    direct = response.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    pieces: list[str] = []
    for item in response.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content") or []:
            if isinstance(content, dict) and content.get("type") in {"output_text", "text"}:
                text = content.get("text")
                if isinstance(text, str):
                    pieces.append(text)
    return "\n".join(pieces).strip()


def run_agent(
    user_prompt: str,
    config: AgentConfig,
    tool_executor: ToolExecutor,
    *,
    transport: ResponsesTransport | None = None,
    system_prompt: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    on_event: Callable[[str], None] | None = None,
) -> str:
    if not user_prompt.strip():
        raise AgentError("User prompt is empty")

    instructions = system_prompt if system_prompt is not None else DEFAULT_PROMPT.read_text(encoding="utf-8")
    function_tools = copy.deepcopy(tools) if tools is not None else load_function_tools()
    responses = transport or HttpResponsesTransport(config)
    input_items: list[dict[str, Any]] = [{"role": "user", "content": user_prompt.strip()}]

    for round_index in range(1, config.max_tool_rounds + 1):
        payload: dict[str, Any] = {
            "model": config.model,
            "instructions": instructions,
            "input": input_items,
            "tools": function_tools,
            "tool_choice": "auto",
            "parallel_tool_calls": False,
            "store": False,
            "max_output_tokens": config.max_output_tokens,
        }
        if config.reasoning_effort != "none":
            payload["reasoning"] = {"effort": config.reasoning_effort}
        if on_event:
            on_event(f"AI round {round_index}")

        response = responses.create(payload)
        output = response.get("output")
        if not isinstance(output, list):
            raise AgentError("Responses API response has no output array")

        # Reasoning models require their complete output items on the next turn.
        input_items.extend(copy.deepcopy(item) for item in output if isinstance(item, dict))
        calls = [item for item in output if isinstance(item, dict) and item.get("type") == "function_call"]
        if not calls:
            text = extract_output_text(response)
            if text:
                return text
            raise AgentError("Model returned neither function calls nor final text")

        for call in calls:
            name = str(call.get("name") or "")
            call_id = str(call.get("call_id") or "")
            if not call_id:
                raise AgentError(f"Function call has no call_id: {name}")
            try:
                arguments = json.loads(str(call.get("arguments") or "{}"))
            except json.JSONDecodeError as error:
                result: Any = {"ok": False, "error": f"invalid function arguments JSON: {error}"}
            else:
                if not isinstance(arguments, dict):
                    result = {"ok": False, "error": "function arguments must be a JSON object"}
                else:
                    if on_event:
                        on_event(f"tool {name}")
                    try:
                        result = tool_executor.execute(name, arguments)
                    except Exception as error:
                        result = {"ok": False, "error": str(error)}
            input_items.append(
                {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(result, ensure_ascii=False),
                }
            )

    raise AgentError(f"Agent exceeded max_tool_rounds={config.max_tool_rounds}")
