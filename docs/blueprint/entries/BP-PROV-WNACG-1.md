---
id: BP-PROV-WNACG-1
title: wnacg.com 站台下載器
system: backend-provider
tags: [backend, provider, wnacg, site-specific]
status: 已完成
request_verbatim: "CLAUDE.md「Site-specific logic：Preserve nhentai + wnacg specialized download logic — do not generalise away」；process.md「providers/sites/：Pixiv / nhentai / wnacg 特化處理」"
decided_date: 2026-05-21
exec_links:
  - app/providers/sites/wnacg.py
  - app/providers/gallery_dl/provider.py
origin: "`app/providers/sites/wnacg.py` 首次入庫於 Build ns-media-hub unified workspace（998bfec，2026-05-21）"
---

## 設計說明

`app/providers/sites/wnacg.py`（144 行）是 wnacg.com 本子頁的專用下載器，由
`app/providers/gallery_dl/provider.py` 依網域 `wnacg.com` 分派呼叫（`download()`
第 169-172 行）。除圖片直抓外，額外支援**壓縮檔下載並解壓**：
可選依賴 `py7zr`（`.7z`）與 `rarfile`（`.rar`），皆以 `try/except ImportError` 包裹
（缺套件時該格式跳過，不中斷其他格式）；`zipfile`（標準庫）恆可用。
`_config_link()` 解析頁面內嵌 script 取得下載設定，`cloudscraper` + `BeautifulSoup`
處理反爬蟲頁面。

### 誠實現況

`py7zr`/`rarfile` 屬選用依賴 —— 若執行環境未安裝，對應壓縮格式的檔案會靜默跳過而非
報錯；本 blueprint seeding 未逐一驗證這兩個套件目前是否已裝在 `requirements.txt`／
`venv`（若要精確判斷，需查 `requirements.txt` 內容，非本次程式碼盤點範圍）。
沒有針對本檔的獨立 pytest 覆蓋；`download/wnacg/` 目錄下有真實下載內容作為功能存在的
旁證，但不構成結構化測試紀錄，故不填 `tests:` 區塊。

## 錯誤訊息遮蔽（2026-09-02 加入）

`_sanitize_error()` 負責在下載失敗訊息進入 `jobs.error` / `history_entries.meta.error`
（前端 HistoryView / JobsView 會直接顯示）之前，把敏感片段拔掉。目前遮蔽的範圍：

- URL 的 **query string**（`?token=…` 之類的簽章參數）
- URL 的 **fragment**（`#access_token=…`）
- URL 的 **userinfo**（`https://user:pass@host/…`）
- 本機**絕對路徑**（呼叫端以 `paths=` 傳入者，含 Windows `OSError.__str__()`
  會把反斜線加倍的變體）
- urllib3 那種**無 scheme** 的 `/path?query` 形狀

保留（刻意不遮）：HTTP 狀態碼、主機名、port、路徑、**檔名**、urllib3 的 `(Caused by …)` 原因。
這些是站主自己排查失敗時唯一的線索，遮掉會讓錯誤訊息失去用途。

### 已知可接受殘留風險 — 路徑段中的簽章（站主 2026-09-02 決定）

若某個下載服務把簽章**放在 URL 路徑裡**（例如
`https://cdn.example.com/dl/AKIA…SECRET/檔名.zip`，S3／R2 風格），那段簽章**不會被遮蔽**，
會原封不動出現在歷史紀錄的錯誤訊息上。

- **技術上為何如此**：遮蔽器只拔 query／fragment／userinfo，路徑段整段保留。
- **為何不修**：站主在 2026-09-02 明確選擇「不遮，寫成已知可接受風險」。遮掉路徑
  等於連檔名一起遮掉，而檔名是站主判斷「是哪一個檔案下載失敗」的主要依據；
  這是單機自用工具（127.0.0.1，無外部觀眾），權衡後可讀性優先。
- **邊界**：本條僅限「簽章位於路徑段」。query／fragment／userinfo／本機絕對路徑
  仍必須遮蔽，未來任何改動不得放寬那四項。
- **另一個先天限制（非本條決定，記錄用）**：不含 URL 形狀的**裸 token**
  （例如被回顯的 `Authorization: Bearer …` 標頭）無法用 URL 規則遮蔽。目前
  `requests` / `cloudscraper` 都不會把請求標頭寫進例外的 `str()`，故實務上不可達；
  但因此本函式只能描述為「遮蔽 **URL 攜帶的**憑證」，不可描述為「遮蔽憑證」。

### 稽核紀錄

- 2026-09-01 首版遮蔽器上線（分支 `feat/render-history-error`）。
- 2026-09-02 opus 級獨立安全審查建構並實際執行 34 組破解樣本，找出 5 個缺陷：
  下載寫檔站點漏傳 `paths=`（絕對路徑外洩，已證實可觸發）、三個 return 站點完全未經
  遮蔽（含 CONFIG API 簽章連結鑄造路徑）、正則大小寫敏感、`_PATH_QUERY_RE` 前置
  lookbehind 過嚴、`_strip_userinfo()` 在密碼含 `/` 時會輸出**錯誤的主機名**。
  五項全部修正（commit `b91e523`）；路徑段簽章一項依上述決定不修，改記於本條。

### 過度遮蔽也是缺陷（2026-09-02 第三輪審查）

