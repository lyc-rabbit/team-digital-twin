import React, { useEffect, useMemo, useRef, useState } from 'react'
import {
  FolderKanban, Plus, ArrowLeft, Check, Circle, Pause, X, Pencil,
} from 'lucide-react'
import { api } from '../api/client.js'

const TYPES = ['业务项目', '技术项目', 'AI项目', '平台项目', '探索项目', '优化项目', '其他']
const PRIORITIES = ['P0', 'P1', 'P2', 'P3']
const STATUSES = [
  { id: 'open', label: '开启' },
  { id: 'paused', label: '暂停' },
  { id: 'closed', label: '关闭' },
]
const STATUS_CLS = {
  open: 'bg-emerald-50 text-emerald-700 border-emerald-100',
  paused: 'bg-amber-50 text-amber-700 border-amber-100',
  closed: 'bg-slate-100 text-slate-600 border-slate-200',
}
const ROLES = ['负责人', '项目经理', '技术负责人', '产品', '开发', '设计', '测试', '业务', '顾问', '其他']
const LEVELS = ['核心', '主要', '辅助', '临时']
const RISK_TYPES = ['技术', '资源', '时间', '需求', '人员', '外部依赖', '质量', '其他']
const REL_TYPES = ['依赖', '前置', '关联', '影响']
const STAGE_STATUSES = [
  { id: 'not_started', label: '未开始' },
  { id: 'in_progress', label: '进行中' },
  { id: 'completed', label: '已完成' },
  { id: 'paused', label: '暂停' },
  { id: 'delayed', label: '延期' },
  { id: 'cancelled', label: '取消' },
]

const HEALTH_CLS = {
  healthy: 'bg-emerald-50 text-emerald-700 border-emerald-100',
  attention: 'bg-amber-50 text-amber-700 border-amber-100',
  risk: 'bg-red-50 text-red-700 border-red-100',
  insufficient: 'bg-slate-100 text-slate-600 border-slate-200',
}

const VIEWER_KEY = 'pc_viewer_id'

function statusLabel(id) {
  return STATUSES.find((s) => s.id === id)?.label || id
}

function StatusChip({ status }) {
  const label = statusLabel(status)
  const cls = STATUS_CLS[status] || STATUS_CLS.open
  return (
    <span className={`inline-flex px-2 py-0.5 rounded-full text-xs border ${cls}`}>
      {label}
    </span>
  )
}

function HealthChip({ health }) {
  if (!health) return null
  const cls = HEALTH_CLS[health.status] || HEALTH_CLS.insufficient
  return (
    <span className={`inline-flex px-2 py-0.5 rounded-full text-xs border ${cls}`}>
      {health.label}{health.score != null ? ` ${health.score}` : ''}
    </span>
  )
}

