<script setup>
import { ref, watch } from 'vue'

import { createOrResolveDoujinSeries, searchDoujinSeries } from '../../api/gallery'

// 分類 (series) combobox — a CONTROLLED VOCABULARY, not a free-text box
// (user: 「分類的要有dropdown 不然錯別字大小寫空格就都分散了」). Typing
// filters existing series as-you-type; when nothing matches, a "+ 建立「X」"
// option creates one. If the name is a near-duplicate of an existing series
// (typo/punctuation-level similarity — case/spacing differences are already
// unified server-side and never reach this state), the collision is shown
// inline: pick the existing one, or confirm creating a separate entry
// anyway. Nothing is auto-merged and nothing is silently duplicated.
const props = defineProps({
  seriesId: { type: [Number, null], default: null },
  seriesName: { type: String, default: '' },
})

const emit = defineEmits(['select'])

const query = ref(props.seriesName || '')
const open = ref(false)
const suggestions = ref([])
const loading = ref(false)
const creating = ref(false)
const error = ref('')
const nearDuplicates = ref([]) // candidates from a 409, or [] normally
let debounceTimer = null

watch(
  () => props.seriesName,
  (name) => {
    query.value = name || ''
  },
)

function scheduleSearch() {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(runSearch, 200)
}

async function runSearch() {
  loading.value = true
  try {
    suggestions.value = await searchDoujinSeries(query.value)
  } finally {
    loading.value = false
  }
}

function onFocus() {
  open.value = true
  nearDuplicates.value = []
  error.value = ''
  runSearch()
}

function onInput() {
  nearDuplicates.value = []
  error.value = ''
  scheduleSearch()
}

function selectExisting(series) {
  query.value = series.name
  open.value = false
  nearDuplicates.value = []
  emit('select', { id: series.id, name: series.name })
}

function clearSelection() {
  query.value = ''
  suggestions.value = []
  nearDuplicates.value = []
  emit('select', { id: null, name: '' })
}

async function createNew(confirm) {
  const name = query.value.trim()
  if (!name) return
  creating.value = true
  error.value = ''
  try {
    const result = await createOrResolveDoujinSeries(name, confirm)
    selectExisting(result.series)
  } catch (e) {
    if (e.status === 409 && e.payload?.candidates) {
      nearDuplicates.value = e.payload.candidates
    } else {
      error.value = e.message || '建立分類失敗'
    }
  } finally {
    creating.value = false
  }
}

function exactMatchExists() {
  const key = query.value.trim().toLowerCase()
  return suggestions.value.some((s) => s.name.toLowerCase() === key)
}
</script>

<template>
  <div class="series-combobox">
    <div class="series-combobox__row">
      <input
        v-model="query"
        class="form-input"
        type="text"
        placeholder="輸入或搜尋分類..."
        maxlength="500"
        @focus="onFocus"
        @input="onInput"
      />
      <button
        v-if="query"
        class="series-combobox__clear"
        type="button"
        title="清除分類"
        @click="clearSelection"
      >✕</button>
    </div>

    <div v-if="open" class="series-combobox__panel">
      <div v-if="loading" class="series-combobox__hint">搜尋中…</div>
      <ul v-else-if="suggestions.length" class="series-combobox__list">
        <li v-for="s in suggestions" :key="s.id">
          <button type="button" @click="selectExisting(s)">{{ s.name }}</button>
        </li>
      </ul>
      <div v-else class="series-combobox__hint">沒有符合的分類。</div>

      <div v-if="nearDuplicates.length" class="series-combobox__near-dup">
        <p>「{{ query.trim() }}」跟現有分類很像，你是不是要選這個？</p>
        <ul class="series-combobox__list">
          <li v-for="c in nearDuplicates" :key="c.id">
            <button type="button" @click="selectExisting(c)">使用「{{ c.name }}」</button>
          </li>
        </ul>
        <button
          class="series-combobox__force-create"
          type="button"
          :disabled="creating"
          @click="createNew(true)"
        >仍要建立「{{ query.trim() }}」</button>
      </div>
      <button
        v-else-if="query.trim() && !exactMatchExists()"
        class="series-combobox__create"
        type="button"
        :disabled="creating"
        @click="createNew(false)"
      >{{ creating ? '建立中...' : `+ 建立「${query.trim()}」` }}</button>

      <div v-if="error" class="series-combobox__error">{{ error }}</div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
@use '../../styles/tokens' as *;

.series-combobox {
  position: relative;
}

.series-combobox__row {
  display: flex;
  align-items: center;
  gap: 0.4rem;
}

.series-combobox__clear {
  border: none;
  background: transparent;
  color: $slate-500;
  cursor: pointer;
  font-size: 0.85rem;
  padding: 0.2rem 0.4rem;
  flex-shrink: 0;

  &:hover {
    color: #b91c1c;
  }
}

.series-combobox__panel {
  position: relative;
  margin-top: 0.35rem;
  border: 1px solid $slate-200;
  border-radius: 0.6rem;
  background: #fff;
  padding: 0.5rem;
  box-shadow: 0 6px 18px rgba(15, 23, 42, 0.08);
}

.series-combobox__list {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 10rem;
  overflow-y: auto;

  button {
    display: block;
    width: 100%;
    text-align: left;
    border: none;
    background: transparent;
    padding: 0.4rem 0.5rem;
    border-radius: 0.4rem;
    cursor: pointer;
    font-size: 0.86rem;
    color: $slate-900;

    &:hover {
      background: $surface-soft;
    }
  }
}

.series-combobox__hint {
  font-size: 0.8rem;
  color: $slate-500;
  padding: 0.3rem 0.5rem;
}

.series-combobox__create {
  display: block;
  width: 100%;
  text-align: left;
  border: none;
  background: transparent;
  color: $blue-600;
  font-weight: 600;
  font-size: 0.86rem;
  padding: 0.4rem 0.5rem;
  cursor: pointer;
  border-radius: 0.4rem;

  &:hover {
    background: $surface-soft;
  }
}

.series-combobox__near-dup {
  margin-top: 0.4rem;
  padding-top: 0.4rem;
  border-top: 1px dashed $slate-200;

  p {
    margin: 0 0 0.3rem;
    font-size: 0.8rem;
    color: $slate-700;
  }
}

.series-combobox__force-create {
  width: 100%;
  margin-top: 0.3rem;
  border: 1px dashed $slate-300;
  background: transparent;
  color: $slate-600;
  font-size: 0.8rem;
  padding: 0.35rem 0.5rem;
  border-radius: 0.4rem;
  cursor: pointer;

  &:hover {
    border-color: $blue-600;
    color: $blue-600;
  }
}

.series-combobox__error {
  margin-top: 0.3rem;
  font-size: 0.78rem;
  color: #b91c1c;
}
</style>
