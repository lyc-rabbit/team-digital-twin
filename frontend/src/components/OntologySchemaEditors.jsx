import React, { useEffect, useMemo, useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'

const DATA_TYPES = ['String', 'Text', 'Integer', 'Float', 'Boolean', 'Date', 'DateTime', 'Enum', 'EntityRef', 'Array']
const SOURCES = [
  { id: 'hr', label: 'HR' },
  { id: 'human', label: '人工' },
  { id: 'llm', label: 'AI抽取' },
  { id: 'inferred', label: '推理' },
  { id: 'event', label: '事件证据' },
]
const CARDINALITIES = ['1:1', '1:n', 'n:1', 'n:n']
const KIND_LABEL = {
  property: '属性约束',
  uniqueness: '唯一性',
  enum: '枚举',
  range: '范围',
  type: '类型约束',
  relation: '关系约束',
  temporal: '时间约束',
  custom: '自定义',
}

function propsFingerprint(list) {
  return JSON.stringify((list || []).map((p) => ({
    name: p.name || '',
    label: p.label || '',
    description: p.description || '',
    data_type: p.data_type || 'String',
    required: !!p.required,
    unique: !!p.unique,
    enum_values: p.enum_values || [],
    sources: [...(p.sources || [])].sort(),
    match: !!p.match,
    extract: p.extract !== false,
    min: p.min ?? '',
    max: p.max ?? '',
    default: p.default ?? '',
  })))
}

function emptyProp() {
  return {
    name: '',
    label: '',
    data_type: 'String',
    required: false,
    unique: false,
    enum_values: [],
    sources: ['human', 'llm'],
    match: false,
    extract: true,
    min: '',
    max: '',
    default: '',
    description: '',
  }
}

export function PropertySchemaPanel({ types, selectedType, onSelect, busy, onSave }) {
  const typeList = types?.types || []
  const current = typeList.find((t) => t.id === selectedType?.id) || selectedType
  const [rows, setRows] = useState(null)
  const schemaRows = current?.schema?.properties || current?.properties || []
  const editing = rows || schemaRows
  const forbidden = current?.schema?.forbidden_as_property || []

  useEffect(() => { setRows(null) }, [current?.id])

  const patch = (idx, key, value) => {
    const next = editing.map((row, i) => (i === idx ? { ...row, [key]: value } : row))
    setRows(next)
  }

  const addRow = () => setRows([...(editing || []), emptyProp()])
  const removeRow = (idx) => setRows(editing.filter((_, i) => i !== idx))
  const dirty = useMemo(() => propsFingerprint(editing) !== propsFingerprint(schemaRows), [editing, schemaRows])

  return (
    <div className="grid grid-cols-1 md:grid-cols-[200px_1fr] gap-4">
      <section className="bg-white rounded-2xl border border-slate-100 p-3 max-h-[70vh] overflow-auto">
        <div className="text-[11px] text-slate-400 px-2 mb-1">选类型，编辑自身字段</div>
        {typeList.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => { onSelect(t); setRows(null) }}
            className={`w-full text-left px-2 py-1.5 rounded-lg text-sm ${selectedType?.id === t.id ? 'bg-brand-50 text-brand-800 font-semibold' : 'hover:bg-slate-50 text-slate-700'}`}
          >
            {t.name}
            <span className="text-[10px] text-slate-400 ml-1">{(t.schema?.properties || []).length}</span>
          </button>
        ))}
      </section>
      <section className="bg-white rounded-2xl border border-slate-100 p-5 space-y-3">
        {current ? (
          <>
            <div>
              <div className="text-lg font-bold text-slate-800">{current.name} 属性 Schema</div>
              <p className="text-[11px] text-slate-500 mt-1">
                这里定义「{current.name} 自身有什么字段」。Project / Task / Event 必须分开：项目是长期业务，任务是计划，事件是事实。能力、同事、资源请到「关系定义」。
              </p>
              {forbidden.length ? (
                <p className="text-[11px] text-amber-700 bg-amber-50 rounded-lg px-2 py-1 mt-2">
                  禁止当属性：{forbidden.join('、 ')}
                </p>
              ) : null}
            </div>
            <div className="overflow-auto">
              <table className="w-full text-[11px] text-left min-w-[1100px]">
                <thead>
                  <tr className="text-slate-400 border-b">
                    <th className="py-1 pr-2">属性名</th>
                    <th className="py-1 pr-2">描述</th>
                    <th className="py-1 pr-2">类型</th>
                    <th className="py-1 pr-2">必填</th>
                    <th className="py-1 pr-2">唯一</th>
                    <th className="py-1 pr-2">枚举/约束</th>
                    <th className="py-1 pr-2">来源</th>
                    <th className="py-1 pr-2">匹配</th>
                    <th className="py-1 pr-2">抽取</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {editing.map((row, idx) => (
                    <tr key={`${current?.id}-${idx}-${row.name}`} className="border-b border-slate-50 align-top">
                      <td className="py-1 pr-2">
                        <input className="w-24 border rounded px-1 py-0.5" value={row.name || ''}
                          onChange={(e) => patch(idx, 'name', e.target.value)} />
                      </td>
                      <td className="py-1 pr-2">
                        <textarea
                          className="w-52 min-h-[36px] border rounded px-1 py-0.5 resize-y leading-snug"
                          placeholder="属性说明"
                          value={row.description || ''}
                          onChange={(e) => patch(idx, 'description', e.target.value)}
                        />
                      </td>
                      <td className="py-1 pr-2">
                        <select className="border rounded px-1 py-0.5" value={row.data_type || 'String'}
                          onChange={(e) => patch(idx, 'data_type', e.target.value)}>
                          {DATA_TYPES.map((d) => <option key={d}>{d}</option>)}
                        </select>
                      </td>
                      <td className="py-1 pr-2">
                        <input type="checkbox" checked={!!row.required} onChange={(e) => patch(idx, 'required', e.target.checked)} />
                      </td>
                      <td className="py-1 pr-2">
                        <input type="checkbox" checked={!!row.unique} onChange={(e) => patch(idx, 'unique', e.target.checked)} />
                      </td>
                      <td className="py-1 pr-2">
                        {row.data_type === 'Enum' ? (
                          <input className="w-40 border rounded px-1 py-0.5" placeholder="planning,running"
                            value={(row.enum_values || []).join(',')}
                            onChange={(e) => patch(idx, 'enum_values', e.target.value.split(',').map((s) => s.trim()).filter(Boolean))} />
                        ) : row.data_type === 'Integer' || row.data_type === 'Float' ? (
                          <span className="flex gap-1">
                            <input className="w-12 border rounded px-1 py-0.5" placeholder="min" value={row.min ?? ''}
                              onChange={(e) => patch(idx, 'min', e.target.value === '' ? null : Number(e.target.value))} />
                            <input className="w-12 border rounded px-1 py-0.5" placeholder="max" value={row.max ?? ''}
                              onChange={(e) => patch(idx, 'max', e.target.value === '' ? null : Number(e.target.value))} />
                          </span>
                        ) : <span className="text-slate-300">—</span>}
                      </td>
                      <td className="py-1 pr-2">
                        <div className="flex flex-wrap gap-1 max-w-[160px]">
                          {SOURCES.map((s) => (
                            <label key={s.id} className="flex items-center gap-0.5 whitespace-nowrap">
                              <input
                                type="checkbox"
                                checked={(row.sources || []).includes(s.id)}
                                onChange={(e) => {
                                  const cur = new Set(row.sources || [])
                                  if (e.target.checked) cur.add(s.id)
                                  else cur.delete(s.id)
                                  patch(idx, 'sources', [...cur])
                                }}
                              />
                              {s.label}
                            </label>
                          ))}
                        </div>
                      </td>
                      <td className="py-1 pr-2">
                        <input type="checkbox" checked={!!row.match} onChange={(e) => patch(idx, 'match', e.target.checked)} title="参与实体匹配" />
                      </td>
                      <td className="py-1 pr-2">
                        <input type="checkbox" checked={row.extract !== false} onChange={(e) => patch(idx, 'extract', e.target.checked)} title="允许 LLM 抽取" />
                      </td>
                      <td className="py-1">
                        <button type="button" className="text-slate-300 hover:text-red-600" onClick={() => removeRow(idx)}>
                          <Trash2 size={12} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex gap-2">
              <button type="button" onClick={addRow} className="text-xs px-3 py-1.5 rounded-lg border border-slate-200 flex items-center gap-1">
                <Plus size={12} /> 新增属性
              </button>
              <button
                type="button"
                disabled={busy || !current.id || !dirty}
                onClick={() => onSave(current.id, editing).then(() => setRows(null))}
                className="text-xs px-3 py-1.5 rounded-lg bg-brand-600 text-white disabled:opacity-50"
              >
                保存属性 Schema
              </button>
            </div>
          </>
        ) : (
          <p className="text-xs text-slate-400">左侧选择一个类型。</p>
        )}
      </section>
    </div>
  )
}

export function RelationSchemaPanel({ relations, typeNames, busy, onSave, onDelete }) {
  const [form, setForm] = useState({
    name: '', source_type: 'Person', target_type: 'Project', description: '',
    cardinality: 'n:n', temporal: true, symmetric: false,
  })
  return (
    <div className="space-y-4">
      <section className="bg-white rounded-2xl border border-slate-100 p-5">
        <h3 className="text-sm font-bold text-slate-800">关系 Schema</h3>
        <p className="text-[11px] text-slate-500 mt-1">
          声明「不同类型之间允许怎么连」。例如 Person --OWNER--&gt; Project。旧图关系名（如 BELONGS_TO、WORKS_ON）作为别名保留，分析时视为合法。
        </p>
        <div className="overflow-auto mt-3">
          <table className="w-full text-[11px] text-left min-w-[800px]">
            <thead>
              <tr className="text-slate-400 border-b">
                <th className="py-1">关系</th>
                <th className="py-1">源类型</th>
                <th className="py-1">目标类型</th>
                <th className="py-1">基数</th>
                <th className="py-1">时态</th>
                <th className="py-1">别名</th>
                <th className="py-1">说明</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {(relations || []).map((r) => (
                <tr key={r.id} className="border-b border-slate-50">
                  <td className="py-1.5 font-mono text-brand-700">{r.name}</td>
                  <td>{r.source_type}</td>
                  <td>{r.target_type}</td>
                  <td>{r.rule?.cardinality || 'n:n'}</td>
                  <td>{r.rule?.temporal === false ? '否' : '是'}</td>
                  <td className="text-slate-400 font-mono">{(r.rule?.aliases || []).join(', ') || '—'}</td>
                  <td className="text-slate-500">{r.description}</td>
                  <td>
                    <button type="button" className="text-slate-300 hover:text-red-600" onClick={() => onDelete(r)} disabled={busy}>
                      <Trash2 size={12} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="bg-white rounded-2xl border border-slate-100 p-5 space-y-2">
        <div className="text-xs font-semibold text-slate-700">新增允许关系</div>
        <div className="grid grid-cols-1 md:grid-cols-5 gap-2">
          <input className="text-xs border rounded-lg px-2 py-1.5" placeholder="OWNER"
            value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <select className="text-xs border rounded-lg px-2 py-1.5" value={form.source_type}
            onChange={(e) => setForm({ ...form, source_type: e.target.value })}>
            {typeNames.map((n) => <option key={n}>{n}</option>)}
          </select>
          <select className="text-xs border rounded-lg px-2 py-1.5" value={form.target_type}
            onChange={(e) => setForm({ ...form, target_type: e.target.value })}>
            {typeNames.map((n) => <option key={n}>{n}</option>)}
          </select>
          <select className="text-xs border rounded-lg px-2 py-1.5" value={form.cardinality}
            onChange={(e) => setForm({ ...form, cardinality: e.target.value })}>
            {CARDINALITIES.map((c) => <option key={c}>{c}</option>)}
          </select>
          <input className="text-xs border rounded-lg px-2 py-1.5" placeholder="说明"
            value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        </div>
        <button
          type="button"
          disabled={busy || !form.name}
          className="text-xs px-3 py-1.5 rounded-lg bg-brand-600 text-white disabled:opacity-50"
          onClick={() => onSave({
            name: form.name,
            source_type: form.source_type,
            target_type: form.target_type,
            description: form.description,
            rule: { cardinality: form.cardinality, temporal: form.temporal, symmetric: form.symmetric, sources: ['human', 'llm', 'inferred'] },
          }).then(() => setForm({ ...form, name: '', description: '' }))}
        >
          保存关系定义
        </button>
      </section>
    </div>
  )
}

export function ConstraintRulesPanel({
  constraints, manual, rules, inferOpen, inferred, busy,
  onSaveManual, onDeleteManual, onToggleRule, onOpenTickets,
}) {
  const [form, setForm] = useState({ name: '', kind: 'custom', object_type: '', message: '' })
  const grouped = useMemo(() => {
    const map = {}
    for (const c of constraints || []) {
      const k = c.kind || 'custom'
      if (!map[k]) map[k] = []
      map[k].push(c)
    }
    return map
  }, [constraints])

  return (
    <div className="space-y-4">
      <section className="bg-white rounded-2xl border border-slate-100 p-5">
        <h3 className="text-sm font-bold text-slate-800">校验约束（事实是否合法）</h3>
        <p className="text-[11px] text-slate-500 mt-1">
          必填、唯一、枚举、范围、允许关系由属性/关系 Schema 自动编译。手工规则用于额外时间或业务约束。解析器应读取这一层，而不是自由发挥。
        </p>
        {Object.entries(grouped).map(([kind, items]) => (
          <div key={kind} className="mt-3">
            <div className="text-[11px] font-semibold text-slate-600">{KIND_LABEL[kind] || kind} · {items.length}</div>
            <div className="mt-1 space-y-1 max-h-48 overflow-auto">
              {items.map((c) => (
                <div key={c.id} className="text-[11px] text-slate-700 flex justify-between gap-2 py-0.5 border-b border-slate-50">
                  <span>{c.message || c.name}</span>
                  <span className="text-slate-400 shrink-0">{c.origin === 'schema' ? 'Schema' : '手工'}</span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </section>
      <section className="bg-white rounded-2xl border border-slate-100 p-5 space-y-2">
        <div className="text-xs font-semibold text-slate-700">手工约束</div>
        {(manual || []).map((c) => (
          <div key={c.id} className="flex items-start justify-between gap-2 text-xs py-1 border-b border-slate-50">
            <div>
              <div className="text-slate-800">{c.name}</div>
              <div className="text-[11px] text-slate-500">{c.message} · {c.kind} / {c.object_type}</div>
            </div>
            <button type="button" className="text-slate-300 hover:text-red-600" disabled={busy} onClick={() => onDeleteManual(c.id)}>
              <Trash2 size={12} />
            </button>
          </div>
        ))}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-2">
          <input className="text-xs border rounded-lg px-2 py-1.5" placeholder="名称"
            value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <select className="text-xs border rounded-lg px-2 py-1.5" value={form.kind}
            onChange={(e) => setForm({ ...form, kind: e.target.value })}>
            {Object.keys(KIND_LABEL).map((k) => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}
          </select>
          <input className="text-xs border rounded-lg px-2 py-1.5" placeholder="对象类型 Person/Project"
            value={form.object_type} onChange={(e) => setForm({ ...form, object_type: e.target.value })} />
          <input className="text-xs border rounded-lg px-2 py-1.5" placeholder="说明"
            value={form.message} onChange={(e) => setForm({ ...form, message: e.target.value })} />
        </div>
        <button
          type="button"
          disabled={busy || !form.name}
          className="text-xs px-3 py-1.5 rounded-lg border border-slate-200 disabled:opacity-50"
          onClick={() => onSaveManual(form).then(() => setForm({ name: '', kind: 'custom', object_type: '', message: '' }))}
        >
          新增手工约束
        </button>
      </section>
      <section className="bg-white rounded-2xl border border-slate-100 p-5">
        <h3 className="text-sm font-bold text-slate-800 mb-2">推理规则（含禁止跨语义域：职位≠培养、归属≠贡献、负责≠能力）</h3>
        {(rules || []).map((r) => (
          <div key={r.id} className="flex items-start justify-between gap-3 py-2 border-b border-slate-50 last:border-0">
            <div>
              <div className="text-sm text-slate-800">{r.name}</div>
              <div className="text-[11px] text-slate-500">{r.description}</div>
            </div>
            <button
              disabled={busy}
              onClick={() => onToggleRule(r)}
              className={`text-[11px] px-2 py-1 rounded-lg ${r.status === 'ACTIVE' ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'}`}
            >
              {r.status === 'ACTIVE' ? '启用中' : '已停用'}
            </button>
          </div>
        ))}
      </section>
      <section className="bg-white rounded-2xl border border-slate-100 p-5">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-bold text-slate-800">待确认推断</h3>
          <button type="button" className="text-[11px] text-brand-700" onClick={onOpenTickets}>去工单处理</button>
        </div>
        {inferOpen?.length ? inferOpen.slice(0, 8).map((e) => {
          const p = e.proposed || {}
          return (
            <div key={e.id} className="mb-2 text-sm text-slate-700">
              {p.source} <span className="text-brand-700 font-mono text-xs">{p.relation}</span> {p.target}
            </div>
          )
        }) : <p className="text-xs text-slate-400">没有待确认推理工单。</p>}
        <h3 className="text-sm font-bold text-slate-800 mt-4 mb-2">已确认推断边</h3>
        {inferred?.length ? inferred.map((e) => (
          <div key={e.id} className="mb-2 text-sm text-slate-700">
            {e.source_name} <span className="text-brand-700 font-mono text-xs">{e.relation}</span> {e.target_name}
          </div>
        )) : <p className="text-xs text-slate-400">暂无已确认推断边。</p>}
      </section>
    </div>
  )
}
