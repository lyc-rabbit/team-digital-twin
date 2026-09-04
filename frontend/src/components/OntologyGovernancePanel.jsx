import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Check, GitFork, Loader2, RefreshCw, Undo2, X, AlertTriangle, Pause, Trash2, Eye,
} from 'lucide-react'
import { api } from '../api/client.js'
import { beijingDateTimeLocal, TZ_LABEL } from '../utils/beijingTime.js'
import { ConstraintRulesPanel, PropertySchemaPanel, RelationSchemaPanel } from './OntologySchemaEditors.jsx'

const TABS = [
  { id: 'analyze', label: '语义分析' },
  { id: 'workitems', label: '待确认工单' },
  { id: 'types', label: '类型体系' },
  { id: 'properties', label: '属性定义' },
  { id: 'relations', label: '关系定义' },
  { id: 'constraints', label: '约束规则' },
  { id: 'history', label: '回滚' },
]

const PROBLEM_TITLE = {
  CLASS_INSTANCE_MIX: '类别与实例混在同一 Resource 类型',
  FLAT_RESOURCE_FAMILY: '同族资源可能未挂到总类下',
  WEAK_RELATION_SEMANTICS: '关系语义偏弱',
  NAME_TYPE_AMBIGUITY: '同名可能跨类型',
  INFER_RELATION: '推理候选边',
  MANUAL: '手动重分类',
  SCHEMA_VIOLATION: '属性不符合 Schema',
  RELATION_NOT_IN_SCHEMA: '关系不在 Schema',
  ILLEGAL_CROSS_DOMAIN_INFERENCE: '跨语义域非法推理',
  ILLEGAL_INFER_TRAIN_FROM_ROLE: '从汇报推出培养',
  ILLEGAL_INFER_CONTRIBUTE_FROM_OWNER: '从负责推出贡献',
  ILLEGAL_INFER_CAPABILITY_FROM_OWNER: '从负责推出能力',
}

const KIND_LABEL = {
  CLASSIFY_INSTANCE: '实例归类',
  HIERARCHY_REFACTOR: '层级重构',
  WEAK_RELATION: '弱语义增强',
  INFER_RELATION: '推理关系',
  TYPE_SCHEMA: '类型元数据',
  SUBTYPE_CLUSTER: '同族归类',
  SCHEMA_FIX: '属性约束',
  SCHEMA_RELATION: '关系约束',
  RETRACT_INFERENCE: '撤销非法推理',
}

const RELATION_FALLBACKS = [
  'BELONG_TO', 'BELONGS_TO', 'OWNER', 'CORE_MEMBER', 'PARTICIPATE', 'SUPPORT',
  'MANAGE', 'REPORT_TO', 'HAS_ROLE', 'SERVES_AS', 'RESPONSIBLE_FOR',
  'ACTOR_OF', 'INVOLVES', 'HAS_CAPABILITY', 'USES', 'USES_AI_CAPABILITY',
  'COLLABORATE', 'MENTOR', 'DEPEND_ON', 'DEPENDS_ON', 'OWNS_RESOURCE',
  'IS_A', 'PART_OF', 'PARENT_OF', 'WORKS_ON', 'INVOLVED_IN', 'HAS_RESOURCE',
  'ORG_RESPONSIBILITY', 'EXECUTION_RESPONSIBILITY', 'MANAGEMENT_RESPONSIBILITY',
  'REPORTING_RESPONSIBILITY', 'ACHIEVEMENT_OWNERSHIP', 'MADE_CONTRIBUTION',
  'CONTRIBUTES_TO', 'PERFORMED_TRAINING', 'TRAINING_TARGET',
]

function isEdgeWorkItem(kind) {
  return kind === 'INFER_RELATION' || kind === 'WEAK_RELATION' || kind === 'SCHEMA_RELATION' || kind === 'RETRACT_INFERENCE'
}

function collectRelationNames(schemaRelations, extras = []) {
  const names = new Set(RELATION_FALLBACKS)
  for (const r of schemaRelations || []) {
    if (r.name) names.add(r.name)
    for (const a of r.aliases || []) if (a) names.add(a)
  }
  for (const x of extras) if (x) names.add(x)
  return [...names].sort((a, b) => String(a).localeCompare(String(b)))
}

function flattenInstances(nodes, acc = []) {
  const seen = new Set(acc.map((x) => x.id))
  const walk = (list) => {
    for (const t of list || []) {
      for (const m of [...(t.members || []), ...(t.unclassified || [])]) {
        if (!m?.id || seen.has(m.id)) continue
        seen.add(m.id)
        acc.push({
          id: m.id,
          name: m.name || m.id,
          graph_type: m.graph_type || m.type || '',
          ontology_type: m.ontology_type || '',
          deletable: m.deletable !== false && (m.graph_type || m.type) !== 'Person',
          label: `${m.name || m.id}${m.graph_type ? ` · ${m.graph_type}` : ''}`,
        })
      }
      walk(t.children)
    }
  }
  walk(nodes)
  acc.sort((a, b) => String(a.label).localeCompare(String(b.label), 'zh'))
  return acc
}

function ensureInstanceOption(options, id, name, type) {
  if (!id) return options
  if ((options || []).some((o) => o.id === id)) return options
  return [
    {
      id,
      name: name || id,
      graph_type: type || '',
      label: `${name || id}${type ? ` · ${type}` : ''}`,
    },
    ...(options || []),
  ]
}

function instanceMeta(options, id, fallback = {}) {
  const hit = (options || []).find((o) => o.id === id)
  return {
    id,
    name: hit?.name || fallback.name || id || '',
    graph_type: hit?.graph_type || fallback.graph_type || fallback.type || '',
    deletable: hit ? hit.deletable : (fallback.graph_type || fallback.type) !== 'Person',
  }
}

function stripTypeFromBundle(bundle, typeId, typeName) {
  if (!bundle || !typeId) return bundle
  const walk = (nodes) => (nodes || [])
    .filter((n) => n.id !== typeId)
    .map((n) => ({ ...n, children: walk(n.children) }))
  const roots = walk(bundle.roots)
  return {
    ...bundle,
    roots,
    types: (bundle.types || []).filter((t) => t.id !== typeId),
    relations: (bundle.relations || []).filter((r) => r.source_type !== typeName && r.target_type !== typeName),
  }
}

function stripTypeFromSchema(schema, typeId, typeName) {
  if (!schema) return schema
  return {
    ...schema,
    types: (schema.types || []).filter((t) => t.id !== typeId && t.name !== typeName),
    relations: (schema.relations || []).filter((r) => r.source_type !== typeName && r.target_type !== typeName),
  }
}

