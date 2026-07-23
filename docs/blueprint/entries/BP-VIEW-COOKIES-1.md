---
id: BP-VIEW-COOKIES-1
title: Cookie 管理頁（Cookies）
system: frontend
tags: [frontend, view, cookies]
status: 已完成
request_verbatim: "CLAUDE.md「Web UI ... pages: /、/history、/queue、/jobs、/cookies」；router `{ path: '/cookies', name: 'cookies', component: CookiesView }`"
decided_date: 2026-05-21
exec_links:
  - frontend/src/views/CookiesView.vue
  - app/api/routes/misc.py
depends_on:
  - BP-SVC-CREDENTIALS-1
origin: "`frontend/src/views/CookiesView.vue` 首次入庫於 Build ns-media-hub unified workspace（998bfec，2026-05-21）"
---

## 設計說明

`CookiesView.vue`（168 行）提供 cookie 的清單檢視、新增、修改、刪除 UI，對應
`BP-SVC-CREDENTIALS-1` 的 `/api/cookies` CRUD 端點（寫入操作皆受
`BP-CORE-SECURITY-1` 同源 CSRF 防護）。

### 誠實現況

沒有前端自動化測試覆蓋本頁；本頁是否對使用者清楚呈現「這只是本機同源防護、非
帳號驗證」這個安全模型未在本次盤點中確認（屬 UI 文案/實作層級，非本 blueprint
條目粒度）。
