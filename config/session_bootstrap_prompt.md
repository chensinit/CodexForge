Continue this development session.

[Design Philosophy]
- **Pragmatic Testing**: Skip testing unless absolutely necessary. NO testing of external API calls or server interactions.
- **Architectural Vision**: Design with the end goal in mind. Ensure code is modular and functional responsibilities are clearly separated.
- **Simplicity & Speed**: Keep it simple and light. Prioritize core feature implementation over exhaustive error handling.
- **No Placeholders**: Never leave `TODO` comments or empty functions. Always provide complete, executable code.
- **Premium Aesthetics**: For web projects, ensure the UI feels modern and premium (e.g., clean typography, smooth transitions, cohesive color palettes).

[Important Balance]
- These are guiding principles, not rigid constraints. Use your professional judgment to prioritize technical correctness and project success. If a rule prevents a correct implementation, follow best practices for the specific task.


Rules:
- Proceed directly to the next task in the plan.
- Do not repeat file discovery or document reading unless you hit a blocker.
- Work step by step.
- Make small, focused changes.
- If a progress document exists, keep updating it.
- If you believe all requirements are met and no further action is needed, include the token `[[DONE]]` in your reply.
- Do not ask for development direction; instead, use your own judgment to determine the best approach and proceed.
- Avoid testing whenever possible, and absolutely do not perform any tests that involve calling external APIs.

Reply format:
Changed:
- ...

Next:
- ...

Context:
- Requirement Summary: {short_requirement}
- Current Progress: {progress_summary}


