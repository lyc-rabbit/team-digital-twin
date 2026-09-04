import React, { useCallback, useEffect, useState } from 'react'
import {
  AlertTriangle, Check, FileSearch, Loader2, Plus, ScrollText, Trash2, X,
} from 'lucide-react'
import { api } from '../api/client.js'

const TABS = [
  { id: 'all', label: '全部事实', status: 'all' },
  { id: 'pending', label: '待确认', status: 'pending' },
  { id: 'CONFIRMED', label: '已确认', status: 'CONFIRMED' },
  { id: 'DELETED', label: '已删除', status: 'DELETED' },
  { id: 'conflicts', label: '冲突事实' },
  { id: 'jobs', label: '抽取任务' },
]

const STATUS_LABEL = {
  EXTRACTED: '待确认',
  CONFIRMED: '已确认',
  REJECTED: '已驳回',
  CONFLICT: '冲突',
  SUPERSEDED: '已替代',
  DELETED: '已删除',
}

const STATUS_CLASS = {
  EXTRACTED: 'bg-amber-50 text-amber-700',
  CONFIRMED: 'bg-emerald-50 text-emerald-700',
  REJECTED: 'bg-slate-100 text-slate-500',
  CONFLICT: 'bg-red-50 text-red-700',
  SUPERSEDED: 'bg-violet-50 text-violet-700',
  DELETED: 'bg-slate-100 text-slate-400',
}

const IMPACT_TONE = {
  must_delete: 'text-red-700 bg-red-50',
  recompute: 'text-orange-700 bg-orange-50',
  stale: 'text-amber-800 bg-amber-50',
  none: 'text-emerald-700 bg-emerald-50',
}

function pct(v) {
  if (v == null || Number.isNaN(Number(v))) return '—'
  return `${Math.round(Number(v) * 100)}%`
}

function day(v) {
  if (!v) return '—'
  return String(v).replace('T', ' ').slice(0, 16)
}

