---
id: BP-PROV-DIRECTFILE-1
title: 直接檔案下載器（Discord 附件/embed、擴充功能原始檔）
system: backend-provider
tags: [backend, provider, direct-file]
status: 已完成
request_verbatim: "CLAUDE.md「Download paths: Discord: guild-only — download/discord/<guild>/attachments|embeds/」；程式碼盤點：`app/providers/direct_file/provider.py`"
decided_date: 2026-05-22
exec_links:
  - app/providers/direct_file/provider.py
depends_on:
  - BP-SVC-PATH-1
origin: "`app/providers/direct_file/provider.py` 首次入庫於 commit 86e3683（2026-05-22）"
---

## 設計說明

`app/providers/direct_file/provider.py`（83 行）是「不需要 gallery-dl/yt-dlp 解析、
直接以 HTTP GET 抓檔」的 provider，`Provider.DIRECT_FILE` 對應。以標準庫
`urllib.request` 串流下載（8KB chunk），不引入額外相依套件。

### 呼叫方

- **Discord bot**（`BP-BOT-1`）：訊息內的圖片附件（`_save_attachment`）與 embed 圖片
  （`_download_embed_image`）都經此 provider，`metadata.guild` 存在時落在
  `download/discord/<guild>/`（`discord_root()`，`BP-SVC-PATH-1`），依 CLAUDE.md
  「guild-only，不分 channel」規則。
- **Chrome extension** 也可能以 `provider_hint=direct_file` 強制走此路徑提交原始
  檔案 URL（見 `app/api/routes/jobs.py` `submit_jobs` 的 `providerHint` 參數）。

### 檔名決定邏輯

`_target_file_name()`：優先用呼叫端提供的 `metadata.filename`；若無副檔名則用回應
的 `Content-Type` 透過 `mimetypes.guess_extension()` 補上；都沒有則退回從 URL path
猜測（`file_name_from_url`，`BP-SVC-PATH-1`），最終退回 `.bin`。

### 誠實現況

沒有針對本檔的獨立 pytest 覆蓋。
