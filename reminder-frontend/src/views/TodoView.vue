<script setup lang="ts">
// Vue机能
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
// Naive UI机能
import { Delete20Regular, DocumentEdit20Regular } from '@vicons/fluent';
import { PlusFilled } from '@vicons/material';
import {
  NButton,
  NCheckbox,
  NEmpty,
  NIcon,
  NInput,
  NSelect,
  useMessage,
} from 'naive-ui';
// 自定义机能
import EditTodoModal from '@/components/EditTodoModal.vue';
import { checkIfAlreadyLoggedIn, delTodoById, updateTodoById } from '@/fbApi/apis.ts';
import { useStore } from '@/composables/useStore';
import { formatDateTime } from '@/utils/date';
import type { EditTodoPayload, Todo } from '@/types.ts';

const router = useRouter();
const message = useMessage();
const { state, init, refreshTodos, nicknameOf } = useStore();

const showEditModal = ref(false);
const editingTodo = ref<Todo | null>(null);
const nicknameFilter = ref('');
const tagFilter = ref<string | null>(null);
const statusFilter = ref<'all' | 'pending' | 'done'>('all');

const availableTags = computed(() => {
  const tags = new Set<string>();
  state.todos.forEach((t) => t.tags.forEach((tag) => tags.add(tag)));
  return Array.from(tags).sort().map((tag) => ({ label: tag, value: tag }));
});

const filteredTodos = computed(() => {
  const nick = nicknameFilter.value.trim().toLowerCase();
  return state.todos.filter((t) => {
    if (statusFilter.value === 'done' && !t.completed) return false;
    if (statusFilter.value === 'pending' && t.completed) return false;
    if (tagFilter.value && !t.tags.includes(tagFilter.value)) return false;
    if (nick && !nicknameOf(t.creator).toLowerCase().includes(nick) && !t.content.toLowerCase().includes(nick) && !t.tags.some(tag => tag.toLowerCase().includes(nick))) return false;
    return true;
  });
});

/**
 * Open the edit modal.
 *
 * @param todo The todo to edit, or null to create a new one.
 */
function openEditModal(todo: Todo | null) {
  editingTodo.value = todo;
  showEditModal.value = true;
}

function closeEditModal() {
  showEditModal.value = false;
  editingTodo.value = null;
}

/**
 * Persist a created/edited todo and close the modal.
 *
 * @param payload The edit form payload.
 */
async function handleEditSaved(payload: EditTodoPayload) {
  const res = await updateTodoById(payload);
  if (res.code === 200) {
    closeEditModal();
    refreshTodos();
    message.success(`${payload.todo_id === -1 ? '创建' : '更新'}待办成功`);
  } else {
    message.error(`${payload.todo_id === -1 ? '创建' : '更新'}待办失败(${res.code}):\n${res.payload['message']}`);
  }
}

async function handleRemoveTodo(todoId: number) {
  const res = await delTodoById(todoId);
  if (res.code === 200) {
    message.success('成功删除待办');
    refreshTodos();
  } else {
    message.error(`删除失败(${res.code}):\n${res.payload['message']}`);
  }
}

/**
 * Flip the completion status of a todo.
 *
 * @param todo The todo to toggle.
 */
async function handleToggleComplete(todo: Todo) {
  const payload: EditTodoPayload = {
    todo_id: todo.todo_id,
    content: todo.content,
    due_time: todo.due_time,
    completed: todo.completed,
  };
  const res = await updateTodoById(payload);
  if (res.code === 200) {
    refreshTodos();
  } else {
    message.error(`更新待办失败(${res.code}):\n${res.payload['message']}`);
  }
}

onMounted(async () => {
  await init();
  if (!(await checkIfAlreadyLoggedIn())) {
    router.push('/login');
  }
});
</script>

