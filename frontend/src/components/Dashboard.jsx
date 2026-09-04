import React, { useState, useEffect, useRef } from 'react'
import { Heart, AlertTriangle, ShieldCheck, TrendingUp, RefreshCw } from 'lucide-react'
import { api } from '../api/client.js'
import { beijingToday } from '../utils/beijingTime.js'
import RelationshipScoreDetail from './RelationshipScoreDetail.jsx'
import { RecordEventButton } from './EventRecorderContext.jsx'

const EMOTION_COLORS = {
  '平静': '#94a3b8',
  '积极': '#22c55e',
  '愉悦': '#22c55e',
  '高涨': '#3b82f6',
  '焦虑': '#f59e0b',
  '不满': '#ef4444',
  '愤怒': '#dc2626',
  '压抑': '#6366f1',
  '疲惫': '#a78bfa',
  '强势': '#f97316',
}

function getEmotionColor(emotion) {
  for (const key of Object.keys(EMOTION_COLORS)) {
    if (emotion && emotion.includes(key)) return EMOTION_COLORS[key]
  }
  return '#94a3b8'
}

function getScoreColor(score) {
  // score: -100 ~ 100
  if (score >= 20) return { bg: '#dcfce7', text: '#15803d', label: '良好' }
  if (score >= -10) return { bg: '#fef9c3', text: '#a16207', label: '中性' }
  if (score >= -30) return { bg: '#fed7aa', text: '#c2410c', label: '紧张' }
  return { bg: '#fecaca', text: '#b91c1c', label: '恶化' }
}

function getHealthColor(health) {
  if (health >= 75) return { color: '#22c55e', icon: ShieldCheck, bg: 'from-emerald-500 to-green-600' }
  if (health >= 50) return { color: '#eab308', icon: TrendingUp, bg: 'from-yellow-500 to-amber-600' }
  if (health >= 30) return { color: '#f97316', icon: AlertTriangle, bg: 'from-orange-500 to-red-500' }
  return { color: '#ef4444', icon: AlertTriangle, bg: 'from-red-500 to-rose-600' }
}

function todayStr() {
  return beijingToday()
}

