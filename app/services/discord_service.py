from __future__ import annotations

import asyncio
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
import discord

from app.config.settings import (
    DISCORD_BOT_TOKEN,
    DISCORD_CHANNEL_IDS,
    DISCORD_EMOJI_DONE,
    DISCORD_EMOJI_FAILED,
    DISCORD_EMOJI_QUEUED,
    GALLERY_DL_DOMAINS,
    YTDLP_DOMAINS,
    host_matches,
    is_domain_allowed,
    normalize_domain,
)
from app.domain.enums import JobSource, JobStatus, Provider
from app.domain.jobs import JobRequest
from app.services import download_service, history_service, queue_service
from app.services.path_service import discord_root, file_name_from_url, unique_file_path
from app.services.token_service import load_tokens
from app.storage.repositories import jobs_repo


IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/bmp", "image/tiff"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff"}
URL_PATTERN = re.compile(r"(?:https?://)?(?:www\.)?[a-z0-9.-]+\.[a-z]{2,}[^\s<>\"']*", re.IGNORECASE)
URL_LIKE_PATTERN = re.compile(r"^(?:[a-z][a-z0-9+.-]*://|(?:www\.)?[a-z0-9.-]+\.[a-z]{2,})(?:[/?#].*)?$", re.IGNORECASE)

_FB_QUEUED = "⏳"
_FB_DONE = "✅"
_FB_FAILED = "❌"
_EXECUTOR = ThreadPoolExecutor(max_workers=3)

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


def _parse_emoji(value: str) -> discord.PartialEmoji | str:
    match = re.fullmatch(r"<(a?):(\w+):(\d+)>", value.strip())
    if not match:
        return value
    return discord.PartialEmoji(animated=match.group(1) == "a", name=match.group(2), id=int(match.group(3)))


async def _react(message: discord.Message, cfg: str, fallback: str) -> None:
    try:
        await message.add_reaction(_parse_emoji(cfg))
    except (discord.Forbidden, discord.HTTPException):
        try:
            await message.add_reaction(fallback)
        except Exception:
            return


async def _unreact(message: discord.Message, cfg: str, fallback: str) -> None:
    for emoji in (_parse_emoji(cfg), fallback):
        try:
            await message.remove_reaction(emoji, client.user)
            return
        except Exception:
            continue


def _guild_name(channel) -> str:
    guild = getattr(channel, "guild", None)
    return getattr(guild, "name", None) or "unknown-guild"


def _is_supported_url(url: str) -> bool:
    try:
        url = download_service.normalize_url(url)
    except ValueError:
        return False
    host = normalize_domain(urlparse(url).hostname)
    if not host or not is_domain_allowed(host):
        return False
    return host_matches(host, GALLERY_DL_DOMAINS) or host_matches(host, YTDLP_DOMAINS)


def _normalize_message_url(raw_url: str) -> str | None:
    candidate = (raw_url or "").strip().strip("<>[](){}\"'`")
    candidate = candidate.rstrip(".,!?;:")
    if not candidate:
        return None
    expanded = download_service.expand_url_shortcut(candidate)
    if expanded:
        return expanded
    if not URL_LIKE_PATTERN.fullmatch(candidate):
        return None
    try:
        return download_service.normalize_url(candidate)
    except ValueError:
        return None


