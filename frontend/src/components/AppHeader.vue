<script setup>
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import { useHubStore } from '../stores/hub'
import { formatDateTime } from '../utils/format'

const route = useRoute()
const store = useHubStore()

const navItems = [
  { to: '/', label: '總覽' },
  { to: '/history', label: '歷史' },
  { to: '/queue', label: '佇列' },
  { to: '/jobs', label: '工作' },
  { to: '/cookies', label: 'Cookies' },
]

const queueTotal = computed(() => store.queue.total || store.dashboard.queue.total || 0)
const pendingCount = computed(() => store.queue.pending.length || store.dashboard.queue.pending.length || 0)
const syncLabel = computed(() => (store.lastSyncAt ? formatDateTime(store.lastSyncAt) : '尚未同步'))

async function refreshOverview() {
  await Promise.all([
    store.fetchDashboard({ silent: true }),
    store.fetchQueue({ silent: true }),
    store.fetchJobs({ silent: true }),
  ])
  store.notify('儀表板資料已更新。')
}
</script>

<template>
  <header class="app-header">
    <div class="app-header__brand">
      <div class="brand-mark">NS</div>
      <div>
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
          {{ store.apiHealthy ? 'API 已連線' : 'API 連線異常' }}
        </div>
        <div class="header-chip">Queue {{ queueTotal }}</div>
        <div class="header-chip">Pending {{ pendingCount }}</div>
      </div>
      <button class="btn btn--ghost btn--small app-header__refresh" type="button" @click="refreshOverview">重新整理</button>
      <div class="sync-text">最後同步：{{ syncLabel }}</div>
    </div>
  </header>
</template>
