---
id: BP-SVC-AUTH-COOLDOWN-1
title: 登入失效偵測與冷卻（auth_failure 分類 + auth_cooldown 6h TTL + 錯誤訊息去識別化）
system: backend-service
tags: [backend, service, auth, cookies, security, storage, api]
status: 開發中
request_verbatim: "另外有些下載需要登入的，然後登入過期你要給我個自動刷新的方式不要還要我手動更新"
decided_date: 2026-09-02
exec_links:
  - app/domain/auth_failure.py
  - app/domain/auth_cooldown.py
  - app/domain/error_sanitizer.py
  - app/storage/repositories/auth_cooldown_repo.py
  - app/storage/db.py
  - app/config/settings.py
  - app/services/cookie_service.py
  - app/api/routes/misc.py
  - app/providers/gallery_dl/provider.py
  - app/providers/ytdlp/provider.py
depends_on:
  - BP-CORE-STORAGE-1
  - BP-CORE-SECURITY-1
  - BP-SVC-CREDENTIALS-1
  - BP-PROV-COOKIES-1
  - BP-PROV-GALLERYDL-1
  - BP-PROV-YTDLP-1
origin: "branch `fix/auth-failure-handling`（merge-base `f8a94f3`）；本條目於程式碼仍在審查階段時補記，因為 review-3 認定「新增資料表 + 新增公開端點 + 新增常數卻無 blueprint 紀錄」本身即為阻擋項"
revisions:
  - date: 2026-09-02
    summary: "首次入庫：記錄 auth_failure 三值分類、auth_cooldown 資料表與 6 小時 TTL、DOMAIN_COOLDOWN_ALIASES、DELETE /api/cookies/<domain>/cooldown 手動解除端點，以及 cookie 重新種入／刪除時的自動解除"
---

## 為什麼有這個系統

站主的原始要求是「登入過期要有自動刷新，不要還要我手動更新」。真正能自動化的第一步
不是刷新憑證本身（那需要站方的 refresh token，多數來源沒有），而是**認出「這次失敗
是因為登入失效」並停止用同一份失效憑證反覆撞牆**——否則每個排隊中的任務都會拿著同一
份過期 cookie 再打一次，對站方而言就是一串可疑的失敗登入。

因此本系統做三件事：分類（這次失敗是不是 AUTH？）→ 冷卻（是的話，這個網域先別再帶
憑證了）→ 去識別化（要把原因顯示給站主看，就不能把憑證跟本機路徑一起顯示出去）。

## 一、失敗分類（`app/domain/auth_failure.py`）

`classify(error)` 回傳三值之一——**刻意不是布林值**：

- `AUTH`（`"auth"`）：站方明確拒絕了一個帶憑證的請求。
- `NOT_AUTH`（`"not_auth"`）：明確不是登入問題（例如 gallery-dl 的 `NotFoundError`）。
- `INDETERMINATE`（`"indeterminate"`）：看不出來。

第三個值是設計重點：**只有 `AUTH` 會武裝冷卻**。看不出來的情況不武裝，因為誤判會讓
一個健康的網域被鎖 6 小時；寧可漏判（下次失敗再抓）也不誤判。

比對規則是具名 regex（`_GALLERY_DL_AUTH_CLASS_RE`、`_GALLERY_DL_NOT_FOUND_RE`、
`_GALLERY_DL_CHALLENGE_RE`、`_REDIRECT_TO_LOGIN_RE`、`_REDIRECT_TO_CHALLENGE_RE`、
`_YTDLP_LOGIN_HINT_RE`），兩個 provider（gallery-dl / yt-dlp）的錯誤字串形狀不同，
但共用同一個分類器。

## 二、冷卻（`app/domain/auth_cooldown.py` + `auth_cooldown` 資料表）

### 資料表 —— 補 `BP-CORE-STORAGE-1` 未列的第五張表

```sql
CREATE TABLE IF NOT EXISTS auth_cooldown (
    domain                TEXT PRIMARY KEY,
    cooldown_until        TEXT NOT NULL,
    last_classified_error TEXT DEFAULT '',
    updated_at            TEXT NOT NULL
);
```

兩個必須寫下來的設計決定：

1. **一列一個「網域」，不是一列一個 provider。** gallery-dl 與 yt-dlp 都可能被派去處理
   同一個網域（`app.config.settings.MULTI_PROVIDER_DOMAINS`，例如 x.com／facebook.com），
   而它們會**讀同一份 cookie 檔**。若按 provider 分列，其中一邊武裝了冷卻，另一邊照樣
   拿著同一份失效憑證再撞一次——冷卻等於沒有。

2. **存在 SQLite，不是記憶體。** `-s` 和 `-b` 是兩次獨立的 `dl.cmd` 呼叫，是兩個作業系統
   行程，不共用 Python 全域變數，但會開同一個 `data/app.db`。跨行程唯一可靠的共享狀態
   就是資料庫。

