#!/usr/bin/env python3
"""Command-line entry for the reusable minimal tool-calling agent."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agent_runtime import AgentError, load_config, load_function_tools, run_agent
from tools import ToolRegistry


ROOT = Path(__file__).resolve().parent
WORKSPACES_ROOT = ROOT / "workspaces"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a minimal Responses API agent with local function tools.")
    parser.add_argument("prompt", nargs="*", help="User request")
    parser.add_argument("--config", type=Path, help="JSON config; defaults to config.local.json")
    parser.add_argument("--system-prompt", type=Path, help="Override prompts/system_prompt.md")
    parser.add_argument("--tools", type=Path, help="Override contracts/tools.json")
    parser.add_argument(
        "--workspace",
        default="default",
        help="Isolated workspace name under minimal_ai_agent/workspaces",
    )
    parser.add_argument("--show-config", action="store_true", help="Print sanitized settings and exit")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        config = load_config(args.config)
        if args.show_config:
            print(json.dumps(config.public_dict(), indent=2, ensure_ascii=False))
            return 0

        prompt = " ".join(args.prompt).strip()
        if not prompt:
            raise AgentError("Provide a prompt, or use --show-config")
        system_prompt = None
        if args.system_prompt:
            system_prompt = args.system_prompt.resolve().read_text(encoding="utf-8")
        function_tools = load_function_tools(args.tools.resolve()) if args.tools else None
        workspace = (WORKSPACES_ROOT / args.workspace).resolve()
        try:
            workspace.relative_to(WORKSPACES_ROOT.resolve())
        except ValueError as error:
            raise AgentError("Workspace must stay under minimal_ai_agent/workspaces") from error
        answer = run_agent(
            prompt,
            config,
            ToolRegistry(workspace=workspace),
            system_prompt=system_prompt,
            tools=function_tools,
            on_event=lambda message: print(f"[{message}]", file=sys.stderr),
        )
        print(answer)
        return 0
    except (AgentError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