export default function ProjectCenterPanel({ members = [], initialProjectId }) {
  const [tab, setTab] = useState('all')
  const [view, setView] = useState('list')
  const [projects, setProjects] = useState([])
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [toast, setToast] = useState(null)
  const [editing, setEditing] = useState(null)
  const [filters, setFilters] = useState({ owner_id: '', status: '', type: '', priority: '', sort: 'updated_at' })
  const [viewerId, setViewerId] = useState(() => localStorage.getItem(VIEWER_KEY) || members[0]?.id || '')
  const mountedRef = useRef(true)
  const detailIdRef = useRef(null)
  detailIdRef.current = detail?.id

  useEffect(() => {
    if (!viewerId && members[0]?.id) setViewerId(members[0].id)
  }, [members, viewerId])

  const loadList = async (next = {}) => {
    const f = { ...filters, ...next }
    const params = { sort: f.sort }
    if (f.owner_id) params.owner_id = f.owner_id
    if (f.status) params.status = f.status
    if (f.type) params.type = f.type
    if (f.priority) params.priority = f.priority
    if (tab === 'mine') {
      params.viewer_id = viewerId
      params.member_id = viewerId
    }
    if (tab === 'archive') params.archived_only = true
    const data = await api.listProjects(params)
    if (mountedRef.current) setProjects(data.projects || [])
  }

  useEffect(() => {
    mountedRef.current = true
    ;(async () => {
      try {
        await loadList()
      } catch (err) {
        if (mountedRef.current) setError(err.message || '加载失败')
      } finally {
        if (mountedRef.current) setLoading(false)
      }
    })()
    return () => { mountedRef.current = false }
  }, [tab, viewerId])

  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => mountedRef.current && setToast(null), 4000)
    return () => clearTimeout(t)
  }, [toast])

  useEffect(() => {
    if (!initialProjectId) return
    let cancelled = false
    ;(async () => {
      try {
        const d = await api.getProject(initialProjectId)
        if (!cancelled && mountedRef.current) {
          setDetail(d)
          setView('detail')
        }
      } catch (err) {
        if (mountedRef.current) setError(err.message || '打开项目失败')
      }
    })()
    return () => { cancelled = true }
  }, [initialProjectId])

  const openDetail = async (id) => {
    const d = await api.getProject(id)
    setDetail(d)
    setView('detail')
  }

  const openEdit = (p) => setEditing(p)

  const refreshDetail = async () => {
    const id = detailIdRef.current
    if (!id) return
    const d = await api.getProject(id)
    setDetail(d)
    await loadList()
  }

  if (loading) {
    return <div className="flex items-center justify-center h-full text-slate-400 text-sm">加载项目中心...</div>
  }

  if (view === 'wizard') {
    return (
      <CreateWizard
        members={members}
        onCancel={() => setView('list')}
        onCreated={async (p) => {
          setToast(`项目「${p.name}」已创建`)
          setDetail(p)
          setView('detail')
          await loadList()
        }}
      />
    )
  }

  if (view === 'detail' && detail) {
    return (
      <ProjectDetail
        project={detail}
        members={members}
        projects={projects}
        onBack={async () => {
          setView('list')
          setDetail(null)
          await loadList()
        }}
        onChange={async (p) => {
          setDetail(p)
          await loadList()
        }}
        onRefresh={refreshDetail}
        onToast={setToast}
        viewerId={viewerId}
      />
    )
  }

  const owned = tab === 'mine' ? projects.filter((p) => p.owner_id === viewerId) : []
  const joined = tab === 'mine' ? projects.filter((p) => p.owner_id !== viewerId) : []

  return (
    <div className="p-6 max-w-6xl mx-auto fade-in space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
            <FolderKanban size={20} className="text-brand-600" />
            项目中心
          </h2>
          <p className="text-sm text-slate-500 mt-1">阶段型项目管理。目标和每日任务都是可选的，不作为项目运行前提。</p>
        </div>
        <button
          onClick={() => setView('wizard')}
          className="px-3 py-2 text-sm rounded-lg bg-brand-600 text-white hover:bg-brand-700 flex items-center gap-1.5"
        >
          <Plus size={14} /> 新建项目
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {[
          { id: 'all', label: '项目列表' },
          { id: 'mine', label: '我的项目' },
          { id: 'archive', label: '已关闭' },
        ].map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-3 py-1.5 text-sm rounded-lg ${tab === t.id ? 'bg-white shadow border border-slate-200' : 'text-slate-500'}`}
          >
            {t.label}
          </button>
        ))}
        {tab === 'mine' && (
          <select
            className="ml-auto text-sm border rounded-lg px-2 py-1.5"
            value={viewerId}
            onChange={(e) => {
              setViewerId(e.target.value)
              localStorage.setItem(VIEWER_KEY, e.target.value)
            }}
          >
            {members.map((m) => <option key={m.id} value={m.id}>{m.name} 的视角</option>)}
          </select>
        )}
      </div>

      {tab !== 'archive' && tab !== 'mine' && (
        <div className="flex flex-wrap gap-2 text-sm">
          <select className="border rounded-lg px-2 py-1" value={filters.owner_id} onChange={(e) => setFilters({ ...filters, owner_id: e.target.value })}>
            <option value="">负责人</option>
            {members.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
          </select>
          <select className="border rounded-lg px-2 py-1" value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })}>
            <option value="">状态</option>
            {STATUSES.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
          </select>
          <select className="border rounded-lg px-2 py-1" value={filters.type} onChange={(e) => setFilters({ ...filters, type: e.target.value })}>
            <option value="">类型</option>
            {TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <select className="border rounded-lg px-2 py-1" value={filters.priority} onChange={(e) => setFilters({ ...filters, priority: e.target.value })}>
            <option value="">优先级</option>
            {PRIORITIES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <select className="border rounded-lg px-2 py-1" value={filters.sort} onChange={(e) => setFilters({ ...filters, sort: e.target.value })}>
            <option value="updated_at">更新时间</option>
            <option value="priority">优先级</option>
            <option value="risk">风险</option>
            <option value="end_date">预计完成</option>
          </select>
          <button className="px-3 py-1 border rounded-lg" onClick={() => loadList()}>筛选</button>
        </div>
      )}

      {error && <div className="text-sm text-red-600">{error}</div>}
      {toast && <div className="text-sm text-brand-700 bg-brand-50 border border-brand-100 rounded-lg px-3 py-2">{toast}</div>}

      {tab === 'mine' ? (
        <div className="space-y-5">
          <section>
            <h3 className="text-sm font-semibold text-slate-700 mb-2">我负责的</h3>
            <ProjectTable projects={owned} onOpen={openDetail} onEdit={openEdit} />
          </section>
          <section>
            <h3 className="text-sm font-semibold text-slate-700 mb-2">我参与的</h3>
            <ProjectTable projects={joined} onOpen={openDetail} onEdit={openEdit} />
          </section>
        </div>
      ) : (
        <ProjectTable projects={projects} onOpen={openDetail} onEdit={openEdit} />
      )}

      {editing && (
        <ProjectInfoModal
          project={editing}
          members={members}
          viewerId={viewerId}
          onCancel={() => setEditing(null)}
          onSaved={async (p) => {
            setEditing(null)
            setToast(`项目「${p.name}」已更新`)
            await loadList()
          }}
        />
      )}
    </div>
  )
}

function ProjectTable({ projects, onOpen, onEdit }) {
  if (!projects.length) {
    return <div className="text-sm text-slate-400 bg-white border border-dashed rounded-xl p-8 text-center">暂无项目。阶段是主链路，不必先写目标和每日计划。</div>
  }
  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-slate-50 text-slate-500 text-xs">
          <tr>
            <th className="text-left px-3 py-2 font-medium">项目</th>
            <th className="text-left px-3 py-2 font-medium">负责人</th>
            <th className="text-left px-3 py-2 font-medium">当前阶段</th>
            <th className="text-left px-3 py-2 font-medium">进度</th>
            <th className="text-left px-3 py-2 font-medium">状态</th>
            <th className="text-left px-3 py-2 font-medium">健康</th>
            <th className="text-left px-3 py-2 font-medium">风险</th>
            <th className="text-left px-3 py-2 font-medium">更新</th>
            <th className="text-right px-3 py-2 font-medium">操作</th>
          </tr>
        </thead>
        <tbody>
          {projects.map((p) => {
            const prog = p.stage_progress
            return (
              <tr key={p.id} className="border-t border-slate-100 hover:bg-slate-50">
                <td className="px-3 py-2.5 cursor-pointer" onClick={() => onOpen(p.id)}>
                  <div className="font-medium text-slate-800">{p.name}</div>
                  <div className="text-xs text-slate-400">{p.type || ''} {p.priority || ''}</div>
                </td>
                <td className="px-3 py-2.5 cursor-pointer" onClick={() => onOpen(p.id)}>{p.owner_name}</td>
                <td className="px-3 py-2.5 cursor-pointer" onClick={() => onOpen(p.id)}>{p.current_stage?.name || '—'}</td>
                <td className="px-3 py-2.5 cursor-pointer" onClick={() => onOpen(p.id)}>
                  {prog == null ? (
                    <span className="text-slate-400">未知</span>
                  ) : (
                    <div className="flex items-center gap-2 min-w-[5.5rem]">
                      <div className="w-14 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                        <div className="h-full bg-brand-500" style={{ width: `${Math.min(100, Math.max(0, prog))}%` }} />
                      </div>
                      <span>{Math.round(prog)}%</span>
                    </div>
                  )}
                </td>
                <td className="px-3 py-2.5 cursor-pointer" onClick={() => onOpen(p.id)}><StatusChip status={p.status} /></td>
                <td className="px-3 py-2.5 cursor-pointer" onClick={() => onOpen(p.id)}><HealthChip health={p.health} /></td>
                <td className="px-3 py-2.5 cursor-pointer" onClick={() => onOpen(p.id)}>{p.open_risk_count ? `${p.open_risk_count} 条` : '—'}</td>
                <td className="px-3 py-2.5 text-xs text-slate-400 cursor-pointer" onClick={() => onOpen(p.id)}>{(p.updated_at || '').slice(0, 16).replace('T', ' ')}</td>
                <td className="px-3 py-2.5 text-right whitespace-nowrap">
                  <button
                    type="button"
                    className="text-xs text-brand-600 hover:underline inline-flex items-center gap-0.5"
                    onClick={() => onEdit(p)}
                  >
                    <Pencil size={12} /> 编辑
                  </button>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function CreateWizard({ members, onCancel, onCreated }) {
  const [step, setStep] = useState(1)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [form, setForm] = useState({
    name: '', description: '', owner_id: members[0]?.id || '', status: 'open',
    type: '', priority: '', business: '', start_date: '', end_date: '',
    member_ids: [],
  })
  const [stages, setStages] = useState([{ name: '' }, { name: '' }])
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }))

  const next = () => {
    if (!form.name.trim() || !form.description.trim() || !form.owner_id) {
      setError('名称、简介、负责人为必填')
      return
    }
    setError(null)
    setStep(2)
  }

  const submit = async () => {
    const st = stages.map((s) => ({ name: s.name.trim() })).filter((s) => s.name)
    if (!st.length) {
      setError('请至少填写一个阶段名称')
      return
    }
    setSaving(true)
    setError(null)
    try {
      const created = await api.createProject({
        ...form,
        stages: st,
        members: form.member_ids.filter((id) => id !== form.owner_id).map((id) => ({ user_id: id, role: '其他' })),
      })
      onCreated(created)
    } catch (err) {
      setError(err.message || '创建失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="p-6 max-w-2xl mx-auto fade-in space-y-5">
      <button className="text-sm text-slate-500 flex items-center gap-1" onClick={onCancel}>
        <ArrowLeft size={14} /> 返回列表
      </button>
      <h2 className="text-xl font-bold">新建项目</h2>
      <div className="text-xs text-slate-400">步骤 {step} / 2</div>
      {error && <div className="text-sm text-red-600">{error}</div>}

      {step === 1 && (
        <div className="bg-white border rounded-xl p-4 space-y-3">
          <Field label="项目名称 *"><input className="w-full border rounded-lg px-3 py-2 text-sm" value={form.name} onChange={(e) => set('name', e.target.value)} /></Field>
          <Field label="项目简介 *"><textarea className="w-full border rounded-lg px-3 py-2 text-sm h-24" value={form.description} onChange={(e) => set('description', e.target.value)} /></Field>
          <Field label="项目负责人 *">
            <select className="w-full border rounded-lg px-3 py-2 text-sm" value={form.owner_id} onChange={(e) => set('owner_id', e.target.value)}>
              {members.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
          </Field>
          <Field label="项目状态 *">
            <select className="w-full border rounded-lg px-3 py-2 text-sm" value={form.status} onChange={(e) => set('status', e.target.value)}>
              {STATUSES.filter((s) => s.id !== 'closed').map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
            </select>
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="项目类型（可选）">
              <select className="w-full border rounded-lg px-3 py-2 text-sm" value={form.type} onChange={(e) => set('type', e.target.value)}>
                <option value="">不填</option>
                {TYPES.map((t) => <option key={t}>{t}</option>)}
              </select>
            </Field>
            <Field label="优先级（可选）">
              <select className="w-full border rounded-lg px-3 py-2 text-sm" value={form.priority} onChange={(e) => set('priority', e.target.value)}>
                <option value="">不填</option>
                {PRIORITIES.map((t) => <option key={t}>{t}</option>)}
              </select>
            </Field>
            <Field label="开始时间（可选）"><input type="date" className="w-full border rounded-lg px-3 py-2 text-sm" value={form.start_date} onChange={(e) => set('start_date', e.target.value)} /></Field>
            <Field label="预计结束（可选）"><input type="date" className="w-full border rounded-lg px-3 py-2 text-sm" value={form.end_date} onChange={(e) => set('end_date', e.target.value)} /></Field>
          </div>
          <Field label="项目成员（可选，可后补）">
            <div className="flex flex-wrap gap-2">
              {members.filter((m) => m.id !== form.owner_id).map((m) => (
                <label key={m.id} className="text-xs flex items-center gap-1 border rounded-full px-2 py-1">
                  <input
                    type="checkbox"
                    checked={form.member_ids.includes(m.id)}
                    onChange={() => {
                      const has = form.member_ids.includes(m.id)
                      set('member_ids', has ? form.member_ids.filter((x) => x !== m.id) : [...form.member_ids, m.id])
                    }}
                  />
                  {m.name}
                </label>
              ))}
            </div>
          </Field>
          <div className="flex justify-end">
            <button onClick={next} className="px-4 py-2 text-sm rounded-lg bg-brand-600 text-white">下一步：定义阶段</button>
          </div>
        </div>
      )}

      {step === 2 && (
        <div className="bg-white border rounded-xl p-4 space-y-3">
          <p className="text-sm text-slate-600 bg-slate-50 rounded-lg p-3">
            项目采用阶段式管理，不需要设置每日工作目标。请先定义项目当前阶段和后续阶段。
          </p>
          {stages.map((s, i) => (
            <div key={i} className="flex items-center gap-2">
              <span className="text-xs text-slate-400 w-14">阶段 {i + 1}{i === 0 ? ' · 进行中' : ''}</span>
              <input
                className="flex-1 border rounded-lg px-3 py-2 text-sm"
                placeholder={i === 0 ? '例如：基础架构' : '下一阶段名称'}
                value={s.name}
                onChange={(e) => setStages(stages.map((x, j) => j === i ? { name: e.target.value } : x))}
              />
              {stages.length > 1 && (
                <button className="text-slate-400" onClick={() => setStages(stages.filter((_, j) => j !== i))}><X size={14} /></button>
              )}
            </div>
          ))}
          <button className="text-sm text-brand-600" onClick={() => setStages([...stages, { name: '' }])}>+ 添加阶段</button>
          <div className="flex justify-between pt-2">
            <button className="text-sm text-slate-500" onClick={() => setStep(1)}>上一步</button>
            <button disabled={saving} onClick={submit} className="px-4 py-2 text-sm rounded-lg bg-brand-600 text-white disabled:opacity-50">
              {saving ? '创建中...' : '创建项目'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function Field({ label, children }) {
  return (
    <label className="block text-sm">
      <div className="text-xs text-slate-500 mb-1">{label}</div>
      {children}
    </label>
  )
}

function projectInfoForm(p) {
  return {
    name: p?.name || '',
    description: p?.description || '',
    owner_id: p?.owner_id || '',
    status: p?.status || 'open',
    type: p?.type || '',
    priority: p?.priority || '',
    business: p?.business || '',
    start_date: (p?.start_date || '').slice(0, 10),
    end_date: (p?.end_date || '').slice(0, 10),
  }
}

function ProjectInfoModal({ project, members, viewerId, onCancel, onSaved }) {
  const [form, setForm] = useState(() => projectInfoForm(project))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }))

  useEffect(() => {
    setForm(projectInfoForm(project))
    setError(null)
  }, [project?.id])

  const submit = async (e) => {
    e.preventDefault()
    if (!form.name.trim() || !form.description.trim() || !form.owner_id) {
      setError('名称、简介、负责人为必填')
      return
    }
    setSaving(true)
    setError(null)
    try {
      const updated = await api.updateProject(project.id, {
        name: form.name.trim(),
        description: form.description.trim(),
        owner_id: form.owner_id,
        status: form.status,
        type: form.type,
        priority: form.priority,
        business: form.business.trim(),
        start_date: form.start_date,
        end_date: form.end_date,
        operator_id: viewerId || '',
      })
      onSaved(updated)
    } catch (err) {
      setError(err.message || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/30 z-40 flex items-center justify-center p-4" onClick={onCancel}>
      <form
        className="bg-white rounded-xl w-full max-w-lg p-5 space-y-3 max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
        onSubmit={submit}
      >
        <div className="flex items-start justify-between gap-2">
          <div>
            <h3 className="font-semibold text-slate-800">编辑项目信息</h3>
            <p className="text-xs text-slate-400 mt-0.5">改名称、负责人、类型等基础信息。阶段和进度仍在项目详情里改。</p>
          </div>
          <button type="button" className="text-slate-400 hover:text-slate-600" onClick={onCancel}><X size={16} /></button>
        </div>
        {error && <div className="text-sm text-red-600">{error}</div>}
        <Field label="项目名称 *">
          <input className="w-full border rounded-lg px-3 py-2 text-sm" value={form.name} onChange={(e) => set('name', e.target.value)} />
        </Field>
        <Field label="项目简介 *">
          <textarea className="w-full border rounded-lg px-3 py-2 text-sm h-24" value={form.description} onChange={(e) => set('description', e.target.value)} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="项目负责人 *">
            <select className="w-full border rounded-lg px-3 py-2 text-sm" value={form.owner_id} onChange={(e) => set('owner_id', e.target.value)}>
              {members.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
          </Field>
          <Field label="项目状态">
            <select className="w-full border rounded-lg px-3 py-2 text-sm" value={form.status} onChange={(e) => set('status', e.target.value)}>
              {STATUSES.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
            </select>
          </Field>
          <Field label="项目类型">
            <select className="w-full border rounded-lg px-3 py-2 text-sm" value={form.type} onChange={(e) => set('type', e.target.value)}>
              <option value="">不填</option>
              {TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </Field>
          <Field label="优先级">
            <select className="w-full border rounded-lg px-3 py-2 text-sm" value={form.priority} onChange={(e) => set('priority', e.target.value)}>
              <option value="">不填</option>
              {PRIORITIES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </Field>
          <Field label="开始时间">
            <input type="date" className="w-full border rounded-lg px-3 py-2 text-sm" value={form.start_date} onChange={(e) => set('start_date', e.target.value)} />
          </Field>
          <Field label="预计结束">
            <input type="date" className="w-full border rounded-lg px-3 py-2 text-sm" value={form.end_date} onChange={(e) => set('end_date', e.target.value)} />
          </Field>
        </div>
        <Field label="业务线（可选）">
          <input className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="例如：客服 / 增长" value={form.business} onChange={(e) => set('business', e.target.value)} />
        </Field>
        <div className="flex justify-end gap-2 pt-1">
          <button type="button" className="px-3 py-1.5 text-sm text-slate-500" onClick={onCancel}>取消</button>
          <button disabled={saving} className="px-3 py-1.5 text-sm rounded-lg bg-brand-600 text-white disabled:opacity-50">
            {saving ? '保存中...' : '保存'}
          </button>
        </div>
      </form>
    </div>
  )
}

function ProjectDetail({ project, members, projects, onBack, onChange, onRefresh, onToast, viewerId }) {
  const [completeOpen, setCompleteOpen] = useState(false)
  const [summary, setSummary] = useState('')
  const [busy, setBusy] = useState(false)
  const [editing, setEditing] = useState(false)
  const current = project.current_stage
  const nextStage = useMemo(() => {
    const stages = [...(project.stages || [])].sort((a, b) => a.sort_order - b.sort_order)
    const cur = stages.find((s) => s.id === project.current_stage_id)
    return stages.find((s) => s.sort_order > (cur?.sort_order || 0) && s.status !== 'cancelled')
  }, [project])

  const act = async (fn, ok) => {
    setBusy(true)
    try {
      const r = await fn()
      if (r && (r.id === project.id || Array.isArray(r.stages))) onChange(r)
      else await onRefresh()
      if (ok) onToast(ok)
    } catch (err) {
      onToast(err.message || '操作失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="p-6 max-w-5xl mx-auto fade-in space-y-5">
      <button className="text-sm text-slate-500 flex items-center gap-1" onClick={onBack}>
        <ArrowLeft size={14} /> 返回列表
      </button>

      <div className="bg-white border rounded-xl p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-xl font-bold text-slate-800">{project.name}</h2>
            <p className="text-sm text-slate-500 mt-1">
              负责人：{project.owner_name}
              <span className="mx-2">·</span>状态：<StatusChip status={project.status} />
              <span className="mx-2">·</span>当前阶段：{current?.name || '—'}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="text-xs text-brand-600 hover:underline inline-flex items-center gap-0.5"
              onClick={() => setEditing(true)}
            >
              <Pencil size={12} /> 编辑信息
            </button>
            <HealthChip health={project.health} />
          </div>
        </div>
        {project.health?.status === 'insufficient' && (
          <p className="text-xs text-slate-400 mt-2">数据不足时不编造分数。补齐下面列出的信息后才会评分。</p>
        )}
        <MissingInfoCard health={project.health} current={current} project={project} />
        <StatusActions project={project} busy={busy} onAct={act} />
      </div>

      <section className="bg-white border rounded-xl p-5">
        <h3 className="font-semibold mb-4">阶段进度</h3>
        {current?.progress_view?.value == null && (
          <p className="text-xs text-amber-700 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2 mb-3">
            当前进度未知。请在下方填写人工进度，或给该阶段添加里程碑（完成数会自动换算）。
          </p>
        )}
        <SetProgress project={project} current={current} onAct={act} />
        <StageTimeline
          stages={project.stages || []}
          currentId={project.current_stage_id}
          project={project}
          members={members}
          onAct={act}
        />
        <div className="flex flex-wrap gap-2 mt-4">
          {current && current.status !== 'completed' && (
            <button
              disabled={busy}
              onClick={() => setCompleteOpen(true)}
              className="px-3 py-1.5 text-sm rounded-lg bg-brand-600 text-white disabled:opacity-50"
            >
              完成阶段
            </button>
          )}
          <AddStage members={members} project={project} onAct={act} />
        </div>
      </section>

      <section className="bg-white border rounded-xl p-5 space-y-3">
        <h3 className="font-semibold">项目概览</h3>
        <p className="text-sm text-slate-700 whitespace-pre-wrap">{project.description}</p>
        <ProjectDates project={project} onAct={act} />
        {(project.objectives || []).length > 0 && (
          <div>
            <h4 className="text-sm font-medium mb-1">项目目标</h4>
            {project.objectives.map((o) => (
              <div key={o.id} className="text-sm mb-2">
                <div>{o.title} <span className="text-xs text-slate-400">{o.status}</span></div>
                {o.description && <p className="text-xs text-slate-500">{o.description}</p>}
                {(o.krs || []).map((k) => (
                  <div key={k.id} className="text-xs text-slate-600 ml-3">KR：{k.name} {k.target_value}{k.unit}</div>
                ))}
                <AddKr project={project} objective={o} onAct={act} />
              </div>
            ))}
          </div>
        )}
        <AddObjective project={project} onAct={act} />
        <MembersBlock project={project} members={members} onAct={act} />
      </section>

      {!(project.milestones || []).length && (
        <p className="text-xs text-slate-500 -mt-2">还没有里程碑。补上后可用完成比例计算进度。</p>
      )}
      {(project.milestones || []).length > 0 && (
        <section className="bg-white border rounded-xl p-5">
          <h3 className="font-semibold mb-2">里程碑</h3>
          {project.milestones.map((m) => (
            <div key={m.id} className="flex items-center justify-between text-sm py-1 border-b border-slate-50">
              <span>{m.name} <span className="text-xs text-slate-400">{m.stage_name || ''} · {m.status}</span></span>
              {m.status !== 'completed' && (
                <button className="text-xs text-brand-600" onClick={() => act(() => api.updateProjectMilestone(project.id, m.id, { status: 'completed' }), '里程碑已完成')}>完成</button>
              )}
            </div>
          ))}
        </section>
      )}
      <AddMilestone project={project} members={members} onAct={act} />

      {!(project.risks || []).length && (
        <p className="text-xs text-slate-500 -mt-2">还没有风险记录。健康度目前不计风险项。</p>
      )}
      {(project.risks || []).length > 0 && (
        <section className="bg-white border rounded-xl p-5">
          <h3 className="font-semibold mb-2">风险</h3>
          {project.risks.map((r) => (
            <div key={r.id} className="text-sm py-2 border-b border-slate-50">
              <div className="flex justify-between">
                <span>{r.title} <span className="text-xs text-slate-400">{r.level} · {r.status}</span></span>
                {r.status === 'open' && (
                  <button className="text-xs text-brand-600" onClick={() => act(() => api.updateProjectRisk(project.id, r.id, { status: 'resolved' }), '风险已解决')}>解决</button>
                )}
              </div>
              {r.description && <p className="text-xs text-slate-500">{r.description}</p>}
            </div>
          ))}
        </section>
      )}
      <AddRisk project={project} members={members} onAct={act} />

      <section className="bg-white border rounded-xl p-5">
        <h3 className="font-semibold mb-2">项目动态</h3>
        <p className="text-xs text-slate-400 mb-3">日报只产生动态，不会自动改写阶段或进度。</p>
        <AddActivity project={project} onAct={act} />
        <div className="mt-3 space-y-2">
          {(project.activities || []).map((a) => (
            <div key={a.id} className="text-sm border-l-2 border-slate-200 pl-3">
              <div className="text-xs text-slate-400">{(a.created_at || '').slice(0, 16).replace('T', ' ')} · {a.source}</div>
              <div>{a.content}</div>
            </div>
          ))}
        </div>
      </section>

      {(project.relations || []).length > 0 && (
        <section className="bg-white border rounded-xl p-5">
          <h3 className="font-semibold mb-2">项目关系</h3>
          {project.relations.map((r) => (
            <div key={r.id} className="text-sm flex justify-between py-1">
              <span>{r.relation_type} → {r.target_project_id === project.id ? r.source_project_id : r.target_project_id}</span>
              <button className="text-xs text-slate-400" onClick={() => act(() => api.deleteProjectRelation(project.id, r.id))}>移除</button>
            </div>
          ))}
        </section>
      )}
      <AddRelation project={project} projects={projects} onAct={act} />

      {editing && (
        <ProjectInfoModal
          project={project}
          members={members}
          viewerId={viewerId}
          onCancel={() => setEditing(false)}
          onSaved={(p) => {
            setEditing(false)
            onChange(p)
            onToast(`项目「${p.name}」已更新`)
          }}
        />
      )}
      {completeOpen && (
        <div className="fixed inset-0 bg-black/30 z-40 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl w-full max-w-md p-5">
            <h3 className="font-semibold mb-2">确认阶段完成？</h3>
            <p className="text-sm">当前阶段：{current?.name}</p>
            <p className="text-sm mt-1">下一阶段：{nextStage?.name || '（无，停留在已完成）'}</p>
            <textarea className="w-full border rounded-lg mt-3 p-2 text-sm h-20" placeholder="阶段总结（可选）" value={summary} onChange={(e) => setSummary(e.target.value)} />
            <div className="flex justify-end gap-2 mt-3">
              <button onClick={() => setCompleteOpen(false)}>取消</button>
              <button
                disabled={busy}
                className="px-3 py-1.5 text-sm rounded-lg bg-brand-600 text-white"
                onClick={async () => {
                  await act(() => api.completeProjectStage(project.id, current.id, { summary, operator_id: viewerId }), '阶段已推进')
                  setCompleteOpen(false)
                  setSummary('')
                }}
              >
                确认推进
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function StageTimeline({ stages, currentId, project, members = [], onAct }) {
  const [editingId, setEditingId] = useState(null)
  const rows = [...stages].sort((a, b) => a.sort_order - b.sort_order)
  return (
    <div>
      {rows.map((s, i) => {
        const done = s.status === 'completed'
        const current = s.id === currentId || s.status === 'in_progress'
        const editing = editingId === s.id
        return (
          <div key={s.id} className="flex gap-3">
            <div className="flex flex-col items-center w-6">
              {done ? <Check size={16} className="text-emerald-600" /> : current ? <Circle size={14} className="text-brand-600 fill-brand-600" /> : s.status === 'paused' ? <Pause size={14} className="text-amber-500" /> : <Circle size={14} className="text-slate-300" />}
              {i < rows.length - 1 && <div className="w-px flex-1 bg-slate-200 my-1 min-h-[18px]" />}
            </div>
            <div className="pb-3 flex-1 min-w-0">
              <div className="flex items-start justify-between gap-2">
                <div className={`text-sm ${current ? 'font-semibold text-slate-800' : 'text-slate-600'}`}>
                  {s.sort_order}. {s.name}
                  <span className="ml-2 text-xs text-slate-400">{s.status_label}</span>
                  <span className="ml-2 text-xs text-slate-400">
                    {s.progress_view?.value == null ? '进度未知' : `${s.progress_view.value}%`}
                  </span>
                </div>
                <button
                  type="button"
                  className="flex-shrink-0 text-xs text-brand-600 hover:underline inline-flex items-center gap-0.5"
                  onClick={() => setEditingId(editing ? null : s.id)}
                >
                  <Pencil size={12} />
                  {editing ? '收起' : '编辑'}
                </button>
              </div>
              {editing && (
                <StageEditForm
                  project={project}
                  stage={s}
                  members={members}
                  onAct={onAct}
                  onDone={() => setEditingId(null)}
                />
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function StageEditForm({ project, stage, members, onAct, onDone }) {
  const [form, setForm] = useState({
    name: stage.name || '',
    status: stage.status || 'not_started',
    description: stage.description || '',
    owner_id: stage.owner_id || '',
    planned_start_date: stage.planned_start_date || '',
    planned_end_date: stage.planned_end_date || '',
    progress: stage.progress == null ? '' : String(stage.progress),
  })
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }))
  const milestone = stage.progress_view?.mode === 'milestone'
  return (
    <form
      className="mt-2 p-3 rounded-lg border border-slate-200 bg-slate-50 space-y-2"
      onSubmit={(e) => {
        e.preventDefault()
        if (!form.name.trim()) return
        let progress = null
        if (form.progress !== '') {
          const n = Number(form.progress)
          if (Number.isNaN(n)) return
          progress = Math.max(0, Math.min(100, n))
        }
        onAct(
          () => api.updateProjectStage(project.id, stage.id, {
            name: form.name.trim(),
            status: form.status,
            description: form.description,
            owner_id: form.owner_id || '',
            planned_start_date: form.planned_start_date || '',
            planned_end_date: form.planned_end_date || '',
            progress,
          }),
          '阶段已更新',
        )
        onDone()
      }}
    >
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <label className="text-xs text-slate-500">
          阶段名称
          <input className="mt-1 w-full border rounded px-2 py-1 text-sm bg-white" value={form.name} onChange={(e) => set('name', e.target.value)} />
        </label>
        <label className="text-xs text-slate-500">
          状态
          <select className="mt-1 w-full border rounded px-2 py-1 text-sm bg-white" value={form.status} onChange={(e) => set('status', e.target.value)}>
            {STAGE_STATUSES.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
          </select>
        </label>
        <label className="text-xs text-slate-500">
          进度 %
          <input
            className="mt-1 w-full border rounded px-2 py-1 text-sm bg-white"
            inputMode="decimal"
            placeholder="未知"
            value={form.progress}
            onChange={(e) => set('progress', e.target.value)}
          />
          {milestone && (
            <span className="block mt-0.5 text-[11px] text-slate-400">该阶段有里程碑时，展示进度按完成数计算</span>
          )}
        </label>
        <label className="text-xs text-slate-500 sm:col-span-2">
          说明
          <input className="mt-1 w-full border rounded px-2 py-1 text-sm bg-white" value={form.description} onChange={(e) => set('description', e.target.value)} placeholder="可选" />
        </label>
        <label className="text-xs text-slate-500">
          阶段负责人
          <select className="mt-1 w-full border rounded px-2 py-1 text-sm bg-white" value={form.owner_id} onChange={(e) => set('owner_id', e.target.value)}>
            <option value="">未指定</option>
            {members.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
          </select>
        </label>
        <div className="grid grid-cols-2 gap-2">
          <label className="text-xs text-slate-500">
            计划开始
            <input type="date" className="mt-1 w-full border rounded px-2 py-1 text-sm bg-white" value={form.planned_start_date} onChange={(e) => set('planned_start_date', e.target.value)} />
          </label>
          <label className="text-xs text-slate-500">
            计划结束
            <input type="date" className="mt-1 w-full border rounded px-2 py-1 text-sm bg-white" value={form.planned_end_date} onChange={(e) => set('planned_end_date', e.target.value)} />
          </label>
        </div>
      </div>
      <div className="flex justify-end gap-2">
        <button type="button" className="text-xs text-slate-500" onClick={onDone}>取消</button>
        <button className="px-2.5 py-1 text-xs rounded-lg bg-brand-600 text-white">保存</button>
      </div>
    </form>
  )
}

function deriveMissing(project, current) {
  if (project?.health?.missing?.length) return project.health.missing
  const items = []
  const stages = project?.stages || []
  const progressUnknown = current?.progress_view?.value == null && !stages.some((s) => s.progress != null)
  if (!stages.length) {
    items.push({ key: 'stage', label: '尚未定义阶段', where: '阶段进度', need: 'progress', detail: '至少添加一个阶段' })
  } else if (progressUnknown) {
    items.push({
      key: 'progress', label: '当前阶段进度未知', where: '阶段进度 → 人工进度', need: 'progress',
      detail: '填写 0–100，或给当前阶段加里程碑',
    })
  }
  if (!(project?.milestones || []).length) {
    items.push({ key: 'milestone', label: '没有里程碑', where: '里程碑', need: 'progress', detail: '可选。有里程碑后可用完成比例作为进度' })
  }
  if (!(project?.risks || []).length) {
    items.push({ key: 'risk', label: '没有风险记录', where: '风险', need: 'health', detail: '可选。记过风险后健康度才会计入风险项' })
  }
  const start = (project?.start_date || '').trim()
  const end = (project?.end_date || '').trim()
  if (!start || !end) {
    const lack = [!start && '开始时间', !end && '预计结束时间'].filter(Boolean).join('、')
    items.push({ key: 'dates', label: `缺少${lack}`, where: '项目概览', need: 'health', detail: '起止时间都填了，健康度才会考虑时间维度' })
  }
  return items
}

function MissingInfoCard({ health, current, project }) {
  const missing = deriveMissing(project, current)
  if (!missing.length) return null
  const forProgress = missing.filter((m) => m.need === 'progress')
  const forHealth = missing.filter((m) => m.need === 'health')
  const progressText = current?.progress_view?.value == null ? '未知' : `${Math.round(current.progress_view.value)}%`
  return (
    <div className="mt-3 rounded-lg border border-amber-100 bg-amber-50/80 px-3 py-3">
      <div className="text-sm font-medium text-amber-900">
        当前进度 {progressText}
        {health?.status === 'insufficient' ? ' · 健康度信息不足，暂不打分' : ''}
      </div>
      <p className="text-xs text-amber-800/80 mt-1">不会用日报字数或猜测来补进度。缺什么补什么即可。</p>
      {forProgress.length > 0 && (
        <div className="mt-2">
          <div className="text-xs font-medium text-amber-900 mb-1">要算出进度，还缺</div>
          <ul className="text-xs text-amber-900/90 space-y-1">
            {forProgress.map((m) => (
              <li key={m.key}>· {m.label}（在「{m.where}」）{m.detail ? ` — ${m.detail}` : ''}</li>
            ))}
          </ul>
        </div>
      )}
      {forHealth.length > 0 && (
        <div className="mt-2">
          <div className="text-xs font-medium text-amber-900 mb-1">
            {health?.status === 'insufficient' ? '要开始健康评分，下面再补任意一项即可' : '补上后健康度会更准'}
          </div>
          <ul className="text-xs text-amber-900/90 space-y-1">
            {forHealth.map((m) => (
              <li key={m.key}>· {m.label}（在「{m.where}」）{m.detail ? ` — ${m.detail}` : ''}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function ProjectDates({ project, onAct }) {
  const [start, setStart] = useState(project.start_date || '')
  const [end, setEnd] = useState(project.end_date || '')
  useEffect(() => {
    setStart((project.start_date || '').slice(0, 10))
    setEnd((project.end_date || '').slice(0, 10))
  }, [project.start_date, project.end_date, project.id])
  const missing = !(start && end)
  return (
    <form
      className={`flex flex-wrap items-end gap-2 text-sm ${missing ? 'p-2 rounded-lg bg-amber-50 border border-amber-100' : ''}`}
      onSubmit={(e) => {
        e.preventDefault()
        onAct(() => api.updateProject(project.id, { start_date: start, end_date: end }), '时间已更新')
      }}
    >
      <label className="text-xs text-slate-500">
        开始时间{!start ? '（缺）' : ''}
        <input type="date" className="mt-1 block border rounded px-2 py-1 text-sm bg-white" value={start} onChange={(e) => setStart(e.target.value)} />
      </label>
      <label className="text-xs text-slate-500">
        预计结束{!end ? '（缺）' : ''}
        <input type="date" className="mt-1 block border rounded px-2 py-1 text-sm bg-white" value={end} onChange={(e) => setEnd(e.target.value)} />
      </label>
      <button className="px-2.5 py-1 text-xs rounded-lg border border-slate-200 bg-white">保存时间</button>
    </form>
  )
}

function StatusActions({ project, busy, onAct }) {
  return (
    <div className="flex flex-wrap items-center gap-2 mt-3 text-xs">
      <span className="text-slate-400">项目状态</span>
      {STATUSES.map((s) => {
        const on = project.status === s.id
        return (
          <button
            key={s.id}
            type="button"
            disabled={busy || on}
            onClick={() => onAct(() => api.updateProject(project.id, { status: s.id }), `已设为${s.label}`)}
            className={`px-2.5 py-1 rounded-lg border ${on ? STATUS_CLS[s.id] + ' font-medium' : 'border-slate-200 text-slate-500 hover:bg-slate-50'} disabled:opacity-60`}
          >
            {s.label}
          </button>
        )
      })}
    </div>
  )
}

function AddStage({ project, onAct }) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  if (!open) return <button className="px-3 py-1.5 text-sm border rounded-lg" onClick={() => setOpen(true)}>+ 阶段</button>
  return (
    <form
      className="flex gap-2 items-center"
      onSubmit={(e) => {
        e.preventDefault()
        if (!name.trim()) return
        onAct(() => api.addProjectStage(project.id, { name }), '阶段已添加')
        setName('')
        setOpen(false)
      }}
    >
      <input className="border rounded px-2 py-1 text-sm" placeholder="阶段名称" value={name} onChange={(e) => setName(e.target.value)} />
      <button className="text-sm text-brand-600">添加</button>
      <button type="button" className="text-xs text-slate-400" onClick={() => setOpen(false)}>取消</button>
    </form>
  )
}

function SetProgress({ project, current, onAct }) {
  const saved = current?.progress == null ? '' : String(current.progress)
  const [val, setVal] = useState(saved)
  useEffect(() => { setVal(saved) }, [saved, current?.id])
  if (!current) return null
  const view = current.progress_view || {}
  const shown = view.value
  const milestone = view.mode === 'milestone'
  return (
    <form
      className="mb-4 p-3 rounded-lg border border-slate-200 bg-slate-50 flex flex-wrap items-end gap-2"
      onSubmit={(e) => {
        e.preventDefault()
        if (val === '') {
          onAct(() => api.updateProjectStage(project.id, current.id, { progress: null }), '已设为未知')
          return
        }
        const n = Number(val)
        if (Number.isNaN(n)) return
        onAct(
          () => api.updateProjectStage(project.id, current.id, { progress: Math.max(0, Math.min(100, n)) }),
          '进度已更新',
        )
      }}
    >
      <div className="min-w-[8rem]">
        <div className="text-xs text-slate-500">当前阶段进度</div>
        <div className="text-lg font-semibold text-slate-800 leading-tight">
          {shown == null ? '未知' : `${Math.round(shown)}%`}
        </div>
        <div className="text-[11px] text-slate-400">{current.name}{milestone ? ' · 由里程碑计算' : view.mode === 'manual' ? ' · 人工填写' : ''}</div>
      </div>
      {shown != null && (
        <div className="w-28 h-1.5 bg-slate-200 rounded-full overflow-hidden mb-2">
          <div className="h-full bg-brand-500" style={{ width: `${Math.min(100, Math.max(0, shown))}%` }} />
        </div>
      )}
      {!milestone && (
        <>
          <label className="text-xs text-slate-500">
            填写 0–100
            <input
              className="mt-1 w-24 border rounded px-2 py-1 text-sm bg-white block"
              inputMode="decimal"
              placeholder="未知"
              value={val}
              onChange={(e) => setVal(e.target.value)}
            />
          </label>
          <button className="px-2.5 py-1 text-xs rounded-lg bg-brand-600 text-white">保存进度</button>
        </>
      )}
    </form>
  )
}

function MembersBlock({ project, members, onAct }) {
  const [userId, setUserId] = useState(members[0]?.id || '')
  const [role, setRole] = useState('开发')
  const [level, setLevel] = useState('主要')
  return (
    <div>
      <h4 className="text-sm font-medium mb-2">项目成员</h4>
      <div className="flex flex-wrap gap-2 mb-2">
        {(project.members || []).map((m) => (
          <span key={m.id} className="text-xs border rounded-full px-2 py-1 flex items-center gap-1">
            {m.user_name} · {m.role} · {m.participation_level}
            {m.role !== '负责人' && (
              <button onClick={() => onAct(() => api.deleteProjectMember(project.id, m.id))}><X size={10} /></button>
            )}
          </span>
        ))}
      </div>
      <div className="flex flex-wrap gap-2 text-sm">
        <select className="border rounded px-2 py-1" value={userId} onChange={(e) => setUserId(e.target.value)}>
          {members.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
        </select>
        <select className="border rounded px-2 py-1" value={role} onChange={(e) => setRole(e.target.value)}>
          {ROLES.map((r) => <option key={r}>{r}</option>)}
        </select>
        <select className="border rounded px-2 py-1" value={level} onChange={(e) => setLevel(e.target.value)}>
          {LEVELS.map((r) => <option key={r}>{r}</option>)}
        </select>
        <button className="text-brand-600" onClick={() => onAct(() => api.addProjectMember(project.id, { user_id: userId, role, participation_level: level }), '成员已更新')}>加入</button>
      </div>
    </div>
  )
}

function AddObjective({ project, onAct }) {
  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState('')
  if (!open) return <button className="text-xs text-brand-600" onClick={() => setOpen(true)}>+ 添加目标（可选）</button>
  return (
    <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); onAct(() => api.addProjectObjective(project.id, { title }), '已添加目标'); setTitle(''); setOpen(false) }}>
      <input className="flex-1 border rounded px-2 py-1 text-sm" placeholder="项目目标" value={title} onChange={(e) => setTitle(e.target.value)} />
      <button className="text-sm text-brand-600">保存</button>
    </form>
  )
}

function AddKr({ project, objective, onAct }) {
  const [name, setName] = useState('')
  return (
    <form className="flex gap-2 mt-1" onSubmit={(e) => { e.preventDefault(); if (!name.trim()) return; onAct(() => api.addProjectKr(project.id, objective.id, { name }), '已添加 KR'); setName('') }}>
      <input className="flex-1 border rounded px-2 py-0.5 text-xs" placeholder="添加 KR（可选）" value={name} onChange={(e) => setName(e.target.value)} />
      <button className="text-xs text-brand-600">添加</button>
    </form>
  )
}

function AddMilestone({ project, members, onAct }) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [stageId, setStageId] = useState(project.current_stage_id || '')
  const [date, setDate] = useState('')
  if (!open) return <button className="text-xs text-brand-600" onClick={() => setOpen(true)}>+ 添加里程碑（可选）</button>
  return (
    <form className="bg-white border rounded-xl p-3 flex flex-wrap gap-2 text-sm" onSubmit={(e) => {
      e.preventDefault()
      onAct(() => api.addProjectMilestone(project.id, { name, stage_id: stageId, planned_date: date }), '里程碑已添加')
      setName(''); setOpen(false)
    }}>
      <input className="border rounded px-2 py-1" placeholder="里程碑名称" value={name} onChange={(e) => setName(e.target.value)} />
      <select className="border rounded px-2 py-1" value={stageId} onChange={(e) => setStageId(e.target.value)}>
        {(project.stages || []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
      </select>
      <input type="date" className="border rounded px-2 py-1" value={date} onChange={(e) => setDate(e.target.value)} />
      <button className="text-brand-600">保存</button>
      <button type="button" onClick={() => setOpen(false)}>取消</button>
    </form>
  )
}

function AddRisk({ project, members, onAct }) {
  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState('')
  const [type, setType] = useState('技术')
  const [level, setLevel] = useState('medium')
  if (!open) return <button className="text-xs text-brand-600" onClick={() => setOpen(true)}>+ 添加风险（可选，推荐）</button>
  return (
    <form className="bg-white border rounded-xl p-3 flex flex-wrap gap-2 text-sm" onSubmit={(e) => {
      e.preventDefault()
      onAct(() => api.addProjectRisk(project.id, { title, type, level }), '风险已记录')
      setTitle(''); setOpen(false)
    }}>
      <input className="flex-1 border rounded px-2 py-1" placeholder="风险标题" value={title} onChange={(e) => setTitle(e.target.value)} />
      <select className="border rounded px-2 py-1" value={type} onChange={(e) => setType(e.target.value)}>{RISK_TYPES.map((t) => <option key={t}>{t}</option>)}</select>
      <select className="border rounded px-2 py-1" value={level} onChange={(e) => setLevel(e.target.value)}>
        <option value="high">高</option>
        <option value="medium">中</option>
        <option value="low">低</option>
      </select>
      <button className="text-brand-600">保存</button>
      <button type="button" onClick={() => setOpen(false)}>取消</button>
    </form>
  )
}

function AddActivity({ project, onAct }) {
  const [content, setContent] = useState('')
  return (
    <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (!content.trim()) return; onAct(() => api.addProjectActivity(project.id, { content, source: 'MANUAL' })); setContent('') }}>
      <input className="flex-1 border rounded-lg px-3 py-1.5 text-sm" placeholder="记录一条项目动态" value={content} onChange={(e) => setContent(e.target.value)} />
      <button className="text-sm text-brand-600">发布</button>
    </form>
  )
}

function AddRelation({ project, projects, onAct }) {
  const [open, setOpen] = useState(false)
  const [target, setTarget] = useState('')
  const [rel, setRel] = useState('关联')
  const others = (projects || []).filter((p) => p.id !== project.id)
  if (!others.length) return null
  if (!open) return <button className="text-xs text-brand-600" onClick={() => setOpen(true)}>+ 项目关系（可选）</button>
  return (
    <form className="flex gap-2 text-sm" onSubmit={(e) => {
      e.preventDefault()
      if (!target) return
      onAct(() => api.addProjectRelation(project.id, { target_project_id: target, relation_type: rel }), '关系已添加')
      setOpen(false)
    }}>
      <select className="border rounded px-2 py-1" value={rel} onChange={(e) => setRel(e.target.value)}>{REL_TYPES.map((t) => <option key={t}>{t}</option>)}</select>
      <select className="border rounded px-2 py-1" value={target} onChange={(e) => setTarget(e.target.value)}>
        <option value="">选择项目</option>
        {others.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
      </select>
      <button className="text-brand-600">保存</button>
    </form>
  )
}
