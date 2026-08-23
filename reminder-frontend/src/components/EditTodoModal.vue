<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';
import {
  NButton,
  NDatePicker,
  NDynamicTags,
  NForm,
  NFormItem,
  NInput,
  NModal,
  NTag,
  NText,
} from 'naive-ui';

import type { EditTodoPayload, TagCatalogue, Todo } from '@/types.ts';

const props = defineProps<{
  show: boolean;
  todo: Todo | null;
  me: string;
  isAdmin: boolean;
  tagCatalogue: TagCatalogue | null;
}>();

const emit = defineEmits<{
  close: [];
  save: [payload: EditTodoPayload];
}>();

const tagSearch = ref('');

const form = reactive<{
  content: string;
  dueTimeMillis: number | null;
  owners: string[];
  tags: string[];
}>({
  content: '',
  dueTimeMillis: null,
  owners: [],
  tags: [],
});

watch(
  () => props.todo,
  (todo) => {
    if (todo) {
      form.content = todo.content;
      form.dueTimeMillis =
        todo.due_time > 1e11 ? todo.due_time : todo.due_time * 1000;
      form.owners = [todo.creator];
      form.tags = [...todo.tags];
    } else {
      form.content = '';
      form.dueTimeMillis = Date.now();
      form.owners = props.me ? [props.me] : [];
      form.tags = [];
    }
  },
  { immediate: true },
);

const availableTags = computed<string[]>(() => {
  if (!props.isAdmin || !props.tagCatalogue) return [];
  const seen = new Set<string>();
  props.tagCatalogue.users.forEach((u) =>
    u.tags.forEach((t) => seen.add(t)),
  );
  return Array.from(seen).sort();
});

const filteredTags = computed<string[]>(() => {
  const q = tagSearch.value.trim().toLowerCase();
  if (!q) return availableTags.value;
  return availableTags.value.filter((t) => t.toLowerCase().includes(q));
});

function pickTag(tag: string) {
  const senders = props.tagCatalogue?.tag_senders?.[tag] || [];
  if (senders.length === 0) return;
  form.owners = Array.from(
    new Set([
      ...senders,
      ...form.owners.filter((o) => !senders.includes(o)),
    ]),
  );
}

function tagSenderCount(tag: string) {
  return props.tagCatalogue?.tag_senders?.[tag]?.length ?? 0;
}

function handleUpdateShow(show: boolean) {
  if (!show) emit('close');
}

function handleSave() {
  if (!form.content.trim()) return;
  if (!form.dueTimeMillis) return;

  let completedStatus =
    props.todo !== null ? props.todo.completed : false;
  if (form.dueTimeMillis > Date.now()) {
    completedStatus = false;
  }

  emit('save', {
    todo_id: props.todo !== null ? props.todo.todo_id : -1,
    content: form.content.trim(),
    due_time: Math.floor(form.dueTimeMillis / 1000),
    completed: completedStatus,
    owners: form.owners
      .map((owner) => owner.trim())
      .filter((owner) => owner.length > 0),
    tags: form.tags,
  });
}
</script>

<template>
  <NModal
    :show="show"
    preset="card"
    :title="todo === null ? '✨ 新建待办' : '✏️ 编辑待办'"
    :bordered="false"
    style="max-width: 560px"
    :style="{ width: '92vw' }"
    @update:show="handleUpdateShow"
  >
    <NForm label-placement="top" class="todo-form">
      <NFormItem label="待办内容">
        <NInput
          v-model:value="form.content"
          type="textarea"
          placeholder="请输入待办内容..."
          :autosize="{ minRows: 2, maxRows: 5 }"
        />
      </NFormItem>

      <NFormItem label="到期时间">
        <NDatePicker
          v-model:value="form.dueTimeMillis"
          type="datetime"
          clearable
          style="width: 100%"
        />
      </NFormItem>

      <NFormItem label="任务标签">
        <NDynamicTags v-model:value="form.tags" />
      </NFormItem>

      <template v-if="todo === null">
        <NFormItem label="任务所有者">
          <div class="owners-input">
            <NInput
              v-for="(_, index) in form.owners"
              :key="index"
              :value="form.owners[index]"
              placeholder="输入所有者 sender_id"
              @update:value="(v) => (form.owners[index] = v)"
            >
              <template #suffix>
                <NButton
                  size="tiny"
                  quaternary
                  type="error"
                  @click="form.owners.splice(index, 1)"
                >
                  ×
                </NButton>
              </template>
            </NInput>
            <NButton size="small" dashed @click="form.owners.push('')">
              + 添加所有者
            </NButton>
          </div>
        </NFormItem>

        <NFormItem v-if="isAdmin" label="按标签快速填入所有者">
          <div class="tag-browser">
            <NInput v-model:value="tagSearch" placeholder="搜索标签..." clearable size="small" />
            <div class="tag-browser-list">
              <NTag
                v-for="tag in filteredTags"
                :key="tag"
                size="small"
                round
                class="tag-browser-chip"
                @click="pickTag(tag)"
              >
                {{ tag }}（{{ tagSenderCount(tag) }} 人）
              </NTag>
              <NText v-if="filteredTags.length === 0" depth="3" style="font-size: 13px">
                暂无标签
              </NText>
            </div>
          </div>
        </NFormItem>
      </template>

      <NFormItem v-else label="所有者">
        <NInput v-model:value="form.owners[0]" placeholder="输入任务所有者 sender_id" />
      </NFormItem>
    </NForm>

    <template #footer>
      <div class="modal-footer">
        <NButton quaternary size="large" @click="emit('close')">取消</NButton>
        <NButton type="primary" size="large" @click="handleSave">
          {{ todo === null ? '创建待办' : '保存修改' }}
        </NButton>
      </div>
    </template>
  </NModal>
</template>

<style scoped>
.todo-form {
  gap: 4px;
}

.owners-input {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

.tag-browser {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.tag-browser-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  max-height: 120px;
  overflow-y: auto;
  padding: 4px 0;
}

.tag-browser-chip {
  cursor: pointer;
  transition: transform 0.15s, box-shadow 0.15s;
}

.tag-browser-chip:hover {
  transform: translateY(-1px);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1);
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
</style>