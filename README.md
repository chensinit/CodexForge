# CodexForge

Codex CLI를 작업 에이전트로 쓰고, OpenAI API를 상위 판단기로 붙여서 요구사항부터 완료 판정까지 자동 개발 루프를 돌리는 작은 오케스트레이터입니다.

한 번의 프롬프트로 끝내는 툴이 아니라, 다음 단계를 계속 판단하면서 Codex에 작업을 위임하고 세션 요약까지 남기는 방식에 가깝습니다.

## What It Does

- `config/task.json`에 목표 프로젝트와 요구사항을 적습니다.
- 첫 턴에는 구현 계획을 만들게 합니다.
- 이후 각 턴마다 OpenAI가 현재 진행 상태를 보고 다음 Codex 지시를 결정합니다.
- 세션 턴 제한에 도달하면 진행 문서를 남기고 다음 세션으로 이어갑니다.
- 완료되었다고 판단되면 루프를 종료합니다.

## Loop Shape

```text
Requirement -> Planning -> Codex execution -> OpenAI review -> next instruction
                                          -> session wrap-up -> next session
```

## Repo Layout

```text
autodev/
  cli.py
  controller.py
  orchestrator.py
  codex_runner.py
  config_loader.py
  models.py

config/
  common.json
  task.json
  initial_planning_prompt.md
  session_bootstrap_prompt.md
  step_review_prompt.md
  session_wrapup_prompt.md

pyproject.toml
README.md
```

## Requirements

- Python 3.12+
- Codex CLI installed and available as `codex`
- OpenAI API key

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

`config/common.json`을 채웁니다.

```json
{
  "openai": {
    "api_key": "YOUR_OPENAI_API_KEY",
    "model": "gpt-5-mini"
  },
  "codex": {
    "command": [
      "codex",
      "exec",
      "--skip-git-repo-check",
      "--dangerously-bypass-approvals-and-sandbox"
    ]
  },
  "loop": {
    "max_turns_per_session": 12,
    "max_total_turns": 60
  }
}
```

`config/task.json`에 개발 대상 폴더와 requirement를 적습니다.

한 턴만 실행:

```bash
python3 -m autodev.cli --one-turn
```

전체 루프 실행:

```bash
python3 -m autodev.cli
```

백그라운드 실행:

```bash
nohup python3 -m autodev.cli > develop.log 2>&1 &
```

## Config Files

### `config/common.json`

- OpenAI API 키와 판단 모델
- Codex CLI 실행 명령
- 세션별/전체 턴 제한

### `config/task.json`

- 실제로 개발할 워크스페이스 경로
- 상세 requirement
- step review에 넣을 짧은 requirement

### `config/*.md`

- Codex 부트스트랩
- 초기 계획 생성
- 턴별 리뷰
- 세션 종료 요약

## Runtime Files

실행이 시작되면 대상 워크스페이스 아래에 이런 상태 파일이 생깁니다.

- `.autodev/state.json`
- `.autodev/sessions/session-XXX-progress.md`
- `.autodev/sessions/session-XXX-summary.md`
- `AUTODEV_REQUIREMENT.md`

## Example Use Case

현재 기본 예시는 "계정 기능 없이 글 작성과 타임라인만 있는 X 스타일 미니 SNS"입니다.

이 정도 범위가 첫 테스트용으로 적당합니다.

- 결과물이 눈에 보입니다.
- SQLite로 저장 검증이 됩니다.
- HTML/CSS/서버 로직이 모두 한 번씩 돌게 됩니다.
- 너무 큰 요구사항이 아니라 턴 소모를 통제하기 쉽습니다.

## Notes

- OpenAI 판단기는 `/v1/responses`를 호출합니다.
- Codex CLI 인자 형식이 다르면 `config/common.json`의 `codex.command`를 수정하면 됩니다.
- 기본 설정은 공격적으로 자동화되어 있으니, 공개 저장소에 올릴 때는 실제 API 키를 절대 넣지 마세요.
