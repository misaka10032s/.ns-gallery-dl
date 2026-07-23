---
id: BP-SVC-HISTORY-1
title: 歷史紀錄服務（history_service + /api/history 含 requeue）
system: backend-service
tags: [backend, service, history, api]
status: 已完成
request_verbatim: "process.md「history_service.py：history 查詢 / 更新」；CLAUDE.md「Data storage: Legacy data/history.json auto-migrates to SQLite on init」"
decided_date: 2026-05-21
exec_links:
  - app/services/history_service.py
  - app/api/routes/history.py
  - app/storage/db.py
origin: "`app/services/history_service.py` 首次入庫於 Build ns-media-hub unified workspace（998bfec，2026-05-21）"
---

## 設計說明

`app/services/history_service.py`（38 行）是薄封裝層，實際查詢邏輯在
`app/storage/repositories/history_repo.py`（見 `BP-CORE-STORAGE-1`）。核心操作：
`load_history()`（依日期分組）、`filter_by_history()`（去除已成功過的 URL，供 CLI
批次模式與 Discord bot 避免重複下載）、`add_to_history()`（下載完成後 upsert）、
`delete_from_history()`/`update_history_status()`（使用者手動編輯）。

### API 端點（`app/api/routes/history.py`）

- `GET /api/history`：依日期分組回傳。
- `DELETE /api/history`：需 `date`+`url`。
- `PUT /api/history`：需 `date`+`url`+`status`（限 `JobStatus` 合法值）。
- `POST /api/history/requeue`：批次重新排入佇列——接受 `items[]`（含 provider/meta）
  或簡化的 `links[]`；provider_mode 未指定時，`DIRECT_FILE` 視為 forced、其餘視為
  auto，經 `browser_bridge_service`（`BP-SVC-QUEUE-1`）入隊。

### 誠實現況

`history_entries` 表以 `url` 為 UNIQUE key，**只存每個 URL 的最新狀態**，不是
append-only 的完整下載日誌——同一 URL 重複下載會覆蓋前一筆紀錄，而非累積多筆歷史。
這點在資料庫 schema 註解中已明確標註，非缺陷但使用者應知悉「歷史」一詞在此指
「目前已知狀態」而非「完整事件流」。無獨立 pytest 覆蓋這幾支 API route。
