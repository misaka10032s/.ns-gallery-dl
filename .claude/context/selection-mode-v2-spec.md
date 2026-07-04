# Selection Mode v2 — spec (approved 2026-07-04)

> Design approved by owner via @PM brainstorming session. Implements four user pain points:
> thumbnail-vs-original URLs, oversized images, virtual-scroll pages, bulk picking via a
> uniform-tile overview, plus selection persistence across mode toggles.

## Resolved decisions (do not re-open)

1. Bahamut: article body (`c-article__content`) images ONLY — comment-area thumbnails stay out of scope.
2. Gallery overview = in-page fullscreen overlay, NOT a separate browser window.
3. After a successful "下載所選" submit: selection auto-clears (notification shows count). Failed submit keeps it.
4. In-page drag-marquee is CANCELLED permanently; marquee exists only inside the overview grid.

## A. Catalog layer (foundation)

While selection mode is ON, the engine maintains a **catalog** of every image discovered so far:
`{ url (key, resolved original), previewSrc, order }`. MutationObserver keeps appending as the
user scrolls; catalog + selection Set persist in sessionStorage keyed per page URL (same store
as today). ALL selection operations (toggle, select-all, invert, overview) operate on the
catalog; the live DOM is only a visible projection of it.

- Virtual scrolling: DOM nodes being recycled must not lose state; re-mounted nodes get their
  selected visuals restored on rescan.
- Known limitation (accept + document): images never scrolled into existence are not in the
  catalog. No auto-scroll assist in this version.

## B. Original-URL resolution chain (adapter contract extension)

Engine ships a default resolver; adapters may override per site:

1. If an ancestor `<a href>` points at an image extension (jpg/jpeg/png/gif/webp/avif) → use href.
2. Site-specific thumbnail-URL rewrite rules (this version: Bahamut only — strip the
   `?w=…&h=…&fit=…` query from truth.bahamut.com.tw URLs; keep the rule table extensible).
3. Fallback: `data-src || src`.

Sites that submit page URLs for backend resolution (pixiv etc.) keep that behavior — the
resolver applies to image-URL sites only. Existing 5 sites + bahamut adapters must remain
backward-compatible: an adapter that overrides nothing behaves exactly as today.

## C. Overview overlay (main feature)

Toolbar gains 「一覽」 button + Alt+G shortcut → in-page fullscreen overlay:

- Uniform tile grid (~180px, `object-fit: cover`), lazy-loaded (`loading=lazy` /
  IntersectionObserver); tile preview prefers the page's already-loaded thumbnail src
  (catalog previewSrc), falling back to the original URL.
- Interactions: click = toggle; Shift+click = range (catalog order); **drag-marquee inside the
  grid**; 全選 / 反選 / 清除 / 下載所選; selected tiles show a corner check; live selected count.
- Body scroll locked while open; Esc or close button dismisses; overlay and page share the
  same catalog/Set so the catalog keeps growing in the background while the overlay is open
  (new tiles appear dynamically).
- All user-visible text zh-TW.

## D. Selection persistence

`_leave()` (Alt+S off) removes UI/listeners/visuals ONLY — the selection Set and
sessionStorage survive; re-entering restores them. Clearing happens exactly two ways:
the 「清除」 button, or automatically after a successful submit (decision 3).

## E. Oversized-image niceties (in-page)

Selected-state check badge positioned sticky within the image's visible portion; thicker
selected outline. Nothing else — no in-page marquee (decision 4).

## F. Structure, compatibility, acceptance

- Split `static/module/selector.js` into `selector-core.js`, `selector-catalog.js`,
  `selector-overview.js` (+ split/extend CSS as sensible); update every manifest
  content_scripts entry (load order: catalog → core → overview → site adapter).
- The 5 existing site adapters' `register({ getItems })` calls and the bahamut adapter keep
  working without modification (contract is additive).
- Acceptance: `node --check` on all JS; manifest valid + all paths exist; backend pytest suite
  (54) still passes untouched; grep confirms no site adapter file was modified except where an
  explicit resolver override is added (bahamut rewrite rule may live in the bahamut adapter).
- Manual smoke list must cover: pixiv virtual scroll (scroll far, select early items via
  overview, confirm catalog retained), bahamut C.php long thread overview with 100+ images,
  oversized-strip image badge, Alt+S off/on persistence, submit-success auto-clear,
  submit-failure retention (server stopped), Esc/scroll-lock behavior.

## Out of scope

Auto-scroll assist; bahamut comment-area images; separate overview window; in-page marquee;
any backend change (this is extension-only — the submit path from v1 is reused as-is).
