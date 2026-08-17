<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'

import type { Task } from '@/types.ts'
import { checkIfAlreadyLoggedIn, logout, getTasks, delTaskById } from '@/fbApi/apis.ts'
import { NButton, NButtonGroup, NIcon } from "naive-ui"
import { DocumentEdit20Regular, Delete20Regular } from "@vicons/fluent";

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
  const localDate = new Date(date.getTime() - date.getTimezoneOffset() * 60 * 1000);
  // 截取前 19 位：YYYY-MM-DDTHH:mm:ss
  return localDate.toISOString().slice(0, 19);
}

async function handleRemoveTask(taskId: number) {
  delTaskById(taskId).then(res => {
    switch (res.code) {
      case 200:
        break;
      default:
        break;
    }
  });
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
  <div class="container">
    <n-card class="todo-card shadow-edge">
      <template #header>
        <div class="todo-header">
          <div>
            <span class="todo-title">我的待办事项</span>
            <span class="todo-count">{{ tasks.length }} 项任务</span>
          </div>
          <n-button-group>
            <n-button secondary type="primary" @click="refreshTasks">刷新列表</n-button>
            <n-button secondary type="error" @click="handleLogout">退出登录</n-button>
          </n-button-group>
        </div>
      </template>

      <n-empty v-if="tasks.length === 0" description="暂无任务" />

      <n-list v-else>
        <n-list-item v-for="task in tasks" :key="task.task_id">
          <hr />
          <div class="task-item">
            <n-checkbox v-model:checked="task.completed" />
            <div class="task-content">
              <!-- 任务具体内容的文本 -->
              <div class="task-content-text" :class="{ 'is-completed': task.completed }">
                {{ task.content }}
              </div>
              <div class="task-meta">
                <!-- 到期时间 -->
                <n-text depth="3">{{ toLocalISOString(task.due_time) }}</n-text>

                <!-- 完成情况 -->
                <n-text :type="task.completed ? 'success' : 'info'">
                  {{ task.completed ? '已完成' : '待提醒' }}
                </n-text>

                <n-button-group>
                  <!-- 编辑按钮和删除按钮 -->
                  <n-button size="tiny" secondary ghost type="primary" :bordered="false">
                    <n-icon>
                      <DocumentEdit20Regular />
                    </n-icon>
                  </n-button>
                  <n-button size="tiny" secondary ghost type="error" :bordered="false"
                    @click="handleRemoveTask(task.task_id)">
                    <n-icon>
                      <Delete20Regular />
                    </n-icon>
                  </n-button>
                </n-button-group>
              </div>
            </div>
          </div>
        </n-list-item>
      </n-list>
    </n-card>
  </div>
</template>

<style scoped>
.todo-card {
  width: 100%;
  max-width: 70vw;
  align-self: flex-start;
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

.task-content-text {
  font-size: 15px;
  line-height: 1.5;
  word-break: break-word;
}

.task-content-text.is-completed {
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
