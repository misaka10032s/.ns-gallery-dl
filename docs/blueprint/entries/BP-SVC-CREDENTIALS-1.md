---
id: BP-SVC-CREDENTIALS-1
title: Cookie CRUD 服務 + Token 儲存（cookie_service + token_service + /api/cookies + /api/auth/pixiv）
system: backend-service
tags: [backend, service, cookies, tokens, api, security]
status: 已完成
request_verbatim: "@PM registry ns-media-hub.md Roadmap（現行未勾待辦）：「Cookie 變更 API — 無 auth/CSRF 保護（資安：任意請求皆可改 cookie）」"
decided_date: 2026-05-21
exec_links:
  - app/services/cookie_service.py
  - app/services/token_service.py
  - app/api/routes/misc.py
  - app/api/routes/auth.py
depends_on:
  - BP-CORE-SECURITY-1
  - BP-PROV-COOKIES-1
origin: "`app/services/cookie_service.py`、`app/services/token_service.py` 首次入庫於 Build ns-media-hub unified workspace（998bfec，2026-05-21）；CSRF 同源防護補於 commit f2718f1（2026-06-20）"
revisions:
  - date: 2026-06-20
    summary: "commit f2718f1：cookie 變更端點（POST/PUT/DELETE /api/cookies）加上同源（Origin/Referer）CSRF 防護，`tests/test_csrf_protection.py` 6 案例覆蓋"
  - date: 2026-07-23
    summary: "blueprint seeding 核對：@PM registry 目前仍記載「Cookie 變更 API — 無 auth/CSRF 保護」為待辦，但現行程式碼（app/api/routes/misc.py `_check_same_origin`）已於 2026-06-20 修好——registry 記載已過期，本條目以程式碼現況為準；registry 應於下次維護同步"
  - date: 2026-09-02
    summary: "分支 `fix/auth-failure-handling`（審查中）新增 `DELETE /api/cookies/<domain>/cooldown`（手動解除登入失效冷卻，不動 cookie jar，同源防護，冪等），且 `save_cookie()`／`delete_cookie()` 會自動解除該網域冷卻——見 `BP-SVC-AUTH-COOLDOWN-1`"
---

## 設計說明

### Cookie CRUD（`cookie_service.py`，111 行）

`list_cookies()`/`read_cookie()`/`save_cookie()`/`delete_cookie()`——寫入前
`_normalize_cookie_text()` 接受兩種輸入格式並統一轉成 Netscape cookie 檔格式：
瀏覽器 DevTools 複製的 `Cookie: a=1; b=2` header 字串，或直接貼上完整 Netscape
格式檔案內容（已是該格式則原樣保留）。`_cookie_file_path()` 對每個網域做路徑逃逸
防護（`resolved` 必須落在 `COOKIE_DIR` 內才允許寫入）。

### Token 儲存（`token_service.py`，20 行）

`load_tokens()`/`save_tokens()`——單純的 `data/tokens.json` JSON 讀寫，目前唯一
使用者是 `BP-PROV-PIXIV-1` 的 refresh token 快取。

### API 端點（`app/api/routes/misc.py` + `auth.py`）

- `GET /api/cookies`、`GET /api/cookies/<domain>`：唯讀，無防護（`ENABLE_COOKIE_API`
  功能旗標控制是否啟用整組端點）。
- `POST`/`PUT`/`DELETE /api/cookies`：**寫入端點皆先過 `_check_same_origin()`**
  （`BP-CORE-SECURITY-1`），非同源請求回 403。
- `DELETE /api/cookies/<domain>/cooldown`：手動解除登入失效冷卻，**完全不動 cookie
  jar**；同樣過同源防護；冪等（`cleared` 欄位說明是否真的解除了什麼）。分支
  `fix/auth-failure-handling` 新增，審查中——見 `BP-SVC-AUTH-COOLDOWN-1`。
- `GET /api/auth/pixiv`：只回傳 `{"has_refresh_token": bool}`，不含 token 本身。

### 誠實現況 —— registry 記載已過期，此為本次盤點的重要修正

`@PM` registry `ns-media-hub.md` 現行仍列著「Cookie 變更 API — 無 auth/CSRF
保護（資安：任意請求皆可改 cookie）」為未勾選待辦，但程式碼與 `git log`
顯示這個防護**已於 2026-06-20（commit f2718f1）補上**，且有 6 個 pytest 案例
（`tests/test_csrf_protection.py`）覆蓋「無 header 允許/本機 origin 允許/外部
origin 拒絕/外部 referer 拒絕」等情境。**仍要注意**：這只是同源檢查，不是
session/token 驗證——`misc.py::_check_same_origin` docstring 自己也明確標註
「KNOWN GAP: no session/token auth anywhere...local-only (127.0.0.1) 假設下才安全」。
即本機部署下已足夠，若曾對外暴露則不安全。
