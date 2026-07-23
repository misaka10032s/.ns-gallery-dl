---
id: BP-SVC-GALLERY-1
title: 媒體庫瀏覽服務（gallery_service + /api/gallery/* 含 Range 串流）
system: backend-service
tags: [backend, service, gallery, media, api]
status: 已完成
request_verbatim: "@PM registry ns-media-hub.md Roadmap（已勾）：「Media viewer — GalleryView.vue + /api/gallery/* 完整實作（佐證：commit ff31884 親測確認）」"
decided_date: 2026-05-25
exec_links:
  - app/services/gallery_service.py
  - app/api/routes/gallery.py
origin: "`app/services/gallery_service.py` 首次入庫於 commit ff31884（2026-05-25）"
---

## 設計說明

`app/services/gallery_service.py`（162 行）把 `download/` 目錄樹轉成前端媒體庫可用的
分類/項目/檔案三層結構，供 `BP-VIEW-GALLERY-1` 消費。

### 三層瀏覽模型

1. **分類（category）**：`download/` 下的一級子目錄（如 `pixiv.net`、`discord`）。
2. **項目（item）**：分類內的「葉節點」——`_folder_has_only_files()` 判斷一個目錄
   是否「只含檔案、不含子目錄」，是則視為一個 item（如某作者的整個相簿）；不是則
   視為中繼目錄（如 `pixiv.net/`）並遞迴往下找，直到找到真正的葉節點。單一散落檔案
   （不在任何目錄內）也視為獨立 item。
3. **檔案（file）**：item 目錄內的實際檔案清單。

### API 端點

- `GET /api/gallery`：`list_categories()`，各分類含 `item_count`。
- `GET /api/gallery/items?category=`：`list_items()`。
- `GET /api/gallery/files?path=`：`list_files()`。
- `GET /api/gallery/serve?p=`：`resolve_file()` 解析相對路徑（**含逃逸防護**——
  `resolved.is_relative_to(DOWNLOAD_DIR)`，拒絕 `../` 跳出下載目錄），再用
  Flask `send_file` 或**手動實作 HTTP Range 請求**（`Content-Range`/
  `Accept-Ranges` header，支援影片拖曳跳轉播放）串流回傳。

### 誠實現況

`tests/test_gallery_service.py` 覆蓋 `list_categories`/`list_items`/`list_files`
的目錄樹邏輯；`/api/gallery/serve` 的 Range 請求處理本身無獨立 pytest 覆蓋（僅
route 內邏輯直觀，未見自動化驗證影片拖曳情境）。
