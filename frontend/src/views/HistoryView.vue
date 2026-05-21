<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import CompactPanelCard from '../components/CompactPanelCard.vue'
import StatusChip from '../components/StatusChip.vue'
import { useHubStore } from '../stores/hub'
import { copyText, formatDate, hostnameFromUrl } from '../utils/format'

const store = useHubStore()

const startDate = ref('')
const endDate = ref('')
const search = ref('')
const statusFilter = ref('all')
const providerFilter = ref('all')
const selectedDomains = ref([])
const selectedUrls = ref([])
const jsonMode = ref(false)
const expandedDates = ref([])
const historyViewport = ref(null)
const historyScrollTop = ref(0)
const historyViewportHeight = ref(640)
const historyGroupBaseHeight = 88
const historyItemEstimatedHeight = 128

const allEntries = computed(() => store.historyEntries)
const availableDomains = computed(() =>
  Array.from(new Set(allEntries.value.map((item) => item.domain || hostnameFromUrl(item.url)))).sort(),
)

const filteredEntries = computed(() => {
  const keyword = search.value.trim().toLowerCase()
  const start = startDate.value ? new Date(`${startDate.value}T00:00:00`) : null
  const end = endDate.value ? new Date(`${endDate.value}T23:59:59`) : null

  return allEntries.value.filter((item) => {
    if (statusFilter.value !== 'all' && item.result !== statusFilter.value) return false
    if (providerFilter.value !== 'all' && item.provider !== providerFilter.value) return false

    const itemDate = new Date(`${item.date}T00:00:00`)
    if (start && itemDate < start) return false
    if (end && itemDate > end) return false

    const itemDomain = item.domain || hostnameFromUrl(item.url)
    if (selectedDomains.value.length && !selectedDomains.value.includes(itemDomain)) return false

    if (!keyword) return true
    return [item.url, itemDomain, item.provider, item.source, item.download_path]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(keyword))
  })
})

const groupedEntries = computed(() =>
  filteredEntries.value.reduce((result, item) => {
    result[item.date] = result[item.date] || []
    result[item.date].push(item)
    return result
  }, {}),
)

const groupedDates = computed(() => Object.keys(groupedEntries.value).sort((left, right) => right.localeCompare(left)))
const selectedOutput = computed(() =>
  jsonMode.value ? JSON.stringify(selectedUrls.value, null, 2) : selectedUrls.value.join('\n'),
)
const selectedUrlSet = computed(() => new Set(selectedUrls.value))
const selectedCountByDate = computed(() =>
  Object.fromEntries(
    groupedDates.value.map((date) => [
      date,
      (groupedEntries.value[date] ?? []).reduce((count, item) => count + (selectedUrlSet.value.has(item.url) ? 1 : 0), 0),
    ]),
  ),
)
const selectedSummary = computed(() => (selectedUrls.value.length ? `已選 ${selectedUrls.value.length}` : '未選'))
const virtualGroups = computed(() =>
  groupedDates.value.map((date) => {
    const items = groupedEntries.value[date] ?? []
    const expanded = expandedDates.value.includes(date)
    return {
      date,
      items,
      expanded,
      selectedCount: selectedCountByDate.value[date] ?? 0,
      height: expanded ? historyGroupBaseHeight + items.length * historyItemEstimatedHeight : historyGroupBaseHeight,
    }
  }),
)
const totalVirtualHeight = computed(() => virtualGroups.value.reduce((sum, group) => sum + group.height, 0))
const visibleWindow = computed(() => {
  const overscan = 4
  const viewportTop = historyScrollTop.value
  const viewportBottom = viewportTop + historyViewportHeight.value
  let offset = 0
  let start = 0
  let end = virtualGroups.value.length

  for (let index = 0; index < virtualGroups.value.length; index += 1) {
    const nextOffset = offset + virtualGroups.value[index].height
    if (nextOffset >= viewportTop) {
      start = Math.max(0, index - overscan)
      break
    }
    offset = nextOffset
  }

  offset = 0
  for (let index = 0; index < virtualGroups.value.length; index += 1) {
    offset += virtualGroups.value[index].height
    if (offset >= viewportBottom) {
      end = Math.min(virtualGroups.value.length, index + overscan + 1)
      break
    }
  }

  return { start, end }
})
const visibleGroups = computed(() => virtualGroups.value.slice(visibleWindow.value.start, visibleWindow.value.end))
const beforeSpacerHeight = computed(() =>
  virtualGroups.value.slice(0, visibleWindow.value.start).reduce((sum, group) => sum + group.height, 0),
)
const afterSpacerHeight = computed(() =>
  totalVirtualHeight.value -
  beforeSpacerHeight.value -
  visibleGroups.value.reduce((sum, group) => sum + group.height, 0),
)

function setDateRange(days) {
  const end = new Date()
  const start = new Date()
  start.setDate(end.getDate() - (days - 1))
  startDate.value = start.toISOString().slice(0, 10)
  endDate.value = end.toISOString().slice(0, 10)
}

