<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import {
  NButton,
  NDescriptions,
  NDescriptionsItem,
  NDynamicTags,
  NEmpty,
  NInput,
  NModal,
  NTag,
  useMessage,
} from 'naive-ui';

import {
  addUserTag,
  checkIfAlreadyLoggedIn,
  getTagCatalogue,
  getTodos,
  getUserDetail,
  removeUserTag,
  updateOwnNickname,
  updateUserUmo,
} from '@/fbApi/apis.ts';
import type { TagCatalogue, TagUser, Todo, UserDetail } from '@/types.ts';

const router = useRouter();
const message = useMessage();

const todos = ref<Todo[]>([]);
const isAdmin = ref(false);
const meSenderId = ref('');
const tagCatalogue = ref<TagCatalogue | null>(null);
const myNickname = ref('');
const editingNickname = ref(false);
const showDetail = ref(false);
const detailUser = ref<UserDetail | null>(null);
const editingUmo = ref(false);
const detailUmo = ref('');
const tagFilter = ref<string | null>(null);

const nicknameMap = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {};
  tagCatalogue.value?.users.forEach((u) => {
    map[u.sender_id] = u.nickname || u.sender_id;
  });
  return map;
});

const myDisplayNickname = computed(
  () => nicknameMap.value[meSenderId.value] || meSenderId.value,
);

const availableTodoTags = computed(() => {
  const tags = new Set<string>();
  todos.value.forEach((todo) => todo.tags.forEach((tag) => tags.add(tag)));
  return Array.from(tags)
    .sort()
    .map((tag) => ({ label: tag, value: tag }));
});

const ownTags = computed(() => {
  const me = tagCatalogue.value?.users.find(
    (u) => u.sender_id === meSenderId.value,
  );
  return me ? me.tags : [];
});

watch(
  () =>
    tagCatalogue.value?.users.find(
      (u) => u.sender_id === meSenderId.value,
    )?.nickname,
  (nick) => {
    if (nick !== undefined) myNickname.value = nick;
  },
);

function refreshTodos() {
  getTodos().then((newTodos) => {
    todos.value = newTodos;
    if (
      tagFilter.value &&
      !availableTodoTags.value.some(
        (option) => option.value === tagFilter.value,
      )
    ) {
      tagFilter.value = null;
    }
  });
}

function saveUserUmo() {
  if (!detailUser.value) return;
  const user = detailUser.value;
  const umo = detailUmo.value.trim();
  if (!umo) {
    message.error('umo不能为空');
    return;
  }
  updateUserUmo({ sender_id: user.sender_id, umo }).then((res) => {
    if (res.code === 200) {
      user.umo = umo;
      editingUmo.value = false;
      message.success('umo已更新');
      refreshTags();
    } else {
      message.error(res.payload['message'] || '修改umo失败');
    }
  });
}

function refreshTags() {
  getTagCatalogue().then((cat) => {
    tagCatalogue.value = cat;
  });
}

function saveMyNickname() {
  const nick = myNickname.value.trim();
  if (!nick) {
    message.error('昵称不能为空');
    editingNickname.value = false;
    return;
  }
  updateOwnNickname(nick).then((res) => {
    if (res.code === 200) {
      message.success('昵称已更新');
      editingNickname.value = false;
      refreshTags();
    } else {
      message.error(res.payload['message'] || '修改昵称失败');
    }
  });
}

function openUserDetail(senderId: string) {
  getUserDetail(senderId).then((d) => {
    if (!d) {
      message.error('获取用户信息失败');
      return;
    }
    detailUser.value = d;
    detailUmo.value = d.umo;
    editingUmo.value = false;
    showDetail.value = true;
  });
}

function addTagToUser(senderId: string, tag: string) {
  addUserTag(senderId, tag).then((res) => {
    if (res.code !== 200)
      message.error(res.payload['message'] || '添加标签失败');
    refreshTags();
  });
}

function removeTagFromUser(senderId: string, tag: string) {
  removeUserTag(senderId, tag).then((res) => {
    if (res.code !== 200)
      message.error(res.payload['message'] || '移除标签失败');
    refreshTags();
  });
}

