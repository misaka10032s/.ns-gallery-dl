<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps({
  title: { type: String, required: true },
  description: { type: String, default: '' },
  iconLabel: { type: String, default: 'P' },
  badgeValue: { type: [Number, String], default: '' },
  panelClass: { type: [String, Array, Object], default: '' },
  compactMaxWidth: { type: Number, default: 960 },
  initiallyOpenCompact: { type: Boolean, default: false },
})

const isCompact = ref(false)
const isOpen = ref(true)
let mediaQuery = null
let mediaQueryHandler = null

const hasBadge = computed(() => props.badgeValue !== '' && props.badgeValue !== null && props.badgeValue !== undefined)
const isExpanded = computed(() => !isCompact.value || isOpen.value)

function applyCompactState(matches) {
  isCompact.value = matches
  isOpen.value = matches ? props.initiallyOpenCompact : true
}

function togglePanel() {
  if (!isCompact.value) return
  isOpen.value = !isOpen.value
}

onMounted(() => {
  mediaQuery = window.matchMedia(`(max-width: ${props.compactMaxWidth}px)`)
  applyCompactState(mediaQuery.matches)
  mediaQueryHandler = (event) => applyCompactState(event.matches)
  mediaQuery.addEventListener('change', mediaQueryHandler)
})

onBeforeUnmount(() => {
  mediaQuery?.removeEventListener('change', mediaQueryHandler)
})
</script>

<template>
  <section class="panel-card compact-panel" :class="[panelClass, { 'compact-panel--compact': isCompact, 'compact-panel--collapsed': !isExpanded }]">
    <div class="panel-card__header compact-panel__header">
      <div class="compact-panel__intro">
        <span class="compact-panel__icon" aria-hidden="true">{{ iconLabel }}</span>
        <div>
          <h2>{{ title }}</h2>
          <p v-if="description && (!isCompact || isExpanded)">{{ description }}</p>
        </div>
      </div>

      <button v-if="isCompact" class="compact-panel__toggle" type="button" @click="togglePanel">
        <span v-if="hasBadge" class="compact-panel__count">{{ badgeValue }}</span>
        <span>{{ isExpanded ? '收合' : '展開' }}</span>
      </button>
    </div>

    <div v-show="isExpanded" class="compact-panel__body">
      <slot />
    </div>
  </section>
</template>
