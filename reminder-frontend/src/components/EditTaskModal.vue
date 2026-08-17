<script setup lang="ts">
import { reactive, watch } from 'vue'
import { NModal, NForm, NFormItem, NInput, NDatePicker, NButton } from 'naive-ui'
import type { Task, EditTaskPayload } from '@/types.ts'

const props = defineProps<{
  show: boolean
  task: Task | null
}>()

const emit = defineEmits<{
  close: []
  save: [payload: EditTaskPayload]
}>()

// 内部使用表单副本，避免编辑过程中直接修改父组件的 task
const form = reactive<{
  content: string
  dueTimeMillis: number | null
}>({
  content: '',
  dueTimeMillis: null,
})

watch(
  () => props.task, // 监视源
  (task) => { // 取得新task以后咋办
    if (task) {
      form.content = task.content
      // Task.due_time 兼容秒/毫秒，这里统一转成毫秒给 n-date-picker
      form.dueTimeMillis = task.due_time > 1e11 ? task.due_time : task.due_time * 1000
    }
  },
  { immediate: true } // 初始化之后立即执行“”取得新task以后咋办
)

function handleUpdateShow(show: boolean) {
  if (!show) emit('close')
}

function handleSave() {
  if (!props.task) return
  if (!form.content.trim()) return
  if (!form.dueTimeMillis) return

  emit('save', {
    task_id: props.task.task_id,
    content: form.content.trim(),
    due_time: Math.floor(form.dueTimeMillis / 1000),
  })
}
</script>

<template>
  <n-modal
    preset="card"
    title="编辑任务"
    class="edit-task-modal"
    :show="show"
    @update:show="handleUpdateShow"
  >
    <n-form>
      <n-form-item label="任务内容">
        <n-input
          v-model:value="form.content"
          type="textarea"
          placeholder="请输入任务内容"
        />
      </n-form-item>

      <n-form-item label="到期时间">
        <n-date-picker
          v-model:value="form.dueTimeMillis"
          type="datetime"
          clearable
        />
      </n-form-item>
    </n-form>

    <template #footer>
      <div class="modal-footer">
        <n-button @click="emit('close')">退出而不保存</n-button>
        <n-button type="primary" @click="handleSave">保存并退出</n-button>
      </div>
    </template>
  </n-modal>
</template>

<style scoped>
.edit-task-modal {
  width: 480px;
  max-width: 90vw;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}
</style>
