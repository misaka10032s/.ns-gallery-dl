# 開發與流程說明文件

---

## 專案概觀

`ns-media-hub` 是目前的正式架構。  
這個 repo 已將原本的 `ns-gallery-dl`、`ns-yt-dlp` 行為整合成單一執行核心，並吸收 `ns-chrome-tool` 的 Chrome 擴充功能能力。

核心目標：

- 統一 `gallery-dl` / `yt-dlp` 下載入口
- 統一 Discord bot、Web UI、Chrome extension 與本機 API
- 將歷史紀錄、工作佇列、cookie registry 收斂到 SQLite
- 保留必要的舊入口相容，但以 `app/` 為唯一正式實作

---

## 執行流程

### 啟動腳本 (`dl.cmd` / `dl.sh`)

1. 檢查虛擬環境是否存在
2. 啟動虛擬環境
3. 依 `install.flag` 與 script version 決定是否更新依賴
4. 執行 `python dl.py`

### Python 主入口 (`dl.py`)

`dl.py` 現在只負責轉進：

```python
from app.main import main
```

真正的執行流程在 `app/main.py`：

1. `_bootstrap()`
   - 建立 `data/`、`download/`
   - 若有啟動 server，先檢查 `frontend/` 是否需要自動 build
   - 初始化 SQLite
   - 掃描 cookie registry
   - 啟動 queue worker
2. 解析 CLI 參數
3. 分流成以下模式：
   - `-s`：啟動 Flask API / UI
   - `-b`：啟動 Discord bot
   - `-s -b`：同時啟動 server + bot
   - 無參數：讀取 `dl.txt` 並執行批次下載

### 下載流程

1. 讀取 `dl.txt` 或 CLI URLs
2. 將舊縮寫轉成正式 URL
   - `p123...`
   - `pu123...`
   - `pw123...`
   - `n123...`
   - `w123...`
   - `x`
3. 用 `history_service.filter_by_history()` 去除已成功項目
4. 由 `download_service` 依網域決定 provider：
   - `gallery-dl`
   - `yt-dlp`
   - `direct-file`（bot 圖片附件 / embed）
5. 將結果寫回 SQLite history / jobs

---

## 目前正式結構

### 根目錄

- `dl.py`: Python 入口，導向 `app.main`
- `dl.cmd` / `dl.sh`: 啟動腳本
- `readme.md`: 使用文件
- `process.md`: 開發與架構說明
- `requirements.txt`: Python 依賴
- `frontend/`: Vue + Vite + Pinia 前端 source
- `chromeExtension/`: 單一正式 Chrome extension 套件
- `app/`: 正式 backend / provider / storage / UI
- `module/`: 舊匯入相容層

### `app/`

#### `app/main.py`

- 真正的 CLI 與模式入口
- 整合 server / bot / batch download

#### `app/config/`

- `paths.py`: 全域路徑定義
- `settings.py`: `.env`、bot 網域規則、provider domain 設定
- `features.py`: 功能旗標

#### `app/domain/`

- `jobs.py`: JobRequest / DownloadResult / QueueState
- `enums.py`: Provider / JobSource / JobStatus

#### `app/services/`

- `download_service.py`: URL 正規化、provider 分流、history payload
- `queue_service.py`: queue 建立、worker 執行、queue state
- `history_service.py`: history 查詢 / 更新
- `discord_service.py`: Discord bot 流程
- `browser_bridge_service.py`: extension / API 送件橋接
- `token_service.py`: token 讀寫
- `path_service.py`: 下載路徑規則與檔名生成

#### `app/providers/`

- `gallery_dl/provider.py`: `gallery-dl` 流程
- `ytdlp/provider.py`: `yt-dlp` 流程
- `sites/`: Pixiv / nhentai / wnacg 特化處理
- `cookies/`: cookie metadata / scan / resolve

#### `app/storage/`

- `db.py`: SQLite 連線、schema 初始化、舊 history 遷移
- `repositories/`: jobs / history / cookies 存取層

#### `app/api/`

- `app.py`: `create_app()` 與 bootstrap
- `routes/`: 已拆分的 Flask route 模組
  - `pages.py`
  - `history.py`
  - `queue.py`
  - `jobs.py`
  - `auth.py`
  - `misc.py`

#### `app/ui/`

- Vite build 輸出目錄
- Flask 透過 `static_url_path="/ui"` 提供 assets
- `/`、`/history`、`/queue`、`/jobs`、`/cookies` 都回傳同一個 SPA entry

#### `frontend/`

- `src/router/`: Vue router 頁面路由
- `src/stores/`: Pinia 狀態管理
- `src/views/`: dashboard / history / queue / jobs / cookies
- `src/components/`: header / toast / status / quick submit 等共用元件
- `vite.config.js`: build 到 `app/ui/`

> 現在的正式前端模型是：`frontend/` 負責 source，`app/ui/` 負責 build 輸出與 Flask 提供。

### `module/`

`module/` 現在不再承載正式實作，只保留相容性用途：

- 舊模組匯入仍能成功
- 實際功能都轉呼叫 `app/` 內的新服務

這代表目前程式碼已具備「正式架構在 `app/`、舊入口在 `module/`」的清楚分層。

### `chromeExtension/`

這是目前唯一正式 Chrome extension 套件：

- 原本 selector 匯出功能
- 整合 `ns-chrome-tool` 的 context menu / omnibox / redirect cleanup / popup
- `yt-dlp` 右鍵下載改成走本機 API
- 不再依賴 native messaging

主要結構：

- `background/`: service worker 入口與 offscreen helper
- `core/`: API / notification 小模組
- `static/module/`: NStools 核心模組
- `static/js/`: 第三方前端工具
- `static/template/`: popup / console UI
- `pixiv/`, `nhentai/`, `wnacg/`, `yande.re/`, `facebook/`: 各站 content scripts

---

## 資料與儲存

### SQLite

主要資料庫：`data/app.db`

目前包含：

- `jobs`
- `history_entries`
- `cookie_entries`

### 舊 history 匯入

`app/storage/db.py` 會在初始化時：

1. 建立新 schema
2. 檢查 `data/history.json`
3. 若 `history_entries` 還是空表，就自動匯入舊紀錄

### Cookie 掃描位置

- `cookies/`

舊版若仍存在 `data/cookies/` 或 `module/cookies/` 內容，初始化掃描時會自動搬移到 `cookies/`。

> `cookies/*` 為本機私有檔案，已納入 git ignore。

---

## 下載路徑策略

目前採用網域導向：

```text
download/
  discord/
    <guild>/
      attachments/
      embeds/
  gallery-dl/
    pixiv.net/
      <author>/
    nhentai.net/
    wnacg.com/
    yande.re/
  ytdlp/
    youtube.com/
    x.com/
    facebook.com/
```

規則：

- Discord：只分 guild，不分 channel
- Pixiv：分到作者層級
- YouTube / X / Facebook：只分網域

---

## 純化後目前仍保留的過渡設計

雖然正式架構已移到 `app/`，目前還保留兩個有意識的過渡點：

1. `module/` 相容層
   - 目的：避免舊匯入馬上壞掉
2. `chromeExtension/static/module/*`
   - 目前是整合後可運作版本
   - 未來若要再純化，可再逐步重拆成更細的 feature module

這兩者都不是缺失，而是「為了兼容與功能完整度保留的過渡層」。
