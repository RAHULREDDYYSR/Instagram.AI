---
name: audio-analysis
description: Skill to analyze the audio of an Instagram Reel for transcription, tone, pacing, and hooks.
---

# Audio Analysis Skill

This skill is designed for the `audio_agent` / `reel-analyst` to extract critical audio information from an Instagram Reel.

## Prerequisites

1. The Whisper transcript file `Assets/<shortcode>.txt`, produced by `uv run System/transcribe.py`. You CANNOT read `.wav` / `.mp3` files — never claim to have listened to audio. If the transcript is missing, say so explicitly and base audio findings on the caption alone (mark the report as degraded).

## Analysis Instructions

Base the report on the transcript (plus caption metadata from the reel's Brain note), focusing on the following elements:

### 1. Transcription and Structure
- **Full Transcript:** Quote the transcript verbatim from the `.txt` file (do not re-transcribe or "correct" it; note obvious Whisper artifacts).
- **Hook (0-3s):** What are the exact first words spoken?
- **Hook Category:** Classify the hook against the taxonomy in `Brain/Frameworks/Hook_Database.md` (e.g., Authority & Identity, Contrarian & Niche-Filtering). If it fits none, propose a new category name.
- **Story Structure:** How is the narrative structured? (e.g., Problem -> Agitation -> Solution, Personal Story -> Lesson).
- **Payoff/Value:** What is the core lesson or value delivered to the viewer?
- **CTA (Call to Action):** How does the video end? What are they asking the viewer to do?

### 2. Vocal Delivery
- **Tone:** (e.g., Aggressive, Calming, Educational, Conversational, Authoritative)
- **Emotion:** (e.g., Excited, Serious, Vulnerable, Humorous)
- **Delivery Energy:** High, Medium, or Low?
- **Confidence:** Does the speaker sound confident? (Note filler words like "um", "uh", or hesitations).

### 3. Pacing and Rhythm
- **Words per Second:** Estimate the speaking speed.
- **Speech Rhythm:** Is the speech choppy, fluid, or staccato?
- **Pause Locations:** Where does the speaker intentionally pause for effect?
- **Retention Drops:** Identify areas where the audio drags or becomes less engaging.

## Output Format

Always output your findings in a structured Markdown report:

```markdown
# Audio Analysis Report

## Transcription
(Full text here...)

## Structure
- **Hook:** 
- **Hook Category:** (from Brain/Frameworks/Hook_Database.md taxonomy)
- **Narrative Structure:**
- **Payoff:**
- **CTA:**

## Vocal Delivery
- **Tone:**
- **Emotion:**
- **Delivery Energy:**
- **Confidence:**

## Pacing
- **Words per Second:**
- **Speech Rhythm:**
- **Pause Locations:**
- **Retention Drops:**
```
