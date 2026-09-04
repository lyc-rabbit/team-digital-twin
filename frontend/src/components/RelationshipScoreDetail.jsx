import React, { useEffect, useState } from 'react'
import { ArrowLeft, Loader2, TrendingDown, TrendingUp, Minus } from 'lucide-react'
import { api } from '../api/client.js'

const TREND = {
  up: { Icon: TrendingUp, text: '上升', cls: 'text-emerald-600' },
  down: { Icon: TrendingDown, text: '下降', cls: 'text-red-600' },
  flat: { Icon: Minus, text: '持平', cls: 'text-slate-500' },
}

export default function RelationshipScoreDetail({ fromId, toId, dimension = 'trust', onClose, onOpenEvent }) {
  const [pair, setPair] = useState(null)
  const [detail, setDetail] = useState(null)
  const [dim, setDim] = useState(dimension)
  const [item, setItem] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let alive = true
    setLoading(true)
    Promise.all([
      api.getRelationshipPair(fromId, toId),
      api.getRelationshipScore(fromId, toId, dim),
    ]).then(([p, d]) => {
      if (!alive) return
      setPair(p)
      setDetail(d)
    }).catch((e) => alive && setError(e.message)).finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [fromId, toId, dim])

  const trend = TREND[detail?.trend] || TREND.flat
  const TrendIcon = trend.Icon
  const dims = pair?.dimensions || []

  if (loading) {
    return <div className="p-6 text-sm text-slate-400 flex items-center gap-2"><Loader2 size={14} className="animate-spin" />加载分值详情...</div>
  }

  return (
    <div className="space-y-4">
      {onClose && (
        <button onClick={onClose} className="text-sm text-slate-500 flex items-center gap-1">
          <ArrowLeft size={14} /> 返回
        </button>
      )}
      {error && <div className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</div>}

      <div>
        <h3 className="text-sm font-bold text-slate-800">
          {(detail?.dimension_label) || '信任'}分值详情
        </h3>
        <p className="text-[11px] text-slate-400 mt-0.5">
          {detail?.from_name} → {detail?.to_name} · 分值由事件证据计算，不是孤立打分
        </p>
      </div>

      {dims.length > 1 && (
        <div className="flex flex-wrap gap-1.5">
          {dims.map((d) => (
            <button
              key={d.id}
              onClick={() => { setDim(d.id); setItem(null) }}
              className={`text-[11px] px-2 py-1 rounded-full border ${dim === d.id ? 'bg-brand-600 text-white border-brand-600' : 'bg-white text-slate-600 border-slate-200'}`}
            >
              {d.label} {d.current}
            </button>
          ))}
        </div>
      )}

      <div className="grid grid-cols-3 gap-3">
        <Stat label="当前分值" value={detail?.current ?? 50} />
        <Stat label={`较上周期（${detail?.period_days || 7}天）`} value={`${(detail?.period_delta || 0) > 0 ? '+' : ''}${detail?.period_delta || 0}`} />
        <div className="bg-slate-50 rounded-xl p-3">
          <div className="text-[11px] text-slate-400 mb-1">趋势</div>
          <div className={`text-lg font-bold flex items-center gap-1 ${trend.cls}`}>
            <TrendIcon size={16} /> {trend.text}
          </div>
        </div>
      </div>

      {item ? (
        <EvidenceFact item={item} onBack={() => setItem(null)} onOpenEvent={onOpenEvent} />
      ) : (
        <>
          <EvidenceList
            title="为什么增长？"
            empty="暂无正向证据"
            items={detail?.positive || []}
            tone="pos"
            onOpen={setItem}
          />
          <EvidenceList
            title="负向证据"
            empty="暂无负向证据"
            items={detail?.negative || []}
            tone="neg"
            onOpen={setItem}
          />
          <Timeline points={detail?.timeline || []} />
        </>
      )}
    </div>
  )
}

function Stat({ label, value }) {
  return (
    <div className="bg-slate-50 rounded-xl p-3">
      <div className="text-[11px] text-slate-400 mb-1">{label}</div>
      <div className="text-2xl font-bold text-slate-800">{value}</div>
    </div>
  )
}

