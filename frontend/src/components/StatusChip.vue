<script setup>
import { computed } from 'vue'

const props = defineProps({
  status: {
    type: String,
    default: '',
  },
})

const label = computed(() => (props.status || 'unknown').replace(/-/g, ' '))
</script>

<template>
  <span class="status-chip" :class="`status-chip--${status || 'unknown'}`">{{ label }}</span>
</template>
