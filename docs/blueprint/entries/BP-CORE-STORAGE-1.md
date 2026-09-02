---
id: BP-CORE-STORAGE-1
title: SQLite 儲存層（schema／WAL／舊資料遷移／repositories）
system: backend-core
tags: [backend, storage, sqlite]
status: 已完成
request_verbatim: "@PM registry ns-media-hub.md Roadmap（現行未勾待辦）：「SQLite WAL 模式 — 未啟用 WAL，高並發寫入有鎖競爭風險」；CLAUDE.md「Data storage: All state (jobs, history, cookies registry) in SQLite (data/app.db)；Legacy data/history.json auto-migrates to SQLite on init」"
decided_date: 2026-05-21
exec_links:
  - app/storage/db.py
  - app/storage/repositories/jobs_repo.py
  - app/storage/repositories/history_repo.py
  - app/storage/repositories/cookies_repo.py
  - app/storage/repositories/downloader_state_repo.py
origin: "`app/storage/db.py` 首次入庫於 Build ns-media-hub unified workspace（998bfec，2026-05-21）；WAL 模式啟用於 commit f2718f1（2026-06-20）"
revisions:
  - date: 2026-06-20
    summary: "commit f2718f1：`PRAGMA journal_mode=WAL` 於每次連線建立時執行，允許讀寫並發，降低多執行緒「database is locked」錯誤風險"
  - date: 2026-07-23
    summary: "blueprint seeding 核對：registry 現行仍記載 WAL「未啟用」為待辦，但程式碼（`app/storage/db.py:23`）確認已啟用——registry 記載已過期，本條目以程式碼現況為準"
  - date: 2026-09-02
    summary: "分支 `fix/auth-failure-handling`（審查中）新增第五張表 `auth_cooldown`（PRIMARY KEY domain）與 `auth_cooldown_repo`——設計與 6 小時 TTL 見 `BP-SVC-AUTH-COOLDOWN-1`。注意：該分支較早一輪曾把此表實際建到站主正式 `data/app.db`（零列，未動既有資料），決定保留不 drop"
---

## 設計說明

`app/storage/db.py` 是唯一的 SQLite 連線層（`data/app.db`），四個 repository
（`jobs_repo`/`history_repo`/`cookies_repo`/`downloader_state_repo`）皆透過
`connection()` context manager 取得連線，不直接開連線。

### Schema（`init_db()`，thread-safe 單次初始化）

- `jobs`：每筆下載請求的完整生命週期（provider/source/status/domain/download_path/
  meta_json/error/時間戳）。
- `history_entries`：**每個 URL 的最新狀態**（`UNIQUE(url)`，非 append-only 日誌，
  見 `BP-SVC-HISTORY-1` 的誠實現況說明）。
- `cookie_entries`：cookie 檔案註冊表（`UNIQUE(domain, provider, file_path)`）。
- `downloader_state`：`BP-SVC-UPDATER-1` 的 reactive 更新 cooldown 狀態。
- `auth_cooldown`：登入失效冷卻，**一列一個網域**（不是一列一個 provider——同一網域
  可能被 gallery-dl 與 yt-dlp 都試過，且共用同一份 cookie 檔）。見
  `BP-SVC-AUTH-COOLDOWN-1`。分支 `fix/auth-failure-handling` 新增，審查中。
- 索引：`jobs(status, id)`、`history_entries(event_date DESC)`、
  `history_entries(domain)`、`cookie_entries(domain, provider)`。

### WAL 模式（本次盤點的重要修正——registry 記載已過期）

`_connect()` 每次連線都執行 `PRAGMA journal_mode=WAL`（`db.py:23`）。**@PM
registry 現行仍記載「SQLite WAL 模式 — 未啟用」為待辦**，但這與程式碼現況
（commit f2718f1，2026-06-20 即已加上）不符——這是本次 blueprint seeding 依
CLAUDE.md「程式碼盤點優先於 registry 記載」原則核對出的第二筆 registry 過期記錄
（另一筆見 `BP-CORE-SECURITY-1`）。

### 舊資料遷移

`migrate_legacy_history()`：`init_db()` 時若 `history_entries` 為空且
`data/history.json`（舊格式）存在，逐筆匯入（`INSERT OR IGNORE`，不覆蓋已有資料）。

### 誠實現況

無獨立 pytest 針對 schema/WAL/遷移邏輯本身（其餘測試檔透過呼叫各 repo 間接觸及）；
WAL 模式在高並發寫入下是否確實消除鎖競爭未經壓力測試驗證，僅是理論上的正確配置。
