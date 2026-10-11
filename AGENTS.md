# seamflow-takehome

SeeFood Enterprise: a web app that classifies an image as "Hot Dog" or "Not Hot Dog". Built from the workbench template, one module at a time. Read by Claude Code and Codex; there is no CLAUDE.md on purpose.

Design: docs/ai_docs/requirements.md and docs/ai_docs/plan.md

## Layout

- `docs/ai_docs/` requirements, plan, and API contract. Read both files before every unit.
- `docs/decisions/` one short file per non-obvious decision.
- `docs/guides/` how-tos that are not obvious from the code.
- `backend/` FastAPI API and arq worker. `frontend/` Vite app.

## How to work here

- Run the check and paste its real output. Never report success without it.
- Keep diffs small and single-purpose.
- Git: branch per unit named `<type>/<slug>`, PR, squash-merge to main after CI. Commits use Conventional Commits with an imperative subject under 72 characters. No AI attribution trailers; AI use is disclosed in the README.
- Before writing new code, stop at the first rung that holds: does it need to exist; is it already in this codebase; standard library; native platform or browser feature; installed dependency; one line. Only then write the minimum that works, plus one small test if it has logic. Never cut validation, error handling, security, or accessibility to get there. End each task by listing what was skipped or not checked.
- Change only what the task requires. Don't improve, reformat, or refactor adjacent code; match its style. If you notice unrelated dead code, mention it, don't delete it. Remove only the imports and functions your own change orphaned.
- Python: `uv`. Prefer the standard library; ask before adding a dependency.
- When reviewing, report correctness gaps and missed requirements only. Skip style.
- Write a decision file only when the choice is hard to revert or an agent would otherwise re-open it.
- Docs, README text, comments, and commit messages: write about 80% of the way to ASD-STE100. Sentences under 20 words, active voice, one meaning per word, no should/may/might. Chat replies: normal prose.

## Don't

- Don't create CLAUDE.md, AGENTS.override.md, or per-tool duplicates of these rules.
- Don't install skills, plugins, or frameworks without asking.
- Don't commit secrets. Local config lives in `.env`, which is ignored.