第二輪修正 `_strip_userinfo` 時改用「字串中最後一個 `@`」判斷憑證邊界，結果**反向壞掉**：
當 `@` 出現在 URL 的**路徑**裡（站台給的 `FILE_NAME` 可以含 `@`，檔名清洗黑名單
`[\/*?:",<>|]` 不含 `@`），遮蔽器會把 `@` 之前整段當成憑證刪掉，輸出
`https://CD.zip` —— 真實主機、路徑、檔名全部消失，還捏造一個不存在的主機名。

這條記在這裡是因為它改變了驗收標準：**「敏感字串不見了」不足以證明遮蔽正確**。
只斷言「秘密已消失」的測試對過度遮蔽是盲的，這個回歸就是這樣通過完整 gate 的。
因此本模組的遮蔽測試一律要同時斷言**該保留的東西還在**（主機名、檔名）。

那一版的修正公式（「`@` 其前無 `/`，或 `:` 出現在第一個 `/` 之前」）**後來被證明不完整**：
`host:port` 與 IPv6 字面值裡的冒號都會滿足它，於是帶通訊埠或 IPv6 的網址又重現同一個
捏造主機名的缺陷。它已被下面的設計取代，僅留作記錄。

## 定案設計:帳密一律換成佔位符,其餘一律保留（站主 2026-09-02 決定）

站主原話:「帳號密碼一律不顯示，用[@acc], [@pw] 之類的來取代，但其他包含原因 目標
網址之類的一定要顯示」。

這句話同時解掉了前三輪解不掉的兩難。前面每一版都是「把憑證那一段**刪掉**」,而刪除
必然有猜錯邊界的風險 —— 猜錯就會連主機名、路徑、檔名一起消失,還捏造出一個不存在的
主機名。**換成佔位符則結構上不可能有那種失敗**:主機從來不被移除,只有 userinfo 那一段
被覆寫。

### 判斷規則（RFC 3986,不再用啟發式）

- authority 是 `://`（或開頭的 `//`）到**第一個** `/`、`?`、`#` 之間那一段。之後的東西
  永遠不是 userinfo。
- 只有 authority **之內**的最後一個 `@` 才是 userinfo 邊界。
- 帳號換成 `[@acc]`,密碼換成 `[@pw]`;主機、通訊埠、方括號、路徑、查詢、片段一律不動。
- authority 內沒有 `@` 就完全不碰。
- authority 內若有一個冒號而右側不是通訊埠形狀（非 1–5 位數字）,那不可能是通訊埠,視為
  憑證換成 `[@pw]`。IPv6 的方括號要先排除,否則位址自己的冒號會被誤判。
- 空的 userinfo（`https://@host/…`）直接把那個無意義的 `@` 去掉,不放佔位符 —— 放了等於
  宣稱有一份憑證被保護,那是對遮蔽本身的假陳述。

### 「什麼算憑證」的裁判是 `urlsplit`,不是字串外觀

這是第五輪審查真正解掉爭議的一句,值得寫下來:`requests`/`urllib3` 就是用
`urlsplit().username` / `.password` 組認證標頭的,所以**它說有憑證才算有憑證**。

前三輪反覆爭論的幾個「疑似漏遮」形狀,拿這個判準一量就結案了:
`https://user:PASS/WORD@host/…` 的 `urlsplit` 回報 username/password 皆為 `None`
（`user` 是主機、`PASS` 是無效通訊埠、其餘是路徑),所以那裡沒有任何 HTTP 客戶端會送出的
憑證,看得到的是**主機**和**路徑**,而那兩樣正是站主要求必須顯示的。同理
`us/er:PW@host/…`、`user/PW@host/…`、`https:////user:PW@host/…` 也都沒有憑證 ——
`/` 在 userinfo 裡不合法,必須百分比編碼,而編碼後的 `user:PASS%2FWORD@host` 是**完整
遮蔽**的（實測）。所以這些形狀**原樣保留才是正確行為**,遮它們反而就是那個已經上線過
兩次的過度遮蔽缺陷。

### 驗收標準（因為這輪的教訓）

**「敏感字串不見了」不足以證明遮蔽正確。** 只斷言「秘密已消失」的測試對過度遮蔽是盲的,
那個捏造主機名的回歸就是這樣通過完整 gate 的 —— 兩次。所以本模組的遮蔽測試一律要同時
斷言**該保留的東西還在**（主機、通訊埠、路徑、檔名),而且邊界表以**完全相等**斷言,
因為過度遮蔽的實作根本無法滿足完全相等。邊界表必須包含帶通訊埠、IPv6 字面值,以及
「同時有 userinfo 又有路徑 `@`」這三種形狀 —— 前兩次的缺陷都住在那裡。

### 已知的兩個小瑕疵（不阻擋,記錄用）

- RFC 允許空通訊埠（`https://host.example:/dl/a.zip`,意思是用該 scheme 的預設埠),但
  `^[0-9]{1,5}$` 至少要一位數字,所以會輸出 `host.example:[@pw]`。沒有任何真實資訊被
  破壞（被取代的那一段是空的),只是多了一個「這裡有憑證被藏起來」的誤導標記。
- 兩種 RFC 不合法的 authority（通訊埠超過 5 位數、未加方括號的 IPv6）同樣會拿到
  `[@pw]`。這種網址任何 RFC 解析器都拒收,不可能成為有效下載連結,所以只是外觀問題。

兩者的修法都只是把 `{1,5}` 改成 `{0,5}` 加一列邊界表,下次動到這個檔案時再一併處理。
