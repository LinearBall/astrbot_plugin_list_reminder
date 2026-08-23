<script setup lang="ts">
import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';
import { NButton, NEmpty } from 'naive-ui';

import { checkIfAlreadyLoggedIn } from '@/fbApi/apis';
import { useStore } from '@/composables/useStore';
import { addDays, dateKey, formatTime } from '@/utils/date';
import { onMounted } from 'vue';
import type { Todo } from '@/types';

const router = useRouter();
const { state, init, nicknameOf } = useStore();

type ViewMode = 'day' | 'week' | 'month' | 'year';
const view = ref<ViewMode>('month');
const today = new Date();
today.setHours(0, 0, 0, 0);
const cur = ref(new Date(today));

const WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
const VIEW_MODES: ViewMode[] = ['day', 'week', 'month', 'year'];
const VIEW_LABELS: Record<ViewMode, string> = { day: '日', week: '周', month: '月', year: '年' };
const MONTHS = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'];

/** Group visible todos by their local due date. */
const eventsByDay = computed<Record<string, Todo[]>>(() => {
  const map: Record<string, Todo[]> = {};
  for (const t of state.todos) {
    const d = new Date(t.due_time > 1e11 ? t.due_time : t.due_time * 1000);
    const key = dateKey(d);
    (map[key] ??= []).push(t);
  }
  return map;
});

const title = computed(() => {
  const y = cur.value.getFullYear();
  const m = cur.value.getMonth();
  const d = cur.value.getDate();
  if (view.value === 'month') return `${y}年${m + 1}月`;
  if (view.value === 'year') return `${y}年`;
  if (view.value === 'day') return `${y}年${m + 1}月${d}日`;
  const start = weekStart.value;
  const end = addDays(start, 6);
  const sameMonth = start.getMonth() === end.getMonth();
  return `${start.getFullYear()}年${start.getMonth() + 1}月${start.getDate()}日 - ${sameMonth ? '' : `${end.getMonth() + 1}月`}${end.getDate()}日`;
});

function shift(dir: number) {
  const d = new Date(cur.value);
  if (view.value === 'month') d.setMonth(d.getMonth() + dir);
  else if (view.value === 'year') d.setFullYear(d.getFullYear() + dir);
  else if (view.value === 'week') d.setDate(d.getDate() + dir * 7);
  else d.setDate(d.getDate() + dir);
  cur.value = d;
}

function goToday() {
  cur.value = new Date(today);
  view.value = 'month';
}

/** Monday-free week start: Sunday of the current week. */
const weekStart = computed(() => {
  const d = new Date(cur.value);
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() - d.getDay());
  return d;
});

const weekDays = computed(() =>
  Array.from({ length: 7 }, (_, i) => addDays(weekStart.value, i)),
);

interface DayCell {
  date: Date;
  key: string;
  inMonth: boolean;
  isToday: boolean;
  events: Todo[];
}

/** Build the 6-row month grid, including leading/trailing days. */
const monthCells = computed<DayCell[]>(() => {
  const y = cur.value.getFullYear();
  const m = cur.value.getMonth();
  const first = new Date(y, m, 1);
  const startOffset = first.getDay();
  const start = addDays(first, -startOffset);
  const cells: DayCell[] = [];
  for (let i = 0; i < 42; i++) {
    const date = addDays(start, i);
    const key = dateKey(date);
    cells.push({
      date,
      key,
      inMonth: date.getMonth() === m,
      isToday: date.getTime() === today.getTime(),
      events: eventsByDay.value[key] ?? [],
    });
  }
  return cells;
});

/** Events for the selected day, sorted by due time. */
const dayEvents = computed(() => {
  const key = dateKey(cur.value);
  return [...(eventsByDay.value[key] ?? [])].sort((a, b) => a.due_time - b.due_time);
});

