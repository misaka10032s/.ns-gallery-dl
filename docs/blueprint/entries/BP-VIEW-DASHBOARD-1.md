---
id: BP-VIEW-DASHBOARD-1
title: 總覽頁（Dashboard）
system: frontend
tags: [frontend, view, dashboard, a11y-gap]
status: 已完成
request_verbatim: "CLAUDE.md「Web UI: http://127.0.0.1:7601/ — pages: /、/history、/queue、/jobs、/cookies」；router `{ path: '/', name: 'dashboard', component: DashboardView, meta: { title: '總覽' } }`"
decided_date: 2026-05-21
exec_links:
  - frontend/src/views/DashboardView.vue
  - app/api/routes/misc.py
  - frontend/src/components/AppHeader.vue
origin: "`frontend/src/views/DashboardView.vue` 首次入庫於 Build ns-media-hub unified workspace（998bfec，2026-05-21）"
---

## 設計說明

`DashboardView.vue`（141 行）是 SPA 首頁（`/`），消費 `GET /api/dashboard`
（`app/api/routes/misc.py::dashboard`）一次性聚合回傳的四塊資料：佇列狀態
（`BP-SVC-QUEUE-1`）、工作計數與最近工作（`jobs.counts`/`jobs.recent`）、
歷史統計（`history_repo.summary()`）、cookie 數量（`cookies_repo.count_cookies()`）。
另有 `QuickSubmitPanel.vue`（快速提交下載連結）、`StatCard.vue`/`CompactPanelCard.vue`
等共用元件組成總覽卡片版面。

### 全站共用：AppHeader 已知 a11y 缺口

`AppHeader.vue`（106 行，所有頁面共用的頂部列，含「重新整理」「更新下載器」等純圖示
按鈕）目前**沒有任何 `aria-label`/`title` 屬性**（程式碼盤點：`grep aria-label|title=`
零匹配）。這不是 Dashboard 專屬問題，而是全站級——375px 行動版下純圖示按鈕的文字被
隱藏後，螢幕閱讀器無法得知按鈕名稱。@PM registry 已記載此為低優先待辦，本次程式碼
核對確認現況與 registry 記載一致（仍未修）。

### 誠實現況

無獨立 pytest/前端測試覆蓋本頁；`/api/dashboard` 端點無獨立測試檔。
