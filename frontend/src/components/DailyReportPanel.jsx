import React, { useState, useEffect, useRef } from 'react'
import {
  FileSpreadsheet, Upload, Loader2, RefreshCw, Filter,
  CheckCircle2, AlertTriangle, History, X,
} from 'lucide-react'
import { api } from '../api/client.js'

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
            Excel 增量同步 · 日期+成员唯一键 · Hash Diff · 历史版本 · AI 标签
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

function Stat({ label, value, accent }) {
  return (
    <div className="bg-white/70 rounded-xl px-3 py-2 border border-slate-100/80">
      <div className="text-[10px] text-slate-400">{label}</div>
      <div className={`text-xl font-bold text-slate-800 ${accent || ''}`}>{value ?? 0}</div>
    </div>
  )
}
