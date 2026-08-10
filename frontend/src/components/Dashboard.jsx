import React, { useState, useEffect } from 'react'
import { Heart, AlertTriangle, ShieldCheck, TrendingUp, Clock } from 'lucide-react'
import { api } from '../api/client.js'

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

export default function Dashboard({ members }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [selectedPair, setSelectedPair] = useState(null)

  useEffect(() => {
    api.getDashboard().then(setData).finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-slate-400 text-sm">加载团队数据中...</div>
      </div>
    )
  }

  if (!data) return <div className="p-6 text-slate-500">暂无数据</div>

  const { health, grid, states, recent_events } = data
  const healthStyle = getHealthColor(health.score)
  const HealthIcon = healthStyle.icon

  const memberMap = {}
  for (const m of members) memberMap[m.id] = m

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto fade-in">
      {/* 标题 */}
      <div>
        <h2 className="text-xl font-bold text-slate-800">团队总览</h2>
        <p className="text-sm text-slate-500 mt-1">实时团队健康度 · 关系网格 · 情绪状态</p>
      </div>

      {/* 顶部卡片行 */}
      <div className="grid grid-cols-4 gap-4">
        {/* 健康度大卡 */}
        <div className={`col-span-1 rounded-2xl bg-gradient-to-br ${healthStyle.bg} text-white p-5 shadow-lg`}>
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-medium opacity-80">团队健康度</span>
            <HealthIcon size={18} className="opacity-80" />
          </div>
          <div className="text-4xl font-bold">{health.score}</div>
          <div className="text-sm opacity-90 mt-1">{health.level} · {health.description}</div>
          <div className="flex gap-4 mt-3 text-xs opacity-80">
            <span>平均信任 {health.avg_trust?.toString().padStart(1) > 0 ? '+' : ''}{health.avg_trust}</span>
            <span>平均情绪 {health.avg_sentiment > 0 ? '+' : ''}{health.avg_sentiment}</span>
          </div>
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
          <h3 className="text-sm font-bold text-slate-800 mb-1">关系状态网格</h3>
          <p className="text-[11px] text-slate-400 mb-4">行=主体，列=客体 · 上=信任度，下=情绪值</p>

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
              <div className="text-xs text-slate-600">
                <span className="font-semibold">{selectedPair.replace('→', ' → ')}</span>
                <span className="mx-2 text-slate-300">|</span>
                <span>{grid[selectedPair].tag}</span>
              </div>
              <div className="flex gap-6 mt-2 text-xs">
                <div>
                  <span className="text-slate-400">信任度:</span>
                  <span className="ml-1 font-semibold" style={{ color: getScoreColor(grid[selectedPair].trust).text }}>
                    {grid[selectedPair].trust > 0 ? '+' : ''}{grid[selectedPair].trust}
                  </span>
                  <span className="text-slate-300 ml-1">/ 100</span>
                </div>
                <div>
                  <span className="text-slate-400">情绪值:</span>
                  <span className="ml-1 font-semibold" style={{ color: getScoreColor(grid[selectedPair].sentiment).text }}>
                    {grid[selectedPair].sentiment > 0 ? '+' : ''}{grid[selectedPair].sentiment}
                  </span>
                  <span className="text-slate-300 ml-1">/ 100</span>
                </div>
              </div>
              {grid[selectedPair].last_event_time && (
                <div className="text-[10px] text-slate-400 mt-1.5 flex items-center gap-1">
                  <Clock size={10} />
                  最后更新: {grid[selectedPair].last_event_time}
                </div>
              )}
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
        <div className="col-span-2 bg-white rounded-2xl p-5 shadow-sm border border-slate-100">
          <h3 className="text-sm font-bold text-slate-800 mb-4">近期事件</h3>
          <div className="space-y-2 max-h-80 overflow-y-auto">
            {recent_events.length === 0 && (
              <div className="text-center text-slate-400 text-xs py-8">暂无事件记录</div>
            )}
            {recent_events.map((e) => {
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
