---
id: BP-SVC-DOUJIN-IMPORT-1
title: 舊 hentaiViewer 資料匯入（allData.json + 縮圖，block 2）
system: backend-service
tags: [backend, import, doujinshi, migration, block-2, script]
status: 已測試
request_verbatim: "@PM dispatch brief 2026-08-26/27（block 2 scope，接續 BP-SVC-DOUJIN-1 明確排除
  的兩項）：匯入 D:/backup/CSIA/python/.deprecated/hentaiViewer 的 allData.json（593 筆，329
  作者，N=nhentai 585 筆／W=wnacg 8 筆，favorite 298/295）與 thumbnail/（600 張 jpg，其中 7 張是
  已刪除紀錄留下的孤兒縮圖）。使用者要求：純本地、零網路、零 LLM、確定性 JSON→SQLite＋檔案複製；
  可重複執行不可重複匯入／重複複製；沒有下載資料夾的紀錄要「存在、可瀏覽、可分辨」但不做完整
  wishlist 功能；favorite 要決定怎麼對應進既有模型並說明理由；縮圖必須全部複製（含孤兒——來源
  gallery 有些已 404，遺失即永久遺失）；提供一支可重複執行的驗證工具，讀舊資料夾＋新 DB，
  逐筆核對（不是只比總數），MD5 逐檔核對縮圖，明確列出「刻意沒匯入」的項目，最後給一個不會
  安靜通過的 PASS/FAIL 結論——這是使用者判斷能不能刪除 hentaiViewer 資料夾的依據。"
decided_date: 2026-08-27
exec_links:
  - app/scripts/import_hentai_viewer.py
  - app/scripts/check_hentai_viewer_import.py
  - app/storage/db.py
  - app/storage/repositories/doujin_repo.py
  - tests/test_import_hentai_viewer.py
depends_on:
  - BP-SVC-DOUJIN-1
origin: "首次入庫於本次 block 2 開發（2026-08-27，worktree feat/hv-import，off main@bfce88c）。"
---

## 設計說明

BP-SVC-DOUJIN-1（block 1）刻意排除了兩件事：「匯入舊 hentaiViewer 的 allData.json」與
「wishlist／未下載書籍」。這個 entry 是那兩項的實作，作為既有本子（doujinshi）模型的**資料匯入
層**，不是新功能——沒有新增 API 路由、沒有新增前端頁面，純粹是 `app/scripts/` 底下兩支腳本
（依 cluster-conventions 的 per-language 角色目錄慣例：`scripts/` = manual / one-off jobs，
not on the request path）+ 既有 `doujin_books` table 的兩個新增欄位 + 一張新的最小化表。

### 為什麼是「匯入」而非「即時整合」

hentaiViewer 的 `allData.json` 是使用者手動維護多年的 293 KB 靜態快照，來源網站有些已經
404（例如 `121697` 現場確認已刪除）——這份資料**只存在於這個快照裡**，沒有辦法之後用抓取器
重新取得。匯入的唯一正確時機就是現在，趁 hentaiViewer 資料夾還沒被使用者刪除。匯入完成後，
這支腳本不會再被排程執行——它是一次性遷移工具，可重複執行只是為了安全（見下方「冪等性」），
不是要變成常駐流程。

### 資料核實（先驗證來源事實，再動手，避免對著錯誤的數字設計）

開發前用 Python（非 Git Bash `find`——這個專案已知 MSYS2 在 Windows 上處理部分中日文檔名會
靜默漏掉，BP-SVC-DOUJIN-1 的「519 vs 522」事故就是同一個根因）逐項現場核實：

- `allData.json`：593 筆記錄、329 位作者、代碼前綴 `N`（nhentai）585 筆／`W`（wnacg）8 筆、
  `favorite` 298 筆為 1、295 筆為 0，且**全域 593 個代碼互不重複**。
- 用既有 `doujin_meta_service.extract_gallery_id()` 同款「開頭數字＋`_`或空白」規則
  （`^(\d+)[_ ]`）比對 `download/nhentai/`（401 個資料夾，id 皆不重複）與
  `download/wnacg/`（519 個資料夾，id 皆不重複）：**232 筆有對應資料夾**（231 個 N ＋ 1 個
  W），**361 筆沒有**——與題目給的數字完全一致。
