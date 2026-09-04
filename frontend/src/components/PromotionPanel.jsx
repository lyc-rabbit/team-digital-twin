import React, { useEffect, useRef, useState } from 'react'
import {
  TrendingUp, Plus, Loader2, ArrowLeft, SlidersHorizontal, X,
  Trophy, AlertTriangle, Sparkles, Trash2, Square,
} from 'lucide-react'
import { api } from '../api/client.js'
import { RecordEventButton } from './EventRecorderContext.jsx'

const LAYER_ORDER = ['boss', 'team', 'role', 'custom']

export default function PromotionPanel({ members }) {
  const [view, setView] = useState('list') // list | create | detail
  const [templates, setTemplates] = useState(null)
  const [list, setList] = useState([])
  const [roles, setRoles] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [detail, setDetail] = useState(null)
  const [selectedPerson, setSelectedPerson] = useState(null)
  const [weightOpen, setWeightOpen] = useState(false)
  const mountedRef = useRef(true)

  const loadList = async () => {
    const data = await api.listPromotions()
    if (mountedRef.current) setList(data.simulations || [])
  }

  useEffect(() => {
    mountedRef.current = true
    ;(async () => {
      try {
        const [tpl, roleData] = await Promise.all([
          api.getPromotionTemplates(),
          api.getAiNativeRoles(),
        ])
        if (!mountedRef.current) return
        setTemplates(tpl)
        setRoles(roleData.roles || [])
        await loadList()
      } catch (err) {
        if (mountedRef.current) setError(err.message || '加载失败')
      } finally {
        if (mountedRef.current) setLoading(false)
      }
    })()
    return () => { mountedRef.current = false }
  }, [])

  const openDetail = async (id) => {
    setError(null)
    const d = await api.getPromotion(id)
    setDetail(d)
    setSelectedPerson(null)
    setView('detail')
    const st = d.simulation?.status
    if (st === 'running') pollUntilDone(id)
  }

  const pollUntilDone = async (id) => {
    for (let i = 0; i < 200; i++) {
      const st = await api.getPromotionStatus(id)
      if (!mountedRef.current) return
      setDetail((prev) => prev ? { ...prev, simulation: { ...prev.simulation, ...st } } : prev)
      if (st.status === 'ready' || st.status === 'failed' || st.status === 'cancelled') {
        const d = await api.getPromotion(id)
        if (mountedRef.current) setDetail(d)
        await loadList()
        return
      }
      await new Promise((r) => setTimeout(r, 1200))
    }
  }

  const handleCancel = async (id) => {
    try {
      await api.cancelPromotion(id)
      const d = await api.getPromotion(id)
      if (mountedRef.current) setDetail(d)
      await loadList()
    } catch (err) {
      if (mountedRef.current) setError(err.message || '终止失败')
    }
  }

  const handleDelete = async (id, e) => {
    e?.stopPropagation()
    await api.deletePromotion(id)
    await loadList()
    if (detail?.simulation?.id === id) {
      setView('list')
      setDetail(null)
    }
  }

  if (loading) {
    return <div className="flex items-center justify-center h-full text-slate-400 text-sm">加载晋升推演...</div>
  }

  if (view === 'create') {
    return (
      <CreateView
        members={members}
        roles={roles}
        templates={templates}
        onBack={() => setView('list')}
        onCreated={async (sim) => {
          await loadList()
          await openDetail(sim.id)
        }}
        onError={setError}
      />
    )
  }

  if (view === 'detail' && detail) {
    return (
      <>
        <ResultView
          detail={detail}
          selectedPerson={selectedPerson}
          onSelectPerson={setSelectedPerson}
          onBack={() => { setView('list'); setDetail(null) }}
          onOpenWeights={() => setWeightOpen(true)}
          onCancel={() => handleCancel(detail.simulation.id)}
          error={error}
        />
        {weightOpen && (
          <WeightModal
            detail={detail}
            onClose={() => setWeightOpen(false)}
            onSaved={(d) => { setDetail(d); setWeightOpen(false) }}
            onError={setError}
          />
        )}
      </>
    )
  }

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto fade-in">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
            <TrendingUp size={20} className="text-brand-600" />
            晋升领导
          </h2>
          <p className="text-sm text-slate-500 mt-1">
            角色能力 + 项目成长证据 + 新人培养 + 向上协同 + 关系网 + 管理事件。重点回答：为什么还不能晋升。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <RecordEventButton context={{ source: 'promotion', event_type: 'management' }} />
          <button
          onClick={() => setView('create')}
          className="flex items-center gap-1.5 text-sm font-medium text-white bg-brand-600 hover:bg-brand-700 px-3.5 py-2 rounded-lg"
        >
          <Plus size={15} /> 新建推演
        </button>
        </div>
      </div>

      {error && <div className="text-xs bg-red-50 text-red-700 border border-red-100 rounded-lg px-3 py-2">{error}</div>}

      <div className="grid gap-3">
        {list.map((s) => (
          <button
            key={s.id}
            onClick={() => openDetail(s.id).catch((e) => setError(e.message))}
            className="text-left bg-white rounded-2xl border border-slate-100 shadow-sm p-4 hover:border-brand-200 transition-colors"
          >
            <div className="flex items-start gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-slate-800 truncate">{s.name}</span>
                  <StatusBadge status={s.status} />
                </div>
                <div className="text-xs text-slate-500 mt-1">
                  目标岗位：{s.target_role_name || '未指定'}
                  {s.department ? ` · ${s.department}` : ''}
                  {s.top ? ` · 当前第一 ${s.top.name}（${Math.round(s.top.score)} 分）` : ''}
                </div>
              </div>
              <button
                onClick={(e) => handleDelete(s.id, e)}
                className="p-1.5 text-slate-400 hover:text-red-500"
                title="删除"
              >
                <Trash2 size={14} />
              </button>
            </div>
          </button>
        ))}
        {list.length === 0 && (
          <div className="bg-white rounded-2xl border border-slate-100 py-16 text-center text-sm text-slate-400">
            还没有推演任务。选择一个目标领导岗位，系统会结合角色卡、人员画像和影响力图谱给出排名。
          </div>
        )}
      </div>

      {weightOpen && detail && (
        <WeightModal
          detail={detail}
          onClose={() => setWeightOpen(false)}
          onSaved={(d) => { setDetail(d); setWeightOpen(false) }}
          onError={setError}
        />
      )}
    </div>
  )
}