function onUserTagsUpdated(newTags: string[], user: TagUser) {
  const oldSet = new Set(user.tags);
  const added = newTags.filter((t) => !oldSet.has(t));
  const removed = user.tags.filter((t) => !newTags.includes(t));
  added.forEach((t) => addTagToUser(user.sender_id, t));
  removed.forEach((t) => removeTagFromUser(user.sender_id, t));
}

function onOwnTagsUpdated(newTags: string[]) {
  const oldSet = new Set(ownTags.value);
  const added = newTags.filter((t) => !oldSet.has(t));
  const removed = ownTags.value.filter((t) => !newTags.includes(t));
  added.forEach((t) => addTagToUser(meSenderId.value, t));
  removed.forEach((t) => removeTagFromUser(meSenderId.value, t));
}

onMounted(async () => {
  const me = await checkIfAlreadyLoggedIn();
  if (me === null) {
    router.push('/login');
  }
  meSenderId.value = me ? me.sender_id : '';
  isAdmin.value = me ? me.is_admin : false;
  refreshTodos();
  refreshTags();
});
</script>

<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h1 class="page-title">用户管理</h1>
        <p class="page-subtitle">
          {{
            isAdmin
              ? '管理所有用户的昵称、标签与推送配置'
              : '管理你的个人信息与标签'
          }}
        </p>
      </div>
      <NButton quaternary @click="router.back()">返回</NButton>
    </div>

    <div v-if="!isAdmin" class="um-card">
      <div class="um-section">
        <div class="um-label">昵称</div>
        <div class="um-nick-row">
          <NInput
            v-if="editingNickname"
            v-model:value="myNickname"
            size="small"
            :style="{ width: '240px' }"
            placeholder="输入新昵称"
            @keyup.enter="saveMyNickname"
            @blur="saveMyNickname"
          />
          <template v-else>
            <NButton text type="primary" @click="openUserDetail(meSenderId)">
              {{ myDisplayNickname }}
            </NButton>
            <NButton
              size="tiny"
              quaternary
              type="info"
              @click="editingNickname = true"
            >
              编辑昵称
            </NButton>
          </template>
        </div>
        <div class="um-hint">点击昵称查看详情，点"编辑昵称"可修改自己的昵称</div>
      </div>
      <div class="um-section">
        <div class="um-label">我的标签</div>
        <NDynamicTags
          :value="ownTags"
          @update:value="onOwnTagsUpdated"
        />
      </div>
    </div>

    <div v-else class="um-card">
      <NEmpty
        v-if="!tagCatalogue || tagCatalogue.users.length === 0"
        description="暂无用户"
        style="padding: 40px"
      />
      <div v-else class="um-user-list">
        <div
          v-for="user in tagCatalogue.users"
          :key="user.sender_id"
          class="um-user-row"
          :class="{ 'is-me': user.sender_id === meSenderId }"
        >
          <div class="um-user-info">
            <div class="um-avatar">
              {{ (user.nickname || user.sender_id).charAt(0).toUpperCase() }}
            </div>
            <div class="um-user-meta">
              <div class="um-user-nick">
                <template v-if="user.sender_id === meSenderId">
                  <NInput
                    v-if="editingNickname"
                    v-model:value="myNickname"
                    size="small"
                    :style="{ width: '200px' }"
                    placeholder="输入新昵称"
                    @keyup.enter="saveMyNickname"
                    @blur="saveMyNickname"
                  />
                  <template v-else>
                    <NButton
                      text
                      type="primary"
                      @click="openUserDetail(user.sender_id)"
                    >
                      {{ myDisplayNickname }}
                    </NButton>
                    <NButton
                      size="tiny"
                      quaternary
                      type="info"
                      @click="editingNickname = true"
                    >
                      编辑
                    </NButton>
                  </template>
                </template>
                <template v-else>
                  <NButton
                    text
                    type="primary"
                    @click="openUserDetail(user.sender_id)"
                  >
                    {{ user.nickname }}
                  </NButton>
                  <span class="um-sender-id">{{ user.sender_id }}</span>
                </template>
                <NTag v-if="user.is_admin" size="tiny" type="warning" round>
                  管理员
                </NTag>
              </div>
            </div>
          </div>
          <div class="um-user-tags">
            <NDynamicTags
              :value="user.tags"
              @update:value="onUserTagsUpdated($event, user)"
            />
          </div>
        </div>
      </div>
      <div class="um-footer-hint">
        点击昵称查看详情；自己的昵称可点"编辑"修改
      </div>
    </div>

    <NModal
      v-model:show="showDetail"
      preset="card"
      title="用户详情"
      :style="{ width: '480px' }"
    >
      <NDescriptions
        v-if="detailUser"
        :column="1"
        label-placement="left"
        bordered
      >
        <NDescriptionsItem label="昵称">
          {{ detailUser.nickname }}
        </NDescriptionsItem>
        <NDescriptionsItem label="sender_id">
          <span class="um-mono">{{ detailUser.sender_id }}</span>
        </NDescriptionsItem>
        <NDescriptionsItem label="推送会话 umo">
          <div class="umo-editor">
            <template v-if="editingUmo">
              <NInput
                v-model:value="detailUmo"
                size="small"
                :style="{ width: '260px' }"
                placeholder="输入新 umo"
                @keyup.enter="saveUserUmo"
              />
              <NButton
                size="tiny"
                quaternary
                type="primary"
                @click="saveUserUmo"
              >
                保存
              </NButton>
              <NButton
                size="tiny"
                quaternary
                @click="editingUmo = false"
              >
                取消
              </NButton>
            </template>
            <template v-else>
              <span class="um-mono">{{ detailUser.umo || '（无）' }}</span>
              <NButton
                size="tiny"
                quaternary
                type="info"
                @click="editingUmo = true"
              >
                编辑umo
              </NButton>
            </template>
          </div>
        </NDescriptionsItem>
        <NDescriptionsItem label="管理员">
          {{ detailUser.is_admin ? '是' : '否' }}
        </NDescriptionsItem>
        <NDescriptionsItem label="用户标签">
          <template v-if="detailUser.tags.length > 0">
            <div class="detail-tags">
              <NTag v-for="t in detailUser.tags" :key="t" size="small" round>
                {{ t }}
              </NTag>
            </div>
          </template>
          <span v-else class="um-muted">（无）</span>
        </NDescriptionsItem>
      </NDescriptions>
    </NModal>
  </div>
