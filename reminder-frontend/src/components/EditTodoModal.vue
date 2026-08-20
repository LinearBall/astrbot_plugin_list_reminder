<script setup lang="ts">
// Vue机能
import { computed, reactive, ref, watch } from 'vue';
// Naive UI机能
import { CheckFilled, ClearFilled } from "@vicons/material";
import { NButton, NButtonGroup, NDatePicker, NDynamicInput, NDynamicTags, NForm, NFormItem, NIcon, NInput, NModal, NTag } from 'naive-ui';
// 自定义机能
import type { EditTodoPayload, TagCatalogue, Todo } from '@/types.ts';

const props = defineProps<{
  show: boolean
  todo: Todo | null
  me: string
  isAdmin: boolean
  tagCatalogue: TagCatalogue | null
}>()

const emit = defineEmits<{
  close: []
  save: [payload: EditTodoPayload]
}>()

const tagSearch = ref('')

// 内部使用表单副本，避免编辑过程中直接修改父组件的 todo
const form = reactive<{
  content: string
  dueTimeMillis: number | null
  owners: string[]
  tags: string[]
}>({
  content: '',
  dueTimeMillis: null,
  owners: [],
  tags: [],
})

watch(
  () => props.todo, // 监视源
  (todo) => { // 取得新todo以后咋办
    if (todo) {
      // 编辑已有待办
      form.content = todo.content
      // Todo.due_time 兼容秒/毫秒，这里统一转成毫秒给 n-date-picker
      form.dueTimeMillis = todo.due_time > 1e11 ? todo.due_time : todo.due_time * 1000
      form.owners = []
      form.tags = []
    } else {
      //  要创建新待办：默认所有者填自己的 sender_id，标签留空
      form.content = "";
      form.dueTimeMillis = (new Date()).getTime();
      form.owners = props.me ? [props.me] : []
      form.tags = []
    }
  },
  { immediate: true } // 初始化之后立即执行“”取得新todo以后咋办
)

/** 管理员可见的全部标签（去重排序） */
const availableTags = computed<string[]>(() => {
  if (!props.isAdmin || !props.tagCatalogue) return []
  const seen = new Set<string>()
  props.tagCatalogue.users.forEach(u => u.tags.forEach(t => seen.add(t)))
  return Array.from(seen).sort()
})

/** 根据搜索关键字过滤出来的标签 */
const filteredTags = computed<string[]>(() => {
  const q = tagSearch.value.trim().toLowerCase()
  if (!q) return availableTags.value
  return availableTags.value.filter(t => t.toLowerCase().includes(q))
})

/**
 * 点击标签后，把该标签下的所有 owner(sender_id) 合并填入所有者列表
 * @param tag 标签名
 */
function pickTag(tag: string) {
  const senders = props.tagCatalogue?.tag_senders?.[tag] || []
  if (senders.length === 0) return
  form.owners = Array.from(new Set([...senders, ...form.owners.filter(o => !senders.includes(o))]))
}

/** 某个标签下关联的用户数，用于标签浏览展示 */
function tagSenderCount(tag: string) {
  return props.tagCatalogue?.tag_senders?.[tag]?.length ?? 0
}

/**
 * 在可见性发生变化时，emit一个close事件，可以用来挂载回调函数
 * @param show
 */
function handleUpdateShow(show: boolean) {
  if (!show) emit('close')
}

function handleSave() {
  if (!form.content.trim()) return
  if (!form.dueTimeMillis) return
  // 新待办默认未完成
  let completedStatus = props.todo !== null ? props.todo.completed : false;
  if (form.dueTimeMillis > Date.now()) {
    completedStatus = false;
  }

  const isNew = props.todo === null
  emit("save", {
    todo_id: props.todo !== null ? props.todo.todo_id : -1,
    content: form.content.trim(),
    due_time: Math.floor(form.dueTimeMillis / 1000),  // 转换为秒
    completed: completedStatus,
    owners: isNew ? form.owners : undefined,
    tags: isNew ? form.tags : undefined,
  })
}
</script>

<template>
  <n-modal style="max-width: 75vw" preset="card" :title="todo === null ? '新建待办' : '编辑待办'" :show="show" @update:show="handleUpdateShow">
    <n-form>
      <n-form-item label="待办内容">
        <n-input v-model:value="form.content" type="textarea" placeholder="请输入待办内容" />
      </n-form-item>

      <template v-if="todo === null">
        <!-- 只有新建时才能指定所有者与标签；编辑已有待办保持不变 -->
        <n-form-item label="任务所有者">
          <n-dynamic-input v-model:value="form.owners" :on-create="() => ''">
            <template #default="{ value, index }">
              <n-input :value="value" placeholder="输入所有者 sender_id" @update:value="(v) => (form.owners[index] = v)" />
            </template>
          </n-dynamic-input>
        </n-form-item>

        <n-form-item label="任务标签">
          <n-dynamic-tags v-model:value="form.tags" />
        </n-form-item>

        <!-- 管理员可按标签批量填充所有者 -->
        <n-form-item v-if="isAdmin" label="按标签填入所有者">
          <div class="tag-browser">
            <n-input v-model:value="tagSearch" placeholder="搜索标签" clearable />
            <div class="tag-browser-list">
              <n-tag
                v-for="tag in filteredTags"
                :key="tag"
                size="small"
                round
                class="tag-browser-chip"
                @click="pickTag(tag)"
              >
                {{ tag }}（{{ tagSenderCount(tag) }} 人）
              </n-tag>
              <n-text v-if="filteredTags.length === 0" depth="3">暂无标签</n-text>
            </div>
          </div>
        </n-form-item>
      </template>

      <n-form-item label="到期时间">
        <n-date-picker v-model:value="form.dueTimeMillis" type="datetime" clearable />
      </n-form-item>
    </n-form>

    <template #footer>
      <div style="display: flex; justify-content: flex-end;">
        <n-button-group>
          <n-button ghost :bordered="false" type="error" @click="emit('close')">
            <n-icon>
              <ClearFilled />
            </n-icon>
          </n-button>
          <n-button ghost :bordered="false" type="primary" @click="handleSave">
            <n-icon>
              <CheckFilled />
            </n-icon>
          </n-button>
        </n-button-group>
      </div>
    </template>
  </n-modal>
</template>

<style scoped>
.tag-browser {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tag-browser-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.tag-browser-chip {
  cursor: pointer;
}
</style>
