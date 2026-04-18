from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from autodev.models import CodexResult


class GeminiRunner:
    MAX_ATTEMPTS = 2  # Per model
    INITIAL_DELAY = 10.0

    def __init__(self, api_key: str, models: list[str], event_logger=None):
        self.api_key = api_key
        self.models = models if models else ["gemini-1.5-flash"]
        self.event_logger = event_logger

    def run(self, prompt: str, cwd: Path | str) -> CodexResult:
        if not self.api_key:
            return CodexResult(
                stdout="",
                stderr="Gemini API key is missing. Please add it to config/common.json",
                exit_code=1
            )

        last_error = "No models available"
        
        for model in self.models:
            model_lower = model.lower()
            if "flash-lite" in model_lower:
                nickname = "더욱 가벼운 흰 토끼 요정 (Flash Lite)"
            elif "flash" in model_lower:
                nickname = "흰 토끼 요정 (Flash)"
            else:
                nickname = "지혜로운 애벌레 (Pro)"
            
            self._emit("phase", {"name": "gemini_fallback", "message": f"Trying Gemini {model} ({nickname}) as fallback"})
            
            # System instructions
            full_prompt = (
                f"You are a 'Flash' (fast & light) or 'Pro' (deep & wise) coding assistant acting as a fallback for Codex CLI.\n"
                f"Model: {model} ({nickname})\n"
                f"Current working directory: {cwd}\n"
                f"Task: {prompt}\n\n"
                f"IMPORTANT: If you need to create or modify files, output them as follows:\n"
                f"FILE: path/to/file\n"
                f"```\ncontent\n```\n"
            )

            payload = {
                "contents": [{
                    "parts": [{"text": full_prompt}]
                }]
            }
            
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.api_key}"
            
            for attempt in range(1, self.MAX_ATTEMPTS + 1):
                try:
                    req = urllib.request.Request(
                        url,
                        data=json.dumps(payload).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST"
                    )
                    
                    with urllib.request.urlopen(req, timeout=60) as response:
                        body = json.loads(response.read().decode("utf-8"))
                        
                    text = self._extract_text(body)
                    self._apply_file_changes(text, Path(cwd))
                    
                    return CodexResult(
                        stdout=f"[Gemini Fallback Result - {model}]\n{text}",
                        stderr="",
                        exit_code=0
                    )
                    
                except urllib.error.HTTPError as e:
                    if e.code == 429:
                        last_error = f"HTTP 429: Resource Exhausted ({model})"
                        if attempt < self.MAX_ATTEMPTS:
                            self._emit("info", {"message": f"Gemini {model} quota hit. Waiting 20s for a single retry... ({attempt}/{self.MAX_ATTEMPTS})"})
                            time.sleep(20)
                            continue
                        else:
                            self._emit("info", {"message": f"Gemini {model} still exhausted after retry. Switching to next model."})
                            break # Switch to next model
                    
                    if e.code in {500, 502, 503, 504}:
                        delay = self.INITIAL_DELAY * (2 ** (attempt - 1))
                        self._emit("info", {"message": f"Gemini {model} Server Error {e.code}. Retrying in {delay}s... ({attempt}/{self.MAX_ATTEMPTS})"})
                        time.sleep(delay)
                        last_error = f"HTTP {e.code}: {e.reason} ({model})"
                        continue
                    else:
                        last_error = f"HTTP {e.code}: {e.reason} ({model})"
                        break # Switch to next model
                except Exception as e:
                    last_error = f"Error: {str(e)} ({model})"
                    break # Switch to next model
            
        error_msg = f"All Gemini models failed. Last error: {last_error}"
        self._emit("error", {"message": error_msg})
        return CodexResult(
            stdout="",
            stderr=error_msg,
            exit_code=1
        )

    def _extract_text(self, body: dict) -> str:
        try:
            return body["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            return "No response from Gemini."

    def _apply_file_changes(self, text: str, cwd: Path) -> None:
        # Simple parser for "FILE: path\n```content```"
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
            self._emit("info", {"message": f"Gemini modified {modified_count} file(s)"})

    def _emit(self, event_type: str, payload: dict) -> None:
        if self.event_logger:
            self.event_logger(event_type, payload)