export default function FactGovernancePanel() {
  const [tab, setTab] = useState('all')
  const [overview, setOverview] = useState(null)
  const [list, setList] = useState([])
  const [total, setTotal] = useState(0)
  const [conflicts, setConflicts] = useState([])
  const [jobs, setJobs] = useState([])
  const [q, setQ] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [detail, setDetail] = useState(null)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [deleteOpts, setDeleteOpts] = useState({
    delete_fact: true,
    delete_direct_relations: true,
    stale_downstream: true,
    auto_rebuild: false,
    reason: '',
  })
  const [showCreate, setShowCreate] = useState(false)
  const [showExtract, setShowExtract] = useState(false)
  const [supersedeOf, setSupersedeOf] = useState(null)

  const load = useCallback(async () => {
    setError('')
    const ov = await api.getFactOverview()
    setOverview(ov)
    if (tab === 'conflicts') {
      const c = await api.listFactConflicts()
      setConflicts(c.items || [])
      setList([])
    } else if (tab === 'jobs') {
      const j = await api.listFactJobs()
      setJobs(j.items || [])
      setList([])
    } else {
      const spec = TABS.find((t) => t.id === tab)
      const data = await api.listFacts({ status: spec?.status || 'all', q, pageSize: 80 })
      setList(data.items || [])
      setTotal(data.total || 0)
    }
  }, [tab, q])

  useEffect(() => {
    setLoading(true)
    load().catch((e) => setError(e.message)).finally(() => setLoading(false))
  }, [load])

  const run = async (fn) => {
    setBusy(true)
    setError('')
    try {
      const r = await fn()
      await load()
      return r
    } catch (e) {
      setError(e.message)
      throw e
    } finally {
      setBusy(false)
    }
  }

  const openDetail = async (id) => {
    const d = await api.getFact(id)
    setDetail(d)
  }

  return (
    <div className="p-6 max-w-6xl mx-auto fade-in space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
            <ScrollText size={20} className="text-brand-600" /> 事实管理
          </h2>
          <p className="text-sm text-slate-500 mt-1">
            事实是图谱与分析的上游证据。记录事件、关系抽取、本页录入都先落到这里；确认后才写图谱。不能直接改，只能删除旧事实再建新事实。
          </p>
          {overview?.legacy?.imported ? (
            <p className="text-[11px] text-emerald-700 mt-1">
              已从现有图谱/时态层导入 {overview.legacy.imported} 条历史事实。
            </p>
          ) : null}
        </div>
        <div className="flex gap-2 shrink-0">
          <button
            type="button"
            onClick={() => setShowExtract(true)}
            className="text-xs px-3 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 flex items-center gap-1"
          >
            <FileSearch size={12} /> 抽取事实
          </button>
          <button
            type="button"
            onClick={() => setShowCreate(true)}
            className="text-xs px-3 py-1.5 rounded-lg bg-brand-600 text-white hover:bg-brand-700 flex items-center gap-1"
          >
            <Plus size={12} /> 录入事实
          </button>
        </div>
      </div>

      {error ? <div className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</div> : null}

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Stat label="事实总数" value={overview?.total ?? 0} />
        <Stat label="待确认" value={overview?.pending ?? 0} />
        <Stat label="冲突" value={overview?.conflicts ?? 0} />
        <Stat label="最近新增" value={overview?.recent_new ?? 0} />
        <Stat label="最近变更" value={overview?.recent_changed ?? 0} />
      </div>

      <div className="flex flex-wrap gap-1 bg-slate-50 rounded-xl p-1 w-fit">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={`text-xs px-3 py-1.5 rounded-lg ${tab === t.id ? 'bg-white shadow-sm text-slate-800 font-semibold' : 'text-slate-500'}`}
          >
            {t.label}
            {t.id === 'pending' && overview?.pending ? ` (${overview.pending})` : ''}
            {t.id === 'conflicts' && overview?.conflicts ? ` (${overview.conflicts})` : ''}
          </button>
        ))}
      </div>

      {tab !== 'conflicts' && tab !== 'jobs' ? (
        <input
          className="text-xs border rounded-lg px-3 py-1.5 w-full max-w-md"
          placeholder="搜索主体 / 谓词 / 客体"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      ) : null}

      {loading ? (
        <div className="text-slate-400 text-sm flex items-center gap-2 py-8">
          <Loader2 size={14} className="animate-spin" />加载事实…
        </div>
      ) : null}

      {tab === 'conflicts' ? (
        <section className="bg-white rounded-2xl border border-slate-100 divide-y divide-slate-50">
          {(conflicts || []).length ? conflicts.map((c) => (
            <div key={c.conflict_id} className="p-4 text-sm space-y-2">
              <div className="text-xs text-red-600 flex items-center gap-1">
                <AlertTriangle size={12} /> {c.reason}
              </div>
              <div className="grid md:grid-cols-2 gap-3">
                {[c.fact_a, c.fact_b].map((f) => f ? (
                  <button key={f.fact_id} type="button" className="text-left border rounded-xl p-3 hover:bg-slate-50" onClick={() => openDetail(f.fact_id)}>
                    <Triple fact={f} />
                    <div className="text-[11px] text-slate-400 mt-1">{STATUS_LABEL[f.status]} · {day(f.valid_from)} ~ {day(f.valid_to)}</div>
                  </button>
                ) : null)}
              </div>
            </div>
          )) : <p className="p-5 text-xs text-slate-400">没有开放冲突。时间不重叠的「负责」关系不算冲突。</p>}
        </section>
      ) : null}

      {tab === 'jobs' ? (
        <section className="bg-white rounded-2xl border border-slate-100 divide-y divide-slate-50">
          {(jobs || []).length ? jobs.map((j) => (
            <div key={j.job_id} className="px-4 py-3 text-sm flex justify-between gap-3">
              <div>
                <div className="font-medium text-slate-800">{j.source_title || '未命名文档'}</div>
                <div className="text-[11px] text-slate-400">{j.source_type} · {j.model || '—'} · {j.fact_count} 条事实 · {day(j.created_at)}</div>
              </div>
              <span className="text-[11px] text-slate-500">{j.status}</span>
            </div>
          )) : <p className="p-5 text-xs text-slate-400">还没有抽取任务。用「抽取事实」从文档生成待确认事实，不会直接写图谱。</p>}
        </section>
      ) : null}

      {tab !== 'conflicts' && tab !== 'jobs' ? (
        <section className="bg-white rounded-2xl border border-slate-100 overflow-hidden">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 text-slate-500">
              <tr>
                <th className="px-3 py-2 font-medium">状态</th>
                <th className="px-3 py-2 font-medium">主体</th>
                <th className="px-3 py-2 font-medium">关系</th>
                <th className="px-3 py-2 font-medium">客体</th>
                <th className="px-3 py-2 font-medium">时间</th>
                <th className="px-3 py-2 font-medium">来源</th>
                <th className="px-3 py-2 font-medium">置信</th>
                <th className="px-3 py-2 font-medium">下游</th>
              </tr>
            </thead>
            <tbody>
              {list.length ? list.map((f) => (
                <tr key={f.fact_id} className="border-t border-slate-50 hover:bg-slate-50/80 cursor-pointer" onClick={() => openDetail(f.fact_id)}>
                  <td className="px-3 py-2">
                    <span className={`px-1.5 py-0.5 rounded ${STATUS_CLASS[f.status] || 'bg-slate-50'}`}>{STATUS_LABEL[f.status] || f.status}</span>
                  </td>
                  <td className="px-3 py-2 text-slate-800">{f.subject}</td>
                  <td className="px-3 py-2 font-mono text-brand-700">{f.predicate}</td>
                  <td className="px-3 py-2">{f.object}</td>
                  <td className="px-3 py-2 text-slate-500 whitespace-nowrap">{(f.valid_from || '').slice(0, 10) || '不限'} ~ {(f.valid_to || '').slice(0, 10) || '永久'}</td>
                  <td className="px-3 py-2 text-slate-500 truncate max-w-[140px]">{(f.sources || [])[0]?.title || f.extract_method || '—'}</td>
                  <td className="px-3 py-2">{pct(f.confidence)}</td>
                  <td className="px-3 py-2 text-blue-600">{f.downstream_count || 0}</td>
                </tr>
              )) : (
                <tr><td colSpan={8} className="px-3 py-8 text-center text-slate-400">没有事实。可记录事件、从文档抽取，或在本页录入。</td></tr>
              )}
            </tbody>
          </table>
          {total > list.length ? <div className="text-[11px] text-slate-400 px-3 py-2">共 {total} 条</div> : null}
        </section>
      ) : null}

      {detail ? (
        <FactDetail
          fact={detail}
          busy={busy}
          onClose={() => setDetail(null)}
          onConfirm={() => run(() => api.confirmFact(detail.fact_id)).then((d) => setDetail(d))}
          onReject={() => run(() => api.rejectFact(detail.fact_id)).then(() => setDetail(null))}
          onDelete={() => {
            setDeleteTarget(detail)
            setDeleteOpts((o) => ({ ...o, reason: '' }))
          }}
          onSupersede={() => setSupersedeOf(detail)}
        />
      ) : null}

      {deleteTarget ? (
        <DeleteModal
          fact={deleteTarget}
          opts={deleteOpts}
          setOpts={setDeleteOpts}
          busy={busy}
          onClose={() => setDeleteTarget(null)}
          onConfirm={() => run(async () => {
            await api.deleteFact(deleteTarget.fact_id, deleteOpts)
            setDeleteTarget(null)
            setDetail(null)
          })}
        />
      ) : null}

      {showCreate ? (
        <FactForm
          title="录入事实"
          busy={busy}
          onClose={() => setShowCreate(false)}
          onSubmit={(data) => run(async () => {
            await api.createFact(data)
            setShowCreate(false)
          })}
        />
      ) : null}

      {supersedeOf ? (
        <FactForm
          title={`用新事实替代 ${supersedeOf.fact_id}（旧事实将失效，不会原地修改）`}
          busy={busy}
          initial={supersedeOf}
          onClose={() => setSupersedeOf(null)}
          onSubmit={(data) => run(async () => {
            const r = await api.supersedeFact(supersedeOf.fact_id, data)
            setSupersedeOf(null)
            setDetail(r.new)
          })}
        />
      ) : null}

      {showExtract ? (
        <ExtractModal
          busy={busy}
          onClose={() => setShowExtract(false)}
          onSubmit={(data) => run(async () => {
            await api.extractFacts(data)
            setShowExtract(false)
            setTab('pending')
          })}
        />
      ) : null}
    </div>
  )
}

