<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'

import type { Task } from '@/types.ts'
import { checkIfAlreadyLoggedIn, logout, getTasks } from '@/fbApi/apis.ts'

const router = useRouter()

// TODO: 后续替换为 GET /api/tasks 的真实数据
const tasks = ref<Task[]>([])

async function handleLogout() {
  logout().then(() => {
    router.push('/login')
  });
}

function refreshTasks() {
  getTasks().then(newTasks => {
    tasks.value = newTasks;
  })
}

function toLocalISOString(timestamp: number) {
  const date = new Date(timestamp > 1e11 ? timestamp : timestamp * 1000);
  // 减去时区偏差
  const localDate = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  // 截取前 19 位：YYYY-MM-DDTHH:mm:ss
  return localDate.toISOString().slice(0, 19);
}

onMounted(async () => {
  // 检查是否已登录，若否，则跳转到登录页
  let isAlready = await checkIfAlreadyLoggedIn();
  if (isAlready === null) {
    router.push("/login");  // * 通过这个实现跳转
  }
  refreshTasks();
});
</script>

<template>
  <div class="todo-page">
    <n-card class="todo-card">
      <template #header>
        <div class="todo-header">
          <div>
            <span class="todo-title">我的待办事项</span>
            <span class="todo-count">{{ tasks.length }} 项任务</span>
          </div>
          <n-button @click="refreshTasks">刷新任务列表</n-button>
          <n-button @click="handleLogout">退出登录</n-button>
        </div>
      </template>

      <n-empty v-if="tasks.length === 0" description="暂无任务" />

      <n-list v-else>
        <n-list-item v-for="task in tasks" :key="task.task_id">
          <div class="task-item">
            <n-checkbox v-model:checked="task.completed" />
            <div class="task-content">
              <div class="task-content__text" :class="{ 'is-completed': task.completed }">
                {{ task.content }}
              </div>
              <div class="task-meta">
                <!-- <n-text depth="3">{{ task.due_time }}</n-text> -->
                <n-text depth="3">{{ toLocalISOString(task.due_time) }}</n-text>
                <n-text :type="task.completed ? 'success' : 'info'">
                  {{ task.completed ? '已完成' : '待提醒' }}
                </n-text>
              </div>
            </div>
          </div>
        </n-list-item>
      </n-list>
    </n-card>
  </div>
</template>

<style scoped>
.todo-page {
  min-height: 100vh;
  display: flex;
  justify-content: center;
  padding: 24px 16px;
  background: linear-gradient(135deg, #f0f9ff 0%, #f8fafc 100%);
}

.todo-card {
  width: 100%;
  max-width: 720px;
  align-self: flex-start;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.06);
}

.todo-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.todo-title {
  font-size: 18px;
  font-weight: 600;
}

.todo-count {
  margin-left: 8px;
  font-size: 13px;
  color: #8a919f;
}

.task-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 4px 0;
}

.task-content {
  flex: 1;
  min-width: 0;
}

.task-content__text {
  font-size: 15px;
  line-height: 1.5;
  word-break: break-word;
}

.task-content__text.is-completed {
  text-decoration: line-through;
  color: #8a919f;
}

.task-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 2px;
  font-size: 13px;
}
</style>
