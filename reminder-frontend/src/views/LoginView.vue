<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { NButton, NForm, NFormItem, NInput, useMessage } from 'naive-ui';

import { checkIfAlreadyLoggedIn, checkKey } from '@/fbApi/apis';

const router = useRouter();
const message = useMessage();

const key = ref('');
const loading = ref(false);

async function handleLogin() {
  if (!key.value.trim()) {
    message.warning('请输入登录密钥');
    return;
  }
  loading.value = true;
  try {
    const ok = await checkKey(key.value);
    if (ok) {
      message.success('登录成功');
      router.push('/dashboard');
    } else {
      message.error('密钥错误');
    }
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  const me = await checkIfAlreadyLoggedIn();
  if (me !== null) {
    router.push('/dashboard');
  }
});
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-brand">
        <span class="login-logo">📋</span>
        <h1 class="login-title">待办事项管理</h1>
        <p class="login-subtitle">登录以管理你的待办任务</p>
      </div>
      <NForm label-placement="top">
        <NFormItem label="登录密钥">
          <NInput
            v-model:value="key"
            type="password"
            show-password-on="click"
            placeholder="请输入登录密钥"
            size="large"
            @keyup.enter="handleLogin"
          />
        </NFormItem>
        <NButton type="primary" block size="large" :loading="loading" @click="handleLogin">
          登录
        </NButton>
      </NForm>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 20px;
}

.login-card {
  width: 100%;
  max-width: 420px;
  background: #fff;
  border-radius: 16px;
  padding: 40px 36px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.2);
}

.login-brand {
  text-align: center;
  margin-bottom: 28px;
}

.login-logo {
  font-size: 48px;
  display: block;
  margin-bottom: 12px;
}

.login-title {
  font-size: 26px;
  font-weight: 800;
  color: var(--g900);
  margin: 0;
}

.login-subtitle {
  font-size: 14px;
  color: var(--g500);
  margin: 8px 0 0;
}
</style>