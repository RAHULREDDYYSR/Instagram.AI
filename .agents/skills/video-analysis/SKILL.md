---
name: video-analysis
description: Skill to analyze the first 5 seconds of an Instagram Reel and its keyframes to identify visual patterns, hooks, and editing styles.
---

# Video Analysis Skill

This skill is designed for the `visual_agent` to extract critical visual information from an Instagram Reel.

## Prerequisites

1. Keyframes extracted as `jpg` images (`Assets/<id>_keyframe_*.jpg`) — your PRIMARY evidence. READ all keyframe images IN PARALLEL in a single tool-call block (concurrent Read calls for all `.jpg` files at once).
2. The first-5-seconds `mp4` exists on disk but is NOT directly readable by you. Infer motion, transitions, and pacing from the keyframe sequence plus the caption/metadata in the reel's Brain note. Never claim to have watched the video.

## Analysis Instructions

When analyzing the keyframes, pay close attention to the following aspects:

### 1. Opening Shot (0-1s)
- **Camera Angle:** (e.g., eye-level, low angle, high angle, selfie)
- **Motion:** (e.g., static, walking, frantic movement, slow zoom)
- **Subject:** (What is the first thing the viewer sees?)

### 2. Editing Style
- **Pattern Interrupts:** Identify any sudden visual changes (e.g., zooms, pop-ups, flashes).
- **Scene Transitions:** How does the video move from one shot to another? (e.g., hard cut, zoom transition, whip pan)
- **Visual Pacing:** Fast (multiple cuts per second), Medium, Slow (long takes).

### 3. Text and Overlays
- **Captions:** Are they baked in? What color and font style?
- **Text Overlays:** (e.g., Hook text on screen: "3 things I wish I knew...")

### 4. Hook Archetype
Determine the visual hook archetype:
- **Action Hook:** Subject doing something interesting immediately.
- **Authority Hook:** Subject speaking directly to the camera in an authoritative setting.
- **Curiosity Hook:** Showing something unusual or unexpected.
- **Aesthetic Hook:** High-quality, cinematic visuals that grab attention.

## Output Format

Always output your findings in a structured JSON block:

```json
{
  "opening_shot": {
    "camera_angle": "",
    "motion": "",
    "subject": ""
  },
  "editing_style": {
    "pattern_interrupts": [],
    "scene_transitions": [],
    "visual_pacing": ""
  },
  "text_overlays": {
    "captions": "",
    "hook_text": ""
  },
  "hook_archetype": "",
  "transferable_tactics": [],
  "niche_fit": ""
}
```

- **transferable_tactics:** 2–4 concrete visual moves from this reel that the user (fitness / gym / lifestyle niche) could reuse in their own shoots — e.g. "phrase-by-phrase accent captions", "crash-zoom on the punchline".
- **niche_fit:** one sentence on how naturally this visual style maps onto gym/lifestyle content (or why it wouldn't).
