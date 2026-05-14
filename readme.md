<div align="center">
  <a href="#-english">English</a> | <a href="#-chinese">繁體中文</a> | <a href="#-japanese">日本語</a>
</div>

---

## 🇬🇧 English

<a name="-english"></a>

### 🚀 Introduction

This project provides a set of tools to simplify downloading artworks, using `gallery-dl`. It features a seamless workflow between a Chrome extension for selecting artworks, a local server for receiving and queuing download links, and a Discord bot for automatic image capture.

### ✨ Features

-   **Automated Environment Setup**: Scripts handle Python virtual environment creation and dependency installation.
-   **Multiple Operation Modes**:
    -   **Download**: Fetches artworks from a list of URLs in `dl.txt`.
    -   **Server**: Runs a local Flask server to listen for URLs sent from the Chrome extension.
    -   **Bot**: Runs a Discord bot that monitors specified channels and auto-downloads images.
    -   **Update**: Keeps `pip` and `gallery-dl` up-to-date.
    -   **Combined**: Server and Bot can run simultaneously with a single command.
-   **Discord Bot**:
    -   Monitors specified channels for images and supported site links.
    -   Downloads image attachments directly to `download/discord/`.
    -   Handles embedded images (URL previews added by Discord asynchronously).
    -   Passes supported site URLs (Pixiv, X, nhentai, etc.) through `gallery-dl`.
    -   Shares history with other modes to avoid re-downloading.
-   **Chrome Extension**:
    -   Adds checkboxes to artworks on supported sites.
    -   Sends selected artwork URLs directly to the local server.
    -   Falls back to copying URLs to the clipboard if the server is not running.
-   **Progress Bars**: Displays download progress for all downloads.
-   **History**: Avoids re-downloading files.
-   **Interactive History Viewer**: A web interface at `/history` to view download records. It features:
    -   Filtering by date range with quick selections for the last 1, 7, or 30 days.
    -   Filtering by domain (e.g., pixiv.net, twitter.com) via a popup modal, with an active filter indicator.
    -   A tri-state button to filter by status (All, Failed, Success).
    -   Ability to select records and export the URLs as a list or a JSON array.
    -   A "Submit Selected" button to re-send selected URLs to the download queue.

### 📋 Prerequisites

