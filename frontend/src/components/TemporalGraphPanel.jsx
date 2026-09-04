import React, { useEffect, useMemo, useState } from 'react'
import { Clock, Loader2, RefreshCw } from 'lucide-react'
import { api } from '../api/client.js'
import { beijingToday } from '../utils/beijingTime.js'

const TABS = [
  { id: 'snapshot', label: '历史快照' },
  { id: 'person', label: '人物时间线' },
  { id: 'project', label: '项目时间线' },
  { id: 'event', label: '登记变化' },
  { id: 'influence', label: '时段影响力' },
]

const PRED = {
  OWNER: '负责',
  WORKS_ON: '参与',
  BELONGS_TO: '隶属',
  REPORT_TO: '汇报',
  CONTROL_RESOURCE: '掌控资源',
  HAS_ROLE: '担任角色',
  COLLABORATE_WITH: '合作',
  CONFLICT: '冲突',
  HAS_KNOWLEDGE: '获得技能',
  USES: '使用',
  DEPENDS_ON: '依赖',
  CONTROL_KEY_RESOURCE: '掌握关键资源',
}

export default function TemporalGraphPanel({ members = [] }) {
  const [tab, setTab] = useState('snapshot')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [overview, setOverview] = useState(null)
  const [asOf, setAsOf] = useState(beijingToday())
  const [snap, setSnap] = useState(null)
  const [personId, setPersonId] = useState(members[0]?.id || '')
  const [timeline, setTimeline] = useState(null)
  const [projects, setProjects] = useState([])
  const [projectId, setProjectId] = useState('')
  const [projectTl, setProjectTl] = useState(null)
  const [dateFrom, setDateFrom] = useState(`${beijingToday().slice(0, 4)}-01-01`)
  const [dateTo, setDateTo] = useState(beijingToday())
  const [ranking, setRanking] = useState([])
  const [form, setForm] = useState({
    event_type: 'PROJECT_OWNER_CHANGE',
    event_time: beijingToday(),
    person_id: '',
    other_person_id: '',
    project_id: '',
    resource_id: '',
    department_id: '',
    description: '',
  })

  const eventTypes = overview?.event_types || []

  const loadOverview = async () => {
    const ov = await api.getTemporalOverview()
    setOverview(ov)
    const g = await api.getOigGraph({ types: 'Project' })
    setProjects((g.nodes || []).filter((n) => n.type === 'Project'))
  }

  useEffect(() => {
    loadOverview().catch((e) => setError(e.message)).finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!personId && members[0]) setPersonId(members[0].id)
  }, [members, personId])

  const run = async (fn) => {
    setBusy(true)
    setError(null)
    try {
      await fn()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const loadSnap = () => run(async () => setSnap(await api.getTemporalSnapshot(asOf)))
  const loadPerson = () => run(async () => {
    if (!personId) return
    setTimeline(await api.getPersonTimeline(personId))
  })
  const loadProject = () => run(async () => {
    if (!projectId) return
    setProjectTl(await api.getProjectTimeline(projectId))
  })
  const loadInfluence = () => run(async () => {
    const d = await api.getTemporalInfluence({ dateFrom, dateTo })
    setRanking(d.ranking || [])
  })

  const ownerFacts = useMemo(
    () => (snap?.edges || []).filter((e) => e.relation === 'OWNER'),
    [snap],
  )

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-slate-400 text-sm">
        <Loader2 size={16} className="animate-spin mr-2" />加载时态图谱…
      </div>
    )
  }

  return (
    <div className="p-6 max-w-6xl mx-auto fade-in space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
            <Clock size={20} className="text-brand-600" /> 时间轴分析
          </h2>
          <p className="text-sm text-slate-500 mt-1">
            关系带有效期，交接与离职只关闭旧事实，不删除历史。当前图谱默认只显示此刻仍有效的边。
          </p>
        </div>
        <button onClick={() => run(loadOverview)} className="text-xs px-3 py-1.5 rounded-lg border border-slate-200 text-slate-600 flex items-center gap-1">
          <RefreshCw size={12} /> 刷新
        </button>
      </div>
      {error && <div className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</div>}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="全部事实" value={overview?.fact_count ?? 0} />
        <Stat label="当前有效" value={overview?.open_facts ?? 0} />
        <Stat label="已关闭（历史）" value={overview?.closed_facts ?? 0} />
        <Stat label="时态事件" value={overview?.events ?? 0} />
      </div>

      <div className="flex gap-1 bg-slate-50 rounded-xl p-1 w-fit flex-wrap">
        {TABS.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`text-xs px-3 py-1.5 rounded-lg ${tab === t.id ? 'bg-white shadow-sm text-slate-800 font-semibold' : 'text-slate-500'}`}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'snapshot' && (
        <section className="bg-white rounded-2xl border border-slate-100 p-5 space-y-3">
          <div className="flex gap-2 items-end">
            <label className="text-xs text-slate-500">查询日期
              <input type="date" className="block mt-1 border rounded-lg px-2 py-1.5 text-sm" value={asOf} onChange={(e) => setAsOf(e.target.value)} />
            </label>
            <button disabled={busy} onClick={loadSnap} className="text-xs px-3 py-1.5 rounded-lg bg-brand-600 text-white disabled:opacity-50">查看当时组织</button>
          </div>
          {snap && (
            <div className="text-sm text-slate-700 space-y-2">
              <p>快照 {snap.as_of} · 节点 {snap.nodes?.length || 0} · 当时有效关系 {snap.edges?.length || 0}</p>
              <h4 className="font-semibold text-slate-800">当时项目负责人</h4>
              {ownerFacts.length ? ownerFacts.map((e) => {
                const src = (snap.nodes || []).find((n) => n.id === e.source)
                const tgt = (snap.nodes || []).find((n) => n.id === e.target)
                const p = e.properties || {}
                return (
                  <div key={e.id} className="text-xs text-slate-600">
                    {src?.name || e.source} 负责 {tgt?.name || e.target}
                    <span className="text-slate-400 ml-2">{p.valid_from} ~ {p.valid_to || '今'}</span>
                  </div>
                )
              }) : <p className="text-xs text-slate-400">该日没有 OWNER 事实。请先重建图谱或登记交接。</p>}
            </div>
          )}
        </section>
      )}

      {tab === 'person' && (
        <section className="bg-white rounded-2xl border border-slate-100 p-5 space-y-3">
          <div className="flex gap-2 items-end">
            <select className="text-sm border rounded-lg px-2 py-1.5" value={personId} onChange={(e) => setPersonId(e.target.value)}>
              {members.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
            <button disabled={busy} onClick={loadPerson} className="text-xs px-3 py-1.5 rounded-lg bg-brand-600 text-white">加载时间线</button>
          </div>
          {timeline?.lifecycle && (
            <p className="text-[11px] text-slate-500">
              实体生命周期 {timeline.lifecycle.status} · {timeline.lifecycle.valid_from || '?'} ~ {timeline.lifecycle.valid_to || '今'}
              （离职只改这里和关系有效期，节点仍在）
            </p>
          )}
          {(timeline?.items || []).map((it) => (
            <div key={it.id} className="border-l-2 border-slate-200 pl-3 py-1">
              <div className="text-[11px] text-slate-400">{it.time}{it.end ? ` ~ ${it.end || '今'}` : ''}</div>
              {it.kind === 'fact' ? (
                <div className="text-sm text-slate-800">
                  {it.subject_name} {PRED[it.predicate] || it.predicate} {it.object_name}
                  {it.inferred ? <span className="ml-1 text-[10px] text-brand-600">推断</span> : null}
                </div>
              ) : (
                <div className="text-sm text-slate-800">{it.predicate} {it.description || ''}</div>
              )}
            </div>
          ))}
        </section>
      )}

      {tab === 'project' && (
        <section className="bg-white rounded-2xl border border-slate-100 p-5 space-y-3">
          <div className="flex gap-2 items-end">
            <select className="text-sm border rounded-lg px-2 py-1.5" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
              <option value="">选择项目</option>
              {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
            <button disabled={busy || !projectId} onClick={loadProject} className="text-xs px-3 py-1.5 rounded-lg bg-brand-600 text-white disabled:opacity-50">加载</button>
          </div>
          {(projectTl?.facts || []).map((f) => (
            <div key={f.id} className="text-xs text-slate-600">
              {PRED[f.predicate] || f.predicate} · {f.subject_id} → {f.object_id}
              <span className="text-slate-400 ml-2">{f.valid_from} ~ {f.valid_to || '今'}</span>
            </div>
          ))}
        </section>
      )}

      {tab === 'event' && (
        <section className="bg-white rounded-2xl border border-slate-100 p-5 space-y-3">
          <p className="text-xs text-slate-500">登记交接/离职会关闭旧关系并打开新关系，历史事实保留。</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            <select className="text-sm border rounded-lg px-2 py-1.5" value={form.event_type}
              onChange={(e) => setForm({ ...form, event_type: e.target.value })}>
              {eventTypes.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
            </select>
            <input type="date" className="text-sm border rounded-lg px-2 py-1.5" value={form.event_time}
              onChange={(e) => setForm({ ...form, event_time: e.target.value })} />
            <select className="text-sm border rounded-lg px-2 py-1.5" value={form.person_id}
              onChange={(e) => setForm({ ...form, person_id: e.target.value })}>
              <option value="">人员（原负责人 / 离职者）</option>
              {members.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
            <select className="text-sm border rounded-lg px-2 py-1.5" value={form.other_person_id}
              onChange={(e) => setForm({ ...form, other_person_id: e.target.value })}>
              <option value="">新负责人 / 对方</option>
              {members.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
            <select className="text-sm border rounded-lg px-2 py-1.5" value={form.project_id}
              onChange={(e) => setForm({ ...form, project_id: e.target.value })}>
              <option value="">项目</option>
              {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
            <input className="text-sm border rounded-lg px-2 py-1.5" placeholder="说明，如：项目负责人交接"
              value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </div>
          <button disabled={busy} onClick={() => run(async () => {
            await api.applyTemporalEvent(form)
            await loadOverview()
          })} className="text-sm px-4 py-2 rounded-lg bg-brand-600 text-white disabled:opacity-50">
            写入时态事实（不删历史）
          </button>
        </section>
      )}

      {tab === 'influence' && (
        <section className="bg-white rounded-2xl border border-slate-100 p-5 space-y-3">
          <div className="flex gap-2 items-end flex-wrap">
            <label className="text-xs text-slate-500">从
              <input type="date" className="block mt-1 border rounded-lg px-2 py-1.5 text-sm" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
            </label>
            <label className="text-xs text-slate-500">到
              <input type="date" className="block mt-1 border rounded-lg px-2 py-1.5 text-sm" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
            </label>
            <button disabled={busy} onClick={loadInfluence} className="text-xs px-3 py-1.5 rounded-lg bg-brand-600 text-white">计算该时段影响力</button>
          </div>
          {ranking.slice(0, 12).map((r, i) => (
            <div key={r.id} className="flex justify-between text-sm">
              <span>{i + 1}. {r.name}</span>
              <span className="text-slate-500">{r.influence_score}</span>
            </div>
          ))}
        </section>
      )}
    </div>
  )
}

function Stat({ label, value }) {
  return (
    <div className="bg-white rounded-2xl border border-slate-100 p-4">
      <div className="text-[11px] text-slate-400">{label}</div>
      <div className="text-xl font-bold text-slate-800 mt-0.5">{value}</div>
    </div>
  )
}