- `thumbnail/`：600 個檔案，593 筆記錄全部有對應縮圖，另有 **7 個孤兒縮圖**
  （`N226543`/`N243300`/`N243693`/`N277847`/`N293151`/`N308311`/`N343700`，代碼不在
  `allData.json` 裡——使用者刪除紀錄時留下的殘留）。

### 儲存（純新增，兩個表的其中一個是全新最小化表）

`app/storage/db.py`：

- **`doujin_books` 新增兩欄**：`imported_favorite`（INTEGER，NULL＝這本書沒有舊庫匯入資料，
  0/1＝已匯入）、`imported_thumbnail`（TEXT，相對 `DATA_DIR` 的路徑，如
  `doujin_thumbnails/N105189.jpg`）。**這是這個 table 第一次對「已經可能有資料的既有 table」
  加欄位**——之前每次 schema 變動（見 BP-SVC-DOUJIN-1）都巧合發生在 `doujin_books`
  還是空表的時候，這次 live DB 已經有資料（block 1 剛上線），所以新增了
  `_ensure_doujin_import_columns()`：`init_db()` 每次啟動都會 `PRAGMA table_info` 檢查這
  兩欄存不存在，不存在才 `ALTER TABLE ADD COLUMN`——這個專案原本沒有 migration
  framework，這是第一個真正需要它的變動，用最小化方式補上，不是引入一整套 migration 系統。
- **不放進 `purchase_state`，是獨立欄位**：`purchase_state` 是既有、面向 UI 的「有沒有實際
  付費購買」欄位（`ALLOWED_PURCHASE_STATES`），hentaiViewer 的 `favorite`（收藏／喜歡星號）
  是完全不同的軸——把兩者合併，未來使用者在編輯面板點一次「已購買」就會把匯入的收藏訊號
  永久蓋掉，且沒有分開的欄位可以救回來。298/295 接近對半分，是真實訊號，值得用獨立欄位
  無損保留。
- **matched 記錄的 title/artist 寫進 `*_fetched`，絕不碰 `*_override`**：這是既有
  「manual-edit-wins」機制（BP-SVC-DOUJIN-1）的寫入端規則——`doujin_repo.set_import_fields()`
  只在**當下這一列**的 `*_override`（使用者手動編輯）與 `*_fetched`（已經抓過的站點資料）
  都是空的時候才寫入舊庫的 title/artist；兩者任一有值就跳過。這保證匯入永遠不會蓋掉使用者
  自己編輯過的欄位，**也**不會蓋掉一次真正的站點抓取（品質通常比 2022 年的舊快照更新更準）。
  `imported_favorite`／`imported_thumbnail` 則是匯入獨有的欄位，沒有其他寫入者，每次執行
  都無條件覆寫成當下來源值（見下方冪等性）。
- **新表 `doujin_wanted_books`**（361 筆沒有資料夾的記錄）：`(source, code)` 複合主鍵，
  只有 `title`/`artist`/`favorite`/`thumbnail_path` 幾個欄位，**沒有編輯 API**。刻意做成
  獨立表，不是在 `doujin_books` 塞一列假的 `folder_path`——既有 `doujin_books` 的所有邏輯
  （`resolve_book_dir`、詳情頁的頁數掃描、閱讀器）都假設 `folder_path` 是磁碟上一個真實存在
  的資料夾，硬塞一個假路徑會靜默打破這些假設。這正是題目要求「不要做整個 wishlist 功能，
  只要讓紀錄存在且可分辨」的最小化實作：一張表、一組 CRUD 函式（`doujin_repo` 內
  `get_wanted_book`/`list_wanted_books`/`upsert_wanted_book`/`delete_wanted_book`），
  沒有狀態機、沒有前端、沒有 API 路由。
- **兩表互斥、可自動升級（promotion）**：同一支腳本重跑時，若某筆先前落在
  `doujin_wanted_books` 的記錄，這次在 `download/` 底下找到對應資料夾了，會把它寫進
  `doujin_books`（同上述 fetched 規則）並刪掉 `doujin_wanted_books` 裡的舊列
  （`delete_wanted_book`，回傳是否真的刪到東西，計入 `ImportResult.promoted`）——使用者
  之後真的把某本「待購」的書下載下來，下次重跑匯入腳本就會自動把它從「待購」移到「已下載」，
  不會兩邊同時存在同一筆。