-   [Python 3](https://www.python.org/downloads/)

### ⚙️ Configuration (`.env`)

Copy `.env.example` to `.env` and fill in your values. This file is only required for the Discord Bot mode.

```
DISCORD_BOT_TOKEN=your_bot_token_here
DISCORD_CHANNEL_IDS=123456789012345678,987654321098765432
```

-   **`DISCORD_BOT_TOKEN`**: Create a bot at the [Discord Developer Portal](https://discord.com/developers/applications). Enable the **Message Content Intent** in the Bot settings.
-   **`DISCORD_CHANNEL_IDS`**: Comma-separated channel IDs. Right-click a channel → **Copy Channel ID** (requires Developer Mode in Discord settings).

### 🖥️ How to Use

All modes are launched through a single entry point. On first run (or after an update), dependencies are installed automatically.

> **Linux / macOS**: Run `chmod +x dl.sh` once, then use `./dl.sh` instead of `dl.cmd`.

| Command | Description |
|---|---|
| `dl.cmd` | Download all URLs from `dl.txt` |
| `dl.cmd -s` | Start the Flask server (port 7601) |
| `dl.cmd -b` | Start the Discord bot |
| `dl.cmd -s -b` | Start Flask server **and** Discord bot together |
| `dl.cmd -u` | Force-reinstall / update all dependencies |
| `dl.cmd -h` | Show help |

#### Server mode

Starts a local server at `http://127.0.0.1:7601` that receives links from the Chrome extension. View download history at `/history`.

#### Bot mode

Monitors the Discord channels listed in `DISCORD_CHANNEL_IDS` and auto-downloads:
-   **Image attachments** → saved to `download/discord/`
-   **Embedded images** (URL previews) → saved to `download/discord/`
-   **Supported site URLs** (Pixiv, X, nhentai, wnacg, yande.re, …) → processed by `gallery-dl`

### 🧩 Chrome Extension

1.  **Installation:**
    -   Open Chrome and navigate to `chrome://extensions`.
    -   Enable **Developer mode**.
    -   Click **Load unpacked** and select the `chromeExtension` folder.
2.  **Usage:**
    -   Go to a supported site.
    -   Checkboxes will appear on each artwork. Select the ones you want.
    -   Click the **Export** button. The links will be sent to your local server.

### 🌐 Supported Sites

-   Pixiv
-   X (Twitter)
-   nhentai
-   wnacg
-   yande.re

### 📜 Update Log

-   **2026-05-14 v1.0.2**
    1.  Added Discord bot mode (`-b`): monitors channels, auto-downloads images and gallery-dl URLs.
    2.  Added combined server + bot mode (`-s -b`).
    3.  Added `.env` support for secrets (bot token, channel IDs).
    4.  Consolidated launcher scripts — removed `dl.server.*`, `dl.update.*`.
    5.  Auto-install missing dependencies on startup.
-   **2025-10-07 v1.0.1**
    1.  Added a local web UI to view download history.
    2.  Fixed wnacg downloader: now downloads and extracts the zip archive instead of scraping slide images.
-   **2025-08-19 v1.0.0**
    -   Initial release.

---

## 🇨🇳 繁體中文

<a name="-chinese"></a>

### 🚀 簡介

本專案提供一套使用 `gallery-dl` 的工具，旨在簡化下載作品的流程。它整合了 Chrome 擴充功能（用於選擇作品）、本機伺服器（用於接收和排隊下載連結）以及 Discord 機器人（用於自動擷取圖片），提供無縫的工作體驗。

### ✨ 功能

-   **自動化環境設定**：腳本會自動處理 Python 虛擬環境的建立和依賴項安裝。
-   **多種操作模式**：
    -   **下載**：從 `dl.txt` 中的 URL 列表下載作品。
    -   **伺服器**：執行本機 Flask 伺服器，以接收從 Chrome 擴充功能傳送的 URL。
    -   **Bot**：執行 Discord 機器人，監聽指定頻道並自動下載圖片。
    -   **更新**：強制重新安裝 / 更新所有依賴項。
    -   **組合模式**：伺服器與 Bot 可透過單一指令同時啟動。
-   **Discord 機器人**：
    -   監聽 `DISCORD_CHANNEL_IDS` 中指定的頻道。
    -   直接下載圖片附件到 `download/discord/`。
    -   處理 Discord 非同步嵌入的預覽圖片（embed）。
    -   將支援網站的連結（Pixiv、X、nhentai 等）交由 `gallery-dl` 處理。
    -   與其他模式共用歷史紀錄，避免重複下載。
-   **Chrome 擴充功能**：
    -   在支援的網站上為作品新增核取方塊。
    -   將選定的作品 URL 直接傳送到本機伺服器。
    -   如果伺服器未執行，則會降級為將 URL 複製到剪貼簿。
-   **進度條**：為所有下載任務顯示進度條。
-   **歷史紀錄**：避免重複下載檔案。
-   **互動式歷史記錄檢視器**：一個位於 `/history` 的網頁介面，用於檢視下載記錄。其功能包括：
    -   依日期範圍篩選，並提供「近1日」、「近7日」、「近30日」的快速選項。
    -   透過彈出視窗依網域（例如 pixiv.net, twitter.com）進行篩選，並帶有啟用狀態指示燈。
    -   一個三段式按鈕，用於依狀態（全部、僅失敗、僅成功）篩選。
    -   能夠選取記錄並將 URL 匯出為列表或 JSON 陣列。
    -   一個「送出所選」按鈕，可將選取的 URL 重新傳送到下載佇列。

### 📋 需先安裝

-   [Python 3](https://www.python.org/downloads/)

### ⚙️ 設定（`.env`）

將 `.env.example` 複製為 `.env` 並填入設定值。此檔案僅在 Discord Bot 模式下必須配置。

```
DISCORD_BOT_TOKEN=your_bot_token_here
DISCORD_CHANNEL_IDS=123456789012345678,987654321098765432
```

-   **`DISCORD_BOT_TOKEN`**：在 [Discord 開發者平台](https://discord.com/developers/applications) 建立機器人，並在 Bot 設定中啟用 **Message Content Intent**。
-   **`DISCORD_CHANNEL_IDS`**：以逗號分隔的頻道 ID。在 Discord 中右鍵點擊頻道 → **複製頻道 ID**（需在 Discord 設定中開啟「開發者模式」）。

### 🖥️ 如何使用

所有模式均透過單一入口啟動。首次執行（或升級後），依賴項會自動安裝。

> **Linux / macOS**：先執行一次 `chmod +x dl.sh`，之後使用 `./dl.sh` 代替 `dl.cmd`。

| 指令 | 說明 |
|---|---|
| `dl.cmd` | 下載 `dl.txt` 中的所有 URL |
| `dl.cmd -s` | 啟動 Flask 伺服器（port 7601）|
| `dl.cmd -b` | 啟動 Discord 機器人 |
| `dl.cmd -s -b` | 同時啟動 Flask 伺服器**與** Discord 機器人 |
| `dl.cmd -u` | 強制重新安裝 / 更新所有依賴項 |
| `dl.cmd -h` | 顯示說明 |

#### 伺服器模式

啟動本機伺服器 `http://127.0.0.1:7601`，接收來自 Chrome 擴充功能的連結。可在 `/history` 查看下載歷史。

#### Bot 模式

監聽 `DISCORD_CHANNEL_IDS` 中指定的頻道，自動下載：
-   **圖片附件** → 儲存到 `download/discord/`
-   **嵌入預覽圖片**（URL embed）→ 儲存到 `download/discord/`
-   **支援網站的連結**（Pixiv、X、nhentai、wnacg、yande.re 等）→ 由 `gallery-dl` 處理

### 🧩 Chrome 擴充功能

1.  **安裝**：
    -   開啟 Chrome 並前往 `chrome://extensions`。
    -   啟用 **開發者模式**。
    -   點擊 **載入未封裝的擴充功能** 並選擇 `chromeExtension` 資料夾。
2.  **使用**：
    -   前往支援的網站。
    -   每個作品上都會出現核取方塊。選擇您想要的。
    -   點擊 **Export** 按鈕。連結將被傳送到您的本機伺服器。

### 🌐 支援的網站

-   Pixiv
-   X (Twitter)
-   nhentai
-   wnacg
-   yande.re

### 📜 更新紀錄

-   **2026-05-14 v1.0.2**
    1.  新增 Discord Bot 模式（`-b`）：監聽頻道、自動下載圖片與 gallery-dl 連結。
    2.  新增伺服器 + Bot 組合模式（`-s -b`）。
    3.  新增 `.env` 支援（Bot Token、頻道 ID 等機密設定）。
    4.  整合啟動腳本，移除 `dl.server.*`、`dl.update.*`。
    5.  啟動時自動偵測並安裝缺少的依賴項。
-   **2025-10-07 v1.0.1**
    1.  新增本地網頁 UI 以檢視下載紀錄。
    2.  修正 wnacg 下載器，改為下載並解壓縮 zip 檔案，而非抓取幻燈片圖片。
-   **2025-08-19 v1.0.0**
    -   初版完成。

---

## 🇯🇵 日本語

<a name="-japanese"></a>

### 🚀 概要

このプロジェクトは、`gallery-dl` を使用して作品のダウンロードを簡素化するための一連のツールを提供します。Chrome拡張機能、ローカルサーバー、そしてDiscordボットを統合したシームレスなワークフローを実現します。

### ✨ 機能

-   **自動環境設定**：スクリプトがPython仮想環境の作成と依存関係のインストールを自動的に処理します。
-   **複数の操作モード**：
    -   **ダウンロード**：`dl.txt` のURLリストから作品を取得します。
    -   **サーバー**：Chrome拡張機能から送信されたURLを待ち受けるローカルFlaskサーバーを実行します。
    -   **ボット**：Discordボットを起動し、指定チャンネルを監視して画像を自動ダウンロードします。
    -   **更新**：すべての依存関係を強制再インストール／更新します。
    -   **組み合わせ**：サーバーとボットを1つのコマンドで同時起動できます。
-   **Discordボット**：
    -   `DISCORD_CHANNEL_IDS` で指定したチャンネルを監視します。
    -   画像添付ファイルを `download/discord/` に直接保存します。
    -   Discordが非同期で追加するembedプレビュー画像も処理します。
    -   対応サイトのURL（Pixiv、X、nhentaiなど）は `gallery-dl` で処理します。
    -   他のモードと履歴を共有し、重複ダウンロードを防ぎます。
-   **Chrome拡張機能**：
    -   対応サイトの作品にチェックボックスを追加します。
    -   選択した作品のURLをローカルサーバーに直接送信します。
    -   サーバーが実行されていない場合は、URLをクリップボードにコピーするフォールバック機能があります。
-   **プログレスバー**：すべてのダウンロードの進捗状況を表示します。
-   **履歴**：ファイルの再ダウンロードを防ぎます。
-   **インタラクティブ履歴ビューア**：ダウンロード履歴を閲覧するためのウェブインターフェース（`/history`）。主な機能：
    -   日付範囲によるフィルタリング機能と、「過去1日間」「過去7日間」「過去30日間」のクイック選択。
    -   ポップアップモーダルを介したドメイン（例：pixiv.net, twitter.com）によるフィルタリング（アクティブフィルターインジケーター付き）。
    -   ステータス（すべて、失敗のみ、成功のみ）でフィルタリングするための3状態ボタン。
    -   レコードを選択し、URLをリストまたはJSON配列としてエクスポートする機能。
    -   選択したURLをダウンロードキューに再送信するための「選択を送信」ボタン。

### 📋 事前インストール

-   [Python 3](https://www.python.org/downloads/)

### ⚙️ 設定（`.env`）

`.env.example` を `.env` にコピーして値を入力してください。このファイルはDiscordボットモードでのみ必要です。

```
DISCORD_BOT_TOKEN=your_bot_token_here
DISCORD_CHANNEL_IDS=123456789012345678,987654321098765432
```

-   **`DISCORD_BOT_TOKEN`**：[Discord Developer Portal](https://discord.com/developers/applications) でボットを作成し、Bot設定で **Message Content Intent** を有効にしてください。
-   **`DISCORD_CHANNEL_IDS`**：カンマ区切りのチャンネルID。Discordでチャンネルを右クリック → **チャンネルIDをコピー**（Discordの設定で「開発者モード」を有効にする必要があります）。

### 🖥️ 使用方法

すべてのモードは単一のエントリポイントから起動します。初回実行時（またはアップデート後）、依存関係は自動的にインストールされます。

> **Linux / macOS**：最初に `chmod +x dl.sh` を一度実行し、以降は `dl.cmd` の代わりに `./dl.sh` を使用してください。

| コマンド | 説明 |
|---|---|
| `dl.cmd` | `dl.txt` のすべてのURLをダウンロード |
| `dl.cmd -s` | Flaskサーバーを起動（port 7601）|
| `dl.cmd -b` | Discordボットを起動 |
| `dl.cmd -s -b` | FlaskサーバーとDiscordボットを**同時に**起動 |
| `dl.cmd -u` | すべての依存関係を強制再インストール／更新 |
| `dl.cmd -h` | ヘルプを表示 |

#### サーバーモード

`http://127.0.0.1:7601` にローカルサーバーを起動し、Chrome拡張機能からのリンクを受信します。`/history` でダウンロード履歴を確認できます。

#### ボットモード

`DISCORD_CHANNEL_IDS` で指定したチャンネルを監視し、以下を自動ダウンロードします：
-   **画像添付ファイル** → `download/discord/` に保存
-   **埋め込みプレビュー画像**（URL embed）→ `download/discord/` に保存
-   **対応サイトのURL**（Pixiv、X、nhentai、wnacg、yande.reなど）→ `gallery-dl` で処理

### 🧩 Chrome 拡張機能

1.  **インストール**：
    -   Chromeを開き、`chrome://extensions` に移動します。
    -   **デベロッパーモード** を有効にします。
    -   **パッケージ化されていない拡張機能を読み込む** をクリックし、`chromeExtension` フォルダを選択します。
2.  **使用法**：
    -   対応サイトにアクセスします。
    -   各作品にチェックボックスが表示されます。希望のものを選択します。
    -   **Export** ボタンをクリックします。リンクがローカルサーバーに送信されます。

### 🌐 対応サイト

-   Pixiv
-   X (Twitter)
-   nhentai
-   wnacg
-   yande.re

### 📜 更新履歴

-   **2026-05-14 v1.0.2**
    1.  Discordボットモード（`-b`）を追加：チャンネル監視、画像・gallery-dl URLの自動ダウンロード。
    2.  サーバー＋ボット組み合わせモード（`-s -b`）を追加。
    3.  `.env` サポートを追加（ボットトークン、チャンネルIDなどの機密設定）。
    4.  起動スクリプトを統合し、`dl.server.*`、`dl.update.*` を削除。
    5.  起動時に不足している依存関係を自動検出・インストール。
-   **2025-10-07 v1.0.1**
    1.  ダウンロード履歴を閲覧するためのローカルWeb UIを追加しました。
    2.  wnacgダウンローダーを修正：スライド画像をスクレイピングする代わりに、zipアーカイブをダウンロードして展開するように変更しました。
-   **2025-08-19 v1.0.0**
    -   初期リリース。