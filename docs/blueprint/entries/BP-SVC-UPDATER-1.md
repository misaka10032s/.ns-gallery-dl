---
id: BP-SVC-UPDATER-1
title: 下載器套件自動更新系統（yt-dlp / gallery-dl，reactive + manual）
system: backend-service
tags: [backend, service, updater, yt-dlp, gallery-dl]
status: 已完成
request_verbatim: "@PM registry ns-media-hub.md Roadmap（已勾）：「下載器版本更新系統(yt-dlp/gallery-dl) — pip 統一管理 + 中央套件清單驅動；三觸發點：出錯守衛式自動更新+單次重試...Web UI「更新下載器」鈕...launcher -U；...無排程/啟動更新；103 測試通過；base+delta 雙 reviewer PASS + 375px 行動版目視 OK（merged aa17f60 [build-frontend]；run docs: state/runs/ns-media-hub-downloader-update/）」"
decided_date: 2026-07-22
exec_links:
  - app/services/updater_service.py
  - app/config/downloaders.py
  - app/api/routes/downloaders.py
  - app/storage/repositories/downloader_state_repo.py
qa_log:
  - date: 2026-09-07
    q: "@PM 待回答 N4（2026-09-05 全叢集稽核疑似漏收）：早年提過「gallery-dl 自動更新誤觸」與「Windows pip 安裝 timeout」兩件事，未進任何待辦也無裁定紀錄。現在程式還有自動更新機制嗎？要不要補回待辦？"
    a: "查證（haiku，2026-09-07）：無定時／啟動自動更新；只有下載失敗且判定為提取器過期時才被動 `pip install -U`（`app/services/updater_service.py:105-182`），冷卻 6 小時（`app/config/downloaders.py:19`）、timeout 300 秒（`downloaders.py:25`、`updater_service.py:79`）；啟動腳本 `dl.cmd:47`／`dl.sh:54` 只在版本不符或帶 `-u` 時才 `pip install --upgrade`（無 timeout，但不會誤觸）。兩件舊問題在現行機制下不會發生。站主原話：「N4 結案」——**結案，不補待辦**。"
origin: "`app/services/updater_service.py`、`app/config/downloaders.py` 首次入庫於 commit 0122272（2026-07-22），merge commit aa17f60（同日）"
---

## 設計說明

CLAUDE.md 有專節記載此系統（見 CLAUDE.md「Downloader package updates」）——本條目是
其在 blueprint 中的功能級對應紀錄。中央註冊表 `app/config/downloaders.py`
`DOWNLOADER_PACKAGES = {"ytdlp": "yt-dlp", "gallery-dl": "gallery-dl"}`：新增下載器
只需在此加一行，`updater_service`、手動 API、launcher `-U` 都自動derive。

### 三個觸發點

1. **Reactive（出錯守衛式）**：`BP-SVC-DOWNLOAD-1` 偵測到失敗訊息符合
   `STALE_EXTRACTOR_SIGNATURES`（"cannot parse data" / "unable to extract" /
   "failed to parse json data" / "an unexpected error occurred"，逐一對照真實
   gallery-dl CLI 輸出格式驗證過）時呼叫 `maybe_reactive_update()`：若在 6 小時
   cooldown 內且已確認為最新版，直接跳過（不重複 pip 呼叫）；否則執行
   `pip install -U <package>`（300 秒逾時），版本確實變動才觸發**單次**重試
   （每 job 硬上限，見 `BP-SVC-DOWNLOAD-1`）。
2. **手動**：`POST /api/downloaders/update`（同源 CSRF 防護，佇列忙碌中回 409
   拒絕——避免與進行中的下載子行程搶佔）+ Web UI 標頭「更新下載器」按鈕。
3. **Launcher `-U`**：`dl.cmd -u`/`dl.sh -u` 強制更新所有註冊套件（進 Python 前，
   shell 腳本層處理）。

### 反無腦更新迴圈設計

`downloader_state_repo`（SQLite `downloader_state` 表）記錄每套件最後確認版本與
時間戳；timeout 時**不落地**任何狀態（避免誤判「已確認最新」壓制真正需要的下一次
檢查）；已確認最新時**仍落地**（刷新 cooldown），回覆清楚的「已是最新，非版本問題」
訊息取代原始 extractor 錯誤字串。**明確不做**排程/每次啟動自動更新（CLAUDE.md 設計
決策，保持啟動速度、避免無謂上游churn）。

### 誠實現況

Registry 記載「103 測試通過、base+delta 雙 reviewer PASS + 375px 行動版目視 OK」為
merge 當下（commit aa17f60）的驗收證據；本 blueprint 未重跑這批測試，故不在本條目
填 `tests:` 結構化紀錄（避免把 registry 的敘述性文字包裝成看似本次驗證過的結構化
資料）——如需查證，`tests/test_updater_service.py`/`test_downloaders_route.py` 為
對應測試檔案，可自行執行 `py -3.11 -m pytest tests/test_updater_service.py
tests/test_downloaders_route.py` 複驗。
