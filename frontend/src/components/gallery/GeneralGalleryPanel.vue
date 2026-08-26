<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { apiRequest } from '../../api/client'

// General-mode gallery (pixiv / bahamut / yandere / facebook / twitter /
// discord / gelbooru / kemono.partyfanbox / x / everything not configured as
// doujinshi — app.config.gallery_modes): thumbnail wall, at most grouped by
// artist folder. Unchanged behavior from the pre-split GalleryView.vue —
// only relocated into its own component so the doujinshi mode could be added
// without growing one view file toward a thousand lines.
const props = defineProps({
  category: { type: Object, required: true },
})

const items = ref([])
const search = ref('')
const loadingItems = ref(false)

const viewerFiles = ref([])
const viewerIndex = ref(0)
const viewerOpen = ref(false)
const viewerItemName = ref('')

const filteredItems = computed(() => {
  const kw = search.value.trim().toLowerCase()
  if (!kw) return items.value
  return items.value.filter((item) => item.name.toLowerCase().includes(kw))
})

const currentFile = computed(() => viewerFiles.value[viewerIndex.value] ?? null)

async function loadItems() {
  items.value = []
  search.value = ''
  loadingItems.value = true
  try {
    items.value = await apiRequest(`/api/gallery/items?category=${encodeURIComponent(props.category.path)}`)
  } finally {
    loadingItems.value = false
  }
}

async function openItem(item) {
  let files
  if (item.type === 'file') {
    files = [{ name: item.name, path: item.path, media_type: item.media_type }]
  } else {
    files = await apiRequest(`/api/gallery/files?path=${encodeURIComponent(item.path)}`)
  }
  viewerFiles.value = files
  viewerIndex.value = 0
  viewerItemName.value = item.name
  viewerOpen.value = true
}

function closeViewer() {
  viewerOpen.value = false
  viewerFiles.value = []
}

function prevFile() {
  if (viewerIndex.value > 0) viewerIndex.value--
}

function nextFile() {
  if (viewerIndex.value < viewerFiles.value.length - 1) viewerIndex.value++
}

function onViewerKeydown(e) {
  if (!viewerOpen.value) return
  if (e.key === 'ArrowRight' || e.key === 'ArrowDown') nextFile()
  if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') prevFile()
  if (e.key === 'Escape') closeViewer()
}

function serveUrl(path) {
  return `/api/gallery/serve?p=${encodeURIComponent(path)}`
}

watch(() => props.category?.path, loadItems, { immediate: true })

onMounted(() => {
  window.addEventListener('keydown', onViewerKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onViewerKeydown)
})
</script>

<template>
  <div>
    <!-- Search -->
    <div class="gallery-toolbar">
      <input
        v-model="search"
        class="form-input gallery-search"
        type="search"
        placeholder="搜尋名稱..."
      />
      <span class="gallery-count">{{ filteredItems.length }} 個項目</span>
    </div>

    <!-- Item grid -->
    <div v-if="loadingItems" class="empty-state">載入中…</div>
    <div v-else-if="!filteredItems.length" class="empty-state">此分類沒有項目。</div>
    <div v-else class="gallery-grid">
      <button
        v-for="item in filteredItems"
        :key="item.path"
        class="gallery-card"
        type="button"
        @click="openItem(item)"
      >
        <div class="gallery-card__thumb">
          <img
            v-if="item.preview"
            :src="serveUrl(item.preview)"
            :alt="item.name"
            loading="lazy"
          />
          <div v-else class="gallery-card__no-thumb">
            {{ item.media_type === 'video' ? '▶' : '📁' }}
          </div>
        </div>
        <div class="gallery-card__label">
          <span class="gallery-card__name">{{ item.name }}</span>
          <span class="gallery-card__meta">{{ item.file_count }} 個檔案</span>
        </div>
      </button>
    </div>

    <!-- Viewer modal -->
    <Teleport to="body">
      <div v-if="viewerOpen" class="viewer-backdrop" @click.self="closeViewer">
        <div class="viewer-shell">

          <!-- Top bar -->
          <div class="viewer-topbar">
            <div class="viewer-topbar__title">
              {{ viewerItemName }}
              <span class="viewer-topbar__pos">
                {{ viewerIndex + 1 }} / {{ viewerFiles.length }}
              </span>
            </div>
            <div class="viewer-topbar__actions">
              <a
                v-if="currentFile"
                :href="serveUrl(currentFile.path)"
                :download="currentFile.name"
                class="btn btn--ghost btn--small"
                target="_blank"
              >↓ 下載</a>
              <button class="btn btn--ghost btn--small" type="button" @click="closeViewer">✕ 關閉</button>
            </div>
          </div>

          <!-- Media area -->
          <div class="viewer-media">
            <template v-if="currentFile">
              <img
                v-if="currentFile.media_type === 'image'"
                :key="currentFile.path"
                :src="serveUrl(currentFile.path)"
                :alt="currentFile.name"
                class="viewer-img"
              />
              <video
                v-else-if="currentFile.media_type === 'video'"
                :key="currentFile.path"
                :src="serveUrl(currentFile.path)"
                class="viewer-video"
                controls
                autoplay
              />
              <div v-else class="viewer-unsupported">
                無法預覽此檔案格式（{{ currentFile.name }}）
              </div>
            </template>
          </div>

          <!-- Navigation arrows -->
          <button
            v-if="viewerIndex > 0"
            class="viewer-arrow viewer-arrow--prev"
            type="button"
            @click="prevFile"
          >‹</button>
          <button
            v-if="viewerIndex < viewerFiles.length - 1"
            class="viewer-arrow viewer-arrow--next"
            type="button"
            @click="nextFile"
          >›</button>

          <!-- Thumbnail filmstrip -->
          <div class="viewer-strip">
            <button
              v-for="(file, idx) in viewerFiles"
              :key="file.path"
              class="viewer-strip__thumb"
              :class="{ 'viewer-strip__thumb--active': idx === viewerIndex }"
              type="button"
              @click="viewerIndex = idx"
            >
              <img
                v-if="file.media_type === 'image'"
                :src="serveUrl(file.path)"
                :alt="file.name"
                loading="lazy"
              />
              <span v-else class="viewer-strip__video-icon">▶</span>
            </button>
          </div>

        </div>
      </div>
    </Teleport>
  </div>
