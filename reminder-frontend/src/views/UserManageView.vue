<script setup lang="ts">
// Vue机能
import { computed, onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
// Naive UI机能
import { NButton, NIcon, NCard, NDescriptions, NDescriptionsItem, NDynamicTags, NEmpty, NInput, NModal, NTag, NText, useMessage } from "naive-ui";
import { ClearFilled } from "@vicons/material";
// 自定义机能
import { addUserTag, checkIfAlreadyLoggedIn, getTagCatalogue, getTodos, getUserDetail, removeUserTag, updateOwnNickname, updateUserUmo } from '@/fbApi/apis.ts';
import type { TagCatalogue, TagUser, Todo, UserDetail } from '@/types.ts';

const router = useRouter()
const message = useMessage();

const todos = ref<Todo[]>([])
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
const tagFilter = ref<string | null>(null)

/** sender_id -> 昵称 映射，用于任务列表等处展示昵称 */
const nicknameMap = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {}
  tagCatalogue.value?.users.forEach(u => { map[u.sender_id] = u.nickname || u.sender_id })
  return map
})

/** 当前用户昵称的展示值（取不到时回退 sender_id） */
const myDisplayNickname = computed(() => nicknameMap.value[meSenderId.value] || meSenderId.value)

const availableTodoTags = computed(() => {
  const tags = new Set<string>()
  todos.value.forEach(todo => todo.tags.forEach(tag => tags.add(tag)))
  return Array.from(tags).sort().map(tag => ({ label: tag, value: tag }))
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
    <!-- 用户管理：普通用户管理自己的昵称与标签，管理员管理所有用户 -->
    <n-card class="card-inner shadow-edge">
      <!-- 标题 -->
      <template #header>
        <div class="card-header">
          <div class="card-title">用户管理</div>
          <div class="card-action">
            <n-button ghost :bordered="false" type="error" @click="router.back()">
              <n-icon>
                <ClearFilled />
              </n-icon>
            </n-button>
          </div>
        </div>
      </template>
      <!-- 普通用户：仅自己 -->
      <template v-if="!isAdmin">
        <div class="self-panel">
          <div class="user-nick">
            <template v-if="editingNickname">
              <n-input v-model:value="myNickname" size="small" :style="{ width: '200px' }" placeholder="输入新昵称"
                @keyup.enter="saveMyNickname" @blur="saveMyNickname" />
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
          <div v-for="user in tagCatalogue.users" :key="user.sender_id" class="tag-row"
            :class="{ 'is-me': user.sender_id === meSenderId }">
            <div class="user-nick">
              <!-- 自己的昵称：点击看详情，旁边有编辑昵称按钮 -->
              <template v-if="user.sender_id === meSenderId">
                <template v-if="editingNickname">
                  <n-input v-model:value="myNickname" size="small" :style="{ width: '200px' }" placeholder="输入新昵称"
                    @keyup.enter="saveMyNickname" @blur="saveMyNickname" />
                </template>
                <template v-else>
                  <n-button text type="primary" @click="openUserDetail(user.sender_id)">{{ myDisplayNickname
                    }}</n-button>
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

    <!-- 用户详情弹窗 -->
    <n-modal v-model:show="showDetail" preset="card" title="用户详情" :style="{ width: '460px' }">
      <n-descriptions v-if="detailUser" :column="1" label-placement="left">
        <n-descriptions-item label="昵称">{{ detailUser.nickname }}</n-descriptions-item>
        <n-descriptions-item label="sender_id">{{ detailUser.sender_id }}</n-descriptions-item>
        <n-descriptions-item label="推送会话 umo">
          <div class="umo-editor">
            <template v-if="editingUmo">
              <n-input v-model:value="detailUmo" size="small" :style="{ width: '260px' }" placeholder="输入新 umo"
                @keyup.enter="saveUserUmo" />
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

.card-inner {
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