### TTL 與解除條件

`AUTH_COOLDOWN_SECONDS = 6 * 60 * 60`（6 小時）。四種解除方式：

| 解除方式 | 觸發點 | 理由 |
|---|---|---|
| 時間到 | `in_cooldown()` 比對 `datetime.now()` | 一般情況 |
| cookie 檔被改動 | `in_cooldown(domain, cookie_path)` 比對 mtime | **憑證換了，冷卻立刻作廢**，不必再等 TTL |
| 站主重新種入 cookie | `cookie_service.save_cookie()` | 重新種入本身就是站主說「我修好了」的訊號；即使內容逐位元相同也算 |
| 站主刪除 cookie | `cookie_service.delete_cookie()`（僅在真的刪掉檔案時） | 之後會以匿名方式嘗試，沒有理由再對著一份不存在的憑證冷卻 |

`in_cooldown()` 的 `cookie_path` 參數是選填且向後相容——不給就是純 TTL 行為。

### 別名折疊（`DOMAIN_COOLDOWN_ALIASES`）

```python
DOMAIN_COOLDOWN_ALIASES = {"twitter.com": "x.com", "fb.watch": "facebook.com"}
```

這是**只給冷卻用**的折疊，`cooldown_domain_key()` 是唯一使用者。cookie 檔命名與
`cookie_entries` 註冊表**刻意不折疊**，仍以呼叫端的字面網域為鍵。

要折疊的原因是兩邊的鍵來源不同：`in_cooldown()` / `record_auth_failure()` 拿到的是
**任務網址的字面主機名**，而 `clear_cooldown()` 拿到的是**站主在 UI／API 填的網域**。
兩者不保證一致——用 twitter.com 網址武裝的冷卻，會在站主以 x.com 重新種入 cookie 後
存活下來，因為對 SQLite 的 PRIMARY KEY 而言那是兩列不相干的資料。

## 三、錯誤訊息去識別化（`app/domain/error_sanitizer.py`）

失敗原因要顯示給站主看（`BP-VIEW-HISTORY-1`），所以顯示前必須先去識別化。設計依據是
站主 2026-09-02 的裁示：**帳號密碼一律不顯示，用 `[@acc]` / `[@pw]` 取代；但原因、目標、
網址一定要顯示。**

`sanitize_error()` 的做法是**取代**而非刪除。這點是四輪反覆後才定案的：刪除必須猜邊界，
猜錯就會連主機名和檔名一起刪掉，甚至捏造出一個不存在的網址顯示給站主——取代則結構上
不可能刪錯，因為主機從來不會被移除。

邊界判定依 RFC 3986：authority 到第一個 `/`、`?` 或 `#` 為止，只有 authority 內的最後一個
`@` 才是 userinfo。判斷「什麼算憑證」以 `urlsplit().username` / `.password` 為準——因為
`requests`／`urllib3` 就是用它來組認證標頭的。

保留（絕不遮蔽）：主機名、port、路徑、**檔名**。過度遮蔽同樣被視為缺陷。

## 四、手動解除端點

`DELETE /api/cookies/<path:domain>/cooldown`

- 用途：站主判斷站方的封鎖已經解除，不想等滿 6 小時。
- **完全不動 cookie jar**，只解除冷卻。
- 與其他 cookie 變更端點共用同一個同源 CSRF 防護（`_check_same_origin`，
  見 `BP-CORE-SECURITY-1`）。
- 冪等：不論原本有沒有冷卻都回 200，`cleared` 欄位說明是否真的解除了什麼。

## 誠實現況 / 已知限制

- **本條目在程式碼合併前寫入。** `status: 開發中`，分支 `fix/auth-failure-handling` 仍在
  審查（review-3 判定 CHANGES-NEEDED）。合併後須以 revision 補記最終 commit。
- **不是「自動刷新憑證」。** 站主要的是自動刷新；本系統只做到「認出失效並停止撞牆 +
  讓站主一鍵解除」。真正的自動刷新需要各站的 refresh token 機制，多數來源沒有——
  這條差距是刻意留下的，不是遺漏。
- **`INDETERMINATE` 不武裝冷卻**，所以認不出來的登入失效仍會反覆重試。這是誤判與漏判
  之間的刻意取捨。
- **測試隔離缺口（review-3 B1，尚未修復）**：`tests/conftest.py` 的 autouse fixture 目前
  只把 `app.storage.db` 的三個路徑導向 tmp，cookie jar／token 檔／download 樹仍指向正式
  資料。本分支新增的測試已開始走 `save_cookie`／`delete_cookie` 這條路徑，而
  `delete_cookie()` 內有 `unlink()`。修復前不得合併。
- **既有污染**：本分支較早的一輪曾把 `auth_cooldown` 資料表實際建到站主的正式
  `data/app.db` 裡（零列資料，未動到任何既有資料）。決定**保留不 drop**——drop 本身
  又是一次對正式資料庫的寫入。