function Stat({ label, value }) {
  return (
    <div className="bg-white rounded-2xl border border-slate-100 px-4 py-3">
      <div className="text-[11px] text-slate-400">{label}</div>
      <div className="text-xl font-bold text-slate-800 mt-0.5">{value}</div>
    </div>
  )
}

function Triple({ fact }) {
  return (
    <div className="text-sm text-slate-800">
      <span className="font-semibold">{fact.subject}</span>
      <span className="mx-1 font-mono text-brand-700">{fact.predicate}</span>
      <span className="font-semibold">{fact.object}</span>
    </div>
  )
}

function FactDetail({ fact, busy, onClose, onConfirm, onReject, onDelete, onSupersede }) {
  const impact = fact.impact || {}
  const groups = impact.groups || {}
  const open = fact.status === 'EXTRACTED' || fact.status === 'CONFLICT'
  return (
    <div className="fixed inset-0 z-50 bg-slate-900/40 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-3xl max-h-[90vh] overflow-hidden flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between px-5 py-4 border-b border-slate-100">
          <div>
            <div className="text-sm font-bold text-slate-800">事实 {fact.fact_id}</div>
            <Triple fact={fact} />
          </div>
          <button type="button" onClick={onClose} className="text-slate-400 p-1"><X size={16} /></button>
        </div>
        <div className="overflow-auto px-5 py-4 space-y-5 text-sm">
          <Section title="① 事实本身">
            <KV k="状态" v={STATUS_LABEL[fact.status] || fact.status} />
            <KV k="主体" v={`${fact.subject}${fact.subject_type ? ` · ${fact.subject_type}` : ''}`} />
            <KV k="谓词" v={`${fact.predicate}${fact.ontology_relation ? ` → ${fact.ontology_relation}` : ''}`} />
            <KV k="客体" v={`${fact.object}${fact.object_type ? ` · ${fact.object_type}` : ''}`} />
            <KV k="现实有效时间" v={`${fact.valid_from || '不限'} ~ ${fact.valid_to || '永久'}`} />
            <KV k="抽取时间" v={day(fact.extracted_at || fact.created_at)} />
            <KV k="确认时间" v={day(fact.confirmed_at)} />
          </Section>
          <Section title="② 证据">
            {(fact.sources || []).length ? (fact.sources || []).map((s) => (
              <div key={s.source_id} className="bg-slate-50 rounded-lg px-3 py-2 mb-2">
                <div className="text-xs text-slate-500">{s.source_type} · {s.title || '—'}{s.page ? ` · 第 ${s.page} 页` : ''}</div>
                <p className="text-xs text-slate-700 mt-1 whitespace-pre-wrap">{s.source_text || '无原文片段'}</p>
              </div>
            )) : <p className="text-xs text-slate-400">没有挂载来源。</p>}
          </Section>
          <Section title="③ 抽取信息">
            <KV k="方法" v={fact.extract_method || '—'} />
            <KV k="模型" v={fact.extract_model || '—'} />
            <KV k="置信度" v={pct(fact.confidence)} />
            {(fact.entity_bindings || []).map((b) => (
              <KV key={b.binding_id} k={b.role === 'subject' ? '主体对齐' : '客体对齐'} v={`${b.mention} → ${b.graph_node_id || '未对齐'} (${b.entity_type || ''})`} />
            ))}
          </Section>
          <Section title="④ 被哪些图谱对象使用">
            {(fact.relation_bindings || []).length ? (fact.relation_bindings || []).map((b) => (
              <div key={b.binding_id} className="text-xs font-mono text-slate-700">{b.source_node_id} —{b.relation}→ {b.target_node_id}</div>
            )) : <p className="text-xs text-slate-400">尚未写入图谱。确认后才会映射实例和关系。</p>}
            {(fact.lineage?.children || []).filter((c) => c.link_kind === 'DIRECT').map((c) => (
              <div key={c.derived_id} className="text-xs text-slate-600">直接 · {c.kind} · {c.title}</div>
            ))}
          </Section>
          <Section title="⑤ 下游影响">
            <div className="text-[11px] text-slate-400 mb-2">影响 {impact.downstream_count || 0} 项 · 直接 {impact.direct_count || 0} · 间接 {impact.indirect_count || 0}</div>
            {['must_delete', 'recompute', 'stale', 'none'].map((level) => (
              (groups[level] || []).length ? (
                <div key={level} className="mb-2">
                  {(groups[level] || []).map((g, i) => (
                    <div key={g.derived_id || i} className={`text-xs rounded-lg px-2 py-1 mb-1 ${IMPACT_TONE[level] || ''}`}>
                      {g.label} · {g.kind_label || g.kind} · {g.title}
                    </div>
                  ))}
                </div>
              ) : null
            ))}
            {(fact.lineage?.children || []).length ? (
              <div className="text-[11px] text-slate-500 font-mono whitespace-pre-wrap mt-2">
                {fact.fact_id}{'\n'}{(fact.lineage.children || []).map((c) => `  └─ ${c.kind} ${c.title}`).join('\n')}
              </div>
            ) : null}
          </Section>
        </div>
        <div className="px-5 py-3 border-t border-slate-100 flex flex-wrap gap-2">
          {open ? (
            <>
              <button type="button" disabled={busy} onClick={onConfirm} className="text-xs px-3 py-1.5 rounded-lg bg-emerald-50 text-emerald-700 flex items-center gap-1 disabled:opacity-50">
                <Check size={12} /> 确认并写入图谱
              </button>
              <button type="button" disabled={busy} onClick={onReject} className="text-xs px-3 py-1.5 rounded-lg bg-slate-50 text-slate-500">驳回</button>
            </>
          ) : null}
          {fact.status !== 'DELETED' && fact.status !== 'SUPERSEDED' ? (
            <>
              <button type="button" disabled={busy} onClick={onSupersede} className="text-xs px-3 py-1.5 rounded-lg border border-slate-200">用新事实替代</button>
              <button type="button" disabled={busy} onClick={onDelete} className="text-xs px-3 py-1.5 rounded-lg bg-red-50 text-red-700 flex items-center gap-1">
                <Trash2 size={12} /> 删除
              </button>
            </>
          ) : null}
        </div>
      </div>
    </div>
  )
}

