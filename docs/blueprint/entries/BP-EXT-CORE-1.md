---
id: BP-EXT-CORE-1
title: Extension 核心基礎設施（background service worker/右鍵選單/API 橋接/popup）
system: extension
tags: [extension, core, deployable, manifest-v3]
status: 已完成
request_verbatim: "process.md「chromeExtension/：這是目前唯一正式 Chrome extension 套件……background/：service worker 入口與 offscreen helper；core/：API / notification 小模組……不再依賴 native messaging」"
decided_date: 2025-08-13
exec_links:
  - chromeExtension/manifest.json
  - chromeExtension/background/index.js
  - chromeExtension/background/router.js
  - chromeExtension/background/offscreen.js
  - chromeExtension/core/api.js
  - chromeExtension/core/notify.js
  - chromeExtension/core/targets.js
  - chromeExtension/static/module/menu.js
  - chromeExtension/features/download_submit/submit.js
origin: "`chromeExtension/manifest.json` 首次可考記錄於 commit c8b0ca8（2025-08-13）——早於 ns-media-hub 本身（此為吸收自 ns-chrome-tool 的既有歷史，見 CLAUDE.md「External repos absorbed — do NOT modify: javascript/ns-chrome-tool」）；background/router/core 現行結構首次入庫於 998bfec（2026-05-21，ns-media-hub 整合 commit）"
---

## 設計說明

**這是三個獨立可部署元件之一**：Chrome MV3 extension，`manifest_version: 3`，
目前版本號 `2.2.0`（`manifest.json`）。`background/index.js` 是 service worker
入口，串起 offscreen document（`ensureOffscreenDocument`，MV3 service worker
不能直接操作剪貼簿，需經 offscreen document 中介）、訊息路由
（`registerMessageRouter`）、Pixiv 認證監聽（`initializePixivAuthListener`）。

### 訊息路由與下載提交橋接

`background/router.js` 監聽 `downloadUrls`/`submitYtdlp`/`downloadImageSelection`
三種訊息型別，轉呼叫 `features/download_submit/submit.js`，非同步回應
`{success: bool}`（供內容腳本判斷是否自動清空選取，`BP-EXT-SELECTION-1` 決策 3）。
`core/api.js::submitLinks()`/`submitImageSelection()` 實際呼叫本機後端
`http://127.0.0.1:7601/api/jobs`（`BP-SVC-QUEUE-1`），失敗時**退回複製到剪貼簿**
（`copyFallback`，經 offscreen document）並跳系統通知，讓使用者在後端未啟動時仍
不遺失待下載連結。

### 右鍵選單

`static/module/menu.js`（375 行）——CLAUDE.md/registry 記載已收斂為單一頂層選單
「下載此內容」（`downloadContent`，走 `inferProviderHint` 自動判斷 provider），
取代舊有的自建 `downloadRoot` 分組（曾與 Chrome 自動分組造成雙層選單，見 registry
roadmap 修復記錄，merged ede6f03）。

### 三個近期修復的執行環境穩定性問題（registry 記載，已核對程式碼一致）

`overrideOnCopyAndPaste` 動態註冊冪等化（unregister→register + try/catch）；
`chrome-error://`/`chrome://`/`about://` 等非可注入頁面的 `checkTabById`/
`isInjectableUrl` 防護；`NStools_background.js` 裸注入補上 `await`+錯誤捕捉
（merged 24c8bcb）。

### 誠實現況

`chromeExtension/tests/` 只有 2 支測試（`test-catalog-resolution.js`/
`test-selection-math.js`），皆針對 `BP-EXT-SELECTION-1` 的選取引擎邏輯，不覆蓋本
條目所述的 background/core/menu 基礎設施；這些修復多數依賴 registry 記載的
「待使用者 load-unpacked 瀏覽器煙測」，非本 blueprint 可驗證的結構化測試紀錄。
