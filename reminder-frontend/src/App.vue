<script setup lang="ts">
import { onMounted } from 'vue';
import { RouterView, useRoute, useRouter } from 'vue-router';
import {
  dateZhCN,
  NConfigProvider,
  NDialogProvider,
  NLoadingBarProvider,
  NMessageProvider,
  NNotificationProvider,
  zhCN,
} from 'naive-ui';

import AppNavbar from '@/components/AppNavbar.vue';
import { useStore } from '@/composables/useStore';

const router = useRouter();
const route = useRoute();
const { state, init } = useStore();

onMounted(async () => {
  await init();
  if (!state.loggedIn && route.name !== 'login') {
    router.push('/login');
  }
});
</script>

<template>
  <NConfigProvider :locale="zhCN" :date-locale="dateZhCN">
    <NLoadingBarProvider>
      <NMessageProvider>
        <NDialogProvider>
          <NNotificationProvider>
            <template v-if="state.loggedIn && route.name !== 'login'">
              <div class="app-shell">
                <AppNavbar />
                <RouterView />
              </div>
            </template>
            <RouterView v-else />
          </NNotificationProvider>
        </NDialogProvider>
      </NMessageProvider>
    </NLoadingBarProvider>
  </NConfigProvider>
</template>

<style>
#app {
  min-height: 100vh;
}
</style>