function Section({ title, children }) {
  return (
    <div>
      <div className="text-xs font-semibold text-slate-700 mb-2">{title}</div>
      <div className="space-y-1">{children}</div>
    </div>
  )
}

function KV({ k, v }) {
  return (
    <div className="flex gap-2 text-xs">
      <span className="text-slate-400 w-24 shrink-0">{k}</span>
      <span className="text-slate-800 break-all">{v || '—'}</span>
    </div>
  )
}

function DeleteModal({ fact, opts, setOpts, busy, onClose, onConfirm }) {
  const impact = fact.impact || {}
  const toggle = (key) => setOpts((o) => ({ ...o, [key]: !o[key] }))
  return (
    <div className="fixed inset-0 z-[60] bg-slate-900/50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg p-5 space-y-3" onClick={(e) => e.stopPropagation()}>
        <div className="text-sm font-bold text-slate-800">删除事实 {fact.fact_id}？</div>
        <p className="text-xs text-slate-600">该事实当前被 {impact.downstream_count || 0} 个对象引用。直接依赖 {impact.direct_count || 0}，间接 {impact.indirect_count || 0}。</p>
        <p className="text-[11px] text-slate-400">不会物理删除记录。下游默认标为失效并生成待重建任务，不自动重跑分析。</p>
        <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={opts.delete_fact} onChange={() => toggle('delete_fact')} /> 删除事实（软删除）</label>
        <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={opts.delete_direct_relations} onChange={() => toggle('delete_direct_relations')} /> 删除直接派生关系</label>
        <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={opts.stale_downstream} onChange={() => toggle('stale_downstream')} /> 标记下游结果失效</label>
        <label className="flex items-center gap-2 text-xs text-slate-400"><input type="checkbox" checked={opts.auto_rebuild} onChange={() => toggle('auto_rebuild')} /> 自动重新分析（不推荐默认开启）</label>
        <input className="w-full border rounded-lg px-2 py-1.5 text-xs" placeholder="删除原因" value={opts.reason} onChange={(e) => setOpts((o) => ({ ...o, reason: e.target.value }))} />
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="text-xs px-3 py-1.5 rounded-lg border">取消</button>
          <button type="button" disabled={busy} onClick={onConfirm} className="text-xs px-3 py-1.5 rounded-lg bg-red-600 text-white disabled:opacity-50">确认删除</button>
        </div>
      </div>
    </div>
  )
}

