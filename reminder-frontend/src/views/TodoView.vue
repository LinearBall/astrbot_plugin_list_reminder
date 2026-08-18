<script setup lang="ts">
// Vue机能
import { onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
// Naive UI机能
import { Delete20Regular, DocumentEdit20Regular } from "@vicons/fluent";
import { LogOutFilled, PlusFilled, RefreshFilled } from "@vicons/material";
import { NButton, NButtonGroup, NCard, NCheckbox, NIcon, NList, NListItem, NText, useMessage } from "naive-ui";
// 自定义机能
import EditTodoModal from '@/components/EditTodoModal.vue';
import { checkIfAlreadyLoggedIn, delTodoById, getTodos, logout, updateTodoById } from '@/fbApi/apis.ts';
import type { EditTodoPayload, Todo } from '@/types.ts';

const router = useRouter()
const message = useMessage();

const todos = ref<Todo[]>([])
const showEditModal = ref(false)
const editingTodo = ref<Todo | null>(null)

async function handleLogout() {
  logout().then(() => {
    router.push('/login')
  });
}

function refreshTodos() {
  getTodos().then(newTodos => {
    todos.value = newTodos;
  })
}

function toLocalISOString(timestamp: number) {
  const date = new Date(timestamp > 1e11 ? timestamp : timestamp * 1000);
  // 由于JS会强行把时间转到UTC-0，因此需要减去时区偏差
  const localDate = new Date(date.getTime() - date.getTimezoneOffset() * 60 * 1000);
  // 截取前 19 位：YYYY-MM-DDTHH:mm:ss
  return localDate.toISOString().slice(0, 19);
}

async function handleRemoveTodo(todoId: number) {
  delTodoById(todoId).then(res => {
    switch (res.code) {
      case 200:
        message.success("成功删除待办");
        refreshTodos();
        break;
      default:
        message.error(`删除失败(${res.code}): \n${res.payload["message"]}`);
        break;
    }
  });
}
/**
 * 打开编辑待办的Modal
 * @param todo 要编辑的待办，若为null则表示创建新待办
 */
function openEditModal(todo: Todo | null) {
  editingTodo.value = todo
  showEditModal.value = true
}

function closeEditModal() {
  showEditModal.value = false
  editingTodo.value = null
}

/**
 * 将需要更新的待办的信息发回后端去更新，然后关闭Modal
 * @param payload 要更新的待办的具体信息
 */
async function handleEditSaved(payload: EditTodoPayload) {
  updateTodoById(payload).then(res => {
    if (res.code === 200) {
      closeEditModal()
      refreshTodos()
    } else {
      message.error(`${payload.todo_id === -1 ? "创建" : "更新"}待办失败(${res.code}): \n${res.payload["message"]}`)
    }
  });
}

async function handleCompletionStatus(curTodo: Todo) {
  let payload: EditTodoPayload = {
    todo_id: curTodo.todo_id,
    content: curTodo.content,
    due_time: curTodo.due_time,
    completed: curTodo.completed
  }
  updateTodoById(payload).then(res => {
    if (res.code === 200) {
      refreshTodos();
    } else {
      message.error(`更新待办失败(${res.code}): \n${res.payload["message"]}`)
    }
  });
}

onMounted(async () => {
  // 检查是否已登录，若否，则跳转到登录页
  let isAlready = await checkIfAlreadyLoggedIn();
  if (isAlready === null) {
    router.push("/login");  // * 通过这个实现跳转
  }
  refreshTodos();
});
</script>

<template>
  <div class="container">
    <n-card class="todo-card shadow-edge">
      <template #header>
        <div class="todo-header">
          <div>
            <span class="todo-title">我的待办事项</span>
            <span class="todo-count">{{ todos.length }} 项待办</span>
          </div>
          <n-button-group>
            <n-button ghost :bordered="false" type="primary" @click="openEditModal(null)">
              <n-icon>
                <PlusFilled />
              </n-icon>
            </n-button>
            <n-button ghost :bordered="false" type="primary" @click="refreshTodos">
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

      <n-empty v-if="todos.length === 0" description="暂无待办" />

      <n-list v-else>
        <n-list-item v-for="todo in todos" :key="todo.todo_id">
          <div class="todo-item">
            <n-checkbox v-model:checked="todo.completed" @update:checked="handleCompletionStatus(todo)" />
            <div class="todo-content">
              <!-- 待办具体内容的文本 -->
              <div class="todo-content-text" :class="{ 'is-completed': todo.completed }">
                {{ todo.content }}
              </div>
              <div class="todo-meta">
                <!-- 到期时间 -->
                <n-text depth="3">{{ toLocalISOString(todo.due_time) }}</n-text>

                <!-- 完成情况 -->
                <n-text :type="todo.completed ? 'success' : 'info'">
                  {{ todo.completed ? '已完成' : '待提醒' }}
                </n-text>

                <n-button-group>
                  <!-- 编辑按钮和删除按钮 -->
                  <n-button size="tiny" ghost type="primary" :bordered="false" @click="openEditModal(todo)">
                    <n-icon>
                      <DocumentEdit20Regular />
                    </n-icon>
                  </n-button>
                  <n-button size="tiny" ghost type="error" :bordered="false" @click="handleRemoveTodo(todo.todo_id)">
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

    <EditTodoModal :show="showEditModal" :todo="editingTodo" @close="closeEditModal" @save="handleEditSaved" />
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

.todo-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 4px 0;
}

.todo-content {
  flex: 1;
  min-width: 0;
}

.todo-content-text {
  font-size: 15px;
  line-height: 1.5;
  word-break: break-word;
}

.todo-content-text.is-completed {
  text-decoration: line-through;
  color: #8a919f;
}

.todo-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 2px;
  font-size: 13px;
}
</style>
