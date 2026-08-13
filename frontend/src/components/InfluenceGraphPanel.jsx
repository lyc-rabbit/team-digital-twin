import React, { useEffect, useMemo, useRef, useState } from 'react'
import {
  Network, RefreshCw, Loader2, Sparkles, AlertTriangle,
  Users, Trophy, GitBranch, ShieldAlert, X, FileText,
} from 'lucide-react'
import { api } from '../api/client.js'
import ForceGraph, { TYPE_COLORS, REL_COLORS } from './ForceGraph.jsx'

const TABS = [
  { id: 'graph', label: '图谱', icon: GitBranch },
  { id: 'rank', label: '影响力', icon: Trophy },
  { id: 'community', label: '组织圈层', icon: Users },
  { id: 'risk', label: '风险', icon: ShieldAlert },
  { id: 'promo', label: '晋升画像', icon: Sparkles },
]

const REL_LABELS = {
  REPORT_TO: '汇报',
  COLLABORATE_WITH: '协作',
  MENTOR: '培养',
  TRUST: '信任',
  CONFLICT: '冲突',
  CONTROL_RESOURCE: '资源控制',
  INFORMAL_MEMBER: '非正式组织',
  OWNER: '负责',
  HAS_ROLE: '担任角色',
  BELONGS_TO: '隶属',
  WORKS_ON: '参与项目',
  HAS_KNOWLEDGE: '掌握知识',
  INVOLVED_IN: '参与事件',
}

const TYPE_LABELS = {
  Person: '人员',
  Role: '角色',
  Department: '部门',
  Project: '项目',
  Resource: '资源',
  Knowledge: '知识',
  Event: '事件',
  InformalGroup: '非正式组织',
}

const DEFAULT_TYPES = ['Person', 'Project', 'InformalGroup', 'Resource', 'Department']
const DEFAULT_RELS = [
  'REPORT_TO', 'COLLABORATE_WITH', 'MENTOR', 'TRUST', 'CONFLICT',
  'CONTROL_RESOURCE', 'INFORMAL_MEMBER', 'OWNER', 'WORKS_ON',
]

