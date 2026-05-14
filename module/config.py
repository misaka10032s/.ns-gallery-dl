# -- config.py --

import os
from dotenv import load_dotenv

load_dotenv()

# File Paths
HISTORY_FILE = "data/history.json"
TOKEN_FILE = "data/token.json"
INPUT_FILE = "dl.txt"
DOWNLOAD_DIR = "download"

# Download Settings
MAX_RETRIES = 10
RETRY_DELAY = 5  # seconds
DL_DELAY = 5  # seconds
MAX_DOWNLOAD_THREADS = 5

# Discord Bot
DISCORD_BOT_TOKEN: str = os.environ.get("DISCORD_BOT_TOKEN", "")
DISCORD_CHANNEL_IDS: set[int] = {
    int(x.strip())
    for x in os.environ.get("DISCORD_CHANNEL_IDS", "").split(",")
    if x.strip().isdigit()
}

# Discord Bot Reaction Emojis
# Unicode emoji or custom emoji in <:name:id> / <a:name:id> format.
# If the custom emoji is unavailable (no permission), the bot falls back to the defaults.
DISCORD_EMOJI_QUEUED: str = os.environ.get("DISCORD_EMOJI_QUEUED", "⏳")
DISCORD_EMOJI_DONE:   str = os.environ.get("DISCORD_EMOJI_DONE",   "✅")
DISCORD_EMOJI_FAILED: str = os.environ.get("DISCORD_EMOJI_FAILED", "❌")
