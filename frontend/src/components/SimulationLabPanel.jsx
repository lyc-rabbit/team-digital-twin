import React, { useEffect, useMemo, useState } from 'react'
import { FlaskConical, Loader2, AlertTriangle } from 'lucide-react'
import { api } from '../api/client.js'

const TABS = [
  { id: 'simulate', label: '管理推演' },
  { id: 'growth', label: '成长预测' },
  { id: 'train', label: '培养方案' },
  { id: 'org', label: '组织模拟' },
  { id: 'policy', label: '制度中心' },
  { id: 'history', label: '推演记录' },
]

const SEV = {
  high: 'text-red-700 bg-red-50 border-red-100',
  medium: 'text-amber-800 bg-amber-50 border-amber-100',
  low: 'text-slate-600 bg-slate-50 border-slate-100',
}

function fmt(t) {
  if (!t) return ''
  return String(t).replace('T', ' ').slice(0, 16)
}

function Judgment({ judgment, title = '判断依据' }) {
  if (!judgment) return null
  return (
    <div className="mt-3 rounded-xl border border-slate-100 bg-slate-50/80 p-3 space-y-2">
      <div className="text-[11px] font-semibold text-slate-500">{title} · 规则计算，不是 LLM 打分</div>
      <div>
        <div className="text-[10px] text-slate-400">结论</div>
        <p className="text-sm font-medium text-slate-800">{judgment.conclusion}</p>
      </div>
      <div>
        <div className="text-[10px] text-slate-400">原因</div>
        <p className="text-xs text-slate-600 leading-relaxed">{judgment.reason}</p>
      </div>
      <div>
        <div className="text-[10px] text-slate-400">证据</div>
        {(judgment.evidence || []).length === 0 ? (
          <p className="text-xs text-slate-400">暂无引用事实</p>
        ) : (judgment.evidence || []).map((e, i) => (
          <div key={i} className="text-xs text-slate-600 py-1 border-b border-white/70 last:border-0">
            <span className="text-slate-400">{fmt(e.time)}</span>
            {e.source && <span className="ml-1.5 text-[10px] px-1.5 py-0.5 rounded bg-white">{e.source}</span>}
            <span className="ml-1.5 font-medium">{e.title}</span>
            {e.text && <div className="text-slate-500 mt-0.5">{e.text}</div>}
          </div>
        ))}
      </div>
      <div className="text-[10px] text-slate-400">时间 {fmt(judgment.time) || '—'} · 来源 {judgment.source === 'llm' ? '模型复述' : '规则引擎'}</div>
    </div>
  )
}

function MetricGrid({ metrics }) {
  const entries = Object.entries(metrics || {})
  if (!entries.length) return null
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
      {entries.map(([k, v]) => {
        const val = v && typeof v === 'object' ? v.value : v
        const arrow = v && typeof v === 'object' ? v.arrow : ''
        const level = v && typeof v === 'object' ? v.level : ''
        return (
          <div key={k} className={`rounded-xl border px-3 py-2 ${SEV[level] || 'border-slate-100 bg-white'}`}>
            <div className="text-[11px] text-slate-500">{k}</div>
            <div className="text-lg font-bold text-slate-800">{val}{arrow ? ` ${arrow}` : ''}</div>
            {v && v.current != null && <div className="text-[10px] text-slate-400">当前 {v.current}</div>}
          </div>
        )
      })}
    </div>
  )
}