function clearFilters() {
  startDate.value = ''
  endDate.value = ''
  search.value = ''
  statusFilter.value = 'all'
  providerFilter.value = 'all'
  selectedDomains.value = []
}

function toggleDomain(domain) {
  if (selectedDomains.value.includes(domain)) {
    selectedDomains.value = selectedDomains.value.filter((item) => item !== domain)
    return
  }
  selectedDomains.value = [...selectedDomains.value, domain]
}

function isSelected(url) {
  return selectedUrls.value.includes(url)
}

function toggleSelection(url) {
  if (isSelected(url)) {
    selectedUrls.value = selectedUrls.value.filter((item) => item !== url)
    return
  }
  selectedUrls.value = [...selectedUrls.value, url]
}

function selectAllVisible() {
  selectedUrls.value = Array.from(new Set(filteredEntries.value.map((item) => item.url)))
}

function clearAllVisible() {
  const visible = new Set(filteredEntries.value.map((item) => item.url))
  selectedUrls.value = selectedUrls.value.filter((url) => !visible.has(url))
}

function clearSelection() {
  selectedUrls.value = []
}

function selectDateGroup(date) {
  const urls = (groupedEntries.value[date] ?? []).map((item) => item.url)
  selectedUrls.value = Array.from(new Set([...selectedUrls.value, ...urls]))
}

function clearDateGroup(date) {
  const urls = new Set((groupedEntries.value[date] ?? []).map((item) => item.url))
  selectedUrls.value = selectedUrls.value.filter((url) => !urls.has(url))
}

function isExpanded(date) {
  return expandedDates.value.includes(date)
}

function toggleGroup(date) {
  expandedDates.value = isExpanded(date)
    ? expandedDates.value.filter((item) => item !== date)
    : [...expandedDates.value, date]
  nextTick(updateViewportMetrics)
}

function onHistoryScroll(event) {
  historyScrollTop.value = event.target.scrollTop
}

function updateViewportMetrics() {
  if (!historyViewport.value) return
  historyViewportHeight.value = historyViewport.value.clientHeight || 640
}

async function copySelection() {
  await copyText(selectedOutput.value)
  store.notify('已複製選取內容。')
}

async function requeueSelected() {
  const count = await store.requeueHistory(selectedUrls.value)
  if (count > 0) {
    clearSelection()
  }
}

async function toggleStatus(item) {
  const nextStatus = item.result === 'success' ? 'failed' : 'success'
  await store.updateHistoryStatus(item.date, item.url, nextStatus)
}

async function confirmDelete(item) {
  const confirmed = window.confirm(`確定要刪除這筆紀錄？\n${item.url}`)
  if (!confirmed) return
  await store.deleteHistoryEntry(item.date, item.url)
}

watch(filteredEntries, (entries) => {
  const visible = new Set(entries.map((item) => item.url))
  selectedUrls.value = selectedUrls.value.filter((url) => visible.has(url))
  expandedDates.value = expandedDates.value.filter((date) => groupedEntries.value[date]?.length)
  nextTick(() => {
    if (historyViewport.value) {
      historyViewport.value.scrollTop = 0
      historyScrollTop.value = 0
    }
    updateViewportMetrics()
  })
})

onMounted(() => {
  store.fetchHistory({ silent: true }).catch(() => {})
  updateViewportMetrics()
  window.addEventListener('resize', updateViewportMetrics)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', updateViewportMetrics)
})
</script>

