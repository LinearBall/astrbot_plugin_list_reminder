<script setup lang="ts">
// Vue机能
import { computed, onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
// Naive UI机能
import { Delete20Regular, DocumentEdit20Regular } from "@vicons/fluent";
import { LogOutFilled, PlusFilled, RefreshFilled, ManageAccountsFilled } from "@vicons/material";
import { NButton, NButtonGroup, NCard, NCheckbox, NEmpty, NIcon, NInput, NList, NListItem, NSelect, NTag, NText, useMessage } from "naive-ui";
// 自定义机能
import EditTodoModal from '@/components/EditTodoModal.vue';
import { checkIfAlreadyLoggedIn, delTodoById, getTagCatalogue, getTodos, logout, toggleAdmin, updateTodoById } from '@/fbApi/apis.ts';
import type { EditTodoPayload, TagCatalogue, Todo } from '@/types.ts';

const router = useRouter()
const message = useMessage();

const todos = ref<Todo[]>([])
const showEditModal = ref(false)
const editingTodo = ref<Todo | null>(null)
const isAdmin = ref(false)
const meSenderId = ref('')
const tagCatalogue = ref<TagCatalogue | null>(null)
const myNickname = ref('')
const editingNickname = ref(false)
// 用户详情弹窗
const nicknameFilter = ref('')
const tagFilter = ref<string | null>(null)
const showUncompleted = ref(true)
const showCompleted = ref(false)

/** sender_id -> 昵称 映射，用于任务列表等处展示昵称 */
const nicknameMap = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {}
  tagCatalogue.value?.users.forEach(u => { map[u.sender_id] = u.nickname || u.sender_id })
  return map
})

function nicknameOf(senderId: string) {
  return nicknameMap.value[senderId] || senderId
}

const availableTodoTags = computed(() => {
  const tags = new Set<string>()
  todos.value.forEach(todo => todo.tags.forEach(tag => tags.add(tag)))
  return Array.from(tags).sort().map(tag => ({ label: tag, value: tag }))
})

const filteredTodos = computed(() => {
  const nickname = nicknameFilter.value.trim().toLowerCase()
  const tag = tagFilter.value
  return todos.value.filter(todo => {
    if (!showUncompleted.value && !todo.completed) return false
    if (!showCompleted.value && todo.completed) return false
    if (tag && !todo.tags.includes(tag)) return false
    if (nickname && !nicknameOf(todo.creator).toLowerCase().includes(nickname)) return false
    return true
  })
})

/** 自己的昵称随标签目录同步变化，保证输入框显示最新值 */
watch(
  () => tagCatalogue.value?.users.find(u => u.sender_id === meSenderId.value)?.nickname,
  (nick) => {
    if (nick !== undefined) myNickname.value = nick
  }
)

async function handleLogout() {
  logout().then(() => {
    router.push('/login')
  });
}

function refreshTodos() {
  getTodos().then(newTodos => {
    todos.value = newTodos;
    if (tagFilter.value && !availableTodoTags.value.some(option => option.value === tagFilter.value)) {
      tagFilter.value = null
    }
  })
}

function refreshTags() {
  getTagCatalogue().then(cat => {
    tagCatalogue.value = cat
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

async function handleToggleAdmin() {
  toggleAdmin()
    .then((res) => {
      if (res.code === 200) {
        isAdmin.value = !!res.payload["is_admin"];
        message.success(res.payload["message"]);
        refreshTodos();
        refreshTags();
      } else {
        message.error(res.payload["message"] || "操作失败");
      }
    })
    .catch((err) => {
      console.error(err);
      message.error("操作失败，请稍后重试");
    });
}

onMounted(async () => {
  // 检查是否已登录，若否，则跳转到登录页
  let me = await checkIfAlreadyLoggedIn();
  if (me === null) {
    router.push("/login");  // * 通过这个实现跳转
  }
  meSenderId.value = me ? me.sender_id : '';
  isAdmin.value = me ? me.is_admin : false;
  refreshTodos();
  refreshTags();
});
</script>

<template>
  <div class="container">
    <n-card class="card-inner shadow-edge">
      <template #header>
        <div class="card-header">
          <div>
            <span class="card-title">我的待办事项</span>
            <span class="card-count">{{ filteredTodos.length }} / {{ todos.length }} 项待办</span>
            <span class="todo-owner">当前账号：{{ meSenderId }}</span>
          </div>
          <div class="card-actions">
            <n-button ghost :bordered="false" :type="isAdmin ? 'warning' : 'primary'" @click="handleToggleAdmin">
              {{ isAdmin ? '关闭管理员权限' : '开启管理员权限' }}
            </n-button>
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
              <n-button ghost :bordered="false" type="info" @click="router.push('/user-manage')">
                <n-icon>
                  <ManageAccountsFilled />
                </n-icon>
              </n-button>
              <n-button ghost :bordered="false" type="error" @click="handleLogout">
                <n-icon>
                  <LogOutFilled />
                </n-icon>
              </n-button>
            </n-button-group>
          </div>
        </div>
      </template>

      <div class="todo-filters">
        <n-input v-model:value="nicknameFilter" size="small" clearable placeholder="按昵称筛选" />
        <n-select v-model:value="tagFilter" size="small" clearable placeholder="按标签筛选" :options="availableTodoTags" />
        <n-button size="small" ghost :type="showUncompleted ? 'primary' : 'default'"
          @click="showUncompleted = !showUncompleted">
          {{ showUncompleted ? '隐藏未完成' : '显示未完成' }}
        </n-button>
        <n-button size="small" ghost :type="showCompleted ? 'success' : 'default'"
          @click="showCompleted = !showCompleted">
          {{ showCompleted ? '隐藏已完成' : '显示已完成' }}
        </n-button>
      </div>

      <n-empty v-if="filteredTodos.length === 0" description="暂无待办" />

      <n-list v-else>
        <n-list-item v-for="todo in filteredTodos" :key="todo.todo_id">
          <div class="todo-item">
            <n-checkbox v-model:checked="todo.completed" @update:checked="handleCompletionStatus(todo)" />
            <div class="todo-content">
              <!-- 待办具体内容的文本 -->
              <div class="todo-content-text" :class="{ 'is-completed': todo.completed }">
                {{ todo.content }}
              </div>
              <div class="todo-tags" v-if="todo.tags.length > 0">
                <n-tag v-for="tag in todo.tags" :key="tag" size="small" round>{{ tag }}</n-tag>
              </div>
              <div class="todo-meta">
                <!-- 任务所有者（显示昵称） -->
                <n-text depth="3">所有者：{{ nicknameOf(todo.creator) }}</n-text>

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

    <EditTodoModal :show="showEditModal" :todo="editingTodo" :me="meSenderId" :is-admin="isAdmin"
      :tag-catalogue="tagCatalogue" @close="closeEditModal" @save="handleEditSaved" />
  </div>
</template>

<style scoped>
.todo-filters {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.todo-filters .n-input,
.todo-filters .n-select {
  max-width: 180px;
}

.todo-owner {
  margin-left: 12px;
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

.todo-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 4px;
}

.todo-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 4px;
  font-size: 13px;
}
</style>
