<script setup>
import { ref } from 'vue'

import { apiRequest } from '../api/client'
import DoujinBookWall from '../components/gallery/DoujinBookWall.vue'
import GeneralGalleryPanel from '../components/gallery/GeneralGalleryPanel.vue'

// Media library. `mode` on each category (from app.config.gallery_modes via
// GET /api/gallery) decides which panel renders — this view no longer needs
// its own copy of "which sources are doujinshi": doujinshi mode (wnacg /
// nhentai / 18comic / exhentai) gets a cover-wall + page reader
// (DoujinBookWall), everything else keeps the pre-existing thumbnail wall
// (GeneralGalleryPanel, unchanged behavior — only relocated out of this file
// so a second full mode didn't grow this view toward a thousand lines).
const categories = ref([])
const selectedCategory = ref(null)
const loadingCats = ref(false)

async function fetchCategories() {
  loadingCats.value = true
  try {
    categories.value = await apiRequest('/api/gallery')
    if (categories.value.length) {
      const stillExists = categories.value.find((c) => c.path === selectedCategory.value?.path)
      selectedCategory.value = stillExists ?? categories.value[0]
    } else {
      selectedCategory.value = null
    }
  } finally {
    loadingCats.value = false
  }
}

function selectCategory(cat) {
  selectedCategory.value = cat
}

fetchCategories()
</script>

<template>
  <section class="page">
    <div class="page-heading">
      <div>
        <h1>媒體庫</h1>
        <p>瀏覽已下載的圖片與影片。</p>
      </div>
      <button class="btn btn--ghost" type="button" :disabled="loadingCats" @click="fetchCategories">
        {{ loadingCats ? '載入中...' : '重新整理' }}
      </button>
    </div>

    <!-- Category chips -->
    <div class="gallery-cats">
      <button
        v-for="cat in categories"
        :key="cat.path"
        class="cat-chip"
        :class="{ 'cat-chip--active': selectedCategory?.path === cat.path }"
        type="button"
        @click="selectCategory(cat)"
      >
        {{ cat.name }}
        <span class="cat-chip__count">{{ cat.item_count }}</span>
      </button>
      <div v-if="!categories.length && !loadingCats" class="gallery-empty-hint">
        下載目錄是空的，先用 Queue 下載一些東西吧！
      </div>
    </div>

    <DoujinBookWall
      v-if="selectedCategory && selectedCategory.mode === 'doujinshi'"
      :key="`doujin-${selectedCategory.path}`"
      :category="selectedCategory"
    />
    <GeneralGalleryPanel
      v-else-if="selectedCategory"
      :key="`general-${selectedCategory.path}`"
      :category="selectedCategory"
    />
  </section>
</template>

<style lang="scss" scoped>
@use '../styles/tokens' as *;

// ── Category chips ─────────────────────────────────────────────────────────
.gallery-cats {
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem;
  margin-bottom: 1.2rem;
}

.cat-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.4rem 0.9rem;
  border-radius: 999px;
  border: 1px solid $slate-300;
  background: $surface-soft;
  color: $slate-700;
  font-size: 0.88rem;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s, color 0.15s;

  &:hover {
    border-color: $blue-600;
    color: $blue-600;
  }

  &--active {
    background: $blue-600;
    border-color: $blue-600;
    color: #fff;

    .cat-chip__count {
      background: rgba(255, 255, 255, 0.25);
    }
  }
}

.cat-chip__count {
  display: inline-block;
  padding: 0 0.4rem;
  border-radius: 999px;
  background: $slate-200;
  font-size: 0.78rem;
  font-weight: 700;
}

.gallery-empty-hint {
  color: $slate-500;
  font-size: 0.9rem;
  padding: 0.4rem 0;
}
</style>
