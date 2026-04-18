Create an implementation plan from the user requirement.

Rules:
- Do not write code yet.
- Read the requirement markdown in the project first.
- Read the project first if useful.
- Focus on concrete development steps.
- Keep the plan practical and short.
- Break work into small sequential tasks.
- Mention risks or unclear points only if they matter.
- Save the plan as a markdown document in the project.
- If a progress document already exists, update that same document instead of making a new one.
- In your reply, briefly say what document you created and what comes next.
- If the entire project or task is already complete and no further action is needed, include the token `[[DONE]]` in your reply.
- Do not ask for development direction; instead, use your own judgment to determine the best approach and proceed.
- Avoid testing whenever possible, and absolutely do not perform any tests that involve calling external APIs.

Write a markdown document in this format:

# Development Plan

## Goal
- ...

## Steps
1. ...
2. ...
3. ...

## Risks
- ...

## First Task
- ...

Input:
- Workspace: {workspace_path}
- Requirement: {requirement}
