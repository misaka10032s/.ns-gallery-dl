import { apiRequest } from './client'

// Doujinshi (本子) mode API — cover wall / reader / edit panel. Mirrors the
// backend endpoints registered in app/api/routes/gallery.py; kept as a thin
// wrapper so GalleryView.vue and its child components never build query
// strings or JSON bodies inline.

export function fetchDoujinBooks(source) {
  return apiRequest(`/api/gallery/doujin/books?source=${encodeURIComponent(source)}`)
}

export function fetchDoujinBookDetail(folderPath) {
  return apiRequest(`/api/gallery/doujin/book?path=${encodeURIComponent(folderPath)}`)
}

export function updateDoujinBook(folderPath, fields) {
  return apiRequest('/api/gallery/doujin/book', {
    method: 'PUT',
    body: { folder_path: folderPath, ...fields },
  })
}

export function addDoujinLink(folderPath, label, url) {
  return apiRequest('/api/gallery/doujin/book/links', {
    method: 'POST',
    body: { folder_path: folderPath, label, url },
  })
}

export function deleteDoujinLink(folderPath, linkId) {
  return apiRequest(
    `/api/gallery/doujin/book/links/${linkId}?folder_path=${encodeURIComponent(folderPath)}`,
    { method: 'DELETE' },
  )
}

export function fetchDoujinBookMeta(folderPath) {
  return apiRequest('/api/gallery/doujin/book/fetch-meta', {
    method: 'POST',
    body: { folder_path: folderPath },
  })
}

// 分類 (series) — controlled vocabulary combobox.
export function searchDoujinSeries(query) {
  return apiRequest(`/api/gallery/doujin/series?q=${encodeURIComponent(query ?? '')}`)
}

// Resolves to an existing series (exact case/space-insensitive match),
// raises on a near-duplicate (error.status === 409, error.payload.candidates)
// unless confirm=true, or creates a brand-new one.
export function createOrResolveDoujinSeries(name, confirm = false) {
  return apiRequest('/api/gallery/doujin/series', {
    method: 'POST',
    body: { name, confirm },
  })
}
