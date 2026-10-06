---
name: reel-refine
description: Diagnose and refine a pasted reel script against Instagram.AI's fixed rubric, proven patterns, and personal style, explaining each change. Use for script feedback and the legacy /refine alias.
---

# Reel refine

Invoke as `$reel-refine <script or file> [feedback]`. If there is no usable hook, topic, or angle, request the script or one compact clarification rather than guessing. Read an explicitly supplied file as the script.

## Delegate the critique

Use the exact native Codex `agent_type="style-critic"` when exposed. If the wrapper lacks `agent_type`, read `.codex/agents/style-critic.toml`, apply its `model` and `model_reasoning_effort` where supported, and include its complete `developer_instructions` in the spawn prompt. Name the task `style-critic`, preserve its boundaries, and report unsupported overrides. Include root, the complete script, user feedback, declared runtime, and constraints. The supervisor coordinates and presents the returned critique.

For the `collaboration.spawn_agent` fallback, use a fresh task context (`fork_turns="none"`) when supplying model/effort overrides; full-history forks cannot take those overrides. Map `model_reasoning_effort` to the wrapper's `reasoning_effort` field. Provide all necessary scope and evidence in that fresh prompt.

Check `Brain/My_Style.md`, `Brain/Rubric.md`, `Brain/Pattern_Library.md`, `Brain/Playbook.md`, and `Brain/Frameworks/Hook_Database.md` before scoring/refining. If missing, report the Brain prerequisite; do not invent rubric factors or the owner's voice. The fixed rubric is never edited.

Require the critic to:

- Score the original's eight rubric factors, justify each with the script, and derive overall retention as their arithmetic mean rounded half-up to one decimal. Keep any creative performance estimate separate.
- Preserve the user's central idea, working lines, pillar, and register; apply `Brain/My_Style.md` without an unrequested pivot to fitness.
- Return a diagnosis table and three largest retention issues, the full refined draft, and a change log tied to patterns/rubric factors.
- Load `.agents/skills/reel-script-structure/SKILL.md` for separate contiguous timestamp blocks with `Voice`, `Visual`, and `On-Screen Text` (explicit `(none)` allowed), no shooting-script table. Use a complete ending and calculate spoken word count/WPS for the declared runtime; default 30 seconds unless the script or request calls for 60.
- Propose exact `Brain/My_Style.md` lines only when a repeatable preference is supported. A proposal is not approval to edit. Only this role may apply a style change, after the human explicitly approves those lines; preserve existing knowledge.

## Present and save

Present the full diagnosis, refined script, change log, and any exact style proposal. Do not collapse the script into a summary. A request to refine already authorizes producing the draft; saving it is authorized when the user asks to save/keep it or the original request includes persistence. In that case, have the critic save to a new `Brain/Scripts/<Title_With_Underscores>.md` without overwriting another draft, then delegate `uv run System/preflight.py script --file <path>` to exact `reel-ingestor` (use the same native-role/fallback procedure). Repair and recheck failures before reporting the saved draft as valid, and provide its absolute link. Apply a My_Style edit only with the separate explicit approval described above.

## Successful completion cleanup

Follow the root `AGENTS.md` Completion and Assets cleanup barrier. After every requested result is saved outside Assets, required validation/quality checks pass, all writers and asset consumers finish, and there are no unresolved failures/revisions or user review holds, the top-level supervisor MUST delegate `uv run System/cleanup_assets.py --all-assets` to exact `reel-ingestor` (using the role binding/fallback above). The owner has already authorized this: no repeated permission request. Wait for any attended improvement pass first. Verify exit 0, the retained folder when it existed, and `Remaining entries: 0`; report removed counts and durable result paths. All Assets contents are temporary, including hidden files, nested directories, links and workflow.png. Never delete Brain, workbook/database, creator registry, Telegram state, or outputs saved elsewhere. Do not run asset-dependent checks again after deletion.

Nested invocations defer cleanup to their outermost workflow so analysis cannot clear inputs before later drafting/PDF/delivery stages. Retain assets if required work is incomplete or other known consumers still need them; report the reason. Dry-run, status-only, blocked, and output-not-persisted requests do not trigger deletion. Only the authorized checkout's literal Assets folder is eligible.
