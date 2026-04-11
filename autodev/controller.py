from __future__ import annotations

import json
import urllib.request

from autodev.config_loader import render_prompt
from autodev.models import ControllerDecision


class OpenAIController:
    def __init__(self, *, model: str, api_key: str, review_prompt_template: str):
        self.model = model
        self.api_key = api_key
        self.review_prompt_template = review_prompt_template

    def decide(self, *, config, state, last_codex_result, known_blockers: str):
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required")

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
        with urllib.request.urlopen(request) as response:
            body = json.loads(response.read().decode("utf-8"))

        text = self._extract_text(body)
        data = self._parse_decision_json(text)
        return ControllerDecision(**data)

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
