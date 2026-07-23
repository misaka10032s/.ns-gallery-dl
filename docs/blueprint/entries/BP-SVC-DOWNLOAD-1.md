---
id: BP-SVC-DOWNLOAD-1
title: 下載請求核心調度（URL 正規化／provider 分流與 fallback／reactive 更新整合）
system: backend-service
tags: [backend, service, download, orchestration]
status: 已完成
request_verbatim: "process.md「download_service.py：URL 正規化、provider 分流、history payload」；dl.txt/CLI 舊縮寫轉正式 URL：p123.../pu123.../pw123.../n123.../w123.../x"
decided_date: 2026-05-21
exec_links:
  - app/services/download_service.py
  - app/main.py
depends_on:
  - BP-PROV-GALLERYDL-1
  - BP-PROV-YTDLP-1
  - BP-PROV-DIRECTFILE-1
  - BP-SVC-UPDATER-1
origin: "`app/services/download_service.py` 首次入庫於 Build ns-media-hub unified workspace（998bfec，2026-05-21）"
---

## 設計說明

`app/services/download_service.py`（203 行）是整個下載流程的中樞，三種呼叫來源
（CLI 批次模式 `app/main.py::run_batch_download`、Discord bot `BP-BOT-1`、佇列 worker
`BP-SVC-QUEUE-1`）最終都收斂到這裡的 `download_request()`。

### 舊縮寫展開（`expand_url_shortcut`）

`p123`/`pw123` → Pixiv artwork、`pu123` → Pixiv user、`n123` → nhentai gallery、
`w123` → wnacg photo index。CLI 批次模式（`dl.txt`）與 Discord bot 訊息解析都走
這個共用函式，維持行為一致。

### Provider 分流與 fallback 鏈（`provider_candidates` / `download_request`）

```mermaid
flowchart TD
    A[download_request] --> B[provider_candidates 依 domain 決定候選清單]
    B --> C{host 屬於<br/>MULTI_PROVIDER_DOMAINS<br/>facebook/x.com}
    C -- 是 --> D["[GALLERY_DL, YTDLP] 依序嘗試"]
    C -- 否，屬 YTDLP_DOMAINS --> E[YTDLP]
    C -- 否 --> F[GALLERY_DL]
    D --> G[逐一嘗試 provider]
    E --> G
    F --> G
    G -- SUCCESS/SKIPPED --> H[終態，回傳，不再試下一 provider]
    G -- FAILED 且疑似過期擷取器 --> I["updater_service.maybe_reactive_update()<br/>（每 job 至多觸發一次）"]
    I -- 有重試 --> J[原 provider 重試一次]
    I -- 無重試/非過期擷取器 --> K[換下一個候選 provider]
    J --> H
    K --> G
```

- **每 job 硬上限一次**自動更新重試（`update_retry_used` 旗標），避免更新→失敗→更新
  無限迴圈——即使一個 job 有多個候選 provider 也只觸發一次。
- 每次嘗試都記錄進 `attempts` 清單（provider/status/error/是否為自動更新重試），
  最終寫入 job 的 `meta.attempts`，供前端 Jobs 頁（`BP-VIEW-JOBS-1`）與歷史紀錄
  追溯完整重試軌跡。

### 誠實現況

`tests/test_download_service.py` + `test_download_service_reactive_update.py` 對
`provider_candidates`／reactive 更新整合路徑有 pytest 覆蓋；完整端到端下載（實際呼叫
provider 子行程）未覆蓋（provider 層各自的誠實現況見對應 `BP-PROV-*` 條目）。
