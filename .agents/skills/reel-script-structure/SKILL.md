---
name: advanced-reel-script-structure
description: Format a finalized reel concept into contiguous timestamped shooting blocks with detailed Voice, Visual, and On-Screen Text directions. Use after the hook and narrative beats are chosen, or when asked to add timestamps and camera directions; preserve the script's own content domain.
---

# Advanced Reel Script Structure

Format a finished concept into a ready-to-shoot production blueprint. Before formatting, read `Brain/My_Style.md` and `Brain/Rubric.md`; report missing required files instead of inventing the owner's style or scoring rules. Personal style and explicit user constraints override generic suggestions.

The supervisor routes new scripts through `script-drafter` and refinements through `style-critic`. This specialist skill formats their writing; it does not run pipeline scripts or create a video.

## Domain and voice

Keep the topic/source pillar and register throughout wording, examples, visuals, thumbnail, and caption. A gym concept can use equipment/physique imagery; a mindset concept needs fitting faces, interiors, text, journals, city/nature scenes, or other appropriate visuals. Reuse source mechanics rather than wording, celebrity authority, or unsupported claims. Do not borrow gym props simply because an earlier formatting example used them.

Honor complete, punchy endings from personal style; do not impose an unfinished looping sentence or generic save/share prompt. A visual loop is optional when compatible with the chosen ending.

## Shooting blocks

Each timestamp range is a separate heading/paragraph, never a shooting-script table. Include all three keys; use explicit `(none)` when there is no overlay.

```markdown
### 0:00–0:03
**Voice:** [Exact spoken words or explicit audio cue.]
**Visual:** [Shot type + setting/lighting + movement/transition + exact action.]
**On-Screen Text:** [Short overlay or (none).]

### 0:03–0:07
**Voice:** [Next beat.]
**Visual:** [A concrete change in shot, framing, or action.]
**On-Screen Text:** [(none)]
```

The visual line needs a shot type (CU, macro, wide, OTS, etc.), a movement or transition, and a specific action; add environment/lighting details that support the script. Scale detail to the declared production lane. Keep overlays concise (normally fewer than six words). Plan a visual change roughly every three to five seconds when it supports the register.

Cover the full declared runtime from `0:00` with contiguous, non-overlapping ranges. Plan hook → retention/problem → value/payoff → complete ending, adjusting beat lengths to the actual concept rather than forcing a template. For a 30-second reel, a useful starting allocation is 0–3, 3–7, 7–25, 25–30 seconds; for 60 seconds, 0–3, 3–10, 10–50, 50–60. These are planning aids, not mandatory cuts.

Count spoken words and report words/second against declared runtime. This is a delivery estimate, not a measured source cadence. Keep each block's voice within its duration; aim around 2.5–3 WPS for an energetic script only when personal style supports it.

## Canonical draft document

Wrap the blocks in the existing draft format:

1. `# <Title>` and metadata: topic/concept, audience, pillar/register, **Framework:**, canonical Brain sources as wiki-links, **Length (s):** 30 (replace 30 with the runtime), focus allocation, spoken-word budget, **Estimated Performance Score:**, and separate **Overall Retention Score:** 7.5 / 10 (replace with the calculated score). Use these exact label formats for preflight compatibility.
2. `## Rubric Self-Score` followed by retention/psychology rationale and a table for the eight fixed factors, each with a concrete justification. Use `| Factor | Score | Justification |` and integer score cells such as `7 / 10`. Put the overall mean in the metadata line above, not a ninth numeric factor row. Overall retention is the arithmetic mean rounded half-up to one decimal; creative performance estimates remain separate.
3. Three alternative hooks.
4. Full timestamped shooting script as separate blocks.
5. Thumbnail idea and caption.
6. Production summary: word count/WPS, shoot estimate, new shots, feasibility lane (`LOW_PRODUCTION` or `HIGH_UPSIDE`), and asset/rights assumptions.

Rubric tables are allowed outside the shooting blocks. Save in the assigned unique run/instance directory; never overwrite earlier drafts. The supervisor delegates `System/preflight.py script --file <path>` to `reel-ingestor` and sends only valid drafts to `pdf-builder`.
