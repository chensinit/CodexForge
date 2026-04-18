from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from autodev.models import CodexResult


class QwenRunner:
    MAX_ATTEMPTS_PER_MODEL = 2
    INITIAL_DELAY = 10.0

    def __init__(self, api_key: str, models: list[str], base_url: str, event_logger=None):
        self.api_key = api_key
        self.models = models
        self.base_url = base_url.rstrip("/")
        self.event_logger = event_logger

    def run(self, prompt: str, cwd: Path | str) -> CodexResult:
        if not self.api_key:
            return CodexResult(
                stdout="",
                stderr="Qwen API key is missing. Please add it to config/common.json",
                exit_code=1
            )

        last_error = "No models configured"
        
        # Outer loop: Iterate through models (Plus -> Next -> Flash)
        for model in self.models:
            self._emit("phase", {"name": "qwen_fallback", "message": f"Trying Qwen model: {model}"})
            
            system_prompt = (
                f"You are a coding assistant acting as a fallback for Codex CLI.\n"
                f"Current working directory: {cwd}\n"
                f"Task: {prompt}\n\n"
                f"IMPORTANT: If you need to create or modify files, output them as follows:\n"
                f"FILE: path/to/file\n"
                f"```\ncontent\n```\n"
            )

            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1
            }
            
            url = f"{self.base_url}/chat/completions"
            
            # Inner loop: Retry on transient errors for the current model
            for attempt in range(1, self.MAX_ATTEMPTS_PER_MODEL + 1):
                try:
                    req = urllib.request.Request(
                        url,
                        data=json.dumps(payload).encode("utf-8"),
                        headers={
                            "Content-Type": "application/json",
                            "Authorization": f"Bearer {self.api_key}"
                        },
                        method="POST"
                    )
                    
                    with urllib.request.urlopen(req, timeout=90) as response:
                        body = json.loads(response.read().decode("utf-8"))
                        
                    text = self._extract_text(body)
                    self._apply_file_changes(text, Path(cwd))
                    
                    self._emit("info", {"message": f"Successfully finished task using {model}"})
                    return CodexResult(
                        stdout=f"[Qwen Fallback Result - {model}]\n{text}",
                        stderr="",
                        exit_code=0
                    )
                    
                except urllib.error.HTTPError as e:
                    # If it's a 404 (model not found) or 401 (auth), don't retry, just move to next model
                    if e.code in {404, 401}:
                        last_error = f"HTTP {e.code} for {model}: {e.reason}"
                        self._emit("error", {"message": f"Model {model} failed with {e.code}. Moving to next model."})
                        break
                        
                    if e.code in {429, 500, 502, 503, 504}:
                        delay = self.INITIAL_DELAY * (2 ** (attempt - 1))
                        reason = "Rate Limit" if e.code == 429 else f"Server Error {e.code}"
                        self._emit("info", {"message": f"Qwen {model} {reason}. Retrying in {delay}s... ({attempt}/{self.MAX_ATTEMPTS_PER_MODEL})"})
                        time.sleep(delay)
                        last_error = f"HTTP {e.code}: {e.reason}"
                        continue
                    else:
                        last_error = f"HTTP {e.code}: {e.reason}"
                        break
                except Exception as e:
                    last_error = f"Error with {model}: {str(e)}"
                    self._emit("error", {"message": last_error})
                    break
        
        error_msg = f"Qwen fallback failed for all models. Last error: {last_error}"
        self._emit("error", {"message": error_msg})
        return CodexResult(
            stdout="",
            stderr=error_msg,
            exit_code=1
        )

    def _extract_text(self, body: dict) -> str:
        try:
            return body["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
            return "No response from Qwen."

    def _apply_file_changes(self, text: str, cwd: Path) -> None:
        pattern = r"FILE:\s*([^\n]+)\n+```[a-zA-Z]*\n(.*?)\n```"
        matches = re.finditer(pattern, text, re.DOTALL)
        
        modified_count = 0
        for match in matches:
            rel_path = match.group(1).strip()
            content = match.group(2)
            abs_path = (cwd / rel_path).resolve()
            
            try:
                abs_path.parent.mkdir(parents=True, exist_ok=True)
                abs_path.write_text(content, encoding="utf-8")
                self._emit("file_modified", {"path": str(rel_path)})
                modified_count += 1
            except Exception as e:
                self._emit("error", {"message": f"Failed to write to {rel_path}: {e}"})
        
        if modified_count > 0:
            self._emit("info", {"message": f"Qwen modified {modified_count} file(s)"})

    def _emit(self, event_type: str, payload: dict) -> None:
        if self.event_logger:
            self.event_logger(event_type, payload)
