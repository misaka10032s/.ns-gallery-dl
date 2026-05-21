<script setup>
import { computed, onMounted, ref } from 'vue'

import { useHubStore } from '../stores/hub'
import { formatDateTime } from '../utils/format'

const store = useHubStore()
const search = ref('')
const provider = ref('all')
const domainInput = ref('')
const cookieValue = ref('')
const editingDomain = ref('')

const filteredCookies = computed(() => {
  const keyword = search.value.trim().toLowerCase()
  return store.cookies.filter((item) => {
    if (provider.value !== 'all' && item.provider !== provider.value) return false
    if (!keyword) return true
    return [item.domain, item.provider, item.file_name, item.file_path]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(keyword))
  })
})

onMounted(() => {
  store.fetchCookies({ silent: true }).catch(() => {})
})

function resetForm() {
  domainInput.value = ''
  cookieValue.value = ''
  editingDomain.value = ''
}

async function editCookie(domain) {
  const result = await store.loadCookieContent(domain)
  domainInput.value = result.domain
  cookieValue.value = result.content
  editingDomain.value = result.domain
}

async function submitCookie() {
  await store.saveCookie({
    domain: domainInput.value,
    cookieValue: cookieValue.value,
    previousDomain: editingDomain.value,
  })
  resetForm()
}

async function removeCookie(domain) {
  await store.deleteCookie(domain)
  if (editingDomain.value === domain) {
    resetForm()
  }
}
</script>

<template>
  <section class="page">
    <div class="page-heading">
      <div>
        <h1>Cookie 管理</h1>
        <p>統一檢視自動掃描到的 cookie 檔與對應 provider。</p>
      </div>
      <button class="btn btn--ghost" type="button" :disabled="store.isLoading('cookies')" @click="store.fetchCookies()">
        {{ store.isLoading('cookies') ? '重新掃描中...' : '重新掃描' }}
      </button>
    </div>

    <div class="content-grid content-grid--two">
      <section class="panel-card">
        <div class="panel-card__header">
          <div>
            <h2>{{ editingDomain ? '編輯 Cookie' : '新增 Cookie' }}</h2>
            <p>輸入網域與 cookie 值後，系統會自動命名檔案並立即套用。</p>
          </div>
        </div>

        <div class="field">
          <label class="field-label" for="cookie-domain">網域</label>
          <input id="cookie-domain" v-model="domainInput" class="input" type="text" placeholder="例如 facebook.com 或 x.com" />
        </div>

        <div class="field cookies-editor">
          <label class="field-label" for="cookie-value">Cookie 值</label>
          <textarea
            id="cookie-value"
            v-model="cookieValue"
            class="textarea"
            rows="10"
            placeholder="可貼上 Cookie header（name=value; name2=value2）或完整 Netscape cookie file 內容。"
          />
        </div>

        <div class="button-row cookies-actions">
          <button class="btn btn--primary" type="button" :disabled="store.isLoading('cookie-save')" @click="submitCookie">
            {{ store.isLoading('cookie-save') ? '儲存中...' : editingDomain ? '更新 Cookie' : '新增 Cookie' }}
          </button>
          <button class="btn btn--ghost" type="button" @click="resetForm">清空</button>
        </div>

        <ul class="helper-paths">
          <li><code>cookies/</code></li>
          <li>檔名會自動命名為 <code>cookies-&lt;domain&gt;.txt</code></li>
        </ul>
      </section>

      <section class="panel-card">
        <div class="panel-card__header">
          <div>
            <h2>篩選</h2>
            <p>快速找出特定站點的 cookie 配置。</p>
          </div>
        </div>
        <div class="filters-grid">
          <input v-model="search" class="input" type="search" placeholder="搜尋 domain、檔名、路徑..." />
          <select v-model="provider" class="select">
            <option value="all">所有 provider</option>
            <option value="gallery-dl">gallery-dl</option>
            <option value="ytdlp">yt-dlp</option>
            <option value="shared">shared</option>
          </select>
        </div>
      </section>
    </div>

    <section class="panel-card">
      <div class="panel-card__header">
        <div>
          <h2>Cookie Registry</h2>
          <p>共 {{ filteredCookies.length }} 筆。</p>
        </div>
      </div>

      <div v-if="filteredCookies.length === 0" class="empty-state">目前沒有掃描到 cookie 檔。</div>
      <div v-else class="table-shell">
        <table class="data-table">
          <thead>
            <tr>
              <th>Domain</th>
              <th>Provider</th>
              <th>檔名</th>
              <th>路徑</th>
              <th>更新時間</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in filteredCookies" :key="`${item.domain}-${item.provider}-${item.file_path}`">
              <td>{{ item.domain }}</td>
              <td>{{ item.provider }}</td>
              <td>{{ item.file_name }}</td>
              <td class="break-all">{{ item.file_path }}</td>
              <td>{{ formatDateTime(item.updated_at) }}</td>
              <td>
                <div class="button-row button-row--compact table-actions">
                  <button class="btn btn--ghost btn--small" type="button" @click="editCookie(item.domain)">編輯</button>
                  <button class="btn btn--danger btn--small" type="button" @click="removeCookie(item.domain)">刪除</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </section>
</template>
