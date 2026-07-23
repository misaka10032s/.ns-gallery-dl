---
id: BP-SVC-FRONTEND-1
title: 前端自動建置偵測（dev-time frontend auto-build)
system: backend-service
tags: [backend, service, frontend-build, devtool]
status: 已完成
request_verbatim: "CLAUDE.md 啟動腳本表「-s：Start server + UI（auto-rebuilds frontend if source changed）」；process.md「若有啟動 server，先檢查 frontend/ 是否需要自動 build」"
decided_date: 2026-05-21
exec_links:
  - app/services/frontend_service.py
  - app/main.py
origin: "`app/services/frontend_service.py` 首次入庫於 Build ns-media-hub unified workspace（998bfec，2026-05-21）"
---

## 設計說明

`app/services/frontend_service.py`（58 行）是 `dl.cmd -s`/`dl.sh -s` 啟動伺服器模式
時的前置檢查，非對外 API，純粹是開發便利機制。`ensure_frontend_ready()`
（`app/main.py::_bootstrap(ensure_ui=True)` 呼叫）：

1. 確認 `npm` 在 PATH 上，找不到直接拋錯（明確訊息而非靜默失敗）。
2. `frontend/node_modules` 不存在 → 跑 `npm install`。
3. `needs_build()`：比較 `frontend/src`、`frontend/public`、
   `package.json`/`package-lock.json`/`vite.config.js`/`index.html` 的最新
   mtime 是否晚於 `app/ui/index.html`（build 產物）的 mtime，是則跑
   `npm run build`；否則印出「Frontend build is up to date」並跳過。

### 誠實現況

以 **檔案 mtime 比較**判斷是否需要重建，而非內容 hash——理論上存在「內容沒變但
mtime 被更新（如 git checkout/整批觸碰檔案）觸發不必要重建」的邊界情況，但代價僅是
多跑一次 build，非正確性問題，屬可接受取捨。無獨立 pytest 覆蓋。