export default function InfluenceGraphPanel({ members }) {
  const [tab, setTab] = useState('graph')
  const [graph, setGraph] = useState({ nodes: [], edges: [], status: null })
  const [ranking, setRanking] = useState([])
  const [community, setCommunity] = useState(null)
  const [risks, setRisks] = useState(null)
  const [loading, setLoading] = useState(true)
  const [rebuilding, setRebuilding] = useState(false)
  const [error, setError] = useState(null)
  const [selected, setSelected] = useState(null)
  const [profile, setProfile] = useState(null)
  const [promoId, setPromoId] = useState('')
  const [types, setTypes] = useState(DEFAULT_TYPES)
  const [rels, setRels] = useState(DEFAULT_RELS)
  const [extractOpen, setExtractOpen] = useState(false)
  const [extractText, setExtractText] = useState('')
  const [extracting, setExtracting] = useState(false)
  const [extractResult, setExtractResult] = useState(null)
  const mountedRef = useRef(true)

  const loadAll = async () => {
    const [g, rank, comm, risk] = await Promise.all([
      api.getOigGraph(),
      api.getOigInfluenceRanking(),
      api.getOigCommunity(),
      api.getOigRisk(),
    ])
    if (!mountedRef.current) return
    setGraph(g)
    setRanking(rank.ranking || [])
    setCommunity(comm)
    setRisks(risk)
    const persons = (g.nodes || []).filter((n) => n.type === 'Person')
    if (!promoId && persons[0]) setPromoId(persons[0].id)
  }

  useEffect(() => {
    mountedRef.current = true
    loadAll()
      .catch((err) => mountedRef.current && setError(err.message || '加载失败'))
      .finally(() => mountedRef.current && setLoading(false))
    return () => { mountedRef.current = false }
  }, [])

  const visibleNodes = useMemo(
    () => (graph.nodes || []).filter((n) => types.includes(n.type)),
    [graph.nodes, types],
  )
  const visibleIds = useMemo(() => new Set(visibleNodes.map((n) => n.id)), [visibleNodes])
  const visibleEdges = useMemo(
    () => (graph.edges || []).filter(
      (e) => rels.includes(e.relation) && visibleIds.has(e.source) && visibleIds.has(e.target),
    ),
    [graph.edges, rels, visibleIds],
  )

  const handleRebuild = async () => {
    setRebuilding(true)
    setError(null)
    try {
      await api.rebuildOigGraph()
      await loadAll()
    } catch (err) {
      setError(err.message || '重建失败')
    } finally {
      if (mountedRef.current) setRebuilding(false)
    }
  }

  const handleSelect = async (node) => {
    setSelected(node)
    if (node?.type === 'Person') {
      setPromoId(node.id)
      try {
        const p = await api.getOigLeadership(node.id)
        if (mountedRef.current) setProfile(p)
      } catch {
        if (mountedRef.current) setProfile(null)
      }
    } else {
      setProfile(null)
    }
  }

  const handleExtract = async () => {
    if (!extractText.trim()) return
    setExtracting(true)
    setExtractResult(null)
    try {
      const res = await api.extractOig(extractText.trim(), 'document')
      setExtractResult(res)
      await loadAll()
    } catch (err) {
      setExtractResult({ error: err.message })
    } finally {
      setExtracting(false)
    }
  }

  const loadPromo = async (id) => {
    setPromoId(id)
    if (!id) return
    try {
      const p = await api.getOigLeadership(id)
      setProfile(p)
      const node = (graph.nodes || []).find((n) => n.id === id)
      if (node) setSelected(node)
    } catch (err) {
      setError(err.message)
    }
  }

  const status = graph.status || {}
  const stats = status.stats || {}
  const neoOk = status.neo4j_connected

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-slate-400 text-sm">
        加载组织影响力图谱...
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col p-6 max-w-[1600px] mx-auto w-full fade-in">
      <div className="flex items-start justify-between gap-4 mb-4">
        <div>
          <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
            <Network size={20} className="text-brand-600" />
            组织影响力图谱
            <span className="text-[10px] font-semibold tracking-wide text-brand-600 bg-brand-50 px-1.5 py-0.5 rounded">
              OIG
            </span>
          </h2>
          <p className="text-sm text-slate-500 mt-1">
            人员 · 岗位 · 项目 · 资源 · 知识 · 事件的动态影响关系 · 晋升推演计算基础
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => { setExtractOpen(true); setExtractResult(null) }}
            className="flex items-center gap-1.5 text-sm font-medium text-slate-600 bg-white border border-slate-200 hover:bg-slate-50 px-3 py-2 rounded-lg"
          >
            <FileText size={14} />
            从文档抽取
          </button>
          <button
            onClick={handleRebuild}
            disabled={rebuilding}
            className="flex items-center gap-1.5 text-sm font-medium text-white bg-brand-600 hover:bg-brand-700 disabled:opacity-50 px-3.5 py-2 rounded-lg"
          >
            {rebuilding ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}
            {rebuilding ? '重建中...' : '重建图谱'}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-3 mb-4">
        <StatCard label="节点" value={stats.node_count ?? 0} hint={formatCounts(stats.nodes_by_type)} />
        <StatCard label="关系" value={stats.edge_count ?? 0} hint={formatCounts(stats.edges_by_relation, REL_LABELS)} />
        <StatCard
          label="图存储"
          value={status.primary === 'neo4j' || neoOk ? 'Neo4j 主存' : 'SQLite 兜底'}
          hint={
            neoOk
              ? '读写与计算走 Neo4j，SQLite 作离线兜底'
              : (status.neo4j_configured
                ? `Neo4j 未连通，已降级 SQLite：${status.neo4j_error || ''}`
                : '未配置 Neo4j，当前使用 SQLite 兜底')
          }
          accent={neoOk ? 'text-emerald-600' : 'text-amber-700'}
        />
        <StatCard
          label="高风险"
          value={risks?.summary?.high ?? 0}
          hint={`中风险 ${risks?.summary?.medium ?? 0} · 共 ${risks?.summary?.count ?? 0} 项`}
          accent="text-amber-600"
        />
      </div>

      {error && (
        <div className="mb-3 text-xs bg-red-50 text-red-700 border border-red-100 rounded-lg px-3 py-2">
          {error}
        </div>
      )}

      <div className="flex gap-1 mb-3 bg-white border border-slate-100 rounded-xl p-1 w-fit">
        {TABS.map((t) => {
          const Icon = t.icon
          const active = tab === t.id
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                active ? 'bg-brand-600 text-white' : 'text-slate-500 hover:bg-slate-50'
              }`}
            >
              <Icon size={14} />
              {t.label}
            </button>
          )
        })}
      </div>

      <div className="flex-1 min-h-0">
        {tab === 'graph' && (
          <div className="h-full grid grid-cols-1 xl:grid-cols-[1fr_320px] gap-4">
            <ForceGraph
              nodes={visibleNodes}
              edges={visibleEdges}
              selectedId={selected?.id}
              onSelect={handleSelect}
            />
            <aside className="bg-white rounded-2xl border border-slate-100 shadow-sm p-4 overflow-y-auto space-y-4">
              <div>
                <div className="text-xs font-bold text-slate-700 mb-2">节点类型</div>
                <div className="flex flex-wrap gap-1.5">
                  {Object.keys(TYPE_LABELS).map((t) => (
                    <FilterChip
                      key={t}
                      active={types.includes(t)}
                      color={TYPE_COLORS[t]}
                      label={TYPE_LABELS[t]}
                      onClick={() => setTypes((prev) => toggle(prev, t))}
                    />
                  ))}
                </div>
              </div>
              <div>
                <div className="text-xs font-bold text-slate-700 mb-2">关系</div>
                <div className="flex flex-wrap gap-1.5">
                  {Object.keys(REL_LABELS).map((r) => (
                    <FilterChip
                      key={r}
                      active={rels.includes(r)}
                      color={REL_COLORS[r]}
                      label={REL_LABELS[r]}
                      onClick={() => setRels((prev) => toggle(prev, r))}
                    />
                  ))}
                </div>
              </div>
              {selected ? (
                <NodeDetail node={selected} edges={graph.edges} nodes={graph.nodes} profile={profile} />
              ) : (
                <p className="text-xs text-slate-400">点击节点查看关系与晋升画像。节点大小 = 影响力，边粗 = 关系强度。</p>
              )}
            </aside>
          </div>
        )}

        {tab === 'rank' && <RankingView ranking={ranking} onPick={loadPromo} />}
        {tab === 'community' && <CommunityView data={community} />}
        {tab === 'risk' && <RiskView data={risks} />}
        {tab === 'promo' && (
          <PromoView
            members={(graph.nodes || []).filter((n) => n.type === 'Person')}
            promoId={promoId}
            profile={profile}
            onPick={loadPromo}
          />
        )}
      </div>

      {extractOpen && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl w-full max-w-xl p-5 shadow-xl">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-bold text-slate-800">LLM 关系抽取</h3>
              <button onClick={() => setExtractOpen(false)} className="text-slate-400 hover:text-slate-600">
                <X size={16} />
              </button>
            </div>
            <p className="text-xs text-slate-500 mb-2">
              粘贴邮件、会议纪要、周报或日报。系统将抽取人员 / 项目 / 事件关系并写入图谱。
            </p>
            <textarea
              value={extractText}
              onChange={(e) => setExtractText(e.target.value)}
              rows={6}
              className="w-full text-sm border border-slate-200 rounded-xl p-3 outline-none focus:border-brand-400"
              placeholder="例如：张三帮助李四解决 Agent 部署问题，两人共同负责 AI 客服二期。"
            />
            <div className="flex justify-end mt-3">
              <button
                onClick={handleExtract}
                disabled={extracting || !extractText.trim()}
                className="flex items-center gap-1.5 text-sm font-medium text-white bg-brand-600 hover:bg-brand-700 disabled:opacity-50 px-3.5 py-2 rounded-lg"
              >
                {extracting ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
                抽取并写入
              </button>
            </div>
            {extractResult && (
              <div className="mt-3 text-xs bg-slate-50 rounded-xl p-3 max-h-48 overflow-y-auto">
                {extractResult.error ? (
                  <span className="text-red-600">{extractResult.error}</span>
                ) : (
                  <>
                    <div className="text-slate-500 mb-1">
                      写入节点 {extractResult.applied?.nodes ?? 0} · 关系 {extractResult.applied?.edges ?? 0}
                      {extractResult.degraded ? ' · 降级规则抽取' : ''}
                    </div>
                    {(extractResult.extraction?.relations || []).map((r, i) => (
                      <div key={i} className="text-slate-700">
                        {r.source} —{r.relation}→ {r.target}
                        <span className="text-slate-400"> ({Math.round((r.confidence || 0) * 100)}%)</span>
                      </div>
                    ))}
                    {!(extractResult.extraction?.relations || []).length && (
                      <div className="text-slate-400">未识别到可用关系</div>
                    )}
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function toggle(list, item) {
  return list.includes(item) ? list.filter((x) => x !== item) : [...list, item]
}

function formatCounts(obj, labels) {
  if (!obj || !Object.keys(obj).length) return '暂无'
  return Object.entries(obj)
    .slice(0, 4)
    .map(([k, v]) => `${labels?.[k] || TYPE_LABELS[k] || k} ${v}`)
    .join(' · ')
}

function StatCard({ label, value, hint, accent }) {
  return (
    <div className="bg-white rounded-2xl p-4 shadow-sm border border-slate-100">
      <div className="text-[11px] text-slate-500 mb-1">{label}</div>
      <div className={`text-2xl font-bold ${accent || 'text-slate-800'}`}>{value}</div>
      {hint && <div className="text-[11px] text-slate-400 mt-1 truncate" title={hint}>{hint}</div>}
    </div>
  )
}

function FilterChip({ active, color, label, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`text-[11px] px-2 py-0.5 rounded-full border transition-colors ${
        active ? 'text-white border-transparent' : 'text-slate-500 border-slate-200 bg-white'
      }`}
      style={active ? { background: color } : undefined}
    >
      {label}
    </button>
  )
}

function NodeDetail({ node, edges, nodes, profile }) {
  const byId = Object.fromEntries((nodes || []).map((n) => [n.id, n]))
  const related = (edges || []).filter((e) => e.source === node.id || e.target === node.id)
  return (
    <div className="space-y-3">
      <div>
        <div className="text-xs font-bold text-slate-800">{node.name}</div>
        <div className="text-[11px] text-slate-400">
          {TYPE_LABELS[node.type] || node.type}
          {node.position ? ` · ${node.position}` : ''}
          {node.department ? ` · ${node.department}` : ''}
        </div>
      </div>
      {node.type === 'Person' && (
        <div className="grid grid-cols-2 gap-2">
          <MiniMetric label="影响力" value={node.influence_score ?? profile?.influence ?? 0} />
          <MiniMetric label="领导力" value={profile?.leadership_score ?? node.leadership_score ?? '-'} />
        </div>
      )}
      {!!(node.skills || []).length && (
        <div className="flex flex-wrap gap-1">
          {node.skills.map((s) => (
            <span key={s} className="text-[10px] bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded">{s}</span>
          ))}
        </div>
      )}
      <div>
        <div className="text-[11px] font-bold text-slate-600 mb-1">关系 {related.length}</div>
        <div className="space-y-1 max-h-56 overflow-y-auto">
          {related.slice(0, 20).map((e) => {
            const otherId = e.source === node.id ? e.target : e.source
            const other = byId[otherId]
            return (
              <div key={e.id} className="text-[11px] text-slate-600 flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: REL_COLORS[e.relation] }} />
                <span className="text-slate-400">{REL_LABELS[e.relation] || e.relation}</span>
                <span className="truncate">{other?.name || otherId}</span>
                <span className="ml-auto text-slate-400">{Math.round((e.properties?.strength || 0) * 100)}</span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

function MiniMetric({ label, value }) {
  return (
    <div className="bg-slate-50 rounded-lg px-2 py-1.5">
      <div className="text-[10px] text-slate-400">{label}</div>
      <div className="text-sm font-bold text-slate-800">{value}</div>
    </div>
  )
}

function RankingView({ ranking, onPick }) {
  if (!ranking?.length) {
    return <Empty hint="暂无影响力排名。请先添加成员并重建图谱。" />
  }
  return (
    <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-slate-50 text-[11px] text-slate-500">
          <tr>
            <th className="text-left font-medium px-4 py-2">排名</th>
            <th className="text-left font-medium px-4 py-2">人员</th>
            <th className="text-right font-medium px-4 py-2">影响力</th>
            <th className="text-right font-medium px-4 py-2">连接数</th>
            <th className="text-right font-medium px-4 py-2">Degree</th>
            <th className="text-right font-medium px-4 py-2">Betweenness</th>
            <th className="text-right font-medium px-4 py-2">PageRank</th>
          </tr>
        </thead>
        <tbody>
          {ranking.map((r) => (
            <tr
              key={r.id}
              className="border-t border-slate-50 hover:bg-brand-50/40 cursor-pointer"
              onClick={() => onPick(r.id)}
            >
              <td className="px-4 py-2.5 font-bold text-slate-400">{r.rank}</td>
              <td className="px-4 py-2.5 font-medium text-slate-800">{r.name}</td>
              <td className="px-4 py-2.5 text-right font-bold text-brand-600">{r.influence_score}</td>
              <td className="px-4 py-2.5 text-right text-slate-600">{r.connections}</td>
              <td className="px-4 py-2.5 text-right text-slate-500">{r.degree}</td>
              <td className="px-4 py-2.5 text-right text-slate-500">{r.betweenness}</td>
              <td className="px-4 py-2.5 text-right text-slate-500">{r.pagerank}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function CommunityView({ data }) {
  const communities = data?.communities || []
  const holes = data?.structural_holes || []
  if (!communities.length && !holes.length) {
    return <Empty hint="暂无圈层数据。协作关系积累后将自动发现社群。" />
  }
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div className="space-y-3">
        <h3 className="text-sm font-bold text-slate-800">Louvain 社群</h3>
        {communities.map((c) => (
          <div key={c.id} className="bg-white rounded-2xl border border-slate-100 p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="font-semibold text-slate-800 text-sm">{c.name}</span>
              <span className="text-[11px] text-slate-400">{c.size} 人</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {(c.members || []).map((m) => (
                <span key={m.id} className="text-[11px] bg-teal-50 text-teal-700 px-2 py-0.5 rounded-full">
                  {m.name}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
      <div className="space-y-3">
        <h3 className="text-sm font-bold text-slate-800">结构洞 · 关键连接人</h3>
        {holes.map((h) => (
          <div key={h.id} className="bg-white rounded-2xl border border-slate-100 p-4">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-slate-800 text-sm">{h.name}</span>
              <span className="text-sm font-bold text-brand-600">{h.hole_score}</span>
            </div>
            <div className="text-[11px] text-slate-400 mt-1">
              约束系数 {h.constraint} · 度数 {h.degree}
            </div>
            {h.bridges?.length > 0 && (
              <div className="text-[11px] text-slate-600 mt-2">
                桥接：{h.bridges.slice(0, 4).map((b) => `${b.from}↔${b.to}`).join('、')}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function RiskView({ data }) {
  const items = data?.items || []
  if (!items.length) return <Empty hint="未发现显著组织风险。" />
  return (
    <div className="space-y-3">
      {items.map((r) => (
        <div key={r.id} className="bg-white rounded-2xl border border-slate-100 p-4 flex gap-3">
          <div className={`mt-0.5 ${
            r.level === 'high' ? 'text-red-500' : r.level === 'medium' ? 'text-amber-500' : 'text-slate-400'
          }`}>
            <AlertTriangle size={18} />
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-slate-800 text-sm">{r.title}</span>
              <span className="text-[10px] uppercase tracking-wide text-slate-400">{r.type}</span>
              <span className="ml-auto text-sm font-bold text-slate-700">{r.score}</span>
            </div>
            <p className="text-xs text-slate-500 mt-1">{r.detail}</p>
          </div>
        </div>
      ))}
    </div>
  )
}

function PromoView({ members, promoId, profile, onPick }) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-[240px_1fr] gap-4">
      <div className="bg-white rounded-2xl border border-slate-100 p-3 space-y-1 overflow-y-auto max-h-[640px]">
        {members.map((m) => (
          <button
            key={m.id}
            onClick={() => onPick(m.id)}
            className={`w-full text-left px-3 py-2 rounded-lg text-sm ${
              promoId === m.id ? 'bg-brand-50 text-brand-700 font-semibold' : 'hover:bg-slate-50 text-slate-700'
            }`}
          >
            {m.name}
            <span className="block text-[10px] font-normal text-slate-400">{m.position || m.id}</span>
          </button>
        ))}
        {!members.length && <p className="text-xs text-slate-400 p-2">暂无人员节点</p>}
      </div>
      <div className="bg-white rounded-2xl border border-slate-100 p-6">
        {!profile ? (
          <p className="text-sm text-slate-400">选择左侧人员查看晋升画像。</p>
        ) : (
          <div className="space-y-5">
            <div>
              <h3 className="text-lg font-bold text-slate-800">{profile.person}</h3>
              <p className="text-xs text-slate-400 mt-1">{profile.formula}</p>
            </div>
            <div className="flex items-end gap-6">
              <div>
                <div className="text-[11px] text-slate-400">Leadership Score</div>
                <div className="text-4xl font-bold text-brand-600">{profile.leadership_score}</div>
              </div>
            </div>
            <div className="space-y-3">
              {[
                ['组织影响力', profile.influence, 'bg-brand-500'],
                ['能力', profile.capability, 'bg-indigo-400'],
                ['业绩', profile.performance, 'bg-sky-500'],
                ['团队认可 / 信任', profile.trust, 'bg-amber-500'],
                ['资源控制', profile.resource_control, 'bg-emerald-500'],
                ['冲突风险', profile.conflict_risk, 'bg-red-500'],
              ].map(([label, val, bar]) => (
                <div key={label}>
                  <div className="flex justify-between text-xs text-slate-600 mb-1">
                    <span>{label}</span>
                    <span className="font-semibold">{val}</span>
                  </div>
                  <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                    <div className={`h-full ${bar}`} style={{ width: `${Math.min(100, val || 0)}%` }} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function Empty({ hint }) {
  return (
    <div className="bg-white rounded-2xl border border-slate-100 py-16 text-center text-sm text-slate-400">
      {hint}
    </div>
  )
}
