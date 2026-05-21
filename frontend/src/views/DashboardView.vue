<script setup>
import { computed, onMounted } from 'vue'

import StatCard from '../components/StatCard.vue'
import StatusChip from '../components/StatusChip.vue'
import { useHubStore } from '../stores/hub'
import { formatDate, formatDateTime } from '../utils/format'

const store = useHubStore()

const dashboard = computed(() => store.dashboard)
const jobCounts = computed(() => dashboard.value.jobs.counts || {})
const recentJobs = computed(() => dashboard.value.jobs.recent || [])
const topDomains = computed(() => dashboard.value.history.top_domains || [])
const recentDays = computed(() => [...(dashboard.value.history.recent_days || [])].reverse())
const maxRecentDayCount = computed(() => Math.max(...recentDays.value.map((item) => item.count), 1))

onMounted(() => {
  store.fetchDashboard({ silent: true }).catch(() => {})
  store.fetchJobs({ silent: true }).catch(() => {})
})
</script>

<template>
  <section class="page">
    <div class="page-heading">
      <div>
        <h1>總覽</h1>
        <p>用一個工作台看下載核心、queue、歷史紀錄與 cookie registry 的整體狀態。</p>
      </div>
      <button class="btn btn--ghost" type="button" :disabled="store.isLoading('dashboard')" @click="store.fetchDashboard()">
        {{ store.isLoading('dashboard') ? '更新中...' : '更新總覽' }}
      </button>
    </div>

    <div class="stats-grid">
      <StatCard title="Queue 項目" :value="dashboard.queue.total" hint="含目前執行與待處理工作" tone="primary" />
      <StatCard title="成功紀錄" :value="dashboard.history.success" hint="目前 history_entries 中狀態為 success" tone="success" />
      <StatCard title="失敗紀錄" :value="dashboard.history.failed" hint="可從歷史頁快速重新送出" tone="danger" />
      <StatCard title="Cookie 檔案" :value="dashboard.cookies.count" hint="自動掃描 data/cookies 與相容路徑" />
    </div>

    <div class="content-grid content-grid--two">
      <section class="panel-card">
        <div class="panel-card__header">
          <div>
            <h2>工作狀態摘要</h2>
            <p>依目前 jobs table 匯總。</p>
          </div>
        </div>

        <div class="status-summary">
          <div class="summary-pill summary-pill--queued">Queued {{ jobCounts.queued ?? 0 }}</div>
          <div class="summary-pill summary-pill--running">Running {{ jobCounts.running ?? 0 }}</div>
          <div class="summary-pill summary-pill--success">Success {{ jobCounts.success ?? 0 }}</div>
          <div class="summary-pill summary-pill--failed">Failed {{ jobCounts.failed ?? 0 }}</div>
          <div class="summary-pill summary-pill--skipped">Skipped {{ jobCounts.skipped ?? 0 }}</div>
        </div>

        <div class="dashboard-current">
          <div class="dashboard-current__label">目前下載中</div>
          <div class="dashboard-current__value">
            {{ dashboard.queue.current || '目前沒有執行中的工作' }}
          </div>
        </div>
      </section>

      <section class="panel-card">
        <div class="panel-card__header">
          <div>
            <h2>歷史摘要</h2>
            <p>快速掌握近期分布。</p>
          </div>
        </div>

        <div v-if="recentDays.length === 0" class="empty-state">目前沒有可顯示的歷史趨勢。</div>
        <div v-else class="bar-list">
          <div v-for="item in recentDays" :key="item.date" class="bar-row">
            <div class="bar-row__label">{{ formatDate(item.date) }}</div>
            <div class="bar-row__track">
              <div class="bar-row__fill" :style="{ width: `${Math.max(10, (item.count / maxRecentDayCount) * 100)}%` }" />
            </div>
            <div class="bar-row__value">{{ item.count }}</div>
          </div>
        </div>
      </section>
    </div>

    <div class="content-grid content-grid--two">
      <section class="panel-card">
        <div class="panel-card__header">
          <div>
            <h2>Top Domains</h2>
            <p>最常出現的歷史來源。</p>
          </div>
        </div>

        <div v-if="topDomains.length === 0" class="empty-state">還沒有歷史資料。</div>
        <ul v-else class="domain-list">
          <li v-for="item in topDomains" :key="item.domain" class="domain-list__item">
            <span>{{ item.domain }}</span>
            <strong>{{ item.count }}</strong>
          </li>
        </ul>
      </section>

      <section class="panel-card">
        <div class="panel-card__header">
          <div>
            <h2>近期工作</h2>
            <p>最近 8 筆 job。</p>
          </div>
        </div>

        <div v-if="recentJobs.length === 0" class="empty-state">目前沒有工作紀錄。</div>
        <div v-else class="table-shell">
          <table class="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>狀態</th>
                <th>Provider</th>
                <th>來源</th>
                <th>更新時間</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="job in recentJobs" :key="job.id">
                <td>#{{ job.id }}</td>
                <td><StatusChip :status="job.status" /></td>
                <td>{{ job.provider }}</td>
                <td>{{ job.source }}</td>
                <td>{{ formatDateTime(job.updated_at) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  </section>
</template>
