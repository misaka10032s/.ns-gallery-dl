---
id: BP-PROV-GALLERYDL-1
title: gallery-dl 通用下載引擎（orchestration + 站台特化分派）
system: backend-provider
tags: [backend, provider, gallery-dl, generic]
status: 已完成
request_verbatim: "CLAUDE.md「Download engines: gallery-dl, yt-dlp — both pip-managed via venv, invoked as subprocesses」；process.md「gallery_dl/provider.py：gallery-dl 流程」"
decided_date: 2026-05-21
exec_links:
  - app/providers/gallery_dl/provider.py
  - app/providers/gallery_dl/auth.py
depends_on:
  - BP-PROV-BAHAMUT-1
  - BP-PROV-NHENTAI-1
  - BP-PROV-WNACG-1
  - BP-PROV-PIXIV-1
  - BP-PROV-COOKIES-1
origin: "`app/providers/gallery_dl/provider.py` 首次入庫於 Build ns-media-hub unified workspace（998bfec，2026-05-21）"
---

## 設計說明

`app/providers/gallery_dl/provider.py`（236 行）是「gallery-dl」provider 的統一入口
`download(url, tokens, max_retries=5, retry_delay=5, metadata=None)`，同時扮演兩個角色：

1. **站台特化分派器**：`nhentai.net` → `BP-PROV-NHENTAI-1`、`wnacg.com` →
   `BP-PROV-WNACG-1`、`forum.gamer.com.tw`/`gamer.com.tw` → `BP-PROV-BAHAMUT-1`（含
   `selected_urls` 精準下載）。這三站繞過真正的 gallery-dl CLI，直接用內建 scraper。
2. **通用 gallery-dl CLI 包裝**：其餘所有 `GALLERY_DL_DOMAINS`（pixiv/danbooru/
   patreon/civitai/deviantart/…，見 `app/config/settings.py`）走真正的 `gallery-dl`
   子行程，流程：

```mermaid
flowchart TD
    A[download url] --> B{domain 是否為<br/>nhentai/wnacg/bahamut}
    B -- 是 --> C[站台特化 scraper]
    B -- 否 --> D[cookie candidates 依 domain 決定順序]
    D --> E[_probe_user_root: pixiv ajax API /<br/>facebook,x.com 用 gallery-dl -j 探測作者名]
    E --> F["gallery-dl --simulate（試算張數，不下載）"]
    F -- 回傳 0 張 --> G[標記 saw_zero_results]
    F -- 失敗 --> H[記錄錯誤, 進入下一 cookie candidate]
    F -- 有張數 --> I[真正下載: gallery-dl url -D root]
    I -- 成功 --> J{downloaded==0 且 skipped>0}
    J -- 是 --> K[SKIPPED：整批已存在]
    J -- 否 --> L[SUCCESS]
    I -- 失敗 --> M{pixiv 且此次嘗試失敗}
    M -- 是 --> N[重新取得 refresh token 後 continue]
    M -- 否 --> O{還有重試次數}
    O -- 是 --> P[sleep retry_delay 後重試]
    O -- 否 --> Q[FAILED，附最後一行錯誤訊息]
```

### 關鍵行為細節

- **Cookie 候選順序依網域客製**（`_cookie_candidates`）：X/Twitter 先不帶 cookie
  再帶；Facebook 先帶 cookie 再不帶——因兩站對 cookie 存在與否的反應不同（部分頁面
  帶 cookie 反而觸發驗證牆）。
- **使用者根目錄探測**（`_probe_user_root`）：Pixiv 用官方 ajax API；Facebook/X
  用 `gallery-dl -j`（JSON dump 模式）取得作者名，讓下載落在
  `download/pixiv.net/<author>/` 這類分層路徑（`BP-SVC-PATH-1`）。
- **錯誤訊息萃取**（`_last_error_line`）：gallery-dl 錯誤格式固定為
  `[<name>][error] <message>`（已對照真實 CLI 輸出驗證），優先抓這類行，否則退回最後
  一行非空輸出，確保 job 的 `error` 欄位永遠有可讀診斷文字。
- **與 `BP-SVC-UPDATER-1` 的整合點**：此 provider 本身不觸發更新——是呼叫方
  `download_service.download_request`（`BP-SVC-DOWNLOAD-1`）在偵測到失敗訊息符合
  「疑似過期擷取器」特徵時才觸發 reactive 更新重試，本 provider 只負責把診斷字串
  乾淨地往上傳。

### 誠實現況

沒有針對本檔的獨立 pytest 覆蓋（`tests/test_gallery_dl_error_capture.py` 只測
`_last_error_line` 錯誤訊息萃取這一小段邏輯，不含完整 `download()` 流程）；`--simulate`
先行試算的成本（每次下載都先跑一次完整模擬）未量化，屬效能上的已知取捨，非缺陷。
