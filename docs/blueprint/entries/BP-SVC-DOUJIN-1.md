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
  - app/services/doujin_meta_service.py
  - app/services/gallery_service.py
  - app/services/path_service.py
  - app/providers/sites/nhentai.py
  - app/storage/repositories/doujin_repo.py
  - app/storage/db.py
  - app/api/routes/gallery.py
  - tests/test_doujin_service.py
  - tests/test_gallery_service.py
  - tests/test_path_service.py
depends_on:
  - BP-SVC-GALLERY-1
origin: "首次入庫於本次 block 1 開發（2026-08-26，worktree feat/doujin-view）；同日三輪
  使用者追加決議（同一輪討論，未開新 entry）：(1) 移除彩頁欄位、分類改控制詞彙表 dropdown；
  (2) 名稱/作者/社團的自動偵測來源從『解析資料夾名稱』改為『站點 metadata 抓取』——資料夾
  名稱是有損渲染，不是真相來源（使用者原話：「不要用標題分析 因為那部一定有完整資訊」）；
  (3) 驗收發現同一個問題有三個不同答案（wnacg 513/522/519）——根因排除、移除 exhentai
  （「exhentai 不用 他要專門的cookie才能瀏覽」）、空來源過濾（「空資料夾不用刪 但是顯是要
  過濾0的」）、補 threads.com/bilibili.com 別名。"
---

## 設計說明

本子（doujinshi）不是獨立頁面，而是既有 Gallery 服務的**第二種呈現模式**。哪些來源走本子
模式是**設定，不是寫死清單**：`app/config/gallery_modes.py` 的 `DOUJINSHI_SOURCES`
（目前 `wnacg` / `nhentai` / `18comic` / `exhentai`）是唯一真相來源，`resolve_mode(source)`
回傳 `"doujinshi"` 或 `"general"`；新增第五個本子站只需在這裡加一行，`doujin_service`、
`api/routes/gallery.py`、前端都不用動。`gallery_service.list_categories()` 現在會把
`mode` 一併塞進每個分類，前端因此不需要自己再維護一份來源清單（見 `BP-VIEW-DOUJIN-1`）。

### 儲存（純新增，未動任何既有 table；本輪對 doujin_books 欄位做了兩次追加調整）

`app/storage/db.py` 的 `init_db()` 新增三個 `CREATE TABLE IF NOT EXISTS`：

- **`doujin_series`**（本輪新增）：分類（系列）的**控制詞彙表**——書籍存的是
  `series_id`（可為 NULL＝「沒有分類」，first-class 狀態，不是空字串 sentinel），不是
  再打一次系列名稱。`name` 是顯示形式（保留使用者原始大小寫/空白排版）；
  `normalized_name`（trim + 內部連續空白摺成一個空白 + 全小寫）`UNIQUE`，是唯一性判斷的
  key。改名一個系列會讓所有引用它的書一起變（因為存的是 id，不是字串）。
- `doujin_books`：PK 是 `folder_path`（相對 `DOWNLOAD_DIR`，如
  `wnacg/100873_[...] さなえの湯(泡)`）——**惰性建立**：一個本子模式來源底下的資料夾
  「就是」一本書，不管使用者有沒有動過它；只有第一次「觸碰」（開詳情頁 / 編輯 / 加連結 /
  抓取站點資料）才會真的 INSERT 一列（`doujin_repo.ensure_book`，
  `INSERT ... ON CONFLICT DO NOTHING`）。**彩頁欄位已於本輪移除**（使用者不要這個欄位，
  且尚無任何資料——不留隱藏欄位）。**名稱/作者/社團不再各自是一個欄位**，改成
  `title_override`/`artist_override`/`circle_override`（使用者手動編輯，NULL＝未編輯）
  + `title_fetched`/`artist_fetched`/`circle_fetched`（站點抓回來的值，NULL＝從未抓過或
  該次抓取沒有這個欄位）——見下方「名稱/作者/社團的來源」。另有 `page_count`（快取的磁碟
  頁數）+ `page_count_override`（NULL=不覆蓋，設定則優先於快取值）+ `page_count_fetched`
  （站點回報的頁數，只作交叉核對，不影響顯示的 `page_count`）+ `cover_page`（''=自動用
  第一頁）+ `last_page_index`（閱讀進度，伺服器端持久化）+
  `meta_fetch_status`/`meta_fetched_at`/`meta_source_url`（見下方「抓取結果永遠可見」）。
