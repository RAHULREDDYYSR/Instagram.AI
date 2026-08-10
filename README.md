# Instagram.AI

> **Personal reel intelligence pipeline** — scrape Instagram Reels, analyze patterns with AI agents, and generate ready-to-shoot scripts from your Brain.

[![Python](https://img.shields.io/badge/Python-3.13-blue?logo=python&logoColor=white)](https://www.python.org/)
[![OpenCode](https://img.shields.io/badge/Powered%20by-OpenCode-000?logo=opencode&logoColor=white)](https://opencode.ai)
[![License](https://img.shields.io/badge/License-Private-red)](./LICENSE)

---

## Overview

Instagram.AI is a local intelligence pipeline that:

- **Scrapes** Instagram Reels from your creator watchlist (via Apify)
- **Ingests** media — downloads video, extracts keyframes + audio (yt-dlp + ffmpeg)
- **Transcribes** audio to text (Whisper API)
- **Analyzes** visual patterns, audio hooks, and retention psychology (AI agents)
- **Distills** patterns into a durable Brain knowledge graph
- **Generates** ready-to-shoot reel scripts adapted to your niche
- **Accepts reels from Telegram** — send links from your phone, process them later

All of this runs locally on your machine. No cloud hosting required (except OpenAI Whisper API for transcription).

---

## Architecture

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': { 'primaryColor': '#1a1a2e', 'primaryTextColor': '#fff', 'primaryBorderColor': '#C0392B', 'lineColor': '#C0392B', 'secondaryColor': '#2D2D44', 'tertiaryColor': '#16213e'}}}%%

flowchart TB
    subgraph INPUT["📥 Input Sources"]
        direction TB
        APIFY["Apify Scraper<br/>System/scrape.py"]
        TELEGRAM["Telegram Chat<br/>/tg command"]
        MANUAL["Manual Ingest<br/>ingest_reel.py"]
    end

    subgraph PIPELINE["⚙️ Processing Pipeline"]
        direction TB
        PROCESS["process_reels.py<br/>Download + Extract + Brain Notes"]
        TRANSCRIBE["transcribe.py<br/>Whisper API → .txt"]
    end

    subgraph AGENTS["🤖 AI Agents"]
        direction TB
        INGESTOR["reel-ingestor<br/>bash: allow | edit: deny"]
        ANALYST["reel-analyst<br/>bash: deny | edit: allow<br/>video-analysis + audio-analysis skills"]
        LIBRARIAN["pattern-librarian<br/>bash: deny | edit: allow<br/>Distills patterns into Brain"]
        DRAFTER["script-drafter<br/>bash: deny | edit: allow<br/>Generates 2-3 script drafts"]
        CRITIC["style-critic<br/>bash: deny | edit: allow<br/>Refines user-pasted scripts"]
        TG_AGENT["telegram-agent<br/>bash: allow | edit: allow<br/>Fetches TG messages, dedup, feed pipeline"]
        PDF_BUILDER["pdf-builder<br/>bash: allow | edit: allow<br/>Generates premium PDFs"]
    end

    subgraph BRAIN["🧠 Brain (Obsidian Wiki)"]
        direction TB
        EXCEL["Reels_Log.xlsx<br/>Spreadsheet of truth"]
        NOTES["Reels/*.md + Branding/*.md<br/>Per-reel notes"]
        ANALYSES["Analyses/<id>_*<br/>visual.json, audio.md, retention.md"]
        PATTERNS["Patterns/*.md<br/>Reusable hook/editing patterns"]
        FRAMEWORKS["Frameworks/<br/>Hook_Database, Script_Framework_Library"]
        SCRIPTS["Scripts/*.md<br/>Generated drafts"]
        PLAYBOOK["Playbook.md, Pattern_Library.md<br/>Trend_Reports.md, My_Style.md"]
    end

    subgraph OUTPUT["📤 Output"]
        direction TB
        PDF["Premium PDFs<br/>draft_result/*.pdf"]
        TG_REPLY["Telegram Reply<br/>PDF sent back to chat"]
    end

    %% Input flows
    APIFY -->|SCRAPED| EXCEL
    TELEGRAM -->|TG_AGENT| EXCEL
    MANUAL -->|SCRAPED| EXCEL

    %% Pipeline flows
    EXCEL -->|Status=SCRAPED| PROCESS
    PROCESS -->|Status=PROCESSED| TRANSCRIBE
    TRANSCRIBE -->|Assets/<id>.txt| ANALYST

    %% Agent flows
    INGESTOR -->|Runs| PROCESS
    INGESTOR -->|Runs| TRANSCRIBE
    TG_AGENT -->|Fetches| TELEGRAM
    TG_AGENT -->|Spawns| INGESTOR

    ANALYST -->|Writes| ANALYSES
    ANALYST -->|Fills| NOTES
    ANALYST -->|Flags novel| LIBRARIAN

    LIBRARIAN -->|Creates/Updates| PATTERNS
    LIBRARIAN -->|Refreshes| FRAMEWORKS
    LIBRARIAN -->|Updates| PLAYBOOK

    DRAFTER -->|Reads| PLAYBOOK
    DRAFTER -->|Reads| PATTERNS
    DRAFTER -->|Writes| SCRIPTS
    DRAFTER -->|Adapts from| ANALYSES

    PDF_BUILDER -->|Reads| SCRIPTS
    PDF_BUILDER -->|Generates| PDF

    CRITIC -->|Reads| PLAYBOOK
    CRITIC -->|Refines| SCRIPTS

    %% Output flows
    PDF -->|Optional| TG_REPLY
    TG_AGENT -->|Sends| TG_REPLY

    %% Styling
    classDef input fill:#16213e,stroke:#C0392B,stroke-width:2px,color:#fff
    classDef pipeline fill:#1a1a2e,stroke:#2D2D44,stroke-width:2px,color:#fff
    classDef agent fill:#2D2D44,stroke:#C0392B,stroke-width:2px,color:#fff
    classDef brain fill:#0f3460,stroke:#e94560,stroke-width:2px,color:#fff
    classDef output fill:#533483,stroke:#e94560,stroke-width:2px,color:#fff

    class APIFY,TELEGRAM,MANUAL input
    class PROCESS,TRANSCRIBE pipeline
    class INGESTOR,ANALYST,LIBRARIAN,DRAFTER,CRITIC,TG_AGENT,PDF_BUILDER agent
    class EXCEL,NOTES,ANALYSES,PATTERNS,FRAMEWORKS,SCRIPTS,PLAYBOOK brain
    class PDF,TG_REPLY output
```

---

## Pipeline

| Step | Command | Effect |
|---|---|---|
| **1. Scrape** | `uv run System/scrape.py --category NICHE\|BRANDING\|ALL [--max-reels N]` | Apify metadata → `Brain/Reels_Log.xlsx`, Status=SCRAPED |
| **2. Process** | `uv run System/process_reels.py [--shortcode <id>] [--shortcodes <id> ...] [--limit N] [--checkpoint-every N]` | Downloads + validates/extracts media, creates Brain note, Status=PROCESSED after scoped transcription |
| **3. Transcribe** | `uv run System/transcribe.py [--shortcode <id>] [--shortcodes <id> ...]` | Whisper → `Assets/<id>.txt` (auto-chains for exact processed IDs) |
| **4. Analyze** | `/analyze` command (opencode) | Spawns `reel-analyst` agents → writes `Brain/Analyses/<id>_*` |
| **5. Mark** | `uv run System/mark_analyzed.py [--shortcodes <id> ...]` | Valid analysis trios → Status=ANALYZED |
| **6. Distill** | `/sync` or spawn `pattern-librarian` | Patterns → `Brain/Patterns/`, `Playbook.md`, etc. |
| **7. Draft** | `/draft <topic>` or `/redraft <reel_url>` | `script-drafter` → `Brain/Scripts/<Title>.md` |
| **8. PDF** | `/draft` (auto) or spawn `pdf-builder` | Scripts → `draft_result/<Topic>.pdf` |

**Status lifecycle:** `SCRAPED → PROCESSED → ANALYZED`

For a registered one-off reel, run `uv run System/register_oneoff.py <url>`
then `uv run System/process_reels.py --shortcode <id>`. This keeps the reel in
the Excel lifecycle and makes it eligible for guarded cleanup. Use
`System/ingest_reel.py` only as the raw asset utility.

Performance snapshots are append-only via
`uv run System/record_outcome.py --shortcode <id> ...` and are stored under
`Brain/Outcomes/` for later score calibration.

---

## Telegram Integration

Send Instagram reel links from your phone to your Telegram bot. Process them later via `/tg`.

```mermaid
%%{init: {'theme': 'dark'}}%%

sequenceDiagram
    participant U as 👤 You (Phone)
    participant TG as 📱 Telegram Bot
    participant OC as 💻 OpenCode (/tg)
    participant PL as ⚙️ Pipeline
    participant AI as 🤖 AI Agents
    participant BR as 🧠 Brain

    U->>TG: Send reel link
    TG-->>U: "Reel saved: ABC123"
    
    Note over U,TG: Later...
    
    U->>OC: /tg
    OC->>TG: getUpdates (fetch messages)
    TG-->>OC: 3 new reels found
    
    OC->>OC: Dedup by shortcode
    OC->>OC: Detect draft intent
    OC-->>U: "Found 3 reels. 1 has draft request. Process?"
    
    U->>OC: Yes, process all
    
    OC->>PL: process_reels.py --shortcode ABC123
    PL->>BR: Update Excel (Status=PROCESSED)
    
    OC->>AI: Spawn reel-analyst (×3 parallel)
    AI->>BR: Write Analyses/<id>_*
    AI->>BR: Update Patterns
    
    OC->>PL: mark_analyzed.py
    PL->>BR: Status=ANALYZED
    
    Note over OC,BR: If draft requested...
    
    OC->>AI: Spawn script-drafter
    AI->>BR: Write Scripts/*.md
    
    OC->>AI: Spawn pdf-builder
    AI->>OC: draft_result/Scripts.pdf
    
    OC->>TG: sendDocument (PDF)
    TG-->>U: 📄 Scripts.pdf
```

### How it works

1. **Send links** — Text your Telegram bot with Instagram reel URLs
2. **Fetch** — Run `/tg` in opencode. The `telegram-agent` fetches messages, extracts URLs, deduplicates by shortcode
3. **Present** — Agent shows you what it found and asks what to do
4. **Process** — Reels enter the **same pipeline** as Apify-scraped reels (no separate path)
5. **Draft** — If a message said "draft 2 scripts based on this", scripts are generated after analysis
6. **Deliver** — PDFs are sent back to your Telegram chat

### Setup

```bash
# 1. Create a Telegram bot via @BotFather, get the token
# 2. Add to .env
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_ALLOWED_CHAT_ID=your_chat_id

# 3. Send a test message to your bot, then fetch it
uv run telegram_bot/fetch_messages.py --dry-run
```

---

## Agent System

| Agent | Permissions | Role |
|---|---|---|
| `reel-ingestor` | bash ✓ | Runs pipeline scripts (scrape, process, transcribe, mark, cleanup) |
| `reel-analyst` | edit ✓ | Analyzes keyframes + transcript, writes `Brain/Analyses/<id>_*` |
| `pattern-librarian` | edit ✓ | Distills patterns into `Brain/Patterns/`, updates Playbook |
| `script-drafter` | edit ✓ | Generates 2-3 reel script drafts using Brain knowledge |
| `style-critic` | edit ✓ | Refines user-pasted scripts against rubric + My_Style |
| `telegram-agent` | bash ✓ edit ✓ | Fetches Telegram messages, deduplicates, feeds pipeline |
| `pdf-builder` | bash ✓ edit ✓ | Builds premium magazine-style PDFs from scripts |

### Commands

| Command | Description |
|---|---|
| `/sync [NICHE\|BRANDING\|ALL]` | Full pipeline: scrape → process → analyze → distill |
| `/analyze [shortcode\|pending]` | Parallel analysis of unanalyzed reels |
| `/draft <topic>` | Generate 2-3 script drafts from the Brain |
| `/redraft <reel_url>` | Ingest → analyze → 2-3 niche-adapted redrafts |
| `/refine <script>` | Critique + refined draft vs rubric & My_Style |
| `/tg [--dry-run]` | Fetch reel links from Telegram, feed into pipeline |

---

## Brain Structure

```
Brain/
├── Reels_Log.xlsx          # Spreadsheet of truth (deduped by shortcode)
├── Reels/                  # NICHE reel notes (per-shortcode .md)
├── Branding/               # BRANDING reel notes (per-shortcode .md)
├── Analyses/               # Agent outputs (visual.json, audio.md, retention.md)
├── Creators/               # _registry.json — processed shortcodes per creator
├── Patterns/               # Reusable hook/editing patterns (wiki-linked)
├── Frameworks/             # Hook_Database.md, Script_Framework_Library.md
├── Scripts/                # Generated script drafts
├── Playbook.md             # Aggregated playbook
├── Pattern_Library.md      # Pattern index with confidence scores
├── Trend_Reports.md        # Trend observations (2+ reels required)
├── My_Style.md             # Your personal style rules (edited by style-critic)
└── Rubric.md               # FIXED scoring rubric (never edited)
```

All notes use **Obsidian wiki-links** `[[Node Name]]` for cross-referencing.

---

## Setup

### Prerequisites

- **Python 3.13** (pinned in `.python-version`)
- **uv** (Python package manager) — [install](https://docs.astral.sh/uv/getting-started/installation/)
- **ffmpeg** on `PATH` (for audio extraction)
- **OpenCode** — [install](https://opencode.ai)
- **APIFY_API_KEY** — [get one](https://apify.com/)
- **OPENAI_API_KEY** — [get one](https://platform.openai.com/)

### Installation

```bash
# Clone the repo
git clone https://github.com/RAHULREDDYYSR/Instagram.AI.git
cd Instagram.AI

# Install dependencies
uv sync

# Set up environment
cp .env.example .env
# Edit .env with your API keys

# Verify ffmpeg
ffmpeg -version
```

### First Run

```bash
# 1. Scrape creators (edit System/creators.json first)
uv run System/scrape.py --category NICHE --max-reels 5

# 2. Process reels (download + extract + transcribe)
uv run System/process_reels.py --category NICHE --limit 5

# 3. Analyze in opencode
# Open opencode and run: /analyze

# 4. Distill patterns
# In opencode: spawn pattern-librarian

# 5. Generate scripts
# In opencode: /draft "discipline over motivation"
```

---

## Configuration

### `System/creators.json`

Edit this file to add/remove creators from your watchlist:

```json
{
  "creators": [
    {
      "username": "creator_handle",
      "category": "NICHE",
      "scraped_reels": [],
      "processed_reels": []
    }
  ]
}
```

### `.env`

| Variable | Required | Description |
|---|---|---|
| `APIFY_API_KEY` | Yes | Apify API key for scraping |
| `OPENAI_API_KEY` | Yes | OpenAI key for Whisper transcription |
| `TELEGRAM_BOT_TOKEN` | Optional | Telegram bot token (for `/tg` command) |
| `TELEGRAM_ALLOWED_CHAT_ID` | Optional | Your chat ID (whitelist) |

---

## Tech Stack

| Component | Technology |
|---|---|
| **Scraping** | [Apify](https://apify.com/) + custom actors |
| **Video Download** | [yt-dlp](https://github.com/yt-dlp/yt-dlp) |
| **Audio Extraction** | [ffmpeg](https://ffmpeg.org/) |
| **Transcription** | [OpenAI Whisper API](https://platform.openai.com/docs/guides/speech-to-text) |
| **AI Agents** | [OpenCode](https://opencode.ai) subagents |
| **Brain** | Obsidian-flavored markdown with wiki-links |
| **Excel** | [pandas](https://pandas.pydata.org/) + [openpyxl](https://openpyxl.readthedocs.io/) |
| **PDF Generation** | [ReportLab](https://www.reportlab.com/) |
| **Telegram** | Bot API via `requests` (no long-polling) |

---

## Project Structure

```
Instagram.AI/
├── System/                 # Pipeline scripts
│   ├── scrape.py           # Apify scraper
│   ├── process_reels.py    # Download + extract + Brain notes
│   ├── transcribe.py       # Whisper transcription
│   ├── ingest_reel.py      # One-off reel download
│   ├── mark_analyzed.py    # Flip Status=ANALYZED
│   ├── cleanup_assets.py   # Delete media for ANALYZED reels
│   └── creators.json       # Creator watchlist
├── telegram_bot/           # Telegram integration
│   ├── fetch_messages.py   # One-shot getUpdates
│   ├── send_file.py        # Send PDFs to Telegram
│   ├── store.py            # JSON tracker + Excel sync
│   └── config.py           # Env loader
├── Brain/                  # Knowledge base (gitignored)
├── Assets/                 # Downloaded media (gitignored)
├── .opencode/              # Agent definitions + commands
├── .agents/                # Skills + agent docs
├── AGENTS.md               # Supervisor rules
└── pyproject.toml          # Python dependencies
```

---

## Contributing

This is a private project. If you're reading this, you're either:
- Me (hi 👋)
- Someone I shared this with (thanks for looking!)

---

## License

Private — not for redistribution.

---

<div align="center">

**Built with [OpenCode](https://opencode.ai) · Powered by curiosity**

</div>
