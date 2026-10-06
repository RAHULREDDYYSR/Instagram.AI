---
name: reel-draft
description: Write ready-to-shoot reel scripts on a topic using Instagram.AI's Brain, personal style, and proven patterns, then validate and compile a PDF. Use for topic-based drafting and the legacy /draft alias.
---

# Reel draft

Invoke as `$reel-draft <topic> [constraints]`. Ask for a topic only when none was supplied.

## Delegation

Coordinate the exact roles `script-drafter`, `reel-ingestor`, and `pdf-builder`; do not do their work in the supervisor. Use native Codex `agent_type` with the exact role name when exposed. If the wrapper lacks `agent_type`, read `.codex/agents/<role>.toml`, spawn an agent with that role's `model` and `model_reasoning_effort` when supported, and include its complete `developer_instructions` in the task prompt. Name the task after the role, preserve its file/tool boundaries, and report any unsupported override rather than substituting an unrestricted generic worker.

For the `collaboration.spawn_agent` fallback, use a fresh task context (`fork_turns="none"`) when supplying model/effort overrides; full-history forks cannot take those overrides. Map `model_reasoning_effort` to the wrapper's `reasoning_effort` field. Provide all necessary scope and evidence in that fresh prompt.

Every handoff includes repository root, run ID, input scope, explicit output paths, constraints, and expected success/failure evidence. Batch independent spawns when supported; otherwise launch them without waiting between launches and respect available concurrency slots.

## Resolve the brief

- Check that `Brain/My_Style.md`, `Brain/Rubric.md`, `Brain/Playbook.md`, `Brain/Pattern_Library.md`, `Brain/Frameworks/Hook_Database.md`, `Brain/Frameworks/Script_Framework_Library.md`, and `Brain/Trend_Reports.md` exist. Report missing Brain prerequisites before drafting; never invent style, rubric, or proven patterns. `Brain/Rubric.md` is fixed.
- Default to three distinct drafts of 30 seconds, with complete punchy spoken endings. Infer the pillar and register from the topic; fitness, bodybuilding, gym, lifestyle, masculinity, self-improvement, and relationships are available, with no fitness default. `Brain/My_Style.md`, including Vibe Match, governs wording, examples, visuals, thumbnail, and caption.
- Ask one compact clarification only if subject, purpose, pillar, or requested creator style is materially ambiguous. Honor user-supplied constraints and existing authorization.
- Derive 2–4 topic-specific focus areas and a reasonable allocation from Brain confidence and pillar adjacency. Auto-allocate by default when the user provided no split or authorized auto. An optional focus question may improve a genuinely ambiguous brief; it is not a mandatory gate. Custom weights sum to 100, with no area below 10% unless the user requests it. Record and pass verbatim `Focus Allocation: X% area / Y% area / Z% area`.

## Draft, validate, and deliver

1. Assign a unique `run_id` and outputs under `Brain/Scripts/_runs/<run_id>/<instance_id>/`. Spawn one `script-drafter` for the requested count; exactly two requested drafts may use two concurrent drafters with distinct angle assignments and isolated directories. Never overwrite existing drafts. If another run is mutating aggregate Brain files, give drafters an immutable snapshot of relevant aggregate text and cited canonical nodes, or wait for that writer to finish.
2. Require the drafter to load `.agents/skills/reel-script-structure/SKILL.md` and write the established metadata, eight-factor rubric table, three alternative hooks, timestamped shooting blocks, thumbnail/caption, and production summary. Each block has `Voice`, `Visual`, and `On-Screen Text` (explicit `(none)` allowed), with contiguous non-overlapping timestamps from 0:00 to declared runtime. Measure draft spoken word count and compute WPS; identify runtime as an estimate. Keep `Estimated Performance Score` separate from `Overall Retention Score`, which is the eight scores' arithmetic mean rounded half-up to one decimal. A two-draft set differs across at least two of hook grammar, framework, emotional angle, visual engine, production effort, or CTA.
3. Spawn `reel-ingestor` to run `uv run System/preflight.py script --file <path>` separately for every exact Markdown output. Repair invalid outputs through the drafter, then recheck; no invalid draft enters PDF generation. Check score arithmetic, metadata, timestamps, word budget, ending/CTA, and shooting format.
4. Spawn `pdf-builder` with only the validated paths and a unique `draft_result/<run_id>/<slug>.pdf`. It runs `uv run System/generate_scripts_pdf.py --scripts <paths...> --output <pdf> --topic <topic>` and `uv run System/preflight.py pdf --file <pdf> --title <topic>`. The PDF CLI accepts 1–3 inputs; for larger requested sets, build separately named batches. Verify nonzero outputs and actual validation results; do not deliver missing titles, `Untitled`, `Framework: —`, or failed text extraction as a finished PDF.
5. Present every full draft, preceded by title, framework, focus allocation, estimated performance score and arithmetic rubric score. Include absolute Markdown/PDF links, production lane, and a short comparison of the angles. Report exact failure evidence if delivery remains incomplete. PDF creation does not authorize sending files or messages to Telegram or any other recipient.
