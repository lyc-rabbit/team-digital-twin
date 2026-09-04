import React, { useEffect, useState } from 'react'
import { ArrowUpRight, FileText, KeyRound, Loader2, ShieldAlert, Users } from 'lucide-react'
import { api } from '../api/client.js'
import { RecordEventButton } from './EventRecorderContext.jsx'
import RelationshipScoreDetail from './RelationshipScoreDetail.jsx'

const TABS = [
  { id: 'relation', label: '上级关系' },
  { id: 'trust', label: '信任' },
  { id: 'auth', label: '授权' },
  { id: 'report', label: '汇报' },
  { id: 'risk', label: '协同风险' },
]

const SEV = {
  high: 'bg-red-50 text-red-700 border-red-100',
  medium: 'bg-amber-50 text-amber-800 border-amber-100',
  low: 'bg-slate-50 text-slate-600 border-slate-100',
}

function fmtTime(t) {
  if (!t) return ''
  return String(t).replace('T', ' ').slice(0, 16)
}

function JudgmentBlock({ judgment, title = '系统判断' }) {
  if (!judgment) return null
  const evidence = judgment.evidence || []
  return (
    <div className="mt-3 rounded-xl border border-slate-100 bg-slate-50/80 p-3 space-y-2">
      <div className="text-[11px] font-semibold text-slate-500">{title}</div>
      <div>
        <div className="text-[10px] uppercase tracking-wide text-slate-400">结论</div>
        <p className="text-sm font-medium text-slate-800">{judgment.conclusion}</p>
      </div>
      <div>
        <div className="text-[10px] uppercase tracking-wide text-slate-400">原因</div>
        <p className="text-xs text-slate-600 leading-relaxed">{judgment.reason}</p>
      </div>
      <div>
        <div className="text-[10px] uppercase tracking-wide text-slate-400">证据</div>
        {evidence.length === 0 ? (
          <p className="text-xs text-slate-400">暂无对应事件或项目事实。</p>
        ) : evidence.map((e, i) => (
          <div key={`${e.event_id || e.source_id || i}-${i}`} className="text-xs text-slate-600 py-1.5 border-b border-white/70 last:border-0">
            <span className="text-slate-400">{fmtTime(e.time)}</span>
            {e.source && <span className="ml-1.5 text-[10px] px-1.5 py-0.5 rounded bg-white text-slate-500">{e.source}</span>}
            <span className="ml-1.5 font-medium">{e.title}</span>
            {e.text && <div className="text-slate-500 mt-0.5 leading-relaxed">{e.text}</div>}
          </div>
        ))}
      </div>
      <div className="flex items-center justify-between text-[10px] text-slate-400">
        <span>时间 {fmtTime(judgment.time) || '—'}</span>
        <span>来源 {judgment.source === 'llm' ? '模型重组' : '规则 + 事件证据'}</span>
      </div>
    </div>
  )
}

