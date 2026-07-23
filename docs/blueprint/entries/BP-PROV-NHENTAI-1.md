---
id: BP-PROV-NHENTAI-1
title: nhentai.net 站台下載器
system: backend-provider
tags: [backend, provider, nhentai, site-specific]
status: 已完成
request_verbatim: "CLAUDE.md「Site-specific logic：Preserve nhentai + wnacg specialized download logic — do not generalise away」；process.md「providers/sites/：Pixiv / nhentai / wnacg 特化處理」"
decided_date: 2026-05-21
exec_links:
  - app/providers/sites/nhentai.py
  - app/providers/gallery_dl/provider.py
origin: "`app/providers/sites/nhentai.py` 首次入庫於 Build ns-media-hub unified workspace（998bfec，2026-05-21，本專案初始整合 commit）"
---

## 設計說明

`app/providers/sites/nhentai.py`（95 行）是 nhentai.net 本子頁的專用下載器，由
`app/providers/gallery_dl/provider.py` 依網域 `nhentai.net` 分派呼叫（`download()`
第 164-167 行）。使用 `cloudscraper` + `BeautifulSoup` 解析頁面圖片清單，
`BoundedSemaphore(5)` 併發下載，`tqdm` 顯示進度，檔名以 `_remove_illegal_chars`
過濾 Windows 非法字元並截斷至 150 字。

### 為何需要特化邏輯（而非直接用通用 gallery-dl CLI）

nhentai 有反爬蟲/CDN 特性，通用 gallery-dl extractor 對此站的行為不穩定；本專案自行
維護一份輕量 scraper，繞開對外部 CLI 的依賴。CLAUDE.md 明確要求保留此特化邏輯，不可
簡化併回通用路徑。

### 誠實現況

沒有針對本檔的獨立 pytest 覆蓋；`download/` 目錄下有真實下載內容作為功能存在的旁證，
但不構成結構化測試紀錄，故不填 `tests:` 區塊。
