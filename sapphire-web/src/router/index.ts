import { createRouter, createWebHistory } from 'vue-router'
import DashboardView from '../views/DashboardView.vue'

const router = createRouter({
    history: createWebHistory(import.meta.env.BASE_URL),
    routes: [
        {
            path: '/',
            name: 'dashboard',
            component: DashboardView
        },
        {
            path: '/terminal',
            name: 'terminal',
            component: () => import('../views/TerminalView.vue')
        },
        {
            path: '/agents',
            name: 'agents',
            component: () => import('../views/AgentsView.vue')
        },
        {
            path: '/settings',
            name: 'settings',
            component: () => import('../views/SettingsView.vue')
        },
        // Add more routes here
    ]
})

export default router
