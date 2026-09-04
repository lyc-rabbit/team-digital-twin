import React, { useEffect, useMemo, useRef, useState } from 'react'
import {
  Radar, RefreshCw, Loader2, X, AlertTriangle, HelpCircle, Users,
} from 'lucide-react'
import { api } from '../api/client.js'
import { beijingToday } from '../utils/beijingTime.js'
import { RecordEventButton } from './EventRecorderContext.jsx'

const TABS = [
  { id: 'today', label: '今日总览' },
  { id: 'members', label: '人员动向' },
  { id: 'projects', label: '项目态势' },
  { id: 'risks', label: '团队风险' },
  { id: 'trends', label: '趋势变化' },
  { id: 'config', label: '配置' },
]

const PIPELINE_STEPS = ['数据采集', '数据校验', '趋势计算', 'AI分析', '报告生成']

const CONTEXT_TYPES = [
  { id: '今日特殊事项', hint: '今天有什么系统不知道但值得记录的事情？' },
  { id: '项目变化', hint: '项目是否发生计划外变化？' },
  { id: '人员变化', hint: '是否有人承担了临时职责？' },
  { id: '风险', hint: '是否存在尚未进入系统的风险？' },
  { id: '管理层信息', hint: '是否有重要会议 / 领导安排？' },
]

const STATUS_UI = {
  normal: { label: '正常', cls: 'bg-emerald-50 text-emerald-700 border-emerald-100' },
  attention: { label: '关注', cls: 'bg-amber-50 text-amber-700 border-amber-100' },
  risk: { label: '风险', cls: 'bg-red-50 text-red-700 border-red-100' },
}

const SEV_UI = {
  high: { icon: '🔴', label: '高风险', cls: 'border-red-200 bg-red-50' },
  medium: { icon: '🟠', label: '中风险', cls: 'border-orange-200 bg-orange-50' },
  attention: { icon: '🟡', label: '关注', cls: 'border-amber-200 bg-amber-50' },
  info: { icon: '🔵', label: '信息', cls: 'border-sky-200 bg-sky-50' },
}

const RISK_CAT = {
  PROJECT: '项目风险',
  PERSON: '人员风险',
  RESOURCE: '资源风险',
  COLLAB: '协作风险',
  PROGRESS: '进度风险',
  STRUCTURE: '结构风险',
}

const ATTN_UI = {
  high: { icon: '🔴', label: '高优先级', cls: 'border-red-200 bg-red-50' },
  medium: { icon: '🟠', label: '中优先级', cls: 'border-orange-200 bg-orange-50' },
  watch: { icon: '🟡', label: '观察', cls: 'border-amber-200 bg-amber-50' },
  attention: { icon: '🟡', label: '观察', cls: 'border-amber-200 bg-amber-50' },
}

const RISK_STATUS = {
  open: '待处理',
  confirmed: '已确认',
  ignored: '已忽略',
  resolved: '已解决',
}

function todayStr() {
  return beijingToday()
}

function statusOf(score) {
  const s = Number(score || 0)
  if (s >= 80) return 'normal'
  if (s >= 60) return 'attention'
  return 'risk'
}

function pct(v) {
  const n = Number(v || 0)
  return `${n.toFixed(n % 1 ? 1 : 0)}%`
}

function starsOf(change) {
  if (change?.stars) return change.stars
  const score = Math.abs(Number(change?.change_score || (change?.confidence || 0) * 40))
  const n = Math.max(1, Math.min(5, Math.round(score / 8)))
  return '★'.repeat(n) + '☆'.repeat(5 - n)
}

function stepIndex(current) {
  const text = current || ''
  if (text.includes('完成')) return PIPELINE_STEPS.length
  const map = {
    数据采集: 0, 数据校验: 1, 趋势计算: 2, 异常检测: 2, AI分析: 3, 报告生成: 4,
  }
  for (const [k, i] of Object.entries(map)) {
    if (text.includes(k)) return i
  }
  return 0
}

