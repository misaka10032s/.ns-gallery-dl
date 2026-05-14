# module/bot/dc.py
# Discord bot: monitors specified channels and auto-downloads images / gallery-dl URLs.

import re
import asyncio
import aiohttp
import discord
from pathlib import Path
from urllib.parse import urlparse, unquote
from concurrent.futures import ThreadPoolExecutor

from ..fetch import try_download
from ..history import add_to_history, filter_by_history
from ..downloader import add_to_display, remove_from_display
from ..config import (
    DOWNLOAD_DIR,
    DISCORD_BOT_TOKEN, DISCORD_CHANNEL_IDS,
    DISCORD_EMOJI_QUEUED, DISCORD_EMOJI_DONE, DISCORD_EMOJI_FAILED,
)

IMAGE_CONTENT_TYPES = {
    "image/jpeg", "image/png", "image/gif",
    "image/webp", "image/bmp", "image/tiff",
}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff"}

URL_PATTERN = re.compile(r"https?://[^\s<>\"']+")

GALLERYDL_DOMAINS = {
    # Social / art platforms
    "pixiv.net", "x.com", "twitter.com",
    "bsky.app",
    "instagram.com", "tumblr.com", "reddit.com",
    "deviantart.com", "artstation.com",
    "flickr.com", "imgur.com",
    "pinterest.com", "pinterest.co.uk", "pin.it",
    # Creator / fan platforms
    "fanbox.cc", "patreon.com", "skeb.jp",
    "civitai.com",
    # Booru / image boards
    "danbooru.donmai.us", "gelbooru.com", "konachan.com", "yande.re",
    "sankaku.app",
    # Archives
    "kemono.cr", "coomer.st",
    # Misc
    "nhentai.net", "wnacg.com",
    "art.ngfiles.com",
}

# Unicode fallbacks used when a custom emoji permission check fails
_FB_QUEUED = "⏳"
_FB_DONE   = "✅"
_FB_FAILED = "❌"

_executor = ThreadPoolExecutor(max_workers=3)

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


# ── emoji helpers ─────────────────────────────────────────────────────────────

def _parse_emoji(s: str) -> discord.PartialEmoji | str:
    """
    Parse a config emoji string.
    - '<:name:id>'  → PartialEmoji (static custom)
    - '<a:name:id>' → PartialEmoji (animated custom)
    - anything else → unicode string (used as-is)
    """
    m = re.fullmatch(r"<(a?):(\w+):(\d+)>", s.strip())
    if m:
        return discord.PartialEmoji(
            animated=(m.group(1) == "a"),
            name=m.group(2),
            id=int(m.group(3)),
        )
    return s


async def _react(message: discord.Message, cfg: str, fallback: str) -> None:
    """Add a reaction; on Forbidden / HTTPException fall back to the unicode default."""
    try:
        await message.add_reaction(_parse_emoji(cfg))
    except (discord.Forbidden, discord.HTTPException):
        try:
            await message.add_reaction(fallback)
        except Exception as e:
            print(f"[Bot] Could not add reaction '{fallback}': {e}")


async def _unreact(message: discord.Message, cfg: str, fallback: str) -> None:
    """Remove the bot's own reaction (silently ignored if missing or no permission)."""
    for emoji in (_parse_emoji(cfg), fallback):
        try:
            await message.remove_reaction(emoji, client.user)
            return
        except Exception:
            continue


# ── file / url helpers ────────────────────────────────────────────────────────

def _is_gallerydl_url(url: str) -> bool:
    url_lower = url.lower()
    return any(domain in url_lower for domain in GALLERYDL_DOMAINS)


def _url_to_filename(url: str) -> str:
    path = urlparse(url).path
    name = unquote(Path(path).name)
    return name if (name and "." in name) else "image.jpg"


def _channel_dir_name(channel) -> str:
    """Return a filesystem-safe name for a Discord channel."""
    name = getattr(channel, "name", None) or str(getattr(channel, "id", "unknown"))
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip("_ ") or str(getattr(channel, "id", "unknown"))


def _make_save_path(filename: str, channel_name: str = "unknown") -> Path:
    save_dir = Path(DOWNLOAD_DIR) / "discord" / channel_name
    save_dir.mkdir(parents=True, exist_ok=True)
    stem, suffix = Path(filename).stem, Path(filename).suffix or ".jpg"
    path = save_dir / f"{stem}{suffix}"
    counter = 1
    while path.exists():
        path = save_dir / f"{stem}_{counter}{suffix}"
        counter += 1
    return path