function findTypeNode(nodes, id) {
  for (const n of nodes || []) {
    if (n.id === id) return n
    const hit = findTypeNode(n.children, id)
    if (hit) return hit
  }
  return null
}

function flattenTypeOptions(nodes, prefix = '') {
  const out = []
  for (const n of nodes || []) {
    const path = prefix ? `${prefix} / ${n.name}` : n.name
    out.push({ id: n.id, name: n.name, path })
    out.push(...flattenTypeOptions(n.children, path))
  }
  return out
}

function stripInstanceFromTypes(bundle, nodeId) {
  if (!bundle || !nodeId) return bundle
  const walk = (nodes) => (nodes || []).map((n) => {
    const members = (n.members || []).filter((m) => m.id !== nodeId)
    const unclassified = (n.unclassified || []).filter((m) => m.id !== nodeId)
    const children = walk(n.children)
    return {
      ...n,
      members,
      unclassified,
      children,
      member_count: members.length,
      unclassified_count: unclassified.length,
      deletable: children.length === 0 && members.length === 0 && unclassified.length === 0,
    }
  })
  const roots = walk(bundle.roots)
  return {
    ...bundle,
    roots,
    types: (bundle.types || []).map((t) => {
      const node = findTypeNode(roots, t.id)
      if (!node) return t
      return {
        ...t,
        member_count: (node.members || []).length,
        unclassified_count: (node.unclassified || []).length,
        deletable: node.deletable,
      }
    }),
  }
}

function dropInstanceFromType(node, nodeId) {
  if (!node) return node
  const members = (node.members || []).filter((m) => m.id !== nodeId)
  const unclassified = (node.unclassified || []).filter((m) => m.id !== nodeId)
  const children = node.children || []
  return {
    ...node,
    members,
    unclassified,
    deletable: children.length === 0 && members.length === 0 && unclassified.length === 0,
  }
}

function TypeTreeNode({ node, depth = 0, selectedId, onSelect, onDelete }) {
  const classified = (node.members || []).length
  const unclassified = (node.unclassified || []).length
  const count = classified + unclassified
  const canDelete = count === 0 && !(node.children || []).length
  return (
    <div className={depth ? 'ml-3 border-l border-slate-100 pl-2' : ''}>
      <div className={`flex items-center gap-1 rounded-lg ${selectedId === node.id ? 'bg-brand-50' : 'hover:bg-slate-50'}`}>
        <button
          type="button"
          onClick={() => onSelect(node)}
          className={`flex-1 min-w-0 text-left py-1.5 px-2 ${selectedId === node.id ? 'text-brand-800' : ''}`}
        >
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm font-semibold truncate">{node.name}</span>
            <span className="text-[10px] text-slate-400 shrink-0">{count}</span>
          </div>
        </button>
        {canDelete ? (
          <button
            type="button"
            title="删除空类型"
            onClick={(e) => {
              e.stopPropagation()
              onDelete(node)
            }}
            className="shrink-0 p-1 mr-1 text-slate-300 hover:text-red-600"
          >
            <Trash2 size={12} />
          </button>
        ) : null}
      </div>
      {(node.children || []).map((c) => (
        <TypeTreeNode key={c.id} node={c} depth={depth + 1} selectedId={selectedId} onSelect={onSelect} onDelete={onDelete} />
      ))}
    </div>
  )
}

function proposedOf(item, drafts) {
  return { ...(item.proposed || item.payload || {}), ...(drafts[item.id] || {}) }
}

function toDateInput(value) {
  if (!value) return ''
  const s = String(value).replace(' ', 'T')
  if (s.startsWith('0001') || s === '?' || s === '今') return ''
  return s.slice(0, 10)
}

function toDateTimeInput(value) {
  if (!value) return beijingDateTimeLocal()
  const s = String(value).replace(' ', 'T')
  if (s.startsWith('0001')) return beijingDateTimeLocal()
  if (s.length >= 16) return s.slice(0, 16)
  if (s.length >= 10) return `${s.slice(0, 10)}T00:00`
  return beijingDateTimeLocal()
}

function withTimes(proposed) {
  return {
    ...proposed,
    valid_from: toDateInput(proposed.valid_from),
    valid_to: toDateInput(proposed.valid_to),
    current_time: proposed.current_time || beijingDateTimeLocal(),
  }
}

function formatValidity(from, to) {
  const a = toDateInput(from)
  const b = toDateInput(to)
  if (!a && !b) return '不限 ~ 永久'
  return `${a || '不限'} ~ ${b || '永久'}`
}

function needsValidity(kind) {
  return kind === 'INFER_RELATION' || kind === 'WEAK_RELATION'
}

function workItemNodeIds(s) {
  const p = s?.proposed || s?.payload || {}
  const c = s?.current || {}
  const ids = []
  const add = (id) => {
    if (id && !ids.includes(id)) ids.push(id)
  }
  if (s?.object_type === 'node') add(s.object_id)
  add(p.node_id)
  add(p.child_id)
  add(p.parent_id)
  add(p.source)
  add(p.target)
  add(c.source)
  add(c.target)
  return ids
}

function formatDetailValue(value) {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value, null, 2)
    } catch {
      return String(value)
    }
  }
  return String(value)
}