export default function UpwardCollabPanel({ members = [] }) {
  const [personId, setPersonId] = useState(members[0]?.id || '')
  const [managerId, setManagerId] = useState('')
  const [data, setData] = useState(null)
  const [tab, setTab] = useState('relation')
  const [dim, setDim] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [projectId, setProjectId] = useState('')
  const [extraNotes, setExtraNotes] = useState('')
  const [facts, setFacts] = useState(null)
  const [report, setReport] = useState(null)
  const [reportLoading, setReportLoading] = useState(false)

  useEffect(() => {
    if (!personId && members[0]?.id) setPersonId(members[0].id)
  }, [members, personId])

  const load = async (pid, mid) => {
    if (!pid) return
    setLoading(true)
    setError(null)
    try {
      const d = await api.getUpwardArchive(pid, mid || undefined)
      setData(d)
      if (!mid && d.manager_id) setManagerId(d.manager_id)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load(personId, managerId) }, [personId, managerId])

  useEffect(() => {
    setReport(null)
    setFacts(null)
    setExtraNotes('')
    setProjectId('')
    setDim(null)
  }, [personId, managerId])

  useEffect(() => {
    if (tab !== 'report' || !personId) return
    let alive = true
    api.getUpwardFacts(personId, managerId || undefined, projectId || undefined)
      .then((d) => { if (alive) setFacts(d) })
      .catch((e) => { if (alive) setError(e.message) })
    return () => { alive = false }
  }, [tab, personId, managerId, projectId])

  const generate = async () => {
    if (!personId) return
    setReportLoading(true)
    setError(null)
    try {
      const d = await api.generateUpwardReport(personId, {
        manager_id: managerId || undefined,
        project_id: projectId || undefined,
        extra_notes: extraNotes,
      })
      setReport(d)
    } catch (e) {
      setError(e.message)
    } finally {
      setReportLoading(false)
    }
  }

  const riskCount = (data?.risks || []).filter((r) => r.id !== 'none').length
  const managerOptions = data?.managers?.length
    ? data.managers
    : members.filter((m) => m.id !== personId)

  return (
    <div className="p-6 max-w-6xl mx-auto fade-in space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
            <ArrowUpRight size={20} className="text-brand-600" /> 向上协同
          </h2>
          <p className="text-sm text-slate-500 mt-1">
            分析上级如何改变对你的信任与授权，用已有事实起草汇报，并识别协同风险。判断必须落到证据。
          </p>
        </div>
        <RecordEventButton context={{
          source: 'upward',
          person_id: personId,
          related_persons: managerId ? [managerId] : [],
          event_type: 'upward',
          event_tag: 'report',
          created_by: personId,
        }} />
      </div>

      <div className="flex flex-wrap gap-3">
        <select className="border border-slate-200 rounded-lg px-3 py-2 text-sm" value={personId} onChange={(e) => { setPersonId(e.target.value); setDim(null) }}>
          {members.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
        </select>
        <select className="border border-slate-200 rounded-lg px-3 py-2 text-sm" value={managerId} onChange={(e) => setManagerId(e.target.value)}>
          <option value="">自动识别上级</option>
          {managerOptions.map((m) => (
            <option key={m.id} value={m.id}>{m.name}{m.event_count != null ? ` · ${m.event_count} 次` : ''}</option>
          ))}
        </select>
      </div>

      <div className="flex flex-wrap gap-1 bg-slate-100 rounded-xl p-1 w-fit">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => { setTab(t.id); setDim(null) }}
            className={`px-3 py-1.5 rounded-lg text-sm ${tab === t.id ? 'bg-white text-slate-800 shadow-sm font-semibold' : 'text-slate-500 hover:text-slate-700'}`}
          >
            {t.label}
            {t.id === 'risk' && riskCount > 0 && (
              <span className="ml-1.5 text-[10px] px-1.5 py-0.5 rounded-full bg-red-100 text-red-700">{riskCount}</span>
            )}
          </button>
        ))}
      </div>

      {error && <div className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</div>}
      {loading && <div className="text-sm text-slate-400 flex items-center gap-2"><Loader2 size={14} className="animate-spin" />加载中</div>}

      {data && tab === 'relation' && (
        <section className="bg-white rounded-2xl border border-slate-100 p-5 space-y-3">
          <div className="flex items-center gap-2">
            <Users size={16} className="text-brand-600" />
            <h3 className="text-sm font-bold text-slate-800">
              上级关系档案 {data.manager_name ? `· ${data.manager_name}` : ''}
            </h3>
            <span className="text-[11px] text-slate-400">{data.event_count || 0} 条协同事件</span>
          </div>
          {!data.manager_id && (
            <p className="text-xs text-amber-700 bg-amber-50 rounded-lg px-3 py-2">尚未识别到固定上级。请先记录带上级的汇报/授权/反馈事件，或在上方手动选择。</p>
          )}
          {Object.entries(data.groups || {}).map(([label, items]) => (
            <div key={label}>
              <div className="text-[11px] font-semibold text-slate-500 mb-1">{label}</div>
              {(items || []).length === 0 ? (
                <p className="text-xs text-slate-400 mb-2">暂无</p>
              ) : items.slice(0, 6).map((e) => (
                <div key={e.id} className="text-xs text-slate-600 py-1.5 border-b border-slate-50">
                  <span className="text-slate-400">{fmtTime(e.event_time)}</span>
                  <span className="ml-2 font-medium">{e.title}</span>
                  {e.summary && <div className="text-slate-400 mt-0.5 leading-relaxed">{e.summary}</div>}
                  {e.result && <div className="text-slate-500">结果：{e.result}</div>}
                </div>
              ))}
            </div>
          ))}
        </section>
      )}

      {data && tab === 'trust' && !dim && (
        <section className="bg-white rounded-2xl border border-slate-100 p-5">
          <h3 className="text-sm font-bold text-slate-800 mb-1">信任维度</h3>
          <p className="text-[11px] text-slate-400 mb-3">
            专业判断、项目交付、风险处理、自主决策、人员管理。分值由证据计算，点击可追溯到事件。
          </p>
          {!data.manager_id && (
            <p className="text-xs text-slate-400">需要先确定上级，才能计算其对你的信任变化。</p>
          )}
          <div className="space-y-3">
            {(data.dimensions || []).map((d) => (
              <button key={d.id} onClick={() => setDim(d.id)}
                className="w-full text-left rounded-xl border border-slate-100 hover:border-brand-200 hover:bg-brand-50/40 px-3 py-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-slate-700">{d.label}</span>
                  <span className="font-bold text-slate-800">{d.current}
                    <span className={`ml-2 text-[11px] ${d.period_delta > 0 ? 'text-emerald-600' : d.period_delta < 0 ? 'text-red-600' : 'text-slate-400'}`}>
                      {d.period_delta > 0 ? '+' : ''}{d.period_delta}
                    </span>
                  </span>
                </div>
                {d.judgment && (
                  <p className="text-xs text-slate-500 mt-1">{d.judgment.conclusion} — {d.judgment.reason}</p>
                )}
              </button>
            ))}
          </div>
        </section>
      )}

      {data && tab === 'trust' && dim && data.manager_id && (
        <div className="bg-white rounded-2xl border border-slate-100 p-5">
          <RelationshipScoreDetail
            fromId={data.manager_id}
            toId={personId}
            dimension={dim}
            onClose={() => setDim(null)}
          />
        </div>
      )}

      {data && tab === 'auth' && data.authorization && (
        <section className="bg-white rounded-2xl border border-slate-100 p-5 space-y-4">
          <div className="flex items-center gap-2">
            <KeyRound size={16} className="text-brand-600" />
            <h3 className="text-sm font-bold text-slate-800">授权等级</h3>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
            {(data.authorization.levels || []).map((lv) => {
              const active = lv.id === data.authorization.level
              return (
                <div key={lv.id} className={`rounded-xl border px-3 py-2 ${active ? 'border-brand-400 bg-brand-50' : 'border-slate-100 bg-slate-50'}`}>
                  <div className={`text-xs font-bold ${active ? 'text-brand-700' : 'text-slate-400'}`}>{lv.id}</div>
                  <div className={`text-[11px] mt-0.5 ${active ? 'text-slate-800' : 'text-slate-500'}`}>{lv.label}</div>
                </div>
              )
            })}
          </div>
          <p className="text-sm text-slate-600">{data.authorization.meaning}</p>
          {data.authorization.consecutive_good_decisions >= 3 && (
            <p className="text-xs text-emerald-700 bg-emerald-50 rounded-lg px-3 py-2">
              连续 {data.authorization.consecutive_good_decisions} 次项目决策结果良好，自主决策信任有上调依据。
            </p>
          )}
          <div className="text-sm bg-brand-50 text-brand-800 rounded-lg px-3 py-2">
            建议：{data.authorization.suggestion}
          </div>
          <JudgmentBlock judgment={data.authorization.judgment} title="授权判断" />
        </section>
      )}

      {tab === 'report' && (
        <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-4">
          <section className="bg-white rounded-2xl border border-slate-100 p-5 space-y-3">
            <div className="flex items-center gap-2">
              <FileText size={16} className="text-brand-600" />
              <h3 className="text-sm font-bold text-slate-800">生成汇报</h3>
            </div>
            <p className="text-[11px] text-slate-400">不会虚构事实。段落只重组项目、事件、日报和你手动补充的内容。</p>
            <label className="block text-[11px] text-slate-500">项目</label>
            <select className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
              <option value="">全部相关项目</option>
              {(data?.projects || []).map((p) => (
                <option key={p.id} value={p.id}>{p.name}{p.is_owner ? ' · 负责人' : ''}</option>
              ))}
            </select>
            <label className="block text-[11px] text-slate-500">手动补充事实（可选）</label>
            <textarea
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm min-h-[110px]"
              placeholder="只写你确认发生过的事实，例如：本周完成接口联调；需要领导拍板是否上线。"
              value={extraNotes}
              onChange={(e) => setExtraNotes(e.target.value)}
            />
            <button
              onClick={generate}
              disabled={reportLoading}
              className="w-full bg-brand-600 hover:bg-brand-700 disabled:opacity-60 text-white text-sm rounded-lg py-2"
            >
              {reportLoading ? '正在重组事实…' : '生成汇报'}
            </button>
            <p className="text-[11px] text-slate-400">可用事实 {facts?.fact_count ?? 0} 条</p>
          </section>

          <section className="bg-white rounded-2xl border border-slate-100 p-5 space-y-4">
            {!report && (
              <div>
                <h3 className="text-sm font-bold text-slate-800 mb-2">已核验事实</h3>
                {(facts?.facts || []).length === 0 ? (
                  <p className="text-xs text-slate-400">还没有可写入汇报的项目、事件或日报。请先记录事实，或在左侧手动补充。</p>
                ) : (facts.facts || []).slice(0, 16).map((f, i) => (
                  <div key={`${f.source}-${f.source_id || i}`} className="text-xs text-slate-600 py-1.5 border-b border-slate-50">
                    <span className="text-slate-400">{fmtTime(f.time)}</span>
                    <span className="ml-1.5 text-[10px] px-1.5 py-0.5 rounded bg-slate-100">{f.source}</span>
                    <div className="mt-0.5 leading-relaxed">{f.text}</div>
                  </div>
                ))}
              </div>
            )}
            {report && (
              <div className="space-y-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h3 className="text-sm font-bold text-slate-800">汇报草稿 · {report.person_name} → {report.manager_name || '上级'}</h3>
                    <p className="text-[11px] text-slate-400 mt-0.5">{report.note} · {fmtTime(report.generated_at)} · {report.fact_count} 条事实</p>
                  </div>
                  {report.degraded && <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-50 text-amber-700">规则模板</span>}
                </div>
                {(report.sections || []).map((s) => (
                  <div key={s.id}>
                    <div className="text-[11px] font-semibold text-slate-500 mb-1">{s.label}</div>
                    <p className="text-sm text-slate-700 whitespace-pre-wrap leading-relaxed">{s.text}</p>
                    {(s.sources || []).length > 0 && (
                      <div className="mt-1 text-[11px] text-slate-400">
                        来源：{s.sources.slice(0, 4).map((x) => x.source).join(' / ')}
                      </div>
                    )}
                  </div>
                ))}
                <div>
                  <div className="text-[11px] font-semibold text-slate-500 mb-1">引用事实</div>
                  {(report.facts || []).map((f, i) => (
                    <div key={`${f.source}-${f.source_id || i}`} className="text-[11px] text-slate-500 py-1 border-b border-slate-50">
                      {fmtTime(f.time)} · {f.source} · {f.text}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </section>
        </div>
      )}

      {data && tab === 'risk' && (
        <div className="space-y-3">
          <p className="text-xs text-slate-500">
            近 {data.lookback_days || 30} 天窗口。每条风险都给出结论、原因、证据和时间来源，而不是一句“AI 认为有风险”。
          </p>
          {(data.risks || []).map((r) => (
            <section key={r.id} className={`rounded-2xl border p-5 ${SEV[r.severity] || SEV.low}`}>
              <div className="flex items-start gap-2">
                <ShieldAlert size={16} className="mt-0.5" />
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-bold">{r.title}</h3>
                    <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-white/70">{r.severity === 'high' ? '高' : r.severity === 'medium' ? '中' : '低'}</span>
                  </div>
                  <p className="text-sm mt-2">建议：{r.suggestion}</p>
                  <JudgmentBlock judgment={r.judgment} title="风险判断" />
                </div>
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  )
}
