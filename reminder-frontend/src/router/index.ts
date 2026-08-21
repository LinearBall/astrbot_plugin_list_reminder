import { createRouter, createWebHistory } from 'vue-router';

import { getAuthKey } from '@/fbApi/apis';
import LoginView from '@/views/LoginView.vue';
import TodoView from '@/views/TodoView.vue';
import UserManageView from "@/views/UserManageView.vue";

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/todo',
      name: 'todos',
      component: TodoView,
    },
    {
      path: '/login',
      name: 'login',
      component: LoginView,
    },
    {
      path: "/user-manage",
      name: "User Management",
      component: UserManageView,
    },
    {
      // 未知路径统一回到待办列表
      path: '/:pathMatch(.*)*',
      redirect: '/login',
    },
  ],
})

// 方案A：把当前标签页的登录密钥保留在 URL query 上，
// 这样同一浏览器里每个标签页都能持有自己的账号身份。
router.beforeEach((to) => {
  const key = getAuthKey();
  if (key && !to.query.key) {
    return { path: to.path, query: { ...to.query, key } };
  }
  return true;
})

export default router
