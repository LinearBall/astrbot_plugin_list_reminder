<script setup lang="ts">
// Vue机能
import { onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
// Naive UI机能
import { Delete20Regular, DocumentEdit20Regular } from "@vicons/fluent";
import { LogOutFilled, PlusFilled, RefreshFilled } from "@vicons/material";
import { NButton, NButtonGroup, NCard, NCheckbox, NIcon, NList, NListItem, NText, useMessage } from "naive-ui";
// 自定义机能
import EditTaskModal from '@/components/EditTaskModal.vue';
import { checkIfAlreadyLoggedIn, delTaskById, getTasks, logout, updateTaskById } from '@/fbApi/apis.ts';
import type { EditTaskPayload, Task } from '@/types.ts';

const router = useRouter()
const message = useMessage();

const tasks = ref<Task[]>([])
const showEditModal = ref(false)
const editingTask = ref<Task | null>(null)

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
  // 由于JS会强行把时间转到UTC-0，因此需要减去时区偏差
  const localDate = new Date(date.getTime() - date.getTimezoneOffset() * 60 * 1000);
  // 截取前 19 位：YYYY-MM-DDTHH:mm:ss
  return localDate.toISOString().slice(0, 19);
}

async function handleRemoveTask(taskId: number) {
  delTaskById(taskId).then(res => {
    switch (res.code) {
      case 200:
        message.success("成功删除任务");
        refreshTasks();
        break;
      default:
        message.error(`删除失败(${res.code}): \n${res.payload}`);
        break;
    }
  });
}
/**
 * 打开编辑任务的Modal
 * @param task 要编辑的任务，若为null则表示创建新任务
 */
function openEditModal(task: Task | null) {
  editingTask.value = task
  showEditModal.value = true
}

function closeEditModal() {
  showEditModal.value = false
  editingTask.value = null
}

/**
 * 将需要更新的任务的信息发回后端去更新，然后关闭Modal
 * @param payload 要更新的任务的具体信息
 */
async function handleEditSaved(payload: EditTaskPayload) {
  updateTaskById(payload).then(res => {
    if (res.code === 200) {
      closeEditModal()
      refreshTasks()
    } else {
      message.error(`${payload.task_id === -1 ? "创建" : "更新"}任务失败(${res.code}): \n${res.payload}`)
    }
  });
}

async function handleCompletionStatus(curTask: Task) {
  let payload: EditTaskPayload = {
    task_id: curTask.task_id,
    content: curTask.content,
    due_time: curTask.due_time,
    completed: curTask.completed
  }
  updateTaskById(payload).then(res => {
    if (res.code === 200) {
      refreshTasks();
    } else {
      message.error(`更新任务失败(${res.code}): \n${res.payload}`)
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
            <n-button ghost :bordered="false" type="primary" @click="openEditModal(null)">
              <n-icon>
                <PlusFilled />
              </n-icon>
            </n-button>
            <n-button ghost :bordered="false" type="primary" @click="refreshTasks">
              <n-icon>
                <RefreshFilled />
              </n-icon>
            </n-button>
            <n-button ghost :bordered="false" type="error" @click="handleLogout">
              <n-icon>
                <LogOutFilled />
              </n-icon>
            </n-button>
          </n-button-group>
        </div>
      </template>

      <n-empty v-if="tasks.length === 0" description="暂无任务" />

      <n-list v-else>
        <n-list-item v-for="task in tasks" :key="task.task_id">
          <hr />
          <div class="task-item">
            <n-checkbox v-model:checked="task.completed" @update:checked="handleCompletionStatus(task)" />
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
                  <n-button size="tiny" ghost type="primary" :bordered="false" @click="openEditModal(task)">
                    <n-icon>
                      <DocumentEdit20Regular />
                    </n-icon>
                  </n-button>
                  <n-button size="tiny" ghost type="error" :bordered="false" @click="handleRemoveTask(task.task_id)">
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

    <EditTaskModal :show="showEditModal" :task="editingTask" @close="closeEditModal" @save="handleEditSaved" />
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
