<script setup lang="ts">
// Vue机能
import { ref, onMounted } from "vue"
import { useRouter } from "vue-router"
// Naive UI机能
import { NCard, NButton, NForm, NFormItem, NInput, useMessage } from "naive-ui"
// 自定义机能
import { checkIfAlreadyLoggedIn, checkKey } from "@/fbApi/apis"

const router = useRouter()
const message = useMessage()

const key = ref("")
const loading = ref(false) // * 登录按钮用

/**
 * 处理登录事件。若登录成功，则路由到待办页
 */
async function handleLogin() {
  // 首先确认密钥非空
  if (!key.value.trim()) {
    message.warning("请输入登录密钥");
    return;
  }

  loading.value = true;
  checkKey(key.value).then(val => {
    loading.value = false
    if (val) {
      message.success("登录成功");
      router.push("/todo")  // * 通过这个实现跳转
    } else {
      message.error("密钥错误");
    }
  });
}

onMounted(async () => {
  // 检查是否已登录，若是，则直接跳转到待办页
  let isAlready = await checkIfAlreadyLoggedIn();
  if (isAlready !== null) {
    router.push("/todo")  // * 通过这个实现跳转
  }
});
</script>

<template>
  <div class="container">
    <n-card class="login-card shadow-edge" title="个人待办管理">
      <n-form label-placement="top">
        <n-form-item label="登录密钥">
          <n-input v-model:value="key" type="password" placeholder="请输入登录密钥" @keyup.enter="handleLogin" />
        </n-form-item>
        <n-button type="primary" block :loading="loading" @click="handleLogin">
          登录
        </n-button>
      </n-form>
    </n-card>
  </div>
</template>

<style scoped>
.login-card {
  max-width: 40vw;
}
</style>