- `doujin_book_links`：`UNIQUE(book, url)`，一本書可掛多筆連結（N網/P網/購買網...），
  沒有硬 FK（這個 schema 全域都沒開 `PRAGMA foreign_keys`），但 service 層永遠先
  `ensure_book` 才允許加連結。
- `db.py:_connect()` 加了一行 `PRAGMA busy_timeout = 5000`——這是既有 schema 的既存漏洞
  （WAL 只保證讀寫並發，不保證兩個寫入者互相等待，沒 timeout 會立刻炸
  "database is locked"），順手補上，跟本子功能本身無關。

### 分類（系列）：dropdown + 近似重複警告，不是自由文字欄位

使用者原話：「分類的要有dropdown 不然錯別字大小寫空格就都分散了」。設計：

- **正規化規則**：`normalize_series_name()` = trim 頭尾空白 + 內部連續空白（含 tab）摺成
  一個半形空白，**保留原始大小寫**（分類名稱是顯示用的標籤，不是 slug）。唯一性判斷 key
  是這個正規化結果再轉小寫（`normalized_name`）——所以「東方Project」「  東方Project 」
  「東方  Project」「東方PROJECT」全部視為同一個系列，自動附加到同一列，不會分裂成多筆
  （這正是使用者要防的事）。
- **近似重複警告，不是自動合併也不是擋掉**：正規化後仍不完全相同、但用
  `difflib.SequenceMatcher` 算出的相似度 ≥ `SERIES_SIMILARITY_THRESHOLD`（0.82，抓
  打錯字/標點差異，如「東方Proiect」vs「東方Project」）時，`resolve_or_create_series()`
  丟出 `NearDuplicateSeriesError`（帶候選清單），API 回 `409 {error, candidates}`——前端
  顯示「你是不是要選這個？」讓使用者挑現有的，或按「仍要建立」帶 `confirm=true` 重送強制
  新建。不精確比對（差距大於門檻）直接建立，不警告。
- **刪除系列**：`delete_series(series_id, force=False)`。還有書引用時，不給 force
  直接 `SeriesInUseError`（API 回 `409 {error: "series_in_use", book_count}`）——**預設
  阻擋，不靜默孤立**；帶 `force=True` 才會把所有引用它的書 `series_id` 清成 NULL 再刪除，
  回傳值明確帶 `cleared_books` 數量，讓呼叫端知道動了幾本書。這個決定是本次自己選的
  （題目要求「決定行為並說明」）：block 1 沒有系列管理頁面（範圍不含），這個 API 是給未來
  用的，先把行為订清楚。

### 名稱/作者/社團的來源：**沒有解析資料夾名稱**——這是被使用者明確否決的方案

**歷史記錄（誠實記錄一個被推翻的方向）**：本輪一開始依照另一則指示做了一個「解析資料夾
名稱」的規則引擎（`app/config/doujin_parser_rules.py` + `doujin_service.py` 內的
`parse_book_folder_name()`），對 522 個 wnacg 資料夾實測有 100% 非空標題、91.6% 抓到
作者、91.4% 抓到社團。**這個方案已被使用者推翻並整個移除**——使用者原話：「不要用標題分析
因為那部一定有完整資訊」，理由是資料夾名稱是「有損渲染」，真相來源是原站點本身。
`doujin_parser_rules.py` 已刪除，`parse_book_folder_name` 已從 `doujin_service.py` 移除，
沒有留作 fallback。

