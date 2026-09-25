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
          <td v-for="column in columns" :key="column">
            <button v-if="column === '处置单号'" class="link" type="button" @click="openDetail(row)">
              {{ row[column] ?? '—' }}
            </button>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions">
            <button
              v-for="action in actionsFor(row)"
              :key="action"
              class="link"
              type="button"
              @click="openAction(action, row)"
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
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="detail" class="modal-mask" @click.self="closeDetail">
      <div class="modal">
        <header class="modal-head">
          <h3>处置单详情 · {{ detail.处置单号 }}</h3>
          <button class="link" type="button" @click="closeDetail">关闭</button>
        </header>

        <dl class="detail-grid">
          <template v-for="field in detailFields" :key="field">
            <dt>{{ field }}</dt>
            <dd>{{ detail[field] ?? '—' }}</dd>
          </template>
        </dl>

        <section class="detail-block">
          <h4>处理记录</h4>
          <ol v-if="detailLogs.length" class="log-list">
            <li v-for="(log, index) in detailLogs" :key="index" class="log-item">
              <div class="log-head">
                <strong>{{ log.动作 }}</strong>
                <span class="log-state">→ {{ log.流转后状态 }}</span>
                <span class="log-time">{{ log.操作时间 }}</span>
                <span v-if="log.合并角色" class="log-merge">{{ log.合并角色 }}（{{ log.合并组?.join('、') }}）</span>
              </div>
              <p v-if="log.处理意见" class="log-opinion">意见：{{ log.处理意见 }}</p>
              <p v-if="log.处置照片?.length" class="log-photos">照片：{{ log.处置照片.join('、') }}</p>
            </li>
          </ol>
          <p v-else class="empty-state">暂无处理记录</p>
        </section>

        <section class="detail-block">
          <h4>执行流转</h4>
          <div class="action-row">
            <button
              v-for="action in actionsFor(detail)"
              :key="action"
              class="btn"
              :class="{ primary: action === '确认完成' }"
              type="button"
              @click="openAction(action, detail)"
            >
              {{ action }}
            </button>
          </div>
        </section>
      </div>
    </div>

    <div v-if="actionDialog.action" class="modal-mask" @click.self="closeAction">
      <form class="modal" @submit.prevent="submitAction">
        <header class="modal-head">
          <h3>{{ actionDialog.action }} · {{ actionDialog.row?.处置单号 }}</h3>
          <button class="link" type="button" @click="closeAction">关闭</button>
        </header>

        <div v-if="actionDialog.action === '安排处置'" class="form-tip">
          可勾选同一路段上的其他待处置裂缝，合并安排、合并完成时状态会同步流转到每一条处置单。
        </div>

        <template v-if="actionDialog.action !== '取消处置'">
          <label class="form-item" v-for="field in editableFields" :key="field">
            <span>{{ field }}</span>
            <input v-model="actionDialog.form[field]" :placeholder="`如需修改${field}，在此填写`" />
          </label>
          <label class="form-item">
            <span>处理意见</span>
            <textarea v-model="actionDialog.form.处理意见" rows="3" placeholder="填写本次处置意见，退回重做后仍可在处理记录中查阅"></textarea>
          </label>
          <label class="form-item">
            <span>处置照片</span>
            <input v-model="actionDialog.photoText" placeholder="多张照片用逗号分隔，如 before.jpg,after.jpg" />
          </label>
        </template>
        <label v-else class="form-item">
          <span>取消原因</span>
          <textarea v-model="actionDialog.form.处理意见" rows="3" placeholder="说明取消处置的原因"></textarea>
        </label>

        <fieldset v-if="actionDialog.action === '安排处置'" class="form-item merge-box">
          <legend>同路段裂缝（可多选合并处置）</legend>
          <label v-for="candidate in mergeCandidates" :key="String(candidate.id)" class="merge-item">
            <input type="checkbox" :value="candidate.id" v-model="actionDialog.mergeIds" />
            <span>{{ candidate.处置单号 }} · {{ candidate.裂缝类型 }} · {{ candidate.裂缝长度 || '长度未填' }} · {{ candidate.处置状态 }}</span>
          </label>
          <p v-if="!mergeCandidates.length" class="empty-state">该路段暂无可合并的其他处置单</p>
        </fieldset>

        <p v-if="actionDialog.error" class="error-text">{{ actionDialog.error }}</p>
        <footer class="modal-foot">
          <button class="btn" type="button" @click="closeAction">放弃</button>
          <button class="btn primary" type="submit" :disabled="actionDialog.saving">
            {{ actionDialog.saving ? '提交中…' : '确认提交' }}
          </button>
        </footer>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type Log = {
  动作: string
  流转后状态: string
  处理意见: string
  处置照片: string[]
  操作时间: string
  合并组?: number[]
  合并角色?: string
}