function Chip({ code }) {
  const ui = STATUS_UI[code] || STATUS_UI.attention
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${ui.cls}`}>
      {ui.label}
    </span>
  )
}

function Bar({ value, color = 'bg-brand-500' }) {
  const w = Math.max(0, Math.min(100, Number(value || 0)))
  return (
    <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
      <div className={`h-full ${color}`} style={{ width: `${w}%` }} />
    </div>
  )
}

export default function TeamSituationPanel({ members = [], onOpenProject }) {
  const [tab, setTab] = useState('today')
  const [payload, setPayload] = useState(null)
  const [report, setReport] = useState(null)
  const [job, setJob] = useState({ status: 'idle', progress: 0, current_step: '' })
  const [history, setHistory] = useState([])
  const [trends, setTrends] = useState(null)
  const [config, setConfig] = useState(null)
  const [contexts, setContexts] = useState([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [toast, setToast] = useState(null)
  const [error, setError] = useState(null)
  const [contextOpen, setContextOpen] = useState(false)
  const [teamScopeOpen, setTeamScopeOpen] = useState(false)
  const [evidence, setEvidence] = useState(null)
  const [selectedMember, setSelectedMember] = useState(null)
  const [selectedProject, setSelectedProject] = useState(null)
  const [viewingDate, setViewingDate] = useState(null)
  const mountedRef = useRef(true)

  const nameOf = (id) => members.find((m) => m.id === id)?.name || id

  const loadToday = async (forceLatest = false) => {
    const data = await api.getSituationToday()
    if (!mountedRef.current) return data
    setPayload(data)
    setJob(data.job || { status: 'idle' })
    if (forceLatest || !viewingDate) setReport(data.report)
    return data
  }

  const loadExtras = async () => {
    const [hist, cfg, ctx] = await Promise.all([
      api.getSituationReports(),
      api.getSituationConfig(),
      api.listSituationContext(todayStr()),
    ])
    if (!mountedRef.current) return
    setHistory(hist.reports || [])
    setConfig(cfg)
    setContexts(ctx.items || [])
  }

  const attachWatch = async () => {
    setBusy(true)
    const unsub = api.onSituationProgress((st) => {
      if (mountedRef.current) setJob(st)
    })
    try {
      const final = await api.watchSituationAnalyze()
      if (!mountedRef.current) return
      setJob(final)
      if (final.status === 'success') {
        setToast('今日分析完成')
        setViewingDate(null)
        await loadToday(true)
        await loadExtras()
      } else if (final.status === 'failed') {
        setToast(final.error_message || final.message || '分析失败')
      }
    } catch (err) {
      if (mountedRef.current) setToast(err.message || '分析任务异常')
    } finally {
      unsub()
      if (mountedRef.current) setBusy(false)
    }
  }

  useEffect(() => {
    mountedRef.current = true
    ;(async () => {
      try {
        const data = await loadToday()
        await loadExtras()
        const st = data?.job || await api.getSituationStatus()
        if (!mountedRef.current) return
        setJob(st)
        if (st.status === 'running' || api.getSituationPromise()) {
          attachWatch()
        }
      } catch (err) {
        if (mountedRef.current) setError(err.message || '加载失败')
      } finally {
        if (mountedRef.current) setLoading(false)
      }
    })()
    return () => { mountedRef.current = false }
  }, [])

  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => mountedRef.current && setToast(null), 4500)
    return () => clearTimeout(t)
  }, [toast])

  useEffect(() => {
    if (tab !== 'trends') return
    api.getSituationTrends('7d').then((d) => mountedRef.current && setTrends(d)).catch(() => {})
  }, [tab, report?.id])

  const handleAnalyze = async () => {
    if (busy || job.status === 'running') return
    setBusy(true)
    setError(null)
    const unsub = api.onSituationProgress((st) => {
      if (mountedRef.current) setJob(st)
    })
    try {
      const final = await api.analyzeSituation(`manual-${todayStr()}`)
      if (!mountedRef.current) return
      setJob(final)
      if (final.status === 'success') {
        setToast('今日分析完成')
        setViewingDate(null)
        await loadToday(true)
        await loadExtras()
      } else if (final.status === 'failed') {
        setToast(final.error_message || final.message || '分析失败')
      }
    } catch (err) {
      if (mountedRef.current) setToast(err.message || '触发失败')
    } finally {
      unsub()
      if (mountedRef.current) setBusy(false)
    }
  }

  const openHistory = async (date) => {
    setViewingDate(date)
    const data = await api.getSituationReports({ date })
    const item = (data.reports || [])[0]
    if (item) setReport(item)
  }

  const patchRisk = async (id, status) => {
    await api.patchSituationRisk(id, status)
    await loadToday()
    if (viewingDate) await openHistory(viewingDate)
  }

  const patchQuestion = async (id, status) => {
    await api.patchSituationQuestion(id, status)
    await loadToday()
    if (viewingDate) await openHistory(viewingDate)
    setToast(status === 'long_term' ? '已记为长期变化' : status === 'temporary' ? '已记为临时变化' : '已忽略')
  }

  const saveConfig = async (next) => {
    const saved = await api.updateSituationConfig(next)
    setConfig(saved)
    setToast('配置已保存')
  }

  const saveTeamMembers = async (ids) => {
    if (!ids.length) {
      setToast('请至少勾选一名团队成员')
      return
    }
    const saved = await api.updateSituationConfig({ included_member_ids: ids })
    setConfig(saved)
    setTeamScopeOpen(false)
    setToast('已更新计入人员，正在重新分析…')
    await handleAnalyze()
  }

  const keyChanges = useMemo(() => {
    const llm = report?.llm_json?.key_changes
    if (llm?.length) return llm.slice(0, 5)
    return (report?.changes || []).slice(0, 5)
  }, [report])

  if (loading) {
    return <div className="flex items-center justify-center h-full text-slate-400 text-sm">加载团队态势...</div>
  }

  const running = job.status === 'running' || busy
  const cfg = config || payload?.config || {}
  const hour = String(cfg.scheduler_hour ?? 12).padStart(2, '0')
  const minute = String(cfg.scheduler_minute ?? 0).padStart(2, '0')
  const reportDate = report?.report_date || todayStr()
  const isToday = report?.report_date === todayStr()
  const created = report?.created_at ? String(report.created_at).slice(11, 19) : ''
  const includedIds = Array.isArray(cfg.included_member_ids) && cfg.included_member_ids.length
    ? cfg.included_member_ids
    : members.map((m) => m.id)
  const includedMembers = members.filter((m) => includedIds.includes(m.id))

  return (
    <div className="p-6 max-w-6xl mx-auto fade-in space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
            <Radar size={20} className="text-brand-600" />
            团队态势
          </h2>
          <p className="text-sm text-slate-500 mt-1">
            {reportDate}{created ? ` · ${created.slice(0, 5)}更新` : ` · ${hour}:${minute}更新`}
            <span className="mx-2 text-slate-300">·</span>
            观察变化并做判断，项目管理在项目中心
            {viewingDate && viewingDate !== todayStr() && (
              <span className="ml-2 text-amber-600">正在查看历史 {viewingDate}</span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <RecordEventButton context={{ source: 'team-situation' }} />
          <button
            onClick={() => setContextOpen(true)}
            className="px-3 py-2 text-sm rounded-lg border border-slate-200 bg-white hover:bg-slate-50"
          >
            数据补充
          </button>
          <button
            onClick={handleAnalyze}
            disabled={running}
            className="px-3 py-2 text-sm rounded-lg bg-brand-600 text-white hover:bg-brand-700 disabled:opacity-50 flex items-center gap-1.5"
          >
            {running ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            立即分析
          </button>
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl px-4 py-3 flex flex-col gap-2">
        {running ? (
          <>
            <div className="flex items-center gap-2 text-sm text-brand-700">
              <Loader2 size={14} className="animate-spin" />
              分析中... {job.current_step || job.message || ''}
              <span className="text-slate-400">{job.progress || 0}%</span>
            </div>
            <div className="flex flex-wrap gap-2 text-xs">
              {PIPELINE_STEPS.map((s, i) => {
                const cur = stepIndex(job.current_step)
                const on = i <= cur
                return (
                  <span key={s} className={on ? 'text-brand-700 font-medium' : 'text-slate-400'}>
                    {i > 0 && <span className="text-slate-300 mr-2">→</span>}
                    {s}
                  </span>
                )
              })}
            </div>
          </>
        ) : job.status === 'failed' ? (
          <div className="text-sm text-red-600 flex items-center gap-2">
            <AlertTriangle size={14} />
            分析失败：{job.error_message || job.message}
          </div>
        ) : report ? (
          <div className="text-sm text-emerald-700 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-500" />
            {isToday ? '今日分析完成' : `${reportDate} 分析完成`}
            {created && <span className="text-slate-400">最后更新时间：{created}</span>}
          </div>
        ) : (
          <div className="text-sm text-slate-500">尚未生成态势报告，请点击「立即分析」或等待每日定时任务。</div>
        )}
      </div>

      {error && <div className="text-sm text-red-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2">{error}</div>}
      {toast && <div className="text-sm text-brand-700 bg-brand-50 border border-brand-100 rounded-lg px-3 py-2">{toast}</div>}

      <div className="flex gap-1 bg-slate-200/70 p-1 rounded-lg w-fit flex-wrap">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-3 py-1.5 text-sm rounded-md ${tab === t.id ? 'bg-white shadow text-slate-800' : 'text-slate-500 hover:text-slate-700'}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'today' && (
        <TodayTab
          report={report}
          history={history}
          keyChanges={keyChanges}
          onHistory={openHistory}
          onClearHistory={() => { setViewingDate(null); setReport(payload?.report || null) }}
          viewingDate={viewingDate}
          onEvidence={setEvidence}
          onMember={(id) => { setSelectedMember(id); setTab('members') }}
          onProject={(id, source) => {
            if (onOpenProject && id && source === 'project_center') onOpenProject(id)
            else { setSelectedProject(id); setTab('projects') }
          }}
          onQuestion={patchQuestion}
          onPatchRisk={patchRisk}
          nameOf={nameOf}
          includedMembers={includedMembers}
          onEditTeam={() => setTeamScopeOpen(true)}
        />
      )}
      {tab === 'members' && (
        <MembersTab
          report={report}
          members={members}
          selected={selectedMember}
          onSelect={setSelectedMember}
          onEvidence={setEvidence}
          onOpenProject={onOpenProject}
        />
      )}
      {tab === 'projects' && (
        <ProjectsTab
          report={report}
          selected={selectedProject}
          onSelect={setSelectedProject}
          nameOf={nameOf}
          onOpenProject={onOpenProject}
        />
      )}
      {tab === 'risks' && (
        <RisksTab report={report} onPatch={patchRisk} onEvidence={setEvidence} onOpenProject={onOpenProject} onMember={(id) => { setSelectedMember(id); setTab('members') }} />
      )}
      {tab === 'trends' && (
        <TrendsTab trends={trends} onRange={async (r) => setTrends(await api.getSituationTrends(r))} />
      )}
      {tab === 'config' && config && (
        <ConfigTab
          config={config}
          members={members}
          includedIds={includedIds}
          onSave={saveConfig}
          onSaveMembers={saveTeamMembers}
        />
      )}

      {contextOpen && (
        <ContextModal
          members={members}
          contexts={contexts}
          onClose={() => setContextOpen(false)}
          onSaved={async () => {
            await loadExtras()
            setToast('已记入 Team Context（source=manual）')
            setContextOpen(false)
          }}
        />
      )}

      {teamScopeOpen && (
        <TeamScopeModal
          members={members}
          selectedIds={includedIds}
          onClose={() => setTeamScopeOpen(false)}
          onSave={saveTeamMembers}
          saving={running}
        />
      )}

      {evidence && (
        <EvidenceDrawer item={evidence} onClose={() => setEvidence(null)} />
      )}
    </div>
  )
}

function TodayTab({
  report, history, keyChanges, onHistory, onClearHistory, viewingDate,
  onEvidence, onMember, onProject, onQuestion, onPatchRisk, nameOf,
  includedMembers = [], onEditTeam,
}) {
  if (!report) {
    return (
      <div className="space-y-4">
        <div className="text-sm text-slate-500 bg-white border border-dashed border-slate-200 rounded-xl p-8 text-center">
          暂无报告。团队态势只读取日报、项目中心、角色卡和关系网，不会在这里创建或修改项目。
        </div>
        <div className="bg-white border border-slate-200 rounded-xl p-4 flex items-start justify-between gap-3">
          <div>
            <div className="text-sm font-medium text-slate-800">计入团队 {includedMembers.length} 人</div>
            <p className="text-xs text-slate-500 mt-1">分析前可先去掉非本团队人员，避免他们拉低健康度。</p>
          </div>
          <button type="button" onClick={onEditTeam} className="px-2.5 py-1.5 text-xs rounded-lg border border-slate-200 hover:bg-slate-50 flex items-center gap-1">
            <Users size={12} /> 修改团队人员
          </button>
        </div>
      </div>
    )
  }
  const llm = report.llm_json || {}
  const reasons = report.snapshot_meta?.health_reasons || []
  const questions = (report.questions || []).filter((q) => q.status === 'open')
  const attn = (report.attention_items || []).slice()
  const order = { high: 0, medium: 1, watch: 2, attention: 3 }
  attn.sort((a, b) => (order[a.priority] ?? 9) - (order[b.priority] ?? 9))
  const projectOf = (id) => (report.projects || []).find((p) => p.project_id === id)
  const openProject = (id) => {
    const p = projectOf(id)
    onProject(id, p?.source)
  }
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <HealthCard title="团队状态" score={report.team_health_score} status={report.team_status} />
        <HealthCard title="人员状态" score={report.member_score} status={report.member_status || statusOf(report.member_score)} />
        <HealthCard title="项目状态" score={report.project_score} status={report.project_status_label || statusOf(report.project_score)} />
      </div>

      <div className="bg-white border border-slate-200 rounded-xl p-4">
        <div className="flex items-center justify-between mb-2">
          <h3 className="font-semibold text-slate-800">Team Health Score</h3>
          <span className="text-2xl font-bold text-slate-800">{Number(report.team_health_score || 0).toFixed(1)}</span>
        </div>
        <Bar value={report.team_health_score} />
        <p className="text-xs text-slate-500 mt-2">
          项目 {report.project_score} ×40% + 人员 {report.member_score} ×25% + 任务 {report.task_score} ×20% + 协作 {report.collaboration_score} ×15%
          （权重以配置为准）
        </p>
        <div className="mt-3 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-xs text-slate-500 mb-1">计入团队 {includedMembers.length} 人（未勾选的人不参与健康度）</div>
            <div className="flex flex-wrap gap-1">
              {includedMembers.length === 0 && <span className="text-xs text-amber-600">尚未勾选</span>}
              {includedMembers.map((m) => (
                <span key={m.id} className="px-2 py-0.5 text-xs rounded-full bg-slate-100 text-slate-600">{m.name}</span>
              ))}
            </div>
          </div>
          <button
            type="button"
            onClick={onEditTeam}
            className="flex-shrink-0 px-2.5 py-1.5 text-xs rounded-lg border border-slate-200 hover:bg-slate-50 flex items-center gap-1"
          >
            <Users size={12} />
            修改团队人员
          </button>
        </div>
        {reasons.length > 0 && (
          <ul className="mt-2 text-sm text-slate-600 list-disc pl-5 space-y-0.5">
            {reasons.map((r) => <li key={r}>{r}</li>)}
          </ul>
        )}
        {llm.summary && (
          <div className="mt-3 text-sm text-slate-700 bg-slate-50 rounded-lg p-3">
            {llm.summary}
            {llm.degraded && <span className="ml-2 text-xs text-amber-600">（规则引擎降级，未调用 LLM）</span>}
          </div>
        )}
      </div>

      <section>
        <h3 className="font-semibold text-slate-800 mb-3">🔥 今日重要变化</h3>
        <p className="text-xs text-slate-400 mb-3">最多展示 5 条。项目阶段变化来自项目中心，不是日报猜测。</p>
        <div className="space-y-3">
          {keyChanges.length === 0 && <p className="text-sm text-slate-400">未检测到显著变化。</p>}
          {keyChanges.map((c, i) => (
            <div key={c.object_id || i} className="bg-white border border-slate-200 rounded-xl p-4">
              <div className="flex items-center gap-2 text-xs mb-1">
                <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-600">{c.kind || c.change_label || '变化'}</span>
                <Chip code={c.severity === 'high' || c.severity === 'medium' ? (c.severity === 'high' ? 'risk' : 'attention') : (c.severity === 'info' ? 'normal' : c.severity || 'attention')} />
              </div>
              <div className="font-medium text-slate-800">{c.title}</div>
              <p className="text-sm text-slate-600 mt-1">{c.fact || c.description}</p>
              {c.inference && (
                <p className="text-xs text-slate-500 mt-1"><span className="font-medium text-slate-600">推断：</span>{c.inference}</p>
              )}
              {c.suggestion && (
                <p className="text-xs text-slate-500"><span className="font-medium text-slate-600">建议：</span>{c.suggestion}</p>
              )}
              <div className="flex items-center gap-4 mt-2 text-xs text-slate-500">
                <span>变化程度：{starsOf(c)}</span>
                <span>置信度：{Math.round(Number(c.confidence || 0) * 100)}%</span>
                <button className="text-brand-600 hover:underline" onClick={() => onEvidence(c)}>分析依据</button>
                {c.object_id && (c.object_type === 'project' || (c.kind || c.change_label || '').includes('项目')) ? (
                  <button className="text-brand-600 hover:underline" onClick={() => openProject(c.object_id)}>查看项目</button>
                ) : c.object_id ? (
                  <button className="text-brand-600 hover:underline" onClick={() => onMember(c.object_id)}>查看成员</button>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      </section>

      {questions.length > 0 && (
        <section className="bg-amber-50 border border-amber-100 rounded-xl p-4">
          <h3 className="font-semibold text-amber-900 flex items-center gap-1.5 mb-3">
            <HelpCircle size={16} /> 需要确认
          </h3>
          <p className="text-xs text-amber-800 mb-3">数据不足时系统不会强行推断长期趋势。</p>
          <div className="space-y-3">
            {questions.map((q) => (
              <div key={q.id} className="bg-white rounded-lg p-3 border border-amber-100">
                <p className="text-sm text-slate-700">{q.question}</p>
                {q.member_id && <p className="text-xs text-slate-400 mt-1">{nameOf(q.member_id)}</p>}
                <div className="flex flex-wrap gap-2 mt-2">
                  <button onClick={() => onQuestion(q.id, 'long_term')} className="px-2 py-1 text-xs rounded bg-brand-600 text-white">确认长期变化</button>
                  <button onClick={() => onQuestion(q.id, 'temporary')} className="px-2 py-1 text-xs rounded border border-slate-200">仅记录为临时变化</button>
                  <button onClick={() => onQuestion(q.id, 'ignored')} className="px-2 py-1 text-xs rounded text-slate-500">忽略</button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {(llm.recommendations || []).length > 0 && (
        <section className="bg-white border border-slate-200 rounded-xl p-4">
          <h3 className="font-semibold text-slate-800 mb-2">建议</h3>
          <ul className="text-sm text-slate-600 space-y-1 list-disc pl-5">
            {llm.recommendations.map((r, i) => <li key={i}>{r.text || r}</li>)}
          </ul>
        </section>
      )}

      <section>
        <h3 className="font-semibold text-slate-800 mb-3">🎯 需要你关注</h3>
        <p className="text-xs text-slate-400 mb-3">给管理者的行动建议，不是项目清单。</p>
        <div className="space-y-3">
          {attn.length === 0 && <p className="text-sm text-slate-400">当前没有需要立即处理的事项。</p>}
          {attn.map((a) => {
            const ui = ATTN_UI[a.priority] || ATTN_UI.watch
            const pid = a.project_id
            const mid = a.member_id
            return (
              <div key={a.id || a.risk_id} className={`border rounded-xl p-4 ${ui.cls}`}>
                <div className="text-xs mb-1">{ui.icon} {ui.label}{a.category ? ` · ${RISK_CAT[a.category] || a.category}` : ''}</div>
                <div className="font-medium text-slate-800">{a.title}</div>
                <p className="text-sm text-slate-600 mt-1">{a.description}</p>
                <div className="flex flex-wrap gap-2 mt-3">
                  {pid && <button className="px-2 py-1 text-xs rounded bg-white border" onClick={() => openProject(pid)}>查看项目</button>}
                  {mid && <button className="px-2 py-1 text-xs rounded bg-white border" onClick={() => onMember(mid)}>查看成员</button>}
                  <button className="px-2 py-1 text-xs rounded bg-white border text-slate-500" onClick={() => onPatchRisk(a.risk_id || a.id, 'ignored')}>忽略</button>
                </div>
              </div>
            )
          })}
        </div>
      </section>

      {history.length > 0 && (
        <section>
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-semibold text-slate-800">历史报告</h3>
            {viewingDate && (
              <button className="text-xs text-brand-600" onClick={onClearHistory}>回到最新</button>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            {history.slice(0, 14).map((h) => (
              <button
                key={h.id}
                onClick={() => onHistory(h.report_date)}
                className={`px-2.5 py-1 text-xs rounded-lg border ${viewingDate === h.report_date ? 'border-brand-400 bg-brand-50 text-brand-700' : 'border-slate-200 bg-white text-slate-600'}`}
              >
                {h.report_date} · {Number(h.team_health_score || 0).toFixed(0)}
              </button>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}

function HealthCard({ title, score, status }) {
  const ui = STATUS_UI[status] || STATUS_UI.attention
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4">
      <div className="text-xs text-slate-500">{title}</div>
      <div className="mt-2 flex items-end justify-between">
        <span className={`text-lg font-bold ${ui.cls.split(' ')[1]}`}>{ui.label}</span>
        <span className="text-sm text-slate-400">{Number(score || 0).toFixed(1)}</span>
      </div>
    </div>
  )
}

function MembersTab({ report, members, selected, onSelect, onEvidence, onOpenProject }) {
  const rows = report?.members || []
  if (!report) return <Empty />
  const current = rows.find((m) => m.member_id === selected) || rows[0]
  return (
    <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
      <div className="lg:col-span-2 space-y-2">
        {rows.map((m) => {
          const name = m.name || members.find((x) => x.id === m.member_id)?.name || m.member_id
          const active = current?.member_id === m.member_id
          return (
            <button
              key={m.member_id}
              onClick={() => onSelect(m.member_id)}
              className={`w-full text-left bg-white border rounded-xl p-3 ${active ? 'border-brand-400 ring-1 ring-brand-100' : 'border-slate-200'}`}
            >
              <div className="flex items-center justify-between">
                <span className="font-medium text-slate-800">{name}</span>
                <Chip code={m.risk_level === 'risk' ? 'risk' : m.risk_level === 'attention' ? 'attention' : 'normal'} />
              </div>
              <div className="text-xs text-slate-500 mt-1">主要工作 {m.main_work || '—'}</div>
              <div className="flex items-center gap-3 mt-2 text-xs text-slate-500">
                <span>项目 {m.project_count || 0}</span>
                <span>负载 {m.workload_score || 0}% {m.workload_band ? `· ${m.workload_band}` : ''}</span>
              </div>
              <Bar value={m.workload_score} color={(m.workload_score || 0) >= 85 ? 'bg-red-500' : (m.workload_score || 0) >= 70 ? 'bg-amber-500' : 'bg-emerald-500'} />
            </button>
          )
        })}
        {rows.length === 0 && <p className="text-sm text-slate-400">无成员数据</p>}
      </div>
      <div className="lg:col-span-3 bg-white border border-slate-200 rounded-xl p-4">
        {current ? (
          <MemberDetail m={current} members={members} onEvidence={onEvidence} onOpenProject={onOpenProject} />
        ) : <p className="text-sm text-slate-400">选择一名成员</p>}
      </div>
    </div>
  )
}

function MemberDetail({ m, members, onEvidence, onOpenProject }) {
  const name = m.name || members.find((x) => x.id === m.member_id)?.name || m.member_id
  const d7 = m.work_focus?.d7 || {}
  const d30 = m.work_focus?.d30 || {}
  const delta = m.focus_change || {}
  const keys = Object.keys({ ...d7, ...d30 })
  const topDelta = Object.entries(delta).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))[0]
  return (
    <div>
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-lg font-bold text-slate-800">{name}</h3>
          <p className="text-sm text-slate-500">{m.role || ''}</p>
        </div>
        <Chip code={m.risk_level === 'risk' ? 'risk' : m.risk_level === 'attention' ? 'attention' : 'normal'} />
      </div>
      <dl className="grid grid-cols-2 gap-3 mt-4 text-sm">
        <div><dt className="text-xs text-slate-400">主要工作</dt><dd>{m.main_work || '—'}</dd></div>
        <div><dt className="text-xs text-slate-400">参与项目</dt><dd>{m.project_count || 0}　核心 {m.core_project_count || 0}</dd></div>
        <div><dt className="text-xs text-slate-400">近期变化</dt><dd>{topDelta ? `${topDelta[0]} ${topDelta[1] > 0 ? '↑' : '↓'}` : '—'}</dd></div>
        <div><dt className="text-xs text-slate-400">工作负载</dt><dd>{m.workload_score}% · {m.workload_band || ''}</dd></div>
        <div><dt className="text-xs text-slate-400">角色变化</dt><dd>{m.role_change || '—'}</dd></div>
        <div><dt className="text-xs text-slate-400">置信度</dt><dd>{Math.round(Number(m.confidence || 0) * 100)}%</dd></div>
      </dl>
      {(m.pc_roles || []).length > 0 && (
        <div className="mt-4">
          <h4 className="text-sm font-semibold mb-2">项目职责（项目中心）</h4>
          <div className="space-y-1 text-sm text-slate-600">
            {m.pc_roles.map((r) => (
              <div key={r.project_id} className="flex justify-between gap-2">
                <span>{r.project_name} · {r.role} · {r.participation_level}</span>
                {onOpenProject && r.project_id && (
                  <button className="text-xs text-brand-600" onClick={() => onOpenProject(r.project_id)}>查看项目</button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
      <div className="mt-3 text-xs text-slate-500 space-y-0.5">
        {m.projects_added?.length > 0 && <div>新增项目：{m.projects_added.join('、')}</div>}
        {m.projects_exited?.length > 0 && <div>退出项目：{m.projects_exited.join('、')}</div>}
        {m.owned_projects?.length > 0 && <div>负责项目：{m.owned_projects.join('、')}</div>}
      </div>
      {(m.collab_signals || []).length > 0 && (
        <p className="text-xs text-slate-500 mt-2">协作信号：{(m.collab_signals || []).slice(0, 3).map((c) => c.pair).join('、')}</p>
      )}
      {(m.role_cards || []).length > 0 && (
        <p className="text-xs text-slate-500 mt-1">角色卡：{(m.role_cards || []).map((c) => `${c.role_name} ${Math.round(c.match_score || 0)}`).join('、')}</p>
      )}
      {m.summary && <p className="text-sm text-slate-600 mt-3 bg-slate-50 rounded-lg p-3">{m.summary}</p>}
      <h4 className="text-sm font-semibold mt-5 mb-2">工作重心（7日 vs 30日）</h4>
      <div className="space-y-2">
        {keys.map((k) => (
          <div key={k} className="text-xs">
            <div className="flex justify-between text-slate-600 mb-0.5">
              <span>{k}</span>
              <span>7日 {pct(d7[k])}　30日 {pct(d30[k])}　{delta[k] ? `${delta[k] > 0 ? '+' : ''}${delta[k]}%` : ''}</span>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Bar value={d7[k]} />
              <Bar value={d30[k]} color="bg-slate-400" />
            </div>
          </div>
        ))}
      </div>
      <button
        className="mt-4 text-xs text-brand-600 hover:underline"
        onClick={() => onEvidence({
          title: `${name} 工作重心依据`,
          confidence: m.confidence,
          evidence: [
            `近7天日报 ${m.report_days_7 || 0} 条`,
            `近30天日报 ${m.report_days_30 || 0} 条`,
            ...Object.entries(delta).filter(([, v]) => Math.abs(v) >= 5).map(([k, v]) => `${k} ${v > 0 ? '+' : ''}${v}%`),
            '负载未使用日报字数，由出勤天数 × 并发项目 × 任务难度构成',
          ],
          fact: `近7天主项目：${(m.projects || []).join('、') || '—'}`,
        })}
      >
        分析依据
      </button>
    </div>
  )
}

function ProjectsTab({ report, selected, onSelect, nameOf, onOpenProject }) {
  const rows = (report?.projects || []).filter((p) => p.source === 'project_center' || (report.projects || []).every((x) => x.source !== 'project_center'))
  if (!report) return <Empty />
  if ((report.projects || []).length === 0) {
    return (
      <div className="text-sm text-slate-500 bg-white border border-dashed rounded-xl p-8 text-center">
        项目中心暂无登记项目。团队态势只观察变化，不在这里创建或修改项目。
      </div>
    )
  }
  const statusChip = (p) => {
    const h = p.health?.status || p.risk_level
    if (h === 'risk' || h === 'high') return 'risk'
    if (h === 'attention' || h === 'medium' || h === 'insufficient') return 'attention'
    return 'normal'
  }
  return (
    <div className="space-y-3">
      <p className="text-xs text-slate-400">这里看「项目发生了什么」，不是项目管理。事实在项目中心。</p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {rows.map((p) => {
          const active = selected === p.project_id
          const stageLine = p.previous_stage && p.previous_stage !== p.current_stage
            ? `${p.previous_stage} → ${p.current_stage || '—'}`
            : (p.current_stage || '阶段未知')
          const riskN = (p.open_risks || []).length
          return (
            <div key={p.project_id} className={`bg-white border rounded-xl p-4 ${active ? 'border-brand-400' : 'border-slate-200'}`}>
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h3 className="font-semibold text-slate-800">{p.project_name}</h3>
                  <p className="text-xs text-slate-500 mt-1">当前阶段　{stageLine}</p>
                </div>
                <Chip code={statusChip(p)} />
              </div>
              <div className="mt-3 text-xs text-slate-600">
                <div className="text-slate-400 mb-1">近期变化</div>
                {(p.recent_changes || []).length === 0 && <div className="text-slate-400">暂无对比样本（需至少两天快照）</div>}
                {(p.recent_changes || []).map((c) => <div key={c}>{c}</div>)}
              </div>
              <div className="mt-2 text-xs text-slate-500">
                风险 {riskN} 项
                {p.health_trend === 'down' && ' · 健康度 ↓'}
                {p.health_trend === 'up' && ' · 健康度 ↑'}
                {p.owner_name && ` · 负责人 ${p.owner_name}`}
              </div>
              {p.summary && (
                <p className="text-sm text-slate-600 mt-3 bg-slate-50 rounded-lg p-3">
                  <span className="text-xs text-slate-400 block mb-1">AI判断</span>
                  {p.summary}
                </p>
              )}
              {p.source === 'project_center' && onOpenProject && (
                <button className="mt-3 text-xs text-brand-600" onClick={() => onOpenProject(p.project_id)}>查看项目</button>
              )}
              {p.source !== 'project_center' && (
                <p className="mt-3 text-[11px] text-slate-400">仅来自日报提及，尚未登记到项目中心，仅作观察。</p>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function RisksTab({ report, onPatch, onEvidence, onOpenProject, onMember }) {
  const rows = report?.risks || []
  if (!report) return <Empty />
  const order = { high: 0, medium: 1, attention: 2, info: 3 }
  const sorted = [...rows].sort((a, b) => (order[a.severity] ?? 9) - (order[b.severity] ?? 9))
  const groups = {}
  for (const r of sorted) {
    const cat = r.category || (String(r.type || '').startsWith('ATTENTION_') ? String(r.type).slice(10) : 'PROJECT')
    if (!groups[cat]) groups[cat] = []
    groups[cat].push(r)
  }
  const cats = ['PROJECT', 'PERSON', 'RESOURCE', 'COLLAB', 'PROGRESS', 'STRUCTURE']
  return (
    <div className="space-y-5">
      <p className="text-xs text-slate-400">团队风险覆盖项目、人员、资源、协作、进度和结构。项目风险事实来自项目中心。</p>
      {sorted.length === 0 && <p className="text-sm text-slate-400">当前无未关闭风险。风险来自规则检测，LLM 只解释。</p>}
      {cats.filter((c) => groups[c]?.length).map((cat) => (
        <section key={cat}>
          <h3 className="text-sm font-semibold text-slate-700 mb-2">{RISK_CAT[cat] || cat}</h3>
          <div className="space-y-3">
            {groups[cat].map((r) => {
              const ui = SEV_UI[r.severity] || SEV_UI.info
              const pid = r.project_id || (r.object_type === 'project' ? r.object_id : null)
              const mid = r.member_id || (r.object_type === 'member' ? r.object_id : null)
              return (
                <div key={r.id || r.risk_id} className={`border rounded-xl p-4 ${ui.cls}`}>
                  <div className="text-xs mb-1">{ui.icon} {ui.label} · {r.type || r.risk_type} · {RISK_STATUS[r.status] || r.status}</div>
                  <div className="font-medium text-slate-800">{r.title}</div>
                  <p className="text-sm text-slate-600 mt-1">{r.description}</p>
                  <div className="flex flex-wrap gap-2 mt-3">
                    <button className="text-xs text-brand-700 hover:underline" onClick={() => onEvidence(r)}>分析依据</button>
                    {pid && onOpenProject && <button className="text-xs text-brand-700 hover:underline" onClick={() => onOpenProject(pid)}>查看项目</button>}
                    {mid && onMember && <button className="text-xs text-brand-700 hover:underline" onClick={() => onMember(mid)}>查看成员</button>}
                    {r.status === 'open' && (
                      <>
                        <button className="px-2 py-1 text-xs rounded bg-white border" onClick={() => onPatch(r.id || r.risk_id, 'confirmed')}>确认</button>
                        <button className="px-2 py-1 text-xs rounded bg-white border" onClick={() => onPatch(r.id || r.risk_id, 'ignored')}>忽略</button>
                        <button className="px-2 py-1 text-xs rounded bg-white border" onClick={() => onPatch(r.id || r.risk_id, 'resolved')}>已解决</button>
                      </>
                    )}
                    {r.status !== 'open' && (
                      <button className="px-2 py-1 text-xs rounded bg-white border" onClick={() => onPatch(r.id || r.risk_id, 'open')}>重开</button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </section>
      ))}
    </div>
  )
}

function TrendsTab({ trends, onRange }) {
  if (!trends) return <div className="text-sm text-slate-400">加载趋势...</div>
  return (
    <div className="space-y-5">
      <div className="flex gap-2">
        {['7d', '30d', '90d'].map((r) => (
          <button
            key={r}
            onClick={() => onRange(r)}
            className={`px-3 py-1 text-sm rounded-lg border ${trends.range === r ? 'border-brand-400 bg-brand-50 text-brand-700' : 'border-slate-200 bg-white'}`}
          >
            {r === '7d' ? '7天' : r === '30d' ? '30天' : '90天'}
          </button>
        ))}
      </div>
      <p className="text-xs text-slate-400">{trends.note}</p>

      <section className="bg-white border border-slate-200 rounded-xl p-4">
        <h3 className="font-semibold mb-3">团队健康度</h3>
        {(trends.health || []).length === 0 && <p className="text-sm text-slate-400">每日报告积累后将形成序列。V1 先提供 7 日 vs 30 日占比。</p>}
        <div className="flex items-end gap-1 h-28">
          {(trends.health || []).map((h) => (
            <div key={h.date} className="flex-1 flex flex-col items-center justify-end h-full">
              <div className="w-full bg-brand-500 rounded-t" style={{ height: `${Math.max(8, h.score || 0)}%` }} title={`${h.date} ${h.score}`} />
              <span className="text-[10px] text-slate-400 mt-1 truncate w-full text-center">{String(h.date).slice(5)}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="bg-white border border-slate-200 rounded-xl p-4">
        <h3 className="font-semibold mb-3">成员趋势</h3>
        <div className="space-y-3">
          {(trends.member_focus || []).map((m) => {
            const ups = Object.entries(m.delta || {}).filter(([, v]) => v >= 8).map(([k, v]) => `${k} ↑ ${v}%`)
            const downs = Object.entries(m.delta || {}).filter(([, v]) => v <= -8).map(([k, v]) => `${k} ↓ ${Math.abs(v)}%`)
            return (
              <div key={m.member_id} className="text-sm border-b border-slate-100 pb-2">
                <div className="font-medium">{m.name} <span className="text-xs text-slate-400 font-normal">负载 {m.workload}</span></div>
                <div className="text-xs text-slate-600 mt-1">{[...ups, ...downs].join('　') || '重心相对稳定'}</div>
              </div>
            )
          })}
        </div>
      </section>

      <section className="bg-white border border-slate-200 rounded-xl p-4">
        <h3 className="font-semibold mb-3">项目趋势</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm mb-3">
          <div>项目总数 <b>{trends.project_stats?.total ?? trends.team?.project_count ?? 0}</b></div>
          <div>开启 <b>{trends.project_stats?.open ?? trends.project_stats?.active ?? 0}</b></div>
          <div>暂停 <b>{trends.project_stats?.paused ?? 0}</b></div>
          <div>关闭 <b>{trends.project_stats?.closed ?? trends.project_stats?.completed ?? 0}</b></div>
        </div>
        <div className="text-xs text-slate-500 space-y-0.5">
          <div>本周完成阶段 +{trends.team?.week_stage_advances ?? 0}</div>
          <div>新增风险 +{trends.team?.week_risks_added ?? 0}　解决风险 +{trends.team?.week_risks_resolved ?? 0}</div>
          <div>延期里程碑 +{trends.team?.week_milestones_delayed ?? 0}</div>
        </div>
        {trends.project_stats?.summary && <p className="text-sm text-slate-700 mt-3">{trends.project_stats.summary}</p>}
        <div className="mt-3 space-y-1 text-sm">
          {(trends.projects || []).map((p) => (
            <div key={p.project_id} className="flex justify-between">
              <span>{p.name}</span>
              <span className="text-slate-500">{p.stage || '—'} · {p.health_trend === 'down' ? '↓' : p.health_trend === 'up' ? '↑' : '→'}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="bg-white border border-slate-200 rounded-xl p-4">
        <h3 className="font-semibold mb-2">团队趋势</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
          <div>平均负载 <b>{trends.team?.load_avg ?? '—'}</b></div>
          <div>协作分 <b>{trends.team?.collaboration_score ?? '—'}</b></div>
          <div>风险数 <b>{trends.team?.risk_count ?? 0}</b></div>
          <div>资源冲突 <b>{trends.team?.resource_conflicts ?? 0}</b></div>
        </div>
        {trends.member_trend && (
          <div className="mt-3 text-xs text-slate-500">
            近7日团队投入：开发 {trends.member_trend.dev}% · 管理/协调 {trends.member_trend.mgmt}% · 协作 {trends.member_trend.collab}% · 培养 {trends.member_trend.mentor}%
          </div>
        )}
      </section>

      {(trends.ai_trends || []).length > 0 && (
        <section className="bg-white border border-slate-200 rounded-xl p-4">
          <h3 className="font-semibold mb-2">AI 趋势结论</h3>
          <p className="text-sm text-slate-700 mb-3">{trends.ai_summary}</p>
          {(trends.ai_trends || []).map((t, i) => (
            <div key={i} className="text-sm mb-2">
              <div className="font-medium">{t.name} {t.direction === 'up' ? '↑' : t.direction === 'down' ? '↓' : '→'}</div>
              {t.fact && <p className="text-xs text-slate-600"><span className="font-medium">事实：</span>{t.fact}</p>}
              {t.inference && <p className="text-xs text-slate-500"><span className="font-medium">推断：</span>{t.inference}</p>}
            </div>
          ))}
        </section>
      )}
    </div>
  )
}

function ConfigTab({ config, members = [], includedIds = [], onSave, onSaveMembers }) {
  const [form, setForm] = useState({
    project_weight: config.project_weight ?? 40,
    member_weight: config.member_weight ?? 25,
    task_weight: config.task_weight ?? 20,
    collab_weight: config.collab_weight ?? 15,
    scheduler_enabled: !!config.scheduler_enabled,
    scheduler_hour: config.scheduler_hour ?? 12,
    scheduler_minute: config.scheduler_minute ?? 0,
  })
  const [picked, setPicked] = useState(includedIds)
  const total = Number(form.project_weight) + Number(form.member_weight) + Number(form.task_weight) + Number(form.collab_weight)
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }))
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-4 max-w-xl">
      <h3 className="font-semibold">计入团队人员</h3>
      <p className="text-xs text-slate-500">未勾选的人不计入 Team Health Score、人员负载和缺勤。适合把协作方、已离职或非本团队人员排除在外。</p>
      <MemberScopeList members={members} selected={picked} onChange={setPicked} />
      <button
        type="button"
        disabled={!picked.length}
        onClick={() => onSaveMembers(picked)}
        className="px-3 py-2 text-sm rounded-lg border border-slate-200 hover:bg-slate-50 disabled:opacity-50"
      >
        保存人员并重新分析
      </button>

      <h3 className="font-semibold pt-2">健康度权重（第一版可配置）</h3>
      {[
        ['project_weight', '项目健康度'],
        ['member_weight', '人员状态'],
        ['task_weight', '任务推进'],
        ['collab_weight', '协作稳定性'],
      ].map(([k, label]) => (
        <label key={k} className="flex items-center justify-between text-sm">
          <span>{label}</span>
          <input
            type="number"
            className="w-24 border rounded px-2 py-1"
            value={form[k]}
            onChange={(e) => set(k, Number(e.target.value))}
          />
        </label>
      ))}
      <p className={`text-xs ${Math.abs(total - 100) < 0.1 ? 'text-slate-400' : 'text-amber-600'}`}>合计 {total}（按比例归一化，不必严格等于 100）</p>
      <h3 className="font-semibold pt-2">每日自动分析</h3>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={form.scheduler_enabled} onChange={(e) => set('scheduler_enabled', e.target.checked)} />
        启用调度
      </label>
      <div className="flex items-center gap-2 text-sm">
        <input type="number" min={0} max={23} className="w-16 border rounded px-2 py-1" value={form.scheduler_hour} onChange={(e) => set('scheduler_hour', Number(e.target.value))} />
        :
        <input type="number" min={0} max={59} className="w-16 border rounded px-2 py-1" value={form.scheduler_minute} onChange={(e) => set('scheduler_minute', Number(e.target.value))} />
      </div>
      <p className="text-xs text-slate-400">数据源：日报（今天做了什么）、项目中心（项目现在是什么）、角色卡、人际关系网、AI Native 竞争。团队态势只做变化检测与判断，不管理项目。</p>
      <p className="text-xs text-slate-400">本工作台为本地单用户。成员互评隔离将在接入登录后生效；请勿把晋升潜力类判断转发给普通成员。</p>
      <button onClick={() => onSave(form)} className="px-3 py-2 text-sm rounded-lg bg-brand-600 text-white">保存配置</button>
    </div>
  )
}

function MemberScopeList({ members, selected, onChange }) {
  const ids = members.map((m) => m.id)
  const toggle = (id) => {
    if (selected.includes(id)) onChange(selected.filter((x) => x !== id))
    else onChange([...selected, id])
  }
  return (
    <div>
      <div className="flex gap-2 mb-2">
        <button type="button" className="text-xs text-brand-600" onClick={() => onChange(ids)}>全选</button>
        <button type="button" className="text-xs text-slate-500" onClick={() => onChange([])}>清空</button>
        <span className="text-xs text-slate-400">已选 {selected.length} / {members.length}</span>
      </div>
      <div className="max-h-56 overflow-y-auto border border-slate-100 rounded-lg divide-y">
        {members.map((m) => (
          <label key={m.id} className="flex items-center gap-2 px-3 py-2 text-sm hover:bg-slate-50 cursor-pointer">
            <input type="checkbox" checked={selected.includes(m.id)} onChange={() => toggle(m.id)} />
            <span className="font-medium text-slate-800">{m.name}</span>
            <span className="text-xs text-slate-400">{m.role}</span>
          </label>
        ))}
        {members.length === 0 && <div className="px-3 py-4 text-xs text-slate-400">暂无成员</div>}
      </div>
    </div>
  )
}

function TeamScopeModal({ members, selectedIds, onClose, onSave, saving }) {
  const [picked, setPicked] = useState(selectedIds)
  return (
    <div className="fixed inset-0 bg-black/30 z-40 flex items-center justify-center p-4">
      <div className="bg-white rounded-xl w-full max-w-md p-5 shadow-xl">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold">修改团队人员</h3>
          <button type="button" onClick={onClose}><X size={16} /></button>
        </div>
        <p className="text-xs text-slate-500 mb-3">只勾选本团队成员。未勾选的人不计入 Team Health Score。</p>
        <MemberScopeList members={members} selected={picked} onChange={setPicked} />
        <div className="flex justify-end gap-2 mt-4">
          <button type="button" onClick={onClose} className="px-3 py-1.5 text-sm">取消</button>
          <button
            type="button"
            disabled={saving || !picked.length}
            onClick={() => onSave(picked)}
            className="px-3 py-1.5 text-sm rounded-lg bg-brand-600 text-white disabled:opacity-50 flex items-center gap-1"
          >
            {saving && <Loader2 size={14} className="animate-spin" />}
            保存并重新分析
          </button>
        </div>
      </div>
    </div>
  )
}

function ContextModal({ members, contexts, onClose, onSaved }) {
  const [ctype, setCtype] = useState(CONTEXT_TYPES[0].id)
  const [content, setContent] = useState('')
  const [saving, setSaving] = useState(false)
  const hint = CONTEXT_TYPES.find((t) => t.id === ctype)?.hint
  const submit = async () => {
    if (!content.trim()) return
    setSaving(true)
    try {
      await api.addSituationContext({
        context_type: ctype,
        content: content.trim(),
        context_date: todayStr(),
        creator_id: members[0]?.id || '',
      })
      await onSaved()
    } finally {
      setSaving(false)
    }
  }
  return (
    <div className="fixed inset-0 bg-black/30 z-40 flex items-center justify-center p-4">
      <div className="bg-white rounded-xl w-full max-w-lg p-5 shadow-xl">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold">补充团队信息</h3>
          <button onClick={onClose}><X size={16} /></button>
        </div>
        <p className="text-xs text-slate-500 mb-3">写入 Team Context，标记 source=manual，不会与自动采集数据混淆。</p>
        <div className="flex flex-wrap gap-1 mb-3">
          {CONTEXT_TYPES.map((t) => (
            <button
              key={t.id}
              onClick={() => setCtype(t.id)}
              className={`px-2 py-1 text-xs rounded-lg border ${ctype === t.id ? 'border-brand-400 bg-brand-50' : 'border-slate-200'}`}
            >
              {t.id}
            </button>
          ))}
        </div>
        <p className="text-xs text-slate-500 mb-2">{hint}</p>
        <textarea
          className="w-full border rounded-lg p-2 text-sm h-28"
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="只记录系统不知道、但值得进入今日分析的事实。"
        />
        <div className="flex justify-end gap-2 mt-3">
          <button onClick={onClose} className="px-3 py-1.5 text-sm">取消</button>
          <button disabled={saving || !content.trim()} onClick={submit} className="px-3 py-1.5 text-sm rounded-lg bg-brand-600 text-white disabled:opacity-50">
            {saving ? '提交中...' : '提交'}
          </button>
        </div>
        {contexts?.length > 0 && (
          <div className="mt-4 border-t pt-3">
            <div className="text-xs text-slate-400 mb-2">今日已补充</div>
            {contexts.map((c) => (
              <div key={c.id} className="text-xs text-slate-600 mb-1">
                <span className="text-slate-400">[{c.context_type}]</span> {c.content}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function EvidenceDrawer({ item, onClose }) {
  const facts = item.evidence || item.facts || []
  return (
    <div className="fixed inset-0 bg-black/30 z-40 flex items-end md:items-center justify-center p-4">
      <div className="bg-white rounded-xl w-full max-w-lg p-5 shadow-xl">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold">分析依据</h3>
          <button onClick={onClose}><X size={16} /></button>
        </div>
        <p className="font-medium text-sm">{item.title}</p>
        {item.confidence != null && (
          <p className="text-xs text-slate-400 mt-1">置信度 {Math.round(Number(item.confidence) * 100)}%</p>
        )}
        {item.fact && <p className="text-sm mt-2"><span className="font-medium">事实：</span>{item.fact}</p>}
        {item.inference && <p className="text-sm text-slate-600"><span className="font-medium">推断：</span>{item.inference}</p>}
        {item.suggestion && <p className="text-sm text-slate-600"><span className="font-medium">建议：</span>{item.suggestion}</p>}
        <ul className="mt-3 text-sm text-slate-600 list-disc pl-5 space-y-1">
          {(Array.isArray(facts) ? facts : []).map((e, i) => <li key={i}>{typeof e === 'string' ? e : JSON.stringify(e)}</li>)}
        </ul>
      </div>
    </div>
  )
}

function Empty() {
  return <div className="text-sm text-slate-500 bg-white border border-dashed rounded-xl p-8 text-center">请先生成今日态势。</div>
}
