---
id: BP-CORE-SECURITY-1
title: 同源 CSRF 防護 + SSRF 防護（misc.py 共用 guard）
system: backend-core
tags: [backend, security, csrf, ssrf]
status: 已完成
request_verbatim: "@PM registry ns-media-hub.md Roadmap（現行未勾待辦）：「Cookie 變更 API — 無 auth/CSRF 保護（資安：任意請求皆可改 cookie）」"
decided_date: 2026-06-20
exec_links:
  - app/api/routes/misc.py
  - app/api/routes/downloaders.py
origin: "`_check_same_origin()`/`_is_safe_url()` 首次入庫於 commit f2718f1（2026-06-20，「feat+security(ns-media-hub): docs sync, /gallery SPA fallback, cookie CSRF guard, tests, WAL」）"
---

## 設計說明

`app/api/routes/misc.py` 提供兩個跨端點共用的安全 guard：

### 同源 CSRF 防護（`_check_same_origin`）

檢查請求的 `Origin`（優先）或 `Referer` header 是否為 `127.0.0.1`/`localhost`；
兩者皆缺（如 `curl` 直接呼叫）視為本機工具呼叫允許通過；host 不符則回
`(False, "拒絕跨來源的 cookie 變更請求。")`，呼叫端回 HTTP 403。目前套用於：

- `POST`/`PUT`/`DELETE /api/cookies`（`BP-SVC-CREDENTIALS-1`）
- `POST /api/downloaders/update`（`BP-SVC-UPDATER-1`，`app/api/routes/downloaders.py`
  直接 import 復用同一函式）

### SSRF 防護（`_is_safe_url`）

`POST /api/fetch_status`（`app.py` 內建的除錯用「探測 URL 是否可存取」端點）呼叫，
拒絕非 http/https scheme，並用 `socket.getaddrinfo` 解析主機後檢查
`is_loopback`/`is_private`/`is_link_local`/`is_reserved`/`is_unspecified`，
防止此端點被用來探測內網（SSRF）。

### 明確已知的殘留缺口（程式碼自己的 docstring 標註）

`_check_same_origin` 的 docstring 明確自陳：「這是 same-origin CSRF check only ——
this app's mutating endpoints 完全沒有 session/token 驗證……只在嚴格本機
（127.0.0.1）情境下算安全，若此伺服器曾對外暴露則不安全」。這不是本次盤點發現的
新問題，是原始碼作者自己已記錄的設計取捨，本條目原樣轉載以維持誠實。

### 誠實現況 —— 本次盤點的重要修正

**@PM registry 現行仍記載「Cookie 變更 API — 無 auth/CSRF 保護」為未勾選待辦**，
但這個防護實際上已於 2026-06-20（commit f2718f1）加入，`tests/test_csrf_protection.py`
6 個案例覆蓋「無 header／本機 Origin／本機 named Origin／外部 Origin／外部
Referer／本機 Referer」情境。Registry 對此項目的記載已過期，本 blueprint 條目
以程式碼與 git 歷史為準；建議下次 registry 維護時同步勾除。