/** Events for a week column with their hour/minute offsets. */
function weekEventsFor(date: Date) {
  const key = dateKey(date);
  return (eventsByDay.value[key] ?? []).map((t) => {
    const d = new Date(t.due_time > 1e11 ? t.due_time : t.due_time * 1000);
    const minutes = d.getHours() * 60 + d.getMinutes();
    return { todo: t, top: (minutes / 60) * 48, time: formatTime(t.due_time) };
  });
}

interface MiniCell {
  day: number | null;
  isToday: boolean;
  hasEvent: boolean;
}

/** Build one mini month grid for the year view. */
function miniMonth(year: number, month: number): MiniCell[] {
  const first = new Date(year, month, 1);
  const dim = new Date(year, month + 1, 0).getDate();
  const cells: MiniCell[] = [];
  for (let i = 0; i < first.getDay(); i++) cells.push({ day: null, isToday: false, hasEvent: false });
  for (let d = 1; d <= dim; d++) {
    const date = new Date(year, month, d);
    cells.push({
      day: d,
      isToday: date.getTime() === today.getTime(),
      hasEvent: !!eventsByDay.value[dateKey(date)],
    });
  }
  return cells;
}

const eventCountOfMonth = (year: number, month: number) =>
  Object.entries(eventsByDay.value).filter(([key]) => {
    const [y, m] = key.split('-').map(Number);
    return y === year && m! - 1 === month;
  }).reduce((sum, [, evs]) => sum + evs.length, 0);

function openDay(date: Date) {
  cur.value = new Date(date);
  cur.value.setHours(0, 0, 0, 0);
  view.value = 'day';
}

function openMonth(month: number) {
  cur.value = new Date(cur.value.getFullYear(), month, 1);
  view.value = 'month';
}

onMounted(async () => {
  await init();
  if (!(await checkIfAlreadyLoggedIn())) router.push('/login');
});
</script>