const ENDPOINT = '/api/crack'
const columns = ["处置单号", "所在路段", "裂缝类型", "裂缝长度", "灌缝材料", "作业班组", "完成日期", "处置状态"]
const detailFields = ["处置单号", "所在路段", "裂缝类型", "裂缝长度", "灌缝材料", "作业班组", "处置状态", "完成日期", "处置完成时间"]
const editableFields = ["裂缝类型", "裂缝长度", "灌缝材料", "作业班组"]
const ALL_ACTIONS = ["安排处置", "确认完成", "退回重做", "取消处置"]
const ACTIONS_BY_STATUS: Record<string, string[]> = {
  待安排: ["安排处置", "取消处置"],
  处置中: ["确认完成", "取消处置"],
  已完成: ["退回重做"],
  已取消: [],
}

const rows = ref<Row[]>([])
const allRows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
const detail = ref<Row | null>(null)
const detailLogs = ref<Log[]>([])

const actionDialog = reactive({
  action: '' as string,
  row: null as Row | null,
  form: {} as Record<string, string>,
  photoText: '',
  mergeIds: [] as number[],
  saving: false,
  error: '',
})

const stats = computed(() => {
  const pending = allRows.value.filter((row) => row.处置状态 === '待安排').length
  const cancelled = allRows.value.filter((row) => row.处置状态 === '已取消').length
  const length = allRows.value
    .filter((row) => row.处置状态 === '已完成')
    .reduce((sum, row) => sum + (parseFloat(String(row.裂缝长度 ?? '')) || 0), 0)
  return [
    { label: "待安排处置", value: pending },
    { label: "本月处置长度(m)", value: Math.round(length * 10) / 10 },
    { label: "取消单数", value: cancelled },
  ]
})

const mergeCandidates = computed(() => {
  if (!actionDialog.row) return []
  const road = actionDialog.row.所在路段
  const selfId = actionDialog.row.id
  return allRows.value.filter((row) =>
    row.所在路段 === road &&
    row.id !== selfId &&
    (row.处置状态 === '待安排' || row.处置状态 === '处置中'))
})

function actionsFor(row: Row): string[] {
  return ACTIONS_BY_STATUS[String(row.处置状态 ?? '')] ?? []
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '处置单登记沿用原有登记入口，本页只改状态流转相关能力'
}

async function openDetail(row: Row) {
  detail.value = row
  detailLogs.value = []
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      throw new Error('处置单详情读取失败')
    }
    const full = await response.json()
    detail.value = full as Row
    detailLogs.value = (full.处理记录 ?? []) as Log[]
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '处置单详情读取失败'
  }
}

function closeDetail() {
  detail.value = null
  detailLogs.value = []
}

function openAction(action: string, row: Row) {
  actionDialog.action = action
  actionDialog.row = row
  actionDialog.form = {}
  for (const field of editableFields) {
    actionDialog.form[field] = String(row[field] ?? '')
  }
  actionDialog.form.处理意见 = ''
  actionDialog.photoText = ''
  actionDialog.mergeIds = []
  actionDialog.error = ''
}

function closeAction() {
  if (actionDialog.saving) return
  actionDialog.action = ''
  actionDialog.row = null
  actionDialog.error = ''
}

