from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from autodev.config_loader import render_prompt
from autodev.models import ControllerDecision


class OpenAIController:
    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
    MAX_ATTEMPTS = 3
    RETRY_DELAY_SECONDS = 1.0

    def __init__(self, *, model: str, api_key: str, review_prompt_template: str):
        self.model = model
        self.api_key = api_key
        self.review_prompt_template = review_prompt_template

    def decide(self, *, config, state, last_codex_result, known_blockers: str):
        if not self.api_key:
            raise RuntimeError("OpenAI API key is required in config/common.json under openai.api_key")

        # Fast path for explicit completion token
        if last_codex_result and last_codex_result.stdout and "[[DONE]]" in last_codex_result.stdout:
            return ControllerDecision(
                status="complete",
                next_instruction="",
                reason="Codex explicitly requested completion via [[DONE]] token.",
                focus="completed",
                progress_update=state.progress_summary,
            )

        system_prompt = (
            "Return strict JSON only. "
            "Use keys: status, next_instruction, reason, focus, progress_update. "
            "Allowed status values: continue, complete."
        )
        user_prompt = render_prompt(
            self.review_prompt_template,
            {
                "requirement": config.requirement,
                "short_requirement": config.short_requirement,
                "workspace_path": config.workspace,
                "plan_summary": state.plan_summary or "No plan summary yet.",
                "progress_summary": state.progress_summary or "No progress yet.",
                "last_codex_response": (
                    "None yet."
                    if last_codex_result is None
                    else last_codex_result.stdout or "No stdout."
                ),
                "last_execution_result": (
                    "None yet."
                    if last_codex_result is None
                    else f"exit_code={last_codex_result.exit_code}, stderr={last_codex_result.stderr or 'none'}"
                ),
                "known_blockers": known_blockers or "none",
            },
        )
        payload = {
            "model": self.model,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
                {"role": "user", "content": [{"type": "input_text", "text": user_prompt}]},
            ],
        }
        request = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        body = self._request_with_retry(request)

        text = self._extract_text(body)
        data = self._parse_decision_json(text)
        return ControllerDecision(**data)

    def _request_with_retry(self, request: urllib.request.Request) -> dict:
        last_error_message = "no response body"
        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                detail = self._read_error_detail(exc)
                if exc.code == 401:
                    raise RuntimeError(
                        "OpenAI API authentication failed (401 Unauthorized). "
                        "Check config/common.json openai.api_key."
                    ) from exc
                last_error_message = f"HTTP {exc.code}: {detail}"
                if not self._should_retry_http_error(exc.code) or attempt == self.MAX_ATTEMPTS:
                    raise RuntimeError(
                        f"OpenAI API request failed after {attempt} attempt(s): {last_error_message}"
                    ) from exc
            except urllib.error.URLError as exc:
                reason = getattr(exc, "reason", None) or str(exc) or "unknown network error"
                last_error_message = f"network error: {reason}"
                if attempt == self.MAX_ATTEMPTS:
                    raise RuntimeError(
                        f"OpenAI API request failed after {attempt} attempt(s): {last_error_message}"
                    ) from exc

            time.sleep(self.RETRY_DELAY_SECONDS * attempt)

        raise RuntimeError(
            f"OpenAI API request failed after {self.MAX_ATTEMPTS} attempt(s): {last_error_message}"
        )

    def _extract_text(self, body: dict) -> str:
        if body.get("output_text"):
            return body["output_text"]
        output = body.get("output", [])
        for item in output:
            for content in item.get("content", []):
                text = content.get("text")
                if text:
                    return text
        raise RuntimeError("No text output returned from OpenAI response")

    def _parse_decision_json(self, text: str) -> dict:
        candidate = text.strip()
        if candidate.startswith("```"):
            candidate = self._strip_code_fence(candidate)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise RuntimeError("OpenAI response did not contain a JSON object")

        return json.loads(candidate[start : end + 1])

    def _strip_code_fence(self, text: str) -> str:
        lines = text.splitlines()
        if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].startswith("```"):
            return "\n".join(lines[1:-1]).strip()
        return text

    def _should_retry_http_error(self, status_code: int) -> bool:
        return status_code in self.RETRYABLE_STATUS_CODES

    def _read_error_detail(self, exc: urllib.error.HTTPError) -> str:
        try:
            body = exc.read().decode("utf-8").strip()
        except Exception:
            body = ""
        return body or exc.reason or "no response body"
