---
id: BP-VIEW-QUEUE-1
title: 下載佇列頁（Queue）
system: frontend
tags: [frontend, view, queue]
status: 已完成
request_verbatim: "CLAUDE.md「Web UI ... pages: /、/history、/queue、/jobs、/cookies」；router `{ path: '/queue', name: 'queue', component: QueueView }`"
decided_date: 2026-05-21
exec_links:
  - frontend/src/views/QueueView.vue
  - app/api/routes/queue.py
depends_on:
  - BP-SVC-QUEUE-1
origin: "`frontend/src/views/QueueView.vue` 首次入庫於 Build ns-media-hub unified workspace（998bfec，2026-05-21）"
---

## 設計說明

`QueueView.vue`（126 行）顯示目前佇列狀態，消費 `GET /api/queue`
（`BP-SVC-QUEUE-1::get_state()`）——`current`（正在下載的 URL）+ `pending`
（等待中清單）+ `total`。透過 Pinia store（`frontend/src/stores/hub.js`）輪詢
更新，讓使用者即時看到佇列消化進度。

### 誠實現況

沒有前端自動化測試覆蓋本頁；輪詢頻率/機制細節屬實作層級，未在本次盤點中逐行核對
（若需要，應查 `stores/hub.js` 的輪詢邏輯，非本 blueprint 條目粒度）。
