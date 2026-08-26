---
id: BP-SVC-DOUJIN-1
title: 本子模式服務層（doujin_service + doujin_books/doujin_book_links schema，block 1）
system: backend-service
tags: [backend, service, gallery, doujinshi, api, block-1]
status: 已測試
request_verbatim: "@PM dispatch brief 2026-08-26（block 1 scope）：「The feature being built is
  viewing what has been downloaded — the same media library, but different sources need
  different ways of viewing them. The old hentaiViewer tool is simply the doujinshi-shaped
  view; it is being folded in as one view mode of the gallery, not as a separate page.」
  doujinshi 模式來源：wnacg / nhentai / 18comic / exhentai；一個子資料夾＝一本書，封面牆→
  逐頁閱讀，書籍自身欄位可編輯。明確排除：wishlist（無資料夾紀錄）、hentaiViewer
  allData.json 匯入、圖片標籤/LLM、全庫搜尋、全庫掃描/雜湊——全部留給 block 2。"
decided_date: 2026-08-26
exec_links:
  - app/config/gallery_modes.py
  - app/services/doujin_service.py
  - app/storage/repositories/doujin_repo.py
  - app/storage/db.py
  - app/api/routes/gallery.py
  - tests/test_doujin_service.py
depends_on:
  - BP-SVC-GALLERY-1
origin: "首次入庫於本次 block 1 開發（2026-08-26，worktree feat/doujin-view）"
---

## 設計說明

本子（doujinshi）不是獨立頁面，而是既有 Gallery 服務的**第二種呈現模式**。哪些來源走本子
模式是**設定，不是寫死清單**：`app/config/gallery_modes.py` 的 `DOUJINSHI_SOURCES`
（目前 `wnacg` / `nhentai` / `18comic` / `exhentai`）是唯一真相來源，`resolve_mode(source)`
回傳 `"doujinshi"` 或 `"general"`；新增第五個本子站只需在這裡加一行，`doujin_service`、
`api/routes/gallery.py`、前端都不用動。`gallery_service.list_categories()` 現在會把
`mode` 一併塞進每個分類，前端因此不需要自己再維護一份來源清單（見 `BP-VIEW-DOUJIN-1`）。

### 儲存（純新增，未動任何既有 table）

`app/storage/db.py` 的 `init_db()` 新增兩個 `CREATE TABLE IF NOT EXISTS`：

- `doujin_books`：PK 是 `folder_path`（相對 `DOWNLOAD_DIR`，如
  `wnacg/100873_[...] さなえの湯(泡)`）——**惰性建立**：一個本子模式來源底下的資料夾
  「就是」一本書，不管使用者有沒有動過它；只有第一次「觸碰」（開詳情頁 / 編輯 / 加連結）才會
  真的 INSERT 一列（`doujin_repo.ensure_book`，`INSERT ... ON CONFLICT DO NOTHING`）。
  欄位對應使用者要求的 名稱/作者/社團/尺寸/彩頁/分類/購買狀態，另外 `page_count`（快取的
  磁碟頁數）+ `page_count_override`（NULL=不覆蓋，設定則優先於快取值）+ `cover_page`
  （''=自動用第一頁）+ `last_page_index`（閱讀進度，伺服器端持久化）。
- `doujin_book_links`：`UNIQUE(book, url)`，一本書可掛多筆連結（N網/P網/購買網...），
  沒有硬 FK（這個 schema 全域都沒開 `PRAGMA foreign_keys`），但 service 層永遠先
  `ensure_book` 才允許加連結。
- `db.py:_connect()` 加了一行 `PRAGMA busy_timeout = 5000`——這是既有 schema 的既存漏洞
  （WAL 只保證讀寫並發，不保證兩個寫入者互相等待，沒 timeout 會立刻炸
  "database is locked"），順手補上，跟本子功能本身無關。

### 頁數推導（使用者要求：不必手動輸入）

`page_count` = 資料夾內圖片副檔名檔案數（沿用 `gallery_service.IMAGE_EXTS`），用
`os.scandir` + `DirEntry.is_file()`/`.name` 算，**不對任何檔案呼叫 `os.stat()`**——
`list_source_books()`（封面牆）因此是「一次目錄讀取」而不是「N 次檔案 stat」。
`page_count_override` 設定時整個蓋過推導值（`_effective_page_count`）；清掉的方式是把
`page_count_override` 顯式傳 `null`。

### 效能：wnacg 512 本、55725 個檔案