function ResultCard({ result }) {
  if (!result) return null
  const risks = result.risks || []
  return (
    <section className="bg-white rounded-2xl border border-slate-100 p-5 space-y-4">
      <div>
        <div className="text-[11px] text-slate-400">场景</div>
        <h3 className="text-lg font-bold text-slate-800">{result.title || result.scenario_label}</h3>
        {result.narrative && <p className="text-sm text-slate-600 mt-1">{result.narrative}</p>}
        {result.is_prediction && <p className="text-[11px] text-amber-700 mt-1">本页内容为情景推演 / 风险预测，不能当作已发生事实。</p>}
      </div>
      <div>
        <div className="text-[11px] font-semibold text-slate-500 mb-2">预计结果</div>
        <MetricGrid metrics={result.metrics || result.impact} />
      </div>
      {risks.length > 0 && (
        <div>
          <div className="text-[11px] font-semibold text-slate-500 mb-2">最大风险</div>
          <ol className="space-y-1">
            {risks.slice(0, 6).map((r, i) => (
              <li key={i} className="text-sm text-slate-700 flex gap-2">
                <span className="text-slate-400">{i + 1}.</span>
                <span>{r.title || r}</span>
                {r.level && <span className={`text-[10px] px-1.5 py-0.5 rounded ${SEV[r.level] || ''}`}>{r.level === 'high' ? '高' : r.level === 'medium' ? '中' : '低'}</span>}
              </li>
            ))}
          </ol>
        </div>
      )}
      {(result.recommendations || []).length > 0 && (
        <div>
          <div className="text-[11px] font-semibold text-slate-500 mb-2">推荐</div>
          <ol className="space-y-1">
            {result.recommendations.map((r, i) => (
              <li key={i} className="text-sm text-slate-700">{i + 1}. {typeof r === 'string' ? r : r.title || r.name}</li>
            ))}
          </ol>
        </div>
      )}
      <Judgment judgment={result.judgment} />
    </section>
  )
}