function FactForm({ title, initial, busy, onClose, onSubmit }) {
  const [form, setForm] = useState({
    subject: initial?.subject || '',
    predicate: initial?.predicate || '',
    object: initial?.object || '',
    subject_type: initial?.subject_type || 'Person',
    object_type: initial?.object_type || 'Project',
    valid_from: (initial?.valid_from || '').slice(0, 10),
    valid_to: (initial?.valid_to || '').slice(0, 10),
    source_title: initial?.sources?.[0]?.title || '',
    source_text: initial?.sources?.[0]?.source_text || '',
    page: initial?.sources?.[0]?.page || '',
    confidence: initial?.confidence ?? 1,
  })
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }))
  return (
    <div className="fixed inset-0 z-50 bg-slate-900/40 flex items-center justify-center p-4" onClick={onClose}>
      <form
        className="bg-white rounded-2xl shadow-xl w-full max-w-lg p-5 space-y-3"
        onClick={(e) => e.stopPropagation()}
        onSubmit={(e) => { e.preventDefault(); onSubmit(form) }}
      >
        <div className="text-sm font-bold text-slate-800">{title}</div>
        <div className="grid grid-cols-3 gap-2">
          <input className="border rounded-lg px-2 py-1.5 text-xs" placeholder="主体" required value={form.subject} onChange={(e) => set('subject', e.target.value)} />
          <input className="border rounded-lg px-2 py-1.5 text-xs" placeholder="谓词，如负责" required value={form.predicate} onChange={(e) => set('predicate', e.target.value)} />
          <input className="border rounded-lg px-2 py-1.5 text-xs" placeholder="客体" required value={form.object} onChange={(e) => set('object', e.target.value)} />
        </div>
        <div className="grid grid-cols-2 gap-2">
          <input type="date" className="border rounded-lg px-2 py-1.5 text-xs" value={form.valid_from} onChange={(e) => set('valid_from', e.target.value)} />
          <input type="date" className="border rounded-lg px-2 py-1.5 text-xs" value={form.valid_to} onChange={(e) => set('valid_to', e.target.value)} />
        </div>
        <input className="w-full border rounded-lg px-2 py-1.5 text-xs" placeholder="来源标题" value={form.source_title} onChange={(e) => set('source_title', e.target.value)} />
        <textarea className="w-full border rounded-lg px-2 py-1.5 text-xs h-20" placeholder="原文片段" value={form.source_text} onChange={(e) => set('source_text', e.target.value)} />
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="text-xs px-3 py-1.5 rounded-lg border">取消</button>
          <button type="submit" disabled={busy} className="text-xs px-3 py-1.5 rounded-lg bg-brand-600 text-white disabled:opacity-50">保存为待确认事实</button>
        </div>
      </form>
    </div>
  )
}

