# CLAUDE.md

本檔提供給 Claude Code 在本 repo 工作時的指引。所有說明、註解、文件一律使用**繁體中文**，並遵循 SOTA（State of the Art）最佳實務。

## 專案概觀

**NS Media Hub**（原 `ns-gallery-dl` 重構而來）是統一的媒體下載入口，整合：

- `gallery-dl` 圖站下載、`yt-dlp` 影音下載
- Discord bot 監聽頻道並自動下載
- 本機 API / queue / history / jobs Web UI
- Chrome extension（選取匯出、站點前往、omnibox、redirect 清理）
- cookie 掃描與集中管理

> 外部 repo `D:\backup\CSIA\.ns-yt-dlp` 與 `D:\backup\CSIA\javascript\ns-chrome-tool` 不需修改；本專案已吸收其核心能力。

## 技術棧

- **後端**：Python 3.11、Flask（API + 直接提供前端產物）、SQLite（`data/app.db`）
- **前端**：Vue 3 + Vite 8 + Pinia + vue-router，樣式用 SCSS（sass）
- **下載引擎**：gallery-dl、yt-dlp
- **Bot**：Discord bot
- 注意：Windows 環境 Python 指令為 `python`（非 `python3`）

## 開發與啟動

### 啟動腳本（Windows / Linux）

```bat
dl.cmd          # 下載 dl.txt 內的 URL
dl.cmd -s       # 啟動本機 API / UI 伺服器（前端 source 有變更會自動 build）
dl.cmd -b       # 啟動 Discord bot
dl.cmd -s -b    # 同時啟動 server + bot（自動檢查 / build 前端）
dl.cmd -u       # 重新安裝 / 更新依賴
dl.cmd -h       # 顯示說明
```

Linux / macOS 對應 `./dl.sh`（同樣旗標）。Web UI 預設在 `http://127.0.0.1:7601/`，頁面含 `/`、`/history`、`/queue`、`/jobs`、`/cookies`。

### 前端

```bash
cd frontend
npm install
npm run build   # 產物輸出到 app/ui/，由 Flask 直接提供
npm run dev     # 開發伺服器（127.0.0.1:5173）
```

`dl.cmd -s` 啟動時，Python 流程會自動比對前端 source 是否比現有 build 新，必要時自動 `npm run build`。

## 專案結構

```text
frontend/          Vue + Vite + Pinia source（styles/ 為共用 SCSS partials）
app/
  api/             Flask app 與 API 入口（routes/: history/queue/jobs/auth/misc/pages）
  config/          路徑、環境設定、功能旗標
  domain/          job / provider / status 型別
  providers/       gallery-dl、yt-dlp、site-specific、cookies
  services/        queue、history、bot、token、bridge
  storage/         SQLite schema 與 repositories
  ui/              Vite build 輸出（由 Flask 提供）
chromeExtension/   唯一正式 Chrome extension
module/            舊入口相容層
data/              app.db、tokens、cookies
download/          下載輸出
dl.py              Python 主入口（導向 app.main）
```

## 關鍵慣例

### 下載路徑（網域導向）

- Discord：**只分 guild，不分 channel**（`download/discord/<guild>/attachments|embeds/`）
- Pixiv：**分到作者層級**（`download/gallery-dl/pixiv.net/<author>/`）
- YouTube / X / Facebook：**只分網域**（`download/ytdlp/<domain>/`）
- bot 支援網域由 provider/domain registry 決定，**不要散落硬編碼**

### Cookie

- 正式路徑統一為 `cookies/`，舊路徑會在掃描時自動移轉
- `cookies/*` 已在 `.gitignore`，視為本機私有設定，**絕不提交**
- 掃描結果寫入 SQLite registry，provider 執行時自動解析適用 cookie

### 資料儲存

- jobs / history / cookies registry 皆存於 SQLite（`data/app.db`）
- 舊版 `data/history.json` 會在初始化時自動遷移到 SQLite

### `.env`

由 `.env.example` 複製。關鍵欄位：`DISCORD_BOT_TOKEN`、`DISCORD_CHANNEL_IDS`、`BOT_DOMAIN_ALLOWLIST`、`BOT_DOMAIN_DENYLIST`、`DISCORD_EMOJI_*`。

## graphify 知識圖譜

本專案使用 graphify（Python 套件已安裝）維護知識圖譜，輸出於 `graphify-out/`。

規則：
- 回答架構或程式碼相關問題前，先讀取 `graphify-out/GRAPH_REPORT.md` 了解核心節點與社群結構
- 若 `graphify-out/wiki/index.md` 存在，優先瀏覽 wiki 而非直接讀原始檔
- 本次會話中修改程式碼後，執行以下指令保持圖譜同步：

```bash
python -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"
```

> 若 `graphify-out/` 尚未產生，先初始化圖譜後再依上述規則使用。

## MCP 工具使用

### 資料庫查詢

- 需要驗證資料、對照欄位、釐清 schema 時，直接查詢本機 SQLite `data/app.db`，避免單靠程式碼推測

### 瀏覽器測試

本專案有 Vue Web UI 與 Chrome extension，瀏覽器測試以下列 MCP 擇一：

- 瀏覽器操作只能透過點擊左側選單開啟功能，**不要直接走 URL**（畫面會無法正確載入）
- **`mcp__...chrome-devtools__*`** — 獨立 Chrome profile，適合無登入狀態的頁面檢測、效能 trace、Lighthouse 稽核
- **`mcp__...playwright__*`** — Playwright 自動化，適合互動流程、表單、多步操作的端到端測試

### 登入協作流程

- 若要測試的頁面需要登入，**不要嘗試自動填帳密**
- 直接告知使用者：「此頁面需要登入，請你手動登入後告訴我，我再接手操作」
- 使用者完成登入並回報後，再接續自動化

## Skill 使用規則

**功能開發、設計討論必須使用以下 skill：**

1. **`superpowers:brainstorming`** — 任何新功能、改善、架構變更前，**必須先**用此 skill 進行腦力激盪和設計
2. **`frontend-design`** — 所有前端 UI 相關工作（Vue 元件、頁面、樣式）搭配使用，產出有設計品質、非通用 AI 風格的介面
3. **graphify** — 設計時可利用知識圖譜輔助（見上方 graphify 區塊）

## Git 操作

- **重要**：絕不自動執行 git 指令（add、commit、push、merge、rebase）；commit 由使用者手動執行，確保每次都有明確 message 與目的

## 語言和文件

- 所有說明、註解、文件必須使用**繁體中文**
- 遵循 SOTA（State of the Art）最佳實務