<template>
  <div class="page">
    <div class="page-header">
      <h1 class="page-title">任务日历</h1>
      <p class="page-subtitle">按日历视图查看所有待办事项的时间安排</p>
    </div>

    <div class="cal-toolbar">
      <div class="cal-nav">
        <NButton secondary @click="goToday">今天</NButton>
        <button class="cal-nav-btn" title="上一个" @click="shift(-1)">◀</button>
        <button class="cal-nav-btn" title="下一个" @click="shift(1)">▶</button>
        <span class="cal-title">{{ title }}</span>
      </div>
      <div class="view-switcher">
        <button
          v-for="v in VIEW_MODES"
          :key="v"
          class="view-btn"
          :class="{ active: view === v }"
          @click="view = v"
        >
          {{ VIEW_LABELS[v] }}
        </button>
      </div>
    </div>

    <div class="cal-card">
      <!-- Month -->
      <div v-if="view === 'month'">
        <div class="cal-grid weekdays">
          <div v-for="w in WEEKDAYS" :key="w" class="wd">{{ w }}</div>
        </div>
        <div class="cal-grid month-grid">
          <div
            v-for="cell in monthCells"
            :key="cell.key"
            class="cal-day"
            :class="{ other: !cell.inMonth, today: cell.isToday }"
            @click="openDay(cell.date)"
          >
            <span class="day-num">{{ cell.date.getDate() }}</span>
            <div class="day-events">
              <div
                v-for="ev in cell.events.slice(0, 3)"
                :key="ev.todo_id"
                class="cal-event"
                :class="{ done: ev.completed }"
              >
                {{ ev.content }}
              </div>
              <div v-if="cell.events.length > 3" class="day-more">+{{ cell.events.length - 3 }} 更多</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Week -->
      <div v-else-if="view === 'week'" class="week-wrap">
        <div class="week-grid">
          <div class="week-corner" />
          <div
            v-for="d in weekDays"
            :key="d.toISOString()"
            class="week-wd"
            :class="{ today: dateKey(d) === dateKey(today) }"
            @click="openDay(d)"
          >
            <div class="wn-name">{{ WEEKDAYS[d.getDay()] }}</div>
            <span class="wn-num" :class="{ 'num-today': dateKey(d) === dateKey(today) }">{{ d.getDate() }}</span>
          </div>
        </div>
        <div class="week-body">
          <div class="week-timecol">
            <div v-for="h in 24" :key="h" class="week-time">{{ String(h - 1).padStart(2, '0') }}:00</div>
          </div>
          <div
            v-for="d in weekDays"
            :key="'c' + d.toISOString()"
            class="week-col"
            :class="{ 'col-today': dateKey(d) === dateKey(today) }"
          >
            <div v-for="h in 24" :key="h" class="week-slot" />
            <div
              v-for="ev in weekEventsFor(d)"
              :key="ev.todo.todo_id"
              class="cal-event week-event"
              :class="{ done: ev.todo.completed }"
              :style="{ top: ev.top + 'px' }"
            >
              <span class="we-time">{{ ev.time }}</span>
              <span class="we-title">{{ ev.todo.content }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Day -->
      <div v-else-if="view === 'day'">
        <div class="day-header">
          <div class="day-date">{{ title }}</div>
          <div class="day-wd">{{ WEEKDAYS[cur.getDay()] }}</div>
        </div>
        <NEmpty v-if="dayEvents.length === 0" description="这一天没有待办事项" style="padding: 60px" />
        <div v-else class="timeline">
          <div v-for="h in 24" :key="h" class="time-slot">
            <span class="time-label">{{ String(h - 1).padStart(2, '0') }}:00</span>
            <div class="slot-events">
              <div
                v-for="ev in dayEvents.filter((e) => {
                  const d = new Date(e.due_time > 1e11 ? e.due_time : e.due_time * 1000);
                  return d.getHours() === h - 1;
                })"
                :key="ev.todo_id"
                class="time-event"
                :class="{ done: ev.completed }"
              >
                <div class="te-time">{{ formatTime(ev.due_time) }}</div>
                <div class="te-title">{{ ev.content }}</div>
                <div class="te-meta">👤 {{ nicknameOf(ev.creator) }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Year -->
      <div v-else class="year-grid">
        <div
          v-for="m in 12"
          :key="m"
          class="month-card"
          :class="{ current: cur.getFullYear() === today.getFullYear() && m - 1 === today.getMonth() }"
          @click="openMonth(m - 1)"
        >
          <div class="mc-title">{{ MONTHS[m - 1] }}</div>
          <div class="mini-cal">
            <div class="mini-wds">
              <div v-for="w in WEEKDAYS" :key="w" class="mini-wd">{{ w.charAt(1) }}</div>
            </div>
            <div class="mini-days">
              <div
                v-for="(cell, i) in miniMonth(cur.getFullYear(), m - 1)"
                :key="i"
                class="mini-day"
                :class="{ other: cell.day === null, today: cell.isToday, 'has-event': cell.hasEvent }"
              >
                {{ cell.day ?? '' }}
              </div>
            </div>
          </div>
          <div class="mc-stat">
            <template v-if="eventCountOfMonth(cur.getFullYear(), m - 1) > 0">
              <strong>{{ eventCountOfMonth(cur.getFullYear(), m - 1) }}</strong> 项待办
            </template>
            <template v-else>无待办</template>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cal-toolbar {
  background: #fff;
  border-radius: var(--radius);
  padding: 16px 22px;
  box-shadow: var(--shadow-lg);
  margin-bottom: 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}

.cal-nav {
  display: flex;
  align-items: center;
  gap: 8px;
}

.cal-nav-btn {
  width: 36px;
  height: 36px;
  border: 1px solid var(--g200);
  background: #fff;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 14px;
  color: var(--g600);
}

.cal-nav-btn:hover {
  border-color: var(--primary);
  color: var(--primary);
  background: var(--primary-bg);
}

.cal-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--g900);
  min-width: 200px;
  margin-left: 8px;
}

