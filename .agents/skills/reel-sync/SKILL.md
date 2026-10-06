---
name: reel-sync
description: Run Instagram.AI's creator scrape, scoped media processing/transcription, parallel analysis, and pattern distillation end to end. Use for full pipeline runs and the legacy /sync alias.
---

# Reel sync

Invoke as `$reel-sync [NICHE|BRANDING|ALL] [--max-reels N]`; default ALL and 5 reels per creator. Honor explicit category, limits, and creator scope. Creator lists come from `System/creators.json`, not hardcoded agent usernames.

## Delegate and prepare

Use exact native Codex `agent_type="reel-ingestor"` for deterministic stages. If the wrapper lacks `agent_type`, read `.codex/agents/reel-ingestor.toml`, apply its `model`/`model_reasoning_effort` where supported, and put complete `developer_instructions` in the task prompt. Apply the same procedure to `reel-analyst`, `pattern-librarian`, and `pipeline-improver` when the linked workflows call them. Preserve boundaries and report unsupported overrides; the supervisor never runs pipeline scripts itself.

For the `collaboration.spawn_agent` fallback, use a fresh task context (`fork_turns="none"`) when supplying model/effort overrides; full-history forks cannot take those overrides. Map `model_reasoning_effort` to the wrapper's `reasoning_effort` field. Provide all necessary scope and evidence in that fresh prompt.

Verify workbook and Brain prerequisites, including fixed `Brain/Rubric.md`, and ask the ingestor to check runtime/credentials by availability only: `uv`, ffmpeg, Apify for scrape/process, OpenAI for transcription. Never paste `.env` or cookie contents. Missing Brain files require a prerequisite report, not fabricated knowledge.

Maintain one exact run manifest across the stages: command/arguments, category/creator scope, newly scraped IDs, selected processing IDs, extraction successes, transcript successes, valid analysis IDs, actual statuses, failures/retries/user corrections, outputs, and timings when known. Never infer per-ID success from a count or zero exit status. Never run concurrent workbook writers or pattern librarians, and never hand-edit workbook/registry. The normal run keeps media for analysis and does not invoke cleanup.

## Strict stage order

1. **Scrape:** spawn `reel-ingestor` for `uv run System/scrape.py --category <category> --max-reels <N>` plus only supported user-supplied filters. Preserve workbook columns such as Source, dedup by shortcode, and return the exact new-ID manifest.
2. **Select/process:** have ingestor select the pending workbook rows in the authorized category, respecting any requested limit. A normal category sync includes eligible existing pending rows; a user request limited to newly scraped reels must use only that subset. Freeze and report the selected IDs, then run `uv run System/process_reels.py --category <category> --shortcodes <ids...>` with supported optional limits/checkpoint controls. Empty selection means no processing, never an unscoped command. Processing transcribes only successful extraction IDs. Verify valid transcript/assets and PROCESSED status before downstream handoff; do not pass extraction-only successes or silently use `--skip-transcribe`/`--delete-assets`.
3. **Analyze/validate:** load [reel-analyze](../reel-analyze/SKILL.md) as a nested workflow with only the exact validated processed-ID manifest. Repair missing/invalid scoped transcripts where needed. Spawn one analyst per ID in parallel within capacity, respect their evidence limitations, and wait for the analyst barrier before per-ID analysis preflight.
4. **Mark/distill:** these stages belong to the same nested analysis invocation; do not run them twice. Follow its validated-only status marking and single batch librarian. `mark_analyzed.py --shortcodes <ids...>` writes workbook state; the librarian writes pattern/aggregate knowledge. They may run concurrently after validation when their state domains are separate, but sequential marking then distillation is safe and simpler. Do not introduce a dependency on absent `System/patterns_index.py` or `_index.md`; librarian dedup uses focused existing-node discovery. Any parallel drafting elsewhere must read a frozen Brain snapshot captured before librarian writes.
5. **Report:** list new reels scraped, selected/processed IDs, valid transcripts, completed analyses with hook/retention per ID, patterns created/updated, failed/skipped IDs, and verified cleanup eligibility. Distinguish aggregate counts from exact success lists; never claim a lifecycle stage or persistence completed before its evidence returns.
6. **Improve once:** after the final top-level report, load [pipeline-self-improvement](../pipeline-self-improvement/SKILL.md) with this run's manifest. Qualify only on human interaction during the run beyond the initial invocation; otherwise emit `Self-improvement skipped: unattended session.`

On a failed stage, stop dependent work, report exact errors and the narrow stage/scope to resume. Preserve successes already written and unrelated pending reels. Resume only after ingestor verifies artifact manifests and workspace lock/preflight results; at most one evidence-based retry per failed operation. An unattended run never gains permission to mutate instructions or send Telegram messages.
