import React, { useState, useEffect, useRef } from 'react'
import {
  FileSpreadsheet, Upload, Loader2, RefreshCw, Filter,
  CheckCircle2, AlertTriangle, History, X, Sparkles, Copy, Save, ArrowRight,
} from 'lucide-react'
import { api } from '../api/client.js'
import { beijingToday, TZ_LABEL } from '../utils/beijingTime.js'

export default function DailyReportPanel({ members }) {
  const [reports, setReports] = useState([])
  const [loading, setLoading] = useState(true)
  const [importing, setImporting] = useState(false)
  const [taskResult, setTaskResult] = useState(null)
  const [error, setError] = useState(null)
  const [filters, setFilters] = useState({ date: '', member: '', project: '', skill: '' })
  const [historyOpen, setHistoryOpen] = useState(null)
  const [historyRows, setHistoryRows] = useState([])
  const fileRef = useRef(null)
  const mountedRef = useRef(true)

  const loadReports = async (nextFilters = filters) => {
    const params = {}
    if (nextFilters.date) params.date = nextFilters.date
    if (nextFilters.member) params.member = nextFilters.member
    if (nextFilters.project) params.project = nextFilters.project
    if (nextFilters.skill) params.skill = nextFilters.skill
    const data = await api.getDailyReports(params)
    if (mountedRef.current) setReports(data.reports || [])
  }

  useEffect(() => {
    mountedRef.current = true
    loadReports()
      .catch((err) => mountedRef.current && setError(err.message))
      .finally(() => mountedRef.current && setLoading(false))
    return () => { mountedRef.current = false }
  }, [])

  const pollTask = async (taskId) => {
    for (let i = 0; i < 120; i++) {
      const st = await api.getDailyImportTask(taskId)
      if (!mountedRef.current) return null
      setTaskResult(st)
      if (st.status === 'success' || st.status === 'failed') return st
      await new Promise((r) => setTimeout(r, 1000))
    }
    throw new Error('导入超时，请稍后在任务列表查看')
  }

  const handleFile = async (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setImporting(true)
    setError(null)
    setTaskResult(null)
    try {
      const start = await api.importDailyReport(file)
      const final = await pollTask(start.task_id)
      if (final?.status === 'success') {
        await loadReports()
      } else if (final?.status === 'failed') {
        setError(final.message || '导入失败')
      }
    } catch (err) {
      if (mountedRef.current) setError(err.message || '导入失败')
    } finally {
      if (mountedRef.current) setImporting(false)
    }
  }

  const applyFilters = async () => {
    setLoading(true)
    setError(null)
    try {
      await loadReports(filters)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const openHistory = async (reportId) => {
    setHistoryOpen(reportId)
    try {
      const data = await api.getDailyReportHistory(reportId)
      if (mountedRef.current) setHistoryRows(data.history || [])
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto fade-in">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
            <FileSpreadsheet size={20} className="text-brand-600" />
            日报管理
          </h2>
          <p className="text-sm text-slate-500 mt-1">
            口语改写专业描述 · 一键转入 · Excel 增量同步 · 日期+成员唯一
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input
            ref={fileRef}
            type="file"
            accept=".xlsx,.xlsm"
            className="hidden"
            onChange={handleFile}
          />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={importing}
            className="flex items-center gap-1.5 text-sm font-medium text-white bg-brand-600 hover:bg-brand-700 disabled:opacity-50 px-3.5 py-2 rounded-lg"
          >
            {importing ? <Loader2 size={15} className="animate-spin" /> : <Upload size={15} />}
            {importing ? '同步中...' : '上传 Excel'}
          </button>
          <button
            onClick={applyFilters}
            disabled={loading}
            className="flex items-center gap-1.5 text-sm text-slate-600 border border-slate-200 hover:border-brand-300 px-3 py-2 rounded-lg"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            刷新
          </button>
        </div>
      </div>

      <RewriteComposer members={members} onIngested={() => loadReports()} />

      <div className="bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-xs text-slate-500">
        Excel 格式：首列为「日期」，其余列为成员姓名（需与成员管理中的姓名一致）。同一日期+成员出现两次会导入失败。
      </div>

      {/* 同步结果 */}
      {taskResult && (
        <div className={`rounded-2xl border p-5 ${
          taskResult.status === 'failed'
            ? 'bg-red-50 border-red-100'
            : taskResult.status === 'processing'
              ? 'bg-brand-50 border-brand-100'
              : 'bg-white border-slate-100 shadow-sm'
        }`}>
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-800 mb-3">
            {taskResult.status === 'processing' ? (
              <Loader2 size={16} className="animate-spin text-brand-600" />
            ) : taskResult.status === 'success' ? (
              <CheckCircle2 size={16} className="text-emerald-600" />
            ) : (
              <AlertTriangle size={16} className="text-red-600" />
            )}
            本次导入：{taskResult.file_name || `任务 #${taskResult.task_id}`}
            <span className="text-xs font-normal text-slate-400 ml-1">
              {taskResult.message || taskResult.status}
            </span>
          </div>
          <div className="grid grid-cols-5 gap-3">
            <Stat label="总记录" value={taskResult.total_count} />
            <Stat label="新增" value={taskResult.new} accent="text-emerald-600" />
            <Stat label="更新" value={taskResult.updated} accent="text-amber-600" />
            <Stat label="无变化" value={taskResult.unchanged} />
            <Stat label="失败/未绑定" value={taskResult.errors} accent="text-red-600" />
          </div>
          {taskResult.result?.unbound?.length > 0 && (
            <div className="mt-3 text-xs text-amber-700 bg-amber-50 rounded-lg px-3 py-2">
              待绑定成员：{taskResult.result.unbound.map((u) => u.member_name).filter((v, i, a) => a.indexOf(v) === i).join('、')}
              （请先在成员管理中添加同名成员后重新导入）
            </div>
          )}
          {taskResult.result?.errors?.length > 0 && (
            <div className="mt-2 text-xs text-red-600 space-y-0.5">
              {taskResult.result.errors.slice(0, 5).map((e, i) => <div key={i}>· {e}</div>)}
            </div>
          )}
        </div>
      )}

      {error && (
        <div className="text-xs text-red-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2">{error}</div>
      )}

      {/* 筛选 */}
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-4">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-700 mb-3">
          <Filter size={14} /> 数据筛选
        </div>
        <div className="grid grid-cols-4 gap-3">
          <input
            type="date"
            value={filters.date}
            onChange={(e) => setFilters({ ...filters, date: e.target.value })}
            className="text-xs border border-slate-200 rounded-lg px-2.5 py-2"
          />
          <select
            value={filters.member}
            onChange={(e) => setFilters({ ...filters, member: e.target.value })}
            className="text-xs border border-slate-200 rounded-lg px-2.5 py-2 bg-white"
          >
            <option value="">全部成员</option>
            {members.map((m) => (
              <option key={m.id} value={m.id}>{m.name}</option>
            ))}
          </select>
          <input
            type="text"
            placeholder="项目关键词"
            value={filters.project}
            onChange={(e) => setFilters({ ...filters, project: e.target.value })}
            className="text-xs border border-slate-200 rounded-lg px-2.5 py-2"
          />
          <div className="flex gap-2">
            <input
              type="text"
              placeholder="技能关键词"
              value={filters.skill}
              onChange={(e) => setFilters({ ...filters, skill: e.target.value })}
              className="flex-1 text-xs border border-slate-200 rounded-lg px-2.5 py-2"
            />
            <button
              onClick={applyFilters}
              className="text-xs bg-slate-800 text-white px-3 rounded-lg hover:bg-slate-700"
            >
              查询
            </button>
          </div>
        </div>
      </div>

      {/* 列表 */}
      <div className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
        <div className="px-5 py-3 border-b border-slate-100 text-sm font-semibold text-slate-800">
          日报数据 <span className="text-slate-400 font-normal text-xs ml-1">{reports.length} 条</span>
        </div>
        {loading ? (
          <div className="text-center text-slate-400 text-sm py-12">加载中...</div>
        ) : reports.length === 0 ? (
          <div className="text-center text-slate-400 text-sm py-12">暂无日报，请先上传 Excel</div>
        ) : (
          <div className="divide-y divide-slate-50 max-h-[520px] overflow-y-auto">
            {reports.map((r) => (
              <div key={r.id} className="px-5 py-3 hover:bg-slate-50/80">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs font-semibold text-slate-800">{r.member_name || r.member_id}</span>
                      <span className="text-[10px] text-slate-400">{r.report_date}</span>
                      <span className="text-[10px] text-slate-400">v{r.version}</span>
                      {r.activity_type && (
                        <span className="text-[10px] bg-slate-100 text-slate-500 px-1.5 py-0.5 rounded">{r.activity_type}</span>
                      )}
                    </div>
                    <p className="text-xs text-slate-600 leading-relaxed whitespace-pre-wrap">{r.content}</p>
                    <div className="flex flex-wrap gap-1.5 mt-2">
                      {(r.projects || []).map((p) => (
                        <span key={p} className="text-[10px] bg-brand-50 text-brand-600 px-1.5 py-0.5 rounded">{p}</span>
                      ))}
                      {(r.skills || []).map((s) => (
                        <span key={s} className="text-[10px] bg-emerald-50 text-emerald-700 px-1.5 py-0.5 rounded">{s}</span>
                      ))}
                    </div>
                  </div>
                  <button
                    onClick={() => openHistory(r.id)}
                    className="flex items-center gap-1 text-[11px] text-slate-400 hover:text-brand-600 flex-shrink-0"
                    title="查看历史版本"
                  >
                    <History size={13} />
                    历史
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 历史弹层 */}
      {historyOpen && (
        <div className="fixed inset-0 bg-black/30 z-50 flex items-center justify-center p-4" onClick={() => setHistoryOpen(null)}>
          <div
            className="bg-white rounded-2xl shadow-xl w-full max-w-lg max-h-[70vh] overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-5 py-3 border-b border-slate-100">
              <h3 className="text-sm font-bold text-slate-800">历史版本 · #{historyOpen}</h3>
              <button onClick={() => setHistoryOpen(null)} className="text-slate-400 hover:text-slate-600">
                <X size={16} />
              </button>
            </div>
            <div className="p-4 space-y-3 overflow-y-auto max-h-[60vh]">
              {historyRows.length === 0 ? (
                <div className="text-xs text-slate-400 text-center py-8">暂无历史</div>
              ) : historyRows.map((h) => (
                <div key={h.id} className="border border-slate-100 rounded-xl p-3 text-xs">
                  <div className="flex items-center justify-between mb-1.5">
                    <span className={`font-medium ${h.change_type === 'NEW' ? 'text-emerald-600' : 'text-amber-600'}`}>
                      {h.change_type}
                    </span>
                    <span className="text-slate-400">{h.created_at}</span>
                  </div>
                  {h.old_content && (
                    <div className="text-slate-400 mb-1 line-through">{h.old_content}</div>
                  )}
                  <div className="text-slate-700">{h.new_content}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function RewriteComposer({ members, onIngested }) {
  const [styles, setStyles] = useState([])
  const [styleId, setStyleId] = useState('')
  const [promptDrafts, setPromptDrafts] = useState({})
  const [rawText, setRawText] = useState('')
  const [result, setResult] = useState('')
  const [reportDate, setReportDate] = useState(beijingToday())
  const [memberId, setMemberId] = useState(members[0]?.id || '')
  const [existing, setExisting] = useState(null)
  const [generating, setGenerating] = useState(false)
  const [saving, setSaving] = useState(false)
  const [ingesting, setIngesting] = useState(false)
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)

  const currentStyle = styles.find((s) => s.id === styleId)
  const currentPrompt = promptDrafts[styleId] ?? currentStyle?.prompt ?? ''
  const savedPrompt = currentStyle?.prompt ?? ''
  const promptDirty = currentStyle ? currentPrompt.trim() !== (savedPrompt || '').trim() : false

  useEffect(() => {
    let alive = true
    api.getDailyReportStyles()
      .then((data) => {
        if (!alive) return
        const rows = data.styles || []
        setStyles(rows)
        const drafts = {}
        rows.forEach((s) => { drafts[s.id] = s.prompt || '' })
        setPromptDrafts(drafts)
        setStyleId((prev) => prev || rows[0]?.id || '')
      })
      .catch((err) => alive && setError(err.message))
    return () => { alive = false }
  }, [])

  useEffect(() => {
    if (!memberId && members[0]?.id) setMemberId(members[0].id)
  }, [members, memberId])

  useEffect(() => {
    if (!result || !reportDate || !memberId) {
      setExisting(null)
      return
    }
    let alive = true
    api.getDailyReports({ date: reportDate, member: memberId, limit: 1 })
      .then((data) => {
        if (!alive) return
        setExisting((data.reports || [])[0] || null)
      })
      .catch(() => alive && setExisting(null))
    return () => { alive = false }
  }, [result, reportDate, memberId])

  const selectStyle = (id) => {
    setStyleId(id)
    setNotice(null)
  }

  const handleSavePrompt = async () => {
    if (!styleId) return
    setSaving(true)
    setError(null)
    setNotice(null)
    try {
      const saved = await api.saveDailyReportStyle(styleId, { prompt: currentPrompt })
      setStyles((prev) => prev.map((s) => (s.id === styleId ? { ...s, ...saved } : s)))
      setPromptDrafts((prev) => ({ ...prev, [styleId]: saved.prompt }))
      setNotice('提示词已保存')
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const handleGenerate = async () => {
    if (!rawText.trim()) {
      setError('请先输入一段工作描述')
      return
    }
    if (!styleId) {
      setError('请选择一种风格')
      return
    }
    setGenerating(true)
    setError(null)
    setNotice(null)
    try {
      const data = await api.rewriteDailyReport({
        text: rawText.trim(),
        style_id: styleId,
        prompt: currentPrompt,
      })
      setResult(data.text || '')
      if (data.degraded) setNotice('当前为降级模式，结果由规则模板生成，可在设置中配置大模型后重试')
    } catch (err) {
      setError(err.message)
    } finally {
      setGenerating(false)
    }
  }

  const handleCopy = async () => {
    const text = (result || '').trim()
    if (!text) return
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      const el = document.createElement('textarea')
      el.value = text
      document.body.appendChild(el)
      el.select()
      document.execCommand('copy')
      document.body.removeChild(el)
    }
    setCopied(true)
    setTimeout(() => setCopied(false), 1600)
  }

  const handleIngest = async () => {
    if (!reportDate) {
      setError('请选择日报日期')
      return
    }
    if (!memberId) {
      setError('请选择日报人员')
      return
    }
    if (!result.trim()) {
      setError('请先生成或填写日报内容')
      return
    }
    setIngesting(true)
    setError(null)
    setNotice(null)
    try {
      const data = await api.ingestDailyReport({
        report_date: reportDate,
        member_id: memberId,
        content: result.trim(),
      })
      const actionText = data.action === 'appended' ? '已追加到当天日报' : '已新增当天日报'
      setNotice(`${actionText} · ${data.member_name} · ${data.report_date}`)
      setExisting({
        id: data.report_id,
        content: data.content,
        version: data.version,
        report_date: data.report_date,
        member_id: data.member_id,
        member_name: data.member_name,
      })
      onIngested?.()
    } catch (err) {
      setError(err.message)
    } finally {
      setIngesting(false)
    }
  }

  return (
    <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-5 space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-bold text-slate-800 flex items-center gap-2">
            <Sparkles size={15} className="text-brand-600" />
            生成专业描述
          </h3>
          <p className="text-xs text-slate-400 mt-1">输入口语描述，选风格后生成可编辑的日报正文，再一键转入当天日报。</p>
        </div>
      </div>

      <textarea
        value={rawText}
        onChange={(e) => setRawText(e.target.value)}
        rows={4}
        placeholder="例如：今天下午跟产品对了一下登录页，修了两个样式问题，晚上把接口文档补上了。"
        className="w-full text-sm border border-slate-200 rounded-xl px-3 py-2.5 leading-relaxed resize-y min-h-[96px]"
      />

      <div>
        <div className="text-[11px] font-semibold text-slate-500 mb-2">风格</div>
        <div className="flex flex-wrap gap-2">
          {styles.map((s) => {
            const active = s.id === styleId
            return (
              <button
                key={s.id}
                type="button"
                onClick={() => selectStyle(s.id)}
                className={`text-sm px-3 py-1.5 rounded-lg border ${
                  active
                    ? 'bg-brand-50 border-brand-400 text-brand-800 font-semibold'
                    : 'bg-white border-slate-200 text-slate-600 hover:border-brand-300'
                }`}
              >
                {s.label}
              </button>
            )
          })}
        </div>
      </div>

      {currentStyle && (
        <div className="bg-slate-50 border border-slate-100 rounded-xl p-3 space-y-2">
          <div className="flex items-center justify-between gap-2">
            <div className="text-[11px] font-semibold text-slate-500">
              {currentStyle.label} · 所用提示词
              {promptDirty && <span className="ml-1.5 text-amber-600 font-normal">未保存</span>}
            </div>
            <button
              type="button"
              onClick={handleSavePrompt}
              disabled={saving || !promptDirty}
              className="flex items-center gap-1 text-[11px] text-white bg-slate-800 hover:bg-slate-700 disabled:opacity-40 px-2.5 py-1 rounded-lg"
            >
              {saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
              保存
            </button>
          </div>
          <textarea
            value={currentPrompt}
            onChange={(e) => setPromptDrafts((prev) => ({ ...prev, [styleId]: e.target.value }))}
            rows={6}
            className="w-full text-xs font-mono border border-slate-200 bg-white rounded-lg px-3 py-2 leading-relaxed resize-y min-h-[120px]"
          />
        </div>
      )}

      <button
        type="button"
        onClick={handleGenerate}
        disabled={generating}
        className="flex items-center gap-1.5 text-sm font-medium text-white bg-brand-600 hover:bg-brand-700 disabled:opacity-50 px-4 py-2 rounded-lg"
      >
        {generating ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />}
        {generating ? '生成中...' : '生成专业描述'}
      </button>

      {error && (
        <div className="text-xs text-red-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2">{error}</div>
      )}
      {notice && (
        <div className="text-xs text-emerald-700 bg-emerald-50 border border-emerald-100 rounded-lg px-3 py-2">{notice}</div>
      )}

      {result !== '' && (
        <div className="border-t border-slate-100 pt-4 space-y-4">
          <div>
            <div className="flex items-center justify-between gap-2 mb-2">
              <div className="text-[11px] font-semibold text-slate-500">生成结果（可修改）</div>
              <button
                type="button"
                onClick={handleCopy}
                className="flex items-center gap-1 text-[11px] text-slate-600 border border-slate-200 hover:border-brand-300 px-2.5 py-1 rounded-lg"
              >
                {copied ? <CheckCircle2 size={12} className="text-emerald-600" /> : <Copy size={12} />}
                {copied ? '已复制' : '一键复制'}
              </button>
            </div>
            <textarea
              value={result}
              onChange={(e) => setResult(e.target.value)}
              rows={6}
              className="w-full text-sm border border-slate-200 rounded-xl px-3 py-2.5 leading-relaxed resize-y min-h-[120px]"
            />
          </div>

          <div className="bg-slate-50 rounded-xl p-4 space-y-3">
            <div className="text-[11px] font-semibold text-slate-500">转入日报（日期 + 人员 + 内容）</div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">日期（{TZ_LABEL}）</label>
                <input
                  type="date"
                  value={reportDate}
                  onChange={(e) => setReportDate(e.target.value)}
                  className="w-full text-sm border border-slate-200 rounded-lg px-2.5 py-2 bg-white"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">人员</label>
                <select
                  value={memberId}
                  onChange={(e) => setMemberId(e.target.value)}
                  className="w-full text-sm border border-slate-200 rounded-lg px-2.5 py-2 bg-white"
                >
                  <option value="">请选择</option>
                  {members.map((m) => (
                    <option key={m.id} value={m.id}>{m.name}</option>
                  ))}
                </select>
              </div>
            </div>
            {existing ? (
              <div className="text-xs text-amber-800 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2">
                当天已有 {existing.member_name || '该成员'} 的日报（v{existing.version}），一键转入将追加在原文之后。
                <div className="mt-1 text-slate-500 whitespace-pre-wrap max-h-20 overflow-hidden">{existing.content}</div>
              </div>
            ) : (
              <div className="text-xs text-slate-400">当天尚无该成员日报，一键转入将新增一条。</div>
            )}
            <button
              type="button"
              onClick={handleIngest}
              disabled={ingesting}
              className="flex items-center gap-1.5 text-sm font-medium text-white bg-slate-800 hover:bg-slate-700 disabled:opacity-50 px-4 py-2 rounded-lg"
            >
              {ingesting ? <Loader2 size={15} className="animate-spin" /> : <ArrowRight size={15} />}
              {ingesting ? '转入中...' : '一键转入'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function Stat({ label, value, accent }) {
  return (
    <div className="bg-white/70 rounded-xl px-3 py-2 border border-slate-100/80">
      <div className="text-[10px] text-slate-400">{label}</div>
      <div className={`text-xl font-bold text-slate-800 ${accent || ''}`}>{value ?? 0}</div>
    </div>
  )
}