.view-switcher {
  display: flex;
  background: var(--g100);
  border-radius: var(--radius-sm);
  padding: 3px;
}

.view-btn {
  padding: 7px 18px;
  border: none;
  background: transparent;
  font-size: 14px;
  font-weight: 600;
  color: var(--g500);
  cursor: pointer;
  border-radius: 6px;
}

.view-btn.active {
  background: #fff;
  color: var(--g900);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.08);
}

.cal-card {
  background: #fff;
  border-radius: var(--radius);
  box-shadow: var(--shadow-lg);
  overflow: hidden;
}

/* Shared event style: unified blue, completed = strikethrough */
.cal-event {
  background: #dbeafe;
  color: #1e40af;
  border-left: 3px solid #3b82f6;
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cal-event.done {
  opacity: 0.55;
  text-decoration: line-through;
}

/* Month */
.cal-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
}

.weekdays .wd {
  padding: 14px;
  text-align: center;
  font-size: 13px;
  font-weight: 700;
  color: var(--g500);
  background: var(--g50);
  border-bottom: 2px solid var(--g200);
}

.cal-day {
  min-height: 110px;
  padding: 8px;
  border-right: 1px solid var(--g100);
  border-bottom: 1px solid var(--g100);
  cursor: pointer;
  display: flex;
  flex-direction: column;
}

.cal-day:hover {
  background: var(--g50);
}

.cal-day.other {
  background: var(--g50);
  color: var(--g300);
}

.cal-day.today {
  background: var(--primary-bg);
}

.day-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  font-size: 13px;
  font-weight: 600;
  border-radius: 50%;
  margin-bottom: 4px;
}

.cal-day.today .day-num {
  background: var(--primary);
  color: #fff;
}

.day-events {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.day-more {
  font-size: 11px;
  color: var(--primary);
  font-weight: 600;
  padding: 1px 6px;
}

/* Week */
.week-grid {
  display: grid;
  grid-template-columns: 60px repeat(7, 1fr);
}

.week-corner {
  background: var(--g50);
  border-bottom: 2px solid var(--g200);
}

.week-wd {
  padding: 12px 8px;
  text-align: center;
  background: var(--g50);
  border-bottom: 2px solid var(--g200);
  cursor: pointer;
}

.wn-name {
  font-size: 12px;
  font-weight: 700;
  color: var(--g600);
}

.wn-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  font-size: 15px;
  font-weight: 700;
  margin-top: 4px;
}

.wn-num.num-today {
  background: var(--primary);
  color: #fff;
}

.week-body {
  display: grid;
  grid-template-columns: 60px repeat(7, 1fr);
  position: relative;
}

.week-timecol {
  display: flex;
  flex-direction: column;
}

.week-time {
  height: 48px;
  padding-right: 8px;
  text-align: right;
  font-size: 11px;
  color: var(--g400);
  font-weight: 600;
}

.week-col {
  border-left: 1px solid var(--g100);
  position: relative;
}

.week-col.col-today {
  background: rgba(37, 99, 235, 0.03);
}

.week-slot {
  height: 48px;
  border-bottom: 1px solid var(--g100);
}

.week-event {
  position: absolute;
  left: 2px;
  right: 2px;
  height: 42px;
  overflow: hidden;
  z-index: 1;
}

.week-event:hover {
  z-index: 2;
}

.we-time {
  display: block;
  font-size: 10px;
  opacity: 0.8;
}

