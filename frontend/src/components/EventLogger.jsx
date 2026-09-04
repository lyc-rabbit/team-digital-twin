import React, { useEffect, useMemo, useState } from 'react'
import { Send, CheckCircle2, Loader2, AlertTriangle, X } from 'lucide-react'
import { api } from '../api/client.js'
import { beijingDateTimeLocal, TZ_LABEL } from '../utils/beijingTime.js'

const EMPTY_FIELDS = {
  background: '', facts: '', expected: '', difference: '',
  actions: '', result: '', evidence: '', judgement: '',
  attempts: '', help_request: '',
}

export default function EventLogger({ members = [], onSaved, onClose, onSkip, context = {}, modal }) {
  const [taxonomy, setTaxonomy] = useState({ types: [] })
  const [template, setTemplate] = useState(null)
  const [eventTime, setEventTime] = useState(context.event_time || beijingDateTimeLocal)
  const [eventType, setEventType] = useState(context.event_type || '')
  const [eventTag, setEventTag] = useState(context.event_tag || '')
  const [createdBy, setCreatedBy] = useState(context.created_by || members[0]?.id || '')
  const [targetId, setTargetId] = useState(context.person_id || context.target_person_id || '')
  const [related, setRelated] = useState(context.related_persons || [])
  const [fields, setFields] = useState({ ...EMPTY_FIELDS, ...(context.fields || {}) })
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.getEventTaxonomy().then(setTaxonomy).catch(() => {})
  }, [])

  useEffect(() => {
    setTargetId(context.person_id || context.target_person_id || '')
    setCreatedBy(context.created_by || members[0]?.id || '')
    setEventType(context.event_type || '')
    setEventTag(context.event_tag || '')
    setRelated([...(context.related_persons || [])])
    setFields({ ...EMPTY_FIELDS, ...(context.fields || {}) })
    if (context.event_time) setEventTime(String(context.event_time).slice(0, 16))
    setResult(null)
    setError(null)
  }, [context.person_id, context.target_person_id, context.created_by, context.event_type, context.event_tag, context.event_time, context.queue_index])

  const typeObj = useMemo(
    () => (taxonomy.types || []).find((t) => t.id === eventType),
    [taxonomy, eventType],
  )
  const tags = typeObj?.tags || []

  useEffect(() => {
    if (!eventType || !eventTag) {
      setTemplate(null)
      return
    }
    api.getEventTemplate(eventType, eventTag).then(setTemplate).catch(() => setTemplate(null))
  }, [eventType, eventTag])

  const setField = (id, value) => setFields((prev) => ({ ...prev, [id]: value }))

  const toggleRelated = (id) => {
    setRelated((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }

  const handleSubmit = async () => {
    if (!eventType || !eventTag) {
      setError('请先选择事件类型和标签，系统会按标签生成描述框架')
      return
    }
    if (!targetId && !createdBy) {
      setError('请选择关联人员')
      return
    }
    const filled = (template?.fields || []).some((f) => (fields[f.id] || '').trim())
    if (!filled) {
      setError('请按框架填写至少一项事实描述')
      return
    }
    setError(null)
    setLoading(true)
    setResult(null)
    const involved = [createdBy, targetId, ...related].filter(Boolean)
    const unique = [...new Set(involved)]
    try {
      const extra = {}
      if (fields.attempts) extra.attempts = fields.attempts
      if (fields.help_request) extra.help_request = fields.help_request
      const res = await api.logEvent({
        event_time: eventTime,
        event_type: eventType,
        event_tag: eventTag,
        involved_members: unique,
        created_by: createdBy || undefined,
        target_person_id: targetId || undefined,
        subjects: targetId ? [{ person_id: targetId, role: 'target' }] : [],
        related_persons: related,
        related_project_id: context.project_id || '',
        related_stage_id: context.stage_id || '',
        related_role_id: context.role_id || '',
        related_newcomer_id: context.newcomer_id || '',
        source: context.source || 'manual',
        background: fields.background,
        facts: fields.facts,
        expected: fields.expected,
        difference: fields.difference,
        actions: fields.actions,
        result: fields.result,
        evidence: fields.evidence,
        judgement: fields.judgement,
        attempts: fields.attempts,
        help_request: fields.help_request,
        extra_fields: extra,
        scene: template?.title,
      })
      setResult(res)
      setFields({ ...EMPTY_FIELDS })
      onSaved?.(res)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const memberName = (id) => members.find((m) => m.id === id)?.name || id
  const ctxHint = contextHint(context, memberName)
  const queueTotal = Number(context.queue_total || 0)
  const queueIndex = Number(context.queue_index || 0)
  const inQueue = queueTotal > 1
  const lastInQueue = inQueue && queueIndex >= queueTotal

  return (
    <div className={`${modal ? 'p-5' : 'p-6 max-w-3xl mx-auto'} fade-in`}>
      <div className="mb-5 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-slate-800">
            记录事件
            {inQueue && <span className="ml-2 text-sm font-medium text-brand-700">第 {queueIndex}/{queueTotal} 个标签</span>}
          </h2>
          <p className="text-sm text-slate-500 mt-1">
            先选类型和标签，再按框架写事实。保存后进入日历，并生成待确认关系事实；确认后才写入图谱。
          </p>
          {ctxHint && <p className="text-[11px] text-brand-700 bg-brand-50 rounded-md px-2 py-1 mt-2">{ctxHint}</p>}
        </div>
        {onClose && (
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700 p-1"><X size={18} /></button>
        )}
      </div>

      <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-6 space-y-5">
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
          <label className="block text-sm font-semibold text-slate-700 mb-1.5">事件类型</label>
          <div className="flex flex-wrap gap-1.5">
            {(taxonomy.types || []).map((t) => (
              <button key={t.id} type="button"
                onClick={() => { setEventType(t.id); setEventTag(''); setResult(null) }}
                className={`text-xs px-3 py-1.5 rounded-full border ${eventType === t.id ? 'bg-brand-600 text-white border-brand-600' : 'bg-white text-slate-600 border-slate-200'}`}>
                {t.label}
              </button>
            ))}
          </div>
        </div>

        {tags.length > 0 && (
          <div>
            <label className="block text-sm font-semibold text-slate-700 mb-1.5">标签</label>
            <div className="flex flex-wrap gap-1.5">
              {tags.map((t) => (
                <button key={t.id} type="button" onClick={() => { setEventTag(t.id); setResult(null) }}
                  className={`text-xs px-3 py-1.5 rounded-full border ${eventTag === t.id ? 'bg-slate-800 text-white border-slate-800' : 'bg-white text-slate-600 border-slate-200'}`}>
                  {t.label}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="block text-sm font-semibold text-slate-700 mb-1.5">关联人员（对象）</label>
            <select value={targetId} onChange={(e) => setTargetId(e.target.value)}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm">
              <option value="">请选择</option>
              {members.map((m) => <option key={m.id} value={m.id}>{m.name} · {m.role}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-sm font-semibold text-slate-700 mb-1.5">其他相关人</label>
            <div className="flex flex-wrap gap-1">
              {members.filter((m) => m.id !== targetId && m.id !== createdBy).slice(0, 12).map((m) => (
                <button key={m.id} type="button" onClick={() => toggleRelated(m.id)}
                  className={`text-[11px] px-2 py-1 rounded-full border ${related.includes(m.id) ? 'bg-brand-50 text-brand-700 border-brand-200' : 'border-slate-200 text-slate-500'}`}>
                  {m.name}
                </button>
              ))}
            </div>
          </div>
        </div>

        {template ? (
          <div className="space-y-3 border-t border-slate-100 pt-4">
            <div>
              <h3 className="text-sm font-bold text-slate-800">{template.title}</h3>
              {template.hint && <p className="text-[11px] text-amber-700 bg-amber-50 rounded-md px-2 py-1.5 mt-1">{template.hint}</p>}
            </div>
            {(template.fields || []).map((f) => (
              <div key={f.id}>
                <label className="block text-sm font-semibold text-slate-700 mb-1">【{f.label}】</label>
                <textarea
                  rows={2}
                  value={fields[f.id] || ''}
                  onChange={(e) => setField(f.id, e.target.value)}
                  placeholder={f.placeholder}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm resize-none"
                />
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-slate-400 border border-dashed border-slate-200 rounded-lg px-3 py-6 text-center">
            选择类型和标签后，这里会显示对应的事件描述框架。
          </p>
        )}

        {error && (
          <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">
            <AlertTriangle size={15} /> {error}
          </div>
        )}

        <div className="flex gap-2">
          {inQueue && onSkip && (
            <button type="button" onClick={onSkip}
              className="px-4 py-2.5 rounded-lg border border-slate-200 text-sm text-slate-600 hover:bg-slate-50">
              跳过此标签
            </button>
          )}
          <button onClick={handleSubmit} disabled={loading}
            className="flex-1 flex items-center justify-center gap-2 bg-brand-600 text-white py-2.5 rounded-lg font-medium text-sm hover:bg-brand-700 disabled:opacity-50">
            {loading
              ? <><Loader2 size={16} className="animate-spin" />分析并写入证据链...</>
              : <><Send size={16} />{inQueue && !lastInQueue ? '保存并继续下一项' : '保存事件'}</>}
          </button>
        </div>
      </div>

      {result && (
        <div className="mt-5 bg-white rounded-2xl border border-slate-100 p-5 space-y-3">
          <div className="flex items-center gap-2">
            <CheckCircle2 size={18} className="text-emerald-500" />
            <h3 className="text-sm font-bold text-slate-800">事件已写入日历</h3>
          </div>
          {Number(result.facts?.created || 0) > 0 ? (
            <p className="text-xs text-amber-800 bg-amber-50 rounded-lg px-3 py-2">
              已生成 {result.facts.created} 条待确认事实。请到「事实管理」确认后才写入图谱关系。
            </p>
          ) : (
            <p className="text-xs text-slate-500 bg-slate-50 rounded-lg px-3 py-2">
              本次未识别出可登记的关系事实。日历已记录该事件，可稍后在「事实管理」补录。
            </p>
          )}
          {result.parsed_analysis?.structured_problem && (
            <p className="text-xs text-emerald-700 bg-emerald-50 rounded-lg px-3 py-2">
              系统识别：本次完成了结构化问题定义，将计入问题定义能力与关系信任变化。
            </p>
          )}
          {(result.parsed_analysis?.relationship_evidence || []).map((rel, i) => (
            <div key={i} className="text-xs bg-slate-50 rounded-lg px-3 py-2">
              <span className="font-medium">{memberName(rel.from_member_id)} → {memberName(rel.to_member_id)}</span>
              <span className={`ml-2 font-bold ${rel.delta >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                {rel.delta > 0 ? '+' : ''}{rel.delta} {rel.dimension}
              </span>
              <div className="text-slate-500 mt-0.5">{rel.reason}</div>
            </div>
          ))}
          {(result.parsed_analysis?.capability_evidence || []).map((c, i) => (
            <div key={i} className="text-xs text-slate-600">
              能力证据：{memberName(c.employee_id)} · {c.capability_name} · {c.reason}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function contextHint(ctx, memberName) {
  const bits = []
  if (ctx.source === 'newcomer-map') bits.push('来源：新人地图')
  if (ctx.source === 'project') bits.push('来源：项目中心')
  if (ctx.source === 'cadre') bits.push('来源：干部成长')
  if (ctx.source === 'upward') bits.push('来源：向上协同')
  if (ctx.source === 'relationship') bits.push('来源：人物关系网')
  if (ctx.source === 'promotion') bits.push('来源：晋升领导')
  if (ctx.source === 'team-situation') bits.push('来源：团队态势')
  if (ctx.source === 'calendar' || ctx.source === 'calendar-draft' || ctx.source === 'global') bits.push('来源：草稿匹配')
  if (ctx.queue_total > 1) bits.push(`标签队列 ${ctx.queue_index}/${ctx.queue_total}`)
  if (ctx.draft_text) bits.push('已带入草稿原文')
  if (ctx.person_id) bits.push(`关联人员：${memberName(ctx.person_id)}`)
  if (ctx.stage_id) bits.push('已带入培养阶段')
  if (ctx.project_id) bits.push('已关联项目')
  return bits.join(' · ')
}
