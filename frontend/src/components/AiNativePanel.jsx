import React, { useState, useEffect, useRef } from 'react'
import {
  Sparkles, RefreshCw, ChevronRight, ArrowLeft,
  Users, Target, AlertTriangle, Loader2, Shield,
} from 'lucide-react'
import { api } from '../api/client.js'
import { RecordEventButton } from './EventRecorderContext.jsx'

export default function AiNativePanel({ members }) {
  const [roles, setRoles] = useState([])
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [selectedRoleId, setSelectedRoleId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [ranking, setRanking] = useState({ status: 'idle', progress: 0, message: '' })
  const [rankingBusy, setRankingBusy] = useState(false)
  const [toast, setToast] = useState(null)
  const mountedRef = useRef(true)

  const loadRoles = async () => {
    const data = await api.getAiNativeRoles()
    if (!mountedRef.current) return
    setRoles(data.roles || [])
    setSummary(data.summary || null)
    if (data.ranking_status) setRanking(data.ranking_status)
  }

  const attachRankingWatch = async () => {
    setRankingBusy(true)
    const unsub = api.onAiNativeRankingProgress((st) => {
      if (mountedRef.current) setRanking(st)
    })
    try {
      const final = await api.watchAiNativeRanking()
      if (!mountedRef.current) return
      setRanking(final)
      if (final.status === 'success') {
        setToast(final.message || '排名更新完成')
        await loadRoles()
      } else if (final.status === 'failed') {
        setToast(final.message || '排名更新失败')
      }
    } catch (err) {
      if (mountedRef.current) setToast(err.message || '排名任务异常')
    } finally {
      unsub()
      if (mountedRef.current) setRankingBusy(false)
    }
  }

  useEffect(() => {
    mountedRef.current = true
    ;(async () => {
      try {
        await loadRoles()
        const st = await api.getAiNativeRankingStatus()
        if (!mountedRef.current) return
        setRanking(st)
        // 页面切回时：若任务仍在跑，只恢复轮询，不重新触发
        if (st.status === 'running' || api.getAiNativeRankingPromise()) {
          attachRankingWatch()
        }
      } catch (err) {
        if (mountedRef.current) setToast(err.message || '加载失败')
      } finally {
        if (mountedRef.current) setLoading(false)
      }
    })()
    return () => { mountedRef.current = false }
  }, [])

  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => mountedRef.current && setToast(null), 5000)
    return () => clearTimeout(t)
  }, [toast])

  const handleUpdateRanking = async () => {
    if (rankingBusy || ranking.status === 'running') return
    setRankingBusy(true)
    setToast(null)
    const unsub = api.onAiNativeRankingProgress((st) => {
      if (mountedRef.current) setRanking(st)
    })
    try {
      const final = await api.updateAiNativeRanking()
      if (!mountedRef.current) return
      setRanking(final)
      if (final.status === 'success') {
        setToast(final.message || '排名更新完成')
        await loadRoles()
        if (selectedRoleId) {
          const d = await api.getAiNativeRoleDetail(selectedRoleId)
          if (mountedRef.current) setDetail(d)
        }
      } else if (final.status === 'failed') {
        setToast(final.message || '排名更新失败')
      } else if (final.status === 'running') {
        // 幂等命中已有任务
        setToast(final.message || '已有分析任务执行中')
      }
    } catch (err) {
      if (mountedRef.current) setToast(err.message || '触发失败')
    } finally {
      unsub()
      if (mountedRef.current) setRankingBusy(false)
    }
  }

  const openDetail = async (roleId) => {
    setSelectedRoleId(roleId)
    setDetailLoading(true)
    setDetail(null)
    try {
      const d = await api.getAiNativeRoleDetail(roleId)
      if (mountedRef.current) setDetail(d)
    } catch (err) {
      if (mountedRef.current) setToast(err.message || '加载详情失败')
      setSelectedRoleId(null)
    } finally {
      if (mountedRef.current) setDetailLoading(false)
    }
  }

  const isRunning = rankingBusy || ranking.status === 'running'

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-slate-400 text-sm">加载 AI Native 角色地图...</div>
      </div>
    )
  }

  if (selectedRoleId) {
    return (
      <>
        {isRunning && (
          <div className="px-6 pt-4 max-w-3xl mx-auto">
            <div className="bg-brand-50 border border-brand-100 rounded-xl px-4 py-3">
              <div className="flex items-center justify-between text-sm text-brand-700 mb-2">
                <span className="font-medium flex items-center gap-2">
                  <Loader2 size={14} className="animate-spin" />
                  {ranking.message || '分析中...'}
                </span>
                <span>{ranking.progress ?? 0}%</span>
              </div>
              <div className="w-full bg-white rounded-full h-1.5 overflow-hidden">
                <div className="h-1.5 bg-brand-500 rounded-full" style={{ width: `${Math.min(100, ranking.progress || 0)}%` }} />
              </div>
            </div>
          </div>
        )}
        <RoleDetailView
          detail={detail}
          loading={detailLoading}
          rankingBusy={isRunning}
          onBack={() => { setSelectedRoleId(null); setDetail(null) }}
          onRerun={handleUpdateRanking}
          onScopeSaved={async (msg) => {
            setToast(msg)
            const d = await api.getAiNativeRoleDetail(selectedRoleId)
            if (mountedRef.current) setDetail(d)
            await loadRoles()
          }}
        />
      </>
    )
  }

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto fade-in">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
            <Sparkles size={20} className="text-brand-600" />
            角色卡
          </h2>
          <p className="text-sm text-slate-500 mt-1">角色职责 · 培养标准 · 人AI分工 · 问题定义与结构化沟通</p>
        </div>
        <div className="flex items-center gap-2">
          <RecordEventButton context={{ source: 'role-card', event_type: 'people_development' }} />
          <button
          onClick={handleUpdateRanking}
          disabled={isRunning}
          className="flex items-center gap-1.5 text-sm font-medium text-white bg-brand-600 hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed px-3.5 py-2 rounded-lg transition-colors"
        >
          {isRunning ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}
          {isRunning ? '更新排名中...' : '更新排名'}
        </button>
        </div>
      </div>

      {/* 覆盖摘要 */}
      <div className="grid grid-cols-3 gap-4">
        <SummaryCard
          icon={Target}
          label="角色数量"
          value={summary?.role_count ?? roles.length}
          hint={`团队成员 ${summary?.member_count ?? members.length} 人`}
        />
        <SummaryCard
          icon={Shield}
          label="覆盖率"
          value={`${summary?.coverage_rate ?? 0}%`}
          hint={`已覆盖 ${summary?.covered_count ?? 0} 个角色`}
          accent="text-emerald-600"
        />
        <SummaryCard
          icon={AlertTriangle}
          label="高风险角色"
          value={summary?.high_risk_roles ?? summary?.competition_risk ?? 0}
          hint="缺少备份或差距过小的角色数"
          accent="text-amber-600"
        />
      </div>

      {/* 分析进度条 */}
      {isRunning && (
        <div className="bg-brand-50 border border-brand-100 rounded-xl px-4 py-3 fade-in">
          <div className="flex items-center justify-between text-sm text-brand-700 mb-2">
            <span className="font-medium flex items-center gap-2">
              <Loader2 size={14} className="animate-spin" />
              AI正在重新分析团队角色竞争关系...
            </span>
            <span>{ranking.progress ?? 0}%</span>
          </div>
          <div className="w-full bg-white rounded-full h-1.5 overflow-hidden">
            <div
              className="h-1.5 bg-brand-500 rounded-full transition-all"
              style={{ width: `${Math.min(100, ranking.progress || 0)}%` }}
            />
          </div>
          {ranking.message && (
            <p className="text-[11px] text-brand-600/80 mt-1.5">{ranking.message}</p>
          )}
        </div>
      )}

      {toast && (
        <div className="text-xs bg-slate-800 text-white rounded-lg px-3 py-2 fade-in">{toast}</div>
      )}

      {/* 角色卡 */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {roles.map((role) => (
          <RoleCard key={role.id} role={role} onOpen={() => openDetail(role.id)} />
        ))}
      </div>

      {roles.length === 0 && (
        <div className="text-center text-slate-400 text-sm py-16">
          暂无角色数据。请确认后端已初始化 AI Native 角色模型。
        </div>
      )}
    </div>
  )
}