function EvidenceList({ title, empty, items, tone, onOpen }) {
  const cls = tone === 'pos' ? 'text-emerald-700' : 'text-red-600'
  return (
    <section>
      <h4 className="text-xs font-bold text-slate-700 mb-2">{title}</h4>
      {!items.length && <p className="text-xs text-slate-400">{empty}</p>}
      <div className="space-y-1.5">
        {items.map((x, i) => (
          <button
            key={x.id || `${x.event_id}-${i}`}
            onClick={() => onOpen(x)}
            className="w-full text-left bg-white border border-slate-100 hover:border-brand-200 rounded-lg px-3 py-2 flex items-start gap-2"
          >
            <span className={`text-sm font-bold w-10 flex-none ${cls}`}>
              {x.delta > 0 ? '+' : ''}{x.delta}
            </span>
            <span className="text-xs text-slate-700 flex-1">{x.reason}</span>
            <span className="text-[10px] text-slate-400 flex-none">{(x.event_time || '').slice(0, 10)}</span>
          </button>
        ))}
      </div>
    </section>
  )
}

function EvidenceFact({ item, onBack, onOpenEvent }) {
  return (
    <div className="bg-white border border-slate-100 rounded-xl p-4 space-y-2">
      <button onClick={onBack} className="text-[11px] text-brand-600">← 返回证据列表</button>
      <h4 className="text-sm font-bold text-slate-800">事实依据</h4>
      <p className="text-xs text-slate-500">
        事件：{(item.event_time || '').slice(0, 16)} {item.event_title}
      </p>
      {item.facts && (
        <div>
          <div className="text-[11px] font-semibold text-slate-500">事实</div>
          <p className="text-xs text-slate-700 whitespace-pre-wrap">{item.facts}</p>
        </div>
      )}
      {item.result && (
        <div>
          <div className="text-[11px] font-semibold text-slate-500">结果</div>
          <p className="text-xs text-slate-700 whitespace-pre-wrap">{item.result}</p>
        </div>
      )}
      {item.impact && (
        <div>
          <div className="text-[11px] font-semibold text-slate-500">对关系的影响</div>
          <p className="text-xs text-slate-700">{item.impact}</p>
        </div>
      )}
      <div className={`text-sm font-bold ${item.delta >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
        贡献：{item.delta > 0 ? '+' : ''}{item.delta}
      </div>
      {item.event_id && onOpenEvent && (
        <button className="text-xs text-brand-600" onClick={() => onOpenEvent(item.event_id)}>
          查看原始事件
        </button>
      )}
    </div>
  )
}

function Timeline({ points }) {
  const data = (points || []).filter((p) => p.time)
  if (data.length < 1) return null
  const scores = data.map((p) => p.score)
  const min = Math.min(50, ...scores) - 5
  const max = Math.max(80, ...scores) + 5
  const w = 320
  const h = 90
  const xs = data.map((_, i) => 20 + (i * (w - 40)) / Math.max(1, data.length - 1))
  const ys = data.map((p) => h - 16 - ((p.score - min) / (max - min)) * (h - 28))
  const path = xs.map((x, i) => `${i === 0 ? 'M' : 'L'}${x},${ys[i]}`).join(' ')
  return (
    <section>
      <h4 className="text-xs font-bold text-slate-700 mb-2">分值时间线</h4>
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-24 bg-slate-50 rounded-xl">
        <path d={path} fill="none" stroke="#2563eb" strokeWidth="2" />
        {data.map((p, i) => (
          <g key={i}>
            <circle cx={xs[i]} cy={ys[i]} r="3.5" fill="#2563eb">
              <title>{`${p.time?.slice(0, 10) || ''} ${p.delta > 0 ? '+' : ''}${p.delta} → ${p.score}\n${p.reason}`}</title>
            </circle>
            <text x={xs[i]} y={h - 4} textAnchor="middle" fontSize="8" fill="#94a3b8">
              {(p.time || '').slice(5, 10)}
            </text>
          </g>
        ))}
      </svg>
      <p className="text-[10px] text-slate-400 mt-1">把鼠标放到节点上，可看到导致本次变化的事件。</p>
    </section>
  )
}

export function ScoreChip({ fromId, toId, dimension = 'trust', score, onOpen }) {
  const color = score >= 70 ? 'text-emerald-700 bg-emerald-50' : score >= 50 ? 'text-slate-700 bg-slate-50' : 'text-amber-700 bg-amber-50'
  return (
    <button
      type="button"
      onClick={onOpen}
      className={`inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-md ${color}`}
      title="查看为什么是这个分"
    >
      {score}
    </button>
  )
}
