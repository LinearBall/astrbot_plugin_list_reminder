import { createRouter, createWebHistory } from 'vue-router'

import LoginView from '../views/LoginView.vue'
import TodoView from '../views/TodoView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'todos',
      component: TodoView,
    },
    {
      path: '/login',
      name: 'login',
      component: LoginView,
    },
    {
      // 未知路径统一回到待办列表
      path: '/:pathMatch(.*)*',
      redirect: '/',
    },
  ],
})

export default router