function SummaryCard({ icon: Icon, label, value, hint, accent }) {
  return (
    <div className="bg-white rounded-2xl p-5 shadow-sm border border-slate-100">
      <div className="flex items-center gap-2 text-slate-500 text-xs mb-2">
        <Icon size={14} />
        {label}
      </div>
      <div className={`text-3xl font-bold text-slate-800 ${accent || ''}`}>{value}</div>
      {hint && <div className="text-[11px] text-slate-400 mt-1">{hint}</div>}
    </div>
  )
}

function RoleCard({ role, onOpen }) {
  const risk = role.risk_level || 'low'
  const riskCls = risk === 'high' ? 'text-red-600 bg-red-50' : risk === 'medium' ? 'text-amber-600 bg-amber-50' : 'text-emerald-600 bg-emerald-50'
  const riskText = { high: '高风险', medium: '中风险', low: '低风险' }[risk] || risk
  return (
    <div className="bg-white rounded-2xl p-5 shadow-sm border border-slate-100 flex flex-col hover:border-brand-200 transition-colors">
      <div className="flex items-start justify-between mb-3">
        <h3 className="text-sm font-bold text-slate-800">{role.name}</h3>
        <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${riskCls}`}>{riskText}</span>
      </div>

      <div className="mb-3">
        <div className="text-[10px] text-slate-400 mb-0.5">当前负责人</div>
        <div className="text-sm font-semibold text-slate-700 flex items-center gap-1.5">
          <Users size={13} className="text-slate-400" />
          {role.owner?.name || '暂无匹配'}
          {role.owner?.score != null && (
            <span className="text-[10px] font-medium text-brand-600 bg-brand-50 px-1.5 py-0.5 rounded">
              {role.owner.score}%
            </span>
          )}
        </div>
      </div>

      <p className="text-xs text-slate-500 leading-relaxed line-clamp-2 mb-3 flex-1">
        {role.summary || role.description || '暂无职责摘要'}
      </p>

      <div className="mb-3">
        <div className="text-[10px] text-slate-400 mb-1.5">竞争 Top2</div>
        {role.competitors?.length ? (
          <div className="space-y-1">
            {role.competitors.map((c, i) => (
              <div key={c.employee_id} className="flex items-center justify-between text-xs">
                <span className="text-slate-600">
                  <span className="text-slate-400 mr-1">{i + 1}.</span>
                  {c.name}
                </span>
                <span className="text-slate-500 font-medium">匹配度 {c.score}%</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-xs text-slate-400">暂无竞争数据，请先更新排名</div>
        )}
      </div>

      <div className="text-[11px] text-slate-500 mb-3">
        评估范围：{role.evaluation_scope?.label || '当前团队'}
      </div>

      <button
        onClick={onOpen}
        className="mt-auto flex items-center justify-between text-xs font-medium text-brand-600 hover:text-brand-700 pt-2 border-t border-slate-100"
      >
        查看详情
        <ChevronRight size={14} />
      </button>
    </div>
  )
}

function RoleDetailView({ detail, loading, onBack, onRerun, onScopeSaved, rankingBusy }) {
  const [scopeOpen, setScopeOpen] = useState(false)

  if (loading || !detail) {
    return (
      <div className="p-6 max-w-3xl mx-auto fade-in">
        <button onClick={onBack} className="flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700 mb-6">
          <ArrowLeft size={15} /> 返回
        </button>
        <div className="text-slate-400 text-sm py-12 text-center">加载角色详情...</div>
      </div>
    )
  }

  const { role, current_owner: owner, competition, risk_analysis: risk } = detail

  return (
    <div className="p-6 max-w-3xl mx-auto fade-in space-y-5">
      <button onClick={onBack} className="flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700">
        <ArrowLeft size={15} /> 返回
      </button>

      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-800">角色详情</h2>
          <p className="text-sm text-slate-500 mt-1">{role.name}</p>
        </div>
        <button
          onClick={onRerun}
          disabled={rankingBusy}
          className="flex items-center gap-1.5 text-sm font-medium text-white bg-brand-600 hover:bg-brand-700 disabled:opacity-50 px-3 py-2 rounded-lg"
        >
          {rankingBusy ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
          重新分析
        </button>
      </div>

      <section className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5 space-y-3">
        <h3 className="text-sm font-bold text-slate-800">当前负责人</h3>
        {owner ? (
          <div>
            <div className="flex items-center gap-2">
              <span className="text-base font-semibold text-slate-800">{owner.name}</span>
              <span className="text-[11px] text-brand-600 bg-brand-50 px-1.5 py-0.5 rounded">
                匹配度 {owner.score}%
              </span>
            </div>
            {owner.role && <div className="text-xs text-slate-400 mt-0.5">现任职位：{owner.role}</div>}
            {owner.analysis && <p className="text-xs text-slate-600 mt-2 leading-relaxed">{owner.analysis}</p>}
            {owner.oig && (
              <div className="mt-3 grid grid-cols-4 gap-2">
                {[
                  ['组织影响力', owner.oig.influence],
                  ['信任', owner.oig.trust],
                  ['资源控制', owner.oig.resource_control],
                  ['冲突风险', owner.oig.conflict_risk],
                ].map(([label, val]) => (
                  <div key={label} className="bg-slate-50 rounded-lg px-2 py-1.5 text-center">
                    <div className="text-[10px] text-slate-400">{label}</div>
                    <div className="text-sm font-bold text-slate-800">{val ?? '-'}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : (
          <p className="text-xs text-slate-400">暂无匹配负责人，请点击「更新排名」</p>
        )}
      </section>

      <section className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5 space-y-3">
        <h3 className="text-sm font-bold text-slate-800">AI Native职责</h3>
        <p className="text-xs text-slate-600 leading-relaxed">{role.description}</p>
        {role.responsibilities?.length > 0 && (
          <ul className="text-xs text-slate-600 space-y-1 list-disc list-inside">
            {role.responsibilities.map((r) => <li key={r}>{r}</li>)}
          </ul>
        )}
      </section>

      <section className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5 space-y-3">
        <h3 className="text-sm font-bold text-slate-800">核心能力要求</h3>
        {role.required_skills?.length ? (
          <div className="flex flex-wrap gap-2">
            {role.required_skills.map((s) => (
              <span key={s} className="text-[11px] bg-slate-100 text-slate-600 px-2 py-1 rounded-md">{s}</span>
            ))}
          </div>
        ) : (
          <p className="text-xs text-slate-400">暂无</p>
        )}
      </section>

      <section className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5 space-y-3">
        <h3 className="text-sm font-bold text-slate-800">培养标准</h3>
        {(detail.training_standards?.dimensions || []).map((d) => (
          <div key={d.id} className="border border-slate-100 rounded-lg p-3">
            <div className="text-xs font-semibold text-slate-800 mb-1.5">{d.name}</div>
            <div className="space-y-1">
              {Object.entries(d.levels || {}).map(([lv, text]) => (
                <div key={lv} className="text-[11px] text-slate-600 flex gap-2">
                  <span className="text-slate-400 w-20 flex-none">{lv === 'management' ? '干部要求' : lv}</span>
                  <span>{text}</span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </section>

      <section className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5 space-y-2">
        <h3 className="text-sm font-bold text-slate-800">问题定义与结构化沟通</h3>
        <p className="text-xs text-slate-600">{detail.communication_capability?.description}</p>
        <div className="flex flex-wrap gap-1.5">
          {(detail.communication_capability?.evaluations || []).map((e) => (
            <span key={e.id} className="text-[11px] bg-brand-50 text-brand-700 px-2 py-1 rounded-md">{e.label}</span>
          ))}
        </div>
      </section>

      <section className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5 space-y-2">
        <h3 className="text-sm font-bold text-slate-800">人 / AI 分工</h3>
        <table className="w-full text-xs">
          <thead>
            <tr className="text-slate-400">
              <th className="text-left py-1">工作项</th><th>人</th><th>AI</th><th>最终责任</th>
            </tr>
          </thead>
          <tbody>
            {(detail.human_ai_division || []).map((row) => (
              <tr key={row.item} className="border-t border-slate-50 text-slate-700">
                <td className="py-1.5">{row.item}</td>
                <td className="text-center">{row.human === true ? '✅' : row.human === 'review' ? 'Review' : row.human === 'assist' ? '辅助' : '—'}</td>
                <td className="text-center">{row.ai === true ? '✅' : row.ai === false ? '❌' : row.ai === 'assist' ? '辅助' : String(row.ai || '—')}</td>
                <td className="text-center">{row.owner}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {owner && (
        <section className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5 space-y-3">
          <h3 className="text-sm font-bold text-slate-800">当前人员能力分析 · {owner.name}</h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="text-[11px] text-emerald-600 font-medium mb-1">优势</div>
              <ul className="text-xs text-slate-600 space-y-1">
                {(owner.strengths?.length ? owner.strengths : ['暂无']).map((s) => (
                  <li key={s}>· {s}</li>
                ))}
              </ul>
            </div>
            <div>
              <div className="text-[11px] text-amber-600 font-medium mb-1">不足</div>
              <ul className="text-xs text-slate-600 space-y-1">
                {(owner.gaps?.length ? owner.gaps : ['暂无']).map((s) => (
                  <li key={s}>· {s}</li>
                ))}
              </ul>
            </div>
          </div>
        </section>
      )}

      <section className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5 space-y-3">
        <h3 className="text-sm font-bold text-slate-800">竞争人员</h3>
        {competition?.length ? (
          <div className="space-y-3">
            {competition.slice(0, 2).map((c) => (
              <div key={c.employee_id} className="p-3 bg-slate-50 rounded-xl">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-semibold text-slate-800">{c.name}</span>
                  <span className="text-[11px] text-slate-500">匹配度 {c.score}%</span>
                </div>
                {c.reason && <p className="text-xs text-slate-500 mb-1.5">{c.reason}</p>}
                {c.strengths?.length > 0 && (
                  <div className="text-[11px] text-slate-500">
                    优势：{c.strengths.join('、')}
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-slate-400">暂无竞争人员数据</p>
        )}
      </section>

      <section className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5 space-y-2">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold text-slate-800">评估范围</h3>
          <button
            onClick={() => setScopeOpen(true)}
            className="text-xs font-medium text-brand-600 hover:text-brand-700"
          >
            修改评估范围
          </button>
        </div>
        <p className="text-xs text-slate-600">{detail.evaluation_scope?.label || '当前团队'}</p>
        <p className="text-[11px] text-slate-400">
          竞争资格：完成 {detail.evaluation_scope?.minimum_competition_level || 'L2'} 或匹配度 ≥ {detail.evaluation_scope?.minimum_match_score || 60}
          {detail.evaluation_scope?.candidate_count != null ? ` · 当前纳入 ${detail.evaluation_scope.candidate_count} 人` : ''}
        </p>
        <p className="text-[11px] text-slate-400">保存范围后不会自动重算，需点击「重新分析 / 更新排名」。</p>
      </section>

      <section className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5 space-y-2">
        <h3 className="text-sm font-bold text-slate-800">风险分析</h3>
        <div className="text-xs text-slate-600 space-y-1.5">
          <div>
            <span className="text-slate-400">如果负责人离开 · 影响：</span>
            <span className={`ml-1 font-semibold ${
              risk?.impact === '高' ? 'text-red-600' : risk?.impact === '中' ? 'text-amber-600' : 'text-emerald-600'
            }`}>
              {risk?.impact || '未知'}
            </span>
          </div>
          {risk?.if_owner_leaves && <p>{risk.if_owner_leaves}</p>}
          {risk?.suggestion && (
            <p>
              <span className="text-slate-400">建议：</span>
              {risk.suggestion}
            </p>
          )}
        </div>
      </section>
      {scopeOpen && (
        <ScopeModal
          detail={detail}
          onClose={() => setScopeOpen(false)}
          onSaved={async (msg) => {
            setScopeOpen(false)
            if (onScopeSaved) await onScopeSaved(msg)
          }}
        />
      )}
    </div>
  )
}

function ScopeModal({ detail, onClose, onSaved }) {
  const scope = detail.evaluation_scope || {}
  const options = detail.evaluation_options || {}
  const [type, setType] = useState(scope.type || 'TEAM')
  const [project, setProject] = useState(scope.config?.project || '')
  const [ids, setIds] = useState(scope.config?.employee_ids || [])
  const [minLevel, setMinLevel] = useState(scope.minimum_competition_level || 'L2')
  const [minScore, setMinScore] = useState(scope.minimum_match_score || 60)
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState(null)

  const toggle = (id) => {
    setIds((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id])
  }

  const save = async () => {
    setSaving(true)
    setErr(null)
    try {
      const res = await api.updateAiNativeEvaluationScope(detail.role.id, {
        type,
        project: type === 'PROJECT' ? project : undefined,
        employee_ids: type === 'CUSTOM' ? ids : undefined,
        minimum_competition_level: minLevel,
        minimum_match_score: Number(minScore),
      })
      await onSaved(res.message || '评估范围已修改，请点击「更新排名」重新分析。')
    } catch (e) {
      setErr(e.message || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl w-full max-w-md p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-sm font-bold text-slate-800 mb-3">设置角色评估范围</h3>
        <div className="space-y-2 text-sm">
          {[
            ['ALL', '全体人员'],
            ['TEAM', '当前团队'],
            ['PROJECT', '当前项目'],
            ['CUSTOM', '指定人员'],
          ].map(([v, label]) => (
            <label key={v} className="flex items-center gap-2 text-slate-700">
              <input type="radio" name="scope" checked={type === v} onChange={() => setType(v)} />
              {label}
            </label>
          ))}
        </div>
        {type === 'PROJECT' && (
          <select
            className="mt-3 w-full text-sm border border-slate-200 rounded-lg px-3 py-2"
            value={project}
            onChange={(e) => setProject(e.target.value)}
          >
            <option value="">（有日报项目投入的成员）</option>
            {(options.projects || []).map((p) => (
              <option key={p.name} value={p.name}>{p.name}（{p.count}）</option>
            ))}
          </select>
        )}
        {type === 'CUSTOM' && (
          <div className="mt-3 max-h-40 overflow-y-auto border border-slate-100 rounded-lg p-2 space-y-1">
            {(options.members || []).map((m) => (
              <label key={m.id} className="flex items-center gap-2 text-xs text-slate-700">
                <input type="checkbox" checked={ids.includes(m.id)} onChange={() => toggle(m.id)} />
                {m.name} <span className="text-slate-400">{m.role}</span>
              </label>
            ))}
          </div>
        )}
        <div className="grid grid-cols-2 gap-2 mt-3">
          <label className="text-xs text-slate-600">
            最低培养阶段
            <select className="mt-1 w-full border border-slate-200 rounded-lg px-2 py-1.5" value={minLevel} onChange={(e) => setMinLevel(e.target.value)}>
              {['L0', 'L1', 'L2', 'L3', 'L4', 'L5'].map((lv) => <option key={lv} value={lv}>{lv}</option>)}
            </select>
          </label>
          <label className="text-xs text-slate-600">
            或最低匹配度
            <input type="number" className="mt-1 w-full border border-slate-200 rounded-lg px-2 py-1.5" value={minScore} onChange={(e) => setMinScore(e.target.value)} />
          </label>
        </div>
        {err && <p className="text-xs text-red-600 mt-2">{err}</p>}
        <div className="flex justify-end gap-2 mt-4">
          <button onClick={onClose} className="text-sm px-3 py-2 text-slate-500">取消</button>
          <button onClick={save} disabled={saving} className="text-sm font-medium text-white bg-brand-600 disabled:opacity-50 px-3.5 py-2 rounded-lg">
            {saving ? '保存中...' : '保存'}
          </button>
        </div>
      </div>
    </div>
  )
}
