# Instagram.AI — Codex Agent System

The main Codex chat is the supervisor. Project-scoped custom roles are standalone `.codex/agents/*.toml` files; native workflow skills are under `.agents/skills/`. Root `AGENTS.md` contains the routing table, model policy, pipeline contract, and shared invariants.

## Role boundaries

- **reel-ingestor** runs deterministic `System/` pipeline and preflight CLIs via uv. Scripts own workbook/creator registry writes. No manual Brain edits or ad hoc asset deletion.
- **reel-analyst** owns one shortcode's analysis trio and source-note analysis sections. Inspect actual JPEGs with image tools and read the Whisper transcript. Current extraction covers the first five seconds only. Do not claim full-reel visual coverage or heard vocal qualities. Produce the evidence-backed, source-preserving `ADAPTATION_BRIEF v1`.
- **pattern-librarian** is the single writer to aggregate Brain/pattern/framework files. Merge evidence into existing canonical concepts; preserve confidence and provenance. Never change rubric or personal style.
- **script-drafter** writes original, ready-to-shoot scripts using the specialist formatting skill and supplied focus allocation. Respect frozen source pillar/register, `Brain/My_Style.md`, arithmetic rubric scoring, runtime budgets, and unique run/instance paths.
- **style-critic** critiques/refines the user's idea, explains changes, and proposes personal style changes. Apply `Brain/My_Style.md` edits only after explicit approval of the proposal.
- **telegram-agent** owns fetch/status/update CLIs and returns exact IDs plus any draft intent. The supervisor coordinates subsequent domain work. Sending a document/message needs explicit user authorization, passed with the assignment.
- **pdf-builder** uses the public parameterized renderer for validated Markdown paths, verifies PDF preflight, and visually inspects page layout. It does not rewrite scripts, style, workbook, or unrelated code.
- **coding-agent** maintains project code, dependencies, config, and docs within the assignment. Verification uses uv and read-only/local checks where possible; domain pipeline runs remain delegated to reel-ingestor. No live Brain/state edits.
- **pipeline-improver** makes small evidence-based instruction changes after an attended processing run. It cannot change model/effort/permission settings, pipeline code, fixed rubric, approved style, or existing run outputs.

## Skill responsibilities

Six workflow skills replace the OpenCode commands: `reel-draft`, `reel-redraft`, `reel-refine`, `reel-analyze`, `reel-sync`, and `reel-telegram`. They orchestrate the roles above, preserving sequential dependencies and disjoint ownership during parallel work.

Specialist skills remain independently discoverable: `video-analysis`, `audio-analysis`, `advanced-reel-script-structure` (stored in `reel-script-structure/`), and `pipeline-self-improvement`. Load only the skills needed for the current assignment.

## Migration notes

The source `.opencode/` setup is local and gitignored. It is retained in the primary checkout for reference; Codex does not load it. Nine roles were migrated, including the previously undocumented coding, PDF, and instruction-improvement roles.

OpenCode permission switches do not translate to Codex file/tool enforcement. The role scopes above are instructions; runtime permissions inherit the parent session. On hosts lacking custom `agent_type`, the supervisor must pass the actual TOML developer instructions and explicit model/effort to a fresh-context child. Task names alone do not establish bindings.