### 縮圖：存哪裡、為什麼

`data/doujin_thumbnails/<code>.jpg`（`data/` 整個目錄本來就是 `.gitignore`，跟 `app.db`／
`tokens.json` 同一層，是「app 自己管理、不進版控的本地狀態」——縮圖不是下載內容本身
（不屬於 `download/`），是這次匯入附帶的舊庫資產，符合 `DATA_DIR` 既有定位）。**全部 600 張
都複製**，包含 7 張孤兒——複製迴圈是照 `thumbnail/` 目錄本身列出來跑的，不是照
`allData.json` 的記錄跑，這樣孤兒不會被「這筆沒有對應記錄所以跳過」的邏輯意外漏掉。這是
題目明確強調的一點：部分來源 gallery 已經 404，這些縮圖是唯一還存在的視覺紀錄，遺失就是
永久遺失。

複製用 per-file MD5 比對做**冪等**：目的地已存在且 MD5 與來源一致就跳過，不存在或內容不同
才複製（`copy_thumbnail_idempotent`）——第二次執行 600 張全部回報
`skipped-identical`，不會浪費 I/O，也會自我修復萬一上次複製中斷留下的半殘檔案。

### 冪等性——三個獨立機制，各自對應各自的寫入類型

1. **縮圖檔案**：上述 MD5 比對複製，天然冪等。
2. **`doujin_books` 的匯入專屬欄位**（`imported_favorite`/`imported_thumbnail`）：這兩欄
   除了這支腳本沒有其他寫入者，所以**每次都無條件覆寫成當下來源值**——同樣的來源資料寫兩次
   結果相同，天然冪等；來源資料若改變（理論上不會，`allData.json` 已經是靜態快照），也會
   正確反映最新值。
3. **`doujin_wanted_books`**：`INSERT ... ON CONFLICT(source, code) DO UPDATE`（SQLite
   upsert），同一組 `(source, code)` 重複寫入直接覆蓋成相同值，不會產生第二列。

第二次執行的實測結果（見下方「驗證」）：`doujin_books`／`doujin_wanted_books` 列數不變
（232／361），縮圖 0 複製、600 跳過，`ImportResult.matched`/`wanted`/`promoted` 三個計數
與第一次完全相同。

### 安全機制（避免動到正在跑的 live DB）

- `download/` 全程唯讀——兩支腳本裡對 `download_dir` 的唯一操作是 `os.scandir()`
  （比對資料夾、算頁數），沒有任何寫入呼叫。
- hentaiViewer 來源資料夾全程唯讀——`json.loads`/`os.scandir`/`open(...,'rb')` 讀取 MD5／
  `shutil.copy2` 只把它當**來源**（destination 永遠是 `data/doujin_thumbnails/`），沒有
  任何寫入、改名、刪除呼叫。驗證見下方「hentaiViewer 未變動證明」。
- **匯入腳本的安全閘門**：`--data-dir` 未指定、環境變數 `NS_MEDIA_HUB_DATA_DIR` 也未設定時
  （代表會寫到 live `data/app.db`，`dl.py` 可能正開著它），腳本直接拒絕執行並印出理由，
  除非帶 `--i-know-this-is-live`——帶了才會先自動備份一份 `data/app.db.bak-hv-import-<時間戳>`
  再繼續。這次的所有驗證跑法**都**指定了私有的 `--data-dir`（scratch 目錄），從未觸發這個
  自動備份路徑，live DB 完全沒有被寫入過（見下方 MD5 證明）——依照題目「有疑慮就不要碰
  live DB，讓 PM 決定」的指示，這次匯入**沒有**對 live `data/app.db` 執行過寫入，需要正式
  匯入時由 PM 決定時機再跑（帶 `--i-know-this-is-live`，或先設好
  `NS_MEDIA_HUB_DATA_DIR` 指向真正要用的目錄）。
