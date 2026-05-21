<script setup>
defineProps({
  items: {
    type: Array,
    default: () => [],
  },
})

defineEmits(['dismiss'])
</script>

<template>
  <div class="toast-stack">
    <transition-group name="toast">
      <div v-for="item in items" :key="item.id" class="toast" :class="`toast--${item.type}`">
        <span>{{ item.message }}</span>
        <button type="button" class="toast__close" @click="$emit('dismiss', item.id)">×</button>
      </div>
    </transition-group>
  </div>
</template>
