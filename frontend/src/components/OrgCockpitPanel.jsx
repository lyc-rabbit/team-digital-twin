import React, { useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle, Building2, Loader2, RefreshCw, Users, FolderKanban,
  ShieldAlert, Sparkles, ArrowRight,
} from 'lucide-react'
import { api } from '../api/client.js'
import { RecordEventButton } from './EventRecorderContext.jsx'

function n(v, d = 0) {
  const x = Number(v)
  return Number.isFinite(x) ? x : d
}

function toneOf(score) {
  const s = n(score)
  if (s >= 80) return { label: '正常', cls: 'text-emerald-700 bg-emerald-50 border-emerald-100', bar: 'bg-emerald-500' }
  if (s >= 60) return { label: '关注', cls: 'text-amber-700 bg-amber-50 border-amber-100', bar: 'bg-amber-500' }
  return { label: '风险', cls: 'text-red-700 bg-red-50 border-red-100', bar: 'bg-red-500' }
}

function priOf(level) {
  if (level === 'high' || level === 'required') return 0
  if (level === 'medium' || level === 'attention') return 1
  return 2
}

export default function OrgCockpitPanel({ members = [], onNavigate, onOpenProject }) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [situation, setSituation] = useState(null)
  const [dash, setDash] = useState(null)
  const [risks, setRisks] = useState(null)
  const [ranking, setRanking] = useState([])
  const [projects, setProjects] = useState([])
  const [facts, setFacts] = useState(null)
  const mountedRef = useRef(true)

  const load = async () => {
    setError(null)
    const [sit, d, r, rank, proj, fact] = await Promise.allSettled([
      api.getSituationToday(),
      api.getDashboard(),
      api.getOigRisk(),
      api.getOigInfluenceRanking(),
      api.listProjects({ sort: 'updated_at' }),
      api.getFactOverview(),
    ])
    if (!mountedRef.current) return
    if (sit.status === 'fulfilled') setSituation(sit.value)
    if (d.status === 'fulfilled') setDash(d.value)
    if (r.status === 'fulfilled') setRisks(r.value)
    if (rank.status === 'fulfilled') setRanking(rank.value?.ranking || [])
    if (proj.status === 'fulfilled') setProjects(proj.value?.projects || [])
    if (fact.status === 'fulfilled') setFacts(fact.value)
    const failed = [sit, d, r].filter((x) => x.status === 'rejected')
    if (failed.length === 3) setError(failed[0].reason?.message || '驾驶舱数据加载失败')
  }

  useEffect(() => {
    mountedRef.current = true
    load().finally(() => mountedRef.current && setLoading(false))
    return () => { mountedRef.current = false }
  }, [])

  const report = situation?.report || null
  const orgHealth = n(dash?.health?.score, n(report?.team_health_score))
  const projectHealth = n(report?.project_score, orgHealth)
  const talent = n(report?.member_score, orgHealth)
  const oigItems = risks?.items || []
  const keyTalentRisk = oigItems.filter((x) => x.type === 'key_person' || x.type === 'single_point').length
  const blocked = (report?.projects || []).filter((p) => p.status === 'risk' || p.blocked || p.health_status === 'risk').length
    || projects.filter((p) => p.health?.status === 'risk').length
  const resourceBottleneck = oigItems.filter((x) => x.type === 'resource_lock').length
  const orgRisks = n(risks?.summary?.high) + n(risks?.summary?.medium)
    + (report?.risks || []).filter((x) => x.status === 'open').length

  const anomalies = useMemo(() => {
    const list = []
    for (const a of report?.attention_items || []) {
      list.push({
        id: `attn-${a.id || a.title}`,
        level: a.priority === 'high' ? 'high' : a.priority === 'medium' ? 'medium' : 'watch',
        title: a.title || a.summary,
        detail: a.reason || a.recommended_action || a.detail,
        go: a.project_id ? { kind: 'project', id: a.project_id } : { kind: 'nav', id: 'cockpit-risks' },
      })
    }
    for (const r of (report?.risks || []).filter((x) => x.status === 'open')) {
      list.push({
        id: `sit-${r.id}`,
        level: r.severity || r.level || 'medium',
        title: r.title,
        detail: r.detail || r.description,
        go: r.project_id ? { kind: 'project', id: r.project_id } : { kind: 'nav', id: 'cockpit-risks' },
      })
    }
    for (const r of oigItems.filter((x) => x.level === 'high' || x.level === 'medium')) {
      list.push({
        id: `oig-${r.id}`,
        level: r.level,
        title: r.title,
        detail: r.detail,
        go: { kind: 'nav', id: r.type === 'resource_lock' ? 'cockpit-resources' : 'cockpit-key-people' },
      })
    }
    for (const p of projects.filter((p) => p.health?.status === 'risk' || p.health?.status === 'attention')) {
      list.push({
        id: `proj-${p.id}`,
        level: p.health?.status === 'risk' ? 'high' : 'medium',
        title: `${p.name} · ${p.health?.label || '需关注'}`,
        detail: p.health?.reason || p.current_stage || '',
        go: { kind: 'project', id: p.id },
      })
    }
    const seen = new Set()
    return list
      .filter((x) => {
        const k = `${x.title}|${x.detail}`
        if (seen.has(k)) return false
        seen.add(k)
        return true
      })
      .sort((a, b) => priOf(a.level) - priOf(b.level))
      .slice(0, 12)
  }, [report, oigItems, projects])

  const kpis = [
    { label: '组织健康度', value: Math.round(orgHealth), go: 'cockpit-stability' },
    { label: '项目健康度', value: Math.round(projectHealth), go: 'cockpit-projects' },
    { label: '人才稳定性', value: Math.round(talent), go: 'cockpit-talent' },
    { label: '关键人才风险', value: keyTalentRisk, count: true, go: 'cockpit-key-people' },
    { label: '项目阻塞', value: blocked, count: true, go: 'work-risks' },
    { label: '资源瓶颈', value: resourceBottleneck, count: true, go: 'cockpit-resources' },
    { label: '组织风险', value: orgRisks, count: true, go: 'cockpit-risks' },
  ]

  const jump = (go) => {
    if (!go) return
    if (go.kind === 'project' && go.id) onOpenProject?.(go.id)
    else if (go.kind === 'nav') onNavigate?.(go.id)
    else if (typeof go === 'string') onNavigate?.(go)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-slate-400 text-sm">
        <Loader2 size={16} className="animate-spin mr-2" />加载组织驾驶舱...
      </div>
    )
  }

  const changes = (report?.llm_json?.key_changes || report?.changes || []).slice(0, 6)
  const keyPeople = ranking.slice(0, 5)

  return (
    <div className="p-6 max-w-6xl mx-auto fade-in space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
            <Building2 size={20} className="text-brand-600" />
            组织驾驶舱
          </h2>
          <p className="text-sm text-slate-500 mt-1">
            异常优先 · 同一套组织事实，给老板看「哪里需要介入」
          </p>
        </div>
        <div className="flex items-center gap-2">
          <RecordEventButton context={{ source: 'org-cockpit' }} />
          <button
            onClick={() => { setLoading(true); load().finally(() => setLoading(false)) }}
            className="flex items-center gap-1.5 text-sm font-medium text-slate-600 bg-white border border-slate-200 hover:bg-slate-50 px-3 py-2 rounded-lg"
          >
            <RefreshCw size={14} /> 刷新
          </button>
        </div>
      </div>

      {error && (
        <div className="text-xs bg-red-50 text-red-700 border border-red-100 rounded-lg px-3 py-2">{error}</div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
        {kpis.map((k) => {
          const tone = k.count
            ? (k.value > 0 ? toneOf(k.value >= 3 ? 40 : 65) : toneOf(90))
            : toneOf(k.value)
          return (
            <button
              key={k.label}
              type="button"
              onClick={() => jump(k.go)}
              className="text-left bg-white rounded-2xl border border-slate-100 p-3 hover:border-brand-200 hover:shadow-sm transition-shadow"
            >
              <div className="text-[11px] text-slate-500">{k.label}</div>
              <div className="text-2xl font-bold text-slate-800 mt-1">{k.value}</div>
              <span className={`inline-flex mt-1.5 text-[10px] px-1.5 py-0.5 rounded-full border ${tone.cls}`}>
                {k.count ? (k.value > 0 ? '需介入' : '正常') : tone.label}
              </span>
            </button>
          )
        })}
      </div>

      <section className="bg-white rounded-2xl border border-slate-100 p-5">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-bold text-slate-800 flex items-center gap-2">
            <AlertTriangle size={16} className="text-amber-500" />
            需要介入
          </h3>
          <span className="text-[11px] text-slate-400">{anomalies.length} 项优先事项</span>
        </div>
        {anomalies.length === 0 ? (
          <p className="text-sm text-slate-500">当前没有需要老板立刻介入的异常。可下钻到项目态势或风险雷达查看细节。</p>
        ) : (
          <div className="space-y-2">
            {anomalies.map((a) => (
              <button
                key={a.id}
                type="button"
                onClick={() => jump(a.go)}
                className="w-full text-left rounded-xl border border-slate-100 hover:border-brand-200 px-3 py-2.5 flex items-start gap-3"
              >
                <span className="mt-0.5">
                  {a.level === 'high' ? '🔴' : a.level === 'medium' ? '🟠' : '🟡'}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium text-slate-800">{a.title}</div>
                  {a.detail && <div className="text-xs text-slate-500 mt-0.5 line-clamp-2">{a.detail}</div>}
                </div>
                <ArrowRight size={14} className="text-slate-300 mt-1 flex-shrink-0" />
              </button>
            ))}
          </div>
        )}
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <section className="bg-white rounded-2xl border border-slate-100 p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-bold text-slate-800 flex items-center gap-2">
              <Sparkles size={16} className="text-brand-600" /> 关键人物
            </h3>
            <button type="button" onClick={() => onNavigate?.('cockpit-key-people')} className="text-[11px] text-brand-600">
              查看影响力
            </button>
          </div>
          {keyPeople.length === 0 ? (
            <p className="text-xs text-slate-400">暂无影响力排名。请先在组织资产中维护人员并重建图谱。</p>
          ) : (
            <div className="space-y-2">
              {keyPeople.map((p) => (
                <div key={p.id} className="flex items-center gap-3 text-sm">
                  <span className="text-slate-400 w-5">{p.rank}</span>
                  <span className="font-medium text-slate-800 flex-1">{p.name}</span>
                  <span className="text-brand-600 font-bold">{p.influence_score}</span>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="bg-white rounded-2xl border border-slate-100 p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-bold text-slate-800 flex items-center gap-2">
              <FolderKanban size={16} className="text-brand-600" /> 重大变化
            </h3>
            <button type="button" onClick={() => onNavigate?.('cockpit-changes')} className="text-[11px] text-brand-600">
              趋势
            </button>
          </div>
          {changes.length === 0 ? (
            <p className="text-xs text-slate-400">暂无重大变化记录。可在团队态势中触发分析。</p>
          ) : (
            <ul className="space-y-2">
              {changes.map((c, i) => (
                <li key={i} className="text-sm text-slate-700">
                  · {typeof c === 'string' ? c : c.title || c.summary || c.text}
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <button
          type="button"
          onClick={() => onNavigate?.('team-situation')}
          className="bg-white rounded-2xl border border-slate-100 p-4 text-left hover:border-brand-200"
        >
          <Users size={16} className="text-brand-600 mb-2" />
          <div className="text-sm font-semibold text-slate-800">下钻团队管理</div>
          <p className="text-[11px] text-slate-500 mt-1">看人：负载、依赖、新人与梯队</p>
        </button>
        <button
          type="button"
          onClick={() => onNavigate?.('work-overview')}
          className="bg-white rounded-2xl border border-slate-100 p-4 text-left hover:border-brand-200"
        >
          <FolderKanban size={16} className="text-brand-600 mb-2" />
          <div className="text-sm font-semibold text-slate-800">下钻项目与工作</div>
          <p className="text-[11px] text-slate-500 mt-1">看事：进度、阻塞、分工</p>
        </button>
        <button
          type="button"
          onClick={() => onNavigate?.('an-risk')}
          className="bg-white rounded-2xl border border-slate-100 p-4 text-left hover:border-brand-200"
        >
          <ShieldAlert size={16} className="text-brand-600 mb-2" />
          <div className="text-sm font-semibold text-slate-800">为什么这样判断</div>
          <p className="text-[11px] text-slate-500 mt-1">
            组织分析 · 事实待确认 {facts?.pending ?? '—'} · 冲突 {facts?.conflicts ?? '—'}
          </p>
        </button>
      </div>
    </div>
  )
}
