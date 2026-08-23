<script setup lang="ts">
import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';
import { NButton, NDynamicTags, NInput, NPopover, useMessage } from 'naive-ui';

import {
  addUserTag,
  getUserDetail,
  removeUserTag,
  updateOwnNickname,
  updateUserUmo,
} from '@/fbApi/apis';
import { useStore } from '@/composables/useStore';

const router = useRouter();
const message = useMessage();
const { state, refreshTags } = useStore();

const me = computed(() =>
  state.tagCatalogue?.users.find((u) => u.sender_id === state.me),
);
const displayName = computed(() => me.value?.nickname || state.me);
const avatarChar = computed(() => displayName.value.charAt(0).toUpperCase());

const editingNickname = ref(false);
const nicknameDraft = ref('');

/** Switch the nickname field into edit mode. */
function startEditNickname() {
  nicknameDraft.value = me.value?.nickname ?? '';
  editingNickname.value = true;
}

/** Persist the edited nickname and leave edit mode. */
async function saveNickname() {
  const nick = nicknameDraft.value.trim();
  if (!nick) {
    message.error('昵称不能为空');
    return;
  }
  const res = await updateOwnNickname(nick);
  if (res.code === 200) {
    message.success('昵称已更新');
    editingNickname.value = false;
    refreshTags();
  } else {
    message.error(res.payload['message'] || '修改昵称失败');
  }
}

/**
 * Diff the new tag list against the current one and call the add/remove APIs.
 *
 * @param newTags The tag array produced by NDynamicTags.
 */
async function onTagsUpdated(newTags: string[]) {
  const oldTags = me.value?.tags ?? [];
  const added = newTags.filter((t) => !oldTags.includes(t));
  const removed = oldTags.filter((t) => !newTags.includes(t));
  for (const tag of added) {
    const res = await addUserTag(state.me, tag);
    if (res.code !== 200) message.error(res.payload['message'] || '添加标签失败');
  }
  for (const tag of removed) {
    const res = await removeUserTag(state.me, tag);
    if (res.code !== 200) message.error(res.payload['message'] || '移除标签失败');
  }
  refreshTags();
}

const editingUmo = ref(false);
const umoDraft = ref('');

/** Load the current umo from the server and enter edit mode. */
async function startEditUmo() {
  const detail = await getUserDetail(state.me);
  if (!detail) {
    message.error('获取用户信息失败');
    return;
  }
  umoDraft.value = detail.umo;
  editingUmo.value = true;
}

/** Persist the edited umo. */
async function saveUmo() {
  const umo = umoDraft.value.trim();
  if (!umo) {
    message.error('umo 不能为空');
    return;
  }
  const res = await updateUserUmo({ sender_id: state.me, umo });
  if (res.code === 200) {
    message.success('umo 已更新');
    editingUmo.value = false;
    refreshTags();
  } else {
    message.error(res.payload['message'] || '修改 umo 失败');
  }
}
</script>

<template>
  <NPopover trigger="click" placement="bottom-end" :width="300" raw>
    <template #trigger>
      <button class="user-avatar" title="点击设置用户信息">{{ avatarChar }}</button>
    </template>

    <div class="ud-panel">
      <div class="ud-header">
        <div class="ud-avatar">{{ avatarChar }}</div>
        <div>
          <div class="ud-name">{{ displayName }}</div>
          <div class="ud-id">{{ state.me }}</div>
        </div>
      </div>

      <div class="ud-section">
        <div class="ud-label">
          <span>昵称</span>
          <NButton v-if="!editingNickname" size="tiny" quaternary type="primary" @click="startEditNickname">
            编辑
          </NButton>
        </div>
        <div v-if="editingNickname" class="ud-row">
          <NInput
            v-model:value="nicknameDraft"
            size="small"
            placeholder="输入新昵称"
            @keyup.enter="saveNickname"
          />
          <NButton size="small" type="primary" @click="saveNickname">保存</NButton>
        </div>
        <div v-else class="ud-value">{{ me?.nickname || '未设置' }}</div>
      </div>

      <div class="ud-section">
        <div class="ud-label"><span>我的标签</span></div>
        <NDynamicTags
          :value="me?.tags ?? []"
          size="small"
          @update:value="onTagsUpdated"
        />
      </div>

      <div class="ud-section">
        <div class="ud-label">
          <span>推送会话 UMO</span>
          <NButton v-if="!editingUmo" size="tiny" quaternary type="primary" @click="startEditUmo">
            编辑
          </NButton>
        </div>
        <div v-if="editingUmo" class="ud-row">
          <NInput
            v-model:value="umoDraft"
            size="small"
            placeholder="输入新 umo"
            @keyup.enter="saveUmo"
          />
          <NButton size="small" type="primary" @click="saveUmo">保存</NButton>
        </div>
        <div v-else class="ud-value ud-mono">{{ me?.umo || '（无）' }}</div>
      </div>

      <div class="ud-section">
        <div class="ud-label"><span>SENDER ID</span></div>
        <div class="ud-value ud-mono ud-id-value">{{ state.me }}</div>
      </div>

      <NButton
        v-if="state.isAdmin"
          block
          secondary
          size="small"
          @click="router.push('/user-manage')"
        >
          管理所有用户
        </NButton>
    </div>
  </NPopover>
</template>

<style scoped>
.ud-panel {
  background: #fff;
  border-radius: var(--radius);
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.15);
  overflow: hidden;
}

.ud-header {
  padding: 18px;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: #fff;
  display: flex;
  align-items: center;
  gap: 12px;
}

.ud-avatar {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: 700;
  border: 2px solid rgba(255, 255, 255, 0.4);
}

.ud-name {
  font-size: 16px;
  font-weight: 700;
}

.ud-id {
  font-size: 11px;
  opacity: 0.85;
  font-family: monospace;
  margin-top: 2px;
  word-break: break-all;
}

.ud-section {
  padding: 12px 18px;
  border-bottom: 1px solid var(--g100);
}

.ud-section:last-of-type {
  border-bottom: none;
}

.ud-label {
  font-size: 11px;
  font-weight: 700;
  color: var(--g400);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.ud-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.ud-value {
  font-size: 14px;
  color: var(--g800);
  font-weight: 600;
}

.ud-mono {
  font-family: monospace;
  font-weight: 400;
  font-size: 12px;
  word-break: break-all;
}

.ud-id-value {
  color: var(--g500);
}
</style>

