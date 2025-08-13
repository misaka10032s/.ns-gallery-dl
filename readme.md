<div align="center">
  <a href="#-english">English</a> | <a href="#-chinese">繁體中文</a> | <a href="#-japanese">日本語</a>
</div>

---

## 🇬🇧 English

<a name="-english"></a>

### 🚀 Introduction

This project provides a set of tools to simplify downloading artworks from sites like Pixiv, using `gallery-dl`. It includes scripts for managing downloads and a Chrome extension to easily select artworks from a user's page on Pixiv.

### ✨ Features

-   Automated setup of a Python virtual environment.
-   Scripts for downloading (`dl.cmd`, `dl.sh`) and updating (`dl.update.cmd`, `dl.update.sh`).
-   Keeps a history of downloaded files to avoid duplicates.
-   Chrome extension to select multiple artworks and export their IDs.

### 📋 Prerequisites

-   [Python 3](https://www.python.org/downloads/)

### 🖥️ How to Use

#### On Windows

1.  **Run `dl.cmd`:** Double-click this file. On the first run, it will create a virtual environment and install the necessary dependencies.
2.  **Add URLs:** Open `dl.txt` and add the artwork URLs you want to download.
    -   For Pixiv artworks, you can use the short format `p<artwork_id>`, for example: `p12345678`.
    -   Full URLs are also supported.
3.  **Run again:** Run `dl.cmd` again to start the download process.

#### On Linux / macOS

1.  **Make script executable:** Open a terminal and run `chmod +x dl.sh`.
2.  **Run `./dl.sh`:** On the first run, it will create a virtual environment and install the necessary dependencies.
3.  **Add URLs:** Open `dl.txt` and add the artwork URLs you want to download.
    -   For Pixiv artworks, you can use the short format `p<artwork_id>`, for example: `p12345678`.
    -   Full URLs are also supported.
4.  **Run again:** Run `./dl.sh` again to start the download process.

### 🔄 How to Update

To update `pip` and `gallery-dl` to their latest versions:

-   **Windows:** Run `dl.update.cmd`.
-   **Linux / macOS:** Run `./dl.update.sh` (you may need to run `chmod +x dl.update.sh` first).

### 🧩 Chrome Extension

The extension helps you quickly grab artwork IDs from a Pixiv user's page.

1.  **Installation:**
    -   Open Chrome and navigate to `chrome://extensions`.
    -   Enable **Developer mode** in the top-right corner.
    -   Click **Load unpacked**.
    -   Select the `chromeExtension` folder from this project.
2.  **Usage:**
    -   Go to a Pixiv user's page (e.g., `https://www.pixiv.net/users/12345`).
    -   Checkboxes will appear on each artwork. Select the ones you want.
    -   Click the **Export** button in the bottom-left corner.
    -   A dialog will appear with the selected artwork IDs. Copy this list.
    -   Paste the IDs into `dl.txt`, one per line, using the `p<artwork_id>` format.

---

## 🇨🇳 繁體中文

<a name="-chinese"></a>

### 🚀 簡介

該專案提供了一套工具，可使用 `gallery-dl` 簡化從 Pixiv 等網站下載作品的過程。它包含用於管理下載的腳本和一個 Chrome 擴充功能，可輕鬆地從 Pixiv 的使用者頁面選擇作品。

### ✨ 功能

-   自動設定 Python 虛擬環境。
-   用於下載 (`dl.cmd`, `dl.sh`) 和更新 (`dl.update.cmd`, `dl.update.sh`) 的腳本。
-   記錄已下載檔案的歷史，避免重複下載。
-   Chrome 擴充功能，用於選擇多個作品並匯出其 ID。

### 📋 先決條件

-   [Python 3](https://www.python.org/downloads/)

### 🖥️ 如何使用

#### 在 Windows 上

1.  **執行 `dl.cmd`:** 雙擊此檔案。首次執行時，它將建立一個虛擬環境並安裝必要的依賴項。
2.  **新增 URL:** 開啟 `dl.txt` 並新增您要下載的作品 URL。
    -   對於 Pixiv 作品，您可以使用簡短格式 `p<作品_id>`，例如：`p12345678`。
    -   也支援完整的 URL。
3.  **再次執行:** 再次執行 `dl.cmd` 以開始下載過程。

#### 在 Linux / macOS 上

1.  **使腳本可執行:** 開啟終端機並執行 `chmod +x dl.sh`。
2.  **執行 `./dl.sh`:** 首次執行時，它將建立一個虛擬環境並安裝必要的依賴項。
3.  **新增 URL:** 開啟 `dl.txt` 並新增您要下載的作品 URL。
    -   對於 Pixiv 作品，您可以使用簡短格式 `p<作品_id>`，例如：`p12345678`。
    -   也支援完整的 URL。
4.  **再次執行:** 再次執行 `./dl.sh` 以開始下載過程。

### 🔄 如何更新

要將 `pip` 和 `gallery-dl` 更新到最新版本：

-   **Windows:** 執行 `dl.update.cmd`。
-   **Linux / macOS:** 執行 `./dl.update.sh` (您可能需要先執行 `chmod +x dl.update.sh`)。

### 🧩 Chrome 擴充功能

該擴充功能可幫助您從 Pixiv 使用者頁面快速獲取作品 ID。

1.  **安裝:**
    -   開啟 Chrome 並導覽至 `chrome://extensions`。
    -   在右上角啟用 **開發者模式**。
    -   點擊 **載入未封裝的擴充功能**。
    -   從此專案中選擇 `chromeExtension` 資料夾。
2.  **使用:**
    -   前往 Pixiv 使用者頁面 (例如, `https://www.pixiv.net/users/12345`)。
    -   每個作品上都會出現核取方塊。選擇您想要的。
    -   點擊左下角的 **Export** 按鈕。
    -   將出現一個包含所選作品 ID 的對話方塊。複製此列表。
    -   將 ID 貼到 `dl.txt` 中，每行一個，使用 `p<作品_id>` 格式。

---

## 🇯🇵 日本語

<a name="-japanese"></a>

### 🚀 概要

このプロジェクトは、`gallery-dl` を使用して Pixiv などのサイトから作品を簡単にダウンロードするための一連のツールを提供します。ダウンロードを管理するためのスクリプトと、Pixiv のユーザーページから作品を簡単に選択するための Chrome 拡張機能が含まれています。

### ✨ 機能

-   Python 仮想環境の自動セットアップ。
-   ダウンロード用 (`dl.cmd`, `dl.sh`) および更新用 (`dl.update.cmd`, `dl.update.sh`) のスクリプト。
-   重複を避けるためにダウンロードしたファイルの履歴を保持します。
-   複数の作品を選択してその ID をエクスポートするための Chrome 拡張機能。

### 📋 前提条件

-   [Python 3](https://www.python.org/downloads/)

### 🖥️ 使用方法

#### Windows の場合

1.  **`dl.cmd` を実行:** このファイルをダブルクリックします。初回実行時に、仮想環境が作成され、必要な依存関係がインストールされます。
2.  **URL を追加:** `dl.txt` を開き、ダウンロードしたい作品の URL を追加します。
    -   Pixiv の作品の場合、`p<作品_id>` という短い形式を使用できます。例：`p12345678`。
    -   完全な URL もサポートされています。
3.  **再実行:** 再度 `dl.cmd` を実行して、ダウンロードプロセスを開始します。

#### Linux / macOS の場合

1.  **スクリプトを実行可能にする:** ターミナルを開き、`chmod +x dl.sh` を実行します。
2.  **`./dl.sh` を実行:** 初回実行時に、仮想環境が作成され、必要な依存関係がインストールされます。
3.  **URL を追加:** `dl.txt` を開き、ダウンロードしたい作品の URL を追加します。
    -   Pixiv の作品の場合、`p<作品_id>` という短い形式を使用できます。例：`p12345678`。
    -   完全な URL もサポートされています。
4.  **再実行:** 再度 `./dl.sh` を実行して、ダウンロードプロセスを開始します。

### 🔄 更新方法

`pip` と `gallery-dl` を最新バージョンに更新するには：

-   **Windows:** `dl.update.cmd` を実行します。
-   **Linux / macOS:** `./dl.update.sh` を実行します (最初に `chmod +x dl.update.sh` を実行する必要がある場合があります)。

### 🧩 Chrome 拡張機能

この拡張機能は、Pixiv ユーザーページから作品 ID をすばやく取得するのに役立ちます。

1.  **インストール:**
    -   Chrome を開き、`chrome://extensions` に移動します。
    -   右上隅にある **デベロッパーモード** を有効にします。
    -   **パッケージ化されていない拡張機能を読み込む** をクリックします。
    -   このプロジェクトから `chromeExtension` フォルダを選択します。
2.  **使用法:**
    -   Pixiv ユーザーページに移動します (例: `https://www.pixiv.net/users/12345`)。
    -   各作品にチェックボックスが表示されます。必要なものを選択します。
    -   左下隅にある **Export** ボタンをクリックします。
    -   選択した作品 ID を含むダイアログが表示されます。このリストをコピーします。
    -   ID を `dl.txt` に貼り付けます。1行に1つずつ、`p<作品_id>` 形式を使用します。