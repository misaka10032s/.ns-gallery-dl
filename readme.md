<div align="center">
  <a href="#-english">English</a> | <a href="#-chinese">繁體中文</a> | <a href="#-japanese">日本語</a>
</div>

---

## 🇬🇧 English

<a name="-english"></a>

### 🚀 Introduction

This project provides a set of tools to simplify downloading artworks, using `gallery-dl`. It features a seamless workflow between a Chrome extension for selecting artworks and a local server for receiving and queuing download links.

### ✨ Features

-   **Automated Environment Setup**: Scripts handle Python virtual environment creation and dependency installation.
-   **Multiple Operation Modes**:
    -   **Download**: Fetches artworks from a list of URLs in `dl.txt`.
    -   **Server**: Runs a local server to listen for URLs sent from the Chrome extension.
    -   **Update**: Keeps `pip` and `gallery-dl` up-to-date.
-   **Chrome Extension**:
    -   Adds checkboxes to artworks on supported sites.
    -   Sends selected artwork URLs directly to the local server.
    -   Falls back to copying URLs to the clipboard if the server is not running.
-   **Progress Bars**: Displays download progress for all downloads.
-   **History**: Avoids re-downloading files.

### 📋 Prerequisites

-   [Python 3](https://www.python.org/downloads/)

### 🖥️ How to Use

#### 1. Start the Server (Recommended)

-   **Windows**: Run `dl.server.cmd`.
-   **Linux / macOS**: Run `chmod +x dl.server.sh` first, then `./dl.server.sh`.

This will start a local server that waits for links from the Chrome extension.

#### 2. Use the Chrome Extension

-   Install the extension (see below).
-   Browse to a supported site, select artworks using the checkboxes, and click "Export".
-   The links will be automatically sent to the server and added to `dl.txt`.

#### 3. Run the Downloader

-   **Windows**: Run `dl.cmd`.
-   **Linux / macOS**: Run `chmod +x dl.sh` first, then `./dl.sh`.

This will download all the URLs collected in `dl.txt`.

### 🔄 How to Update

-   **Windows**: Run `dl.update.cmd`.
-   **Linux / macOS**: Run `chmod +x dl.update.sh` first, then `./dl.update.sh`.

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

---

## 🇨🇳 繁體中文

<a name="-chinese"></a>

### 🚀 簡介

本專案提供一套使用 `gallery-dl` 的工具，旨在簡化下載作品的流程。它整合了 Chrome 擴充功能（用於選擇作品）和本機伺服器（用於接收和排隊下載連結），提供無縫的工作體驗。

### ✨ 功能

-   **自動化環境設定**：腳本會自動處理 Python 虛擬環境的建立和依賴項安裝。
-   **多種操作模式**：
    -   **下載**：從 `dl.txt` 中的 URL 列表下載作品。
    -   **伺服器**：執行本機伺服器，以接收從 Chrome 擴充功能傳送的 URL。
    -   **更新**：保持 `pip` 和 `gallery-dl` 為最新版本。
-   **Chrome 擴充功能**：
    -   在支援的網站上為作品新增核取方塊。
    -   將選定的作品 URL 直接傳送到本機伺服器。
    -   如果伺服器未執行，則會降級為將 URL 複製到剪貼簿。
-   **進度條**：為所有下載任務顯示進度條。
-   **歷史紀錄**：避免重複下載檔案。

### 📋 需先安裝

-   [Python 3](https://www.python.org/downloads/)

### 🖥️ 如何使用

#### 1. 啟動伺服器（建議）

-   **Windows**：執行 `dl.server.cmd`。
-   **Linux / macOS**：先執行 `chmod +x dl.server.sh`，然後執行 `./dl.server.sh`。

這將啟動一個本機伺服器，等待從 Chrome 擴充功能傳來的連結。

#### 2. 使用 Chrome 擴充功能

-   安裝擴充功能（見下文）。
-   瀏覽支援的網站，使用核取方塊選擇作品，然後點擊「Export」。
-   連結將自動傳送到伺服器並新增到 `dl.txt`。

#### 3. 執行下載器

-   **Windows**：執行 `dl.cmd`。
-   **Linux / macOS**：先執行 `chmod +x dl.sh`，然後執行 `./dl.sh`。

這將下載 `dl.txt` 中收集的所有 URL。

### 🔄 如何更新

-   **Windows**：執行 `dl.update.cmd`。
-   **Linux / macOS**：先執行 `chmod +x dl.update.sh`，然後執行 `./dl.update.sh`。

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

---

## 🇯🇵 日本語

<a name="-japanese"></a>

### 🚀 概要

このプロジェクトは、`gallery-dl` を使用して作品のダウンロードを簡素化するための一連のツールを提供します。作品を選択するためのChrome拡張機能と、ダウンロードリンクを受信してキューに入れるためのローカルサーバーとの間でシームレスなワークフローを実現します。

### ✨ 機能

-   **自動環境設定**：スクリプトがPython仮想環境の作成と依存関係のインストールを自動的に処理します。
-   **複数の操作モード**：
    -   **ダウンロード**：`dl.txt` のURLリストから作品を取得します。
    -   **サーバー**：Chrome拡張機能から送信されたURLを待ち受けるローカルサーバーを実行します。
    -   **更新**：`pip` と `gallery-dl` を最新の状態に保ちます。
-   **Chrome拡張機能**：
    -   対応サイトの作品にチェックボックスを追加します。
    -   選択した作品のURLをローカルサーバーに直接送信します。
    -   サーバーが実行されていない場合は、URLをクリップボードにコピーするフォールバック機能があります。
-   **プログレスバー**：すべてのダウンロードの進捗状況を表示します。
-   **履歴**：ファイルの再ダウンロードを防ぎます。

### 📋 事前インストール

-   [Python 3](https://www.python.org/downloads/)

### 🖥️ 使用方法

#### 1. サーバーを起動する（推奨）

-   **Windows**：`dl.server.cmd` を実行します。
-   **Linux / macOS**：最初に `chmod +x dl.server.sh` を実行し、次に `./dl.server.sh` を実行します。

これにより、Chrome拡張機能からのリンクを待つローカルサーバーが起動します。

#### 2. Chrome拡張機能を使用する

-   拡張機能をインストールします（下記参照）。
-   対応サイトを閲覧し、チェックボックスで作品を選択して「Export」をクリックします。
-   リンクは自動的にサーバーに送信され、`dl.txt` に追加されます。

#### 3. ダウンローダーを実行する

-   **Windows**：`dl.cmd` を実行します。
-   **Linux / macOS**：最初に `chmod +x dl.sh` を実行し、次に `./dl.sh` を実行します。

これにより、`dl.txt` に収集されたすべてのURLがダウンロードされます。

### 🔄 更新方法

-   **Windows**：`dl.update.cmd` を実行します。
-   **Linux / macOS**：最初に `chmod +x dl.update.sh` を実行し、次に `./dl.update.sh` を実行します。

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