import React, { useEffect, useMemo, useRef, useState } from 'react'

const TYPE_COLORS = {
  Person: '#4f46e5',
  Role: '#8b5cf6',
  Department: '#0ea5e9',
  Project: '#f59e0b',
  Resource: '#10b981',
  Knowledge: '#ec4899',
  Event: '#64748b',
  InformalGroup: '#14b8a6',
}

const REL_COLORS = {
  REPORT_TO: '#94a3b8',
  COLLABORATE_WITH: '#3b82f6',
  MENTOR: '#10b981',
  TRUST: '#f59e0b',
  CONFLICT: '#ef4444',
  CONTROL_RESOURCE: '#8b5cf6',
  INFORMAL_MEMBER: '#14b8a6',
  OWNER: '#6366f1',
  HAS_ROLE: '#cbd5e1',
  BELONGS_TO: '#cbd5e1',
  WORKS_ON: '#f59e0b',
  HAS_KNOWLEDGE: '#ec4899',
  INVOLVED_IN: '#94a3b8',
}

function nodeRadius(node) {
  if (node.type === 'Person') {
    const inf = Number(node.influence_score || 0)
    return 12 + inf / 12
  }
  if (node.type === 'Project' || node.type === 'InformalGroup') return 11
  return 9
}

export default function ForceGraph({ nodes, edges, selectedId, onSelect }) {
  const wrapRef = useRef(null)
  const simRef = useRef({ nodes: [], edges: [] })
  const [, setTick] = useState(0)
  const [transform, setTransform] = useState({ x: 0, y: 0, k: 1 })
  const dragRef = useRef(null)
  const panRef = useRef(null)

  const layoutKey = useMemo(
    () => nodes.map((n) => n.id).sort().join('|') + '#' + edges.length,
    [nodes, edges],
  )

  useEffect(() => {
    const el = wrapRef.current
    const w = el?.clientWidth || 800
    const h = el?.clientHeight || 560
    const prev = Object.fromEntries((simRef.current.nodes || []).map((n) => [n.id, n]))
    const cx = w / 2
    const cy = h / 2
    const placed = nodes.map((n, i) => {
      const old = prev[n.id]
      const angle = (i / Math.max(nodes.length, 1)) * Math.PI * 2
      const ring = 80 + (i % 6) * 28
      return {
        ...n,
        x: old?.x ?? cx + Math.cos(angle) * ring,
        y: old?.y ?? cy + Math.sin(angle) * ring,
        vx: 0,
        vy: 0,
        r: nodeRadius(n),
      }
    })
    simRef.current = {
      nodes: placed,
      edges: edges.map((e) => ({
        ...e,
        strength: Number(e.properties?.strength || 0.4),
      })),
    }
  }, [layoutKey, nodes, edges])

  useEffect(() => {
    let raf
    let settled = false
    const step = () => {
      const { nodes: ns, edges: es } = simRef.current
      if (!ns.length) {
        raf = requestAnimationFrame(step)
        return
      }
      if (settled && !dragRef.current) {
        raf = requestAnimationFrame(step)
        return
      }
      const el = wrapRef.current
      const w = el?.clientWidth || 800
      const h = el?.clientHeight || 560
      const cx = w / 2
      const cy = h / 2

      for (let i = 0; i < ns.length; i++) {
        for (let j = i + 1; j < ns.length; j++) {
          const a = ns[i]
          const b = ns[j]
          let dx = a.x - b.x
          let dy = a.y - b.y
          let dist = Math.hypot(dx, dy) || 0.1
          const minDist = a.r + b.r + 18
          const force = 900 / (dist * dist)
          const fx = (dx / dist) * force
          const fy = (dy / dist) * force
          a.vx += fx
          a.vy += fy
          b.vx -= fx
          b.vy -= fy
          if (dist < minDist) {
            const push = (minDist - dist) * 0.08
            a.vx += (dx / dist) * push
            a.vy += (dy / dist) * push
            b.vx -= (dx / dist) * push
            b.vy -= (dy / dist) * push
          }
        }
      }

      const byId = Object.fromEntries(ns.map((n) => [n.id, n]))
      for (const e of es) {
        const a = byId[e.source]
        const b = byId[e.target]
        if (!a || !b) continue
        const dx = b.x - a.x
        const dy = b.y - a.y
        const dist = Math.hypot(dx, dy) || 0.1
        const rest = 90 + (1 - e.strength) * 80
        const k = 0.012 + e.strength * 0.02
        const f = (dist - rest) * k
        const fx = (dx / dist) * f
        const fy = (dy / dist) * f
        a.vx += fx
        a.vy += fy
        b.vx -= fx
        b.vy -= fy
      }

      for (const n of ns) {
        if (dragRef.current?.id === n.id) continue
        n.vx += (cx - n.x) * 0.008
        n.vy += (cy - n.y) * 0.008
        n.vx *= 0.82
        n.vy *= 0.82
        n.x += n.vx
        n.y += n.vy
      }
      const energy = ns.reduce((s, n) => s + n.vx * n.vx + n.vy * n.vy, 0)
      settled = energy < 0.015 && !dragRef.current
      setTick((t) => (t + 1) % 100000)
      raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [layoutKey])

  const simNodes = simRef.current.nodes
  const simEdges = simRef.current.edges
  const pos = Object.fromEntries(simNodes.map((n) => [n.id, n]))

  const onWheel = (e) => {
    e.preventDefault()
    const k = Math.min(2.4, Math.max(0.4, transform.k * (e.deltaY > 0 ? 0.92 : 1.08)))
    setTransform((t) => ({ ...t, k }))
  }

  const onMouseDownBg = (e) => {
    if (e.target.tagName !== 'svg' && e.target.getAttribute('data-bg') !== '1') return
    panRef.current = { x: e.clientX, y: e.clientY, ox: transform.x, oy: transform.y }
  }

  useEffect(() => {
    const move = (e) => {
      if (dragRef.current) {
        const el = wrapRef.current
        const rect = el.getBoundingClientRect()
        const x = (e.clientX - rect.left - transform.x) / transform.k
        const y = (e.clientY - rect.top - transform.y) / transform.k
        const n = simRef.current.nodes.find((x) => x.id === dragRef.current.id)
        if (n) {
          n.x = x
          n.y = y
          n.vx = 0
          n.vy = 0
        }
      } else if (panRef.current) {
        setTransform((t) => ({
          ...t,
          x: panRef.current.ox + (e.clientX - panRef.current.x),
          y: panRef.current.oy + (e.clientY - panRef.current.y),
        }))
      }
    }
    const up = () => {
      dragRef.current = null
      panRef.current = null
    }
    window.addEventListener('mousemove', move)
    window.addEventListener('mouseup', up)
    return () => {
      window.removeEventListener('mousemove', move)
      window.removeEventListener('mouseup', up)
    }
  }, [transform.k, transform.x, transform.y])

  return (
    <div ref={wrapRef} className="w-full h-full min-h-[520px] relative overflow-hidden rounded-2xl bg-slate-950">
      <svg
        className="w-full h-full cursor-grab active:cursor-grabbing"
        onWheel={onWheel}
        onMouseDown={onMouseDownBg}
      >
        <rect width="100%" height="100%" fill="transparent" data-bg="1" />
        <g transform={`translate(${transform.x},${transform.y}) scale(${transform.k})`}>
          {simEdges.map((e) => {
            const a = pos[e.source]
            const b = pos[e.target]
            if (!a || !b) return null
            const color = REL_COLORS[e.relation] || '#64748b'
            const w = 0.6 + (e.strength || 0.3) * 3.2
            const active = selectedId && (e.source === selectedId || e.target === selectedId)
            return (
              <line
                key={e.id || `${e.source}|${e.relation}|${e.target}`}
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke={color}
                strokeWidth={w}
                strokeOpacity={active ? 0.95 : 0.35}
              />
            )
          })}
          {simNodes.map((n) => {
            const color = TYPE_COLORS[n.type] || '#64748b'
            const selected = n.id === selectedId
            return (
              <g
                key={n.id}
                transform={`translate(${n.x},${n.y})`}
                className="cursor-pointer"
                onMouseDown={(e) => {
                  e.stopPropagation()
                  dragRef.current = { id: n.id }
                  onSelect?.(n)
                }}
              >
                {selected && (
                  <circle r={n.r + 6} fill="none" stroke="#fff" strokeWidth="1.5" opacity="0.7" />
                )}
                <circle r={n.r} fill={color} stroke="#0f172a" strokeWidth="1.5" />
                <text
                  y={n.r + 12}
                  textAnchor="middle"
                  fill="#e2e8f0"
                  fontSize="10"
                  fontWeight={selected ? 700 : 500}
                >
                  {n.name}
                </text>
              </g>
            )
          })}
        </g>
      </svg>
      {!nodes.length && (
        <div className="absolute inset-0 flex items-center justify-center text-slate-500 text-sm">
          暂无图谱节点
        </div>
      )}
    </div>
  )
}

export { TYPE_COLORS, REL_COLORS }
