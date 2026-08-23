import { createRouter, createWebHistory } from 'vue-router';

import { getAuthKey } from '@/fbApi/apis';
import CalendarView from '@/views/CalendarView.vue';
import DashboardView from '@/views/DashboardView.vue';
import LoginView from '@/views/LoginView.vue';
import TodoView from '@/views/TodoView.vue';
import UserManageView from '@/views/UserManageView.vue';

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', redirect: '/dashboard' },
    { path: '/dashboard', name: 'dashboard', component: DashboardView },
    { path: '/todos', name: 'todos', component: TodoView },
    { path: '/calendar', name: 'calendar', component: CalendarView },
    { path: '/login', name: 'login', component: LoginView },
    { path: '/user-manage', name: 'user-manage', component: UserManageView },
    { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
  ],
});

// Persist the login key on the URL query so each tab keeps its own session.
router.beforeEach((to) => {
  const key = getAuthKey();
  if (key && !to.query.key) {
    return { path: to.path, query: { ...to.query, key } };
  }
  return true;
});

export default router;
