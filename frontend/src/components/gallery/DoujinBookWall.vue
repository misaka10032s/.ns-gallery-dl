<script setup>
import { computed, ref, watch } from 'vue'

import { fetchDoujinBooks } from '../../api/gallery'
import DoujinBookEditPanel from './DoujinBookEditPanel.vue'
import DoujinBookReader from './DoujinBookReader.vue'

// Doujinshi (本子) mode: cover wall for one source (wnacg / nhentai / 18comic
// / exhentai — whichever app.config.gallery_modes.DOUJINSHI_SOURCES lists).
// One subfolder = one book; clicking a cover opens the page-by-page reader,
// the ✎ button opens the edit panel for that book's own fields + links.
const props = defineProps({
  category: { type: Object, required: true },
})

const books = ref([])
const search = ref('')
const loading = ref(false)

const readingBook = ref(null) // folder_path or null
const editingBook = ref(null) // folder_path or null

const purchaseLabel = {
  purchased: '已購',
  not_purchased: '未購',
}

const filteredBooks = computed(() => {
  const kw = search.value.trim().toLowerCase()
  if (!kw) return books.value
  return books.value.filter((b) =>
    [b.title, b.artist, b.circle, b.series_name].some((v) => (v || '').toLowerCase().includes(kw)),
  )
})

async function loadBooks() {
  books.value = []
  search.value = ''
  loading.value = true
  try {
    books.value = await fetchDoujinBooks(props.category.path)
  } finally {
    loading.value = false
  }
}

function serveUrl(path) {
  return `/api/gallery/serve?p=${encodeURIComponent(path)}`
}

function openReader(book) {
  readingBook.value = book.folder_path
}

function openEdit(book) {
  editingBook.value = book.folder_path
}

function onBookUpdated(updated) {
  const idx = books.value.findIndex((b) => b.folder_path === updated.folder_path)
  if (idx !== -1) {
    books.value[idx] = {
      ...books.value[idx],
      title: updated.title,
      artist: updated.artist,
      circle: updated.circle,
      series_id: updated.series_id,
      series_name: updated.series_name,
      purchase_state: updated.purchase_state,
      page_count: updated.page_count,
      cover: updated.cover,
    }
  }
}

watch(() => props.category?.path, loadBooks, { immediate: true })
</script>

<template>
  <div>
    <div class="gallery-toolbar">
      <input
        v-model="search"
        class="form-input gallery-search"
        type="search"
        placeholder="搜尋標題／作者／社團..."
      />
      <span class="gallery-count">{{ filteredBooks.length }} 本</span>
    </div>

    <div v-if="loading" class="empty-state">載入中…</div>
    <div v-else-if="!filteredBooks.length" class="empty-state">此分類沒有本子。</div>
    <div v-else class="book-wall">
      <div v-for="book in filteredBooks" :key="book.folder_path" class="book-card">
        <button class="book-card__cover" type="button" @click="openReader(book)">
          <img
            v-if="book.cover"
            :src="serveUrl(book.cover)"
            :alt="book.title"
            loading="lazy"
          />
          <div v-else class="book-card__no-cover">📖</div>
          <span
            class="book-card__purchase"
            :class="{ 'book-card__purchase--owned': book.purchase_state === 'purchased' }"
          >
            {{ purchaseLabel[book.purchase_state] ?? book.purchase_state }}
          </span>
        </button>
        <div class="book-card__label">
          <span class="book-card__title">{{ book.title }}</span>
          <span v-if="book.artist || book.circle" class="book-card__sub">
            {{ [book.circle, book.artist].filter(Boolean).join(' / ') }}
          </span>
          <div class="book-card__meta-row">
            <span class="book-card__pages">{{ book.page_count }} 頁</span>
            <button class="book-card__edit-btn" type="button" @click="openEdit(book)">
              ✎ 編輯
            </button>
          </div>
        </div>
      </div>
    </div>

    <DoujinBookReader
      v-if="readingBook"
      :folder-path="readingBook"
      @close="readingBook = null"
    />

    <DoujinBookEditPanel
      v-if="editingBook"
      :folder-path="editingBook"
      @close="editingBook = null"
      @updated="onBookUpdated"
    />
  </div>
</template>

<style lang="scss" scoped>
@use '../../styles/tokens' as *;

.gallery-toolbar {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1.1rem;
  flex-wrap: wrap;
}

.gallery-search {
  flex: 1;
  max-width: 24rem;
  min-width: 0;
}

.gallery-count {
  color: $slate-500;
  font-size: 0.88rem;
  white-space: nowrap;
}

.book-wall {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 1.1rem;
}

.book-card {
  display: flex;
  flex-direction: column;
  border: 1px solid $slate-200;
  border-radius: 0.9rem;
  background: #fff;
  overflow: hidden;
  transition: box-shadow 0.15s, border-color 0.15s;

  &:hover {
    box-shadow: 0 6px 20px rgba(15, 23, 42, 0.1);
    border-color: $blue-600;
  }
}

.book-card__cover {
  position: relative;
  display: block;
  width: 100%;
  aspect-ratio: 3 / 4;
  background: $surface-soft;
  border: none;
  padding: 0;
  cursor: pointer;
  overflow: hidden;

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }
}

.book-card__no-cover {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 2.2rem;
  color: $slate-400;
}

.book-card__purchase {
  position: absolute;
  top: 0.4rem;
  left: 0.4rem;
  padding: 0.15rem 0.5rem;
  border-radius: 999px;
  font-size: 0.68rem;
  font-weight: 700;
  background: rgba(15, 23, 42, 0.65);
  color: #fff;

  &--owned {
    background: $blue-600;
  }
}

.book-card__label {
  padding: 0.55rem 0.65rem 0.6rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.book-card__title {
  font-size: 0.83rem;
  font-weight: 600;
  color: $slate-900;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-all;
}

.book-card__sub {
  font-size: 0.74rem;
  color: $slate-500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.book-card__meta-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 0.1rem;
}

.book-card__pages {
  font-size: 0.74rem;
  color: $slate-500;
}

.book-card__edit-btn {
  border: none;
  background: transparent;
  color: $blue-600;
  font-size: 0.74rem;
  font-weight: 600;
  cursor: pointer;
  padding: 0.1rem 0.3rem;

  &:hover {
    text-decoration: underline;
  }
}

@include down($bp-sm) {
  .gallery-toolbar {
    gap: 0.6rem;
  }

  .gallery-search {
    max-width: 100%;
    flex: 1 1 100%;
  }

  .book-wall {
    grid-template-columns: repeat(auto-fill, minmax(112px, 1fr));
    gap: 0.65rem;
  }

  .book-card__title {
    font-size: 0.78rem;
  }
}
</style>