# ── download coroutines (each returns True = ok, False = failed) ──────────────

async def _save_attachment(attachment: discord.Attachment, channel_name: str) -> bool:
    add_to_display(attachment.url)
    save_path = _make_save_path(attachment.filename, channel_name)
    try:
        await attachment.save(save_path)
        print(f"[Bot] Saved attachment: {save_path}")
        return True
    except Exception as e:
        print(f"[Bot] Failed to save attachment {attachment.filename}: {e}")
        return False
    finally:
        remove_from_display(attachment.url)


async def _download_embed_image(url: str, channel_name: str) -> bool:
    add_to_display(url)
    save_path = _make_save_path(_url_to_filename(url), channel_name)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                resp.raise_for_status()
                with open(save_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(8192):
                        f.write(chunk)
        print(f"[Bot] Saved embed image: {save_path}")
        return True
    except Exception as e:
        print(f"[Bot] Failed to download embed image {url}: {e}")
        return False
    finally:
        remove_from_display(url)


async def _download_url(url: str) -> bool:
    if not filter_by_history([url]):
        print(f"[Bot] Skipping (already downloaded): {url}")
        return True  # already done — not a failure
    add_to_display(url)
    print(f"[Bot] Downloading via gallery-dl: {url}")
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(_executor, try_download, url)
        add_to_history([{"url": url, "result": result}])
        print(f"[Bot] Result for {url}: {result}")
        return result == "success"
    finally:
        remove_from_display(url)


# ── processing + reaction coordinator ────────────────────────────────────────

def _get_embed_image_url(embed: discord.Embed) -> str | None:
    if embed.type == "image" and embed.url:
        return embed.url
    if embed.image and embed.image.url:
        return embed.image.url
    if embed.thumbnail and embed.thumbnail.url:
        return embed.thumbnail.url
    return None




async def _collect_coros(
    message: discord.Message,
    before: discord.Message | None = None,
) -> list:
    """
    Build the list of download coroutines for a message.
    - before=None  → new message: process attachments, content URLs, and type="image" embeds
    - before set   → edited message: handle only newly added type="image" embeds
    - message_snapshots (forwarded messages): attachments + gallery-dl URLs only;
      embeds inside snapshots are link-previews from the original message and are skipped.
    """
    coros = []
    is_new = before is None
    channel_name = _channel_dir_name(message.channel)

    if is_new:
        # Direct image attachments on the message itself
        for attachment in message.attachments:
            ct = (attachment.content_type or "").split(";")[0].strip()
            if ct in IMAGE_CONTENT_TYPES or Path(attachment.filename).suffix.lower() in IMAGE_EXTENSIONS:
                coros.append(_save_attachment(attachment, channel_name))
        # Gallery-dl URLs in message text
        for url in URL_PATTERN.findall(message.content or ""):
            if _is_gallerydl_url(url):
                coros.append(_download_url(url))
        # Forwarded snapshots: attachments + gallery-dl content URLs only (no link-preview embeds)
        for snapshot in getattr(message, "message_snapshots", []):
            for attachment in snapshot.attachments:
                ct = (attachment.content_type or "").split(";")[0].strip()
                if ct in IMAGE_CONTENT_TYPES or Path(attachment.filename).suffix.lower() in IMAGE_EXTENSIONS:
                    coros.append(_save_attachment(attachment, channel_name))
            for url in URL_PATTERN.findall(snapshot.content or ""):
                if _is_gallerydl_url(url):
                    coros.append(_download_url(url))

    # Embedded images on the message itself: only type="image" (direct image URL, not link previews)
    seen_embed_urls: set[str] = {e.url for e in before.embeds if e.url} if before else set()
    for embed in message.embeds:
        if embed.type != "image":
            continue
        if embed.url and embed.url in seen_embed_urls:
            continue
        img_url = _get_embed_image_url(embed)
        if not img_url:
            continue
        source = embed.url or img_url
        if _is_gallerydl_url(source):
            if is_new:
                coros.append(_download_url(source))
        else:
            coros.append(_download_embed_image(img_url, channel_name))

    return coros


async def _process_and_react(message: discord.Message, coros: list) -> None:
    """
    Run all download coroutines, then update the message reaction:
      ⏳ while running  →  ✅ all ok  |  ❌ all failed  |  ✅❌ partial
    """
    await _react(message, DISCORD_EMOJI_QUEUED, _FB_QUEUED)

    results = await asyncio.gather(*coros, return_exceptions=True)

    ok     = sum(1 for r in results if r is True)
    failed = len(results) - ok

    await _unreact(message, DISCORD_EMOJI_QUEUED, _FB_QUEUED)
    if failed == 0:
        await _react(message, DISCORD_EMOJI_DONE, _FB_DONE)
    elif ok == 0:
        await _react(message, DISCORD_EMOJI_FAILED, _FB_FAILED)
    else:  # partial success — show both
        await _react(message, DISCORD_EMOJI_DONE,   _FB_DONE)
        await _react(message, DISCORD_EMOJI_FAILED, _FB_FAILED)


def _emoji_matches(reaction_emoji, cfg: str, fallback: str) -> bool:
    """Check if a reaction emoji matches a configured (custom or unicode) emoji."""
    parsed = _parse_emoji(cfg)
    if isinstance(parsed, discord.PartialEmoji) and hasattr(reaction_emoji, "id"):
        if reaction_emoji.id == parsed.id:
            return True
    return str(reaction_emoji) == fallback


def _already_processed(message: discord.Message) -> bool:
    """
    Return True if this message already has a result reaction (✅ or ❌) from the bot.
    Messages with only ⏳ (bot was killed mid-download) are NOT considered processed
    and will be re-queued.
    """
    for reaction in message.reactions:
        if reaction.me and (
            _emoji_matches(reaction.emoji, DISCORD_EMOJI_DONE,   _FB_DONE) or
            _emoji_matches(reaction.emoji, DISCORD_EMOJI_FAILED, _FB_FAILED)
        ):
            return True
    return False


async def _cmd_download_channel(trigger: discord.Message) -> None:
    """
    Handle the $d / $download command.
    Scans the last 1000 messages, skips already-reacted ones, downloads
    images + gallery-dl URLs, and reacts to each processed message individually.
    """
    channel = trigger.channel
    channel_name = _channel_dir_name(channel)
    print(f"[Bot] $download triggered in #{channel_name} — scanning history (limit=1000)...")

    await _react(trigger, DISCORD_EMOJI_QUEUED, _FB_QUEUED)

    # Collect (message, [coros]) for every unprocessed message that has work to do
    msg_tasks: list[tuple[discord.Message, list]] = []
    seen_direct: set[str] = set()

    async for msg in channel.history(limit=1000, oldest_first=True):
        if msg.author == client.user or msg.id == trigger.id:
            continue
        if _already_processed(msg):
            continue

        coros: list = []
        # Main message: attachments + gallery-dl URLs + type="image" embeds
        for attachment in msg.attachments:
            ct = (attachment.content_type or "").split(";")[0].strip()
            if ct in IMAGE_CONTENT_TYPES or Path(attachment.filename).suffix.lower() in IMAGE_EXTENSIONS:
                coros.append(_save_attachment(attachment, channel_name))
        for url in URL_PATTERN.findall(msg.content or ""):
            if _is_gallerydl_url(url) and url not in seen_direct:
                seen_direct.add(url)
                coros.append(_download_url(url))
        for embed in msg.embeds:
            if embed.type != "image":
                continue
            img_url = _get_embed_image_url(embed)
            if not img_url:
                continue
            source = embed.url or img_url
            if _is_gallerydl_url(source):
                if source not in seen_direct:
                    seen_direct.add(source)
                    coros.append(_download_url(source))
            elif img_url not in seen_direct:
                seen_direct.add(img_url)
                coros.append(_download_embed_image(img_url, channel_name))
        # Forwarded snapshots: attachments + gallery-dl URLs only (no link-preview embeds)
        for snapshot in getattr(msg, "message_snapshots", []):
            for attachment in snapshot.attachments:
                ct = (attachment.content_type or "").split(";")[0].strip()
                if ct in IMAGE_CONTENT_TYPES or Path(attachment.filename).suffix.lower() in IMAGE_EXTENSIONS:
                    coros.append(_save_attachment(attachment, channel_name))
            for url in URL_PATTERN.findall(snapshot.content or ""):
                if _is_gallerydl_url(url) and url not in seen_direct:
                    seen_direct.add(url)
                    coros.append(_download_url(url))

        if coros:
            msg_tasks.append((msg, coros))

    print(f"[Bot] $download: {len(msg_tasks)} unprocessed message(s) in #{channel_name}")

    if not msg_tasks:
        await _unreact(trigger, DISCORD_EMOJI_QUEUED, _FB_QUEUED)
        await _react(trigger, DISCORD_EMOJI_DONE, _FB_DONE)
        return

    total_ok = total_failed = 0
    for msg, coros in msg_tasks:
        await _react(msg, DISCORD_EMOJI_QUEUED, _FB_QUEUED)
        results = await asyncio.gather(*coros, return_exceptions=True)
        ok     = sum(1 for r in results if r is True)
        failed = len(results) - ok
        total_ok     += ok
        total_failed += failed

        await _unreact(msg, DISCORD_EMOJI_QUEUED, _FB_QUEUED)
        if failed == 0:
            await _react(msg, DISCORD_EMOJI_DONE, _FB_DONE)
        elif ok == 0:
            await _react(msg, DISCORD_EMOJI_FAILED, _FB_FAILED)
        else:
            await _react(msg, DISCORD_EMOJI_DONE,   _FB_DONE)
            await _react(msg, DISCORD_EMOJI_FAILED, _FB_FAILED)

    print(f"[Bot] $download #{channel_name}: {total_ok} ok, {total_failed} failed across {len(msg_tasks)} message(s)")

    await _unreact(trigger, DISCORD_EMOJI_QUEUED, _FB_QUEUED)
    if total_failed == 0:
        await _react(trigger, DISCORD_EMOJI_DONE, _FB_DONE)
    elif total_ok == 0:
        await _react(trigger, DISCORD_EMOJI_FAILED, _FB_FAILED)
    else:
        await _react(trigger, DISCORD_EMOJI_DONE,   _FB_DONE)
        await _react(trigger, DISCORD_EMOJI_FAILED, _FB_FAILED)


# ── Discord events ────────────────────────────────────────────────────────────

@client.event
async def on_ready() -> None:
    print(f"[Bot] Logged in as {client.user} (ID: {client.user.id})")
    if DISCORD_CHANNEL_IDS:
        print(f"[Bot] Monitoring {len(DISCORD_CHANNEL_IDS)} channel(s): {sorted(DISCORD_CHANNEL_IDS)}")
    else:
        print("[Bot] Warning: DISCORD_CHANNEL_IDS is not set — no channels are being monitored.")


@client.event
async def on_message(message: discord.Message) -> None:
    if not DISCORD_CHANNEL_IDS or message.channel.id not in DISCORD_CHANNEL_IDS:
        return
    if message.author == client.user:
        return

    # ── text commands ─────────────────────────────────────────────────────────
    cmd = message.content.strip().lower()
    if cmd in ("$d", "$download"):
        asyncio.create_task(_cmd_download_channel(message))
        return

    # ── normal auto-download ──────────────────────────────────────────────────
    coros = await _collect_coros(message)
    if coros:
        asyncio.create_task(_process_and_react(message, coros))


@client.event
async def on_message_edit(before: discord.Message, after: discord.Message) -> None:
    """Catch embed images that Discord appends to messages asynchronously."""
    if not DISCORD_CHANNEL_IDS or after.channel.id not in DISCORD_CHANNEL_IDS:
        return
    if after.author == client.user:
        return
    if len(after.embeds) <= len(before.embeds):
        return
    coros = await _collect_coros(after, before=before)
    if coros:
        asyncio.create_task(_process_and_react(after, coros))


# ── entry point ───────────────────────────────────────────────────────────────

def run() -> None:
    if not DISCORD_BOT_TOKEN:
        print("[Bot] Error: DISCORD_BOT_TOKEN is not set. Add it to your .env file.")
        return
    if not DISCORD_CHANNEL_IDS:
        print("[Bot] Warning: DISCORD_CHANNEL_IDS is not set. The bot will run but won't monitor any channels.")
    print("[Bot] Starting Discord bot... (Ctrl+C to stop)")
    client.run(DISCORD_BOT_TOKEN)