</template>

<style lang="scss" scoped>
@use '../../styles/tokens' as *;

// ── Toolbar ────────────────────────────────────────────────────────────────
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

// ── Item grid ──────────────────────────────────────────────────────────────
.gallery-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 1rem;
}

.gallery-card {
  display: flex;
  flex-direction: column;
  border: 1px solid $slate-200;
  border-radius: 1rem;
  background: #fff;
  overflow: hidden;
  cursor: pointer;
  transition: box-shadow 0.15s, border-color 0.15s;
  text-align: left;
  padding: 0;

  &:hover {
    box-shadow: 0 6px 20px rgba(15, 23, 42, 0.1);
    border-color: $blue-600;
  }
}

.gallery-card__thumb {
  width: 100%;
  aspect-ratio: 1;
  background: $surface-soft;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
}

.gallery-card__no-thumb {
  font-size: 2.5rem;
  color: $slate-400;
}

.gallery-card__label {
  padding: 0.55rem 0.7rem 0.65rem;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.gallery-card__name {
  font-size: 0.83rem;
  font-weight: 600;
  color: $slate-900;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-all;
}

.gallery-card__meta {
  font-size: 0.76rem;
  color: $slate-500;
}

// ── Viewer ─────────────────────────────────────────────────────────────────
.viewer-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.88);
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
}

.viewer-shell {
  position: relative;
  display: flex;
  flex-direction: column;
  width: 96vw;
  height: 96vh;
  max-width: 1400px;
  background: #0f172a;
  border-radius: 1.2rem;
  overflow: hidden;
}

.viewer-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.7rem 1.1rem;
  background: rgba(255, 255, 255, 0.06);
  flex-shrink: 0;
}

.viewer-topbar__title {
  color: #e2e8f0;
  font-size: 0.9rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.viewer-topbar__pos {
  color: #94a3b8;
  font-size: 0.82rem;
  font-weight: 400;
  white-space: nowrap;
}

.viewer-topbar__actions {
  display: flex;
  gap: 0.5rem;
  flex-shrink: 0;
}

.viewer-media {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  position: relative;
}

.viewer-img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  display: block;
}

.viewer-video {
  max-width: 100%;
  max-height: 100%;
  display: block;
  background: #000;
}

.viewer-unsupported {
  color: #94a3b8;
  font-size: 0.9rem;
}

.viewer-arrow {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  background: rgba(255, 255, 255, 0.12);
  border: none;
  color: #fff;
  font-size: 2.5rem;
  line-height: 1;
  padding: 0.5rem 0.9rem;
  border-radius: 0.7rem;
  cursor: pointer;
  z-index: 10;
  transition: background 0.15s;

  &:hover {
    background: rgba(255, 255, 255, 0.25);
  }

  &--prev { left: 0.75rem; }
  &--next { right: 0.75rem; }
}

.viewer-strip {
  display: flex;
  gap: 0.4rem;
  padding: 0.5rem 0.75rem;
  background: rgba(0, 0, 0, 0.4);
  overflow-x: auto;
  flex-shrink: 0;

  &::-webkit-scrollbar { height: 4px; }
  &::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.2); border-radius: 999px; }
}

.viewer-strip__thumb {
  flex-shrink: 0;
  width: 56px;
  height: 56px;
  border-radius: 0.45rem;
  border: 2px solid transparent;
  overflow: hidden;
  cursor: pointer;
  background: rgba(255, 255, 255, 0.08);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: border-color 0.15s;

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }

  &--active {
    border-color: #3b82f6;
  }
}

.viewer-strip__video-icon {
  color: #94a3b8;
  font-size: 1.4rem;
}

@include down($bp-sm) {
  .gallery-toolbar {
    gap: 0.6rem;
  }

  .gallery-search {
    max-width: 100%;
    flex: 1 1 100%;
  }

  .gallery-grid {
    grid-template-columns: repeat(auto-fill, minmax(128px, 1fr));
    gap: 0.7rem;
  }

  .viewer-shell {
    width: 100vw;
    height: 100vh;
    border-radius: 0;
  }

  .viewer-arrow {
    font-size: 1.8rem;
    padding: 0.4rem 0.6rem;
  }
}
</style>