def _extract_urls(text: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for match in URL_PATTERN.findall(text or ""):
        url = _normalize_message_url(match)
        if not url or url in seen:
            continue
        seen.add(url)
        urls.append(url)
    for token in re.split(r"[\s,\u3000\t\r\n]+", text or ""):
        shortcut = download_service.expand_url_shortcut(token.strip().strip("<>[](){}\"'`").rstrip(".,!?;:"))
        if not shortcut or shortcut in seen:
            continue
        seen.add(shortcut)
        urls.append(shortcut)
    return urls


def _save_direct_history(url: str, download_path: str, kind: str, guild_name: str | None = None) -> None:
    history_service.add_to_history(
        [
            {
                "url": url,
                "result": JobStatus.SUCCESS.value,
                "source": JobSource.BOT.value,
                "provider": Provider.DIRECT_FILE.value,
                "download_path": download_path,
                "meta": {"kind": kind, "guild": guild_name} if guild_name else {"kind": kind},
            }
        ]
    )


def _create_bot_job(url: str, provider: Provider, meta: dict) -> int:
    job_id = jobs_repo.create_job(url=url, provider=provider.value, source=JobSource.BOT.value, meta=meta)
    jobs_repo.update_job(job_id, JobStatus.RUNNING.value, meta=meta)
    return job_id


async def _save_attachment(attachment: discord.Attachment, guild_name: str) -> bool:
    root = discord_root(guild_name, "attachments")
    path = unique_file_path(root, attachment.filename)
    meta = {"kind": "attachment", "guild": guild_name, "filename": attachment.filename}
    job_id = _create_bot_job(attachment.url, Provider.DIRECT_FILE, meta)
    queue_service.add_to_display(attachment.url)
    try:
        await attachment.save(path)
        jobs_repo.update_job(job_id, JobStatus.SUCCESS.value, download_path=str(path), meta=meta)
        _save_direct_history(attachment.url, str(path), "attachment", guild_name)
        return True
    except Exception as exc:
        jobs_repo.update_job(job_id, JobStatus.FAILED.value, download_path=str(path), error=str(exc), meta=meta)
        print(f"[Bot] Failed to save attachment {attachment.filename}: {exc}")
        return False
    finally:
        queue_service.remove_from_display(attachment.url)


async def _download_embed_image(url: str, guild_name: str) -> bool:
    root = discord_root(guild_name, "embeds")
    path = unique_file_path(root, file_name_from_url(url, "image.jpg"))
    meta = {"kind": "embed", "guild": guild_name}
    job_id = _create_bot_job(url, Provider.DIRECT_FILE, meta)
    queue_service.add_to_display(url)
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                response.raise_for_status()
                with path.open("wb") as handle:
                    async for chunk in response.content.iter_chunked(8192):
                        handle.write(chunk)
        jobs_repo.update_job(job_id, JobStatus.SUCCESS.value, download_path=str(path), meta=meta)
        _save_direct_history(url, str(path), "embed", guild_name)
        return True
    except Exception as exc:
        jobs_repo.update_job(job_id, JobStatus.FAILED.value, download_path=str(path), error=str(exc), meta=meta)
        print(f"[Bot] Failed to download embed image {url}: {exc}")
        return False
    finally:
        queue_service.remove_from_display(url)


def _run_download_url(url: str) -> bool:
    provider = download_service.classify_provider(url)
    meta = {"kind": "url", "provider_mode": "auto"}
    job_id = jobs_repo.create_job(url=url, provider=provider.value, source=JobSource.BOT.value, meta=meta)
    if not history_service.filter_by_history([url]):
        jobs_repo.update_job(job_id, JobStatus.SKIPPED.value, meta={**meta, "reason": "history"})
        return True
    jobs_repo.update_job(job_id, JobStatus.RUNNING.value, meta=meta)
    result = download_service.download_request(JobRequest(url=url, source=JobSource.BOT, metadata=meta), load_tokens())
    jobs_repo.update_job(
        job_id,
        result.status.value,
        download_path=result.download_path,
        error=result.error,
        meta=result.metadata or meta,
        provider=result.provider.value,
    )
    history_service.add_to_history([download_service.history_payload(url, JobSource.BOT, result)])
    return result.status in {JobStatus.SUCCESS, JobStatus.SKIPPED}


async def _download_url(url: str) -> bool:
    queue_service.add_to_display(url)
    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_EXECUTOR, _run_download_url, url)
    finally:
        queue_service.remove_from_display(url)


def _get_embed_image_url(embed: discord.Embed) -> str | None:
    if embed.type == "image" and embed.url:
        return embed.url
    if embed.image and embed.image.url:
        return embed.image.url
    if embed.thumbnail and embed.thumbnail.url:
        return embed.thumbnail.url
    return None


async def _collect_coros(message: discord.Message, before: discord.Message | None = None) -> list:
    coros = []
    guild_name = _guild_name(message.channel)
    is_new = before is None

    if is_new:
        for attachment in message.attachments:
            content_type = (attachment.content_type or "").split(";")[0].strip()
            if content_type in IMAGE_CONTENT_TYPES or Path(attachment.filename).suffix.lower() in IMAGE_EXTENSIONS:
                coros.append(_save_attachment(attachment, guild_name))

        for url in _extract_urls(message.content or ""):
            if _is_supported_url(url):
                coros.append(_download_url(url))

        for snapshot in getattr(message, "message_snapshots", []):
            for attachment in snapshot.attachments:
                content_type = (attachment.content_type or "").split(";")[0].strip()
                if content_type in IMAGE_CONTENT_TYPES or Path(attachment.filename).suffix.lower() in IMAGE_EXTENSIONS:
                    coros.append(_save_attachment(attachment, guild_name))
            for url in _extract_urls(snapshot.content or ""):
                if _is_supported_url(url):
                    coros.append(_download_url(url))

    seen_embed_urls = {embed.url for embed in before.embeds if embed.url} if before else set()
    for embed in message.embeds:
        if embed.type != "image":
            continue
        if embed.url and embed.url in seen_embed_urls:
            continue
        image_url = _get_embed_image_url(embed)
        if not image_url:
            continue
        source = embed.url or image_url
        if _is_supported_url(source):
            if is_new:
                coros.append(_download_url(source))
        else:
            coros.append(_download_embed_image(image_url, guild_name))

    return coros


def _emoji_matches(reaction_emoji, cfg: str, fallback: str) -> bool:
    parsed = _parse_emoji(cfg)
    if isinstance(parsed, discord.PartialEmoji) and hasattr(reaction_emoji, "id") and reaction_emoji.id == parsed.id:
        return True
    return str(reaction_emoji) == fallback


def _already_processed(message: discord.Message) -> bool:
    for reaction in message.reactions:
        if reaction.me and (
            _emoji_matches(reaction.emoji, DISCORD_EMOJI_DONE, _FB_DONE)
            or _emoji_matches(reaction.emoji, DISCORD_EMOJI_FAILED, _FB_FAILED)
        ):
            return True
    return False


