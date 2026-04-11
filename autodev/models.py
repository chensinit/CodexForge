from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class LoopConfig:
    workspace: Path
    state_path: Path
    session_dir: Path
    requirement_doc_path: Path
    max_turns_per_session: int
    max_total_turns: int
    codex_command: list[str]
    openai_model: str
    openai_api_key: str
    requirement: str
    short_requirement: str
    session_bootstrap_prompt: str
    initial_planning_prompt: str
    session_wrapup_prompt: str
    step_review_prompt: str


@dataclass
class CodexResult:
    stdout: str
    stderr: str
    exit_code: int


@dataclass
class ControllerDecision:
    status: str
    next_instruction: str
    reason: str
    focus: str
    progress_update: str


@dataclass
class SessionState:
    session_id: int
    session_turn: int
    total_turns: int
    status: str
    current_progress_path: Path
    plan_initialized: bool = False
    plan_summary: str = ""
    progress_summary: str = ""
    last_codex_summary: str = ""
    last_codex_stdout: str = ""
    last_codex_stderr: str = ""
    last_codex_exit_code: int | None = None

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(self)
        payload["current_progress_path"] = str(self.current_progress_path)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "SessionState":
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["current_progress_path"] = Path(payload["current_progress_path"])
        return cls(**payload)

    @classmethod
    def initial(cls, *, session_id: int, progress_path: Path) -> "SessionState":
        return cls(
            session_id=session_id,
            session_turn=0,
            total_turns=0,
            status="running",
            current_progress_path=progress_path,
        )
