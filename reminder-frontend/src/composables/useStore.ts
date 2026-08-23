import { reactive } from 'vue';

import {
  checkIfAlreadyLoggedIn,
  getTagCatalogue,
  getTodos,
  toggleAdmin as apiToggleAdmin,
} from '@/fbApi/apis.ts';
import type { TagCatalogue, Todo } from '@/types.ts';

/**
 * Application-wide reactive state shared across the navbar and every view.
 *
 * Admin mode is toggled on the backend through `/api/admin/toggle`; after a
 * successful toggle both `/api/todos` and `/api/tags` return a different data
 * set, so all views refresh from the server through the helpers below.
 */
const state = reactive({
  me: '',
  isAdmin: false,
  loggedIn: false,
  todos: [] as Todo[],
  tagCatalogue: null as TagCatalogue | null,
});

let initPromise: Promise<void> | null = null;

/**
 * Resolve the display nickname for a sender id.
 *
 * @param senderId The raw sender_id stored on a todo.
 * @returns The nickname when known, otherwise the raw sender_id.
 */
function nicknameOf(senderId: string): string {
  const user = state.tagCatalogue?.users.find((u) => u.sender_id === senderId);
  return user?.nickname || senderId;
}

/** Fetch the todo list visible to the current user. */
async function refreshTodos(): Promise<void> {
  state.todos = await getTodos();
}

/** Fetch the tag/user catalogue visible to the current user. */
async function refreshTags(): Promise<void> {
  state.tagCatalogue = await getTagCatalogue();
}

/**
 * Initialise the session exactly once: resolve the current user and load both
 * data sets. Repeated calls return the same in-flight promise.
 */
function init(): Promise<void> {
  if (!initPromise) {
    initPromise = (async () => {
      const me = await checkIfAlreadyLoggedIn();
      state.loggedIn = me !== null;
      state.me = me?.sender_id ?? '';
      state.isAdmin = me?.is_admin ?? false;
      if (me) {
        await Promise.all([refreshTodos(), refreshTags()]);
      }
    })();
  }
  return initPromise;
}

/**
 * Toggle admin mode on the backend, then reload all data.
 *
 * @returns The new admin state.
 */
async function toggleAdminMode(): Promise<boolean> {
  const res = await apiToggleAdmin();
  if (res.code === 200) {
    state.isAdmin = !!res.payload['is_admin'];
    await Promise.all([refreshTodos(), refreshTags()]);
    return state.isAdmin;
  }
  throw new Error(res.payload['message'] || '操作失败');
}

/** Reset the session after logout so the next login re-initialises cleanly. */
function reset(): void {
  initPromise = null;
  state.me = '';
  state.isAdmin = false;
  state.loggedIn = false;
  state.todos = [];
  state.tagCatalogue = null;
}

export function useStore() {
  return {
    state,
    init,
    reset,
    refreshTodos,
    refreshTags,
    toggleAdminMode,
    nicknameOf,
  };
}
