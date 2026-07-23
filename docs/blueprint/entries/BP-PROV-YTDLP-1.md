---
id: BP-PROV-YTDLP-1
title: yt-dlp 影音下載引擎
system: backend-provider
tags: [backend, provider, ytdlp, generic]
status: 已完成
request_verbatim: "CLAUDE.md「Download engines: gallery-dl, yt-dlp — both pip-managed via venv, invoked as subprocesses（yt-dlp resolves through PATH/venv Scripts, NOT a standalone .exe; the old sibling .ns-yt-dlp repo fallback is gone — that repo no longer exists）」"
decided_date: 2026-05-21
exec_links:
  - app/providers/ytdlp/provider.py
  - app/providers/ytdlp/external_adapter.py
depends_on:
  - BP-PROV-COOKIES-1
origin: "`app/providers/ytdlp/provider.py` 首次入庫於 Build ns-media-hub unified workspace（998bfec，2026-05-21）；`.ns-yt-dlp` 舊 repo fallback 移除見 commit（registry/CLAUDE.md 記載，pip-managed 化）"
---

## 設計說明

`app/providers/ytdlp/provider.py`（138 行）是 yt-dlp 影音下載的 provider，處理
YouTube/X/Facebook 等 `YTDLP_DOMAINS`（`app/config/settings.py`）網域。

### 執行檔解析（`_resolve_executable`）

優先序：repo 根目錄手動放置的 `<name>.exe`（本機除錯用）→ `PATH`/venv `Scripts`
（`shutil.which`，pip 安裝 `yt-dlp` 後的標準位置）。**舊的 `.ns-yt-dlp` 姊妹 repo
fallback 已完全移除**——CLAUDE.md 明確記載該 repo 已不存在，本次程式碼核對確認
`provider.py` 註解與此一致，無殘留引用。

### 下載參數

- `--windows-filenames --trim-filenames 120`：檔名相容 Windows 檔案系統限制。
- `--format`：依網域客製——Facebook 用 `best`（避免分軌合併失敗），其餘用
  `bestvideo*+bestaudio/best`。
- `--output`：先用 provider 根目錄產生暫定模板，`_probe_user_root()` 再用
  `--print` 探測上傳者/頻道名稱後**重寫**輸出模板路徑（`command[index+1] = ...`），
  讓檔案最終落在 `download/ytdlp/<domain>/` 下依作者分層（若探測成功）。
- Cookie：`resolve_cookie_file()`（`BP-PROV-COOKIES-1`）解析後以 `--cookies` 傳入。
- ffmpeg：若本機解析得到 `ffmpeg` 路徑，加 `--ffmpeg-location` 顯式指定（避免依賴
  PATH 隱式解析失敗）。

### 誠實現況

沒有針對 `download()` 主流程的獨立 pytest 覆蓋；`tests/test_ytdlp_resolve_executable.py`
只測 `_resolve_executable` 這一小段邏輯。
