# Instagram.AI — Agent System

This document describes the agent system for the Instagram Reel intelligence & script-generation pipeline, and how it maps to the original 8-agent design.

The agents are REAL opencode subagents defined in `.opencode/agent/*.md` and invoked via commands in `.opencode/command/*.md`. The "supervisor" role is played by the primary opencode agent (the chat session itself) — it reads the root `AGENTS.md`, runs commands, and spawns the subagents below.

## Real subagents (`.opencode/agent/`)

### `reel-ingestor` (bash allow / edit deny)
Runs the deterministic pipeline scripts only: `System/scrape.py`, `System/process_reels.py`, `System/transcribe.py`, `System/ingest_reel.py`, `System/mark_analyzed.py`, `System/cleanup_assets.py`. Never hand-edits Brain files or the Excel log. Reports asset paths and failures.

### `reel-analyst` (edit allow / bash deny)
Analyzes ONE reel: reads every keyframe (`Assets/<id>_keyframe_*.jpg` — its primary visual evidence), the Whisper transcript (`Assets/<id>.txt`), and the reel's Brain note. Uses the `video-analysis` and `audio-analysis` skills, scores retention against the FIXED `Brain/Rubric.md`, writes `Brain/Analyses/<id>_{visual.json,audio.md,retention.md}`, and fills the reel's Brain note. Flags genuinely novel patterns. Spawn several in parallel for throughput (see `/analyze`).

### `pattern-librarian` (edit allow / bash deny)
Distills completed analyses into durable knowledge. Never duplicates a concept — updates existing `Brain/Patterns/*.md` nodes with new evidence and adjusts confidence. Maintains `Brain/Pattern_Library.md`, `Brain/Playbook.md`, `Brain/Trend_Reports.md`, `Brain/Frameworks/Hook_Database.md`, and `Brain/Frameworks/Script_Framework_Library.md`. Never touches `Brain/Rubric.md` or `Brain/My_Style.md`.

### `script-drafter` (edit allow / bash deny)
Generates 2–3 ready-to-shoot drafts on a topic (or adapted from a source reel's structure — never copied). Required reading: `Brain/My_Style.md` (overrides everything), Playbook, Pattern_Library, Hook_Database, Script_Framework_Library, Trend_Reports, Rubric. Formats scripts with the `advanced-reel-script-structure` skill and saves them to `Brain/Scripts/<Title>.md` in the established format (metadata, rubric scoring, alt hooks, timestamped blocks, thumbnail + caption).

### `style-critic` (edit allow / bash deny)
Refines user-pasted scripts: diagnosis vs `Brain/Rubric.md`, refined draft (keeps the user's idea — sharpens it), change log with per-change rationale. Proposes `Brain/My_Style.md` updates and applies them only after explicit user approval.

### `telegram-agent` (bash allow / edit allow)
Fetches Instagram reel links from your Telegram chat, deduplicates by shortcode, detects draft requests, and feeds reels into the existing pipeline. Calls `telegram_bot/fetch_messages.py` (one-shot `getUpdates` API call — no long-polling bot), stores results in `telegram_bot/telegram_reels.json` + syncs to `Brain/Reels_Log.xlsx` (Source=TELEGRAM). Presents suggestions to user, then orchestrates the same agents as `/sync`: `reel-ingestor` → `reel-analyst` → `pattern-librarian` → (optionally) `script-drafter` → `pdf-builder` → `telegram_bot/send_file.py` to deliver PDFs back to the chat. Timeline tracking via `last_update_id` offset ensures no message is read twice.

## Commands (`.opencode/command/`)

| Command | Flow |
|---|---|
| `/draft <topic>` | Smart defaults (30s, 3 drafts, SAVE CTA) → `script-drafter` → 2–3 drafts. Asks clarifying questions only when genuinely ambiguous. |
| `/redraft <reel_url>` | `reel-ingestor` → `reel-analyst` → `pattern-librarian` (if novel) → `script-drafter` (2–3 niche-adapted redrafts). |
| `/refine <script>` | `style-critic` → diagnosis + refined draft + change log. My_Style edits need approval. |
| `/analyze [shortcode\|pending]` | Up to 4 `reel-analyst` subagents in parallel → `mark_analyzed.py` → `pattern-librarian` for the batch. |
| `/sync [NICHE\|BRANDING\|ALL]` | scrape → process → transcribe → parallel analyze → distill, end to end. |
| `/tg [--dry-run] [--status]` | `telegram-agent` → fetch reel links from Telegram chat, dedup, detect draft requests, feed into pipeline. |

## Mapping from the original 8-agent design

| Original concept | Now |
|---|---|
| Supervisor Agent | Primary opencode agent (the chat session) |
| Ingestion Agent | `reel-ingestor` |
| Visual + Audio + Retention Agents | `reel-analyst` (one agent, both skills + rubric) |
| Pattern Intelligence Agent | `pattern-librarian` |
| Knowledge Graph Agent | `pattern-librarian` |
| Script Generator Agent | `script-drafter` |
| Feedback Evolution Agent | `style-critic` |
| Telegram Input Agent | `telegram-agent` |

## Invariants

- `Brain/Rubric.md` is FIXED — no agent ever edits it.
- `Brain/My_Style.md` is edited only by `style-critic`, only with user approval.
- Media in `Assets/` is deleted only by `System/cleanup_assets.py`, only for ANALYZED reels.
- Agents must not claim to have watched video or listened to audio — keyframes and Whisper transcripts are the only evidence.
