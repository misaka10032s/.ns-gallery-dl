---
id: BP-EXT-SITES-1
title: 各站台 content script 適配器（bahamut/facebook/nhentai/pixiv/wnacg/yande.re）
system: extension
tags: [extension, site-adapter]
status: 已完成
request_verbatim: "process.md「chromeExtension/：pixiv/, nhentai/, wnacg/, yande.re/, facebook/：各站 content scripts」；selection-mode-v2-spec.md「Existing 5 sites + bahamut adapters must remain backward-compatible」"
decided_date: 2025-08-13
exec_links:
  - chromeExtension/pixiv/content.js
  - chromeExtension/nhentai/content.js
  - chromeExtension/wnacg/content.js
  - chromeExtension/facebook/content.js
  - chromeExtension/yande.re/content.js
  - chromeExtension/bahamut/content.js
  - chromeExtension/manifest.json
depends_on:
  - BP-EXT-SELECTION-1
origin: "pixiv/yande.re `content.js` 首次可考記錄於 commit c8b0ca8（2025-08-13，吸收自 ns-chrome-tool）；nhentai/wnacg/facebook 首次記錄於 commit a55bc11（2025-08-14）；bahamut 較晚加入，首次入庫於 commit 2bd108d（2026-07-04）"
revisions:
  - date: 2026-07-04
    summary: "commit 2bd108d：新增 bahamut 站台適配器（forum.gamer.com.tw C.php/Co.php），含 resolveUrl 覆寫（去除 CDN resize 查詢參數）與 submitMode: 'imageSelection'"
---

## 設計說明

六個站台各自一支輕量 content script，全部透過共用引擎
（`NsSelector.register({...})`，`BP-EXT-SELECTION-1`）掛上契約，本身只需回答
「這個頁面上哪些元素是可選取的圖片」（`getItems`），不重寫任何選取/框選/overlay 邏輯：

| 站台 | 檔案行數 | 匹配頁面 | 特殊處理 |
|---|---|---|---|
| Pixiv | 16 | `/users/*`, `/artworks/*` | `a[href*="/artworks/"]` 且含 `<img>` |
| nhentai | 16 | `nhentai.net/*` | 標準 `getItems` |
| wnacg | 18 | `wnacg.com/*` | 標準 `getItems` |
| Facebook | 18 | `facebook.com/*` | 標準 `getItems` |
| yande.re | 13 | `/post`, `/post?tags=*` | 標準 `getItems` |
| Bahamut | 32 | `C.php*`, `Co.php*` | `resolveUrl` 覆寫（去 CDN resize 參數）+ `submitMode: 'imageSelection'`，只抓 `c-article__content` 內文章本文圖片，過濾論壇表情/圖示（`i2.bahamut.com.tw/forum/icons` 路徑） |

### Manifest 內容腳本載入順序

每個站台的 `content_scripts` 條目都固定載入順序
`selector-catalog.js → selector-core.js → selector-overview.js → <site>/content.js`
——引擎先就緒，站台適配器最後註冊，避免競態。

### 誠實現況

`selection-mode-v2-spec.md` 明確要求「5 個既有站台 + bahamut 適配器維持向後相容
（contract is additive）」——本次程式碼盤點確認 5 個既有站台的 `content.js` 皆只有
`getItems`（未見 `resolveUrl` 等 v2 新增覆寫），符合 spec 對「未主動加新功能的站台
應維持零修改」的驗收條件。除 bahamut 外的 5 站無獨立 pytest/JS 單元測試（
`chromeExtension/tests/` 兩支測試檔測的是引擎邏輯本身，非各站 `getItems` 選擇器）。
