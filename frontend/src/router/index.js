import { createRouter, createWebHistory } from 'vue-router'

import CookiesView from '../views/CookiesView.vue'
import DashboardView from '../views/DashboardView.vue'
import GalleryView from '../views/GalleryView.vue'
import HistoryView from '../views/HistoryView.vue'
import JobsView from '../views/JobsView.vue'
import QueueView from '../views/QueueView.vue'

const routes = [
  { path: '/', name: 'dashboard', component: DashboardView, meta: { title: '總覽' } },
  { path: '/gallery', name: 'gallery', component: GalleryView, meta: { title: '媒體庫' } },
  { path: '/history', name: 'history', component: HistoryView, meta: { title: '歷史紀錄' } },
  { path: '/queue', name: 'queue', component: QueueView, meta: { title: '下載佇列' } },
  { path: '/jobs', name: 'jobs', component: JobsView, meta: { title: '工作紀錄' } },
  { path: '/cookies', name: 'cookies', component: CookiesView, meta: { title: 'Cookie 管理' } },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.afterEach((to) => {
  document.title = `NS Media Hub · ${to.meta.title ?? '控制台'}`
})

export default router