.we-title {
  display: block;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Day */
.day-header {
  text-align: center;
  padding: 22px;
  border-bottom: 1px solid var(--g200);
}

.day-date {
  font-size: 26px;
  font-weight: 800;
  color: var(--g900);
}

.day-wd {
  font-size: 15px;
  color: var(--g500);
  margin-top: 4px;
}

.timeline {
  padding: 0 24px 24px 80px;
  position: relative;
}

.timeline::before {
  content: '';
  position: absolute;
  left: 70px;
  top: 0;
  bottom: 24px;
  width: 2px;
  background: var(--g200);
}

.time-slot {
  position: relative;
  min-height: 48px;
  padding: 4px 0;
}

.time-label {
  position: absolute;
  left: -70px;
  width: 50px;
  text-align: right;
  font-size: 12px;
  font-weight: 600;
  color: var(--g400);
}

.slot-events {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.time-event {
  background: #fff;
  border: 1px solid var(--g200);
  border-left: 4px solid var(--primary);
  border-radius: var(--radius-sm);
  padding: 10px 14px;
}

.time-event.done {
  opacity: 0.6;
}

.time-event.done .te-title {
  text-decoration: line-through;
  color: var(--g400);
}

.te-time {
  font-size: 12px;
  color: var(--g400);
  font-weight: 600;
}

.te-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--g800);
  margin: 2px 0;
}

.te-meta {
  font-size: 12px;
  color: var(--g400);
}

/* Year */
.year-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  padding: 24px;
}

.month-card {
  border: 1px solid var(--g200);
  border-radius: var(--radius-sm);
  overflow: hidden;
  cursor: pointer;
}

.month-card:hover {
  border-color: var(--primary-light);
  box-shadow: var(--shadow);
  transform: translateY(-2px);
}

.month-card.current {
  border-color: var(--primary);
  box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.2);
}

.mc-title {
  padding: 10px;
  font-size: 14px;
  font-weight: 700;
  text-align: center;
  background: var(--g50);
  border-bottom: 1px solid var(--g200);
}

.mini-cal {
  padding: 8px;
}

.mini-wds,
.mini-days {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 1px;
}

.mini-wd {
  text-align: center;
  font-size: 10px;
  font-weight: 600;
  color: var(--g400);
  padding: 2px 0;
}

.mini-day {
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  color: var(--g600);
  border-radius: 3px;
  position: relative;
}

.mini-day.other {
  visibility: hidden;
}

.mini-day.today {
  background: var(--primary);
  color: #fff;
  font-weight: 700;
}

.mini-day.has-event::after {
  content: '';
  position: absolute;
  bottom: 1px;
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--primary);
}

.mini-day.today.has-event::after {
  background: #fff;
}

.mc-stat {
  padding: 6px 10px;
  font-size: 11px;
  color: var(--g500);
  text-align: center;
  border-top: 1px solid var(--g100);
  background: var(--g50);
}

.mc-stat strong {
  color: var(--primary);
}

@media (max-width: 1024px) {
  .year-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .cal-toolbar {
    flex-direction: column;
    gap: 10px;
    padding: 12px;
  }

  .cal-nav {
    width: 100%;
    justify-content: space-between;
  }

  .cal-title {
    font-size: 16px;
  }

  .view-switcher {
    width: 100%;
    justify-content: center;
  }

  .cal-grid {
    gap: 2px;
  }

  .cal-day {
    min-height: 70px;
    padding: 4px;
  }

  .day-num {
    font-size: 12px;
  }

  .cal-event {
    font-size: 10px;
    padding: 1px 4px;
  }

  .week-grid {
    grid-template-columns: 40px repeat(7, 1fr);
  }

  .week-body {
    grid-template-columns: 40px repeat(7, 1fr);
  }

  .week-wd {
    padding: 8px 2px;
  }

  .wn-name {
    font-size: 10px;
  }

  .wn-num {
    width: 26px;
    height: 26px;
    font-size: 13px;
  }

  .week-time {
    font-size: 10px;
    padding-right: 4px;
  }

  .timeline {
    padding: 0 12px 12px 60px;
  }

  .timeline::before {
    left: 50px;
  }

  .time-label {
    left: -50px;
    width: 40px;
    font-size: 10px;
  }

  .day-date {
    font-size: 20px;
  }

  .year-grid {
    grid-template-columns: 1fr;
    gap: 12px;
    padding: 14px;
  }
}
</style>