- **一個已修正的設計陷阱，誠實記錄**：第一版腳本試著在 `main()` 內用
  `os.environ["NS_MEDIA_HUB_DATA_DIR"] = ...` 來套用 `--data-dir`，實測完全無效——`import
  app.scripts.import_hentai_viewer` 這行本身就會先觸發 `app/__init__.py` → `app.main` →
  transitively `app.config.paths`，用**程序啟動當下**的環境變數把 `DATA_DIR`/`DB_FILE`
  凍結成模組常數；腳本內部再晚設定環境變數已經來不及生效。現場實測命中：資料悄悄寫進了
  `<worktree>/data/app.db`（不是預期的 scratch 目錄，好在也不是 live DB，只是位置錯了）。
  修正方式改成 `_apply_data_dir_override()`：直接對已載入的 `app.storage.db` 模組物件
  重新賦值 `DATA_DIR`/`DB_FILE`（跟 `tests/conftest.py` 的 `tmp_db` fixture 用
  `unittest.mock.patch.object` 做的事完全同一招，只是手動做一次）——因為 `_connect()`
  在**呼叫當下**才讀取這兩個模組全域變數，不是在 import 當下就固定。

## 驗證工具（`app/scripts/check_hentai_viewer_import.py`）——題目真正要的東西

使用者要的不是「匯入完成」的宣告，是「一個可以自己判斷能不能刪 hentaiViewer 資料夾的
工具」。這支腳本：

- **全程唯讀**：SQLite 連線用 `mode=ro` URI 開啟（不經過 `app.storage.db`／不會意外呼叫
  `init_db()` 的 `CREATE TABLE`），對 hentaiViewer／`download/` 只有讀取操作。
- **逐筆核對，不是只比總數**：593 筆 `allData.json` 記錄，每一筆各自查 DB（matched 記錄查
  `doujin_books` 對應列的 `imported_favorite`/`imported_thumbnail`/title-artist 來源是否
  存在；no-folder 記錄查 `doujin_wanted_books` 精確比對 `favorite`/`title`/`artist`/
  `thumbnail_path`，並確認**沒有**同時出現在 `doujin_books`）。任何一筆不符都會被具名列出
  （代碼 + 具體差異），不會被平均掉。
- **縮圖用逐檔 MD5 比對**，不是檔名或大小——`check_thumbnails()` 對來源 600 個檔案各自算
  MD5，跟目的地同名檔案的 MD5 比對，缺檔／內容不符都具名列出。
- **明確列出所有「刻意沒匯入」的項目**：掃描 hentaiViewer 目錄下除了 `allData.json`／
  `thumbnail/` 以外的每一項（`allData.index.json`／`backup/`／`template/`／
  `hentaiCollector.py`／`hentaiViewerServer.py`／`runserver.cmd`／`Link.txt`／
  `LinkTmp.txt`／`文字.txt`，實測還多一個 `__pycache__`），各自標大小＋一行說明；
  `Link.txt`/`LinkTmp.txt`/`文字.txt` 三個純文字檔**只讀檔名與大小，內容完全不讀不摘要**
  （題目明確要求）。清單是**動態掃描**產生（不是寫死清單再核對），所以萬一 hentaiViewer
  資料夾在這之後多了新檔案，會自動被標成「UNEXPECTED — 需要人工檢視」而不是安靜漏掉。
- **結論行不會安靜放行**：任何一筆記錄缺失/不符、任何一張縮圖缺失/MD5 不符、記錄總數不是
  593、來源縮圖總數不是 600，都會讓結論變成明確的 `FAIL — DO NOT DELETE hentaiViewer/`
  並列出所有失敗項目；全部核對通過才印 `PASS`，同時仍會提醒使用者自行檢視「刻意沒匯入」
  清單裡的項目。
- **hentaiViewer 資料夾已刪除時的行為**：不會假裝 PASS——印出「來源資料夾找不到，這個
  checker 沒有東西可以拿來核對」並以結束碼 2 結束（區分於 0=PASS／1=FAIL）。

## 驗證

以下全部針對**私有 DB 拷貝**執行（`--data-dir` 指向 scratch 目錄），從未觸碰 live
`data/app.db` 的寫入路徑：

1. **私有拷貝匯入**（真正複製一份 live `data/app.db` 到 scratch 目錄再匯入，模擬正式流程）：
   `records total 593 / matched 232 (promoted 0) / wanted 361 / thumbnails copied 600 /
   orphaned 7`——與資料核實階段的數字完全一致。
