from __future__ import annotations

from pathlib import Path

from autodev.config_loader import render_prompt
from autodev.models import CodexResult, ControllerDecision, LoopConfig, SessionState


class AutoDevOrchestrator:
    def __init__(self, *, config: LoopConfig, codex_runner, controller, event_logger=None):
        self.config = config
        self.codex_runner = codex_runner
        self.controller = controller
        self.event_logger = event_logger

    def run_turn(self):
        state = self._load_or_create_state()
        self._ensure_requirement_doc()
        last_codex_result = self._last_codex_result_from_state(state)
        known_blockers = self._known_blockers(last_codex_result)

        if not state.plan_initialized:
            plan_prompt = render_prompt(
                self.config.initial_planning_prompt,
                {
                    "workspace_path": self.config.workspace,
                    "requirement": self.config.requirement,
                },
            )
            self._emit("phase", {"name": "planning", "message": "Creating initial plan"})
            codex_result = self._run_codex_with_retry(plan_prompt)
            self._emit_result("codex_plan", plan_prompt, codex_result)
            if self._is_fatal_environment_error(codex_result):
                return self._handle_fatal_codex_error(
                    state=state,
                    codex_result=codex_result,
                    reason="Codex could not start in the target workspace.",
                    focus="environment",
                    progress_update="No code implemented; Codex failed before planning due to a workspace environment error.",
                )
            state.plan_initialized = True
            state.plan_summary = self._summarize_codex_output(codex_result.stdout)
            state.last_codex_summary = state.plan_summary
            state.last_codex_stdout = codex_result.stdout
            state.last_codex_stderr = codex_result.stderr
            state.last_codex_exit_code = codex_result.exit_code
            state.save(self.config.state_path)
            return {
                "event": "planning_created",
                "state": state,
                "decision": ControllerDecision(
                    status="continue",
                    next_instruction="Create the initial development plan document.",
                    reason="The project needs a saved plan before iterative coding starts.",
                    focus="planning",
                    progress_update=state.progress_summary,
                ),
                "codex_result": codex_result,
            }

        if state.total_turns >= self.config.max_total_turns:
            wrap_prompt = self._render_wrapup_prompt(state)
            self._emit("phase", {"name": "wrap_up", "message": "Writing session wrap-up"})
            codex_result = self._run_codex_with_retry(wrap_prompt)
            self._emit_result("codex_wrap_up", wrap_prompt, codex_result)
            if self._is_fatal_environment_error(codex_result):
                return self._handle_fatal_codex_error(
                    state=state,
                    codex_result=codex_result,
                    reason="Codex could not write the session wrap-up due to a workspace environment error.",
                    focus="environment",
                    progress_update=state.progress_summary,
                )
            state.status = "stopped"
            state.last_codex_summary = self._summarize_codex_output(codex_result.stdout)
            state.last_codex_stdout = codex_result.stdout
            state.last_codex_stderr = codex_result.stderr
            state.last_codex_exit_code = codex_result.exit_code
            state.save(self.config.state_path)
            return {
                "event": "max_turns_reached",
                "state": state,
                "decision": ControllerDecision(
                    status="continue",
                    next_instruction="Write the session summary and stop.",
                    reason="The total turn limit was reached.",
                    focus="handoff",
                    progress_update=state.progress_summary,
                ),
                "codex_result": codex_result,
            }

        self._emit("phase", {"name": "review", "message": "Requesting next instruction from OpenAI"})
        decision = self.controller.decide(
            config=self.config,
            state=state,
            last_codex_result=last_codex_result,
            known_blockers=known_blockers,
        )
        self._emit(
            "llm_decision",
            {
                "status": decision.status,
                "reason": decision.reason,
                "focus": decision.focus,
                "progress_update": decision.progress_update,
                "next_instruction": decision.next_instruction,
            },
        )

        if decision.status == "complete":
            if decision.next_instruction.strip() and decision.next_instruction.strip().lower() not in {
                "none",
                "no more work",
                "nothing",
            }:
                self._emit(
                    "phase",
                    {"name": "finalize", "message": "Running final documentation step"},
                )
                codex_result = self._run_codex_with_retry(decision.next_instruction)
                self._emit_result("codex_finalize", decision.next_instruction, codex_result)
                if self._is_fatal_environment_error(codex_result):
                    return self._handle_fatal_codex_error(
                        state=state,
                        codex_result=codex_result,
                        reason="Codex could not complete the final documentation step due to a workspace environment error.",
                        focus="environment",
                        progress_update=decision.progress_update,
                    )
                state.last_codex_summary = self._summarize_codex_output(codex_result.stdout)
                state.last_codex_stdout = codex_result.stdout
                state.last_codex_stderr = codex_result.stderr
                state.last_codex_exit_code = codex_result.exit_code
            state.status = "completed"
            state.progress_summary = decision.progress_update
            state.save(self.config.state_path)
            return {"event": "completed", "state": state, "decision": decision}

        if self._should_wrap_before_execution(state):
            wrap_prompt = self._render_wrapup_prompt(state)
            self._emit("phase", {"name": "wrap_up", "message": "Session limit reached, asking Codex to summarize"})
            codex_result = self._run_codex_with_retry(wrap_prompt)
            self._emit_result("codex_wrap_up", wrap_prompt, codex_result)
            if self._is_fatal_environment_error(codex_result):
                return self._handle_fatal_codex_error(
                    state=state,
                    codex_result=codex_result,
                    reason="Codex could not finish the session wrap-up due to a workspace environment error.",
                    focus="environment",
                    progress_update=decision.progress_update,
                )
            next_state = SessionState.initial(
                session_id=state.session_id + 1,
                progress_path=self._progress_path_for_session(state.session_id + 1),
            )
            next_state.plan_initialized = True
            next_state.plan_summary = state.plan_summary
            next_state.progress_summary = decision.progress_update
            next_state.total_turns = state.total_turns
            next_state.last_codex_summary = self._summarize_codex_output(codex_result.stdout)
            next_state.last_codex_stdout = codex_result.stdout
            next_state.last_codex_stderr = codex_result.stderr
            next_state.last_codex_exit_code = codex_result.exit_code
            next_state.save(self.config.state_path)
            return {
                "event": "session_wrapped",
                "state": next_state,
                "decision": decision,
                "codex_result": codex_result,
            }

        codex_prompt = decision.next_instruction
        if state.session_turn == 0:
            codex_prompt = self._render_bootstrap_prompt(state, decision)
        self._emit("phase", {"name": "codex", "message": "Running Codex for the next step"})
        codex_result = self._run_codex_with_retry(codex_prompt)
        self._emit_result("codex_turn", codex_prompt, codex_result)
        if self._is_fatal_environment_error(codex_result):
            return self._handle_fatal_codex_error(
                state=state,
                codex_result=codex_result,
                reason="Codex could not execute the requested step due to a workspace environment error.",
                focus="environment",
                progress_update=state.progress_summary or decision.progress_update,
            )
        state.session_turn += 1
        state.total_turns += 1
        state.progress_summary = decision.progress_update
        state.last_codex_summary = self._summarize_codex_output(codex_result.stdout)
        state.last_codex_stdout = codex_result.stdout
        state.last_codex_stderr = codex_result.stderr
        state.last_codex_exit_code = codex_result.exit_code
        state.save(self.config.state_path)
        return {
            "event": "turn_executed",
            "state": state,
            "decision": decision,
            "codex_result": codex_result,
        }

    def run_until_stop(self):
        history = []
        while True:
            result = self.run_turn()
            history.append(result)
            if result["event"] in {"completed", "max_turns_reached"}:
                return history

    def _load_or_create_state(self) -> SessionState:
        if self.config.state_path.exists():
            return SessionState.load(self.config.state_path)

        state = SessionState.initial(
            session_id=1,
            progress_path=self._progress_path_for_session(1),
        )
        self._write_text(state.current_progress_path, self._default_progress_markdown())
        state.save(self.config.state_path)
        return state

    def _default_progress_markdown(self) -> str:
        return (
            "# PROGRESS\n\n"
            "## Completed\n- none\n\n"
            "## Current\n- not started\n\n"
            "## Next\n- waiting for first Codex turn\n\n"
            "## Issues\n- none\n"
        )

    def _read_progress(self, path: Path) -> str:
        if not path.exists():
            return self._default_progress_markdown()
        return path.read_text(encoding="utf-8")

    def _write_text(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _progress_path_for_session(self, session_id: int) -> Path:
        return self.config.session_dir / f"session-{session_id:03d}-progress.md"

    def _should_wrap_before_execution(self, state: SessionState) -> bool:
        return state.session_turn + 1 >= self.config.max_turns_per_session

    def _summarize_codex_output(self, stdout: str) -> str:
        text = " ".join(stdout.split())
        if len(text) <= 240:
            return text
        return f"{text[:237]}..."

    def _last_codex_result_from_state(self, state: SessionState):
        if state.last_codex_exit_code is None:
            return None
        return CodexResult(
            stdout=state.last_codex_stdout,
            stderr=state.last_codex_stderr,
            exit_code=state.last_codex_exit_code,
        )

    def _known_blockers(self, last_codex_result: CodexResult | None) -> str:
        if last_codex_result is None:
            return "none"
        if last_codex_result.exit_code == 0:
            return "none"
        stderr = last_codex_result.stderr.strip() or "unknown error"
        return f"Previous Codex execution failed: {stderr}"

    def _render_bootstrap_prompt(
        self, state: SessionState, decision: ControllerDecision
    ) -> str:
        bootstrap = render_prompt(
            self.config.session_bootstrap_prompt,
            {
                "requirement": self.config.short_requirement or self.config.requirement,
                "progress_summary": state.progress_summary or "No progress yet.",
            },
        )
        return f"{bootstrap}\n\nTask:\n{decision.next_instruction}"

    def _render_wrapup_prompt(self, state: SessionState) -> str:
        return render_prompt(
            self.config.session_wrapup_prompt,
            {
                "requirement": self.config.short_requirement or self.config.requirement,
                "progress_summary": state.progress_summary or "No progress yet.",
            },
        )

    def _ensure_requirement_doc(self) -> None:
        if self.config.requirement_doc_path.exists():
            return
        content = f"# Requirement\n\n{self.config.requirement.strip()}\n"
        self._write_text(self.config.requirement_doc_path, content)

    def _run_codex_with_retry(self, prompt: str) -> CodexResult:
        result = self.codex_runner.run(prompt, cwd=self.config.workspace)
        self._emit_result("codex_attempt_1", prompt, result)
        if result.exit_code == 0:
            return result
        if self._is_fatal_environment_error(result):
            return result

        retry_prompt = (
            f"{prompt}\n\n"
            "The previous Codex execution failed. "
            f"Retry once and focus on completing the same task. Error: {result.stderr.strip() or 'unknown error'}"
        )
        retry_result = self.codex_runner.run(retry_prompt, cwd=self.config.workspace)
        self._emit_result("codex_attempt_2", retry_prompt, retry_result)
        if retry_result.exit_code == 0:
            return retry_result
        return retry_result

    def _emit_result(self, event_type: str, prompt: str, result: CodexResult) -> None:
        self._emit(
            event_type,
            {
                "prompt": prompt,
                "exit_code": result.exit_code,
                "stdout": result.stdout,
                "stderr": result.stderr,
            },
        )

    def _emit(self, event_type: str, payload: dict) -> None:
        if self.event_logger is None:
            return
        self.event_logger(event_type, payload)

    def _is_fatal_environment_error(self, result: CodexResult) -> bool:
        if result.exit_code == 0:
            return False
        stderr = result.stderr or ""
        fatal_markers = [
            "Not inside a trusted directory",
            "No such file or directory",
            "Permission denied",
        ]
        return any(marker in stderr for marker in fatal_markers)

    def _handle_fatal_codex_error(
        self,
        *,
        state: SessionState,
        codex_result: CodexResult,
        reason: str,
        focus: str,
        progress_update: str,
    ) -> dict:
        state.status = "error"
        state.last_codex_summary = self._summarize_codex_output(codex_result.stderr or "")
        state.last_codex_stdout = codex_result.stdout
        state.last_codex_stderr = codex_result.stderr
        state.last_codex_exit_code = codex_result.exit_code
        state.progress_summary = progress_update
        state.save(self.config.state_path)
        decision = ControllerDecision(
            status="continue",
            next_instruction="Fix the workspace environment error before retrying.",
            reason=reason,
            focus=focus,
            progress_update=progress_update,
        )
        self._emit(
            "fatal_environment_error",
            {
                "reason": reason,
                "stderr": codex_result.stderr,
                "exit_code": codex_result.exit_code,
            },
        )
        return {
            "event": "fatal_environment_error",
            "state": state,
            "decision": decision,
            "codex_result": codex_result,
        }