**現在的設計**：`title`/`artist`/`circle` 的有效值在讀取時即時計算（從不預先合併存
DB），優先序：`*_override`（手動編輯，永遠贏）> `*_fetched`（站點抓回來的，見下）>
一個**不存 DB 的**預設值（`title` 預設資料夾名稱本身；`artist`/`circle` 預設空字串——
跟本功能最初、還沒有解析器/抓取器之前的行為完全一樣）。API 回應同時帶
`<field>_source`（`"manual"`/`"fetched"`/`"default"`）讓前端知道目前顯示的是哪一層，
以及 `folder_name`（資料夾原始名稱，永遠可見——找不到磁碟上的資料夾、或懷疑抓到的資料
有誤時，這是唯一能對照回去的東西）。

**唯一允許讀資料夾名稱的地方**：`doujin_meta_service.extract_gallery_id()`，只抓開頭那串
數字 ID（`"100873_..."` → `"100873"`），**不解讀其餘任何文字**。這是讀一個識別碼，不是
分析標題——使用者原話明確區分了這兩件事，且要求「不要超出這個範圍」。

### 站點 metadata 抓取（`app/services/doujin_meta_service.py` + `app/providers/sites/nhentai.py`）

- **只在使用者主動按「抓取」時對單一本書執行**——瀏覽封面牆、開詳情頁都**不**觸發任何網路
  請求（`list_source_books`/`get_book_detail` 完全唯讀）。批次回填是未來功能，這輪沒做。
- **哪些來源接了真的抓取器，是逐一實測過的，不是猜的**（2026-08-26 現場驗證）：
  - **`nhentai`：已接上、已驗證可用。** 擴充既有的
    `app/providers/sites/nhentai.py`（原本只在下載流程裡抓 `<h1 class="title">` 就丟掉
    其餘資料）新增 `fetch_gallery_metadata()`：抓 `<span class="pretty">`（乾淨標題，
    不是原本 `.text` 會拿到的「[circle (artist)] title [tags]」混雜字串——那串正是資料夾
    名稱本身的來源，不能再拿來當『站點資料』）、`Artists:`/`Groups:` tag-container（結構化
    作者/社團）、`Pages:` tag-container（結構化頁數，只作交叉核對）。
  - **`wnacg`：現場檢查後判定不接。** wnacg 的 gallery 頁面 `<title>` 就是跟資料夾名稱
    同款的方括號混雜字串（`[circle (artist)] title (parody) [tags] - 站名`），**沒有**
    獨立的作者/社團欄位——接上它等於換個地方重做一次被使用者否決的字串分析。頁面上唯一
    乾淨的結構化資料是「頁數：17P」，但單獨接頁數交叉核對、不接標題/作者/社團，價值有限，
    這輪沒做；留給使用者/PM 決定要不要只接頁數交叉核對。
  - **`18comic`：未接。** `app/providers/sites/` 沒有既有的 18comic 供應器，且該站已知
    有額外的反機器人/行動 API 金鑰門檻，超出這輪範圍。
  - **`exhentai`：未接。** 需要 gid+token 兩個值才能抓一個 gallery，不是單一數字 id；
    而且（見下方覆蓋率）這個庫裡 exhentai 資料夾本來就沒有 id 前綴，就算接了也沒有 id
    可用。
  - `doujin_meta_service.SUPPORTED_META_SOURCES` 是唯一決定「這個來源有沒有抓取器」的
    地方（目前只有 `{"nhentai"}`），配置驅動，跟 `gallery_modes.DOUJINSHI_SOURCES`
    是同一種模式但**刻意分開**——「是本子模式」跟「有沒有抓取器」是兩個獨立的問題。
- **速率限制 + 重試**：同一站點的請求間隔至少 **3 秒**（process-wide，`threading.Lock`
  + 單調時鐘），這是 750 本書 × 逐本抓取如果沒有節流會做的事——避免使用者說的「被當機器人
  擋下來」。網路錯誤/例外重試 **2 次**（共 3 次嘗試），backoff **5 秒、15 秒**；
  404／被擋（no `#info` block，通常是挑戰頁）**不重試**，直接回報，因為重試不會讓
  Cloudflare 挑戰自己過去。
