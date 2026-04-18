from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from autodev.config_loader import load_loop_config
from autodev.codex_runner import CodexRunner
from autodev.gemini_runner import GeminiRunner
from autodev.qwen_runner import QwenRunner
from autodev.controller import OpenAIController
from autodev.orchestrator import AutoDevOrchestrator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Autonomous Codex CLI development loop driven by OpenAI API"
    )
    parser.add_argument(
        "--common-config",
        default="config/common.json",
        help="Shared sensitive settings JSON path",
    )
    parser.add_argument(
        "--task-config",
        default="config/task.json",
        help="Task settings JSON path",
    )
    parser.add_argument(
        "--prompt-dir",
        default="config",
        help="Prompt template directory",
    )
    parser.add_argument(
        "--one-turn",
        action="store_true",
        help="Execute only one orchestration turn",
    )
    return parser


def main() -> int:
    try:
        args = build_parser().parse_args()
        config = load_loop_config(
            common_config_path=Path(args.common_config).resolve(),
            task_config_path=Path(args.task_config).resolve(),
            prompt_dir=Path(args.prompt_dir).resolve(),
        )

        print("=" * 80, file=sys.stderr)
        print(f"Workspace Path: {config.workspace}", file=sys.stderr)
        print("Starting task with the following requirement:", file=sys.stderr)
        print("-" * 80, file=sys.stderr)
        print(config.requirement, file=sys.stderr)
        print("=" * 80, file=sys.stderr, flush=True)

        orchestrator = AutoDevOrchestrator(
            config=config,
            codex_runner=CodexRunner(config.codex_command, event_logger=_log_event),
            gemini_runner=GeminiRunner(
                api_key=config.gemini_api_key,
                models=config.gemini_models,
                event_logger=_log_event
            ),
            qwen_runner=QwenRunner(
                api_key=config.qwen_api_key,
                models=config.qwen_models,
                base_url=config.qwen_base_url,
                event_logger=_log_event
            ),
            controller=OpenAIController(
                model=config.openai_model,
                api_key=config.openai_api_key,
                review_prompt_template=config.step_review_prompt,
            ),
            event_logger=_log_event,
        )
        if args.one_turn:
            results = [orchestrator.run_turn()]
        else:
            results = orchestrator.run_until_stop()
        print(json.dumps([_serialize_result(result) for result in results], ensure_ascii=False))
        return 0
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1


def _serialize_result(result: dict) -> dict:
    return {
        "event": result["event"],
        "session_id": result["state"].session_id,
        "session_turn": result["state"].session_turn,
        "total_turns": result["state"].total_turns,
        "status": result["state"].status,
        "reason": result["decision"].reason,
        "focus": result["decision"].focus,
        "progress_update": result["decision"].progress_update,
    }


def _log_event(event_type: str, payload: dict) -> None:
    print(
        json.dumps({"event": event_type, **payload}, ensure_ascii=False),
        file=sys.stderr,
        flush=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
