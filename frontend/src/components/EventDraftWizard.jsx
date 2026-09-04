import React, { useEffect, useMemo, useState } from 'react'
import { Loader2, AlertTriangle, Sparkles, X, Plus } from 'lucide-react'
import { api } from '../api/client.js'
import { beijingDateTimeLocal, TZ_LABEL } from '../utils/beijingTime.js'

function keyOf(typeId, tagId) {
  return `${typeId}::${tagId}`
}

export default function EventDraftWizard({ members = [], context = {}, onClose, onConfirm }) {
  const [text, setText] = useState(context.draft_text || '')
  const [eventTime, setEventTime] = useState(context.event_time || beijingDateTimeLocal())
  const [createdBy, setCreatedBy] = useState(context.created_by || members[0]?.id || '')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)
  const [checked, setChecked] = useState({})
  const [extraType, setExtraType] = useState('')
  const [extraTag, setExtraTag] = useState('')

  const [taxonomy, setTaxonomy] = useState({ types: [] })

  useEffect(() => {
    api.getEventTaxonomy().then(setTaxonomy).catch(() => {})
  }, [])

  useEffect(() => {
    if (context.event_time) setEventTime(String(context.event_time).slice(0, 16))
    if (context.created_by) setCreatedBy(context.created_by)
    if (context.draft_text) setText(context.draft_text)
  }, [context.event_time, context.created_by, context.draft_text])

  const types = useMemo(() => {
    if ((taxonomy.types || []).length) return taxonomy.types
    const map = new Map()
    for (const row of result?.catalog || []) {
      if (!map.has(row.event_type)) map.set(row.event_type, { id: row.event_type, label: row.type_label, tags: [] })
      map.get(row.event_type).tags.push({ id: row.event_tag, label: row.tag_label })
    }
    return [...map.values()]
  }, [taxonomy, result])
  const extraTags = types.find((t) => t.id === extraType)?.tags || []

  const selectedKeys = Object.keys(checked).filter((k) => checked[k])

  const handleAnalyze = async () => {
    if (!text.trim()) {
      setError('请先描述发生了什么')
      return
    }
    setError(null)
    setLoading(true)
    try {
      const data = await api.suggestEventTags({
        text: text.trim(),
        created_by: createdBy || undefined,
        event_time: eventTime || undefined,
      })
      setResult(data)
      const next = {}
      for (const m of data.matches || []) {
        next[keyOf(m.event_type, m.event_tag)] = !!m.selected_default
      }
      if ((data.matches || []).length && !Object.values(next).some(Boolean)) {
        next[keyOf(data.matches[0].event_type, data.matches[0].event_tag)] = true
      }
      setChecked(next)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const addExtra = () => {
    if (!extraType || !extraTag) return
    const k = keyOf(extraType, extraTag)
    const exists = (result?.matches || []).some((m) => keyOf(m.event_type, m.event_tag) === k)
    if (!exists) {
      const typeObj = types.find((t) => t.id === extraType)
      const tagObj = (typeObj?.tags || []).find((t) => t.id === extraTag)
      setResult((prev) => ({
        ...(prev || {}),
        matches: [
          ...(prev?.matches || []),
          {
            event_type: extraType,
            event_tag: extraTag,
            type_label: typeObj?.label || extraType,
            tag_label: tagObj?.label || extraTag,
            title: tagObj?.label || extraTag,
            confidence: 0,
            reason: '手动补充',
            suggested_fields: { facts: text.trim() },
            person_id: '',
            related_persons: [],
          },
        ],
      }))
    }
    setChecked((prev) => ({ ...prev, [k]: true }))
    setExtraTag('')
  }

  const handleRecord = () => {
    const chosen = (result?.matches || []).filter((m) => checked[keyOf(m.event_type, m.event_tag)])
    if (!chosen.length) {
      setError('请至少选择一个标签')
      return
    }
    onConfirm({
      draft_text: text.trim(),
      event_time: eventTime,
      created_by: createdBy,
      source: context.source || 'calendar-draft',
      matches: chosen,
    })
  }

  return (
    <div className="p-5">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-slate-800">记录事件</h2>
          <p className="text-sm text-slate-500 mt-1">
            先写下发生了什么，点分析后勾选匹配的标签。保存后进入日历，并生成待确认事实。
          </p>
        </div>
        {onClose && (
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-700 p-1"><X size={18} /></button>
        )}
      </div>

      <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-6 space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="block text-sm font-semibold text-slate-700 mb-1.5">事件时间（{TZ_LABEL}）</label>
            <input type="datetime-local" value={eventTime} onChange={(e) => setEventTime(e.target.value)}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block text-sm font-semibold text-slate-700 mb-1.5">记录人</label>
            <select value={createdBy} onChange={(e) => setCreatedBy(e.target.value)}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm">
              <option value="">请选择</option>
              {members.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
          </div>
        </div>

        <div>
          <label className="block text-sm font-semibold text-slate-700 mb-1.5">发生了什么</label>
          <textarea
            rows={6}
            value={text}
            onChange={(e) => { setText(e.target.value); setResult(null) }}
            placeholder="用自己的话写。例如：下午向王总汇报了支付链路延期，同时小李卡住需要帮忙看日志。"
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm resize-none"
          />
        </div>

        <button type="button" onClick={handleAnalyze} disabled={loading}
          className="w-full flex items-center justify-center gap-2 bg-slate-800 text-white py-2.5 rounded-lg font-medium text-sm hover:bg-slate-900 disabled:opacity-50">
          {loading ? <><Loader2 size={16} className="animate-spin" />正在匹配标签...</> : <><Sparkles size={16} />分析匹配标签</>}
        </button>

        {error && (
          <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">
            <AlertTriangle size={15} /> {error}
          </div>
        )}

        {result && (
          <div className="space-y-3 border-t border-slate-100 pt-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-slate-800">可能匹配的标签（可多选）</h3>
              {result.degraded && (
                <span className="text-[10px] bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded">规则匹配</span>
              )}
            </div>
            {!(result.matches || []).length && (
              <p className="text-xs text-slate-400">没有自动命中。请在下方手动补一个标签。</p>
            )}
            <div className="space-y-2">
              {(result.matches || []).map((m) => {
                const k = keyOf(m.event_type, m.event_tag)
                return (
                  <label key={k} className={`flex gap-3 items-start rounded-xl border px-3 py-2.5 cursor-pointer ${checked[k] ? 'border-brand-300 bg-brand-50' : 'border-slate-200 bg-white'}`}>
                    <input type="checkbox" className="mt-1" checked={!!checked[k]} onChange={() => setChecked((p) => ({ ...p, [k]: !p[k] }))} />
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-medium text-slate-800">
                        {m.type_label} / {m.tag_label}
                        {m.confidence > 0 && (
                          <span className="ml-2 text-[10px] text-slate-400">{Math.round(m.confidence * 100)}%</span>
                        )}
                      </div>
                      {m.reason && <p className="text-[11px] text-slate-500 mt-0.5">{m.reason}</p>}
                    </div>
                  </label>
                )
              })}
            </div>

            {types.length > 0 && (
              <div className="flex flex-wrap items-end gap-2 pt-1">
                <div>
                  <div className="text-[11px] text-slate-500 mb-1">补充其他标签</div>
                  <select value={extraType} onChange={(e) => { setExtraType(e.target.value); setExtraTag('') }}
                    className="border border-slate-200 rounded-lg px-2 py-1.5 text-sm">
                    <option value="">类型</option>
                    {types.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
                  </select>
                </div>
                <select value={extraTag} onChange={(e) => setExtraTag(e.target.value)}
                  className="border border-slate-200 rounded-lg px-2 py-1.5 text-sm" disabled={!extraType}>
                  <option value="">标签</option>
                  {extraTags.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
                </select>
                <button type="button" onClick={addExtra} disabled={!extraType || !extraTag}
                  className="inline-flex items-center gap-1 text-xs px-2 py-1.5 rounded-lg border border-slate-200 text-slate-600 disabled:opacity-40">
                  <Plus size={12} /> 加入
                </button>
              </div>
            )}

            <button type="button" onClick={handleRecord} disabled={!selectedKeys.length}
              className="w-full bg-brand-600 text-white py-2.5 rounded-lg font-medium text-sm hover:bg-brand-700 disabled:opacity-50">
              记录已选标签（{selectedKeys.length}）
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
