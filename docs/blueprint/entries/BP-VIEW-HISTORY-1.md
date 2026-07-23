---
id: BP-VIEW-HISTORY-1
title: 歷史紀錄頁（History，含刪除/更新狀態/批次 requeue）
system: frontend
tags: [frontend, view, history]
status: 已完成
request_verbatim: "CLAUDE.md「Web UI ... pages: /、/history、/queue、/jobs、/cookies」；router `{ path: '/history', name: 'history', component: HistoryView }`"
decided_date: 2026-05-21
exec_links:
  - frontend/src/views/HistoryView.vue
  - app/api/routes/history.py
depends_on:
  - BP-SVC-HISTORY-1
origin: "`frontend/src/views/HistoryView.vue` 首次入庫於 Build ns-media-hub unified workspace（998bfec，2026-05-21）"
---

## 設計說明

`HistoryView.vue`（418 行，是所有頁面中第二大的 view，僅次於 Gallery）依日期分組顯示
`GET /api/history` 結果，支援單筆刪除（`DELETE /api/history`）、狀態手動修正
（`PUT /api/history`）、批次重新排入佇列（`POST /api/history/requeue`，
`BP-SVC-HISTORY-1`）。

### 誠實現況

沒有前端自動化測試覆蓋本頁；本檔案行數較大（418 行），是否有進一步拆分空間屬前端
實作層級判斷，不在本次 blueprint 程式碼盤點範圍內評論。
