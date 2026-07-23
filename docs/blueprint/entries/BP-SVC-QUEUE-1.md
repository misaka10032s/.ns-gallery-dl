---
id: BP-SVC-QUEUE-1
title: 佇列與工作提交（queue worker + browser_bridge + /api/jobs, /api/queue）
system: backend-service
tags: [backend, service, queue, jobs, api]
status: 已完成
request_verbatim: "process.md「queue_service.py：queue 建立、worker 執行、queue state」；app/main.py bootstrap「啟動 queue worker」"
decided_date: 2026-05-21
exec_links:
  - app/services/queue_service.py
  - app/services/browser_bridge_service.py
  - app/api/routes/jobs.py
  - app/api/routes/queue.py
depends_on:
  - BP-SVC-DOWNLOAD-1
  - BP-SVC-HISTORY-1
origin: "`app/services/queue_service.py`、`app/services/browser_bridge_service.py` 首次入庫於 Build ns-media-hub unified workspace（998bfec，2026-05-21）"
---

## 設計說明

### 佇列 worker（`queue_service.py`）

單一背景 daemon thread（`start_worker()`，`app/main.py::_bootstrap` 啟動）從
`Queue[int]`（job id）依序取件執行，`_run_job()` 讀 job 中繼資料還原
`JobRequest` 後交給 `BP-SVC-DOWNLOAD-1` 的 `download_request()`，完成後寫回
`jobs` 表狀態並補一筆 history。**整個 app 只有一條下載執行緒**——這是刻意的設計
（`updater_service` 的 pip timeout 註解明確提及「這支 worker 是唯一的下載佇列」），
簡化併發控制但代表下載是完全序列化的，沒有平行下載。

`get_state()` 回傳 `{current, pending, total}`：`pending` 來自 SQLite
`jobs_repo.list_pending_urls()`，額外用 `_display_urls`（記憶體內清單）補上「尚未寫進
DB 但已開始處理」的項目（如附件下載中）以及排除當前執行中避免雙重計數，供
`BP-VIEW-QUEUE-1` 輪詢顯示。

### 提交入口（`browser_bridge_service.py`）

`submit_urls()`/`submit_requests()`——薄封裝，把 `JobRequest` 組好後呼叫
`queue_service.enqueue_requests()`。所有外部提交管道（`/api/jobs` POST、`/download`
legacy 相容端點、history 頁面 requeue、job retry）都經這一層，是外部提交與內部佇列
之間唯一的收斂點。

### API 端點

- `POST /api/jobs`：接受 `links[]`/`items[]`、`providerHint`、`meta`（含 extension
  選取模式的 `selected_urls`），回 202。
- `POST /download`：舊版相容端點，等同 `/api/jobs` 但不支援 provider hint/meta。
- `POST /api/jobs/<id>/retry`：讀原 job 的 meta 剔除 attempt 追蹤欄位後重新入隊，
  保留原 provider mode（auto/forced）。
- `GET /api/jobs`：回傳最近 200 筆。
- `GET /api/queue`：回傳目前佇列狀態。

### 誠實現況

無獨立 pytest 覆蓋 worker 執行緒本身或這幾支 API route（`tests/` 下無
`test_queue_service.py`/`test_jobs_route.py`）；`test_meta_preservation.py` 涵蓋
retry 路徑 meta 保留邏輯的一部分。
