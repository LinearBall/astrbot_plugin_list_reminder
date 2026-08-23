<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import Chart from 'chart.js/auto';

import { dateKey, formatDateTime, toDate } from '@/utils/date';
import { useStore } from '@/composables/useStore';

const { state, nicknameOf } = useStore();

const TAG_COLORS = [
  '#3b82f6', '#10b981', '#f59e0b', '#ef4444',
  '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16',
];

const stats = computed(() => {
  const now = Date.now();
  let done = 0;
  let overdue = 0;
  for (const t of state.todos) {
    if (t.completed) done++;
    else if (toDate(t.due_time).getTime() < now) overdue++;
  }
  return {
    total: state.todos.length,
    done,
    pending: state.todos.length - done,
    overdue,
  };
});

/** Tag -> count, with untagged todos grouped into "其他". */
const tagStats = computed(() => {
  const counts: Record<string, number> = {};
  for (const t of state.todos) {
    if (t.tags.length === 0) {
      counts['其他'] = (counts['其他'] ?? 0) + 1;
    } else {
      t.tags.forEach((tag) => {
        counts[tag] = (counts[tag] ?? 0) + 1;
      });
    }
  }
  return counts;
});

/** Last 7 days (oldest -> newest) of due dates with completed/pending counts. */
const trend = computed(() => {
  const days: { label: string; key: string; done: number; pending: number }[] = [];
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  for (let i = 6; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(today.getDate() - i);
    const key = dateKey(d);
    days.push({
      label: `${d.getMonth() + 1}/${d.getDate()}`,
      key,
      done: 0,
      pending: 0,
    });
  }
  const index: Record<string, (typeof days)[number]> = {};
  days.forEach((d) => (index[d.key] = d));
  for (const t of state.todos) {
    const key = dateKey(toDate(t.due_time));
    const bucket = index[key];
    if (bucket) {
      if (t.completed) bucket.done++;
      else bucket.pending++;
    }
  }
  return days;
});

/** Todos ordered by due time descending, for the activity feed. */
const activity = computed(() =>
  [...state.todos].sort((a, b) => b.due_time - a.due_time).slice(0, 6),
);

/** Per-creator completion stats for the ranking panel. */
const ranking = computed(() => {
  const map: Record<string, { total: number; done: number }> = {};
  for (const t of state.todos) {
    let entry = map[t.creator];
    if (!entry) {
      entry = { total: 0, done: 0 };
      map[t.creator] = entry;
    }
    entry.total++;
    if (t.completed) entry.done++;
  }
  return Object.entries(map)
    .map(([creator, v]) => ({ creator, ...v, pct: v.total ? Math.round((v.done / v.total) * 100) : 0 }))
    .sort((a, b) => b.done - a.done);
});

const tagCanvas = ref<HTMLCanvasElement | null>(null);
const trendCanvas = ref<HTMLCanvasElement | null>(null);
let tagChart: Chart | null = null;
let trendChart: Chart | null = null;

onMounted(() => {
  if (tagCanvas.value) {
    tagChart = new Chart(tagCanvas.value, {
      type: 'doughnut',
      data: { labels: [], datasets: [{ data: [], backgroundColor: [], borderWidth: 3, borderColor: '#fff' }] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '60%',
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const total = (ctx.dataset.data as number[]).reduce((a, b) => a + (b as number), 0);
                const pct = total ? Math.round(((ctx.parsed as number) / total) * 100) : 0;
                return ` ${ctx.label}: ${ctx.parsed} 项 (${pct}%)`;
              },
            },
          },
        },
      },
    });
  }
  if (trendCanvas.value) {
    trendChart = new Chart(trendCanvas.value, {
      type: 'bar',
      data: {
        labels: [],
        datasets: [
          { label: '已完成', data: [], backgroundColor: '#10b981', borderRadius: 6, barPercentage: 0.6 },
          { label: '待完成', data: [], backgroundColor: '#3b82f6', borderRadius: 6, barPercentage: 0.6 },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: 'top', labels: { usePointStyle: true, pointStyle: 'rectRounded' } } },
        scales: {
          x: { grid: { display: false } },
          y: { beginAtZero: true, ticks: { precision: 0 } },
        },
      },
    });
  }
  syncCharts();
});

/** Push the latest computed data into both charts. */
function syncCharts() {
  if (tagChart) {
    const labels = Object.keys(tagStats.value);
    const dataset = tagChart.data.datasets[0]!;
    tagChart.data.labels = labels;
    dataset.data = labels.map((l) => tagStats.value[l] ?? 0);
    dataset.backgroundColor = labels.map((_, i) => TAG_COLORS[i % TAG_COLORS.length]);
    tagChart.update();
  }
  if (trendChart) {
    const doneSet = trendChart.data.datasets[0]!;
    const pendingSet = trendChart.data.datasets[1]!;
    trendChart.data.labels = trend.value.map((d) => d.label);
    doneSet.data = trend.value.map((d) => d.done);
    pendingSet.data = trend.value.map((d) => d.pending);
    trendChart.update();
  }
}

watch(() => state.todos, syncCharts, { deep: true });

onUnmounted(() => {
  tagChart?.destroy();
  trendChart?.destroy();
});

const rankColors = [
  'linear-gradient(90deg,#10b981,#34d399)',
  'linear-gradient(90deg,#2563eb,#60a5fa)',
  'linear-gradient(90deg,#f59e0b,#fbbf24)',
  'linear-gradient(90deg,#6366f1,#a78bfa)',
  'linear-gradient(90deg,#ef4444,#f87171)',
];
</script>