- **Cookie 沿用既有機制，不寫死憑證**：`doujin_meta_service._scraper_with_cookies()`
  透過 `cookies_repo.find_cookie(domain)` 拿使用者已經在 Cookie 管理頁註冊的 Netscape
  格式 cookie 檔案（沒有就不帶 cookie 繼續跑，壞掉的 cookie 檔案也不能讓抓取整個爆掉）——
  這正是要避免的舊 `hentaiViewer` 反面案例（`hentaiCollector.py` 把 2022 年就過期的
  帳密明文寫死在原始碼裡）。
- **抓取結果永遠可見，不會靜默失敗**：每次抓取無論成功與否都會寫
  `meta_fetch_status`（`ok`/`blocked`/`not_found`/`network_error`/`no_gallery_id`/
  `unsupported_source`）+ `meta_fetched_at` + `meta_source_url`（成功時）到書籍列——
  「從沒抓過」跟「抓過但失敗」在 API 回應裡是可以分辨的兩種狀態，不會長得一樣。
- **手動編輯永遠贏，抓取永遠不會蓋掉它**：`fetch_book_metadata()` 只寫 `*_fetched` 欄位，
  從不碰 `*_override`——跟 `page_count`/`page_count_override` 同一套機制（cache 值 +
  獨立的手動覆蓋欄位，NULL＝未覆蓋），這次是題目要求「重用已經做過的機制」，所以三個欄位
  都套用同一個形狀，不是另外發明一套。

### 頁數推導（使用者要求：不必手動輸入）

`page_count` = 資料夾內圖片副檔名檔案數（沿用 `gallery_service.IMAGE_EXTS`），用
`os.scandir` + `DirEntry.is_file()`/`.name` 算，**不對任何檔案呼叫 `os.stat()`**——
`list_source_books()`（封面牆）因此是「一次目錄讀取」而不是「N 次檔案 stat」。
`page_count_override` 設定時整個蓋過推導值（`_effective_page_count`）；清掉的方式是把
`page_count_override` 顯式傳 `null`。

### 效能：wnacg 522 本、55725 個檔案

`list_source_books()` **完全不寫 DB**（純瀏覽不會觸發惰性建立風暴），且用**一次**
`doujin_repo.get_books(folder_paths)` 批次查所有既有列（`WHERE folder_path IN (...)`），
而不是每本書各查一次。實測：wnacg 全量 522 個書籍資料夾耗時 **0.165 秒**。

### 誤判記錄——「513 vs 522 不是 bug」這句話錯了，已修正（2026-08-26 驗收發現）

上一版本條目寫著「兩者對非扁平資料夾的認定本來就不同，不是 bug」——**這句話是錯的**，
是本次驗收（真的去點畫面）才抓出來的：使用者同時看到三個不同數字（來源選單徽章 513、
封面牆標題「522 本」、驗收工具自己 shell 出來的「519」），同一個問題不該有三個答案。

**三個數字各自在算什麼，逐一查清楚**：

- **513** —— 舊版 `gallery_service.list_categories()` 用 `_iter_leaf_items()`（既有的
  「葉節點」遞迴邏輯，設計給 pixiv 這種「來源/作者資料夾/相簿」多層結構用）算 `item_count`。
  它的葉節點定義是「該資料夾**只含檔案、不含任何子目錄**」；wnacg 底下若一本書的資料夾裡
  自己還帶了個子資料夾（例如附贈內容另外開一個小資料夾），`_folder_has_only_files()` 就會
  判它「不是葉節點」，改成遞迴往下找——那本書因此在計數裡消失或被拆成別的東西，不會被算成
  一本。這是真正的**低估**，不是「另一種合理定義」。
- **522** —— `doujin_service.list_source_books()`（封面牆本體）與新版 `list_categories()`
  現在共用同一套邏輯（`gallery_service._count_immediate_subdirs()`）：wnacg 資料夾正下面
  有幾個子目錄，就是幾本書，句點，不管子目錄裡面長什麼樣。**這是唯一正確的定義**——直接對應
  這個功能的規格「一個子資料夾＝一本書」，也是使用者實際在螢幕上數到的數字。
