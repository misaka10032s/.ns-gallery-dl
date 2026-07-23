---
id: BP-PROV-PIXIV-1
title: Pixiv 認證整合（薄層 — 實際下載走通用 gallery-dl 主流程）
system: backend-provider
tags: [backend, provider, pixiv, site-specific, auth]
status: 已完成
request_verbatim: "process.md「providers/sites/：Pixiv / nhentai / wnacg 特化處理」；程式碼盤點：`app/providers/sites/pixiv.py` 現行僅 5 行，重新匯出 `get_pixiv_refresh_token`"
decided_date: 2026-05-21
exec_links:
  - app/providers/sites/pixiv.py
  - app/providers/gallery_dl/auth.py
  - app/providers/gallery_dl/provider.py
depends_on:
  - BP-PROV-GALLERYDL-1
origin: "`app/providers/sites/pixiv.py` 首次入庫於 Build ns-media-hub unified workspace（998bfec，2026-05-21）"
---

## 設計說明

**重要誠實澄清**：不同於 bahamut/nhentai/wnacg 三站各自維護完整的自訂 scraper，
`app/providers/sites/pixiv.py` 現行內容**只有 5 行**——單純重新匯出
`app/providers/gallery_dl/auth.py::get_pixiv_refresh_token`。Pixiv 的實際圖片下載
**不是**由這個檔案處理，而是直接走 `app/providers/gallery_dl/provider.py` 的通用
gallery-dl CLI 子行程路徑（見 `BP-PROV-GALLERYDL-1`），只是該路徑對 `pixiv.net`
網域有兩項特殊處理：

1. **認證**：`download()` 讀取 `get_pixiv_refresh_token(tokens)`，寫入環境變數
   `GALLERYDL_PIXIV_REFRESH_TOKEN` 供 gallery-dl CLI 使用；若下載中途失敗會重新取
   refresh token 再重試（`provider.py` 第 220-224 行）。
2. **作者分層存放**：`_probe_pixiv_user_root()` 呼叫 Pixiv 官方 ajax API
   （`/ajax/illust/<id>`）取得作者名，讓下載路徑落在
   `download/pixiv.net/<author>/`（對應 CLAUDE.md「Pixiv：author-level」路徑規則）。

### Token 取得鏈（`app/providers/gallery_dl/auth.py::get_pixiv_refresh_token`）

1. 優先用 `data/tokens.json` 內已存的 `pixiv_refresh_token`。
2. 沒有則讀 gallery-dl 自身的 `~/.config/gallery-dl/config.json`
   `extractor.pixiv.refresh-token`（若使用者曾手動跑過 gallery-dl 的 pixiv 設定）。
3. 仍沒有則呼叫 `gallery-dl oauth:pixiv` 觸發互動式 OAuth 流程（需終端機互動，非
   headless 友善）取得 token 後寫回 config.json，再讀出存進 `data/tokens.json`。
4. 每次成功取得都會 `save_tokens()` 寫回 `data/tokens.json`，之後的請求直接命中第 1 步。

`/api/auth/pixiv`（`BP-VIEW-DASHBOARD-1` 之外的獨立端點）只回傳
`{"has_refresh_token": bool}` 供前端顯示認證狀態，不負責寫入。

### 誠實現況

第 3 步的互動式 OAuth（`subprocess.run(["gallery-dl", "oauth:pixiv"], check=True)`）
在無終端機的伺服器模式下無法完成使用者互動；這代表「首次 Pixiv 認證」實務上仍需一次
手動、有終端機的執行環境，非全自動——這點未見於 registry/CLAUDE.md 的既有記載，本次
程式碼盤點新發現，列為使用者應知的現況細節。
