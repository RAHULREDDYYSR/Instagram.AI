# Instagram.AI

Instagram.AI is a local intelligence pipeline for Instagram Reels. It scrapes
creator metadata, downloads and extracts reel assets, transcribes audio,
analyzes visual and retention patterns, and generates ready-to-shoot scripts
from the Brain.

## Telegram Control

The local Telegram bot exposes the existing OpenCode workflow from a private
Telegram chat. It uses long polling, so the Windows machine running the bot
must remain online. No public webhook or inbound port is required.

### Setup

1. Install the project dependencies:

   ```powershell
   uv sync
   ```

2. Install OpenCode and verify it is available:

   ```powershell
   npm install -g opencode-ai
   opencode --version
   ```

   OpenCode can also be installed through WSL, Chocolatey, Scoop, or its
   official installer. Keep the bot and this repository in the same runtime
   environment.

3. Create a bot with BotFather and copy the token into `.env`.

4. Copy `.env.example` to `.env`, then fill in the provider credentials and
   at least one Telegram allowlist value:

   ```dotenv
   TELEGRAM_BOT_TOKEN=your_bot_token
   TELEGRAM_ALLOWED_CHAT_ID=your_private_chat_id
   TELEGRAM_ALLOWED_USER_ID=your_telegram_user_id
   ```

   Use `@userinfobot` to find the Telegram user/chat ID. Never commit `.env`.

5. Authenticate OpenCode with the provider used by the project, then start
   the bot from the repository root:

   ```powershell
   uv run System/telegram_bot.py
   ```

   The bot starts or reuses an OpenCode server on `127.0.0.1:4096`.

### Commands

| Telegram command | Action |
|---|---|
| `/draft <topic>` | Generate script drafts and deliver Markdown/PDF outputs. |
| `/redraft <Instagram URL>` | Ingest, analyze, and adapt a source reel. |
| `/refine <script>` | Run the style critic against pasted script text. |
| Upload `.md`/`.txt`, then `/refine` | Refine an uploaded script file. |
| `/analyze [pending\|shortcode]` | Analyze one reel or pending reels. |
| `/sync [NICHE\|BRANDING\|ALL] [--max-reels N]` | Run the full pipeline after confirmation. |
| `/status` | Read the current spreadsheet and asset status. |
| `/cleanup` | Preview eligible media and require confirmation before deletion. |
| `/cancel` | Request cancellation of the active workflow. |

Natural-language aliases such as `draft a reel about discipline` are accepted
for the supported actions. Unknown messages are not passed to a shell or an
unrestricted agent.

### Safety Notes

- Only the configured Telegram chat/user can invoke workflows.
- Pipeline jobs are serialized because they write shared Excel and Brain files.
- User input is validated and passed as subprocess arguments, never as shell
  source.
- Generated scripts and PDFs are delivered as Telegram documents. Raw media is
  not uploaded automatically.
- `/cleanup` always runs a dry-run first and needs an explicit button press.
- The existing OpenCode Telegram MCP remains available for outbound messages,
  but it must not call `getUpdates` while this bot is running because the bot
  owns the long-polling update stream.