<template>
  <div class="page">
    <div class="page-header">
      <h1 class="page-title">仪表盘</h1>
      <p class="page-subtitle">欢迎回来！以下是你待办事项的整体情况 👋</p>
    </div>

    <div class="stats-grid">
      <div class="stat-card">
        <div>
          <div class="stat-label">全部待办</div>
          <div class="stat-value" style="color: var(--primary)">{{ stats.total }}</div>
        </div>
        <div class="stat-icon">📋</div>
      </div>
      <div class="stat-card">
        <div>
          <div class="stat-label">已完成</div>
          <div class="stat-value" style="color: var(--success)">{{ stats.done }}</div>
        </div>
        <div class="stat-icon">✅</div>
      </div>
      <div class="stat-card">
        <div>
          <div class="stat-label">进行中</div>
          <div class="stat-value" style="color: var(--warning)">{{ stats.pending }}</div>
        </div>
        <div class="stat-icon">⏳</div>
      </div>
      <div class="stat-card">
        <div>
          <div class="stat-label">已逾期</div>
          <div class="stat-value" style="color: var(--danger)">{{ stats.overdue }}</div>
        </div>
        <div class="stat-icon">⚠️</div>
      </div>
    </div>

    <div class="charts-grid">
      <div class="chart-card">
        <h3 class="chart-title">🏷️ 任务标签统计</h3>
        <div class="chart-box"><canvas ref="tagCanvas" /></div>
        <div class="tag-legend">
          <div v-for="(label, i) in Object.keys(tagStats)" :key="label" class="legend-item">
            <span class="legend-dot" :style="{ background: TAG_COLORS[i % TAG_COLORS.length] }" />
            {{ label }}
            <strong style="margin-left: 4px">{{ tagStats[label] }}</strong>
          </div>
        </div>
      </div>
      <div class="chart-card">
        <h3 class="chart-title">📊 近 7 天待办（按到期日）</h3>
        <div class="chart-box"><canvas ref="trendCanvas" /></div>
      </div>
    </div>

    <div class="charts-grid">
      <div class="card">
        <div class="block-title">最近动态</div>
        <div v-if="activity.length === 0" class="empty-inline">暂无动态</div>
        <div v-for="t in activity" :key="t.todo_id" class="act-item">
          <span class="act-dot" :class="t.completed ? 's' : 'w'" />
          <div class="act-content">
            <div class="act-text">
              <strong>{{ nicknameOf(t.creator) }}</strong>
              {{ t.completed ? '完成了待办' : '创建了待办' }}「{{ t.content }}」
            </div>
            <div class="act-time">{{ formatDateTime(t.due_time) }}</div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="block-title">👥 成员待办排行</div>
        <div v-if="ranking.length === 0" class="empty-inline">暂无数据</div>
        <div v-for="(r, i) in ranking" :key="r.creator" class="progress-row">
          <div class="pr-head">
            <span>{{ nicknameOf(r.creator) }}</span>
            <span>{{ r.done }}/{{ r.total }} 完成</span>
          </div>
          <div class="pr-bar">
            <div class="pr-fill" :style="{ width: r.pct + '%', background: rankColors[i % rankColors.length] }" />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
  margin-bottom: 24px;
}

.stat-card {
  background: #fff;
  border-radius: var(--radius);
  padding: 22px;
  box-shadow: var(--shadow-lg);
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.stat-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--g700);
  margin-bottom: 8px;
}

.stat-value {
  font-size: 36px;
  font-weight: 800;
  line-height: 1;
}

.stat-icon {
  font-size: 30px;
}

.charts-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
  margin-bottom: 24px;
}

.chart-card {
  background: #fff;
  border-radius: var(--radius);
  padding: 22px;
  box-shadow: var(--shadow-lg);
}

.chart-title {
  font-size: 18px;
  font-weight: 700;
  margin: 0 0 16px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--g100);
}

.chart-box {
  position: relative;
  height: 300px;
}

.tag-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--g100);
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--g600);
}

.legend-dot {
  width: 12px;
  height: 12px;
  border-radius: 3px;
}

.block-title {
  padding: 18px 22px;
  font-size: 18px;
  font-weight: 700;
  border-bottom: 1px solid var(--g100);
}

.empty-inline {
  padding: 28px;
  text-align: center;
  color: var(--g400);
  font-size: 14px;
}

.act-item {
  display: flex;
  gap: 12px;
  padding: 14px 22px;
}

.act-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  margin-top: 6px;
  flex-shrink: 0;
}

.act-dot.s {
  background: var(--success);
}

.act-dot.w {
  background: var(--warning);
}

.act-text {
  font-size: 14px;
  color: var(--g700);
}

.act-time {
  font-size: 12px;
  color: var(--g400);
  margin-top: 2px;
}

.progress-row {
  padding: 12px 22px;
}

.pr-head {
  display: flex;
  justify-content: space-between;
  font-size: 14px;
  margin-bottom: 6px;
}

.pr-head span:first-child {
  font-weight: 600;
}

.pr-head span:last-child {
  color: var(--g500);
  font-size: 13px;
}

.pr-bar {
  height: 8px;
  background: var(--g100);
  border-radius: 4px;
  overflow: hidden;
}

.pr-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.3s ease;
}

@media (max-width: 1024px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .charts-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
    gap: 12px;
    margin-bottom: 16px;
  }

  .stat-card {
    padding: 16px;
  }

  .stat-label {
    font-size: 12px;
  }

  .stat-value {
    font-size: 28px;
  }

  .stat-icon {
    font-size: 24px;
  }

  .chart-card {
    padding: 16px;
  }

  .chart-title {
    font-size: 16px;
    padding-bottom: 10px;
    margin-bottom: 10px;
  }

  .chart-box {
    height: 240px;
  }

  .block-title {
    padding: 14px 18px;
    font-size: 16px;
  }

  .act-item {
    padding: 12px 18px;
  }

  .progress-row {
    padding: 10px 18px;
  }
}
</style>