- **519** —— 這個數字**不是任何程式邏輯算出來的**，是這次驗收拿 Git Bash 的 `find`/`ls`
  之類工具在 Windows 上跑，遇到 3 個含特殊字元的日文/中文檔名（例如
  `115110_[山桜汉化] (こみトレ35) [ココアホリック...`）時 MSYS2 的路徑編碼處理失敗
  （`find: '...': No such file or directory`，實際上該資料夾存在，是工具讀不到，不是
  資料夾真的少了 3 個），因此少算了 3 個。**這是驗收工具本身的編碼瑕疵，不是這個功能的
  程式碼路徑產生的數字**，用 Python `os.scandir`（Windows 寬字元 API，不受這個問題影響）
  重新算，跟 522 完全一致。

**修正**：`gallery_service.list_categories()` 對本子模式來源不再呼叫 `_iter_leaf_items()`，
改成跟 `list_source_books()` 完全同一個 `_count_immediate_subdirs()` 函式——**現在只有一個
計數定義、一條程式碼路徑**，一般模式來源（pixiv 等）維持原本 `_iter_leaf_items()` 不變。
副作用是 wnacg/nhentai 這兩個本子來源的 `item_count` 計算反而**變快**（不用逐本書
`_first_preview`/`file_count`），整體 `list_categories()` 從 16.4 秒降到 9.6～10.9 秒
（同一支程式、同一批真實資料，前後端對端量測，見下方測試段落）——目前剩下的時間全部是
pixiv（81,040 個檔案）+ kemono.partyfanbox（19,978 個檔案）等一般模式來源既有的
`_iter_leaf_items()` 遞迴掃描，這次沒有動，也不在題目範圍內。

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

### exhentai 移除（2026-08-26 驗收後決議，不是我自己決定的）

使用者原話：「exhentai 不用 他要專門的cookie才能瀏覽」——不只是抓取要 cookie，**連瀏覽
本體都要專用 cookie**，加上這個庫裡目前只有一本 exhentai 書，不值得為它扛這個複雜度。
`app/config/gallery_modes.DOUJINSHI_SOURCES` 移除 `"exhentai"`，`resolve_mode()` 因此
自動把它歸回 general 模式——不需要在任何其他檔案另外處理，它照樣能在一般縮圖牆瀏覽（單一
相簿），只是不再有封面牆/逐頁閱讀器/欄位編輯那一套。`app/services/doujin_meta_service.py`
先前替它保留的「需要 gid+token」註解已更新，反映「已從本子來源移除，不只是抓取器沒接」。

### 空來源過濾（2026-08-26，「空資料夾不用刪 但是顯是要過濾0的」）

`gallery_service.list_categories()` 現在會跳過 `item_count == 0` 的來源，**不刪除**
底下的資料夾——`download/bilibili.com`、`minecraft`、`threads.com`、`youtube` 這四個
目前真實存在、確認 0 個檔案的殘留資料夾，驗證後仍原封不動留在磁碟上，只是不再出現在
`/api/gallery` 回應裡。**成本是零**：`item_count` 本來就要為每個來源算一次（不管本子還是
一般模式），這裡只是算完之後多一個 `if item_count == 0: continue`，沒有新增任何額外掃描
——真正的效能改善其實來自上面「513 vs 522」那個 bug 修正本身（本子來源改用更便宜的計數
方式），不是這個過濾動作。

### 兩筆網域別名補齊（`app/services/path_service.py`，`CATEGORY_ALIASES`）

使用者原話：「threads.com/bilibili.com = threads/bilibili」——新增
`"threads.com": "threads"`、`"bilibili.com": "bilibili"`。這只影響**未來**下載會落在
哪個資料夾（`path_service.storage_category()` 是下載時決定儲存路徑用的），**不會**、
也**沒有**搬動或刪除既有的 `download/threads.com/`、`download/bilibili.com/`——那兩個
資料夾目前是空的，補上別名後它們會因為上面「空來源過濾」自然從清單消失，不是因為被搬走。

