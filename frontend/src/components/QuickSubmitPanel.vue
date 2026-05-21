<script setup>
import { computed, ref } from 'vue'

import CompactPanelCard from './CompactPanelCard.vue'
import { useHubStore } from '../stores/hub'

const store = useHubStore()
const inputValue = ref('')

const queuedPreview = computed(() => store.queue.pending.slice(0, 4))
const queueSummary = computed(() => `待處理 ${store.queue.pending.length}`)

async function submitLinks() {
  const count = await store.submitLinks(inputValue.value)
  if (count > 0) {
    inputValue.value = ''
  }
}

async function pasteLinks() {
  try {
    inputValue.value = await navigator.clipboard.readText()
  } catch {
    store.notify('無法從剪貼簿讀取內容。', 'error')
  }
}
</script>

<template>
  <CompactPanelCard
    title="快速送件"
    description="貼上網址後直接排入 queue，provider 由系統自動判斷。"
    icon-label="Q"
    :badge-value="store.queue.total"
    :summary-text="queueSummary"
    panel-class="quick-submit"
    :compact-max-width="1200"
  >

    <label class="field-label" for="quick-submit-input">URL 清單</label>
    <textarea
      id="quick-submit-input"
      v-model="inputValue"
      class="textarea"
      rows="10"
      placeholder="每行一個網址，或以空白、逗號分隔。"
    />

    <div class="button-row quick-submit__actions">
      <button class="btn btn--primary" type="button" :disabled="store.isLoading('submit')" @click="submitLinks">
        {{ store.isLoading('submit') ? '送出中...' : '送出' }}
      </button>
      <button class="btn btn--ghost" type="button" @click="pasteLinks">貼上</button>
      <button class="btn btn--ghost" type="button" @click="inputValue = ''">清空</button>
    </div>

    <div class="helper-list">
      <div class="helper-list__title">小提醒</div>
      <ul>
        <li>Pixiv、nhentai、wnacg 會自動交給 gallery-dl。</li>
        <li>YouTube、X、Facebook 會自動交給 yt-dlp。</li>
        <li>支援一次送出多個網址，並會保留 queue / jobs 紀錄。</li>
      </ul>
    </div>

    <div class="mini-feed">
      <div class="mini-feed__title">即將處理</div>
      <div v-if="queuedPreview.length === 0" class="empty-state empty-state--compact">目前 queue 是空的。</div>
      <ul v-else class="mini-feed__list">
        <li v-for="item in queuedPreview" :key="item">{{ item }}</li>
      </ul>
    </div>
  </CompactPanelCard>
</template>
