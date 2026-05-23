<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

import StatusChip from '../components/StatusChip.vue'
import { useHubStore } from '../stores/hub'
import { formatDateTime } from '../utils/format'

const store = useHubStore()
const search = ref('')
const status = ref('all')
const provider = ref('all')
const source = ref('all')
const autoRefresh = ref(localStorage.getItem('nsmh-jobs-autorefresh') !== '0')
let timerId = null

const filteredJobs = computed(() => {
  const keyword = search.value.trim().toLowerCase()
  return store.jobs.filter((job) => {
    if (status.value !== 'all' && job.status !== status.value) return false
    if (provider.value !== 'all' && job.provider !== provider.value) return false
    if (source.value !== 'all' && job.source !== source.value) return false
    if (!keyword) return true
    return [job.url, job.domain, job.download_path, job.error, job.provider, job.source]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(keyword))
  })
})

function clearTimer() {
  if (timerId !== null) {
    window.clearInterval(timerId)
    timerId = null
  }
}

function syncAutoRefresh() {
  clearTimer()
  if (!autoRefresh.value) return
  timerId = window.setInterval(() => {
    store.fetchJobs({ silent: true }).catch(() => {})
  }, 6000)
}

onMounted(() => {
  store.fetchJobs({ silent: true }).catch(() => {})
  syncAutoRefresh()
})

onUnmounted(() => {
  clearTimer()
})

watch(autoRefresh, (value) => {
  localStorage.setItem('nsmh-jobs-autorefresh', value ? '1' : '0')
  syncAutoRefresh()
})
</script>

<template>
  <section class="page">
    <div class="page-heading">
      <div>
        <h1>工作紀錄</h1>
        <p>在同一頁完成搜尋、篩選與 retry，不用再回其他頁找 URL。</p>
      </div>
      <div class="page-heading__actions">
        <label class="toggle">
          <input v-model="autoRefresh" type="checkbox" />
          <span>自動更新</span>
        </label>
        <button class="btn btn--ghost" type="button" :disabled="store.isLoading('jobs')" @click="store.fetchJobs()">
          {{ store.isLoading('jobs') ? '更新中...' : '重新整理' }}
        </button>
      </div>
    </div>

    <section class="panel-card">
      <div class="filters-grid">
        <input v-model="search" class="input" type="search" placeholder="搜尋 URL、下載路徑、domain、錯誤訊息..." />
        <select v-model="status" class="select">
          <option value="all">所有狀態</option>
          <option value="queued">queued</option>
          <option value="running">running</option>
          <option value="success">success</option>
          <option value="failed">failed</option>
          <option value="skipped">skipped</option>
        </select>
        <select v-model="provider" class="select">
          <option value="all">所有 provider</option>
          <option value="gallery-dl">gallery-dl</option>
          <option value="ytdlp">yt-dlp</option>
          <option value="direct-file">direct-file</option>
        </select>
        <select v-model="source" class="select">
          <option value="all">所有來源</option>
          <option value="manual">manual</option>
          <option value="api">api</option>
          <option value="extension">extension</option>
          <option value="discord">discord</option>
        </select>
      </div>
    </section>

    <section class="panel-card">
      <div class="panel-card__header">
        <div>
          <h2>工作表</h2>
          <p>共 {{ filteredJobs.length }} / {{ store.jobs.length }} 筆。</p>
        </div>
      </div>

      <div v-if="filteredJobs.length === 0" class="empty-state">沒有符合條件的工作。</div>
      <div v-else class="table-shell">
        <table class="data-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>狀態</th>
              <th>Provider</th>
              <th>來源</th>
              <th>Domain</th>
              <th>URL</th>
              <th>Download Path</th>
              <th>Updated</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="job in filteredJobs" :key="job.id">
              <td>#{{ job.id }}</td>
              <td><StatusChip :status="job.status" /></td>
              <td>{{ job.provider }}</td>
              <td>{{ job.source }}</td>
              <td>{{ job.domain }}</td>
              <td class="break-all">
                <a :href="job.url" target="_blank" rel="noreferrer">{{ job.url }}</a>
                <div v-if="job.error" class="table-error">{{ job.error }}</div>
              </td>
              <td class="break-all">{{ job.download_path || '—' }}</td>
              <td>{{ formatDateTime(job.updated_at) }}</td>
              <td>
                <button class="btn btn--ghost btn--small" type="button" @click="store.retryJob(job.id)">重試</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </section>
</template>
