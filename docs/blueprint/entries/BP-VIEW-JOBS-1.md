---
id: BP-VIEW-JOBS-1
title: 工作紀錄頁（Jobs，含重試）
system: frontend
tags: [frontend, view, jobs]
status: 已完成
request_verbatim: "CLAUDE.md「Web UI ... pages: /、/history、/queue、/jobs、/cookies」；router `{ path: '/jobs', name: 'jobs', component: JobsView }`"
decided_date: 2026-05-21
exec_links:
  - frontend/src/views/JobsView.vue
  - app/api/routes/jobs.py
depends_on:
  - BP-SVC-QUEUE-1
origin: "`frontend/src/views/JobsView.vue` 首次入庫於 Build ns-media-hub unified workspace（998bfec，2026-05-21）"
---

## 設計說明

`JobsView.vue`（150 行）顯示 `GET /api/jobs`（最近 200 筆）——每筆含 provider/
status/domain/download_path/`meta.attempts`（`BP-SVC-DOWNLOAD-1` 記錄的完整
provider fallback + reactive 更新重試軌跡）。提供單筆「重試」動作，呼叫
`POST /api/jobs/<id>/retry`（`BP-SVC-QUEUE-1`）。

### 誠實現況

沒有前端自動化測試覆蓋本頁；`meta.attempts` 這類巢狀診斷資料在 UI 上如何呈現
（是否有摺疊/展開等細節）屬像素級實作，未在本次程式碼盤點逐一核對。
