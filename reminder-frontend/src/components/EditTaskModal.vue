<script setup lang="ts">
// Vue机能
import { reactive, watch } from 'vue';
// Naive UI机能
import { CheckFilled, ClearFilled } from "@vicons/material";
import { NButton, NButtonGroup, NDatePicker, NForm, NFormItem, NIcon, NInput, NModal } from 'naive-ui';
// 自定义机能
import type { EditTaskPayload, Task } from '@/types.ts';

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
      // 编辑已有任务
      form.content = task.content
      // Task.due_time 兼容秒/毫秒，这里统一转成毫秒给 n-date-picker
      form.dueTimeMillis = task.due_time > 1e11 ? task.due_time : task.due_time * 1000
    } else {
      //  要创建新任务
      form.content = "";
      form.dueTimeMillis = (new Date()).getTime();
    }
  },
  { immediate: true } // 初始化之后立即执行“”取得新task以后咋办
)

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
  // 新任务默认未完成
  let completedStatus = props.task !== null ? props.task.completed : false;
  if (form.dueTimeMillis > Date.now()) {
    completedStatus = false;
  }

  emit("save", {
    task_id: props.task !== null ? props.task.task_id : -1,
    content: form.content.trim(),
    due_time: Math.floor(form.dueTimeMillis / 1000),  // 转换为秒
    completed: completedStatus,
  })
}
</script>

<template>
  <n-modal style="max-width: 75vw" preset="card" title="编辑任务" class="edit-task-modal" :show="show"
    @update:show="handleUpdateShow">
    <n-form>
      <n-form-item label="任务内容">
        <n-input v-model:value="form.content" type="textarea" placeholder="请输入任务内容" />
      </n-form-item>

      <n-form-item label="到期时间">
        <n-date-picker v-model:value="form.dueTimeMillis" type="datetime" clearable />
      </n-form-item>
    </n-form>

    <template #footer>
      <div class="modal-footer">
        <!-- todo: 美化 -->
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
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}
</style>
