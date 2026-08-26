<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { fetchDoujinBookDetail, updateDoujinBook } from '../../api/gallery'

// Page-by-page doujinshi reader. Pages come back from the backend already in
// natural/numeric order (app.services.doujin_service.natural_sort_key), so
// "10.jpg" never sorts before "2.jpg" here. Reading position is persisted
// server-side (doujin_books.last_page_index) so it survives navigating away
// and coming back later, not just a client-local memory.
const props = defineProps({
  folderPath: { type: String, required: true },
})

const emit = defineEmits(['close'])

const loading = ref(true)
const detail = ref(null)
const index = ref(0)
let saveTimer = null

const pages = computed(() => detail.value?.pages ?? [])
const currentPage = computed(() => pages.value[index.value] ?? null)

function serveUrl(path) {
  return `/api/gallery/serve?p=${encodeURIComponent(path)}`
}

async function load() {
  loading.value = true
  try {
    detail.value = await fetchDoujinBookDetail(props.folderPath)
    index.value = detail.value?.last_page_index ?? 0
  } finally {
    loading.value = false
  }
}

function schedulePositionSave() {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    updateDoujinBook(props.folderPath, { last_page_index: index.value }).catch(() => {})
  }, 500)
}

function goPrev() {
  if (index.value > 0) index.value--
}

function goNext() {
  if (index.value < pages.value.length - 1) index.value++
}

function close() {
  if (saveTimer) clearTimeout(saveTimer)
  updateDoujinBook(props.folderPath, { last_page_index: index.value }).catch(() => {})
  emit('close')
}

// Tap zones: left third = previous page, right two-thirds = next page — the
// forward tap target is intentionally bigger since "keep reading forward" is
// the common one-handed gesture (thumb reaching across a phone screen).
function onImageTap(e) {
  const rect = e.currentTarget.getBoundingClientRect()
  const ratio = (e.clientX - rect.left) / rect.width
  if (ratio < 0.35) goPrev()
  else goNext()
}

function onKeydown(e) {
  if (e.key === 'ArrowRight' || e.key === 'ArrowDown' || e.key === ' ') goNext()
  else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') goPrev()
  else if (e.key === 'Escape') close()
  else return
  e.preventDefault()
}

watch(index, () => {
  if (!loading.value) schedulePositionSave()
})

watch(() => props.folderPath, load, { immediate: true })

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
  if (saveTimer) clearTimeout(saveTimer)
})
</script>

<template>
  <Teleport to="body">
    <div class="reader-backdrop">
      <div class="reader-shell">
        <div class="reader-topbar">
          <span class="reader-topbar__title">{{ detail?.title ?? '' }}</span>
          <button class="btn btn--ghost btn--small" type="button" @click="close">✕ 關閉</button>
        </div>

        <div v-if="loading" class="reader-loading">載入中…</div>
        <template v-else>
          <div class="reader-media" @click="onImageTap">
            <img
              v-if="currentPage"
              :key="currentPage.path"
              :src="serveUrl(currentPage.path)"
              :alt="currentPage.name"
              class="reader-img"
            />
            <div v-else class="reader-empty">此本子沒有可顯示的頁面。</div>
          </div>

          <div class="reader-bottombar">
            <button
              class="reader-nav-btn"
              type="button"
              :disabled="index === 0"
              @click.stop="goPrev"
            >‹ 上一頁</button>
            <span class="reader-position">{{ index + 1 }} / {{ pages.length }}</span>
            <button
              class="reader-nav-btn"
              type="button"
              :disabled="index >= pages.length - 1"
              @click.stop="goNext"
            >下一頁 ›</button>
          </div>
        </template>
      </div>
    </div>
  </Teleport>
</template>

<style lang="scss" scoped>
@use '../../styles/tokens' as *;

.reader-backdrop {
  position: fixed;
  inset: 0;
  background: #0f172a;
  z-index: 110;
  display: flex;
  align-items: stretch;
  justify-content: center;
}

.reader-shell {
  position: relative;
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
}

.reader-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.6rem 1rem;
  background: rgba(255, 255, 255, 0.06);
  flex-shrink: 0;
}

.reader-topbar__title {
  color: #e2e8f0;
  font-size: 0.88rem;
  font-weight: 600;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.reader-loading,
.reader-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #94a3b8;
  font-size: 0.9rem;
}

.reader-media {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  cursor: pointer;
  min-height: 0;
}

.reader-img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  display: block;
  user-select: none;
}

.reader-bottombar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.6rem;
  padding: 0.6rem 0.8rem;
  padding-bottom: max(0.6rem, env(safe-area-inset-bottom));
  background: rgba(255, 255, 255, 0.06);
  flex-shrink: 0;
}

.reader-nav-btn {
  border: 1px solid rgba(255, 255, 255, 0.25);
  background: rgba(255, 255, 255, 0.08);
  color: #e2e8f0;
  border-radius: 0.7rem;
  padding: 0.55rem 1rem;
  font-size: 0.85rem;
  cursor: pointer;
  flex: 1;
  max-width: 10rem;

  &:disabled {
    opacity: 0.35;
    cursor: default;
  }

  &:not(:disabled):hover {
    background: rgba(255, 255, 255, 0.18);
  }
}

.reader-position {
  color: #94a3b8;
  font-size: 0.82rem;
  white-space: nowrap;
  flex-shrink: 0;
}

@include down($bp-sm) {
  .reader-topbar__title {
    font-size: 0.8rem;
  }

  .reader-nav-btn {
    padding: 0.6rem 0.7rem;
    font-size: 0.8rem;
  }
}
</style>
