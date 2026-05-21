<script setup>
import { computed } from 'vue'

import { formatNumber } from '../utils/format'

const props = defineProps({
  title: {
    type: String,
    required: true,
  },
  value: {
    type: [String, Number],
    default: 0,
  },
  hint: {
    type: String,
    default: '',
  },
  tone: {
    type: String,
    default: 'default',
  },
})

const displayValue = computed(() => (typeof props.value === 'number' ? formatNumber(props.value) : props.value))
</script>

<template>
  <article class="stat-card" :class="`stat-card--${tone}`">
    <div class="stat-card__title">{{ title }}</div>
    <div class="stat-card__value">{{ displayValue }}</div>
    <div v-if="hint" class="stat-card__hint">{{ hint }}</div>
  </article>
</template>
