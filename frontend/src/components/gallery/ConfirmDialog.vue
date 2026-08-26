<script setup>
import { ref, watch } from 'vue'

// Reusable destructive-action confirm — backed by a native <dialog>, never
// window.confirm() (cluster rule: any destructive confirmation must use an
// HTML dialog).
const props = defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, default: '確認' },
  message: { type: String, default: '' },
  confirmLabel: { type: String, default: '刪除' },
  cancelLabel: { type: String, default: '取消' },
})

const emit = defineEmits(['confirm', 'cancel'])

const dialogEl = ref(null)

watch(
  () => props.open,
  (isOpen) => {
    const el = dialogEl.value
    if (!el) return
    if (isOpen && !el.open) el.showModal()
    if (!isOpen && el.open) el.close()
  },
)

function onCancel() {
  emit('cancel')
}

function onConfirm() {
  emit('confirm')
}

function onNativeClose() {
  // Fired for Esc too — treat any non-explicit close as cancel.
  emit('cancel')
}
</script>

<template>
  <dialog ref="dialogEl" class="confirm-dialog" @cancel.prevent="onCancel" @close="onNativeClose">
    <div class="confirm-dialog__body">
      <h3 class="confirm-dialog__title">{{ title }}</h3>
      <p v-if="message" class="confirm-dialog__message">{{ message }}</p>
      <div class="confirm-dialog__actions">
        <button class="btn btn--ghost btn--small" type="button" @click="onCancel">
          {{ cancelLabel }}
        </button>
        <button class="btn btn--danger btn--small" type="button" @click="onConfirm">
          {{ confirmLabel }}
        </button>
      </div>
    </div>
  </dialog>
</template>

<style lang="scss" scoped>
@use '../../styles/tokens' as *;

.confirm-dialog {
  border: none;
  border-radius: 1rem;
  padding: 0;
  max-width: min(24rem, calc(100vw - 2rem));
  box-shadow: 0 20px 50px rgba(15, 23, 42, 0.25);

  &::backdrop {
    background: rgba(15, 23, 42, 0.55);
  }
}

.confirm-dialog__body {
  padding: 1.2rem 1.3rem;
}

.confirm-dialog__title {
  margin: 0 0 0.5rem;
  font-size: 1.02rem;
  color: $slate-900;
}

.confirm-dialog__message {
  margin: 0 0 1rem;
  font-size: 0.9rem;
  color: $slate-600;
  line-height: 1.5;
}

.confirm-dialog__actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.6rem;
}
</style>