export default function SimulationLabPanel({ members = [] }) {
  const [tab, setTab] = useState('simulate')
  const [boot, setBoot] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  const [scenario, setScenario] = useState('mentor_people')
  const [personId, setPersonId] = useState(members[0]?.id || '')
  const [reportees, setReportees] = useState([])
  const [projectId, setProjectId] = useState('')
  const [question, setQuestion] = useState('')
  const [addN, setAddN] = useState(10)
  const [addS, setAddS] = useState(2)
  const [addM, setAddM] = useState(1)
  const [days, setDays] = useState(90)
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)

  const [growth, setGrowth] = useState(null)
  const [path, setPath] = useState(null)
  const [plan, setPlan] = useState(null)
  const [schemes, setSchemes] = useState(null)
  const [cohort, setCohort] = useState(null)
  const [orgView, setOrgView] = useState(null)
  const [policies, setPolicies] = useState(null)
  const [history, setHistory] = useState([])
  const [preds, setPreds] = useState([])
  const [actualDays, setActualDays] = useState('')

  const people = boot?.members?.length ? boot.members : members.map((m) => ({ id: m.id, name: m.name, role: m.role }))

  useEffect(() => {
    api.getTwinBootstrap().then((d) => {
      setBoot(d)
      if (!personId && d.members?.[0]) setPersonId(d.members[0].id)
    }).catch((e) => setError(e.message)).finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!personId && members[0]?.id) setPersonId(members[0].id)
  }, [members, personId])

  const selectedScenario = useMemo(
    () => (boot?.scenarios || []).find((s) => s.id === scenario),
    [boot, scenario],
  )

  const run = async () => {
    setBusy(true)
    setError(null)
    try {
      const payload = {
        scenario,
        person_id: personId,
        manager_id: personId,
        reportee_ids: reportees,
        project_id: projectId || undefined,
        question: question || undefined,
        days,
        add_newcomers: Number(addN),
        add_seniors: Number(addS),
        add_managers: Number(addM),
        target_id: personId,
      }
      const d = await api.runTwinSimulate(payload)
      setResult(d)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const loadGrowth = async () => {
    if (!personId) return
    setBusy(true)
    try {
      const [g, p] = await Promise.all([api.getTwinGrowth(personId, days), api.getTwinPath(personId)])
      setGrowth(g)
      setPath(p)
    } catch (e) { setError(e.message) }
    finally { setBusy(false) }
  }

  const loadTrain = async (kind) => {
    setBusy(true)
    try {
      if (kind === 'plan') setPlan(await api.createTwinPlan({ person_id: personId, mentor_id: personId, days: 60, from_level: 'L1', to_level: 'L2' }))
      if (kind === 'compare') setSchemes(await api.compareTwinSchemes({ person_id: reportees[0] || personId, mentor_id: personId }))
      if (kind === 'cohort') setCohort(await api.simulateTwinCohort({ hire_count: Number(addN) || 10 }))
      if (kind === 'opt' && (reportees[0] || personId)) setPlan((prev) => ({ ...prev, optimize: true, opt: null }))
      if (kind === 'opt') {
        const opt = await api.optimizeTwinPlan(reportees[0] || personId)
        setPlan((prev) => ({ ...(prev || {}), optimize: opt }))
      }
    } catch (e) { setError(e.message) }
    finally { setBusy(false) }
  }

  const loadOrg = async (kind) => {
    setBusy(true)
    try {
      if (kind === 'expand') setOrgView({ kind, data: await api.expandTwinOrg({ add_newcomers: Number(addN), add_seniors: Number(addS), add_managers: Number(addM) }) })
      if (kind === 'depart') setOrgView({ kind, data: await api.getTwinDeparture(personId) })
      if (kind === 'struct') setOrgView({ kind, data: await api.getTwinStructures() })
      if (kind === 'informal') setOrgView({ kind, data: await api.getTwinInformal() })
      if (kind === 'knowledge') setOrgView({ kind, data: await api.getTwinKnowledge(personId) })
      if (kind === 'pipeline') setOrgView({ kind, data: await api.getTwinPipeline() })
      if (kind === 'conflict' && reportees[0]) setOrgView({ kind, data: await api.predictTwinConflict({ person_a: personId, person_b: reportees[0] }) })
    } catch (e) { setError(e.message) }
    finally { setBusy(false) }
  }

  const loadPolicies = async () => {
    try { setPolicies(await api.getTwinPolicies()) } catch (e) { setError(e.message) }
  }
  const loadHistory = async () => {
    try {
      const [s, p] = await Promise.all([api.listTwinSimulations(), api.listTwinPredictions(personId)])
      setHistory(s.items || [])
      setPreds(p.items || [])
    } catch (e) { setError(e.message) }
  }

  useEffect(() => {
    if (tab === 'policy') loadPolicies()
    if (tab === 'history') loadHistory()
  }, [tab, personId])

  const toggleReportee = (id) => {
    setReportees((cur) => cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id])
  }

  if (loading) {
    return <div className="flex items-center justify-center h-full text-slate-400 text-sm"><Loader2 size={16} className="animate-spin mr-2" />加载模拟实验室...</div>
  }

  return (
    <div className="p-6 max-w-6xl mx-auto fade-in space-y-5">
      <div>
        <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
          <FlaskConical size={20} className="text-brand-600" /> 模拟实验室
        </h2>
        <p className="text-sm text-slate-500 mt-1">
          用已有事实做组织级推演：如果改变岗位、带人、扩张或有人离开，会发生什么。分数由规则计算，模型只解释。
        </p>
      </div>

      <div className="flex flex-wrap gap-1 bg-slate-100 rounded-xl p-1 w-fit">
        {TABS.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`px-3 py-1.5 rounded-lg text-sm ${tab === t.id ? 'bg-white text-slate-800 shadow-sm font-semibold' : 'text-slate-500'}`}>
            {t.label}
          </button>
        ))}
      </div>
      {error && <div className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</div>}

      {tab === 'simulate' && (
        <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-4">
          <section className="bg-white rounded-2xl border border-slate-100 p-5 space-y-3">
            <h3 className="text-sm font-bold text-slate-800">选择场景</h3>
            {(boot?.scenarios || []).map((s) => (
              <label key={s.id} className={`flex gap-2 items-start rounded-lg border px-3 py-2 cursor-pointer ${scenario === s.id ? 'border-brand-400 bg-brand-50' : 'border-slate-100'}`}>
                <input type="radio" name="sc" checked={scenario === s.id} onChange={() => setScenario(s.id)} className="mt-1" />
                <span>
                  <div className="text-sm font-medium text-slate-800">{s.label}</div>
                  <div className="text-[11px] text-slate-400">{s.hint}</div>
                </span>
              </label>
            ))}
            <label className="block text-[11px] text-slate-500">主体人员</label>
            <select className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={personId} onChange={(e) => setPersonId(e.target.value)}>
              {people.map((m) => <option key={m.id} value={m.id}>{m.name}{m.person_type ? ` · ${m.person_type}` : ''}</option>)}
            </select>
            {(scenario === 'mentor_people' || scenario === 'custom') && (
              <div>
                <div className="text-[11px] text-slate-500 mb-1">被管理人员</div>
                <div className="max-h-36 overflow-auto space-y-1">
                  {people.filter((m) => m.id !== personId).map((m) => (
                    <label key={m.id} className="flex items-center gap-2 text-xs text-slate-700">
                      <input type="checkbox" checked={reportees.includes(m.id)} onChange={() => toggleReportee(m.id)} />
                      {m.name}
                    </label>
                  ))}
                </div>
              </div>
            )}
            {scenario === 'own_project' && (
              <select className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
                <option value="">选择项目（可选）</option>
                {(boot?.projects || []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            )}
            {scenario === 'expand' && (
              <div className="grid grid-cols-3 gap-2">
                <Num label="+新人" value={addN} onChange={setAddN} />
                <Num label="+高级" value={addS} onChange={setAddS} />
                <Num label="+管理" value={addM} onChange={setAddM} />
              </div>
            )}
            {scenario === 'promotion' && (
              <select className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={days} onChange={(e) => setDays(Number(e.target.value))}>
                {[30, 60, 90, 180].map((d) => <option key={d} value={d}>{d} 天</option>)}
              </select>
            )}
            {scenario === 'custom' && (
              <textarea className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm min-h-[80px]"
                placeholder="例如：如果我同时带 3 个人会怎样？"
                value={question} onChange={(e) => setQuestion(e.target.value)} />
            )}
            <button onClick={run} disabled={busy} className="w-full bg-brand-600 hover:bg-brand-700 disabled:opacity-60 text-white text-sm rounded-lg py-2">
              {busy ? '推演中…' : '开始推演'}
            </button>
          </section>
          {result ? <ResultCard result={result} /> : (
            <section className="bg-white rounded-2xl border border-dashed border-slate-200 p-8 text-sm text-slate-400">
              {selectedScenario?.hint || '选择左侧场景后开始推演。'}
              <p className="text-[11px] mt-3">验收情景：新人培养周期、同时带 A/B/C、晋升时间、5→15 人扩张、核心成员离开。</p>
            </section>
          )}
        </div>
      )}

      {tab === 'growth' && (
        <div className="space-y-4">
          <div className="flex flex-wrap gap-3 items-end">
            <select className="border border-slate-200 rounded-lg px-3 py-2 text-sm" value={personId} onChange={(e) => setPersonId(e.target.value)}>
              {people.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
            <select className="border border-slate-200 rounded-lg px-3 py-2 text-sm" value={days} onChange={(e) => setDays(Number(e.target.value))}>
              {[30, 60, 90, 180].map((d) => <option key={d} value={d}>{d} 天</option>)}
            </select>
            <button onClick={loadGrowth} disabled={busy} className="bg-brand-600 text-white text-sm rounded-lg px-4 py-2 disabled:opacity-60">预测</button>
          </div>
          {growth && (
            <section className="bg-white rounded-2xl border border-slate-100 p-5 space-y-3">
              <h3 className="text-sm font-bold">{growth.name} · {growth.person_type} · 未来 {growth.horizon_days} 天</h3>
              <div className="text-sm">管理岗位准备度 {growth.readiness.current}% → {growth.readiness.predicted}%
                {growth.days_to_target != null && <span className="ml-2 text-slate-500">预计约 {growth.days_to_target} 天达到观察线</span>}
              </div>
              {(growth.timeline || []).map((t) => (
                <span key={t.days} className="inline-block text-xs mr-3 text-slate-600">{t.days}天 → {t.readiness}%</span>
              ))}
              {(growth.capabilities || []).map((c) => (
                <div key={c.id} className="flex justify-between text-sm border-b border-slate-50 py-1">
                  <span>{c.label}</span><span>当前 {c.current} → 预测 {c.predicted}</span>
                </div>
              ))}
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div><div className="font-semibold text-emerald-700 mb-1">加速因素</div>{(growth.accelerators || []).map((x) => <div key={x}>· {x}</div>)}</div>
                <div><div className="font-semibold text-amber-700 mb-1">延迟因素</div>{(growth.delays || []).map((x) => <div key={x}>· {x}</div>)}</div>
              </div>
              <p className="text-[11px] text-slate-400">依据：当前能力 + 历史速度 + 已完成实践 + 培养活跃度 + 剩余缺口。{growth.note}</p>
              <Judgment judgment={growth.judgment} />
            </section>
          )}
          {path?.path && (
            <section className="bg-white rounded-2xl border border-slate-100 p-5">
              <h3 className="text-sm font-bold mb-2">干部培养路线</h3>
              <div className="flex flex-wrap gap-2">
                {(path.path.steps || []).map((s) => (
                  <div key={s.id} className={`text-xs px-2 py-1 rounded-lg border ${s.status === '✓' ? 'bg-emerald-50 text-emerald-800' : s.status === '当前' ? 'bg-brand-50 text-brand-800 border-brand-200' : 'bg-slate-50 text-slate-500'}`}>
                    {s.label} · {s.status}
                  </div>
                ))}
              </div>
              <p className="text-sm mt-3">{path.path.next_practice}</p>
              {path.type && <p className="text-xs text-slate-500 mt-2">管理类型：{path.type.type}</p>}
              {path.style && <p className="text-xs text-slate-500">更适合：{path.style.fit_team}</p>}
              <Judgment judgment={path.path.judgment} />
            </section>
          )}
        </div>
      )}

      {tab === 'train' && (
        <div className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <select className="border border-slate-200 rounded-lg px-3 py-2 text-sm" value={personId} onChange={(e) => setPersonId(e.target.value)}>
              {people.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
            <button className="bg-brand-600 text-white text-sm rounded-lg px-3 py-2" onClick={() => loadTrain('plan')}>生成方案</button>
            <button className="border border-slate-200 text-sm rounded-lg px-3 py-2" onClick={() => loadTrain('opt')}>按实际优化</button>
            <button className="border border-slate-200 text-sm rounded-lg px-3 py-2" onClick={() => loadTrain('compare')}>对比 A/B/C</button>
            <button className="border border-slate-200 text-sm rounded-lg px-3 py-2" onClick={() => loadTrain('cohort')}>模拟招 {addN} 人</button>
            <Num label="人数" value={addN} onChange={setAddN} />
          </div>
          {plan?.stages && (
            <section className="bg-white rounded-2xl border border-slate-100 p-5 space-y-3">
              <h3 className="text-sm font-bold">{plan.from_level}→{plan.to_level} · {plan.days} 天 · 导师 {plan.mentor_name || '未指定'}</h3>
              {plan.stages.map((s) => (
                <div key={s.week} className="border-b border-slate-50 pb-2">
                  <div className="text-sm font-semibold">{s.week} {s.theme}</div>
                  <div className="text-xs text-slate-600">目标：{s.goal}</div>
                  <div className="text-xs text-slate-500">AI：{s.ai} · 导师：{s.mentor}</div>
                  <div className="text-xs text-amber-700">风险：{s.risk}</div>
                </div>
              ))}
              {plan.optimize && <Judgment judgment={plan.optimize.judgment} title="方案优化" />}
              <Judgment judgment={plan.judgment} />
            </section>
          )}
          {schemes && (
            <section className="bg-white rounded-2xl border border-slate-100 p-5">
              <h3 className="text-sm font-bold mb-2">培养方案对比 · 推荐 {schemes.recommended}</h3>
              <table className="w-full text-xs">
                <thead><tr className="text-slate-400 text-left"><th className="py-1">方案</th><th>达标天</th><th>导师成本</th><th>AI依赖</th><th>独立性</th><th>综合</th></tr></thead>
                <tbody>
                  {(schemes.schemes || []).map((s) => (
                    <tr key={s.id} className={s.id === schemes.recommended ? 'bg-brand-50 font-semibold' : ''}>
                      <td className="py-1">{s.name}</td><td>{s.days}</td><td>{s.mentor_cost}</td><td>{s.ai_dependency}</td><td>{s.independence}</td><td>{s.score}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <Judgment judgment={schemes.judgment} />
            </section>
          )}
          {cohort && (
            <section className="bg-white rounded-2xl border border-slate-100 p-5 text-sm space-y-2">
              <h3 className="font-bold">招 {cohort.hire_count} 人</h3>
              <p>需要导师 {cohort.mentor_needed}，可用 {cohort.mentor_available}，预计 {cohort.expected_l2_count} 人达 L2（{cohort.expected_l2_rate}%）。</p>
              {(cohort.suitable_mentors || []).map((m) => (
                <div key={m.person_id} className="text-xs">{m.name} 分配 {m.assigned} 人{m.overloaded ? ' · 负荷偏高' : ''}</div>
              ))}
              <Judgment judgment={cohort.judgment} />
            </section>
          )}
        </div>
      )}

      {tab === 'org' && (
        <div className="space-y-4">
          {boot?.pipeline && (
            <section className="bg-white rounded-2xl border border-slate-100 p-5">
              <h3 className="text-sm font-bold mb-2">人才梯队 · {boot.pipeline.health}</h3>
              <div className="flex flex-wrap gap-2">
                {Object.entries(boot.pipeline.pipeline || {}).map(([k, v]) => (
                  <div key={k} className="text-xs bg-slate-50 rounded-lg px-3 py-2"><span className="text-slate-400">{k}</span> <b>{v}</b></div>
                ))}
              </div>
              {(boot.pipeline.issues || []).map((x) => <p key={x} className="text-xs text-amber-700 mt-2">· {x}</p>)}
            </section>
          )}
          <div className="flex flex-wrap gap-2 items-end">
            <select className="border border-slate-200 rounded-lg px-3 py-2 text-sm" value={personId} onChange={(e) => setPersonId(e.target.value)}>
              {people.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
            <select className="border border-slate-200 rounded-lg px-3 py-2 text-sm" value={reportees[0] || ''} onChange={(e) => setReportees(e.target.value ? [e.target.value] : [])}>
              <option value="">冲突对象 / 对照人员</option>
              {people.filter((m) => m.id !== personId).map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
            <Num label="+新人" value={addN} onChange={setAddN} />
            <button className="bg-brand-600 text-white text-sm rounded-lg px-3 py-2" onClick={() => loadOrg('expand')}>扩张模拟</button>
            <button className="border text-sm rounded-lg px-3 py-2" onClick={() => loadOrg('depart')}>离开影响</button>
            <button className="border text-sm rounded-lg px-3 py-2" onClick={() => loadOrg('struct')}>结构比较</button>
            <button className="border text-sm rounded-lg px-3 py-2" onClick={() => loadOrg('informal')}>非正式组织</button>
            <button className="border text-sm rounded-lg px-3 py-2" onClick={() => loadOrg('knowledge')}>知识依赖</button>
            <button className="border text-sm rounded-lg px-3 py-2" onClick={() => loadOrg('conflict')}>冲突预测</button>
          </div>
          {orgView?.data && (
            <section className="bg-white rounded-2xl border border-slate-100 p-5 space-y-3">
              {orgView.kind === 'expand' && (
                <>
                  <h3 className="text-sm font-bold">{orgView.data.current_size} → {orgView.data.future_size} 人</h3>
                  <p className="text-sm">跨度 {orgView.data.span} · 导师需求 {orgView.data.mentor_needed} · 培养周期 {orgView.data.train_cycle_weeks} 周</p>
                  <p className="text-xs text-amber-700">瓶颈：{(orgView.data.bottlenecks || []).join('、') || '无'}</p>
                  {(orgView.data.recommendations || []).map((r) => <div key={r} className="text-sm">· {r}</div>)}
                </>
              )}
              {orgView.kind === 'depart' && (
                <>
                  <h3 className="text-sm font-bold">若 {orgView.data.name} 离开 · 组织依赖 {orgView.data.org_dependency}</h3>
                  <p className="text-[11px] text-amber-700">{orgView.data.kind_note}</p>
                  {(orgView.data.impacts || []).map((i, idx) => (
                    <div key={idx} className="text-xs">{i.kind} {i.object} · {i.level} · {i.need}</div>
                  ))}
                  <div className="text-sm mt-2">需要建立的备份</div>
                  {(orgView.data.backups || []).map((b) => <div key={b} className="text-xs">· {b}</div>)}
                </>
              )}
              {orgView.kind === 'struct' && (
                <table className="w-full text-xs">
                  <thead><tr className="text-left text-slate-400"><th>方案</th><th>跨度</th><th>深度</th><th>信息成本</th><th>单点</th></tr></thead>
                  <tbody>
                    {(orgView.data.options || []).map((r) => (
                      <tr key={r.id} className={r.id === orgView.data.recommended ? 'bg-brand-50' : ''}>
                        <td className="py-1">{r.name}</td><td>{r.span}</td><td>{r.depth}</td><td>{r.info_cost}</td><td>{r.single_point}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {orgView.kind === 'informal' && (
                <>
                  {(orgView.data.groups || []).map((g) => (
                    <div key={g.id} className="text-sm"><b>{g.name}</b> · {(g.members || []).map((m) => m.name).join('、')}</div>
                  ))}
                  <p className="text-xs text-slate-500">{orgView.data.note}</p>
                </>
              )}
              {orgView.kind === 'knowledge' && (
                <p className="text-sm">{(orgView.data.chain || []).join(' → ')} · 集中度 {orgView.data.concentration}{orgView.data.single_point ? ' · 知识单点风险' : ''}</p>
              )}
              {orgView.kind === 'conflict' && (
                <>
                  <div className="flex items-center gap-2 text-sm">
                    <AlertTriangle size={14} className="text-amber-600" />
                    {orgView.data.person_a?.name} ↔ {orgView.data.person_b?.name} 冲突风险 {orgView.data.risk}（{orgView.data.kind}）
                  </div>
                  {(orgView.data.reasons || []).map((r) => <div key={r} className="text-xs">· {r}</div>)}
                </>
              )}
              <Judgment judgment={orgView.data.judgment} />
            </section>
          )}
        </div>
      )}

      {tab === 'policy' && policies && (
        <div className="space-y-3">
          {(policies.conflicts || []).length > 0 && (
            <section className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm">
              <h3 className="font-bold mb-2">制度冲突</h3>
              {policies.conflicts.map((c, i) => (
                <div key={i} className="mb-2">
                  <div>{c.left_title} ↔ {c.right_title} · {c.level === 'medium' ? '中' : c.level}</div>
                  <div className="text-xs">{c.reason}</div>
                  <div className="text-xs text-amber-800">建议：{c.suggestion}</div>
                </div>
              ))}
            </section>
          )}
          {(policies.policies || []).map((p) => (
            <section key={p.id} className="bg-white rounded-2xl border border-slate-100 p-4">
              <div className="text-[11px] text-slate-400">{p.category}</div>
              <h3 className="text-sm font-bold">{p.title}</h3>
              <p className="text-xs text-slate-600 mt-1">{p.body}</p>
              {p.effectiveness && (
                <p className="text-xs mt-2">
                  效果：{p.effectiveness.verdict}
                  {p.effectiveness.before != null && ` · 实施前 ${p.effectiveness.before} → 实施后 ${p.effectiveness.after}（${p.effectiveness.change_pct}%）`}
                  {p.effectiveness.note ? ` · ${p.effectiveness.note}` : ''}
                </p>
              )}
            </section>
          ))}
        </div>
      )}

      {tab === 'history' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <section className="bg-white rounded-2xl border border-slate-100 p-5">
            <h3 className="text-sm font-bold mb-2">历史推演</h3>
            {history.map((h) => (
              <div key={h.id} className="text-xs py-1.5 border-b border-slate-50">
                {fmt(h.created_at)} · {h.scenario} · {h.title}
              </div>
            ))}
            {!history.length && <p className="text-xs text-slate-400">还没有推演记录</p>}
          </section>
          <section className="bg-white rounded-2xl border border-slate-100 p-5 space-y-2">
            <h3 className="text-sm font-bold">预测 vs 真实</h3>
            {preds.map((p) => (
              <div key={p.id} className="text-xs border-b border-slate-50 py-2">
                <div>{p.kind} · 预测准备度 {(p.predicted || {}).readiness} · 预计天数 {(p.predicted || {}).days_to_target}</div>
                {p.actual ? <div className="text-emerald-700">实际已登记 · 误差 {p.error_pct}%</div> : (
                  <div className="flex gap-2 mt-1">
                    <input className="border rounded px-2 py-1 w-24" placeholder="实际天数" value={actualDays} onChange={(e) => setActualDays(e.target.value)} />
                    <button className="text-brand-600" onClick={async () => {
                      await api.recordTwinActual(p.id, { days_to_target: Number(actualDays), days: Number(actualDays) })
                      loadHistory()
                    }}>登记真实结果</button>
                  </div>
                )}
              </div>
            ))}
            {!preds.length && <p className="text-xs text-slate-400">做一次成长预测后会出现在这里，便于对照误差、修正模型。</p>}
          </section>
        </div>
      )}
    </div>
  )
}

function Num({ label, value, onChange }) {
  return (
    <label className="text-[11px] text-slate-500">
      {label}
      <input type="number" className="block w-20 border border-slate-200 rounded-lg px-2 py-1 text-sm" value={value} onChange={(e) => onChange(e.target.value)} />
    </label>
  )
}
