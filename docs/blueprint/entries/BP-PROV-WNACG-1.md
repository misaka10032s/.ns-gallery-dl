---
id: BP-PROV-WNACG-1
title: wnacg.com 站台下載器
system: backend-provider
tags: [backend, provider, wnacg, site-specific]
status: 已完成
request_verbatim: "CLAUDE.md「Site-specific logic：Preserve nhentai + wnacg specialized download logic — do not generalise away」；process.md「providers/sites/：Pixiv / nhentai / wnacg 特化處理」"
decided_date: 2026-05-21
exec_links:
  - app/providers/sites/wnacg.py
  - app/providers/gallery_dl/provider.py
origin: "`app/providers/sites/wnacg.py` 首次入庫於 Build ns-media-hub unified workspace（998bfec，2026-05-21）"
---

## 設計說明

`app/providers/sites/wnacg.py`（144 行）是 wnacg.com 本子頁的專用下載器，由
`app/providers/gallery_dl/provider.py` 依網域 `wnacg.com` 分派呼叫（`download()`
第 169-172 行）。除圖片直抓外，額外支援**壓縮檔下載並解壓**：
可選依賴 `py7zr`（`.7z`）與 `rarfile`（`.rar`），皆以 `try/except ImportError` 包裹
（缺套件時該格式跳過，不中斷其他格式）；`zipfile`（標準庫）恆可用。
`_config_link()` 解析頁面內嵌 script 取得下載設定，`cloudscraper` + `BeautifulSoup`
處理反爬蟲頁面。

### 誠實現況

`py7zr`/`rarfile` 屬選用依賴 —— 若執行環境未安裝，對應壓縮格式的檔案會靜默跳過而非
報錯；本 blueprint seeding 未逐一驗證這兩個套件目前是否已裝在 `requirements.txt`／
`venv`（若要精確判斷，需查 `requirements.txt` 內容，非本次程式碼盤點範圍）。
沒有針對本檔的獨立 pytest 覆蓋；`download/wnacg/` 目錄下有真實下載內容作為功能存在的
旁證，但不構成結構化測試紀錄，故不填 `tests:` 區塊。