</template>

<style scoped>
.um-card {
  background: #fff;
  border-radius: var(--radius);
  box-shadow: var(--shadow-lg);
  overflow: hidden;
}

.um-section {
  padding: 20px 24px;
  border-bottom: 1px solid var(--g100);
}

.um-section:last-child {
  border-bottom: none;
}

.um-label {
  font-size: 13px;
  font-weight: 700;
  color: var(--g600);
  margin-bottom: 10px;
}

.um-nick-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.um-hint {
  font-size: 12px;
  color: var(--g400);
  margin-top: 8px;
}

.um-user-list {
  padding: 8px 0;
}

.um-user-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 24px;
  border-bottom: 1px solid var(--g100);
  transition: background 0.15s;
}

.um-user-row:hover {
  background: var(--g50);
}

.um-user-row:last-child {
  border-bottom: none;
}

.um-user-row.is-me {
  background: var(--primary-bg);
}

.um-user-info {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.um-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 16px;
  flex-shrink: 0;
}

.um-user-meta {
  min-width: 0;
}

.um-user-nick {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.um-sender-id {
  font-size: 12px;
  color: var(--g400);
  font-family: monospace;
}

.um-user-tags {
  flex-shrink: 0;
  max-width: 400px;
}

.um-footer-hint {
  padding: 14px 24px;
  font-size: 12px;
  color: var(--g400);
  background: var(--g50);
  border-top: 1px solid var(--g100);
}

.umo-editor {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.um-mono {
  font-family: monospace;
  font-size: 13px;
  color: var(--g600);
}

.um-muted {
  color: var(--g400);
}

.detail-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

@media (max-width: 768px) {
  .um-user-row {
    flex-direction: column;
    align-items: flex-start;
    padding: 12px 16px;
  }

  .um-user-tags {
    max-width: 100%;
  }

  .um-section {
    padding: 16px;
  }

  .um-card :deep(.n-card) {
    width: 95vw !important;
  }
}
</style>