function InstanceDetailModal({ nodeId, onClose, onOpenOther }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    setLoading(true)
    setError('')
    setData(null)
    api.getKgInstance(nodeId)
      .then((d) => { if (alive) setData(d) })
      .catch((e) => { if (alive) setError(e.message || '加载失败') })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [nodeId])

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/40 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-white rounded-2xl shadow-xl w-full max-w-2xl max-h-[85vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 px-5 py-4 border-b border-slate-100">
          <div className="min-w-0">
            <div className="text-sm font-bold text-slate-800 truncate">{data?.name || '实例详情'}</div>
            <div className="text-[11px] text-slate-400 mt-0.5">
              {data ? `${data.graph_type || '—'}${data.ontology_type ? ` · 本体 ${data.ontology_type}` : ''} · ${data.entity_status || ''}` : nodeId}
            </div>
          </div>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-700 p-1">
            <X size={16} />
          </button>
        </div>
        <div className="overflow-auto px-5 py-4 space-y-4 text-sm">
          {loading ? (
            <div className="text-slate-400 flex items-center gap-2 py-8 justify-center">
              <Loader2 size={14} className="animate-spin" />加载实例…
            </div>
          ) : null}
          {error ? <div className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</div> : null}
          {data ? (
            <>
              {data.description ? (
                <p className="text-xs text-slate-600 whitespace-pre-wrap bg-slate-50 rounded-lg px-3 py-2">{data.description}</p>
              ) : null}
              <div>
                <div className="text-xs font-semibold text-slate-700 mb-2">属性</div>
                <table className="w-full text-[11px] text-left">
                  <tbody>
                    {(data.schema_properties || []).map((p) => (
                      <tr key={p.name} className="border-b border-slate-50 align-top">
                        <td className="py-1.5 pr-3 text-slate-500 whitespace-nowrap w-28">
                          <div>{p.label || p.name}</div>
                          <div className="text-[10px] text-slate-300 font-mono">{p.name}</div>
                        </td>
                        <td className="py-1.5 text-slate-800 whitespace-pre-wrap break-all">{formatDetailValue(p.value ?? p.raw)}</td>
                      </tr>
                    ))}
                    {(data.extras || []).map((p) => (
                      <tr key={p.name} className="border-b border-slate-50 align-top">
                        <td className="py-1.5 pr-3 text-slate-400 whitespace-nowrap w-28 font-mono">{p.name}</td>
                        <td className="py-1.5 text-slate-600 whitespace-pre-wrap break-all">{formatDetailValue(p.value)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div>
                <div className="text-xs font-semibold text-slate-700 mb-2">关系 · {data.edge_count ?? (data.edges || []).length}</div>
                {(data.edges || []).length ? (
                  <div className="space-y-1 max-h-48 overflow-auto">
                    {(data.edges || []).map((e, idx) => (
                      <div key={e.id || `${e.relation}-${e.other_id}-${idx}`} className="text-[11px] text-slate-600 flex items-center gap-2 py-0.5">
                        <span className="text-slate-400 w-8 shrink-0">{e.direction === 'out' ? '→' : '←'}</span>
                        <span className="font-mono text-brand-700">{e.relation}</span>
                        <button
                          type="button"
                          className="text-left text-blue-600 hover:underline truncate"
                          onClick={() => e.other_id && onOpenOther?.(e.other_id)}
                        >
                          {e.other_name}
                        </button>
                        <span className="text-slate-400 shrink-0">{e.other_type}</span>
                      </div>
                    ))}
                  </div>
                ) : <p className="text-[11px] text-slate-400">没有相连的边。</p>}
              </div>
            </>
          ) : null}
        </div>
      </div>
    </div>
  )
}

function WorkItemActions({ s, proposed, current, busy, instanceOptions, onAccept, onReject, onDefer, onRetire, onDraft }) {
  const [retireId, setRetireId] = useState('')
  const open = s.status === 'open' || s.status === 'pending' || s.status === 'deferred'
  if (!open) return null
  const kind = s.suggestion_type
  if (kind === 'SCHEMA_FIX') {
    const enums = proposed.enum_values || []
    const canWrite = !!proposed.proposed_value || !!proposed.clear_forbidden
    const canRetire = current.graph_type !== 'Person'
    return (
      <div className="space-y-2">
        {enums.length ? (
          <label className="flex items-center gap-2 text-xs text-slate-600">
            规范为
            <select
              className="border rounded-lg px-2 py-1"
              value={proposed.proposed_value || ''}
              onChange={(e) => onDraft({ proposed_value: e.target.value })}
            >
              <option value="">选择枚举值</option>
              {enums.map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          </label>
        ) : null}
        <div className="flex gap-2 mt-1 flex-wrap">
          <button
            disabled={busy || !canWrite}
            onClick={onAccept}
            className="text-xs px-2 py-1 rounded-lg bg-emerald-50 text-emerald-700 flex items-center gap-1 whitespace-nowrap disabled:opacity-50"
          >
            <Check size={12} /> 规范属性
          </button>
          {canRetire ? (
            <button
              disabled={busy}
              onClick={() => onRetire(proposed.node_id || s.object_id)}
              className="text-xs px-2 py-1 rounded-lg bg-red-50 text-red-700 flex items-center gap-1 whitespace-nowrap disabled:opacity-50"
            >
              <Trash2 size={12} /> 下线实例
            </button>
          ) : null}
          <button
            disabled={busy}
            onClick={onReject}
            className="text-xs px-2 py-1 rounded-lg bg-slate-50 text-slate-500 flex items-center gap-1 whitespace-nowrap"
          >
            <X size={12} /> 关闭工单
          </button>
        </div>
      </div>
    )
  }
  if (isEdgeWorkItem(kind)) {
    const src = instanceMeta(instanceOptions, proposed.source, {
      name: proposed.source_name, graph_type: proposed.source_type || current.source_type,
    })
    const tgt = instanceMeta(instanceOptions, proposed.target, {
      name: proposed.target_name, graph_type: proposed.target_type || current.target_type,
    })
    const retireCandidates = [src, tgt].filter((x) => x.id && x.deletable)
      .filter((x, i, arr) => arr.findIndex((y) => y.id === x.id) === i)
    const picked = retireId && retireCandidates.some((x) => x.id === retireId)
      ? retireId
      : (retireCandidates.length === 1 ? retireCandidates[0].id : retireId)
    return (
      <div className="flex gap-2 mt-1 flex-wrap items-center">
        <button
          disabled={busy || !proposed.source || !proposed.target || !(proposed.proposed_relation || proposed.relation)}
          onClick={onAccept}
          className="text-xs px-2 py-1 rounded-lg bg-emerald-50 text-emerald-700 flex items-center gap-1 whitespace-nowrap disabled:opacity-50"
        >
          <Check size={12} /> 同意并写入
        </button>
        {retireCandidates.length ? (
          <>
            {retireCandidates.length > 1 ? (
              <select
                className="text-xs border rounded-lg px-2 py-1 max-w-[180px]"
                value={picked || ''}
                onChange={(e) => setRetireId(e.target.value)}
              >
                <option value="">选择要下线的实例</option>
                {retireCandidates.map((x) => (
                  <option key={x.id} value={x.id}>{x.name || x.id}</option>
                ))}
              </select>
            ) : null}
            <button
              disabled={busy || !picked}
              onClick={() => onRetire(picked)}
              className="text-xs px-2 py-1 rounded-lg bg-red-50 text-red-700 flex items-center gap-1 whitespace-nowrap disabled:opacity-50"
            >
              <Trash2 size={12} /> 下线实例
            </button>
          </>
        ) : null}
        <button
          disabled={busy}
          onClick={onReject}
          className="text-xs px-2 py-1 rounded-lg bg-slate-50 text-slate-500 flex items-center gap-1 whitespace-nowrap"
        >
          <X size={12} /> 关闭工单
        </button>
        {kind !== 'SCHEMA_RELATION' ? (
          <button
            disabled={busy}
            onClick={onDefer}
            className="text-xs px-2 py-1 rounded-lg bg-amber-50 text-amber-700 flex items-center gap-1 whitespace-nowrap"
          >
            <Pause size={12} /> 暂缓
          </button>
        ) : null}
      </div>
    )
  }
  return (
    <div className="flex gap-2 mt-1 flex-wrap">
      <button
        disabled={busy}
        onClick={onAccept}
        className="text-xs px-2 py-1 rounded-lg bg-emerald-50 text-emerald-700 flex items-center gap-1 whitespace-nowrap"
      >
        <Check size={12} /> 同意并写入
      </button>
      <button
        disabled={busy}
        onClick={onReject}
        className="text-xs px-2 py-1 rounded-lg bg-slate-50 text-slate-500 flex items-center gap-1 whitespace-nowrap"
      >
        <X size={12} /> 关闭工单
      </button>
      {(kind === 'CLASSIFY_INSTANCE' || kind === 'HIERARCHY_REFACTOR') ? (
        <button
          disabled={busy}
          onClick={onDefer}
          className="text-xs px-2 py-1 rounded-lg bg-amber-50 text-amber-700 flex items-center gap-1 whitespace-nowrap"
        >
          <Pause size={12} /> 暂缓
        </button>
      ) : null}
    </div>
  )
}

function stripValidityLine(reason) {
  return String(reason || '').replace(/\n?有效(?:期)?[:：][^\n]*/g, '').trim()
}

export default function OntologyGovernancePanel() {
  const [tab, setTab] = useState('analyze')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [overview, setOverview] = useState(null)
  const [analysis, setAnalysis] = useState(null)
  const [draft, setDraft] = useState(null)
  const [types, setTypes] = useState(null)
  const [inferred, setInferred] = useState([])
  const [rules, setRules] = useState([])
  const [workItems, setWorkItems] = useState([])
  const [workTotal, setWorkTotal] = useState(0)
  const [revisions, setRevisions] = useState([])
  const [newType, setNewType] = useState({ name: '', parent_id: '', description: '' })
  const [mergePair, setMergePair] = useState({ sourceId: '', targetId: '' })
  const [itemStatus, setItemStatus] = useState('open')
  const [problemCode, setProblemCode] = useState('')
  const [inferOpen, setInferOpen] = useState([])
  const [drafts, setDrafts] = useState({})
  const [selectedType, setSelectedType] = useState(null)
  const [typeForm, setTypeForm] = useState({ description: '', parent_id: '' })
  const [schemaBundle, setSchemaBundle] = useState(null)
  const [detailNodeId, setDetailNodeId] = useState(null)

  const load = useCallback(async (opts = {}) => {
    setError(null)
    const status = opts.status ?? itemStatus
    const code = opts.problemCode !== undefined ? opts.problemCode : problemCode
    const hideIds = opts.hideNodeIds || []
    const applyTypes = (raw) => {
      let next = raw
      for (const id of hideIds) next = stripInstanceFromTypes(next, id)
      setTypes(next)
      setSelectedType((prev) => (prev ? findTypeNode(next.roots, prev.id) || prev : prev))
      return next
    }
    const typesPromise = api.getKgTypes().then(applyTypes)
    const [ov, an, dr, , inf, ru, wi, rev, inferWi, schema] = await Promise.all([
      api.getKgOverview(),
      api.getKgAnalyze(),
      api.getKgOntologyDraft(),
      typesPromise,
      api.getKgInferred(),
      api.getKgRules(),
      api.getKgWorkItems({ status, problemCode: code, pageSize: 120 }),
      api.getKgRevisions(),
      api.getKgWorkItems({ status: 'open', problemCode: 'INFER_RELATION', pageSize: 80 }),
      api.getKgSchema().catch(() => null),
    ])
    setOverview(ov)
    setAnalysis(an)
    setDraft(dr)
    setInferred(inf.items || [])
    setRules(ru.items || [])
    setWorkItems(wi.items || [])
    setWorkTotal(wi.total ?? (wi.items || []).length)
    setRevisions(rev.items || [])
    setInferOpen(inferWi.items || [])
    if (schema) setSchemaBundle(schema)
  }, [itemStatus, problemCode])

  useEffect(() => {
    load().catch((e) => setError(e.message)).finally(() => setLoading(false))
  }, [load])

  const run = async (fn, loadOpts = {}) => {
    setBusy(true)
    setError(null)
    try {
      await fn()
      await load(loadOpts)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const retireInstance = (id) => {
    if (!window.confirm('确认下线该实例？会从图谱隐藏，重建时也不会再生成。不会物理删库。人员请到成员模块处理。')) return
    run(async () => {
      await api.retireKgInstance(id)
      setTypes((prev) => stripInstanceFromTypes(prev, id))
      setSelectedType((prev) => dropInstanceFromType(prev, id))
    }, { hideNodeIds: [id] })
  }

  const typeOptions = useMemo(() => flattenTypeOptions(types?.roots || []), [types])
  const instanceOptions = useMemo(() => flattenInstances(types?.roots || []), [types])

  const openCount = overview?.open_work_items ?? workTotal

  const selectType = (node) => {
    setSelectedType(node)
    setTypeForm({
      description: node.description || '',
      parent_id: node.parent_id || '',
    })
  }

  const updateDraft = (id, patch) => {
    setDrafts((prev) => ({ ...prev, [id]: { ...(prev[id] || {}), ...patch } }))
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-slate-400 text-sm">
        <Loader2 size={16} className="animate-spin mr-2" />正在扫描当前图谱语义…
      </div>
    )
  }

  const problems = (analysis?.problems || []).filter((p) => (p.open_count == null ? p.count : p.open_count) > 0)
  const clusters = analysis?.clusters || []

  return (
    <div className="p-6 max-w-6xl mx-auto fade-in space-y-5">
      <div className="space-y-2">
        <div className="flex items-center justify-between gap-4">
          <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
            <GitFork size={20} className="text-brand-600" /> 本体治理
          </h2>
          <div className="flex gap-2 shrink-0">
            <button
              onClick={() => run(() => api.publishKgAnalyze())}
              disabled={busy}
              className="text-xs px-3 py-1.5 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 disabled:opacity-50 flex items-center gap-1 whitespace-nowrap"
            >
              {busy ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
              刷新分析
            </button>
            <button
              onClick={() => run(() => api.applyKgConfirmed())}
              disabled={busy}
              className="text-xs px-3 py-1.5 rounded-lg bg-brand-600 text-white hover:bg-brand-700 disabled:opacity-50 whitespace-nowrap"
            >
              应用已确认项
            </button>
          </div>
        </div>
        <p className="text-sm text-slate-500">
          类型体系管「有什么类」；属性定义管「类自身有哪些字段」；关系定义管「类之间怎么连」；约束规则管「什么事实才合法」。分析只生成工单，确认后才写图。
        </p>
      </div>

      {error && <div className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</div>}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="节点" value={analysis?.total_nodes ?? 0} />
        <Stat label="关系" value={analysis?.total_edges ?? 0} />
        <Stat label="待确认工单" value={openCount} />
        <Stat label="已确认推断" value={overview?.inferred ?? inferred.length} />
      </div>

      <div className="flex gap-1 bg-slate-50 rounded-xl p-1 w-fit flex-wrap">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`text-xs px-3 py-1.5 rounded-lg ${tab === t.id ? 'bg-white shadow-sm text-slate-800 font-semibold' : 'text-slate-500'}`}
          >
            {t.label}
            {t.id === 'workitems' && openCount ? ` (${openCount})` : ''}
          </button>
        ))}
      </div>

      {tab === 'analyze' && (
        <div className="space-y-4">
          <section className="bg-white rounded-2xl border border-slate-100 p-5">
            <h3 className="text-sm font-bold text-slate-800 mb-3">当前图谱语义问题</h3>
            {problems.length ? problems.map((p) => (
              <div key={p.code} className="flex gap-2 py-2 border-b border-slate-50 last:border-0 px-1">
                <AlertTriangle size={14} className="text-amber-500 mt-0.5 shrink-0" />
                <div>
                  <div className="text-sm text-slate-800">{PROBLEM_TITLE[p.code] || p.title}</div>
                  <div className="text-[11px] text-slate-500">
                    {p.detail} · {p.open_count != null ? p.open_count : p.count} 处待确认 ·{' '}
                    <button
                      type="button"
                      onClick={() => {
                        setProblemCode(p.code)
                        setItemStatus('open')
                        setTab('workitems')
                      }}
                      className="text-blue-600 hover:text-blue-700 hover:underline"
                    >
                      点此查看工单
                    </button>
                  </div>
                </div>
              </div>
            )) : <p className="text-xs text-slate-400">暂未发现待确认的语义问题。点「刷新分析」会生成待确认工单，不会自动改图。</p>}
          </section>
          <section className="bg-white rounded-2xl border border-slate-100 p-5">
            <h3 className="text-sm font-bold text-slate-800 mb-2">节点类型分布（图谱 type，只读）</h3>
            <div className="flex flex-wrap gap-2">
              {Object.entries(analysis?.types || {}).map(([k, v]) => (
                <span key={k} className="text-xs bg-slate-50 border border-slate-100 rounded-lg px-2 py-1">{k} · {v}</span>
              ))}
            </div>
          </section>
          <section className="bg-white rounded-2xl border border-slate-100 p-5">
            <h3 className="text-sm font-bold text-slate-800 mb-2">同族聚类（不合并实例）</h3>
            {clusters.length ? clusters.map((c) => (
              <div key={c.cluster} className="mb-3 last:mb-0">
                <div className="text-sm font-semibold text-slate-700">
                  {c.cluster} → {c.ontology_type}
                </div>
                <div className="text-[11px] text-slate-500 mt-1">
                  {(c.members || []).map((m) => m.name).join('、 ')}
                </div>
              </div>
            )) : <p className="text-xs text-slate-400">未发现可聚类的同后缀资源族。</p>}
          </section>
          {draft?.entityTypes?.length ? (
            <section className="bg-white rounded-2xl border border-slate-100 p-5">
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-sm font-bold text-slate-800">本体草稿预览</h3>
                <button
                  disabled={busy}
                  onClick={() => run(() => api.applyKgOntology())}
                  className="text-xs px-3 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 disabled:opacity-50"
                >
                  生成工单
                </button>
              </div>
              <p className="text-[11px] text-slate-400 mb-2">{draft.note} 不会整包写图。</p>
            </section>
          ) : null}
        </div>
      )}

      {tab === 'workitems' && (
        <section className="bg-white rounded-2xl border border-slate-100 p-5 space-y-3">
          <div className="flex flex-wrap gap-2">
            <select
              className="text-xs border rounded-lg px-2 py-1.5"
              value={itemStatus}
              onChange={(e) => setItemStatus(e.target.value)}
            >
              <option value="open">待确认</option>
              <option value="deferred">暂缓</option>
              <option value="accepted">已同意</option>
              <option value="rejected">已关闭</option>
              <option value="resolved">已自动关闭</option>
              <option value="all">全部</option>
            </select>
            <select
              className="text-xs border rounded-lg px-2 py-1.5"
              value={problemCode}
              onChange={(e) => setProblemCode(e.target.value)}
            >
              <option value="">全部问题</option>
              {Object.entries(PROBLEM_TITLE).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </div>
          {workItems.length ? workItems.map((s) => {
            const proposed = proposedOf(s, drafts)
            const current = s.current || {}
            const selectedTypeId = proposed.proposed_type_id
              || typeOptions.find((o) => o.name === (proposed.proposed_ontology_type || proposed.ontology_type))?.id
              || ''
            return (
              <div key={s.id} className="border border-slate-100 rounded-xl p-3 space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-sm font-semibold text-slate-800">{s.title || KIND_LABEL[s.suggestion_type]}</div>
                    <div className="text-[11px] text-slate-400 mt-0.5">
                      {KIND_LABEL[s.suggestion_type] || s.suggestion_type}
                      {s.problem_code ? ` · ${s.problem_code}` : ''}
                      {s.confidence != null ? ` · 置信 ${Math.round(s.confidence * 100)}%` : ''}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    {workItemNodeIds({ ...s, proposed }).map((nid) => (
                      <button
                        key={nid}
                        type="button"
                        onClick={() => setDetailNodeId(nid)}
                        className="text-[11px] px-2 py-0.5 rounded border border-slate-200 text-slate-600 hover:bg-slate-50 flex items-center gap-1 whitespace-nowrap"
                      >
                        <Eye size={11} /> {instanceMeta(instanceOptions, nid, {
                          name: nid === proposed.source ? proposed.source_name : nid === proposed.target ? proposed.target_name : '',
                        }).name || '实例详情'}
                      </button>
                    ))}
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-50 text-slate-500">{s.status}</span>
                  </div>
                </div>
                <p className="text-xs text-slate-600 whitespace-pre-wrap">{stripValidityLine(s.reason)}</p>
                {needsValidity(s.suggestion_type) ? (
                  <div className="text-[11px] text-slate-500">有效期：{formatValidity(proposed.valid_from, proposed.valid_to)}</div>
                ) : null}
                {s.suggestion_type === 'SCHEMA_FIX' ? (
                  <div className="text-[11px] text-slate-500">
                    {current.graph_type ? `图谱类型 ${current.graph_type} · ` : ''}
                    当前 {current.field}={String(current.value ?? '空')}
                  </div>
                ) : null}
                {s.suggestion_type === 'CLASSIFY_INSTANCE' || s.suggestion_type === 'HIERARCHY_REFACTOR' ? (
                  <div className="text-[11px] text-slate-500">
                    当前图谱：{current.graph_type || current.child || '—'}
                    {current.ontology_type ? ` / 本体 ${current.ontology_type}` : ''}
                  </div>
                ) : null}

                {s.suggestion_type === 'CLASSIFY_INSTANCE' || s.suggestion_type === 'HIERARCHY_REFACTOR' ? (
                  <label className="flex flex-col gap-1 text-xs text-slate-600">
                    <span>归属到类型树节点<span className="text-slate-400 ml-1">不改图谱 type</span></span>
                    <select
                      className="border rounded-lg px-2 py-1.5 max-w-full"
                      value={selectedTypeId}
                      disabled={s.status === 'accepted' || s.status === 'rejected'}
                      onChange={(e) => {
                        const opt = typeOptions.find((o) => o.id === e.target.value)
                        if (!opt) return
                        updateDraft(s.id, {
                          proposed_type_id: opt.id,
                          proposed_ontology_type: opt.name,
                        })
                      }}
                    >
                      <option value="">请选择左侧类型</option>
                      {typeOptions.map((o) => (
                        <option key={o.id} value={o.id}>{o.path}</option>
                      ))}
                    </select>
                  </label>
                ) : null}

                {isEdgeWorkItem(s.suggestion_type) ? (
                  <div className="grid grid-cols-1 sm:grid-cols-[1fr_minmax(140px,0.7fr)_1fr] gap-2 items-end">
                    <label className="flex flex-col gap-1 text-xs text-slate-600 min-w-0">
                      <span>起点实例</span>
                      <select
                        className="border rounded-lg px-2 py-1.5 w-full"
                        value={proposed.source || ''}
                        disabled={s.status === 'accepted' || s.status === 'rejected'}
                        onChange={(e) => {
                          const id = e.target.value
                          const meta = instanceMeta(instanceOptions, id)
                          updateDraft(s.id, { source: id, source_name: meta.name, source_type: meta.graph_type })
                        }}
                      >
                        <option value="">选择起点</option>
                        {ensureInstanceOption(instanceOptions, proposed.source, proposed.source_name, proposed.source_type).map((o) => (
                          <option key={o.id} value={o.id}>{o.label}</option>
                        ))}
                      </select>
                    </label>
                    <label className="flex flex-col gap-1 text-xs text-slate-600 min-w-0">
                      <span>建议关系</span>
                      <select
                        className="border rounded-lg px-2 py-1.5 w-full"
                        value={proposed.proposed_relation || proposed.relation || ''}
                        disabled={s.status === 'accepted' || s.status === 'rejected'}
                        onChange={(e) => {
                          const v = e.target.value
                          if (s.suggestion_type === 'WEAK_RELATION') updateDraft(s.id, { proposed_relation: v })
                          else updateDraft(s.id, { relation: v, action: 'write' })
                        }}
                      >
                        {collectRelationNames(
                          schemaBundle?.relations || types?.relations || [],
                          [proposed.proposed_relation, proposed.relation, proposed.current_relation, current.relation],
                        ).map((r) => <option key={r} value={r}>{r}</option>)}
                      </select>
                      {s.suggestion_type === 'WEAK_RELATION' ? (
                        <span className="text-[10px] text-slate-400">保留原 {proposed.current_relation || current.relation}</span>
                      ) : null}
                    </label>
                    <label className="flex flex-col gap-1 text-xs text-slate-600 min-w-0">
                      <span>终点实例</span>
                      <select
                        className="border rounded-lg px-2 py-1.5 w-full"
                        value={proposed.target || ''}
                        disabled={s.status === 'accepted' || s.status === 'rejected'}
                        onChange={(e) => {
                          const id = e.target.value
                          const meta = instanceMeta(instanceOptions, id)
                          updateDraft(s.id, { target: id, target_name: meta.name, target_type: meta.graph_type })
                        }}
                      >
                        <option value="">选择终点</option>
                        {ensureInstanceOption(instanceOptions, proposed.target, proposed.target_name, proposed.target_type).map((o) => (
                          <option key={o.id} value={o.id}>{o.label}</option>
                        ))}
                      </select>
                    </label>
                  </div>
                ) : null}

                {needsValidity(s.suggestion_type) ? (
                <div className="flex flex-wrap items-end gap-3 text-xs text-slate-600">
                  <label className="flex flex-col gap-1">
                    <span>有效期起（{TZ_LABEL}）</span>
                    <input
                      type="date"
                      className="border rounded-lg px-2 py-1"
                      disabled={s.status === 'accepted' || s.status === 'rejected'}
                      value={toDateInput(proposed.valid_from)}
                      onChange={(e) => updateDraft(s.id, { valid_from: e.target.value })}
                    />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span>有效期止（不填=永久）</span>
                    <input
                      type="date"
                      className="border rounded-lg px-2 py-1"
                      disabled={s.status === 'accepted' || s.status === 'rejected'}
                      value={toDateInput(proposed.valid_to)}
                      onChange={(e) => updateDraft(s.id, { valid_to: e.target.value })}
                    />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span>当前时间（{TZ_LABEL}）</span>
                    <input
                      type="datetime-local"
                      className="border rounded-lg px-2 py-1"
                      disabled={s.status === 'accepted' || s.status === 'rejected'}
                      value={toDateTimeInput(proposed.current_time)}
                      onChange={(e) => updateDraft(s.id, { current_time: e.target.value })}
                    />
                  </label>
                </div>
                ) : null}

                {s.status === 'accepted' && s.applied ? (
                  <div className="text-[11px] text-emerald-700 bg-emerald-50 rounded-lg px-2 py-1">
                    已应用
                    {s.applied.ontology_type ? ` ontology_type=${s.applied.ontology_type}` : ''}
                    {s.applied.graph_type ? `（type 仍为 ${s.applied.graph_type}）` : ''}
                    {s.applied.added ? ` · 新增 ${s.applied.added}` : ''}
                    {s.applied.kept ? ` · 保留 ${s.applied.kept}` : ''}
                    {(s.applied.added_edges || []).length ? ` · 边 ${(s.applied.added_edges || []).join(', ')}` : ''}
                  </div>
                ) : null}

                <WorkItemActions
                  s={s}
                  proposed={proposed}
                  current={current}
                  busy={busy}
                  instanceOptions={instanceOptions}
                  onDraft={(patch) => updateDraft(s.id, patch)}
                  onAccept={() => {
                    const payload = withTimes(proposedOf(s, drafts))
                    if (s.suggestion_type === 'SCHEMA_RELATION') payload.action = 'write'
                    return run(() => api.acceptKgWorkItem(s.id, payload))
                  }}
                  onReject={() => run(() => api.rejectKgWorkItem(s.id))}
                  onDefer={() => run(() => api.deferKgWorkItem(s.id))}
                  onRetire={(nid) => retireInstance(nid)}
                />
              </div>
            )
          }) : <p className="text-xs text-slate-400">没有匹配的工单。点「刷新分析」生成，确认前不会改图。</p>}
        </section>
      )}

      {tab === 'types' && (
        <div className="grid grid-cols-1 md:grid-cols-[240px_1fr] gap-4">
          <section className="bg-white rounded-2xl border border-slate-100 p-3">
            <div className="text-[11px] text-slate-400 px-2 mb-1">类型树 · 数字为实例数</div>
            {(types?.roots || []).map((r) => (
              <TypeTreeNode
                key={r.id}
                node={r}
                selectedId={selectedType?.id}
                onSelect={selectType}
                onDelete={(node) => run(async () => {
                  if (!window.confirm(`删除空类型「${node.name}」？不会删除图里的实例。`)) return
                  await api.deleteKgType(node.id)
                  setTypes((prev) => stripTypeFromBundle(prev, node.id, node.name))
                  setSchemaBundle((prev) => stripTypeFromSchema(prev, node.id, node.name))
                  if (selectedType?.id === node.id) setSelectedType(null)
                })}
              />
            ))}
          </section>
          <section className="bg-white rounded-2xl border border-slate-100 p-5 space-y-4">
            {selectedType ? (
              <>
                <div>
                  <div className="text-lg font-bold text-slate-800">{selectedType.name}</div>
                  <div className="text-[11px] text-slate-400">名称只读。改描述/父类直接保存到本体层，不改图实例 type。</div>
                </div>
                <label className="block text-xs text-slate-600">
                  描述
                  <textarea
                    className="mt-1 w-full text-sm border rounded-lg px-2 py-1.5 min-h-[72px]"
                    value={typeForm.description}
                    onChange={(e) => setTypeForm({ ...typeForm, description: e.target.value })}
                  />
                </label>
                <label className="block text-xs text-slate-600">
                  父类型
                  <select
                    className="mt-1 w-full text-sm border rounded-lg px-2 py-1.5"
                    value={typeForm.parent_id}
                    onChange={(e) => setTypeForm({ ...typeForm, parent_id: e.target.value })}
                  >
                    <option value="">无父类</option>
                    {(types?.types || []).filter((t) => t.id !== selectedType.id).map((t) => (
                      <option key={t.id} value={t.id}>{t.name}</option>
                    ))}
                  </select>
                </label>
                <button
                  disabled={busy}
                  onClick={() => run(() => api.updateKgType(selectedType.id, {
                    description: typeForm.description,
                    parent_id: typeForm.parent_id || null,
                  }).then((saved) => selectType({ ...selectedType, ...saved, members: selectedType.members, unclassified: selectedType.unclassified, children: selectedType.children })))}
                  className="text-xs px-3 py-1.5 rounded-lg bg-brand-600 text-white disabled:opacity-50"
                >
                  保存类型
                </button>
                <InstanceList
                  title="已归入本类型的图实例"
                  items={selectedType.members || []}
                  busy={busy}
                  onClassify={(id) => run(async () => {
                    await api.classifyKgInstance(id, {
                      typeId: selectedType.id,
                      ontologyType: selectedType.name,
                    })
                    setTab('workitems')
                    setItemStatus('open')
                    setProblemCode('')
                  })}
                  onDelete={retireInstance}
                  onDetail={setDetailNodeId}
                />
                <InstanceList
                  title="尚未标注本体类（按图谱 type 暂挂）"
                  items={selectedType.unclassified || []}
                  busy={busy}
                  onClassify={(id) => run(async () => {
                    await api.classifyKgInstance(id, {
                      typeId: selectedType.id,
                      ontologyType: selectedType.name,
                    })
                    setTab('workitems')
                    setItemStatus('open')
                    setProblemCode('')
                  })}
                  onDelete={retireInstance}
                  onDetail={setDetailNodeId}
                />
              </>
            ) : (
              <p className="text-xs text-slate-400">左侧选择一个本体类型。实例芯片不在树上，归类一律走工单。</p>
            )}

            <div className="border-t border-slate-100 pt-4 space-y-2">
              <div className="text-xs font-semibold text-slate-700">新增类型</div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                <input className="text-xs border rounded-lg px-2 py-1.5" placeholder="新类型名，如 VendorResource"
                  value={newType.name} onChange={(e) => setNewType({ ...newType, name: e.target.value })} />
                <select className="text-xs border rounded-lg px-2 py-1.5" value={newType.parent_id}
                  onChange={(e) => setNewType({ ...newType, parent_id: e.target.value })}>
                  <option value="">无父类</option>
                  {(types?.types || []).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
                <button
                  disabled={busy || !newType.name}
                  onClick={() => run(() => api.createKgType({
                    name: newType.name,
                    parent_id: newType.parent_id || null,
                    description: newType.description,
                  }).then(() => setNewType({ name: '', parent_id: '', description: '' })))}
                  className="text-xs px-3 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 disabled:opacity-50"
                >
                  新增类型
                </button>
              </div>
              <div className="text-xs font-semibold text-slate-700 pt-2">合并本体类型</div>
              <p className="text-[11px] text-slate-400">合并的是类型定义，不会把图里的人/事件合成一个节点。</p>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                <select className="text-xs border rounded-lg px-2 py-1.5" value={mergePair.sourceId}
                  onChange={(e) => setMergePair({ ...mergePair, sourceId: e.target.value })}>
                  <option value="">合并源类型</option>
                  {(types?.types || []).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
                <select className="text-xs border rounded-lg px-2 py-1.5" value={mergePair.targetId}
                  onChange={(e) => setMergePair({ ...mergePair, targetId: e.target.value })}>
                  <option value="">并入目标类型</option>
                  {(types?.types || []).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
                <button
                  disabled={busy || !mergePair.sourceId || !mergePair.targetId}
                  onClick={() => {
                    const src = (types?.types || []).find((t) => t.id === mergePair.sourceId)?.name
                    const tgt = (types?.types || []).find((t) => t.id === mergePair.targetId)?.name
                    if (!window.confirm(`合并本体类型 ${src} 到 ${tgt}？不会把图里的人/事件合成一个节点。`)) return
                    return run(() => api.mergeKgTypes(mergePair).then(() => {
                      setMergePair({ sourceId: '', targetId: '' })
                      setSelectedType(null)
                    }))
                  }}
                  className="text-xs px-3 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 disabled:opacity-50"
                >
                  合并本体类型
                </button>
              </div>
            </div>
          </section>
        </div>
      )}

      {tab === 'properties' && (
        <PropertySchemaPanel
          types={{ types: schemaBundle?.types || types?.types || [] }}
          selectedType={selectedType}
          onSelect={(t) => {
            const full = findTypeNode(types?.roots || [], t.id)
            selectType(full ? { ...full, ...t, members: full.members, unclassified: full.unclassified, children: full.children } : t)
          }}
          busy={busy}
          onSave={(id, properties) => run(() => api.saveKgTypeProperties(id, properties))}
        />
      )}

      {tab === 'relations' && (
        <RelationSchemaPanel
          relations={schemaBundle?.relations || types?.relations || []}
          typeNames={(types?.types || schemaBundle?.types || []).map((t) => t.name)}
          busy={busy}
          onSave={(payload) => run(() => api.saveKgRelation(payload))}
          onDelete={(rel) => {
            if (!window.confirm(`删除关系定义 ${rel.source_type} --${rel.name}--> ${rel.target_type}？不会立刻删图上的边。`)) return
            return run(() => api.deleteKgRelation(rel.id))
          }}
        />
      )}

      {tab === 'constraints' && (
        <ConstraintRulesPanel
          constraints={schemaBundle?.constraints || []}
          manual={schemaBundle?.manual_constraints || []}
          rules={rules}
          inferOpen={inferOpen}
          inferred={inferred}
          busy={busy}
          onSaveManual={(payload) => run(() => api.saveKgConstraint(payload))}
          onDeleteManual={(id) => run(() => api.deleteKgConstraint(id))}
          onToggleRule={(r) => run(() => api.setKgRuleStatus(r.id, r.status === 'ACTIVE' ? 'INACTIVE' : 'ACTIVE'))}
          onOpenTickets={() => {
            setProblemCode('INFER_RELATION')
            setItemStatus('open')
            setTab('workitems')
          }}
        />
      )}

      {tab === 'history' && (
        <section className="bg-white rounded-2xl border border-slate-100 p-5 space-y-2">
          <p className="text-xs text-slate-500">回滚恢复本体类型、属性 Schema、关系定义、约束与推理规则，不会删除图谱节点。</p>
          {revisions.map((r) => (
            <div key={r.id} className="flex items-center justify-between text-sm py-2 border-b border-slate-50">
              <div>
                <div className="text-slate-800">{r.reason || '快照'}</div>
                <div className="text-[11px] text-slate-400">{r.created_time}</div>
              </div>
              <button
                disabled={busy}
                onClick={() => run(() => api.rollbackKg(r.id))}
                className="text-xs px-2 py-1 rounded-lg border border-slate-200 flex items-center gap-1"
              >
                <Undo2 size={12} /> 回滚到此
              </button>
            </div>
          ))}
          {!revisions.length && <p className="text-xs text-slate-400">暂无快照</p>}
        </section>
      )}
      {detailNodeId ? (
        <InstanceDetailModal
          nodeId={detailNodeId}
          onClose={() => setDetailNodeId(null)}
          onOpenOther={setDetailNodeId}
        />
      ) : null}
    </div>
  )
}

function InstanceList({ title, items, busy, onClassify, onDelete, onDetail }) {
  const [tip, setTip] = useState(null)
  return (
    <div>
      <div className="text-xs font-semibold text-slate-700 mb-1">{title} · {items.length}</div>
      {items.length ? (
        <div className="space-y-2 max-h-80 overflow-auto pr-1">
          {items.map((m) => {
            const full = (m.description || m.name || '').trim()
            const canDelete = m.deletable !== false && m.graph_type !== 'Person'
            return (
              <div key={m.id} className="flex items-start justify-between gap-2 text-xs py-1.5 border-b border-slate-50">
                <div
                  className="min-w-0 flex-1 cursor-default"
                  onMouseEnter={(e) => {
                    const r = e.currentTarget.getBoundingClientRect()
                    setTip({
                      text: full,
                      top: Math.min(r.bottom + 6, window.innerHeight - 12),
                      left: r.left,
                      width: Math.min(Math.max(r.width, 280), 480),
                    })
                  }}
                  onMouseLeave={() => setTip(null)}
                >
                  <div className="text-slate-800 leading-5 line-clamp-3 break-words">{full}</div>
                  <div className="text-[10px] text-slate-400 mt-0.5">
                    {m.graph_type}
                    {m.ontology_type ? ` · ${m.ontology_type}` : ''}
                    {m.has_open_item ? <span className="ml-1 text-amber-600">待确认</span> : null}
                  </div>
                </div>
                <div className="flex items-center gap-1 shrink-0 pt-0.5">
                  <button
                    type="button"
                    onClick={() => onDetail?.(m.id)}
                    className="text-[11px] px-2 py-0.5 rounded border border-slate-200 text-slate-600 hover:bg-slate-50 whitespace-nowrap flex items-center gap-1"
                  >
                    <Eye size={11} /> 详情
                  </button>
                  <button
                    disabled={busy}
                    onClick={() => onClassify(m.id)}
                    className="text-[11px] px-2 py-0.5 rounded border border-slate-200 text-slate-600 hover:bg-slate-50 disabled:opacity-50 whitespace-nowrap"
                  >
                    建议重分类
                  </button>
                  {canDelete ? (
                  <button
                    disabled={busy}
                    onClick={() => onDelete(m.id)}
                    className="text-[11px] px-2 py-0.5 rounded border border-red-200 text-red-600 hover:bg-red-50 disabled:opacity-50 whitespace-nowrap"
                  >
                    删除
                  </button>
                  ) : null}
                </div>
              </div>
            )
          })}
        </div>
      ) : <p className="text-[11px] text-slate-400">无</p>}
      {tip ? (
        <div
          className="fixed z-[80] max-h-64 overflow-auto rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-700 shadow-lg whitespace-pre-wrap break-words"
          style={{ top: tip.top, left: tip.left, width: tip.width }}
        >
          {tip.text}
        </div>
      ) : null}
    </div>
  )
}

function Stat({ label, value }) {
  return (
    <div className="bg-white rounded-2xl border border-slate-100 p-4">
      <div className="text-[11px] text-slate-400">{label}</div>
      <div className="text-xl font-bold text-slate-800 mt-0.5">{value}</div>
    </div>
  )
}