function CreateView({ members, roles, templates, onBack, onCreated, onError }) {
  const styles = templates?.styles || []
  const [saving, setSaving] = useState(false)
  const [name, setName] = useState('')
  const [roleId, setRoleId] = useState(roles[0]?.id || 'leader')
  const [department, setDepartment] = useState('')
  const [styleId, setStyleId] = useState(styles[0]?.id || 'tech_expert')
  const [scope, setScope] = useState('all')
  const [picked, setPicked] = useState([])
  const style = styles.find((s) => s.id === styleId) || styles[0]
  const [reqs, setReqs] = useState(() => reqsFromStyle(style))

  useEffect(() => {
    setReqs(reqsFromStyle(styles.find((s) => s.id === styleId)))
  }, [styleId])

  const submit = async () => {
    setSaving(true)
    onError?.(null)
    try {
      const payload = {
        name: name.trim() || undefined,
        target_role_id: roleId,
        department,
        style_id: styleId,
        leadership_style: style ? {
          id: style.id, type: style.type, name: style.name,
          description: style.description, weights: style.weights,
        } : undefined,
        custom_requirements: reqs.filter((r) => r.name.trim()),
        candidate_scope: scope === 'all' ? ['all'] : picked,
      }
      const res = await api.createPromotion(payload)
      await onCreated(res.simulation)
    } catch (err) {
      onError?.(err.message || '创建失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="p-6 max-w-3xl mx-auto fade-in space-y-5">
      <button onClick={onBack} className="flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700">
        <ArrowLeft size={15} /> 返回
      </button>
      <div>
        <h2 className="text-xl font-bold text-slate-800">创建晋升推演</h2>
        <p className="text-sm text-slate-500 mt-1">先选定目标岗位与领导风格，系统会做一次 AI 事实分析；之后改权重不再调用模型。</p>
      </div>

      <section className="bg-white rounded-2xl border border-slate-100 p-5 space-y-4">
        <Field label="推演名称">
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="例如：2026 AI组负责人晋升分析"
            className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 outline-none focus:border-brand-400" />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="目标岗位（角色卡）">
            <select value={roleId} onChange={(e) => setRoleId(e.target.value)}
              className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2">
              {roles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
            </select>
          </Field>
          <Field label="部门">
            <input value={department} onChange={(e) => setDepartment(e.target.value)} placeholder="例如：AI研发部"
              className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 outline-none focus:border-brand-400" />
          </Field>
        </div>
        <Field label="候选人范围">
          <div className="flex gap-3 text-sm">
            <label className="flex items-center gap-1.5">
              <input type="radio" checked={scope === 'all'} onChange={() => setScope('all')} /> 全部成员
            </label>
            <label className="flex items-center gap-1.5">
              <input type="radio" checked={scope === 'pick'} onChange={() => setScope('pick')} /> 指定成员
            </label>
          </div>
          {scope === 'pick' && (
            <div className="flex flex-wrap gap-1.5 mt-2">
              {members.map((m) => {
                const on = picked.includes(m.id)
                return (
                  <button key={m.id} type="button" onClick={() => setPicked((p) => on ? p.filter((x) => x !== m.id) : [...p, m.id])}
                    className={`text-[11px] px-2 py-1 rounded-full border ${on ? 'bg-brand-600 text-white border-brand-600' : 'border-slate-200 text-slate-600'}`}>
                    {m.name}
                  </button>
                )
              })}
            </div>
          )}
        </Field>
      </section>

      <section className="bg-white rounded-2xl border border-slate-100 p-5 space-y-3">
        <h3 className="text-sm font-bold text-slate-800">领导风格模板</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
          {styles.map((s) => (
            <button key={s.id} type="button" onClick={() => setStyleId(s.id)}
              className={`text-left p-3 rounded-xl border ${styleId === s.id ? 'border-brand-500 bg-brand-50' : 'border-slate-100 hover:border-slate-200'}`}>
              <div className="text-sm font-semibold text-slate-800">{s.name}</div>
              <p className="text-[11px] text-slate-500 mt-1 leading-relaxed">{s.description}</p>
            </button>
          ))}
        </div>
        <div>
          <div className="text-xs font-medium text-slate-600 mb-2">个性化要求（可改权重）</div>
          <div className="space-y-2">
            {reqs.map((r, i) => (
              <div key={i} className="flex items-center gap-2">
                <input value={r.name} onChange={(e) => setReqs(editReq(reqs, i, { name: e.target.value }))}
                  className="flex-1 text-sm border border-slate-200 rounded-lg px-2 py-1.5" />
                <input type="number" min={0} max={100} value={r.weight}
                  onChange={(e) => setReqs(editReq(reqs, i, { weight: Number(e.target.value) }))}
                  className="w-16 text-sm border border-slate-200 rounded-lg px-2 py-1.5" />
                <span className="text-[11px] text-slate-400">%</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <button onClick={submit} disabled={saving}
        className="flex items-center gap-1.5 text-sm font-medium text-white bg-brand-600 hover:bg-brand-700 disabled:opacity-50 px-4 py-2.5 rounded-lg">
        {saving ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />}
        {saving ? '正在创建...' : '开始推演'}
      </button>
    </div>
  )
}

function ResultView({ detail, selectedPerson, onSelectPerson, onBack, onOpenWeights, onCancel, error }) {
  const sim = detail.simulation || {}
  const results = detail.results || []
  const model = detail.model || {}
  const layer = model.layer_weights || {}
  const running = sim.status === 'running'
  const person = results.find((r) => r.person_id === selectedPerson)

  return (
    <div className="p-6 max-w-6xl mx-auto fade-in space-y-5">
      <button onClick={onBack} className="flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700">
        <ArrowLeft size={15} /> 返回列表
      </button>
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-800">{sim.name}</h2>
          <p className="text-sm text-slate-500 mt-1">
            目标岗位：{sim.target_role_name || '未指定'}
            {sim.department ? ` · ${sim.department}` : ''}
          </p>
        </div>
        <button onClick={onOpenWeights} disabled={running}
          className="flex items-center gap-1.5 text-sm font-medium text-slate-700 bg-white border border-slate-200 hover:bg-slate-50 disabled:opacity-50 px-3 py-2 rounded-lg">
          <SlidersHorizontal size={14} /> 调整评价模型
        </button>
      </div>

      <div className="flex flex-wrap gap-2 text-xs">
        {LAYER_ORDER.map((k) => (
          <span key={k} className="bg-white border border-slate-100 rounded-full px-3 py-1 text-slate-600">
            {(model.layer_labels || {})[k] || k} {layer[k] ?? '-'}%
          </span>
        ))}
        {sim.mock_mode && <span className="text-amber-600">降级分析</span>}
      </div>

      {running && (
        <div className="bg-brand-50 border border-brand-100 rounded-xl px-4 py-3">
          <div className="flex justify-between text-sm text-brand-700 mb-2">
            <span className="flex items-center gap-2"><Loader2 size={14} className="animate-spin" />{sim.message || '分析中...'}</span>
            <span>{sim.progress || 0}%</span>
          </div>
          <div className="w-full bg-white rounded-full h-1.5 overflow-hidden">
            <div className="h-1.5 bg-brand-500 rounded-full" style={{ width: `${Math.min(100, sim.progress || 0)}%` }} />
          </div>
          <div className="flex items-center justify-between gap-3 mt-2">
            <span className="text-xs text-brand-600">
              {sim.eta_text || '正在估算剩余时间…'}
              {sim.elapsed_seconds ? ` · 已等待 ${sim.elapsed_seconds} 秒` : ''}
            </span>
            <button
              type="button"
              onClick={onCancel}
              className="flex items-center gap-1 text-xs font-medium text-red-600 bg-white border border-red-200 hover:bg-red-50 px-2.5 py-1 rounded-lg"
            >
              <Square size={10} fill="currentColor" /> 终止
            </button>
          </div>
        </div>
      )}
      {error && <div className="text-xs bg-red-50 text-red-700 rounded-lg px-3 py-2">{error}</div>}
      {sim.status === 'failed' && <div className="text-xs bg-red-50 text-red-700 rounded-lg px-3 py-2">{sim.error || sim.message}</div>}
      {sim.status === 'cancelled' && <div className="text-xs bg-slate-100 text-slate-600 rounded-lg px-3 py-2">{sim.message || '任务已终止'}</div>}

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_340px] gap-4">
        <div className="space-y-3">
          {results.map((r) => (
            <button key={r.person_id} onClick={() => onSelectPerson(r.person_id)}
              className={`w-full text-left bg-white rounded-2xl border p-4 ${selectedPerson === r.person_id ? 'border-brand-400 shadow-sm' : 'border-slate-100'}`}>
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center text-sm font-bold text-slate-500">
                  {r.rank}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-semibold text-slate-800">{r.name}</div>
                  <div className="text-[11px] text-slate-400">{r.role}</div>
                </div>
                <div className="text-right">
                  <div className="text-lg font-bold text-brand-600">{Math.round(r.score)}</div>
                  <div className="text-[11px] text-slate-400">晋升概率 {r.promotion_probability}%</div>
                </div>
              </div>
              <div className="grid grid-cols-4 gap-2 mt-3">
                {LAYER_ORDER.map((k) => (
                  <MiniBar key={k} label={(model.layer_labels || {})[k]} value={r.layer_scores?.[k]} />
                ))}
              </div>
            </button>
          ))}
          {!results.length && !running && (
            <div className="bg-white rounded-2xl border border-slate-100 py-12 text-center text-sm text-slate-400">暂无结果</div>
          )}
        </div>
        <aside className="bg-white rounded-2xl border border-slate-100 p-4 h-fit">
          {!person ? (
            <p className="text-xs text-slate-400">点击左侧候选人查看事实、理由、风险与任职预期。改权重后排名会立刻更新，不会重新调用 AI。</p>
          ) : (
            <PersonReport person={person} />
          )}
        </aside>
      </div>
    </div>
  )
}

function PersonReport({ person }) {
  const a = person.analysis_json || {}
  const pred = a.future_prediction || {}
  const g = person.growth || {}
  return (
    <div className="space-y-4">
      <div>
        <div className="flex items-center gap-2">
          <Trophy size={16} className="text-brand-600" />
          <span className="font-bold text-slate-800">{person.name}</span>
        </div>
        <div className="text-[11px] text-slate-400 mt-0.5">综合 {Math.round(person.score)} · 概率 {person.promotion_probability}%</div>
      </div>
      {g.management_ability && (
        <div className="bg-slate-50 rounded-xl p-3 space-y-1">
          <div className="text-[11px] font-bold text-slate-600">当前管理能力</div>
          <p className="text-xs text-slate-700">{g.management_ability} · {g.current_stage}</p>
        </div>
      )}
      <Block title="优势" items={g.strengths?.length ? g.strengths : a.reasoning} />
      <Block title="短板" items={g.weaknesses} />
      <div className="bg-amber-50 border border-amber-100 rounded-xl p-3">
        <div className="text-[11px] font-bold text-amber-800 mb-1">为什么还不能晋升？</div>
        <ul className="text-xs text-amber-900 space-y-1">
          {(g.why_not_promote || ['成长证据不足']).map((x, i) => <li key={i}>· {x}</li>)}
        </ul>
      </div>
      <Block title="缺失经历" items={g.missing_experiences} />
      <Block title="推荐培养动作" items={g.recommended_actions} />
      <Block title="事实" items={a.facts} />
      {a.relationship?.influence && (
        <div>
          <div className="text-[11px] font-bold text-slate-600 mb-1">组织关系</div>
          <p className="text-xs text-slate-600">{a.relationship.influence}</p>
        </div>
      )}
      <Block title="晋升理由" items={a.reasoning} />
      <div>
        <div className="text-[11px] font-bold text-slate-600 mb-1 flex items-center gap-1">
          <AlertTriangle size={12} className="text-amber-500" /> 晋升风险
        </div>
        <ul className="text-xs text-slate-600 space-y-1">
          {(g.promotion_risks || a.risk || ['暂无']).map((x, i) => <li key={i}>· {x}</li>)}
        </ul>
      </div>
      <div className="bg-slate-50 rounded-xl p-3">
        <div className="text-[11px] font-bold text-slate-600 mb-1">任职后预期</div>
        <p className="text-xs text-slate-600">{pred.expected_result || '—'}</p>
        {pred.team_size_growth != null && (
          <p className="text-[11px] text-slate-400 mt-1">团队规模增长预期：{pred.team_size_growth} 人</p>
        )}
      </div>
    </div>
  )
}

function WeightModal({ detail, onClose, onSaved, onError }) {
  const sim = detail.simulation || {}
  const labels = detail.model?.layer_labels || {}
  const [weights, setWeights] = useState({ ...(sim.layer_weights || {}) })
  const [saving, setSaving] = useState(false)
  const sum = LAYER_ORDER.reduce((s, k) => s + Number(weights[k] || 0), 0)

  const save = async () => {
    setSaving(true)
    onError?.(null)
    try {
      const res = await api.updatePromotionWeights(sim.id, { layer_weights: weights })
      onSaved({ simulation: res.simulation, results: res.results, model: res.model, weights: res.weights })
    } catch (err) {
      onError?.(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl w-full max-w-md p-5 shadow-xl">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-bold text-slate-800">评分模型配置</h3>
          <button onClick={onClose} className="text-slate-400"><X size={16} /></button>
        </div>
        <p className="text-xs text-slate-500 mb-4">保存后只按已有事实重算分数与排名，不会重新调用 AI。</p>
        <div className="space-y-3">
          {LAYER_ORDER.map((k) => (
            <div key={k}>
              <div className="flex justify-between text-xs text-slate-600 mb-1">
                <span>{labels[k] || k}</span>
                <span className="font-semibold">{weights[k] ?? 0}%</span>
              </div>
              <input type="range" min={0} max={80} value={weights[k] ?? 0}
                onChange={(e) => setWeights((w) => ({ ...w, [k]: Number(e.target.value) }))}
                className="w-full" />
            </div>
          ))}
        </div>
        <div className={`text-[11px] mt-2 ${Math.abs(sum - 100) > 1 ? 'text-amber-600' : 'text-slate-400'}`}>
          合计 {sum}%{Math.abs(sum - 100) > 1 ? '（保存时会按比例归一到 100%）' : ''}
        </div>
        <div className="flex justify-end gap-2 mt-4">
          <button onClick={onClose} className="text-sm px-3 py-2 text-slate-500">取消</button>
          <button onClick={save} disabled={saving}
            className="text-sm font-medium text-white bg-brand-600 hover:bg-brand-700 disabled:opacity-50 px-3.5 py-2 rounded-lg">
            {saving ? '重算中...' : '保存并重新计算'}
          </button>
        </div>
      </div>
    </div>
  )
}

function Field({ label, children }) {
  return (
    <label className="block space-y-1">
      <span className="text-xs font-medium text-slate-600">{label}</span>
      {children}
    </label>
  )
}

function StatusBadge({ status }) {
  const map = {
    running: 'bg-brand-50 text-brand-700',
    ready: 'bg-emerald-50 text-emerald-700',
    failed: 'bg-red-50 text-red-700',
    draft: 'bg-slate-100 text-slate-500',
    cancelled: 'bg-slate-100 text-slate-600',
  }
  const text = { running: '分析中', ready: '已完成', failed: '失败', draft: '草稿', cancelled: '已终止' }
  return <span className={`text-[10px] px-1.5 py-0.5 rounded ${map[status] || map.draft}`}>{text[status] || status}</span>
}

function MiniBar({ label, value }) {
  const v = Math.round(Number(value) || 0)
  return (
    <div>
      <div className="text-[10px] text-slate-400 truncate">{label}</div>
      <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden mt-0.5">
        <div className="h-full bg-brand-500" style={{ width: `${Math.min(100, v)}%` }} />
      </div>
    </div>
  )
}

function Block({ title, items }) {
  const list = items?.length ? items : null
  if (!list) return null
  return (
    <div>
      <div className="text-[11px] font-bold text-slate-600 mb-1">{title}</div>
      <ul className="text-xs text-slate-600 space-y-1">
        {list.map((x, i) => <li key={i}>· {x}</li>)}
      </ul>
    </div>
  )
}

function reqsFromStyle(style) {
  if (!style) return [{ name: '技术深度', weight: 30 }, { name: '团队培养', weight: 25 }, { name: '业务理解', weight: 25 }, { name: '创新能力', weight: 20 }]
  const labels = style.labels || {}
  const weights = style.weights || {}
  return Object.keys(weights).map((k) => ({ name: labels[k] || k, weight: weights[k] }))
}

function editReq(list, i, patch) {
  return list.map((r, idx) => idx === i ? { ...r, ...patch } : r)
}
