<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

import StatCard from '../components/StatCard.vue'
import { useHubStore } from '../stores/hub'
import { hostnameFromUrl } from '../utils/format'

const store = useHubStore()
const autoRefresh = ref(localStorage.getItem('nsmh-queue-autorefresh') !== '0')
let timerId = 0

const pendingGroups = computed(() => {
  return store.queue.pending.reduce((result, url) => {
    const domain = hostnameFromUrl(url)
    result[domain] = (result[domain] ?? 0) + 1
    return result
  }, {})
})

function clearTimer() {
  if (timerId) {
    window.clearInterval(timerId)
    timerId = 0
  }
}

function syncAutoRefresh() {
  clearTimer()
  if (!autoRefresh.value) return
  timerId = window.setInterval(() => {
    store.fetchQueue({ silent: true }).catch(() => {})
  }, 5000)
}

onMounted(() => {
  store.fetchQueue({ silent: true }).catch(() => {})
  syncAutoRefresh()
})

onUnmounted(() => {
  clearTimer()
})

watch(autoRefresh, (value) => {
  localStorage.setItem('nsmh-queue-autorefresh', value ? '1' : '0')
  syncAutoRefresh()
})
</script>

<template>
  <section class="page">
    <div class="page-heading">
      <div>
        <h1>下載佇列</h1>
        <p>即時查看目前下載中與待處理網址，避免 queue 狀態分散在不同入口。</p>
      </div>
      <div class="page-heading__actions">
        <label class="toggle">
          <input v-model="autoRefresh" type="checkbox" />
          <span>每 5 秒自動更新</span>
        </label>
        <button class="btn btn--ghost" type="button" :disabled="store.isLoading('queue')" @click="store.fetchQueue()">
          {{ store.isLoading('queue') ? '更新中...' : '重新整理' }}
        </button>
      </div>
    </div>

    <div class="stats-grid">
      <StatCard title="總數" :value="store.queue.total" hint="目前 queue 中的總工作數" tone="primary" />
      <StatCard title="待處理" :value="store.queue.pending.length" hint="尚未進入執行階段" />
      <StatCard title="執行中" :value="store.queue.current ? 1 : 0" hint="同時間只會有一項 active" tone="success" />
    </div>

    <div class="content-grid content-grid--two">
      <section class="panel-card">
        <div class="panel-card__header">
          <div>
            <h2>目前下載中</h2>
            <p>工作執行中的主體 URL。</p>
          </div>
        </div>
        <div v-if="!store.queue.current" class="empty-state">目前沒有進行中的下載。</div>
        <div v-else class="current-job">
          <a :href="store.queue.current" target="_blank" rel="noreferrer">{{ store.queue.current }}</a>
          <div class="muted-text">Domain: {{ hostnameFromUrl(store.queue.current) }}</div>
        </div>
      </section>

      <section class="panel-card">
        <div class="panel-card__header">
          <div>
            <h2>待處理分布</h2>
            <p>快速看出 queue 主要堆積在哪些站點。</p>
          </div>
        </div>
        <div v-if="Object.keys(pendingGroups).length === 0" class="empty-state">沒有待處理項目。</div>
        <ul v-else class="domain-list">
          <li v-for="(count, domain) in pendingGroups" :key="domain" class="domain-list__item">
            <span>{{ domain }}</span>
            <strong>{{ count }}</strong>
          </li>
        </ul>
      </section>
    </div>

    <section class="panel-card">
      <div class="panel-card__header">
        <div>
          <h2>待處理清單</h2>
          <p>依照實際 queue 順序顯示。</p>
        </div>
      </div>

      <div v-if="store.queue.pending.length === 0" class="empty-state">queue 是空的。</div>
      <div v-else class="queue-list">
        <div v-for="(url, index) in store.queue.pending" :key="`${url}-${index}`" class="queue-row">
          <div class="queue-row__index">#{{ index + 1 }}</div>
          <div class="queue-row__content">
            <a :href="url" target="_blank" rel="noreferrer">{{ url }}</a>
            <span>{{ hostnameFromUrl(url) }}</span>
          </div>
        </div>
      </div>
    </section>
  </section>
</template>