<template>
  <section class="page">
    <div class="page-heading">
      <div>
        <h1>歷史紀錄</h1>
        <p>整合原本的批次篩選、重新送件與狀態修正，讓處理失敗項目更順手。</p>
      </div>
    </div>

    <section class="panel-card history-filters-panel">
      <div class="filters-grid-text filters-grid--wide history-filter-grid">
        <input v-model="search" class="input history-filter-grid__search" type="search" placeholder="搜尋 URL、provider、domain、下載路徑..." />
      </div>
      <div class="filters-grid filters-grid--wide history-filter-grid">
        <select v-model="statusFilter" class="select">
          <option value="all">所有狀態</option>
          <option value="success">成功</option>
          <option value="failed">失敗</option>
          <option value="skipped">跳過</option>
        </select>
        <select v-model="providerFilter" class="select">
          <option value="all">所有 provider</option>
          <option value="gallery-dl">gallery-dl</option>
          <option value="ytdlp">yt-dlp</option>
          <option value="direct-file">direct-file</option>
        </select>
        <input v-model="startDate" class="input" type="date" />
        <input v-model="endDate" class="input" type="date" />
      </div>

      <div class="button-row history-filter-toolbar">
        <div class="button-row button-row--compact history-range-buttons">
          <button class="btn btn--ghost btn--small" type="button" @click="setDateRange(1)">1 天</button>
          <button class="btn btn--ghost btn--small" type="button" @click="setDateRange(7)">7 天</button>
          <button class="btn btn--ghost btn--small" type="button" @click="setDateRange(30)">30 天</button>
        </div>
        <button class="btn btn--ghost btn--small" type="button" @click="clearFilters">清除篩選</button>
      </div>

      <div class="chip-list">
        <button
          v-for="domain in availableDomains"
          :key="domain"
          class="filter-chip"
          :class="{ 'filter-chip--active': selectedDomains.includes(domain) }"
          type="button"
          @click="toggleDomain(domain)"
        >
          {{ domain }}
        </button>
      </div>
    </section>

    <div class="split-layout">
      <section class="panel-card">
        <div class="panel-card__header history-results-header">
          <div class="history-results-heading">
            <h2>篩選結果</h2>
            <p>共 {{ filteredEntries.length }} / {{ allEntries.length }} 筆。</p>
          </div>
          <div class="button-row history-results-actions">
            <button class="btn btn--ghost btn--small" type="button" @click="selectAllVisible">全選</button>
            <button class="btn btn--ghost btn--small" type="button" @click="clearAllVisible">清空</button>
          </div>
        </div>

        <div v-if="groupedDates.length === 0" class="empty-state">沒有符合條件的歷史資料。</div>
        <div v-else ref="historyViewport" class="history-virtual-list" @scroll="onHistoryScroll">
          <div :style="{ height: `${beforeSpacerHeight}px` }" />
          <details
            v-for="group in visibleGroups"
            :key="group.date"
            class="history-group"
            :class="{ 'history-group--selected': group.selectedCount > 0 }"
            :open="group.expanded"
          >
            <summary @click.prevent="toggleGroup(group.date)">
              <div class="history-group__summary">
                <strong>{{ formatDate(group.date) }}</strong>
                <span class="muted-text">共 {{ group.items.length }} 筆</span>
                <span v-if="group.selectedCount" class="history-group__selected-count">已選 {{ group.selectedCount }}</span>
                <span class="history-day-actions">
                  <button class="btn btn--ghost btn--small" type="button" @click.stop="selectDateGroup(group.date)">全選</button>
                  <button
                    class="btn btn--ghost btn--small"
                    type="button"
                    :disabled="!group.selectedCount"
                    @click.stop="clearDateGroup(group.date)"
                  >
                    清空
                  </button>
                </span>
              </div>
            </summary>

            <div v-if="group.expanded" class="history-group__body">
              <article
                v-for="item in group.items"
                :key="`${group.date}-${item.url}`"
                class="history-item"
                :class="{ 'history-item--selected': isSelected(item.url) }"
              >
                <label class="history-item__checkbox">
                  <input :checked="isSelected(item.url)" type="checkbox" @change="toggleSelection(item.url)" />
                </label>

                <div class="history-item__content">
                  <div class="history-item__title">
                    <a :href="item.url" target="_blank" rel="noreferrer">{{ item.url }}</a>
                  </div>
                  <div class="history-item__meta">
                    <StatusChip :status="item.result" />
                    <span>{{ item.provider }}</span>
                    <span>{{ item.source }}</span>
                    <span>{{ item.domain || hostnameFromUrl(item.url) }}</span>
                    <span>{{ item.download_path || '尚未記錄下載路徑' }}</span>
                  </div>
                </div>

                <div class="history-item__actions">
                  <button class="btn btn--ghost btn--small" type="button" @click="store.requeueHistory([item.url])">重送</button>
                  <button class="btn btn--ghost btn--small" type="button" @click="toggleStatus(item)">
                    改為 {{ item.result === 'success' ? 'failed' : 'success' }}
                  </button>
                  <button class="btn btn--danger btn--small" type="button" @click="confirmDelete(item)">刪除</button>
                </div>
              </article>
            </div>
          </details>
          <div :style="{ height: `${Math.max(0, afterSpacerHeight)}px` }" />
        </div>
      </section>

      <CompactPanelCard
        title="已選擇"
        description="可直接複製或重新送回 queue。"
        icon-label="S"
        :badge-value="selectedUrls.length"
        :summary-text="selectedSummary"
        panel-class="history-selection-panel"
        desktop-panel-class="panel-card--sticky"
        :compact-max-width="1200"
      >
        <div class="history-selection-heading">
          <strong>已選擇 {{ selectedUrls.length }} 筆</strong>
        </div>

        <label class="toggle">
          <input v-model="jsonMode" type="checkbox" />
          <span>JSON 輸出</span>
        </label>

        <div v-if="!selectedUrls.length" class="empty-state empty-state--compact">尚未選取任何 URL。</div>
        <textarea
          v-else
          class="textarea selection-preview"
          :rows="jsonMode ? 12 : 8"
          readonly
          :value="selectedOutput"
        ></textarea>

        <div class="button-row history-selection-actions">
          <button class="btn btn--primary" type="button" :disabled="!selectedUrls.length" @click="requeueSelected">重送所選</button>
          <button class="btn btn--ghost" type="button" :disabled="!selectedUrls.length" @click="copySelection">複製</button>
          <button class="btn btn--ghost" type="button" :disabled="!selectedUrls.length" @click="clearSelection">清空選取</button>
        </div>
      </CompactPanelCard>
    </div>
  </section>
</template>
