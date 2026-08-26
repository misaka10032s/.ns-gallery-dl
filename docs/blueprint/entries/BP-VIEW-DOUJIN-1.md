---
id: BP-VIEW-DOUJIN-1
title: 本子模式前端（封面牆 + 逐頁閱讀器 + 編輯面板，block 1）
system: frontend
tags: [frontend, view, gallery, doujinshi, block-1]
status: 開發中
request_verbatim: "@PM dispatch brief 2026-08-26（block 1 scope）——封面牆（封面／標題／頁數／
  購買狀態一目瞭然）、點封面進逐頁閱讀器（鍵盤導覽 + 記得上次看到哪頁）、編輯面板（欄位 +
  連結新增/刪除）、頁面排序要處理真實檔名的自然/數字排序（10.jpg 不能排在 2.jpg 前面）、
  375px 不能有水平捲軸、閱讀器要能單手操作、破壞性確認一律用 HTML dialog 不用
  window.confirm。"
decided_date: 2026-08-26
exec_links:
  - frontend/src/views/GalleryView.vue
  - frontend/src/components/gallery/DoujinBookWall.vue
  - frontend/src/components/gallery/DoujinBookReader.vue
  - frontend/src/components/gallery/DoujinBookEditPanel.vue
  - frontend/src/components/gallery/SeriesCombobox.vue
  - frontend/src/components/gallery/ConfirmDialog.vue
  - frontend/src/components/gallery/GeneralGalleryPanel.vue
  - frontend/src/api/gallery.js
  - frontend/src/api/client.js
depends_on:
  - BP-SVC-DOUJIN-1
  - BP-VIEW-GALLERY-1
origin: "首次入庫於本次 block 1 開發（2026-08-26，worktree feat/doujin-view）；同日追加：
  移除彩頁欄位、分類改 SeriesCombobox 控制詞彙表元件、名稱/作者/社團加入「⤓ 從站點抓取
  資料」按鈕 + 來源徽章（見 BP-SVC-DOUJIN-1 的 metadata 抓取設計）。"
---

## 設計說明

`GalleryView.vue`（原本 555 行，全站第二大 view）拆成「分類 chips（不變，留在這裡，兩種模式
共用）＋依 `selectedCategory.mode` 切換的內容面板」。原本的一般模式 UI（搜尋、縮圖牆、
影音檢視器）整段搬進新的 `GeneralGalleryPanel.vue`，行為完全不變——只是換了個檔案放，讓
新增第二種完整模式不必把單一 view 撐向千行。本子模式的三個元件都在
`frontend/src/components/gallery/`：

- **`DoujinBookWall.vue`**——封面牆。呼叫 `GET /api/gallery/doujin/books?source=`，卡片顯示
  封面（沿用既有 `/api/gallery/serve?p=` 端點，不是新檔案服務路徑）、標題、作者/社團、頁數、
  購買狀態徽章。點封面開 `DoujinBookReader`，點「✎ 編輯」開 `DoujinBookEditPanel`。
- **`DoujinBookReader.vue`**——逐頁閱讀器。頁面順序完全信任後端回傳（`doujin_service`
  的 `natural_sort_key`，前端不重新排序）。鍵盤：→/↓/space 下一頁，←/↑ 上一頁，
  Esc 關閉。**單手操作**：圖片本身分兩個點擊區——左 35% 上一頁、右 65% 下一頁（往前翻是
  常見手勢，給比較大的點擊區），底部固定一條上一頁/頁碼/下一頁工具列（`env(safe-area-inset-
  bottom)` 讓 iOS 瀏海手機也不被系統手勢列擋住），刻意不放在頂部——拇指從螢幕邊緣去點頂部
  按鈕在手機上並不好按。**閱讀進度記憶**：`last_page_index` 存在後端（`doujin_books` 表），
  翻頁 500ms 防抖後 PUT 回去、關閉時再存一次一定要成功送出的那次——不是純前端 localStorage，
  換裝置或清瀏覽器快取都還記得看到哪頁。
- **`DoujinBookEditPanel.vue`**——右側抽屜（375px 下變全螢幕）。**彩頁欄位已移除**（隨
  `BP-SVC-DOUJIN-1` 的 schema 變更一起拿掉）。名稱/作者/社團三個欄位旁各顯示一個來源徽章
  （「預設」/「站點資料」/「已編輯」，對應 `<field>_source`），手動編輯過的欄位多一顆
  「還原自動值」按鈕（送 `null` 清掉 `*_override`）；面板頂部有「⤓ 從站點抓取資料」按鈕
  （呼叫 `POST /api/gallery/doujin/book/fetch-meta`，只在使用者主動按下時才發網路請求）+
  抓取狀態文字（成功/被擋/找不到/網路錯誤/沒有可辨識 ID/此來源尚未支援，對應
  `meta_fetch_status`）；原始資料夾名稱固定顯示在面板最上方，供對照磁碟上的實際資料夾。
  分類欄位改用 `SeriesCombobox`（見下）。頁數欄位預設留白＝自動偵測，填數字才會覆蓋
  （對應 `page_count_override`），若站點抓過頁數則多顯示「站點：N 頁」供交叉核對。封面欄位
  是下拉選單，選項就是這本書實際的頁面檔名（伺服器驗證過的合法值集合），不能亂填。連結區塊：
  清單 + 新增表單 + 刪除——刪除一律走 `ConfirmDialog.vue`（**原生 `<dialog>`，不是
  `window.confirm`**，符合叢集規則）。
