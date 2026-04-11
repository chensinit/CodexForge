from __future__ import annotations

import json
from pathlib import Path

from autodev.models import LoopConfig


def load_loop_config(
    *,
    common_config_path: Path,
    task_config_path: Path,
    prompt_dir: Path,
) -> LoopConfig:
    common = json.loads(common_config_path.read_text(encoding="utf-8"))
    task = json.loads(task_config_path.read_text(encoding="utf-8"))
    workspace = Path(task["workspace_path"]).expanduser().resolve()
    state_dir = workspace / ".autodev"
    return LoopConfig(
        workspace=workspace,
        state_path=state_dir / "state.json",
        session_dir=state_dir / "sessions",
        requirement_doc_path=workspace / "AUTODEV_REQUIREMENT.md",
        max_turns_per_session=common["loop"]["max_turns_per_session"],
        max_total_turns=common["loop"]["max_total_turns"],
        codex_command=common["codex"]["command"],
        openai_model=common["openai"]["model"],
        openai_api_key=common["openai"]["api_key"],
        requirement=task["requirement"],
        short_requirement=task["short_requirement"],
        session_bootstrap_prompt=(prompt_dir / "session_bootstrap_prompt.md").read_text(
            encoding="utf-8"
        ),
        initial_planning_prompt=(prompt_dir / "initial_planning_prompt.md").read_text(
            encoding="utf-8"
        ),
        session_wrapup_prompt=(prompt_dir / "session_wrapup_prompt.md").read_text(
            encoding="utf-8"
        ),
        step_review_prompt=(prompt_dir / "step_review_prompt.md").read_text(
            encoding="utf-8"
        ),
    )


def render_prompt(template: str, values: dict[str, object]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace(f"{{{key}}}", str(value))
    return rendered
