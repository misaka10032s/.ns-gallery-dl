# 開發與流程說明文件

---

## 專案概觀

本專案旨在提供一套自動化、易於擴充的媒體下載解決方案，核心圍繞 `gallery-dl` 工具。透過批次腳本 (`.cmd`, `.sh`)、Python 主程式以及 Chrome 擴充功能的組合，為開發者與使用者提供高效的下載管理體驗。

---

## 工作流程

### 腳本執行流程 (`dl.cmd` / `dl.sh`)

1.  **環境檢查**:
    -   檢查 `venv` 虛擬環境是否存在，若無則自動使用 `python -m venv` 建立。
    -   此設計確保所有依賴套件與主機環境隔離。

2.  **啟動虛擬環境**:
    -   Windows: `call venv\Scripts\activate.bat`
    -   Linux/macOS: `source venv/bin/activate`

3.  **依賴安裝 (首次執行)**:
    -   透過 `install.flag` 檔案判斷是否為首次執行。
    -   若 `install.flag` 不存在，則執行 `pip install -r requirements.txt` 與 `pip install gallery-dl` 安裝依賴。
    -   安裝成功後建立 `install.flag`，避免後續重複安裝。

4.  **執行主程式**:
    -   執行 `python dl.py`，並將所有命令列參數 (`%*` 或 `$@`) 傳遞給主程式。

5.  **腳本結束**:
    -   `dl.cmd`: 透過 `pause` 指令暫停，讓使用者確認執行結果。
    -   `dl.sh`: 透過 `read -p` 達到相同效果。

### Python 主程式 (`dl.py`)

1.  **初始化**:
    -   載入 `history.json` 的下載歷史與 `token.json` 的認證權杖。
    -   解析命令列參數，檢查是否存在 `-f` 或 `-force` 強制下載旗標。

2.  **URL 解析 (`module/fetch.py`)**:
    -   讀取 `dl.txt` 檔案。
    -   對每行進行正規化處理，支援以下速記法：
        -   `p<ID>` → `https://www.pixiv.net/artworks/<ID>`
        -   `x` → `https://x.com`
        -   自動為無 `http(s)://` 前綴的網址補上 `https://`。

3.  **下載迴圈**:
    -   遍歷所有待下載的 URL。
    -   若非強制下載模式，則檢查該 URL 是否已存在於 `downloaded_all` 集合 (來自 `history.json`)，若存在則跳過。

4.  **執行下載 (`module/fetch.py`)**:
    -   **特定網站處理**: 若 URL 為 `nhentai.net` 或 `wnacg.com`，則呼叫對應的下載函數，並顯示圖片下載進度條。
    -   **認證處理**: 若 URL 為 Pixiv 網址，則透過 `get_pixiv_token` 取得 `refresh-token`，並將其設定於環境變數 `GALLERYDL_PIXIV_REFRESH_TOKEN` 中。
    -   **子程序呼叫**: 透過 `subprocess.run` 呼叫 `gallery-dl` 執行下載。
        -   `check=True`: 確保下載失敗時會拋出 `CalledProcessError` 例外。
        -   `gallery-dl` 的原生進度條會直接顯示在終端機中。
    -   **重試機制**:
        -   若下載失敗 (捕獲 `CalledProcessError`)，則進行重試，最多 `MAX_RETRIES` (10) 次。
        -   若錯誤訊息包含 `timed out` 或 `connection`，則判定為網路問題，延遲 `RETRY_DELAY` (5) 秒後重試。
        -   若為 Pixiv 且錯誤為 `'refresh-token' required`，則觸發 `get_pixiv_token` 重新認證流程。

5.  **儲存結果**:
    -   將本次執行的所有下載結果 (無論成功或失敗) 記錄到 `history.json` 的今日日期底下。

---

## 檔案與模組功能

### 根目錄

-   `dl.py`: 主執行腳本，負責流程控制。
-   `dl.cmd` / `dl.sh`: 提供跨平台的便捷執行入口，管理虛擬環境與依賴。
-   `dl.update.cmd` / `dl.update.sh`: 手動更新 `pip` 與 `gallery-dl` 的腳本。
-   `dl.txt`: 使用者輸入的下載目標清單。
-   `requirements.txt`: Python 依賴描述檔，包含 `requests`, `beautifulsoup4`, `cloudscraper`, `lxml`, `tqdm`。
-   `history.json`: JSON 格式的下載歷史紀錄。
-   `token.json`: 儲存外部服務 (如 Pixiv) 的 OAuth `refresh-token`。

### `module/` - 核心邏輯模組

-   `config.py`: 集中管理所有靜態設定，如檔案路徑、重試次數等。
-   `fetch.py`: 處理 URL 解析與 `gallery-dl` 的實際呼叫、重試邏輯。
-   `history.py`: 負責 `history.json` 的讀取與寫入。
-   `tokens.py`: 負責 `token.json` 的讀取與寫入。

### `module/site/` - 特定網站處理模組

-   `pixiv.py`: 專門處理 Pixiv 的 OAuth 認證流程。
    -   當 `token.json` 中無 `refresh-token` 或 token 失效時，會呼叫 `gallery-dl oauth:pixiv` 讓使用者重新認證，並自動從 `~/.config/gallery-dl/config.json` 讀取新 token。
-   `nhentai.py`: 處理 `nhentai.net` 的下載，包含圖片下載進度條。
-   `wnacg.py`: 處理 `wnacg.com` 的下載，包含圖片下載進度條。

### `chromeExtension/` - Chrome 擴充功能

-   `manifest.json`: 擴充功能的設定檔，定義了內容腳本的注入目標 (`https://www.pixiv.net/users/*`) 與所需權限。
-   `content.js`: 注入到目標網頁的 JavaScript。
    -   使用 `MutationObserver` 監聽頁面 DOM 變化，確保動態載入的內容也能被處理。
    -   遍歷所有包含 `<img>` 的 `<a>` 連結，並在其父容器上疊加一個 checkbox。
    -   在頁面左下角新增一個 "Export" 按鈕，點擊後會收集所有被選中的 checkbox 對應的作品 ID，並以 JSON 陣列的形式透過 `alert()` 顯示。
-   `style.css`: 為 checkbox 和按鈕提供基本樣式。
