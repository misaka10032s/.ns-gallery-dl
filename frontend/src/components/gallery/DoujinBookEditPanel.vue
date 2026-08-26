<script setup>
import { computed, ref, watch } from 'vue'

import { addDoujinLink, deleteDoujinLink, fetchDoujinBookDetail, updateDoujinBook } from '../../api/gallery'
import ConfirmDialog from './ConfirmDialog.vue'

// Edit panel for one doujinshi book's own fields (title/artist/circle/size/
// color-pages/series/purchase state/cover page/page-count override) plus its
// plural links (N網/P網/購買網...). Field read/update and link add/remove all
// go through app/services/doujin_service.py's validation — this panel does
// only light client-side shaping (trim, number parsing) before sending.
const props = defineProps({
  folderPath: { type: String, required: true },
})

const emit = defineEmits(['close', 'updated'])

const loading = ref(true)
const saving = ref(false)
const error = ref('')
const detail = ref(null)

const form = ref({
  title: '',
  artist: '',
  circle: '',
  size_label: '',
  color_pages: '',
  series: '',
  purchase_state: 'not_purchased',
  cover_page: '',
  page_count_override: '',
})

const newLinkLabel = ref('')
const newLinkUrl = ref('')
const linkError = ref('')

const confirmDeleteId = ref(null)

const pageOptions = computed(() => detail.value?.pages ?? [])

function applyDetailToForm(d) {
  form.value = {
    title: d.title ?? '',
    artist: d.artist ?? '',
    circle: d.circle ?? '',
    size_label: d.size_label ?? '',
    color_pages: d.color_pages ?? '',
    series: d.series ?? '',
    purchase_state: d.purchase_state ?? 'not_purchased',
    cover_page: d.cover_page ?? '',
    page_count_override: d.page_count_override ?? '',
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    detail.value = await fetchDoujinBookDetail(props.folderPath)
    applyDetailToForm(detail.value)
  } catch (e) {
    error.value = e.message || '載入失敗'
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  error.value = ''
  try {
    const override = String(form.value.page_count_override).trim()
    const payload = {
      title: form.value.title.trim(),
      artist: form.value.artist.trim(),
      circle: form.value.circle.trim(),
      size_label: form.value.size_label.trim(),
      color_pages: form.value.color_pages.trim(),
      series: form.value.series.trim(),
      purchase_state: form.value.purchase_state,
      cover_page: form.value.cover_page,
      page_count_override: override === '' ? null : Number(override),
    }
    detail.value = await updateDoujinBook(props.folderPath, payload)
    applyDetailToForm(detail.value)
    emit('updated', detail.value)
  } catch (e) {
    error.value = e.message || '儲存失敗'
  } finally {
    saving.value = false
  }
}

async function submitLink() {
  linkError.value = ''
  if (!newLinkUrl.value.trim()) {
    linkError.value = '請輸入連結網址'
    return
  }
  try {
    await addDoujinLink(props.folderPath, newLinkLabel.value.trim(), newLinkUrl.value.trim())
    newLinkLabel.value = ''
    newLinkUrl.value = ''
    detail.value = await fetchDoujinBookDetail(props.folderPath)
  } catch (e) {
    linkError.value = e.message || '新增連結失敗'
  }
}

function requestDeleteLink(id) {
  confirmDeleteId.value = id
}

async function confirmDeleteLink() {
  const id = confirmDeleteId.value
  confirmDeleteId.value = null
  if (id == null) return
  try {
    await deleteDoujinLink(props.folderPath, id)
    detail.value = await fetchDoujinBookDetail(props.folderPath)
  } catch (e) {
    linkError.value = e.message || '刪除連結失敗'
  }
}

function close() {
  emit('close')
}

watch(() => props.folderPath, load, { immediate: true })
</script>

<template>
  <Teleport to="body">
    <div class="edit-backdrop" @click.self="close">
      <div class="edit-panel">
        <div class="edit-panel__header">
          <h3>編輯本子資料</h3>
          <button class="btn btn--ghost btn--small" type="button" @click="close">✕ 關閉</button>
        </div>

        <div v-if="loading" class="empty-state">載入中…</div>
        <template v-else>
          <div v-if="error" class="edit-panel__error">{{ error }}</div>

          <div class="edit-panel__body">
            <label class="field">
              <span>名稱</span>
              <input v-model="form.title" class="form-input" type="text" maxlength="500" />
            </label>

            <div class="field-row">
              <label class="field">
                <span>作者</span>
                <input v-model="form.artist" class="form-input" type="text" maxlength="500" />
              </label>
              <label class="field">
                <span>社團</span>
                <input v-model="form.circle" class="form-input" type="text" maxlength="500" />
              </label>
            </div>

            <div class="field-row">
              <label class="field">
                <span>尺寸</span>
                <input v-model="form.size_label" class="form-input" type="text" maxlength="500" />
              </label>
              <label class="field">
                <span>彩頁</span>
                <input v-model="form.color_pages" class="form-input" type="text" maxlength="500" placeholder="例：p1-4" />
              </label>
            </div>

            <label class="field">
              <span>分類（XX系列）</span>
              <input v-model="form.series" class="form-input" type="text" maxlength="500" />
            </label>

            <div class="field-row">
              <label class="field">
                <span>購買狀態</span>
                <select v-model="form.purchase_state" class="form-input">
                  <option value="not_purchased">未購</option>
                  <option value="purchased">已購</option>
                </select>
              </label>
              <label class="field">
                <span>頁數（自動偵測，可覆蓋）</span>
                <input
                  v-model="form.page_count_override"
                  class="form-input"
                  type="number"
                  min="0"
                  :placeholder="`自動：${detail?.pages?.length ?? 0}`"
                />
              </label>
            </div>

            <label class="field">
              <span>縮圖（預設第一頁）</span>
              <select v-model="form.cover_page" class="form-input">
                <option value="">自動（第一頁）</option>
                <option v-for="p in pageOptions" :key="p.name" :value="p.name">{{ p.name }}</option>
              </select>
            </label>

            <button class="btn btn--primary" type="button" :disabled="saving" @click="save">
              {{ saving ? '儲存中...' : '儲存' }}
            </button>

            <hr class="edit-panel__divider" />

            <div class="edit-panel__links">
              <h4>連結（N網 / P網 / 購買網...）</h4>
              <ul v-if="detail?.links?.length" class="link-list">
                <li v-for="link in detail.links" :key="link.id" class="link-list__item">
                  <span class="link-list__label">{{ link.label || '連結' }}</span>
                  <a :href="link.url" target="_blank" rel="noopener noreferrer" class="link-list__url">
                    {{ link.url }}
                  </a>
                  <button class="link-list__delete" type="button" @click="requestDeleteLink(link.id)">
                    🗑
                  </button>
                </li>
              </ul>
              <p v-else class="link-list__empty">尚未新增連結。</p>

              <div v-if="linkError" class="edit-panel__error">{{ linkError }}</div>

              <div class="link-form">
                <input v-model="newLinkLabel" class="form-input" type="text" placeholder="標籤（如 N網）" maxlength="100" />
                <input v-model="newLinkUrl" class="form-input" type="url" placeholder="https://..." maxlength="2000" />
                <button class="btn btn--ghost btn--small" type="button" @click="submitLink">+ 新增連結</button>
              </div>
            </div>
          </div>
        </template>
      </div>
    </div>

    <ConfirmDialog
      :open="confirmDeleteId !== null"
      title="刪除連結"
      message="確定要刪除這個連結嗎？此操作無法復原。"
      confirm-label="刪除"
      cancel-label="取消"
      @confirm="confirmDeleteLink"
      @cancel="confirmDeleteId = null"
    />
  </Teleport>
</template>

<style lang="scss" scoped>
@use '../../styles/tokens' as *;

.edit-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.5);
  z-index: 105;
  display: flex;
  justify-content: flex-end;
}

