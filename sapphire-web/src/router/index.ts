import { createRouter, createWebHistory } from 'vue-router'
import SapphireBookView from '../views/SapphireBookView.vue'

const router = createRouter({
    history: createWebHistory(import.meta.env.BASE_URL),
    routes: [
        {
            path: '/',
            redirect: '/sapphirebook',
        },
        {
            path: '/sapphirebook',
            name: 'sapphirebook',
            component: SapphireBookView,
        },
        {
            path: '/sapphiretrade',
            name: 'sapphiretrade',
            component: () => import('../views/SapphireTradeView.vue'),
        },
        {
            path: '/sapphirealpha',
            name: 'sapphirealpha',
            component: () => import('../views/SapphireAlphaView.vue'),
        },
        {
            path: '/predictions',
            name: 'predictions',
            component: () => import('../views/SapphirePredictionsView.vue'),
        },
        {
            path: '/agents',
            name: 'agents',
            component: () => import('../views/SapphireAgentsView.vue'),
        },
        {
            path: '/:pathMatch(.*)*',
            redirect: '/sapphirebook',
        },
    ]
})

export default router
