<script setup>
import { onMounted } from 'vue'

import AppHeader from './components/AppHeader.vue'
import QuickSubmitPanel from './components/QuickSubmitPanel.vue'
import ToastStack from './components/ToastStack.vue'
import { useHubStore } from './stores/hub'

const store = useHubStore()

onMounted(() => {
  store.fetchDashboard({ silent: true }).catch(() => {})
  store.fetchQueue({ silent: true }).catch(() => {})
})
</script>

<template>
  <div class="app-shell">
    <AppHeader />

    <main class="workspace">
      <section class="workspace-main">
        <router-view />
      </section>

      <aside class="workspace-side">
        <QuickSubmitPanel />
      </aside>
    </main>

    <div id="compact-panel-dock" class="compact-panel-dock" />

    <ToastStack :items="store.notifications" @dismiss="store.removeNotification" />
  </div>
</template>
