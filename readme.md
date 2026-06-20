# NS Media Hub

原本的 **ns-gallery-dl** 已重構為 **ns-media-hub**。  
這個 repo 現在是統一入口，整合：

- `gallery-dl` 圖站下載
- `yt-dlp` 影音下載
- Discord bot 監聽與自動下載
- 本機 API / queue / history / jobs UI
- Chrome extension 選取匯出、網站前往、omnibox、redirect 清理
- cookie 掃描與集中管理

> 外部 repo `D:\backup\CSIA\.ns-yt-dlp` 與 `D:\backup\CSIA\javascript\ns-chrome-tool` 不需要修改；本專案已吸收其核心能力與相容行為。

## 目前重點功能

### 1. 下載核心

- 依 URL 自動分流到 `gallery-dl` 或 `yt-dlp`
- 保留 `nhentai`、`wnacg` 的特化下載邏輯
- 支援 `dl.txt` 批次下載
- 保留 Pixiv refresh token 流程

### 2. 歷史 / 工作佇列 / 前端工作台

- 以 SQLite (`data/app.db`) 儲存 jobs、history、cookies registry
- 會自動遷移舊版 `data/history.json`
- Web UI 已改為 **Vue + Vite + Pinia** 單頁工作台
- `/` 提供 dashboard 總覽與快速送件面板
- `/history` 提供歷史篩選、批次重送、狀態修正、複製輸出
- `/queue` 顯示目前下載中、待處理分布與 queue 清單
- `/jobs` 提供工作篩選、錯誤檢視與 retry
- `/cookies` 提供 cookie registry、新增 / 編輯 / 刪除管理
- `/gallery` 提供本機媒體瀏覽器，可瀏覽 `download/` 目錄下的圖片與影片

### 5. 媒體瀏覽器（Media Viewer）

- **`/gallery`** — 瀏覽下載目錄中的全部媒體，分類顯示（discord / pixiv / ytdlp 等）
- **`GalleryView.vue`** 元件提供：縮圖格檢視、分類切換、資料夾展開、圖片燈箱
- 後端 API：
  - `GET /api/gallery` — 取得頂層分類列表
  - `GET /api/gallery/items?category=<name>` — 取得分類下的所有媒體項目（子目錄或單一檔案）
  - `GET /api/gallery/files?path=<rel>` — 取得項目下的所有檔案清單
  - `GET /api/gallery/serve?p=<rel>` — 安全提供媒體檔案（支援 Range 分段請求，適合影片串流）
- 路徑安全：所有檔案請求均透過 `resolve_file` 驗證，防止 path traversal 逸出 `download/` 目錄

### 3. Discord bot

- 監聽指定頻道訊息與編輯後新增的 embed 圖
- 下載圖片附件、embed 圖片、支援網域 URL
- 保留 `$d` / `$download` 掃描頻道歷史重新下載
- bot 支援網域改為由 provider/domain registry 決定，不再散落硬編碼

### 4. Chrome extension

`chromeExtension/` 現在是唯一正式版本，整合了：

- 原本 selector 匯出功能
- 右鍵選單快速前往站點代碼
- 站點感知的下載 action（YouTube / X / Facebook / Pixiv / nhentai / WNACG / Yande.re）
- 選取文字 `下載: xxx` 正規化送件（自動補 `https://`、處理 `example(.)com`、支援舊縮寫）
- `yt-dlp` / `gallery-dl` 下載送件到本機 API
- omnibox `ns` 快速前往
- redirect query cleanup（例如 `fbclid`、`twitter/x` 的 `t` / `s`）
- popup 顯示 server 連線狀態與 queue 摘要

## 專案結構

```text
frontend/            Vue + Vite + Pinia source
  src/
    styles/          共用 SCSS partials（tokens / base / shell / controls / content / responsive）
  package.json

app/
  api/                Flask app 與 API 入口
    routes/           history / queue / jobs / auth / misc / pages
  config/             路徑、環境設定、功能旗標
  domain/             job / provider / status 型別
  providers/          gallery-dl、yt-dlp、site-specific、cookies
  services/           queue、history、bot、token、bridge
  storage/            SQLite schema 與 repositories
  ui/                 Vite build 輸出（由 Flask 直接提供）

chromeExtension/      單一正式 Chrome extension
module/               舊入口相容層
data/                 app.db、tokens、cookies
download/             下載輸出
dl.py                 Python 主入口（導向 app.main）
dl.cmd / dl.sh        啟動腳本
```

## 下載路徑規則

目前採 **網域導向**：

```text
download/
  discord/
    <guild>/
      attachments/
      embeds/
  gallery-dl/
    pixiv.net/
      <author...>
    nhentai.net/
    wnacg.com/
    yande.re/
  ytdlp/
    youtube.com/
    x.com/
    facebook.com/
```

規則重點：

