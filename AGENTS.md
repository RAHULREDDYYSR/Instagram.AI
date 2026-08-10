# Instagram.AI — Agent Guide

Personal pipeline that scrapes Instagram Reels (Apify), ingests media (yt-dlp + ffmpeg), transcribes audio (Whisper), analyzes them with AI agents, and turns proven patterns into reel scripts for the owner's niche: fitness / bodybuilding / gym / lifestyle / masculinity / self-improvement / relationships.

`main.py` is a placeholder — real work runs through `System/` scripts and the opencode agents/commands below.

## Toolchain

- Python 3.13 pinned (`.python-version`); ALWAYS `uv run …` — never `python`, never `pip` (see `.agents/rules/uv.md`). Add deps with `uv add <pkg>`.
- `ffmpeg` must be on `PATH` (ingest shells out to it).
- No tests, linter, formatter, or CI exist in this repo — don't look for them.

## Pipeline (order matters)

| Step | Command | Effect |
|---|---|---|
| 1. Scrape | `uv run System/scrape.py --category NICHE\|BRANDING\|ALL [--max-reels N]` | Apify metadata → `Brain/Reels_Log.xlsx`, Status=SCRAPED. Parallel across creators. |
| 2. Process | `uv run System/process_reels.py [--category …] [--limit N] [--shortcodes ID ...] [--checkpoint-every N] [--delete-assets] [--skip-transcribe]` | Downloads + validates media (parallel), creates Brain note, Status=PROCESSED after scoped transcription. **Assets are kept**; chains into transcribe.py. |
| 3. Transcribe | `uv run System/transcribe.py [--shortcode ID] [--shortcodes ID ...] [--limit N]` | Whisper → `Assets/<id>.txt`. Auto-runs for the exact successful IDs at the end of step 2. |
| 4. Analyze | opencode `/analyze` command (agent-driven) | Fills `Brain/Analyses/<id>_*` + the reel's Brain note. |
| 5. Mark | `uv run System/mark_analyzed.py` | Complete analysis trios → Status=ANALYZED. |
| 6. Cleanup | `uv run System/cleanup_assets.py [--dry-run]` | Deletes media only for ANALYZED reels. |

- Creator lists live in `System/creators.json` — edit that file, never hardcode usernames in scripts.
- Registered one-off reel: `uv run System/register_oneoff.py <reel_url>` then `uv run System/process_reels.py --shortcode <id>`; this preserves the normal Excel status lifecycle and cleanup eligibility. Raw asset utility: `uv run System/ingest_reel.py <reel_url>` then `uv run System/transcribe.py --shortcode <id>`.
- Telegram reels: `/tg` — fetches links from your Telegram chat, dedup by shortcode, feeds into the same pipeline (Status=SCRAPED, Source=TELEGRAM in Excel).
- Status lifecycle: `SCRAPED → PROCESSED (keyframes + .wav + .txt on disk; .mp4 pruned) → ANALYZED (media safe to delete)`.

## opencode wiring (`.opencode/`)

- **Subagents** (`.opencode/agent/`): `reel-ingestor` (bash), `reel-analyst`, `pattern-librarian`, `script-drafter`, `style-critic`, `telegram-agent` (bash+edit). Rationale + mapping from the original 8-agent design: `.agents/AGENTS.md`.
- **Commands** (`.opencode/command/`):
  - `/draft <topic>` — 2–3 script drafts from the Brain (smart defaults; asks only if ambiguous).
  - `/redraft <reel_url>` — ingest → analyze → 2–3 niche-adapted redrafts.
  - `/refine <script>` — critique + refined draft vs rubric & My_Style.
  - `/analyze [shortcode|pending]` — parallel analysis of unanalyzed reels.
  - `/sync [NICHE|BRANDING|ALL]` — the full pipeline end-to-end.
  - `/tg [--dry-run] [--status]` — fetch reel links from Telegram chat, dedup, feed into pipeline.
- Skills live in `.agents/skills/` (registered via `skills.paths` in `.opencode/opencode.json`): `video-analysis`, `audio-analysis`, `advanced-reel-script-structure`.

## Brain map (Obsidian wiki-linked `[[…]]`)

