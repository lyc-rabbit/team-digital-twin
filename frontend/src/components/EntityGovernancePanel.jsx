import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  AlertTriangle, Check, GitMerge, Layers, Loader2, RefreshCw, ShieldAlert, Undo2, X,
} from 'lucide-react'
import { api } from '../api/client.js'

const TABS = [
  { id: 'all', label: '全部', status: 'all' },
  { id: 'pending', label: '待审核', status: 'pending_review' },
  { id: 'auto', label: '自动合并', status: 'auto' },
  { id: 'conflict', label: '冲突', status: 'conflict' },
  { id: 'done', label: '已处理', status: 'done' },
]

const TYPE_LABELS = {
  PERSON: '人员',
  ROLE: '角色',
  DEPARTMENT: '部门',
  PROJECT: '项目',
  RESOURCE: '资源',
  KNOWLEDGE: '知识',
  EVENT: '事件',
  ORG_GROUP: '非正式组织',
  Person: '人员',
  Role: '角色',
  Department: '部门',
  Project: '项目',
  Resource: '资源',
  Knowledge: '知识',
  Event: '事件',
  InformalGroup: '非正式组织',
}

const FIELD_LABELS = {
  name: '名称',
  title: '标题',
  owner: '负责人',
  members: '参与成员',
  time: '时间',
  resources: '资源',
  knowledge: '知识',
  embedding: '语义',
  graph: '图结构',
  unique_id: '唯一ID',
  email: '邮箱',
  account: '账号',
  org_context: '组织上下文',
  url: 'URL/仓库',
  type: '类型',
  project: '项目',
  tech: '技术栈',
  topic: '主题',
  author: '作者',
  citation: '引用',
  subject: '主体',
  object: '对象',
  action: '动作',
  source: '来源',
  project_id: '项目ID',
  semantic: '语义',
}

const STATUS_LABEL = {
  pending: '待审核',
  auto_merged: '已自动合并',
  merged: '已合并',
  rejected: '已拒绝',
  skipped: '暂不处理',
}

function pct(v) {
  if (v == null || Number.isNaN(Number(v))) return '—'
  return `${Math.round(Number(v) * 100)}%`
}

