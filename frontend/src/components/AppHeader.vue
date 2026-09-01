<script setup>
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import { useHubStore } from '../stores/hub'
import { formatDateTime } from '../utils/format'

const route = useRoute()
const store = useHubStore()

const navItems = [
  { to: '/', label: '總覽' },
  { to: '/gallery', label: '媒體庫' },
  { to: '/history', label: '歷史' },
  { to: '/queue', label: '佇列' },
  { to: '/jobs', label: '工作' },
  { to: '/cookies', label: 'Cookies' },
]

const queueTotal = computed(() => store.queue.total || store.dashboard.queue.total || 0)
const pendingCount = computed(() => store.queue.pending.length || store.dashboard.queue.pending.length || 0)
const syncLabel = computed(() => (store.lastSyncAt ? formatDateTime(store.lastSyncAt) : '尚未同步'))
const compactSyncLabel = computed(() => {
  if (!store.lastSyncAt) return '同步 --:--'
  const date = new Date(store.lastSyncAt)
  if (Number.isNaN(date.getTime())) return '同步 --:--'
  return `同步 ${date.toLocaleTimeString('zh-TW', { hour12: false, hour: '2-digit', minute: '2-digit' })}`
})

async function refreshOverview() {
  await Promise.all([
    store.fetchDashboard({ silent: true }),
    store.fetchQueue({ silent: true }),
    store.fetchJobs({ silent: true }),
    store.fetchHistory({ silent: true }),
    store.fetchCookies({ silent: true }),
  ])
  store.notify('儀表板資料已更新。')
}

async function updateDownloaders() {
  try {
    await store.updateDownloaders()
  } catch {
    // store.updateDownloaders() already surfaced the error via a toast.
  }
}
</script>

<template>
  <header class="app-header">
    <div class="app-header__brand">
      <div class="brand-mark">NS</div>
      <div class="app-header__brand-copy">
        <div class="brand-title">NS Media Hub</div>
        <div class="brand-subtitle">下載 / 歷史 / Bot / Cookie 一體化控制台</div>
      </div>
    </div>

    <nav class="app-header__nav">
      <RouterLink
        v-for="item in navItems"
        :key="item.to"
        :to="item.to"
        class="nav-link"
        :class="{ 'nav-link--active': route.path === item.to }"
      >
        {{ item.label }}
      </RouterLink>
    </nav>

    <div class="app-header__meta">
      <div class="app-header__chips">
        <div class="header-chip" :class="store.apiHealthy ? 'header-chip--success' : 'header-chip--danger'">
          <span class="header-chip__icon" aria-hidden="true">{{ store.apiHealthy ? '●' : '!' }}</span>
          <span class="header-chip__label">{{ store.apiHealthy ? '已連線' : '異常' }}</span>
        </div>
        <div class="header-chip">
          <span class="header-chip__icon" aria-hidden="true">Q</span>
          <span class="header-chip__label">{{ queueTotal }}</span>
        </div>
        <div class="header-chip header-chip--pending">
          <span class="header-chip__icon" aria-hidden="true">P</span>
          <span class="header-chip__label">{{ pendingCount }}</span>
        </div>
      </div>
      <button
        class="btn btn--ghost btn--small app-header__refresh"
        type="button"
        aria-label="重新整理"
        @click="refreshOverview"
      >
        <span class="app-header__refresh-icon" aria-hidden="true">↻</span>
        <span
          class="app-header__refresh-text"
          aria-hidden="true"
        >重新整理</span>
      </button>
      <button
        class="btn btn--ghost btn--small app-header__refresh app-header__downloader-update"
        type="button"
        aria-label="更新下載器"
        :disabled="store.isLoading('downloader-update')"
        @click="updateDownloaders"
      >
        <span class="app-header__refresh-icon" aria-hidden="true">⇪</span>
        <span
          class="app-header__refresh-text"
          aria-hidden="true"
        >更新下載器</span>
      </button>
      <div class="sync-text">
        <span class="sync-text__full">最後同步：{{ syncLabel }}</span>
        <span class="sync-text__compact">{{ compactSyncLabel }}</span>
      </div>
    </div>
  </header>
</template>
