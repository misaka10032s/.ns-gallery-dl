---
id: BP-PROV-BAHAMUT-1
title: 巴哈姆特（forum.gamer.com.tw）站台下載器
system: backend-provider
tags: [backend, provider, bahamut, site-specific]
status: 已完成
request_verbatim: "@PM registry ns-media-hub.md Roadmap: 「Bahamut Co.php 單一樓層下載 — bahamut.py 新增 Co.php 模式（佐證：實測 158 圖下載成功，reviewer PASS-WITH-NOTES，merged be3a151）」「巴哈 C.php/Co.php 選取下載 — extension 選取模式擴及巴哈，選取圖經 POST /api/jobs meta.selected_urls 走 queue 精準下載 baha_sel_*」"
decided_date: 2026-05-25
exec_links:
  - app/providers/sites/bahamut.py
  - app/providers/gallery_dl/provider.py
origin: "`app/providers/sites/bahamut.py` 首次入庫於 commit ff31884（2026-05-25，「Bahamut Co.php 單一樓層下載」）；選取下載精準下載擴充見 commit cd5928f（registry 記載，未逐一 blame 驗證每行）"
revisions:
  - date: 2026-07-23
    summary: "blueprint seeding：核對現行程式碼與 registry roadmap 描述一致，登記為本條目"
---

## 設計說明

`app/providers/sites/bahamut.py`（245 行）是巴哈姆特哈拉板圖片的專用下載器，由
`app/providers/gallery_dl/provider.py` 依網域（`forum.gamer.com.tw` / `gamer.com.tw`）
分派呼叫（見該檔 `download()` 函式第 174-178 行）。

### 支援的頁面型態

- **C.php**（討論串全串）：抓取所有樓層的圖片。
- **Co.php**（單一樓層）：只抓該樓層。
- 兩種頁面共用同一套解析（`BeautifulSoup` + `cloudscraper`），以 `MAX_THREADS = 5` 的
  `BoundedSemaphore` 併發下載，`tqdm` 顯示進度。

### 精準選取下載（`selected_urls`）

`download_bahamut(url, root, selected_urls=selected_urls)` 接受一組由 Chrome extension
選取模式（見 `BP-EXT-SELECTION-1`）送出的圖片 URL 清單（走 `POST /api/jobs`
`meta.selected_urls`），只下載使用者實際勾選的圖片，而非整篇/整樓所有圖。此路徑的 job
命名慣例為 `baha_sel_*`（依 registry roadmap 記載）。

### 誠實現況

沒有針對本檔的獨立 pytest 覆蓋（`tests/` 目錄下無 `test_bahamut*.py`）；功能正確性目前
依賴 registry roadmap 記載的人工/reviewer 現場驗證記錄（「實測 158 圖下載成功」「reviewer
live 驗證 3 圖精準落地」），非本 blueprint 可驗證的結構化測試紀錄，故本條目不填
`tests:` 區塊 —— 避免捏造。
