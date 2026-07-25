---
id: BP-EXT-SELECTION-1
title: Selection Mode v2 選取引擎（catalog/core/overview 共用模組）
system: extension
tags: [extension, selection-mode, core-feature]
status: 已完成
request_verbatim: "@PM registry ns-media-hub.md Roadmap（已勾）：「Selection Mode v2 — catalog 層（虛擬滾動安全）、縮圖→原圖解析鏈、頁內一覽 overlay（等大 tile/框選/Alt+G）、Alt+S 關閉保留選取、送出成功自動清空；spec 進 .claude/context/（review FAIL→fix→PASS；merged 1eeb556 + spec f51df16；待使用者瀏覽器手動煙測，重點 pixiv 虛擬滾動）」"
decided_date: 2026-07-04
exec_links:
  - chromeExtension/static/module/selector-catalog.js
  - chromeExtension/static/module/selector-core.js
  - chromeExtension/static/module/selector-overview.js
  - chromeExtension/static/module/selector.css
  - chromeExtension/tests/test-catalog-resolution.js
  - chromeExtension/tests/test-selection-math.js
superpowers:
  - path: docs/superpowers/specs/selection-mode-v2-spec.md
    label: Selection Mode v2 — 核准設計（2026-07-04，approved by owner via @PM brainstorming）
origin: "approved 2026-07-04（spec 文件自身標頭日期），merged 1eeb556 + spec commit f51df16"
---

## 設計說明

跨五個站台（Pixiv/nhentai/wnacg/yande.re/Facebook，`BP-EXT-SITES-1`）共用的圖片
選取引擎，三個模組依載入順序（`manifest.json` content_scripts 陣列順序）：
`selector-catalog.js`（206 行）→ `selector-core.js`（346 行）→
`selector-overview.js`（340 行），完整設計見連結的核准 spec（`superpowers:` 欄位，
下方 viewer 內嵌顯示）。

### 四個已解決的痛點（spec 已核准決策，不重開）

1. Bahamut 只抓文章本文圖片（`c-article__content`），留言區縮圖不在範圍內。
2. 一覽總覽是頁內全螢幕 overlay，非另開瀏覽器視窗。
3. 送出成功後選取自動清空（通知顯示數量）；送出失敗保留選取。
4. 頁內拖曳框選永久取消——框選只存在於一覽 overlay 內。

### 三層架構摘要（完整規格見連結 spec）

- **Catalog 層**：選取模式開啟時持續維護一份「目前為止發現的所有圖片」清單
  （`MutationObserver` 隨捲動持續追加），選取狀態存 `sessionStorage`（依頁面 URL
  分 key），虛擬滾動下 DOM 節點被回收也不遺失選取狀態。
- **原圖 URL 解析鏈**：`<a href>` 圖片副檔名優先 → 站台專屬縮圖轉原圖規則
  （目前僅 Bahamut：去除 `truth.bahamut.com.tw` 的 `?w=&h=&fit=` 查詢參數）→
  `data-src`/`src` 退回。
- **一覽 overlay**：等大 tile（~180px）grid，lazy-load，點擊切換/Shift 範圍選/
  拖曳框選（僅限 overlay 內）/全選/反選/清除/下載所選；與頁面共用同一份
  catalog/選取 Set，overlay 開啟期間背景仍持續發現新圖。

### 誠實現況

Spec 本身明確標註「Manual smoke list must cover: pixiv virtual scroll...」——
**registry roadmap 記載此功能仍「待使用者瀏覽器手動煙測，重點 pixiv 虛擬滾動」**，
即程式碼已 reviewer PASS 並 merge（狀態 `已完成` 成立），但使用者實機瀏覽器驗收
（尤其 pixiv 長頁虛擬滾動情境）**尚未完成**——這不構成 `已測試`
（blueprint 狀態枚舉需結構化 §4.3 測試紀錄），如實標記為開放事項，不因程式碼
完成就升級狀態或補測試紀錄。