- `Brain/Reels_Log.xlsx` — spreadsheet of truth (deduped by shortcode).
- `Brain/Reels/<id>.md` (NICHE) / `Brain/Branding/<id>.md` (BRANDING) — per-reel notes.
- `Brain/Analyses/<id>_{visual.json,audio.md,retention.md}` — agent outputs; the complete trio flips a reel to ANALYZED.
- `Brain/Creators/_registry.json` — processed shortcodes per creator.
- `Brain/Patterns/`, `Brain/Frameworks/` (Hook_Database, Script_Framework_Library), `Brain/Scripts/` (generated drafts).
- `Brain/Playbook.md`, `Pattern_Library.md`, `Trend_Reports.md`, `My_Style.md` — aggregated knowledge. `Brain/Rubric.md` is FIXED — never edit it.

## Environment & secrets

- `.env` (gitignored): `APIFY_API_KEY` required by scrape/process; `OPENAI_API_KEY` required by transcribe.
- `.env` also contains `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ALLOWED_CHAT_ID` or `TELEGRAM_ALLOWED_USER_ID` for the local bot.
- `System/cookies.txt` (gitignored): only used by legacy `fetch_creator_reels.py`.
- Never commit or paste the contents of these files.

## Legacy — do not extend

`System/fetch_creator_reels.py` and `System/fetch_multiple_creators.py` are superseded by the scrape → process pipeline. Use only if explicitly asked.

## Generated scripts

Drafts are saved to `Brain/Scripts/<Title>.md` in the established format (metadata header, rubric scoring, alternative hooks, timestamped Voice/Visual/On-Screen-Text blocks via the `advanced-reel-script-structure` skill). `Brain/My_Style.md` rules override skill defaults.

## Supervisor Rules (for the primary opencode agent — the chat session)

### Subagent Binding
- When a command file specifies a named subagent (e.g. `reel-ingestor`, `reel-analyst`, `pattern-librarian`, `script-drafter`, `style-critic`), the supervisor MUST spawn that exact subagent type using the `task` tool with the matching `subagent_type`.
- **Never** use a general-purpose `task` agent as a substitute for a defined subagent. The supervisor is a coordinator, not a worker-bee.

### Subagent Type Mapping
| Work type | Subagent to spawn |
|---|---|
| Pipeline scripts (scrape, process, transcribe, ingest, mark, cleanup) | `reel-ingestor` |
| Analyzing reels (keyframes + transcript + rubric) | `reel-analyst` |
| Distilling patterns into Brain | `pattern-librarian` |
| Writing script drafts | `script-drafter` |
| Refining user-pasted scripts | `style-critic` |
| Fetching reel links from Telegram | `telegram-agent` |

### Parallel Spawning
- When a command says "IN PARALLEL" (e.g. up to 4 `reel-analyst` in `/analyze`), batch ALL parallel spawns in a SINGLE `task` tool call block. Do not spawn them sequentially in the main context.

### Pipeline Execution: ALWAYS via Subagent
The supervisor must **never** execute pipeline scripts (`scrape.py`, `process_reels.py`, `transcribe.py`, `mark_analyzed.py`, `cleanup_assets.py`, `ingest_reel.py`) by calling `uv run` directly in a bash tool call.

**WRONG (don't do this):**
```
bash: uv run System/scrape.py --category BRANDING --max-reels 8
bash: uv run System/process_reels.py --category BRANDING
```

**RIGHT (always use the appropriate subagent):**
```
task: subagent_type=reel-ingestor, prompt="Run scrape.py for BRANDING category, max-reels 8. Report shortcodes scraped and any failures."
task: subagent_type=reel-ingestor, prompt="Run process_reels.py for BRANDING category. Report shortcodes processed and any failures."
task: subagent_type=reel-ingestor, prompt="Run transcribe.py for all PROCESSED reels. Report shortcodes transcribed."
```

The supervisor's only role is to **spawn, coordinate, and delegate** — never to run deterministic pipeline scripts itself. All bash operations for pipeline work go through `reel-ingestor`. All analysis work goes through `reel-analyst`. All pattern/script work goes through their respective subagents.

### Sequential Dependency
- When stages depend on each other (ingest → analyze → redraft), run in order. Do not skip stages or run out of order.