- **`SeriesCombobox.vue`**（本輪新增）——分類的控制詞彙表元件，不是自由文字框。輸入時
  200ms 防抖呼叫 `GET /api/gallery/doujin/series?q=` 篩選既有分類；點一筆既有分類直接套用
  （不會另外呼叫建立 API）；輸入的字串沒有完全符合的既有分類時顯示「+ 建立「X」」，呼叫
  `POST /api/gallery/doujin/series`——伺服器回 200（正規化後完全相同，靜默套用既有那筆）
  或 201（真的建立新的）都直接套用；伺服器回 **409**（近似重複，`error.status===409` +
  `error.payload.candidates`，見 `frontend/src/api/client.js` 對 `apiRequest` 拋出的
  `Error` 新增的 `.status`/`.payload`，向後相容——舊呼叫端只讀 `.message` 不受影響）時，
  面板內顯示候選清單「使用「X」」按鈕（點了直接套用候選、不建立新的）+「仍要建立「X」」
  按鈕（帶 `confirm:true` 重送，明知故犯地建立一筆近似的）——**碰撞永遠可見，但從不擋人**，
  對應使用者的原始要求。清除分類用 ✕ 按鈕（送 `series_id: null`，分類是 first-class 的
  「無」狀態，不是空字串）。
- **`ConfirmDialog.vue`**——可重用的破壞性操作確認元件，`showModal()`/`close()`，
  Esc 視同取消。

### 375 / 768 / 1280 檢查（本次做了什麼、還缺什麼）

三個新元件都在各自 scoped style 裡用 `@include down($bp-sm)`（640px，涵蓋 375）收斂：
封面牆卡片欄寬從 `minmax(150px,1fr)` 降到 `minmax(112px,1fr)`、編輯面板寬度從
`min(28rem,100vw)` 變 `100vw`、閱讀器底部工具列按鈕縮小 padding/字級、一般模式的搜尋列/縮圖
牆同樣有對應的窄螢幕收斂（沿用 `GeneralGalleryPanel.vue`）。**誠實現況**：本次沒有瀏覽器
（Playwright/裝置模擬）可用，**沒有**、也**不能宣稱**「畫面實際渲染正確」——只做了：
`npm run build` 成功（54 modules transformed，無編譯錯誤）；CSS 規則本身是照 CSS Grid
`auto-fill` + `minmax` 寫的，理論上不會產生水平捲軸，但這只是程式碼層級的推論，不是視覺驗證。
**下一步（block 1 收尾前必須做）**：一次 Playwright 375/768/1280 三檔位截圖驗收（叢集
merge-gate 規則），特別看封面牆卡片有沒有擠壓、編輯面板抽屜在 375px 是否真的滿版無溢出、
閱讀器底部工具列在真機瀏覽器（含 iOS Safari 的視覺 viewport 位址列遮擋）是否真的可單手點到。

### 刻意沒做

同 `BP-SVC-DOUJIN-1`「刻意沒做」段——wishlist、hentaiViewer 資料匯入、標籤/LLM、全庫搜尋
一律 block 2；`impeccable` 完整視覺打磨（teach→shape→craft→audit→critique→polish）尚未
跑過，目前是「功能完整、可用、通過既有元件的樣式慣例」而非「經過設計系統審過」的狀態。
分類（系列）**管理頁面沒有做**（刪除系列的 API 存在且行為已定義——見
`BP-SVC-DOUJIN-1`——但沒有在任何 UI 暴露刪除入口；這輪範圍是「書籍編輯面板內建立/套用
分類」，不含系列管理）。

### 待使用者/PM 決定的開放問題（誠實記錄，不是我自己決定）

- **exhentai 沒有 id 前綴、也還沒有抓取器**：這個庫裡唯一一個 exhentai 資料夾就是沒有
  id 前綴的樣本。就算之後要接 exhentai，還需要 gid+token 兩個值，不是單一數字 id ——
  這條路要怎麼走（要不要接、要不要開放使用者手動貼 gid+token）留給使用者決定。
- **wnacg 現場檢查後沒有接抓取器**（見 `BP-SVC-DOUJIN-1`）——它的頁面沒有結構化的
  作者/社團欄位，只有結構化的頁數。要不要只接「頁數交叉核對」（不動名稱/作者/社團），
  這是一個可以做但這輪沒做的選項，留給使用者決定。
- **18comic 沒有既有供應器**，接不接、值不值得為它另外處理反機器人門檻，同樣留給使用者
  決定。