.edit-panel {
  width: min(28rem, 100vw);
  height: 100%;
  background: #fff;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  box-shadow: -12px 0 30px rgba(15, 23, 42, 0.15);
}

.edit-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.2rem;
  border-bottom: 1px solid $slate-200;
  flex-shrink: 0;

  h3 {
    margin: 0;
    font-size: 1rem;
    color: $slate-900;
  }
}

.edit-panel__body {
  padding: 1rem 1.2rem 1.6rem;
  display: flex;
  flex-direction: column;
  gap: 0.9rem;
}

.edit-panel__error {
  margin: 0.6rem 1.2rem 0;
  padding: 0.5rem 0.7rem;
  border-radius: 0.6rem;
  background: rgba(220, 38, 38, 0.08);
  color: #b91c1c;
  font-size: 0.82rem;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  flex: 1;
  min-width: 0;

  span {
    font-size: 0.78rem;
    color: $slate-500;
  }
}

.field-row {
  display: flex;
  gap: 0.7rem;
}

.edit-panel__divider {
  border: none;
  border-top: 1px solid $slate-200;
  margin: 0.2rem 0;
}

.edit-panel__links h4 {
  margin: 0 0 0.6rem;
  font-size: 0.88rem;
  color: $slate-900;
}

.link-list {
  list-style: none;
  margin: 0 0 0.8rem;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.link-list__item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.4rem 0.55rem;
  border: 1px solid $slate-200;
  border-radius: 0.6rem;
  min-width: 0;
}

.link-list__label {
  font-size: 0.76rem;
  font-weight: 700;
  color: $slate-700;
  flex-shrink: 0;
}

.link-list__url {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.78rem;
  color: $blue-600;
}

.link-list__delete {
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 0.9rem;
  flex-shrink: 0;
  padding: 0.15rem 0.3rem;
  border-radius: 0.4rem;

  &:hover {
    background: rgba(220, 38, 38, 0.1);
  }
}

.link-list__empty {
  font-size: 0.82rem;
  color: $slate-500;
  margin: 0 0 0.8rem;
}

.link-form {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

@include down($bp-sm) {
  .edit-panel {
    width: 100vw;
  }

  .field-row {
    flex-direction: column;
    gap: 0.5rem;
  }
}
</style>