### 封面牆的抓取狀態指示（驗收提出的開放問題，這次自己決定並說明理由）

驗收發現：一本書的 metadata 抓取狀態（從沒抓過／被擋／找不到／網路錯誤）目前只有打開
編輯面板才看得到，幾百本書排在牆上完全看不出哪些需要處理。**決定**：`list_source_books()`
（封面牆資料源）多回傳一個 `needs_fetch_attention`（布林值）——**完全不花額外成本**：
`meta_fetch_status` 本來就在那一次 `doujin_repo.get_books()` 批次查詢裡，只是原本沒有
透出去。只有三種狀態算「需要注意」：`blocked`／`not_found`／`network_error`
（`doujin_meta_service.ATTENTION_FETCH_STATUSES`）——**刻意排除**「從沒抓過」（大多數
書都是這狀態，全部標記等於沒有訊號，只有噪音）跟 `no_gallery_id`／`unsupported_source`
（這兩種是來源/資料夾本身的性質，重試永遠不會變，標了也沒用，只會讓使用者白按）。前端
`DoujinBookWall.vue` 顯示一個小的 ⚠ 徽章。

### 刻意沒做（block 1 範圍外，見 dispatch brief 的 Scope 段）

- Wishlist / 未下載書籍（沒有磁碟資料夾的紀錄）——block 2。
- 匯入舊 hentaiViewer 的 `allData.json`——block 2。
- 圖片標籤 / LLM / WD14——不同專案。
- 全庫搜尋、全庫掃描或雜湊——未做。
- 沒有動 general 模式來源本身的 item_count 演算法（`_iter_leaf_items` 邏輯不變，只有
  doujinshi 模式改用更便宜的直屬子目錄計數，見上）；`gallery_service.list_items/
  list_files` 邏輯完全不變。
- exhentai 的抓取器／瀏覽 cookie 需求——已從範圍移除，不是延後。

### 測試

`tests/test_doujin_service.py` + `tests/test_gallery_service.py` + 新增的
`tests/test_path_service.py`，`py -3.11 -m pytest -q` 全綠，**197 案例**（`tests/`
全量）。本輪新增/修正涵蓋：`resolve_mode` 對 exhentai 移除後仍正確解析（wnacg/nhentai/
18comic 仍是 doujinshi，exhentai 現在跟其他一般來源一起走 general）、
`_count_immediate_subdirs`（doujinshi 來源 item_count＝「一子資料夾一本書」，含一本書
資料夾本身帶子目錄的情境）、空來源過濾（含「有內容的來源在有空來源同時存在時仍正常顯示」）、
`needs_fetch_attention` 的三種正向/負向情境（從沒抓過＝false、`ok`＝false、
`blocked`/`not_found`/`network_error`＝true、`no_gallery_id`＝false）、
`path_service` 兩筆新別名 + 既有幾筆回歸樣本。

另外對真實 `download/`（全程唯讀，`DOWNLOAD_DIR` 用環境變數指到真實路徑、`DATA_DIR`
指到 `data/app.db` 的私有拷貝，never the live 7601 db）做了新舊版本 `list_categories()`
的前後對比量測（同一支解譯器行程內背靠背跑，排除快取差異）：舊版 16.4 秒／20 個分類
（含 4 個空的殘留來源、wnacg 算出 513）；新版 9.6～10.9 秒／16 個分類（4 個空來源已過濾、
wnacg 算出 522、exhentai 變成 general 模式）——**新版反而更快**，因為本子來源不再跑
`_iter_leaf_items` 那套逐本書掃描。剩下的時間全部是 pixiv（81,040 檔案）等一般模式來源
既有的遞迴掃描，這次沒有動。驗證完畢後 `data/app.db` MD5 與驗證前完全一致，
`download/` 底下四個空殘留資料夾（`bilibili.com`/`minecraft`/`threads.com`/`youtube`）
逐一確認仍存在於磁碟上。