function ExtractModal({ busy, onClose, onSubmit }) {
  const [text, setText] = useState('')
  const [source_title, setTitle] = useState('')
  const [page, setPage] = useState('')
  return (
    <div className="fixed inset-0 z-50 bg-slate-900/40 flex items-center justify-center p-4" onClick={onClose}>
      <form
        className="bg-white rounded-2xl shadow-xl w-full max-w-lg p-5 space-y-3"
        onClick={(e) => e.stopPropagation()}
        onSubmit={(e) => { e.preventDefault(); onSubmit({ text, source_title, page, source_type: 'document' }) }}
      >
        <div className="text-sm font-bold text-slate-800">从文档抽取事实</div>
        <p className="text-[11px] text-slate-400">抽的是 Fact，不会直接生成关系网。确认后才映射实体并写图。</p>
        <input className="w-full border rounded-lg px-2 py-1.5 text-xs" placeholder="文档标题，如《AI客服项目周报》" value={source_title} onChange={(e) => setTitle(e.target.value)} />
        <input className="w-full border rounded-lg px-2 py-1.5 text-xs" placeholder="页码（可选）" value={page} onChange={(e) => setPage(e.target.value)} />
        <textarea required className="w-full border rounded-lg px-2 py-1.5 text-xs h-36" placeholder="粘贴原文…" value={text} onChange={(e) => setText(e.target.value)} />
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="text-xs px-3 py-1.5 rounded-lg border">取消</button>
          <button type="submit" disabled={busy} className="text-xs px-3 py-1.5 rounded-lg bg-brand-600 text-white disabled:opacity-50">抽取为待确认事实</button>
        </div>
      </form>
    </div>
  )
}
