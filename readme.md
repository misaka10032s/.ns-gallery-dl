# 批量下載工具需求與實作說明

---

## 目標

製作一套基於 Python 與 `gallery-dl` 的批量下載工具，支援從 `dl.txt` 讀取多條連結，下載 Twitter (X)、Pixiv、Facebook 等網站圖片，並具備以下功能：

- 自動檢查並安裝 Python 與 `gallery-dl`
- 支援 Pixiv OAuth 認證管理
- 支援下載歷史紀錄，避免重複下載
- 錯誤自動重試機制（最多 10 次）
- 動態下載動畫提示 (進度顯示)
- 支援命令列強制下載參數 (`-f` / `-force`)

---

## 檔案說明

| 檔案        | 功能說明                                   |
| ----------- | ------------------------------------------ |
| `dl.cmd`    | Windows 批次檔，檢查 Python 與 gallery-dl，執行 `dl.py` |
| `dl.py`     | 主程式，讀取 `dl.txt` 下載連結，管理認證與歷史     |
| `dl.txt`    | 下載連結清單，一行一條，支援特殊語法               |
| `history.json` | 紀錄每天下載結果，避免重複下載                    |
| `token.json`   | Pixiv refresh token 儲存與讀取                     |

---

## `dl.cmd` 功能流程

1. 檢查是否安裝 Python，若未安裝詢問是否自動下載並安裝  
2. 檢查 `gallery-dl` 是否已安裝，若無自動安裝  
3. 執行 `dl.py` 並帶入所有參數

---

## `dl.py` 詳細功能

### 1. 參數

- `-f` 或 `-force`：強制下載，忽略歷史重複檢查

### 2. 讀取與處理 `dl.txt`

- 讀取每行文字，去除空行與空白  
- 特殊語法處理：  
  - `p` + 數字 → 轉換為 `https://www.pixiv.net/artworks/{數字}`  
  - `x` → 轉成 `https://x.com`  
  - 非 https/ http 開頭的自動補 `https://`  

### 3. 歷史紀錄 `history.json` 結構
```json
{
  "yyyy-mm-dd": [
    {"url": "https://...", "result": "success"},
    {"url": "https://...", "result": "failed"}
  ]
}
```
下載成功的 URL 不會被重複下載（跨所有日期）

下載失敗也會記錄，方便日後追蹤

### 4. Pixiv OAuth 認證處理
下載 Pixiv 連結時檢查是否有 refresh token

token 存在於 token.json

若無 token 或遇到 "refresh-token required" 錯誤：

自動執行命令：gallery-dl oauth:pixiv

等待使用者完成認證流程

讀取 ~/.config/gallery-dl/config.json 中的 token 並寫入 token.json

下載時將 token 透過環境變數 GALLERYDL_PIXIV_REFRESH_TOKEN 傳入

### 5. 下載錯誤自動重試
下載失敗時重試最多 10 次

第一次重試不等待，之後每次等待 5 秒

網路錯誤（timeout、連線失敗）自動重試

Pixiv refresh token 錯誤時觸發重新認證流程並重試

其他錯誤也會重試

### 6. 動態下載進度顯示
在下載時同一行顯示 download: {url} . .. ... 循環動畫

下載完成時該行顯示 download: {url} complete 並換行

失敗時停止動畫並顯示錯誤訊息