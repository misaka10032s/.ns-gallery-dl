---
id: BP-SVC-PATH-1
title: 下載路徑／檔名規則服務
system: backend-service
tags: [backend, service, path]
status: 已完成
request_verbatim: "CLAUDE.md「Download paths (provider-directed — no hardcoding outside domain registry): Discord: guild-only；Pixiv: author-level；YouTube / X / Facebook: domain-only」"
decided_date: 2026-05-21
exec_links:
  - app/services/path_service.py
origin: "`app/services/path_service.py` 首次入庫於 Build ns-media-hub unified workspace（998bfec，2026-05-21）"
---

## 設計說明

`app/services/path_service.py`（74 行）是所有 provider 共用的路徑/檔名規則層，
CLAUDE.md 明確要求「no hardcoding outside domain registry」——本檔即該 registry。

### 網域 → 分類目錄別名（`CATEGORY_ALIASES`）

`facebook.com`/`fb.watch` → `facebook`、`forum.gamer.com.tw`/`gamer.com.tw` →
`bahamut`、`twitter.com`/`x.com` → `x`、`youtube.com`/`youtu.be` → `youtube`，其餘
未列網域直接用網域字串本身（經 `sanitize_component` 過濾非法字元）。

### 三種路徑規則（對應 CLAUDE.md 規則表）

- `category_root(domain, subcategory)`：一般規則，`download/<分類>/[<subcategory>]/`。
- `pixiv_root(domain, author)`：等同 `category_root`，Pixiv 專用別名函式（作者層級）。
- `discord_root(guild_name, kind)`：`download/discord/<guild>/`——**只分 guild
  不分 channel**（CLAUDE.md 明確規則）。

### 檔名安全

`sanitize_component()` 移除 Windows 非法字元（`<>:"/\|?*` 及控制字元）、截斷至 120
字；`unique_file_path()` 若目標檔名已存在，附加 `_1`/`_2`… 遞增數字避免覆蓋；
`file_name_from_url()` 從 URL path 猜測檔名，缺副檔名時退回呼叫端提供的 fallback。

### 誠實現況

無獨立 pytest 覆蓋（`test_meta_preservation.py`/`test_download_service*.py` 間接
透過下游行為觸及，但未直接單元測試本檔函式）。