export default function Dashboard({ members }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [reanalyzing, setReanalyzing] = useState(false)
  const [reanalyzeMsg, setReanalyzeMsg] = useState(null)
  const [selectedPair, setSelectedPair] = useState(null)
  const [eventDate, setEventDate] = useState(todayStr)
  const [dayEvents, setDayEvents] = useState([])
  const [eventsLoading, setEventsLoading] = useState(false)
  const [newcomerHome, setNewcomerHome] = useState(null)
  const mountedRef = useRef(true)

  const loadDashboard = () => api.getDashboard().then(setData)

  const loadNewcomers = () => Promise.all([
    api.getNewcomerInterventions(),
    api.listNewcomers(),
  ]).then(([iv, ov]) => {
    if (mountedRef.current) {
      setNewcomerHome({
        ...iv,
        summary: ov.summary,
        newcomers: ov.newcomers || [],
      })
    }
  }).catch(() => {})

  const loadDayEvents = (date) => {
    setEventsLoading(true)
    // event_time 存的是 datetime-local / ISO 格式（含 T），上界也必须用 T，否则字符串比较会漏掉全部事件
    return api.getEvents({ date_from: `${date}T00:00:00`, date_to: `${date}T23:59:59` })
      .then((events) => {
        if (!mountedRef.current) return
        // API 按时间升序，展示时改为最新在前
        setDayEvents([...events].reverse())
      })
      .catch(() => {
        if (mountedRef.current) setDayEvents([])
      })
      .finally(() => {
        if (mountedRef.current) setEventsLoading(false)
      })
  }

  useEffect(() => {
    mountedRef.current = true
    return () => { mountedRef.current = false }
  }, [])

  useEffect(() => {
    loadDashboard().finally(() => mountedRef.current && setLoading(false))
    loadNewcomers()

    // 挂载时检查是否有进行中的批量重分析(切换页面后再回来)
    const pending = api.getReanalyzeStatus()
    if (pending) {
      setReanalyzing(true)
      pending
        .then((result) => {
          if (!mountedRef.current) return
          const degradedNote = result.degraded > 0
            ? ` · ⚠️ ${result.degraded} 条走降级模式(数据未真实重算)`
            : ''
          setReanalyzeMsg(
            `分析完成：成功 ${result.success}/${result.total} 事件${degradedNote}` +
            (result.failed > 0 ? `，失败 ${result.failed}` : '')
          )
          return Promise.all([loadDashboard(), loadDayEvents(eventDate)])
        })
        .catch((err) => {
          if (!mountedRef.current) return
          setReanalyzeMsg(`重新分析失败：${err.message}`)
        })
        .finally(() => {
          if (!mountedRef.current) return
          setReanalyzing(false)
          setTimeout(() => mountedRef.current && setReanalyzeMsg(null), 8000)
        })
    }
  }, [])

  useEffect(() => {
    loadDayEvents(eventDate)
  }, [eventDate])

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      await Promise.all([loadDashboard(), loadDayEvents(eventDate)])
    } finally {
      if (mountedRef.current) setRefreshing(false)
    }
  }

  const handleReanalyze = async () => {
    setReanalyzing(true)
    setReanalyzeMsg(null)
    try {
      const result = await api.reanalyzeAll()
      if (!mountedRef.current) return
      const degradedNote = result.degraded > 0
        ? ` · ⚠️ ${result.degraded} 条走降级模式(数据未真实重算)`
        : ''
      setReanalyzeMsg(
        `分析完成：成功 ${result.success}/${result.total} 事件${degradedNote}` +
        (result.failed > 0 ? `，失败 ${result.failed}` : '')
      )
      await Promise.all([loadDashboard(), loadDayEvents(eventDate)])
    } catch (err) {
      if (!mountedRef.current) return
      setReanalyzeMsg(`重新分析失败：${err.message}`)
    } finally {
      if (!mountedRef.current) return
      setReanalyzing(false)
      setTimeout(() => mountedRef.current && setReanalyzeMsg(null), 8000)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-slate-400 text-sm">加载团队数据中...</div>
      </div>
    )
  }

  if (!data) return <div className="p-6 text-slate-500">暂无数据</div>

  const { health, grid, states } = data
  const healthStyle = getHealthColor(health.score)
  const HealthIcon = healthStyle.icon

  const memberMap = {}
  for (const m of members) memberMap[m.id] = m

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto fade-in">
      {/* 标题 */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-800">团队总览</h2>
          <p className="text-sm text-slate-500 mt-1">实时团队健康度 · 关系网格 · 情绪状态。点击信任分值查看证据。</p>
        </div>
        <RecordEventButton context={{ source: 'dashboard' }} />
      </div>

      {newcomerHome && (newcomerHome.newcomers || []).length > 0 && (
        <div className="bg-white rounded-2xl border border-slate-100 p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-bold text-slate-800">我的新人</h3>
            <span className="text-[11px] text-slate-400">
              需要我处理：{(newcomerHome.required || 0) + (newcomerHome.attention || 0)} · 正常推进：{newcomerHome.summary?.on_track ?? 0}
            </span>
          </div>
          <div className="space-y-2">
            {(newcomerHome.items || []).slice(0, 4).map((iv) => (
              <div key={iv.id} className="text-xs text-slate-600 flex items-start gap-2">
                <span>{iv.level === 'required' ? '🔴' : '🟡'}</span>
                <div>
                  <span className="font-medium">{iv.employee_name}</span>
                  <span className="text-slate-400"> · {iv.reason}</span>
                  <div className="text-slate-400">建议：{iv.recommended_action}</div>
                </div>
              </div>
            ))}
            {(newcomerHome.newcomers || []).filter((c) => c.intervention_level === 'none').slice(0, 3).map((c) => (
              <div key={c.id} className="text-xs text-slate-500">🟢 {c.employee_name} · {c.onboarding_stage_label}{c.current_task ? ` · ${c.current_task.task_name}` : ''}</div>
            ))}
          </div>
          <p className="text-[11px] text-slate-400 mt-3">完整处理请到侧栏「新人地图」。</p>
        </div>
      )}

      {/* 顶部卡片行 */}
      <div className="grid grid-cols-4 gap-4">
        {/* 健康度大卡 */}
        <div className={`col-span-1 rounded-2xl bg-gradient-to-br ${healthStyle.bg} text-white p-5 shadow-lg relative`}>
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-medium opacity-80">团队健康度</span>
            <div className="flex items-center gap-1.5">
              <button
                onClick={handleReanalyze}
                disabled={reanalyzing}
                title="重新分析所有事件"
                className="flex items-center gap-1 text-xs opacity-80 hover:opacity-100 hover:bg-white/20 px-2 py-1 rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <RefreshCw size={12} className={reanalyzing ? 'animate-spin' : ''} />
                {reanalyzing ? '分析中' : '重新分析'}
              </button>
              <HealthIcon size={18} className="opacity-80" />
            </div>
          </div>
          <div className="text-4xl font-bold">{health.score}</div>
          <div className="text-sm opacity-90 mt-1">{health.level} · {health.description}</div>
          <div className="flex gap-4 mt-3 text-xs opacity-80">
            <span>平均信任 {health.avg_trust?.toString().padStart(1) > 0 ? '+' : ''}{health.avg_trust}</span>
            <span>平均情绪 {health.avg_sentiment > 0 ? '+' : ''}{health.avg_sentiment}</span>
          </div>
          {reanalyzeMsg && (
            <div className="mt-3 text-[11px] bg-white/20 rounded-md px-2 py-1.5 fade-in">
              {reanalyzeMsg}
            </div>
          )}
        </div>

        {/* 成员情绪卡片 */}
        {members.map((m) => {
          const state = states[m.id] || {}
          const emoColor = getEmotionColor(state.emotion)
          return (
            <div key={m.id} className="col-span-1 bg-white rounded-2xl p-5 shadow-sm border border-slate-100">
              <div className="flex items-center gap-2 mb-3">
                <div className="w-10 h-10 rounded-full flex items-center justify-center text-white font-bold text-sm"
                  style={{ background: emoColor }}>
                  {m.name[0]}
                </div>
                <div>
                  <div className="text-sm font-semibold text-slate-800">{m.name}</div>
                  <div className="text-[11px] text-slate-400">{m.role}</div>
                </div>
              </div>
              <div className="flex items-center gap-1.5 mb-1">
                <Heart size={13} style={{ color: emoColor }} />
                <span className="text-sm font-medium" style={{ color: emoColor }}>{state.emotion || '平静'}</span>
              </div>
              <div className="w-full bg-slate-100 rounded-full h-1.5">
                <div className="rounded-full h-1.5 transition-all"
                  style={{ width: `${(state.intensity || 3) * 10}%`, background: emoColor }} />
              </div>
              <div className="text-[10px] text-slate-400 mt-1">情绪强度 {state.intensity || 3}/10</div>
            </div>
          )
        })}
      </div>

      {/* 关系网格 + 近期事件 */}
      <div className="grid grid-cols-5 gap-4">
        {/* 3x3 关系网格 */}
        <div className="col-span-3 bg-white rounded-2xl p-5 shadow-sm border border-slate-100">
          <div className="flex items-start justify-between mb-4">
            <div>
              <h3 className="text-sm font-bold text-slate-800">关系状态网格</h3>
              <p className="text-[11px] text-slate-400 mt-0.5">行=主体，列=客体 · 上=信任度，下=情绪值</p>
            </div>
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              title="重新生成网络数据"
              className="flex items-center gap-1 text-xs text-slate-500 hover:text-brand-600 border border-slate-200 hover:border-brand-300 hover:bg-brand-50 px-2.5 py-1.5 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <RefreshCw size={13} className={refreshing ? 'animate-spin' : ''} />
              {refreshing ? '生成中' : '重新生成'}
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-center text-xs">
              <thead>
                <tr>
                  <th className="p-2"></th>
                  {members.map((m) => (
                    <th key={m.id} className="p-2 text-slate-600 font-medium">{m.name}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {members.map((from) => (
                  <tr key={from.id}>
                    <td className="p-2 text-slate-600 font-medium text-right pr-3">{from.name}</td>
                    {members.map((to) => {
                      if (from.id === to.id) {
                        return <td key={to.id} className="p-2"><div className="bg-slate-50 rounded-lg h-16 flex items-center justify-center text-slate-300">—</div></td>
                      }
                      const key = `${from.id}→${to.id}`
                      const rel = grid[key] || { trust: 0, sentiment: 0, tag: '' }
                      const trustColor = getScoreColor(rel.trust)
                      const sentiColor = getScoreColor(rel.sentiment)
                      return (
                        <td key={to.id} className="p-1.5">
                          <button
                            onClick={() => setSelectedPair(selectedPair === key ? null : key)}
                            className={`w-full rounded-lg h-16 flex flex-col items-center justify-center transition-all hover:scale-105 ${
                              selectedPair === key ? 'ring-2 ring-brand-500' : ''
                            }`}
                            style={{ background: trustColor.bg }}
                          >
                            <span className="text-sm font-bold" style={{ color: trustColor.text }}>
                              {rel.trust > 0 ? '+' : ''}{rel.trust}
                            </span>
                            <span className="text-[10px]" style={{ color: sentiColor.text }}>
                              {rel.sentiment > 0 ? '+' : ''}{rel.sentiment}
                            </span>
                          </button>
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* 选中关系的详情 */}
          {selectedPair && grid[selectedPair] && (
            <div className="mt-4 p-3 bg-slate-50 rounded-lg fade-in">
              <RelationshipScoreDetail
                fromId={selectedPair.split('→')[0]}
                toId={selectedPair.split('→')[1]}
                dimension="trust"
                onClose={() => setSelectedPair(null)}
              />
            </div>
          )}

          <div className="flex items-center gap-3 mt-3 text-[10px] text-slate-400">
            <div className="flex items-center gap-1"><div className="w-3 h-3 rounded bg-green-100"></div>良好 (+20~)</div>
            <div className="flex items-center gap-1"><div className="w-3 h-3 rounded bg-yellow-100"></div>中性</div>
            <div className="flex items-center gap-1"><div className="w-3 h-3 rounded bg-orange-100"></div>紧张</div>
            <div className="flex items-center gap-1"><div className="w-3 h-3 rounded bg-red-100"></div>恶化 (-30~)</div>
          </div>
        </div>

        {/* 近期事件 */}
        <div className="col-span-2 bg-white rounded-2xl p-5 shadow-sm border border-slate-100 flex flex-col">
          <div className="flex items-center justify-between gap-3 mb-4 flex-none">
            <h3 className="text-sm font-bold text-slate-800">近期事件</h3>
            <input
              type="date"
              value={eventDate}
              onChange={(e) => setEventDate(e.target.value)}
              className="text-xs text-slate-600 border border-slate-200 rounded-lg px-2 py-1.5 bg-white hover:border-brand-300 focus:outline-none focus:ring-1 focus:ring-brand-400 focus:border-brand-400"
            />
          </div>
          <div className="space-y-2 flex-1 min-h-0 overflow-y-auto">
            {eventsLoading && (
              <div className="text-center text-slate-400 text-xs py-8">加载中...</div>
            )}
            {!eventsLoading && dayEvents.length === 0 && (
              <div className="text-center text-slate-400 text-xs py-8">该日暂无事件记录</div>
            )}
            {!eventsLoading && dayEvents.map((e) => {
              const involvedNames = (e.involved_members || []).map((id) => memberMap[id]?.name || id).join('、')
              return (
                <div key={e.id} className="p-3 bg-slate-50 rounded-lg hover:bg-slate-100 transition-colors cursor-pointer">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[10px] text-brand-600 font-medium bg-brand-50 px-1.5 py-0.5 rounded">
                      {e.scene || '未分类'}
                    </span>
                    <span className="text-[10px] text-slate-400">{e.event_time?.slice(5, 16)}</span>
                  </div>
                  <p className="text-xs text-slate-700 leading-relaxed line-clamp-2">{e.raw_summary}</p>
                  <div className="text-[10px] text-slate-400 mt-1">{involvedNames}</div>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}
