<script setup lang="ts">
// Vue机能
import { computed, onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
// Naive UI机能
import { Delete20Regular, DocumentEdit20Regular } from "@vicons/fluent";
import { LogOutFilled, PlusFilled, RefreshFilled } from "@vicons/material";
import { NButton, NButtonGroup, NCard, NCheckbox, NDescriptions, NDescriptionsItem, NDynamicTags, NEmpty, NIcon, NInput, NList, NListItem, NModal, NSelect, NTag, NText, useMessage } from "naive-ui";
// 自定义机能
import EditTodoModal from '@/components/EditTodoModal.vue';
import { addUserTag, checkIfAlreadyLoggedIn, delTodoById, getTagCatalogue, getTodos, getUserDetail, logout, removeUserTag, toggleAdmin, updateOwnNickname, updateTodoById, updateUserUmo } from '@/fbApi/apis.ts';
import type { EditTodoPayload, TagCatalogue, TagUser, Todo, UserDetail } from '@/types.ts';

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
const showDetail = ref(false)
const detailUser = ref<UserDetail | null>(null)
const editingUmo = ref(false)
const detailUmo = ref('')
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

/** 当前用户昵称的展示值（取不到时回退 sender_id） */
const myDisplayNickname = computed(() => nicknameMap.value[meSenderId.value] || meSenderId.value)

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

const ownTags = computed(() => {
  const me = tagCatalogue.value?.users.find(u => u.sender_id === meSenderId.value)
  return me ? me.tags : []
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

/**
 * Save the umo shown in the user detail modal.
 */
function saveUserUmo() {
  if (!detailUser.value) return
  const user = detailUser.value
  const umo = detailUmo.value.trim()
  if (!umo) {
    message.error("umo不能为空")
    return
  }
  updateUserUmo({ sender_id: user.sender_id, umo }).then(res => {
    if (res.code === 200) {
      user.umo = umo
      editingUmo.value = false
      message.success("umo已更新")
      refreshTags()
    } else {
      message.error(res.payload["message"] || "修改umo失败")
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

/**
 * 保存当前用户自己的昵称
 */
function saveMyNickname() {
  const nick = myNickname.value.trim()
  if (!nick) {
    message.error("昵称不能为空");
    editingNickname.value = false;
    return
  }
  updateOwnNickname(nick).then(res => {
    if (res.code === 200) {
      message.success("昵称已更新");
      editingNickname.value = false;
      refreshTags();
    } else {
      message.error(res.payload["message"] || "修改昵称失败");
    }
  });
}

/**
 * 打开某个用户的详情弹窗（userDB 全部字段 + 标签）
 * @param senderId 目标用户
 */
function openUserDetail(senderId: string) {
  getUserDetail(senderId).then(d => {
    if (!d) {
      message.error("获取用户信息失败");
      return;
    }
    detailUser.value = d
    detailUmo.value = d.umo
    editingUmo.value = false
    showDetail.value = true
  });
}

/**
 * 给指定用户添加标签并刷新目录
 * @param senderId 目标用户
 * @param tag 标签名
 */
function addTagToUser(senderId: string, tag: string) {
  addUserTag(senderId, tag).then(res => {
    if (res.code !== 200) message.error(res.payload["message"] || "添加标签失败");
    refreshTags();
  });
}

/**
 * 给指定用户移除标签并刷新目录
 * @param senderId 目标用户
 * @param tag 标签名
 */
function removeTagFromUser(senderId: string, tag: string) {
  removeUserTag(senderId, tag).then(res => {
    if (res.code !== 200) message.error(res.payload["message"] || "移除标签失败");
    refreshTags();
  });
}

/**
 * 处理某个用户标签集合的新增 / 移除（计算出差异后分别调用接口）
 * @param user 目标用户
 * @param newTags 编辑后的标签数组
 */
function onUserTagsUpdated(newTags: string[], user: TagUser) {
  const oldSet = new Set(user.tags)
  const added = newTags.filter(t => !oldSet.has(t))
  const removed = user.tags.filter(t => !newTags.includes(t))
  added.forEach(t => addTagToUser(user.sender_id, t))
  removed.forEach(t => removeTagFromUser(user.sender_id, t))
}

/**
 * 处理当前用户自己的标签集合变更
 * @param newTags 编辑后的标签数组
 */
function onOwnTagsUpdated(newTags: string[]) {
  const oldSet = new Set(ownTags.value)
  const added = newTags.filter(t => !oldSet.has(t))
  const removed = ownTags.value.filter(t => !newTags.includes(t))
  added.forEach(t => addTagToUser(meSenderId.value, t))
  removed.forEach(t => removeTagFromUser(meSenderId.value, t))
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
    <n-card class="todo-card shadow-edge">
      <template #header>
        <div class="todo-header">
          <div>
            <span class="todo-title">我的待办事项</span>
            <span class="todo-count">{{ filteredTodos.length }} / {{ todos.length }} 项待办</span>
            <span class="todo-owner">当前账号：{{ meSenderId }}</span>
          </div>
          <div class="todo-actions">
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
        <n-button size="small" ghost :type="showUncompleted ? 'primary' : 'default'" @click="showUncompleted = !showUncompleted">
          {{ showUncompleted ? '隐藏未完成' : '显示未完成' }}
        </n-button>
        <n-button size="small" ghost :type="showCompleted ? 'success' : 'default'" @click="showCompleted = !showCompleted">
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

    <!-- 用户管理：普通用户管理自己的昵称与标签，管理员管理所有用户 -->
    <n-card class="tag-card shadow-edge" title="用户管理">
      <!-- 普通用户：仅自己 -->
      <template v-if="!isAdmin">
        <div class="self-panel">
          <div class="user-nick">
            <template v-if="editingNickname">
              <n-input v-model:value="myNickname" size="small" :style="{ width: '200px' }" placeholder="输入新昵称" @keyup.enter="saveMyNickname" @blur="saveMyNickname" />
            </template>
            <template v-else>
              <n-button text type="primary" @click="openUserDetail(meSenderId)">{{ myDisplayNickname }}</n-button>
              <n-button size="tiny" quaternary type="info" @click="editingNickname = true">编辑昵称</n-button>
            </template>
          </div>
          <n-text depth="3" class="nickname-hint">提示：点击昵称查看详情，点“编辑昵称”可修改自己的昵称</n-text>
          <div class="own-tags">
            <n-text depth="2">我的标签</n-text>
            <n-dynamic-tags :value="ownTags" @update:value="onOwnTagsUpdated" />
          </div>
        </div>
      </template>

      <!-- 管理员：所有用户 -->
      <template v-else>
        <n-empty v-if="!tagCatalogue || tagCatalogue.users.length === 0" description="暂无用户" />
        <div v-else class="admin-tag-list">
          <div v-for="user in tagCatalogue.users" :key="user.sender_id" class="tag-row" :class="{ 'is-me': user.sender_id === meSenderId }">
            <div class="user-nick">
              <!-- 自己的昵称：点击看详情，旁边有编辑昵称按钮 -->
              <template v-if="user.sender_id === meSenderId">
                <template v-if="editingNickname">
                  <n-input v-model:value="myNickname" size="small" :style="{ width: '200px' }" placeholder="输入新昵称" @keyup.enter="saveMyNickname" @blur="saveMyNickname" />
                </template>
                <template v-else>
                  <n-button text type="primary" @click="openUserDetail(user.sender_id)">{{ myDisplayNickname }}</n-button>
                  <n-button size="tiny" quaternary type="info" @click="editingNickname = true">编辑昵称</n-button>
                </template>
              </template>
              <!-- 他人昵称点击查看详情 -->
              <template v-else>
                <n-button text type="primary" @click="openUserDetail(user.sender_id)">{{ user.nickname }}</n-button>
                <n-text depth="3" class="sender-hint">({{ user.sender_id }})</n-text>
              </template>
              <n-tag v-if="user.is_admin" size="tiny" type="warning" class="admin-badge">管理员</n-tag>
            </div>
            <n-dynamic-tags :value="user.tags" @update:value="onUserTagsUpdated($event, user)" />
          </div>
          <n-text depth="3" class="nickname-hint">提示：点击昵称查看详情；自己的昵称可点“编辑昵称”修改</n-text>
        </div>
      </template>
    </n-card>

    <EditTodoModal :show="showEditModal" :todo="editingTodo" :me="meSenderId" :is-admin="isAdmin" :tag-catalogue="tagCatalogue" @close="closeEditModal" @save="handleEditSaved" />

    <!-- 用户详情弹窗 -->
    <n-modal v-model:show="showDetail" preset="card" title="用户详情" :style="{ width: '460px' }">
      <n-descriptions v-if="detailUser" :column="1" label-placement="left">
        <n-descriptions-item label="昵称">{{ detailUser.nickname }}</n-descriptions-item>
        <n-descriptions-item label="sender_id">{{ detailUser.sender_id }}</n-descriptions-item>
        <n-descriptions-item label="推送会话 umo">
          <div class="umo-editor">
            <template v-if="editingUmo">
              <n-input v-model:value="detailUmo" size="small" :style="{ width: '260px' }" placeholder="输入新 umo" @keyup.enter="saveUserUmo" />
              <n-button size="tiny" quaternary type="primary" @click="saveUserUmo">保存</n-button>
              <n-button size="tiny" quaternary @click="editingUmo = false">取消</n-button>
            </template>
            <template v-else>
              <n-text>{{ detailUser.umo || '（无）' }}</n-text>
              <n-button size="tiny" quaternary type="info" @click="editingUmo = true">编辑umo</n-button>
            </template>
          </div>
        </n-descriptions-item>
        <n-descriptions-item label="管理员">{{ detailUser.is_admin ? '是' : '否' }}</n-descriptions-item>
        <n-descriptions-item label="用户标签">
          <template v-if="detailUser.tags.length > 0">
            <div class="detail-tags">
              <n-tag v-for="t in detailUser.tags" :key="t" size="small" round>{{ t }}</n-tag>
            </div>
          </template>
          <n-text v-else depth="3">（无）</n-text>
        </n-descriptions-item>
      </n-descriptions>
    </n-modal>
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

.umo-editor {
  display: flex;
  align-items: center;
  gap: 6px;
}

.todo-card,
.tag-card {
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

.todo-actions {
  display: flex;
  align-items: center;
  gap: 8px;
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

.tag-card {
  margin-top: 16px;
}

.self-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.user-nick {
  display: flex;
  align-items: center;
  gap: 8px;
}

.nickname-hint {
  font-size: 12px;
}

.own-tags {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 4px;
}

.tag-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid rgba(128, 128, 128, 0.15);
}

.tag-row:last-child {
  border-bottom: none;
}

.admin-tag-list {
  display: flex;
  flex-direction: column;
}

.sender-hint {
  font-size: 12px;
}

.admin-badge {
  margin-left: 6px;
}

.detail-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
</style>