async function submitAction() {
  const target = actionDialog.row
  if (!target) return
  actionDialog.saving = true
  actionDialog.error = ''
  const values: Record<string, string | string[]> = {}
  for (const field of [...editableFields, '处理意见']) {
    const text = actionDialog.form[field]?.trim()
    if (text) values[field] = text
  }
  const photos = actionDialog.photoText
    .split(/[,，]/)
    .map((item) => item.trim())
    .filter(Boolean)
  if (photos.length) values.处置照片 = photos

  const body: Record<string, unknown> = {
    action: actionDialog.action,
    values,
    merge_ids: actionDialog.mergeIds,
  }
  try {
    const response = await request(`${ENDPOINT}/${target.id}/actions`, {
      method: 'POST',
      body: JSON.stringify(body),
    })
    const payload = await response.json().catch(() => null)
    // 业务失败时后端返回 200 + ok:false，必须以 ok 字段为准，不能只看 HTTP 状态
    if (!response.ok || !payload || payload.ok === false) {
      throw new Error(payload?.message || '裂缝处置动作未生效，请稍后重试')
    }
    actionDialog.action = ''
    actionDialog.row = null
    if (detail.value && detail.value.id === target.id) closeDetail()
    await reload()
  } catch (error) {
    actionDialog.error = error instanceof Error ? error.message : '裂缝处置操作失败'
  } finally {
    actionDialog.saving = false
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const [pageResp, allResp] = await Promise.all([
      request(`${ENDPOINT}?${query}`),
      request(`${ENDPOINT}?size=200`),
    ])
    if (!pageResp.ok || !allResp.ok) {
      throw new Error('处置单列表读取失败')
    }
    const payload = await pageResp.json()
    const allPayload = await allResp.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    allRows.value = allPayload.items ?? []
    // 详情打开时跟着列表数据同步状态；处理记录单独再取一次最新明细
    if (detail.value) {
      const fresh = allRows.value.find((row: Row) => row.id === detail.value?.id)
      if (fresh) {
        const openId = detail.value.id
        detail.value = fresh
        try {
          const detailResp = await request(`${ENDPOINT}/${openId}`)
          if (detailResp.ok && detail.value?.id === openId) {
            const full = await detailResp.json()
            detail.value = full as Row
            detailLogs.value = (full.处理记录 ?? []) as Log[]
          }
        } catch {
          // 详情留痕刷新失败不阻塞列表
        }
      }
    }
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
  padding: 24px;
}
.modal {
  background: #fff;
  border-radius: 10px;
  width: min(720px, 100%);
  max-height: 86vh;
  overflow-y: auto;
  padding: 18px 20px;
  border: 1px solid var(--border);
}
.modal-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.modal-head h3 { margin: 0; font-size: 16px; }
.detail-grid {
  display: grid;
  grid-template-columns: 110px 1fr 110px 1fr;
  gap: 6px 12px;
  margin: 0 0 12px;
  font-size: 13px;
}
.detail-grid dt { color: var(--muted); }
.detail-grid dd { margin: 0; }
.detail-block { border-top: 1px dashed var(--border); padding-top: 10px; margin-top: 10px; }
.detail-block h4 { margin: 0 0 8px; font-size: 14px; }
.log-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.log-item { border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; font-size: 13px; }
.log-head { display: flex; flex-wrap: wrap; gap: 10px; align-items: baseline; }
.log-state { color: var(--brand); }
.log-time, .log-merge { color: var(--muted); font-size: 12px; }
.log-opinion, .log-photos { margin: 4px 0 0; }
.action-row { display: flex; gap: 8px; flex-wrap: wrap; }
.form-tip { background: #eff6ff; border: 1px solid #bfdbfe; color: #1e40af; font-size: 12px; border-radius: 6px; padding: 8px 10px; margin-bottom: 10px; }
.form-item { display: flex; flex-direction: column; gap: 4px; margin-bottom: 10px; font-size: 13px; }
.form-item > span { color: var(--muted); font-size: 12px; }
.form-item input, .form-item textarea {
  border: 1px solid var(--border); border-radius: 6px; padding: 6px 8px; font: inherit;
}
.merge-box { border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; }
.merge-box legend { color: var(--muted); font-size: 12px; padding: 0 4px; }
.merge-item { display: flex; gap: 6px; align-items: center; font-size: 13px; padding: 3px 0; }
.modal-foot { display: flex; justify-content: flex-end; gap: 8px; margin-top: 6px; }
</style>
