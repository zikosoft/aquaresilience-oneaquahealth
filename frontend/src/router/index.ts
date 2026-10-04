import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import { trackPageView } from '@/services/analytics'
import { useAuthStore } from '@/stores/auth'

declare module 'vue-router' {
  interface RouteMeta {
    requiresAuth?: boolean
    module?: string
    titleKey?: string
  }
}

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/auth/LoginView.vue'),
    meta: { requiresAuth: false },
  },
  {
    path: '/',
    component: () => import('@/layouts/DefaultLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      { path: '', redirect: { name: 'dashboard' } },
      {
        path: 'dashboard',
        name: 'dashboard',
        component: () => import('@/views/dashboard/CommandCenterView.vue'),
        meta: { requiresAuth: true, module: 'DASHBOARD', titleKey: 'nav.dashboard' },
      },
      {
        path: 'map',
        name: 'map',
        component: () => import('@/views/map/ResilienceMapView.vue'),
        meta: { requiresAuth: true, module: 'MAP', titleKey: 'nav.map' },
      },
      {
        path: 'alerts',
        name: 'alerts',
        component: () => import('@/views/alerts/EarlyWarningsView.vue'),
        meta: { requiresAuth: true, module: 'ALERTS', titleKey: 'nav.alerts' },
      },
      {
        path: 'intelligence',
        name: 'intelligence',
        component: () => import('@/views/intelligence/AIIntelligenceView.vue'),
        meta: { requiresAuth: true, module: 'AI_INTELLIGENCE', titleKey: 'nav.aiIntelligence' },
      },
      {
        path: 'scenarios',
        name: 'scenarios',
        component: () => import('@/views/scenarios/ScenarioSimulatorView.vue'),
        meta: { requiresAuth: true, module: 'SCENARIOS', titleKey: 'nav.scenarios' },
      },
      {
        path: 'sources',
        name: 'sources',
        component: () => import('@/views/sources/DataSourcesView.vue'),
        meta: { requiresAuth: true, module: 'DATA_SOURCES', titleKey: 'nav.dataSources' },
      },
      {
        path: 'settings',
        name: 'settings',
        component: () => import('@/views/settings/SettingsView.vue'),
        meta: { requiresAuth: true, module: 'SETTINGS', titleKey: 'nav.settings' },
      },
      {
        path: 'forbidden',
        name: 'forbidden',
        component: () => import('@/views/errors/ForbiddenView.vue'),
        meta: { requiresAuth: true },
      },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/views/errors/NotFoundView.vue'),
    meta: { requiresAuth: false },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach(async (to) => {
  const authStore = useAuthStore()

  if (authStore.accessToken && !authStore.currentUser && !authStore.initializing) {
    await authStore.initialize()
  }

  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  if (to.name === 'login' && authStore.isAuthenticated) {
    return { name: 'dashboard' }
  }

  if (to.meta.module && !authStore.can(to.meta.module, 'VIEW')) {
    return { name: 'forbidden' }
  }

  return true
})

router.afterEach((to, _from, failure) => {
  if (failure) return
  trackPageView(to.path, String(to.name ?? to.path))
})

export default router