- Discord：**只分 guild，不分 channel**
- Pixiv：**分到作者層級**
- YouTube / X / Facebook：**只分網域**

## Cookie 管理

cookie 正式路徑統一為：

- `cookies/`

若舊版本仍把 cookie 放在其他舊路徑，系統會在掃描時自動移轉到 `cookies/`。

> `cookies/*` 已加入 git ignore；cookie 檔案視為本機私有設定，不應提交到 repo。

建議檔名：

- `cookies-pixiv-net.txt`
- `cookies-fanbox-cc.txt`
- `x.com_cookies.txt`

系統會把掃描結果寫進 SQLite registry，並在 provider 執行時自動解析適用 cookie。
也可以直接在 `/cookies` 頁面輸入：

- 網域
- Cookie header 值（例如 `name=value; name2=value2`）

系統會自動命名成 `cookies-<domain>.txt`，轉成 Netscape cookie file 後立即套用。

## `.env` 設定

請先複製：

```bash
copy .env.example .env
```

主要欄位：

```env
DISCORD_BOT_TOKEN=your_bot_token_here
DISCORD_CHANNEL_IDS=123456789012345678,987654321098765432

BOT_DOMAIN_ALLOWLIST=
BOT_DOMAIN_DENYLIST=

DISCORD_EMOJI_QUEUED=⏳
DISCORD_EMOJI_DONE=✅
DISCORD_EMOJI_FAILED=❌
```

說明：

- `DISCORD_CHANNEL_IDS`: bot 要監聽的 Discord 頻道 ID
- `BOT_DOMAIN_ALLOWLIST`: 若設定，bot 只處理這些網域
- `BOT_DOMAIN_DENYLIST`: 強制排除的網域

## 使用方式

### Windows

```bat
dl.cmd
dl.cmd -s
dl.cmd -b
dl.cmd -s -b
dl.cmd -h
```

### Linux / macOS

```bash
chmod +x dl.sh
./dl.sh
./dl.sh -s
./dl.sh -b
./dl.sh -s -b
./dl.sh -h
```

### 指令說明

| 指令 | 說明 |
|---|---|
| `dl.cmd` / `./dl.sh` | 下載 `dl.txt` 內的 URL |
| `-s` | 啟動本機 API / UI 伺服器（若前端 source 有變更會自動 build） |
| `-b` | 啟動 Discord bot |
| `-s -b` / `-sb` | 同時啟動 server + bot，並自動檢查 / build 前端 |
| `-u` | 重新安裝 / 更新依賴 |
| `-h` | 顯示說明 |

## `dl.txt` 支援格式

除了完整 URL，也支援舊縮寫：

- `p12345678` -> Pixiv artwork
- `pu123456` -> Pixiv user
- `pw12345678` -> Pixiv artwork
- `n123456` -> nhentai
- `w12345` -> wnacg
- `x` -> `https://x.com`

## Web UI

啟動 `-s` 後：

- `http://127.0.0.1:7601/`
- `http://127.0.0.1:7601/history`
- `http://127.0.0.1:7601/queue`
- `http://127.0.0.1:7601/jobs`
- `http://127.0.0.1:7601/cookies`
- `http://127.0.0.1:7601/gallery`（媒體瀏覽器，可直接瀏覽 `download/` 目錄的圖片與影片）

前端 source 在 `frontend/`，常用指令：

```bash
cd frontend
npm install
npm run build
```

`npm run build` 會把產物輸出到 `app/ui/`，由 Flask 直接提供。

如果直接執行 `dl.cmd -s` 或 `dl.cmd -s -b`，Python 啟動流程也會自動檢查前端 source 是否比目前 build 新，必要時自動執行 `npm run build`。

## Chrome extension 安裝

1. 開啟 `chrome://extensions`
2. 啟用 **Developer mode**
3. 點 **Load unpacked**
4. 選擇本 repo 的 `chromeExtension` 資料夾

目前包含：

- Pixiv / nhentai / wnacg / yande.re / Facebook 選取匯出
- 右鍵輸入代碼前往：
  - `n123456`
  - `w12345`
  - `p12345678`
- 右鍵使用 NS Media Hub 的 yt-dlp 下載
- omnibox：在網址列輸入 `ns` 後接代碼

## 與舊版相容

- `dl.py` 保留為入口，但已導向 `app.main`
- `module/` 仍保留相容層，避免舊匯入直接失效
- 舊的 `data/history.json` 會在新系統初始化時遷移到 SQLite
- `chromeExtension/` 是唯一正式套件；舊的重複 `extension/` 已移除
- Web UI source 現在位於 `frontend/`，實際部署輸出為 `app/ui/`

## 後續可再擴充的方向

- popup 可再補 server 狀態與 cookie registry 摘要
- bot 網域規則改為可從 UI 編輯
- cookies 頁面可再補上格式驗證與匯入來源提示
