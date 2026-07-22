import { defineStore } from 'pinia'

import { apiRequest } from '../api/client'
import { parseLinksInput } from '../utils/format'

function emptyQueue() {
  return { current: null, pending: [], total: 0 }
}

function emptyDashboard() {
  return {
    queue: emptyQueue(),
    jobs: { counts: {}, recent: [] },
    history: { total: 0, success: 0, failed: 0, skipped: 0, top_domains: [], recent_days: [] },
    cookies: { count: 0 },
  }
}

export const useHubStore = defineStore('hub', {
  state: () => ({
    dashboard: emptyDashboard(),
    historyMap: {},
    queue: emptyQueue(),
    jobs: [],
    cookies: [],
    loadingKeys: [],
    notifications: [],
    apiHealthy: true,
    lastSyncAt: '',
  }),
  getters: {
    isLoading: (state) => (key) => state.loadingKeys.includes(key),
    historyEntries: (state) =>
      Object.entries(state.historyMap)
        .flatMap(([date, items]) => items.map((item) => ({ ...item, date })))
        .sort((left, right) => {
          if (left.date === right.date) {
            return String(right.url).localeCompare(String(left.url))
          }
          return String(right.date).localeCompare(String(left.date))
        }),
  },
  actions: {
    setLoading(key, enabled) {
      if (enabled) {
        if (!this.loadingKeys.includes(key)) {
          this.loadingKeys.push(key)
        }
        return
      }
      this.loadingKeys = this.loadingKeys.filter((item) => item !== key)
    },
    notify(message, type = 'success') {
      const id = `${Date.now()}-${Math.random().toString(16).slice(2)}`
      this.notifications.push({ id, type, message })
      window.setTimeout(() => this.removeNotification(id), 4500)
    },
    removeNotification(id) {
      this.notifications = this.notifications.filter((item) => item.id !== id)
    },
    touchSync() {
      this.apiHealthy = true
      this.lastSyncAt = new Date().toISOString()
    },
    async runTask(key, task, { silent = false } = {}) {
      this.setLoading(key, true)
      try {
        const result = await task()
        this.touchSync()
        return result
      } catch (error) {
        this.apiHealthy = false
        if (!silent) {
          this.notify(error.message || '操作失敗', 'error')
        }
        throw error
      } finally {
        this.setLoading(key, false)
      }
    },
    async fetchDashboard({ silent = false } = {}) {
      return this.runTask(
        'dashboard',
        async () => {
          this.dashboard = (await apiRequest('/api/dashboard')) ?? emptyDashboard()
          return this.dashboard
        },
        { silent },
      )
    },
    async fetchHistory({ silent = false } = {}) {
      return this.runTask(
        'history',
        async () => {
          this.historyMap = (await apiRequest('/api/history')) ?? {}
          return this.historyMap
        },
        { silent },
      )
    },
    async fetchQueue({ silent = false } = {}) {
      return this.runTask(
        'queue',
        async () => {
          this.queue = (await apiRequest('/api/queue')) ?? emptyQueue()
          return this.queue
        },
        { silent },
      )
    },
    async fetchJobs({ silent = false } = {}) {
      return this.runTask(
        'jobs',
        async () => {
          this.jobs = (await apiRequest('/api/jobs')) ?? []
          return this.jobs
        },
        { silent },
      )
    },
    async fetchCookies({ silent = false } = {}) {
      return this.runTask(
        'cookies',
        async () => {
          this.cookies = (await apiRequest('/api/cookies')) ?? []
          return this.cookies
        },
        { silent },
      )
    },
    async loadCookieContent(domain) {
      return this.runTask('cookie-content', () => apiRequest(`/api/cookies/${encodeURIComponent(domain)}`))
    },
    async saveCookie({ domain, cookieValue, previousDomain = '' }) {
      const method = previousDomain ? 'PUT' : 'POST'
      const result = await this.runTask('cookie-save', () =>
        apiRequest('/api/cookies', {
          method,
          body: { domain, cookieValue, previousDomain },
        }),
      )
      this.notify(result?.message || 'Cookie 已儲存。')
      await Promise.all([this.fetchCookies({ silent: true }), this.fetchDashboard({ silent: true })])
      return result?.cookie ?? null
    },
    async deleteCookie(domain) {
      const result = await this.runTask('cookie-delete', () =>
        apiRequest('/api/cookies', {
          method: 'DELETE',
          body: { domain },
        }),
      )
      this.notify(result?.message || 'Cookie 已刪除。')
      await Promise.all([this.fetchCookies({ silent: true }), this.fetchDashboard({ silent: true })])
    },
    async submitLinks(rawInput, providerHint = '') {
      const links = parseLinksInput(rawInput)
      if (!links.length) {
        this.notify('請先輸入至少一個 URL。', 'error')
        return 0
      }
      const payload = { links, source: 'manual' }
      if (providerHint) {
        payload.providerHint = providerHint
      }
      const result = await this.runTask('submit', () => apiRequest('/api/jobs', { method: 'POST', body: payload }))
      this.notify(result?.message || `Queued ${links.length} links for download.`)
      await Promise.all([
        this.fetchDashboard({ silent: true }),
        this.fetchQueue({ silent: true }),
        this.fetchJobs({ silent: true }),
      ])
      return links.length
    },
    async requeueHistory(links) {
      const sourceEntries = Array.isArray(links) ? links : []
      const mappedEntries = sourceEntries
        .map((entry) => {
          if (typeof entry === 'string') {
            return this.historyEntries.find((item) => item.url === entry) || { url: entry }
          }
          return entry
        })
        .filter((entry) => entry?.url)
      const cleaned = Array.from(new Map(mappedEntries.map((entry) => [entry.url, entry])).values())
      if (!cleaned.length) {
        this.notify('沒有可重新送出的紀錄。', 'error')
        return 0
      }
      const result = await this.runTask('requeue', () =>
        apiRequest('/api/history/requeue', {
          method: 'POST',
          body: {
            items: cleaned.map((entry) => ({
              url: entry.url,
              provider: entry.provider || null,
              meta: entry.meta || {},
            })),
          },
        }),
      )
      this.notify(result?.message || `Queued ${cleaned.length} links for download.`)
      await Promise.all([
        this.fetchDashboard({ silent: true }),
        this.fetchQueue({ silent: true }),
        this.fetchJobs({ silent: true }),
        this.fetchHistory({ silent: true }),
      ])
      return cleaned.length
    },
    async updateHistoryStatus(date, url, status) {
      await this.runTask('history-update', () =>
        apiRequest('/api/history', {
          method: 'PUT',
          body: { date, url, status },
        }),
      )
      this.notify('歷史狀態已更新。')
      await Promise.all([this.fetchHistory({ silent: true }), this.fetchDashboard({ silent: true })])
    },
    async deleteHistoryEntry(date, url) {
      await this.runTask('history-delete', () =>
        apiRequest('/api/history', {
          method: 'DELETE',
          body: { date, url },
        }),
      )
      this.notify('歷史紀錄已刪除。')
      await Promise.all([this.fetchHistory({ silent: true }), this.fetchDashboard({ silent: true })])
    },
    async retryJob(jobId) {
      const result = await this.runTask('job-retry', () => apiRequest(`/api/jobs/${jobId}/retry`, { method: 'POST' }))
      this.notify(result?.message || '已重新送出工作。')
      await Promise.all([
        this.fetchDashboard({ silent: true }),
        this.fetchQueue({ silent: true }),
        this.fetchJobs({ silent: true }),
        this.fetchHistory({ silent: true }),
      ])
    },
    async updateDownloaders() {
      // Errors (409 佇列忙碌中 / 403 同源檢查失敗) surface automatically via
      // runTask()'s catch → notify(error.message, 'error') — no special-casing needed here.
      const result = await this.runTask('downloader-update', () =>
        apiRequest('/api/downloaders/update', { method: 'POST' }),
      )
      const results = Array.isArray(result?.results) ? result.results : []
      if (!results.length) {
        this.notify('沒有可更新的下載器套件。', 'error')
        return results
      }
      const summary = results
        .map((item) => {
          const label = item.package || '未知套件'
          if (item.changed) {
            return `${label} ${item.old_version || '未知'} → ${item.new_version || '未知'}`
          }
          return `${label} 已是最新 (${item.new_version || item.old_version || '未知'})`
        })
        .join('；')
      this.notify(`下載器更新完成：${summary}`)
      return results
    },
  },
})
