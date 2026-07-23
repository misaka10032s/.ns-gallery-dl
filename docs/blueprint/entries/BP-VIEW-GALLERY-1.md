---
id: BP-VIEW-GALLERY-1
title: 媒體庫頁（Gallery — 巢狀分類瀏覽 + 影音預覽/串流）
system: frontend
tags: [frontend, view, gallery, media]
status: 已完成
request_verbatim: "@PM registry ns-media-hub.md Roadmap（已勾）：「Media viewer — GalleryView.vue + /api/gallery/* 完整實作（佐證：commit ff31884 親測確認）」；todolist.txt「OK 網頁UI: 在網頁閱讀下載來的檔案（/gallery + GalleryView.vue + /api/gallery/* 已完成）」"
decided_date: 2026-05-25
exec_links:
  - frontend/src/views/GalleryView.vue
  - app/api/routes/gallery.py
  - app/api/routes/pages.py
depends_on:
  - BP-SVC-GALLERY-1
origin: "`frontend/src/views/GalleryView.vue` 首次入庫於 commit ff31884（2026-05-25）"
---

## 設計說明

`GalleryView.vue`（555 行，全站最大 view）是「在網頁內直接瀏覽已下載媒體」的功能，
消費 `BP-SVC-GALLERY-1` 的三層 API（分類→項目→檔案）+ `/api/gallery/serve` 的
Range 串流播放。路由 `/gallery` 由 `app/api/routes/pages.py` 註冊 SPA fallback
（`send_from_directory(UI_DIR, "index.html")`），支援瀏覽器直接整頁載入/重新整理
不 404。

### 誠實現況 —— 本次盤點的重要修正

**@PM registry 現行仍記載一筆未勾待辦**：「`/gallery` SPA fallback — SPA 路由
fallback 缺失，直接瀏覽 `/gallery` 404」。但程式碼核對（`app/api/routes/pages.py`
第 17 行 `app.add_url_rule("/gallery", ...)`）與 `git log` 顯示這個路由已於
**2026-06-20（commit f2718f1，同一支 commit 也補上 CSRF+WAL）**註冊完成，與同筆
registry 記載的「Media viewer 已完成」（佐證 commit ff31884，2026-05-25）本身就
有內部矛盾——ff31884 建立 view 時這個 fallback 路由還沒加，f2718f1 才補上。
本條目以程式碼現況為準：**SPA fallback 已存在，非待辦**。

### 誠實現況 —— 其餘

本頁是全站第二大（555 行，僅次於 History 頁的部分行數差距不大）；是否有進一步拆分
空間屬前端實作層級判斷。無前端自動化測試覆蓋本頁；`/api/gallery/serve` 的 Range
串流亦無獨立測試（見 `BP-SVC-GALLERY-1`）。
