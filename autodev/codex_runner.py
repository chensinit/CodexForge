from __future__ import annotations

import json
import selectors
import subprocess

from autodev.models import CodexResult


class CodexRunner:
    def __init__(self, command: list[str], event_logger=None):
        self.command = self._ensure_json_mode(command)
        self.event_logger = event_logger

    def run(self, prompt: str, cwd):
        process = subprocess.Popen(
            [*self.command, prompt],
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        stdout_lines: list[str] = []
        stderr_lines: list[str] = []
        final_messages: list[str] = []
        selector = selectors.DefaultSelector()
        assert process.stdout is not None
        assert process.stderr is not None
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")

        while selector.get_map():
            for key, _ in selector.select():
                line = key.fileobj.readline()
                if line == "":
                    selector.unregister(key.fileobj)
                    continue
                if key.data == "stdout":
                    stdout_lines.append(line)
                    self._handle_stdout_line(line, final_messages)
                else:
                    stderr_lines.append(line)
                    self._emit("codex_stderr", {"line": line.rstrip("\n")})

        exit_code = process.wait()
        return CodexResult(
            stdout="\n".join(message for message in final_messages if message).strip()
            or "".join(stdout_lines),
            stderr="".join(stderr_lines),
            exit_code=exit_code,
        )

    def _handle_stdout_line(self, line: str, final_messages: list[str]) -> None:
        stripped = line.rstrip("\n")
        self._emit("codex_jsonl", {"line": stripped})
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            return

        if payload.get("type") == "item.completed":
            item = payload.get("item", {})
            if item.get("type") == "agent_message" and item.get("text"):
                final_messages.append(item["text"])

    def _emit(self, event_type: str, payload: dict) -> None:
        if self.event_logger is None:
            return
        self.event_logger(event_type, payload)

    def _ensure_json_mode(self, command: list[str]) -> list[str]:
        if "--json" in command:
            return command
        return [*command, "--json"]
