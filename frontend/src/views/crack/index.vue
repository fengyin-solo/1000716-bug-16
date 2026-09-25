<template>
  <section class="page" data-module="crack">
    <header class="page-head">
      <div>
        <h2>裂缝处置管理</h2>
        <p class="page-desc">维护处置单，围绕处置单号、所在路段、裂缝类型、裂缝长度做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记处置单</button>
        <button class="btn" type="button" @click="exportRows">导出裂缝处置清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">详情</button>
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无裂缝处置数据，可先登记处置单</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条裂缝处置记录</span>
      <span v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="detail" class="modal-mask" @click.self="closeDetail">
      <div class="modal-card">
        <header class="modal-head">
          <h3>处置单详情 · {{ detail.处置单号 }}（当前环节：{{ detail.处置状态 ?? detail.status }}）</h3>
          <button class="btn ghost" type="button" @click="closeDetail">关闭</button>
        </header>
        <div class="detail-grid">
          <label v-for="field in editableFields" :key="field" class="detail-item">
            <span>{{ field }}</span>
            <input v-model="detailForm[field]" :placeholder="`填写${field}`" />
          </label>
          <label class="detail-item wide">
            <span>处理意见</span>
            <textarea v-model="detailForm.处理意见" rows="3" placeholder="填写处理意见，退回重做后仍会保留"></textarea>
          </label>
          <label class="detail-item wide">
            <span>照片</span>
            <input v-model="detailForm.照片" placeholder="照片链接或编号，多个用逗号分隔" />
          </label>
        </div>
        <footer class="modal-foot">
          <button class="btn" type="button" @click="saveDetail">保存修改</button>
          <button
            v-for="action in actions"
            :key="action"
            class="btn primary"
            type="button"
            @click="runAction(action, detail, detailForm)"
          >
            {{ action }}
          </button>
        </footer>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/crack'
const columns = ["处置单号", "所在路段", "裂缝类型", "裂缝长度", "灌缝材料", "作业班组", "完成日期", "处置状态"]
const actions = ["安排处置", "确认完成", "退回重做", "取消处置"]
const statuses = ["待安排", "处置中", "已完成", "已取消"]
const editableFields = ["所在路段", "裂缝类型", "裂缝长度", "灌缝材料", "作业班组", "完成日期"]
const stats = [{"label": "待安排处置", "value": 0}, {"label": "本月处置长度", "value": 0}, {"label": "取消单数", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const noticeMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
const detail = ref<Row | null>(null)
const detailForm = ref<Record<string, string>>({})

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '处置单登记入口尚未接入审批流'
}

function fillForm(entry: Row) {
  const form: Record<string, string> = {}
  for (const field of [...editableFields, '处理意见', '照片']) {
    const value = entry[field]
    form[field] = value === null || value === undefined ? '' : String(value)
  }
  detailForm.value = form
}

async function openDetail(row: Row) {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      throw new Error('处置单详情读取失败')
    }
    detail.value = (await response.json()) as Row
    fillForm(detail.value)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '处置单详情读取失败'
  }
}

function closeDetail() {
  detail.value = null
  detailForm.value = {}
}

async function saveDetail() {
  if (!detail.value) {
    return
  }
  await submit(detail.value.id, { ...detailForm.value })
}

async function runAction(action: string, row: Row, edits?: Record<string, string>) {
  await submit(row.id, { action, ...(edits ?? {}) })
}

async function submit(entryId: string | number | null, values: Record<string, string>) {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${entryId}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.message ?? '裂缝处置动作未生效，请稍后重试')
    }
    noticeMessage.value = payload.message ?? '处置单已更新'
    if (detail.value && payload.entry && String(detail.value.id) === String(payload.entry.id)) {
      detail.value = payload.entry as Row
      fillForm(detail.value)
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '裂缝处置操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('处置单列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '裂缝处置列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 20;
}
.modal-card {
  background: #fff;
  border-radius: 8px;
  border: 1px solid var(--border);
  padding: 16px 20px;
  width: 640px;
  max-width: calc(100vw - 48px);
  max-height: calc(100vh - 96px);
  overflow: auto;
}
.modal-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.modal-head h3 {
  margin: 0;
  font-size: 15px;
}
.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px 16px;
}
.detail-item span {
  display: block;
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 4px;
}
.detail-item input,
.detail-item textarea {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 13px;
}
.detail-item.wide {
  grid-column: 1 / -1;
}
.modal-foot {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
}
.notice-text {
  color: #067647;
}
</style>
