<script setup lang="ts">
import { computed, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { NIcon, useMessage } from 'naive-ui';
import { LogOutFilled, MenuFilled } from '@vicons/material';

import { logout } from '@/fbApi/apis';
import { useStore } from '@/composables/useStore';

const router = useRouter();
const route = useRoute();
const message = useMessage();
const { state, toggleAdminMode, reset, nicknameOf } = useStore();
const mobileMenuOpen = ref(false);

const displayName = computed(
  () => nicknameOf(state.me) || state.me,
);
const avatarChar = computed(() =>
  displayName.value.charAt(0).toUpperCase(),
);

async function handleToggleAdmin() {
  try {
    const on = await toggleAdminMode();
    message.success(on ? '已开启管理员权限' : '已关闭管理员权限');
  } catch (e) {
    message.error(e instanceof Error ? e.message : '操作失败，请稍后重试');
  }
}

async function handleLogout() {
  await logout();
  reset();
  router.push('/login');
}

function go(name: string) {
  router.push({ name });
  mobileMenuOpen.value = false;
}

function isActive(name: string): boolean {
  return route.name === name;
}
</script>

<template>
  <nav class="app-navbar">
    <a class="app-brand" @click.prevent="go('dashboard')">
      <span class="logo">📋</span>
      <span class="brand-text">待办事项管理</span>
    </a>

    <div class="app-nav">
      <button class="nav-link" :class="{ active: isActive('dashboard') }" @click="go('dashboard')">
        仪表盘
      </button>
      <button class="nav-link" :class="{ active: isActive('todos') }" @click="go('todos')">
        待办列表
      </button>
      <button class="nav-link" :class="{ active: isActive('calendar') }" @click="go('calendar')">
        任务日历
      </button>
      <button class="nav-link" :class="{ active: isActive('user-manage') }" @click="go('user-manage')">
        用户管理
      </button>
    </div>

    <div class="nav-right">
      <button
        class="admin-toggle"
        :class="{ on: state.isAdmin }"
        :title="state.isAdmin ? '已开启管理员权限，点击关闭' : '点击开启管理员权限'"
        @click="handleToggleAdmin"
      >
        <span class="at-dot" />
        <span class="at-text">{{ state.isAdmin ? '管理员模式' : '个人模式' }}</span>
      </button>
      <button
        class="user-avatar"
        :class="{ active: isActive('user-manage') }"
        title="用户管理"
        @click="go('user-manage')"
      >
        {{ avatarChar }}
      </button>
      <button class="icon-btn-round" title="退出登录" @click="handleLogout">
        <NIcon :size="18"><LogOutFilled /></NIcon>
      </button>
      <button class="mobile-menu-btn" title="菜单" @click="mobileMenuOpen = !mobileMenuOpen">
        <NIcon :size="22"><MenuFilled /></NIcon>
      </button>
    </div>

    <div v-if="mobileMenuOpen" class="mobile-nav">
      <button class="mobile-nav-link" :class="{ active: isActive('dashboard') }" @click="go('dashboard')">
        📊 仪表盘
      </button>
      <button class="mobile-nav-link" :class="{ active: isActive('todos') }" @click="go('todos')">
        📝 待办列表
      </button>
      <button class="mobile-nav-link" :class="{ active: isActive('calendar') }" @click="go('calendar')">
        📅 任务日历
      </button>
      <button class="mobile-nav-link" :class="{ active: isActive('user-manage') }" @click="go('user-manage')">
        👤 用户管理
      </button>
    </div>
  </nav>
</template>