<template>
  <div class="page">
    <div class="page-header todo-header">
      <div>
        <h1 class="page-title">待办列表</h1>
        <p class="page-subtitle">高效管理你的所有待办事项</p>
      </div>
      <NButton type="primary" size="large" @click="openEditModal(null)">
        <template #icon>
          <NIcon><PlusFilled /></NIcon>
        </template>
        新建待办
      </NButton>
    </div>

    <div class="toolbar-card">
      <NInput
        v-model:value="nicknameFilter"
        clearable
        placeholder="搜索待办内容、标签或所有者..."
        clearable-on-mousedown
      />
      <NSelect
        v-model:value="tagFilter"
        clearable
        placeholder="所有标签"
        :options="availableTags"
        consistent-menu-width
      />
      <NSelect
        v-model:value="statusFilter"
        :options="[
          { label: '所有状态', value: 'all' },
          { label: '进行中', value: 'pending' },
          { label: '已完成', value: 'done' },
        ]"
        consistent-menu-width
      />
    </div>

    <div class="table-card">
      <NEmpty v-if="filteredTodos.length === 0" description="暂无待办" style="padding: 48px" />
      <table v-else>
        <thead>
          <tr>
            <th style="width: 44px"></th>
            <th>待办内容</th>
            <th>标签</th>
            <th>状态</th>
            <th>到期时间</th>
            <th>所有者</th>
            <th style="width: 100px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="todo in filteredTodos" :key="todo.todo_id">
            <td>
              <NCheckbox
                :checked="todo.completed"
                @update:checked="handleToggleComplete(todo)"
              />
            </td>
            <td>
              <div class="todo-title" :class="{ done: todo.completed }">{{ todo.content }}</div>
            </td>
            <td>
              <span v-if="todo.tags.length === 0" class="muted">—</span>
              <div v-else class="tag-list">
                <span v-for="tag in todo.tags" :key="tag" class="tag-chip">{{ tag }}</span>
              </div>
            </td>
            <td>
              <span class="badge" :class="todo.completed ? 'badge-s' : 'badge-w'">
                {{ todo.completed ? '已完成' : '进行中' }}
              </span>
            </td>
            <td class="muted">{{ formatDateTime(todo.due_time) }}</td>
            <td>{{ nicknameOf(todo.creator) }}</td>
            <td>
              <NButton size="tiny" quaternary type="primary" @click="openEditModal(todo)">
                <template #icon><NIcon><DocumentEdit20Regular /></NIcon></template>
              </NButton>
              <NButton size="tiny" quaternary type="error" @click="handleRemoveTodo(todo.todo_id)">
                <template #icon><NIcon><Delete20Regular /></NIcon></template>
              </NButton>
            </td>
          </tr>
        </tbody>
      </table>
      <div class="table-footer">
        <span>显示 1 - {{ filteredTodos.length }} 条，共 {{ filteredTodos.length }} 条待办</span>
      </div>
    </div>

    <EditTodoModal
      :show="showEditModal"
      :todo="editingTodo"
      :me="state.me"
      :is-admin="state.isAdmin"
      :tag-catalogue="state.tagCatalogue"
      @close="closeEditModal"
      @save="handleEditSaved"
    />
  </div>
</template>

<style scoped>
.todo-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  flex-wrap: wrap;
  gap: 16px;
}

.toolbar-card {
  background: #fff;
  border-radius: var(--radius);
  padding: 18px 22px;
  box-shadow: var(--shadow-lg);
  margin-bottom: 20px;
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}

.toolbar-card :deep(.n-input) {
  flex: 1;
  min-width: 220px;
}

.toolbar-card :deep(.n-base-selection) {
  min-width: 150px;
}

.table-card {
  background: #fff;
  border-radius: var(--radius);
  box-shadow: var(--shadow-lg);
  overflow: hidden;
}

table {
  width: 100%;
  border-collapse: collapse;
}

thead {
  background: var(--g50);
}

th {
  padding: 14px 22px;
  text-align: left;
  font-size: 13px;
  font-weight: 700;
  color: var(--g600);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  border-bottom: 2px solid var(--g200);
}

td {
  padding: 14px 22px;
  border-bottom: 1px solid var(--g100);
  font-size: 14px;
  vertical-align: middle;
}

tbody tr:hover {
  background: var(--g50);
}

tbody tr:last-child td {
  border-bottom: none;
}

.todo-title {
  font-weight: 600;
  color: var(--g900);
  font-size: 15px;
}

.todo-title.done {
  text-decoration: line-through;
  color: var(--g400);
  font-weight: 500;
}

.muted {
  color: var(--g400);
  font-size: 13px;
}

.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.tag-chip {
  padding: 2px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
  background: var(--primary-bg);
  color: var(--primary);
}

.badge {
  display: inline-block;
  padding: 4px 14px;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 600;
}

.badge-s {
  background: var(--success-bg);
  color: var(--success);
}

.badge-w {
  background: var(--warning-bg);
  color: #b45309;
}

.table-footer {
  padding: 14px 22px;
  background: var(--g50);
  border-top: 1px solid var(--g100);
  font-size: 14px;
  color: var(--g500);
}

@media (max-width: 768px) {
  .todo-header {
    flex-direction: column;
    align-items: stretch;
  }

  .todo-header .n-button {
    width: 100%;
  }

  .toolbar-card {
    flex-direction: column;
    align-items: stretch;
    padding: 14px;
    gap: 10px;
  }

  .toolbar-card :deep(.n-input) {
    min-width: 0;
  }

  .toolbar-card :deep(.n-base-selection) {
    min-width: 0;
    width: 100%;
  }

  .table-card {
    border-radius: var(--radius-sm);
  }

  table {
    display: block;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }

  th,
  td {
    padding: 10px 14px;
    font-size: 13px;
    white-space: nowrap;
  }

  .todo-title {
    font-size: 14px;
    max-width: 200px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .table-footer {
    padding: 12px 14px;
    font-size: 12px;
  }
}
</style>
