<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps({
  title: { type: String, required: true },
  description: { type: String, default: '' },
  iconLabel: { type: String, default: 'P' },
  badgeValue: { type: [Number, String], default: '' },
  summaryText: { type: String, default: '' },
  panelClass: { type: [String, Array, Object], default: '' },
  desktopPanelClass: { type: [String, Array, Object], default: '' },
  compactMaxWidth: { type: Number, default: 1200 },
  initiallyOpenCompact: { type: Boolean, default: false },
})

const isCompact = ref(false)
const isOpen = ref(true)
const instanceId = `compact-panel-${Math.random().toString(16).slice(2)}`
let mediaQuery = null
let mediaQueryHandler = null
let openPanelHandler = null

const hasBadge = computed(() => props.badgeValue !== '' && props.badgeValue !== null && props.badgeValue !== undefined)
const launcherMetric = computed(() => {
  if (props.summaryText) return props.summaryText
  return hasBadge.value ? String(props.badgeValue) : ''
})
function applyCompactState(matches) {
  isCompact.value = matches
  isOpen.value = matches ? false : true
}

function togglePanel() {
  if (!isCompact.value) return
  const nextOpen = !isOpen.value
  if (nextOpen) {
    window.dispatchEvent(new CustomEvent('compact-panel:open', { detail: { id: instanceId } }))
  }
  isOpen.value = nextOpen
}

onMounted(() => {
  mediaQuery = window.matchMedia(`(max-width: ${props.compactMaxWidth}px)`)
  applyCompactState(mediaQuery.matches)
  mediaQueryHandler = (event) => applyCompactState(event.matches)
  openPanelHandler = (event) => {
    if (event.detail?.id !== instanceId) {
      isOpen.value = false
    }
  }
  mediaQuery.addEventListener('change', mediaQueryHandler)
  window.addEventListener('compact-panel:open', openPanelHandler)
})

onBeforeUnmount(() => {
  mediaQuery?.removeEventListener('change', mediaQueryHandler)
  window.removeEventListener('compact-panel:open', openPanelHandler)
})
</script>

<template>
  <section v-if="!isCompact" class="panel-card compact-panel" :class="[panelClass, desktopPanelClass]">
    <div class="panel-card__header compact-panel__header">
      <div class="compact-panel__intro">
        <span class="compact-panel__icon" aria-hidden="true">{{ iconLabel }}</span>
        <div>
          <h2>{{ title }}</h2>
          <p v-if="description">{{ description }}</p>
        </div>
      </div>
    </div>

    <div class="compact-panel__body">
      <slot />
    </div>
  </section>

  <Teleport v-else to="#compact-panel-dock">
    <button class="compact-panel__launcher" :class="[panelClass, { 'compact-panel__launcher--active': isOpen }]" type="button" @click="togglePanel">
      <span class="compact-panel__launcher-main">
        <span class="compact-panel__icon compact-panel__icon--launcher" aria-hidden="true">{{ iconLabel }}</span>
        <span class="compact-panel__launcher-label">{{ title }}</span>
      </span>
      <span v-if="launcherMetric" class="compact-panel__metric">{{ launcherMetric }}</span>
    </button>
  </Teleport>

  <Teleport v-if="isCompact && isOpen" to="body">
    <div v-if="isOpen" class="compact-panel__backdrop" @click="togglePanel" />
    <section v-if="isOpen" class="panel-card compact-panel compact-panel--drawer" :class="panelClass">
      <div class="panel-card__header compact-panel__header">
        <div class="compact-panel__intro">
          <span class="compact-panel__icon" aria-hidden="true">{{ iconLabel }}</span>
          <div>
            <h2>{{ title }}</h2>
            <p v-if="description">{{ description }}</p>
          </div>
        </div>

        <button class="compact-panel__toggle compact-panel__toggle--icon" type="button" aria-label="Close panel" @click="togglePanel">×</button>
      </div>

      <div class="compact-panel__body">
        <slot />
      </div>
    </section>
  </Teleport>
</template>
