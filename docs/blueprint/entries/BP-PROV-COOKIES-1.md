---
id: BP-PROV-COOKIES-1
title: Cookie 掃描／註冊／解析引擎（provider 層）
system: backend-provider
tags: [backend, provider, cookies]
status: 已完成
request_verbatim: "CLAUDE.md「Cookies：Canonical path: cookies/（old paths auto-migrate on scan）；cookies/* is gitignored；Scan results written to SQLite registry; providers resolve applicable cookie automatically」"
decided_date: 2026-05-21
exec_links:
  - app/providers/cookies/registry.py
  - app/providers/cookies/metadata.py
  - app/providers/cookies/resolver.py
origin: "`app/providers/cookies/` 三檔首次入庫於 Build ns-media-hub unified workspace（998bfec，2026-05-21）"
---

## 設計說明

三個小模組構成 provider 層的 cookie 基礎設施（與 `BP-SVC-CREDENTIALS-1` 的
CRUD API 服務層分工：這一層負責「掃描/找出可用 cookie」，服務層負責「使用者新增/
修改/刪除 cookie」）：

- **`registry.py`**：`scan_cookie_files()` 掃描 `cookies/` 目錄下所有 `.txt`，先呼叫
  `migrate_legacy_cookie_files()` 把舊路徑（`LEGACY_COOKIE_DIRS`）的檔案搬到現行
  `COOKIE_DIR`（CLAUDE.md「old paths auto-migrate on scan」），再逐檔用
  `metadata.infer_cookie_metadata()` 推斷網域/provider，寫入（`upsert`）SQLite
  `cookie_entries` 表；每次掃描先 `clear_scanned_entries()` 清空 source='scan' 的
  舊紀錄再重建，確保註冊表與磁碟內容同步、不留殭屍紀錄。
- **`metadata.py`**（24 行）：從檔案內容/檔名推斷 cookie 所屬網域與 provider。
- **`resolver.py`**：`resolve_cookie_file(url, provider)` 是下載流程實際呼叫的
  查詢入口——先精準比對網域+provider，若查無且該網域屬於
  `MULTI_PROVIDER_DOMAINS`（facebook/x.com 等同時可能被 gallery-dl 或 yt-dlp
  下載），退而只用網域比對（不限 provider）。`BP-PROV-GALLERYDL-1` 與
  `BP-PROV-YTDLP-1` 皆呼叫此函式取得可用 cookie 路徑。

### 誠實現況

沒有針對這三個模組的獨立 pytest 覆蓋（`tests/test_cookie_service.py` 測的是
`BP-SVC-CREDENTIALS-1` 的 CRUD 服務層，不含這裡的掃描/解析邏輯）。