2. **重跑一次（冪等性）**：`thumbnails copied 0 / thumbnails unchanged 600`，
   `doujin_books`/`doujin_wanted_books` 列數不變（232/361），三個計數與第一次相同。
3. **驗證腳本**（同一份私有拷貝）：`OK (per-record verified): 593 / 593`、
   `matched (MD5-identical copy present): 600`、零筆 MISMATCH／MISSING，
   `VERDICT: PASS`。
4. **live `data/app.db` 完全未被寫入**：MD5 在這整輪操作前後都是
   `f25ae8ce1ccdda6c93d04b18a07a8f2f`——與私有拷貝的所有動作無關（安全閘門本身也從未被
   觸發，因為所有跑法都帶了 `--data-dir`）。
5. **hentaiViewer 資料夾逐位元組未變動**：全樹 613 個檔案（含 `__pycache__`）中，
   **最新修改時間是 `hentaiViewerServer.py`，2022-10-05**——這次工作階段（2026-08-27）
   完全沒有任何檔案被改動過，比對整棵樹的 mtime 是比重新雜湊整棵樹更直接的證據（雜湊也在
   跑，見 commit 訊息）。`allData.json` 大小（87250 bytes）與 `thumbnail/` 檔案數（600）
   前後一致。
6. **手動抽查**（3 筆有資料夾、3 筆沒有）：3 個 matched 記錄的 `title_fetched`/
   `artist_fetched`/`imported_favorite`/`imported_thumbnail` 皆正確填入，且對應縮圖檔案
   確實存在於 `data/doujin_thumbnails/`；3 個 wanted 記錄同樣核對 `doujin_wanted_books`
   欄位與縮圖路徑，皆正確。
7. **`download/` 未被寫入**：程式碼審查確認 `download_dir` 在兩支腳本裡只出現在
   `os.scandir()` 呼叫裡，沒有任何寫入路徑。
8. **連接埠 6108**：這次工作全程沒有啟動任何伺服器，結束後確認仍是空的。
9. **`pytest tests/ -q`：220 passed**（既有 197 案例 + 這次新增 23 案例，`tests/
   test_import_hentai_viewer.py`），涵蓋：`split_hv_code` 代碼切分（含未知前綴／非數字
   id）、`scan_source_ids` 資料夾比對（底線/空白前綴、缺目錄、忽略檔案）、
   `copy_thumbnail_idempotent` 三種狀態、matched 記錄寫入正確欄位、no-folder 記錄建立
   `doujin_wanted_books`、**手動編輯永遠贏**（預先設定 `title_override` 後匯入不會被覆蓋）、
   **既有站點抓取也不會被覆蓋**（預先設定 `title_fetched` 模擬真實抓取，匯入不會用舊庫資料
   蓋掉）、孤兒縮圖確實複製且不產生任何書籍/待購列、**重跑冪等**（列數、內容不變，僅
   `updated_at` 隨寫入推進——這是既有 `doujin_repo` 慣例，不是 bug）、**待購記錄升級**
   （原本沒資料夾的記錄，資料夾出現後重跑會被移進 `doujin_books` 並從
   `doujin_wanted_books` 刪除）、checker 對缺列／縮圖 MD5 不符會具名回報（刻意製造一筆
   缺陷驗證「不會安靜通過」）、「刻意沒匯入」清單的動態掃描與未知項目標記。

## 刻意沒做（範圍外）

- 沒有新增任何 API 路由或前端頁面——`doujin_wanted_books` 目前只能透過
  `doujin_repo` 的函式或直接查 DB 存取。要不要在封面牆之外另外呈現「待購」列表，是使用者
  之後的決定，不在這次題目範圍內（題目原話：「不要給我做一整個 wishlist 功能」）。
- 沒有把 `favorite` 呈現在既有 UI 上（`DoujinBookEditPanel.vue` 等前端元件完全沒動）——
  這次只負責把訊號無損存進 DB，要不要在畫面上顯示、怎麼顯示，是後續功能決定。
- 沒有對 live `data/app.db` 執行寫入——依題目指示「有疑慮就不要碰、讓 PM 決定」，所有驗證
  都在私有拷貝上完成；正式匯入 live DB 的時機由 PM 決定。