`list_source_books()` **完全不寫 DB**（純瀏覽不會觸發惰性建立風暴），且用**一次**
`doujin_repo.get_books(folder_paths)` 批次查所有既有列（`WHERE folder_path IN (...)`），
而不是每本書各查一次。實測（見下方測試段落）：wnacg 全量 522 個書籍資料夾（含子目錄，比
`list_categories()` 算出的 513 個「葉節點」略多——`list_categories` 用的是既有
`_folder_has_only_files` 葉節點定義，`doujin_service` 用的是「本子來源正下一層的每個
資料夾都是一本書」，兩者對非扁平資料夾的認定本來就不同，不是 bug）耗時 **0.165 秒**。

### API（延伸既有 `/api/gallery/*`，沒有另開一套）

- `GET /api/gallery/doujin/books?source=` → 封面牆資料；`source` 不是本子模式回 400。
- `GET /api/gallery/doujin/book?path=` → 完整詳情（欄位 + `pages`（自然排序）+ `links`）；
  找不到 / 路徑逃逸 / 不是本子來源的直接子目錄一律 404。
- `PUT /api/gallery/doujin/book`（body 含 `folder_path`）→ 驗證後 upsert。
- `POST /api/gallery/doujin/book/links` → 加連結，重複 `(book, url)` 回 409。
- `DELETE /api/gallery/doujin/book/links/<id>?folder_path=` → 刪連結，`id` 綁定
  `folder_path` 範圍（不能用猜的 id 刪別本書的連結）。
- **頁面本身沒有新的檔案服務端點**——一頁就是 `DOWNLOAD_DIR` 底下的一個檔案，繼續走既有
  `/api/gallery/serve?p=`（Range 串流 + `resolve_file` 的 `is_relative_to` 逃逸防護，
  完全沒動）。

### 路徑防護（沿用 `gallery_service.resolve_file` 同款防護，新增一層模式檢查）

`doujin_service.resolve_book_dir(folder_path)`：`is_relative_to(DOWNLOAD_DIR)` 擋
`../` 逃逸（跟 `gallery_service` 同一招），另外要求路徑**恰好**是「本子來源/書資料夾」兩層
（`len(rel.parts) == 2`）且該來源 `resolve_mode() == "doujinshi"`——一般模式的來源（如
`pixiv/artist`）無法透過這條 API 被讀寫。

### 購買狀態：兩態，不是三態

使用者原話是「待購及已購」，但 **block 1 只顯示已經下載到磁碟的書**（wishlist／未下載項目
是 block 2 才有的東西——見下方「刻意沒做」）。「待購」在 block 1 語境下沒有意義（書都已經在
硬碟上了），真正有意義的只有「使用者有沒有實際購買」（例如免費下載 vs. 額外買了實體/付費版）。
因此只有兩個值：`not_purchased`（未購，預設）、`purchased`（已購）；block 2 引入 wishlist
後才需要第三態。

### 刻意沒做（block 1 範圍外，見 dispatch brief 的 Scope 段）

- Wishlist / 未下載書籍（沒有磁碟資料夾的紀錄）——block 2。
- 匯入舊 hentaiViewer 的 `allData.json`——block 2。
- 圖片標籤 / LLM / WD14——不同專案。
- 全庫搜尋、全庫掃描或雜湊——未做。
- 沒有動 general 模式任何程式碼路徑（`gallery_service.list_items/list_files` 邏輯不變，
  只有 `list_categories()` 多了 `mode` 欄位）。

### 測試

`tests/test_doujin_service.py`（40 案例，隨 `tests/` 全量 143 案例一起跑，
`py -3.11 -m pytest -q` 全綠）覆蓋：`resolve_mode` 設定驅動解析、`natural_sort_key`
（`"10.jpg"` 不會排在 `"2.jpg"` 前面，含數字/文字混合檔名不 raise）、`resolve_book_dir`
的逃逸防護（`../`、絕對路徑、非本子來源、非直屬子目錄一律拒絕）、封面牆的頁數推導與
「純瀏覽不寫 DB」、書籍詳情/更新的讀寫往返、`purchase_state`/`cover_page`/
`page_count_override` 的欄位驗證、連結新增/刪除（含重複連結拒絕、跨書刪除拒絕）。
另外對真實 `download/wnacg`（522 本、55725 個檔案，全程唯讀，`DOWNLOAD_DIR` 用環境變數
指到真實路徑、`DATA_DIR` 指到 `data/app.db` 的私有拷貝，never the live 7601 db）跑了
一次端到端 API 驗證：列表、開詳情、改欄位、加兩筆連結、刪一筆、重複連結 409、路徑穿越 404、
非本子來源 400——全部行為正確；驗證完畢後 `data/app.db` MD5 校驗與驗證前完全一致，
`download/` 底下取樣檔案 mtime/size 未變。