async def _process_and_react(message: discord.Message, coros: list) -> None:
    await _react(message, DISCORD_EMOJI_QUEUED, _FB_QUEUED)
    results = await asyncio.gather(*coros, return_exceptions=True)
    ok = sum(1 for item in results if item is True)
    failed = len(results) - ok
    await _unreact(message, DISCORD_EMOJI_QUEUED, _FB_QUEUED)
    if failed == 0:
        await _react(message, DISCORD_EMOJI_DONE, _FB_DONE)
    elif ok == 0:
        await _react(message, DISCORD_EMOJI_FAILED, _FB_FAILED)
    else:
        await _react(message, DISCORD_EMOJI_DONE, _FB_DONE)
        await _react(message, DISCORD_EMOJI_FAILED, _FB_FAILED)


async def _cmd_download_channel(trigger: discord.Message) -> None:
    await _react(trigger, DISCORD_EMOJI_QUEUED, _FB_QUEUED)
    tasks: list[tuple[discord.Message, list]] = []
    seen_urls: set[str] = set()
    async for message in trigger.channel.history(limit=1000, oldest_first=True):
        if message.author == client.user or message.id == trigger.id or _already_processed(message):
            continue
        coros = []
        guild_name = _guild_name(message.channel)
        for attachment in message.attachments:
            content_type = (attachment.content_type or "").split(";")[0].strip()
            if content_type in IMAGE_CONTENT_TYPES or Path(attachment.filename).suffix.lower() in IMAGE_EXTENSIONS:
                coros.append(_save_attachment(attachment, guild_name))
        for url in _extract_urls(message.content or ""):
            if _is_supported_url(url) and url not in seen_urls:
                seen_urls.add(url)
                coros.append(_download_url(url))
        for embed in message.embeds:
            image_url = _get_embed_image_url(embed)
            if not image_url:
                continue
            source = embed.url or image_url
            if _is_supported_url(source):
                if source not in seen_urls:
                    seen_urls.add(source)
                    coros.append(_download_url(source))
            elif image_url not in seen_urls:
                seen_urls.add(image_url)
                coros.append(_download_embed_image(image_url, guild_name))
        if coros:
            tasks.append((message, coros))

    total_ok = 0
    total_failed = 0
    for message, coros in tasks:
        await _react(message, DISCORD_EMOJI_QUEUED, _FB_QUEUED)
        results = await asyncio.gather(*coros, return_exceptions=True)
        ok = sum(1 for item in results if item is True)
        failed = len(results) - ok
        total_ok += ok
        total_failed += failed
        await _unreact(message, DISCORD_EMOJI_QUEUED, _FB_QUEUED)
        if failed == 0:
            await _react(message, DISCORD_EMOJI_DONE, _FB_DONE)
        elif ok == 0:
            await _react(message, DISCORD_EMOJI_FAILED, _FB_FAILED)
        else:
            await _react(message, DISCORD_EMOJI_DONE, _FB_DONE)
            await _react(message, DISCORD_EMOJI_FAILED, _FB_FAILED)

    await _unreact(trigger, DISCORD_EMOJI_QUEUED, _FB_QUEUED)
    if total_failed == 0:
        await _react(trigger, DISCORD_EMOJI_DONE, _FB_DONE)
    elif total_ok == 0:
        await _react(trigger, DISCORD_EMOJI_FAILED, _FB_FAILED)
    else:
        await _react(trigger, DISCORD_EMOJI_DONE, _FB_DONE)
        await _react(trigger, DISCORD_EMOJI_FAILED, _FB_FAILED)


@client.event
async def on_ready() -> None:
    print(f"[Bot] Logged in as {client.user}")
    if DISCORD_CHANNEL_IDS:
        print(f"[Bot] Monitoring channels: {sorted(DISCORD_CHANNEL_IDS)}")
    else:
        print("[Bot] Warning: DISCORD_CHANNEL_IDS is not set.")


@client.event
async def on_message(message: discord.Message) -> None:
    if not DISCORD_CHANNEL_IDS or message.channel.id not in DISCORD_CHANNEL_IDS:
        return
    if message.author == client.user:
        return
    if message.content.strip().lower() in ("$d", "$download"):
        asyncio.create_task(_cmd_download_channel(message))
        return
    coros = await _collect_coros(message)
    if coros:
        asyncio.create_task(_process_and_react(message, coros))


@client.event
async def on_message_edit(before: discord.Message, after: discord.Message) -> None:
    if not DISCORD_CHANNEL_IDS or after.channel.id not in DISCORD_CHANNEL_IDS:
        return
    if after.author == client.user or len(after.embeds) <= len(before.embeds):
        return
    coros = await _collect_coros(after, before=before)
    if coros:
        asyncio.create_task(_process_and_react(after, coros))


def run() -> None:
    if not DISCORD_BOT_TOKEN:
        print("[Bot] DISCORD_BOT_TOKEN is not set.")
        return
    print("[Bot] Starting NS Media Hub Discord bot...")
    client.run(DISCORD_BOT_TOKEN)
