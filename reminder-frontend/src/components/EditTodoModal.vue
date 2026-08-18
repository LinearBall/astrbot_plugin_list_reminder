<script setup lang="ts">
// Vue机能
import { reactive, watch } from 'vue';
// Naive UI机能
import { CheckFilled, ClearFilled } from "@vicons/material";
import { NButton, NButtonGroup, NDatePicker, NForm, NFormItem, NIcon, NInput, NModal } from 'naive-ui';
// 自定义机能
import type { EditTodoPayload, Todo } from '@/types.ts';

const props = defineProps<{
  show: boolean
  todo: Todo | null
}>()

const emit = defineEmits<{
  close: []
  save: [payload: EditTodoPayload]
}>()

// 内部使用表单副本，避免编辑过程中直接修改父组件的 todo
const form = reactive<{
  content: string
  dueTimeMillis: number | null
}>({
  content: '',
  dueTimeMillis: null,
})

watch(
  () => props.todo, // 监视源
  (todo) => { // 取得新todo以后咋办
    if (todo) {
      // 编辑已有待办
      form.content = todo.content
      // Todo.due_time 兼容秒/毫秒，这里统一转成毫秒给 n-date-picker
      form.dueTimeMillis = todo.due_time > 1e11 ? todo.due_time : todo.due_time * 1000
    } else {
      //  要创建新待办
      form.content = "";
      form.dueTimeMillis = (new Date()).getTime();
    }
  },
  { immediate: true } // 初始化之后立即执行“”取得新todo以后咋办
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
  // 新待办默认未完成
  let completedStatus = props.todo !== null ? props.todo.completed : false;
  if (form.dueTimeMillis > Date.now()) {
    completedStatus = false;
  }

  emit("save", {
    todo_id: props.todo !== null ? props.todo.todo_id : -1,
    content: form.content.trim(),
    due_time: Math.floor(form.dueTimeMillis / 1000),  // 转换为秒
    completed: completedStatus,
  })
}
</script>

<template>
  <n-modal style="max-width: 75vw" preset="card" title="编辑待办" :show="show" @update:show="handleUpdateShow">
    <n-form>
      <n-form-item label="待办内容">
        <n-input v-model:value="form.content" type="textarea" placeholder="请输入待办内容" />
      </n-form-item>

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

<style scoped></style>