export default function EntityGovernancePanel() {
  const [overview, setOverview] = useState(null)
  const [tab, setTab] = useState('pending')
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [merges, setMerges] = useState([])
  const [loading, setLoading] = useState(true)
  const [detecting, setDetecting] = useState(false)
  const [error, setError] = useState(null)
  const [detail, setDetail] = useState(null)
  const [detectResult, setDetectResult] = useState(null)

  const loadOverview = useCallback(async () => {
    const [ov, mergeList] = await Promise.all([
      api.getEntityGovernanceOverview(),
      api.listEntityMerges(true),
    ])
    setOverview(ov)
    setMerges(mergeList.items || [])
  }, [])

  const loadCandidates = useCallback(async () => {
    const status = TABS.find((t) => t.id === tab)?.status || 'all'
    const data = await api.listEntityCandidates({ status, page: 1, pageSize: 80 })
    setItems(data.items || [])
    setTotal(data.total || 0)
  }, [tab])

  const reload = useCallback(async () => {
    setError(null)
    await Promise.all([loadOverview(), loadCandidates()])
  }, [loadOverview, loadCandidates])

  useEffect(() => {
    setLoading(true)
    reload().catch((e) => setError(e.message || '加载失败')).finally(() => setLoading(false))
  }, [reload])

  const handleDetect = async () => {
    setDetecting(true)
    setError(null)
    try {
      const res = await api.detectEntityDuplicates({
        entityTypes: ['PERSON', 'PROJECT', 'RESOURCE', 'KNOWLEDGE', 'EVENT', 'ORG_GROUP'],
        force: true,
        autoMerge: true,
      })
      setDetectResult(res)
      await reload()
    } catch (e) {
      setError(e.message || '检测失败')
    } finally {
      setDetecting(false)
    }
  }

  const openDetail = async (id) => {
    try {
      const data = await api.getEntityCandidate(id)
      setDetail(data)
    } catch (e) {
      setError(e.message || '加载候选失败')
    }
  }

  if (loading && !overview) {
    return (
      <div className="flex items-center justify-center h-full text-slate-400 text-sm">
        <Loader2 size={16} className="animate-spin mr-2" />加载实体治理...
      </div>
    )
  }

  return (
    <div className="p-6 max-w-6xl mx-auto fade-in space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
            <Layers size={20} className="text-brand-600" /> 实体治理
          </h2>
          <p className="text-sm text-slate-500 mt-1">
            统一实体层：Canonical + Alias + 证据 + 合并历史。不删除重复节点，合并后重算影响力。
          </p>
        </div>
        <button
          type="button"
          onClick={handleDetect}
          disabled={detecting}
          className="flex items-center gap-1.5 text-sm font-medium text-white bg-brand-600 hover:bg-brand-700 disabled:opacity-50 px-3.5 py-2 rounded-lg"
        >
          {detecting ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
          检测重复实体
        </button>
      </div>

      {error && <div className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</div>}

      {overview && <OverviewCards overview={overview} />}

      {detectResult?.status === 'success' && (
        <div className="bg-emerald-50 border border-emerald-100 rounded-xl px-4 py-3 text-sm text-emerald-800">
          已扫描 {detectResult.scanned} 个节点，发现 {detectResult.candidate_pairs} 组候选
          （自动合并 {detectResult.auto_merged} · 待审核 {detectResult.review} · 冲突 {detectResult.conflicts}）
        </div>
      )}

      {!!(detectResult?.influence_delta || []).length && (
        <InfluenceDelta items={detectResult.influence_delta} />
      )}

      <section className="bg-white rounded-2xl border border-slate-100 shadow-sm">
        <div className="flex gap-1 p-2 border-b border-slate-100">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium ${
                tab === t.id ? 'bg-brand-600 text-white' : 'text-slate-500 hover:bg-slate-50'
              }`}
            >
              {t.label}
            </button>
          ))}
          <span className="ml-auto self-center text-[11px] text-slate-400 px-2">{total} 组</span>
        </div>
        <CandidateTable items={items} onOpen={openDetail} />
      </section>

      <MergeHistory
        merges={merges}
        onUnmerge={async (id) => {
          try {
            await api.unmergeEntities(id)
            await reload()
          } catch (e) {
            setError(e.message || '撤销失败')
          }
        }}
      />

      {detail && (
        <CompareModal
          detail={detail}
          onClose={() => setDetail(null)}
          onDone={async () => {
            setDetail(null)
            await reload()
          }}
          onError={setError}
        />
      )}
    </div>
  )
}

function OverviewCards({ overview }) {
  const cards = [
    { label: '总实体', value: overview.total_entities },
    { label: 'Canonical', value: overview.canonical_entities },
    { label: 'Alias', value: overview.alias_count },
    { label: '已合并', value: overview.merged_count },
    { label: '待审核', value: overview.pending_review },
    { label: '冲突', value: overview.conflicts },
  ]
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
        {cards.map((c) => (
          <div key={c.label} className="bg-white rounded-2xl border border-slate-100 p-4">
            <div className="text-[11px] text-slate-400">{c.label}</div>
            <div className="text-xl font-bold text-slate-800 mt-1">{c.value ?? 0}</div>
          </div>
        ))}
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
        <Metric label="实体重复率" value={`${overview.duplicate_rate_pct ?? 0}%`} />
        <Metric label="解析率" value={pct(overview.resolution_rate)} />
        <Metric label="冲突率" value={pct(overview.conflict_rate)} />
        <Metric label="误合并率" value={pct(overview.false_merge_rate)} />
      </div>
    </div>
  )
}

function Metric({ label, value }) {
  return (
    <div className="bg-slate-50 rounded-xl px-3 py-2 text-slate-600">
      <span className="text-slate-400">{label}</span>
      <span className="ml-2 font-semibold text-slate-800">{value}</span>
    </div>
  )
}

function CandidateTable({ items, onOpen }) {
  if (!items.length) {
    return <p className="text-xs text-slate-400 p-6">暂无候选。点击「检测重复实体」扫描当前图谱。</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-[11px] text-slate-400 border-b border-slate-100">
          <tr>
            <th className="text-left font-medium px-4 py-2">实体 A</th>
            <th className="text-left font-medium px-4 py-2">实体 B</th>
            <th className="text-left font-medium px-4 py-2">类型</th>
            <th className="text-left font-medium px-4 py-2">匹配度</th>
            <th className="text-left font-medium px-4 py-2">状态</th>
          </tr>
        </thead>
        <tbody>
          {items.map((row) => (
            <tr
              key={row.candidate_id}
              onClick={() => onOpen(row.candidate_id)}
              className="border-b border-slate-50 hover:bg-slate-50 cursor-pointer"
            >
              <td className="px-4 py-2.5 font-medium text-slate-800">{row.entity_a?.name || row.entity_a_id}</td>
              <td className="px-4 py-2.5 text-slate-700">{row.entity_b?.name || row.entity_b_id}</td>
              <td className="px-4 py-2.5 text-slate-500">{TYPE_LABELS[row.entity_type] || row.entity_type}</td>
              <td className="px-4 py-2.5 font-semibold text-brand-700">{pct(row.score)}</td>
              <td className="px-4 py-2.5">
                <StatusChip decision={row.decision} status={row.status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function StatusChip({ decision, status }) {
  if (decision === 'FORCE_REVIEW' && status === 'pending') {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] text-red-700 bg-red-50 px-2 py-0.5 rounded-full">
        <ShieldAlert size={11} /> 冲突
      </span>
    )
  }
  const map = {
    pending: 'text-amber-700 bg-amber-50',
    auto_merged: 'text-emerald-700 bg-emerald-50',
    merged: 'text-emerald-700 bg-emerald-50',
    rejected: 'text-slate-500 bg-slate-100',
    skipped: 'text-slate-500 bg-slate-100',
  }
  return (
    <span className={`text-[11px] px-2 py-0.5 rounded-full ${map[status] || 'bg-slate-100 text-slate-500'}`}>
      {STATUS_LABEL[status] || status}
    </span>
  )
}

function CompareModal({ detail, onClose, onDone, onError }) {
  const rec = detail.recommended_canonical
  const [canonical, setCanonical] = useState(rec?.entity_id || detail.entity_a_id)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const a = detail.entityA || {}
  const b = detail.entityB || {}
  const scores = detail.field_scores || {}

  const sourceId = canonical === a.id ? b.id : a.id
  const targetId = canonical

  const run = async (fn) => {
    setBusy(true)
    try {
      await fn()
      await onDone()
    } catch (e) {
      onError(e.message || '操作失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl w-full max-w-3xl p-5 shadow-xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-bold text-slate-800">疑似重复实体</h3>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-600"><X size={16} /></button>
        </div>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <EntityCard title="实体 A" node={a} aliases={detail.aliasesA} evidence={detail.evidenceA} />
          <EntityCard title="实体 B" node={b} aliases={detail.aliasesB} evidence={detail.evidenceB} />
        </div>

        <div className="mt-4 bg-slate-50 rounded-xl p-3 space-y-1.5">
          {Object.entries(scores).map(([k, v]) => (
            <div key={k} className="flex items-center gap-2 text-xs">
              <span className="w-24 text-slate-500">{FIELD_LABELS[k] || k}</span>
              <div className="flex-1 h-1.5 bg-slate-200 rounded-full overflow-hidden">
                <div className="h-full bg-brand-500" style={{ width: `${Math.round(Number(v) * 100)}%` }} />
              </div>
              <span className="w-10 text-right font-semibold text-slate-700">{pct(v)}</span>
            </div>
          ))}
          <div className="pt-1 text-sm font-bold text-slate-800">综合匹配：{pct(detail.score)}</div>
        </div>

        {!!(detail.conflicts || []).length && (
          <div className="mt-3 text-xs bg-red-50 text-red-700 rounded-xl p-3 space-y-1">
            {(detail.conflicts || []).map((c, i) => (
              <div key={i} className="flex gap-1"><AlertTriangle size={12} className="mt-0.5 flex-shrink-0" />{c.message}</div>
            ))}
          </div>
        )}

        {rec && (
          <p className="text-xs text-slate-500 mt-3">
            系统推荐主实体：<b>{rec.name}</b>
            {rec.reasons?.length ? `（${rec.reasons.join('、')}）` : ''}
          </p>
        )}

        <div className="mt-3 text-sm">
          <div className="text-xs font-bold text-slate-600 mb-1">请选择 Canonical Entity</div>
          {[a, b].map((n) => n?.id && (
            <label key={n.id} className="flex items-center gap-2 py-1">
              <input type="radio" name="canonical" checked={canonical === n.id} onChange={() => setCanonical(n.id)} />
              {n.name}
            </label>
          ))}
        </div>
        <input
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="合并理由（可选）"
          className="mt-2 w-full text-sm border border-slate-200 rounded-lg px-3 py-2 outline-none focus:border-brand-400"
        />

        <div className="flex flex-wrap justify-end gap-2 mt-4">
          <button
            type="button"
            disabled={busy}
            onClick={() => run(() => api.skipEntityCandidate({ candidateId: detail.candidate_id }))}
            className="text-sm px-3 py-2 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50"
          >
            暂不处理
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => run(() => api.rejectEntityCandidate({
              candidateId: detail.candidate_id,
              reason: reason || '不是同一实体',
            }))}
            className="text-sm px-3 py-2 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50"
          >
            不是同一实体
          </button>
          <button
            type="button"
            disabled={busy || !sourceId || !targetId}
            onClick={() => run(() => api.mergeEntities({
              sourceEntityId: sourceId,
              targetEntityId: targetId,
              candidateId: detail.candidate_id,
              reason: reason || '人工确认同一实体',
            }))}
            className="flex items-center gap-1.5 text-sm font-medium text-white bg-brand-600 hover:bg-brand-700 disabled:opacity-50 px-3.5 py-2 rounded-lg"
          >
            {busy ? <Loader2 size={14} className="animate-spin" /> : <GitMerge size={14} />}
            合并
          </button>
        </div>
      </div>
    </div>
  )
}

function EntityCard({ title, node, aliases, evidence }) {
  return (
    <div className="border border-slate-100 rounded-xl p-3">
      <div className="text-[11px] text-slate-400">{title}</div>
      <div className="font-bold text-slate-800">{node.name}</div>
      <div className="text-xs text-slate-500 mt-1 space-y-0.5">
        <div>类型：{TYPE_LABELS[node.type] || node.type}</div>
        {node.department && <div>部门：{node.department}</div>}
        {node.position && <div>角色：{node.position}</div>}
        {node.owner && <div>负责人：{node.owner}</div>}
        {node.time && <div>时间：{node.time}</div>}
        {node.domain && <div>领域：{node.domain}</div>}
        {node.category && <div>类别：{node.category}</div>}
        {node.url && <div>URL：{node.url}</div>}
        <div>状态：{node.entity_status}</div>
      </div>
      {!!(aliases || []).length && (
        <div className="mt-2 text-[11px] text-slate-500">
          别名：{(aliases || []).map((x) => x.value).join('、')}
        </div>
      )}
      {!!(evidence || []).length && (
        <div className="mt-2 text-[11px] text-slate-400">
          证据 {(evidence || []).slice(0, 3).map((e) => e.snippet || e.source_type).filter(Boolean).join(' · ')}
        </div>
      )}
    </div>
  )
}

function MergeHistory({ merges, onUnmerge }) {
  const active = useMemo(() => (merges || []).filter((m) => !m.unmerged), [merges])
  if (!active.length) {
    return (
      <section className="bg-white rounded-2xl border border-slate-100 p-5">
        <h3 className="text-sm font-bold text-slate-800 mb-1">合并历史</h3>
        <p className="text-xs text-slate-400">暂无合并记录。所有自动/人工操作都会留痕。</p>
      </section>
    )
  }
  return (
    <section className="bg-white rounded-2xl border border-slate-100 p-5">
      <h3 className="text-sm font-bold text-slate-800 mb-3">合并历史</h3>
      <div className="space-y-2">
        {active.slice(0, 20).map((m) => (
          <div key={m.merge_id} className="flex items-start justify-between gap-3 text-sm border border-slate-100 rounded-xl px-3 py-2">
            <div>
              <div className="text-slate-800">
                {m.source_entity_id} → {m.target_entity_id}
                {m.score != null && <span className="text-slate-400 text-xs ml-2">{pct(m.score)}</span>}
              </div>
              <div className="text-[11px] text-slate-400 mt-0.5">
                {m.operator} · {m.created_at} · {m.reason}
              </div>
              {!!(m.influence_delta || []).length && (
                <div className="text-[11px] text-emerald-700 mt-1">
                  影响力变化：{(m.influence_delta || []).slice(0, 3).map((d) => `${d.name} ${d.before}→${d.after}`).join('；')}
                </div>
              )}
            </div>
            <button
              type="button"
              onClick={() => onUnmerge(m.merge_id)}
              className="flex items-center gap-1 text-xs text-slate-500 hover:text-brand-700 flex-shrink-0"
            >
              <Undo2 size={12} /> 撤销合并
            </button>
          </div>
        ))}
      </div>
    </section>
  )
}

function InfluenceDelta({ items }) {
  return (
    <section className="bg-white rounded-2xl border border-slate-100 p-5">
      <h3 className="text-sm font-bold text-slate-800 mb-2 flex items-center gap-1.5">
        <Check size={14} className="text-emerald-600" /> 影响力重算
      </h3>
      <div className="space-y-1 text-xs text-slate-600">
        {items.slice(0, 8).map((d) => (
          <div key={d.id}>
            {d.name}：{d.before ?? '—'} → {d.after ?? '—'}
            {d.reason ? `（${d.reason}）` : ''}
          </div>
        ))}
      </div>
    </section>
  )
}
