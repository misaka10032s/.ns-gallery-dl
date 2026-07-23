---
id: BP-BOT-1
title: Discord Bot（自動下載/附件/embed/$d 補下載/reaction 狀態）
system: bot
tags: [bot, discord, deployable]
status: 已完成
request_verbatim: "CLAUDE.md「Bot: Discord (Python)」；啟動腳本表「-b：Start Discord bot」；.env「DISCORD_BOT_TOKEN, DISCORD_CHANNEL_IDS, BOT_DOMAIN_ALLOWLIST, BOT_DOMAIN_DENYLIST, DISCORD_EMOJI_*」"
decided_date: 2026-05-21
exec_links:
  - app/services/discord_service.py
  - app/main.py
  - app/config/settings.py
depends_on:
  - BP-PROV-DIRECTFILE-1
  - BP-SVC-DOWNLOAD-1
origin: "`app/services/discord_service.py` 首次入庫於 Build ns-media-hub unified workspace（998bfec，2026-05-21）"
---

## 設計說明

**這是三個獨立可部署元件之一**：`dl.cmd -b`/`dl.sh -b` 啟動獨立行程（`-s -b`
同時啟動與 Web 伺服器），執行 `app/services/discord_service.py::run()`
（`discord.Client`，`intents.message_content = True`）。程式碼盤點確認**完整實作**，
非 stub。

### 自動下載觸發（`on_message`／`on_message_edit`）

`_collect_coros()` 收集三種來源：訊息附件（圖片副檔名或 content-type 判斷，含
`message_snapshots` 轉發訊息內的附件）、訊息文字中萃取的 URL（`_extract_urls`，
含舊縮寫展開 `p123`/`n123`/`w123` 等，復用 `BP-SVC-DOWNLOAD-1` 的
`expand_url_shortcut`）、embed 圖片（型別為 `image` 的 embed）。只監聽
`DISCORD_CHANNEL_IDS` 白名單頻道；`BOT_DOMAIN_ALLOWLIST`/`BOT_DOMAIN_DENYLIST`
另外對 URL 網域做二次過濾（`is_domain_allowed`）。

### `$d`/`$download` 頻道回溯補下載

`_cmd_download_channel()`：從觸發訊息往回掃該頻道最多 1000 則歷史訊息（
`oldest_first=True`），跳過已處理（已有完成/失敗 reaction）的訊息，逐則收集附件/
URL/embed 補下載——用於補抓 bot 上線前錯過的內容。

### 狀態回饋（reaction）

`_react`/`_unreact` 用可設定的自訂 emoji（`DISCORD_EMOJI_QUEUED`/`_DONE`/`_FAILED`，
`.env` 設定，含 `<a?:name:id>` 格式解析），失敗時退回內建 Unicode emoji
（⏳/✅/❌）。全部成功 → ✅；全部失敗 → ❌；部分成功 → 同時掛 ✅+❌ 兩個 reaction。

### 下載路徑

`discord_root(guild_name, kind)`（`BP-SVC-PATH-1`）——`download/discord/<guild>/
attachments|embeds/`，**只分 guild 不分 channel**（CLAUDE.md 明確規則）。

### 誠實現況

無獨立 pytest 覆蓋（`tests/` 下無 `test_discord_service.py`）；`_run_download_url`
透過 `ThreadPoolExecutor(max_workers=3)` 把同步下載邏輯丟到執行緒池執行，讓
asyncio event loop 不被阻塞——這代表 bot 觸發的下載繞過了 `BP-SVC-QUEUE-1` 的單一
序列化 worker（各自獨立跑），與 Web UI/extension 提交走的佇列路徑並不完全共用同一
併發模型，值得使用者知悉（非缺陷，是刻意的獨立路徑，但併發語意不同）。
