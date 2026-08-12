"""Workspace-scoped application tools registered for the minimal agent."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
WORKSPACES_ROOT = ROOT / "workspaces"
ToolHandler = Callable[..., Any]


def echo(text: str) -> dict[str, str]:
    return {"text": text}


class WorkspaceTools:
    """File and Python tools restricted to one child of WORKSPACES_ROOT."""

    def __init__(self, workspace: Path):
        self.workspace = workspace.resolve()
        try:
            self.workspace.relative_to(WORKSPACES_ROOT.resolve())
        except ValueError as error:
            raise ValueError(f"workspace must stay under {WORKSPACES_ROOT}") from error
        self.workspace.mkdir(parents=True, exist_ok=True)

    def _path(self, raw: str, *, must_exist: bool = False) -> Path:
        path = (self.workspace / raw).resolve()
        try:
            path.relative_to(self.workspace)
        except ValueError as error:
            raise ValueError(f"path escapes workspace: {raw}") from error
        if must_exist and not path.exists():
            raise FileNotFoundError(f"path does not exist: {raw}")
        return path

    def list_files(self, path: str = ".") -> dict[str, Any]:
        target = self._path(path, must_exist=True)
        if not target.is_dir():
            raise ValueError(f"not a directory: {path}")
        rows = []
        for item in sorted(target.rglob("*")):
            if len(rows) >= 500:
                return {"files": rows, "truncated": True}
            relative = item.relative_to(self.workspace).as_posix()
            rows.append(relative + ("/" if item.is_dir() else ""))
        return {"files": rows, "truncated": False}

    def read_text_file(self, path: str) -> dict[str, Any]:
        target = self._path(path, must_exist=True)
        if not target.is_file():
            raise ValueError(f"not a file: {path}")
        content = target.read_text(encoding="utf-8")
        if len(content) > 120_000:
            return {"path": path, "content": content[:120_000], "truncated": True}
        return {"path": path, "content": content, "truncated": False}

    def write_text_file(self, path: str, content: str) -> dict[str, Any]:
        if len(content) > 200_000:
            raise ValueError("content exceeds 200000 characters")
        target = self._path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {"path": target.relative_to(self.workspace).as_posix(), "characters": len(content)}

    def run_python(self, arguments: list[str], timeout_s: int = 30) -> dict[str, Any]:
        if not arguments:
            raise ValueError("arguments must not be empty")
        if arguments[0] == "-m":
            if len(arguments) < 2 or arguments[1] != "unittest":
                raise ValueError("only python -m unittest is allowed")
            command_args = arguments
        else:
            script = self._path(arguments[0], must_exist=True)
            if not script.is_file() or script.suffix.lower() != ".py":
                raise ValueError("the first argument must be a workspace Python file")
            command_args = [str(script), *arguments[1:]]
        timeout = max(1, min(int(timeout_s), 60))
        try:
            completed = subprocess.run(
                [sys.executable, *command_args],
                cwd=self.workspace,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as error:
            return {"returncode": None, "stdout": "", "stderr": "", "error": f"timed out after {error.timeout}s"}
        return {
            "returncode": completed.returncode,
            "stdout": completed.stdout[:30_000],
            "stderr": completed.stderr[:30_000],
            "truncated": len(completed.stdout) > 30_000 or len(completed.stderr) > 30_000,
        }

    def handlers(self) -> dict[str, ToolHandler]:
        return {
            "echo": echo,
            "list_files": self.list_files,
            "read_text_file": self.read_text_file,
            "write_text_file": self.write_text_file,
            "run_python": self.run_python,
        }


class ToolRegistry:
    """Dispatch model calls to explicitly registered, workspace-scoped handlers."""

    def __init__(
        self,
        handlers: Mapping[str, ToolHandler] | None = None,
        *,
        workspace: Path | None = None,
    ):
        if handlers is not None:
            self.handlers = dict(handlers)
        else:
            selected = workspace or (WORKSPACES_ROOT / "default")
            self.handlers = WorkspaceTools(selected).handlers()

    def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        handler = self.handlers.get(name)
        if handler is None:
            return {"ok": False, "error": f"unknown tool: {name}"}
        try:
            result = handler(**arguments)
        except Exception as error:
            return {"ok": False, "error": str(error)}
        return {"ok": True, "result": result}

