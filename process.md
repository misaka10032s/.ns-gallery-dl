# 開發與流程說明文件

---

## 專案概觀

本專案旨在提供一套自動化、易於擴充的媒體下載解決方案，核心圍繞 `gallery-dl` 工具。透過批次腳本 (`.cmd`, `.sh`)、Python 主程式、Flask 後端伺服器以及 Chrome 擴充功能的組合，為開發者與使用者提供高效的下載管理體驗。

---

## 工作流程

### 腳本執行流程 (`dl.cmd` / `dl.sh`)

1.  **環境檢查**:
    -   檢查 `venv` 虛擬環境是否存在，若無則自動使用 `python -m venv` 建立。
2.  **啟動虛擬環境**:
    -   Windows: `call venv\Scripts\activate.bat`
    -   Linux/macOS: `source venv/bin/activate`
3.  **依賴安裝 (首次執行)**:
    -   透過 `install.flag` 檔案判斷是否為首次執行。
    -   若 `install.flag` 不存在，則執行 `pip install -r requirements.txt` 與 `pip install gallery-dl` 安裝依賴。
4.  **執行主程式**:
    -   執行 `python dl.py`，並將所有命令列參數 (`%*` 或 `$@`) 傳遞給主程式。

### Python 主程式 (`dl.py`)

1.  **參數解析**:
    -   `-s`, `--server`: 啟動 Flask 伺服器，監聽來自 Chrome 擴充功能的 URL 請求。
    -   `-u`, `--update`: 更新 `pip` 和 `gallery-dl`。
    -   `-f`, `--force`: 強制重新下載已存在的檔案。
    -   若無特殊參數，則執行標準下載流程。

2.  **URL 解析 (`module/fetch.py`)**:
    -   讀取 `dl.txt` 檔案並進行正規化處理。

3.  **下載迴圈**:
    -   遍歷 URL，若非強制模式則跳過歷史紀錄中已成功的項目。

4.  **執行下載 (`module/fetch.py`)**:
    -   **特定網站處理**: `nhentai.net` 和 `wnacg.com` 使用自訂下載器，並顯示 `tqdm` 進度條。
    -   **通用下載**: 其他網站透過 `gallery-dl` 處理。
        -   會先用 `--simulate` 取得檔案總數，然後顯示 `tqdm` 進度條。
    -   **認證與重試**: 內建 Pixiv `refresh-token` 處理和網路錯誤重試機制。

---

## 檔案與模組功能

### 根目錄

-   `dl.py`: 主執行腳本，負責流程控制與參數解析。
-   `dl.cmd` / `dl.sh`: 提供跨平台的便捷執行入口。
-   `dl.update.cmd` / `dl.update.sh`: 呼叫 `dl.py -u` 來更新依賴。
-   `dl.server.cmd` / `dl.server.sh`: 呼叫 `dl.py -s` 來啟動伺服器。
-   `dl.txt`: 使用者輸入的下載目標清單。
-   `requirements.txt`: Python 依賴，包含 `Flask`, `tqdm` 等。
-   `history.json`: 下載歷史紀錄。
-   `token.json`: 儲存 OAuth `refresh-token`。

### `module/` - 核心邏輯模組

-   `server.py`: Flask 應用，提供 `/download` API 端點，接收 Chrome 擴充功能發送的 URL 並寫入 `dl.txt`。
-   `fetch.py`: 處理 URL 解析與下載邏輯。
-   `history.py`, `tokens.py`, `config.py`: 分別管理歷史、權杖和設定。

### `module/site/` - 特定網站處理模組

-   `pixiv.py`, `nhentai.py`, `wnacg.py`: 處理特定網站的下載與認證。

### `chromeExtension/` - Chrome 擴充功能

-   **支援網站**: Pixiv, nhentai, wnacg, yande.re。
-   `background.js`: 擴充功能的核心。
    -   接收來自 `content.js` 的 URL 列表。
    -   優先嘗試透過 `fetch` API 將 URL 發送到 `http://127.0.0.1:5001/download`。
    -   若伺服器請求失敗，則會降級，將 URL 複製到剪貼簿，並顯示桌面通知。
-   `content.js` (各網站): 在頁面上注入 checkbox 和 "Export" 按鈕。
-   `manifest.json`: 設定檔，定義權限，包含 `http://127.0.0.1:5001/*` 的主機權限。
