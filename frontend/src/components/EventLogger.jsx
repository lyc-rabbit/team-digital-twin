import React, { useState, useEffect } from 'react'
import { Send, CheckCircle2, Loader2, Sparkles, AlertTriangle, ChevronLeft, ChevronRight, X } from 'lucide-react'
import { api } from '../api/client.js'

const PAGE_SIZE = 4

export default function EventLogger({ members, onSaved }) {
  const [eventTime, setEventTime] = useState(
    new Date().toISOString().slice(0, 16)
  )
  const [selectedMembers, setSelectedMembers] = useState([])
  const [summary, setSummary] = useState('')
  const [scene, setScene] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [currentPage, setCurrentPage] = useState(1)

  const totalPages = Math.max(1, Math.ceil(members.length / PAGE_SIZE))

  // 成员变动导致页码越界时,自动回退到最后一页
  useEffect(() => {
    if (currentPage > totalPages) {
      setCurrentPage(totalPages)
    }
  }, [currentPage, totalPages])

  const toggleMember = (id) => {
    setSelectedMembers((prev) =>
      prev.includes(id) ? prev.filter((m) => m !== id) : [...prev, id]
    )
  }

  const handleSubmit = async () => {
    if (selectedMembers.length === 0) {
      setError('请至少选择一名涉及成员')
      return
    }
    if (!summary.trim()) {
      setError('请输入事件摘要')
      return
    }
    setError(null)
    setLoading(true)
    setResult(null)

    try {
      const res = await api.logEvent({
        event_time: eventTime,
        involved_members: selectedMembers,
        summary: summary,
        scene: scene || undefined,
      })
      setResult(res)
      setSummary('')
      setScene('')
      setSelectedMembers([])
      onSaved?.()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const memberName = (id) => members.find((m) => m.id === id)?.name || id

  return (
    <div className="p-6 max-w-3xl mx-auto fade-in">
      <div className="mb-6">
        <h2 className="text-xl font-bold text-slate-800">记录团队新事件</h2>
        <p className="text-sm text-slate-500 mt-1">
          录入后系统将自动解析事务影响、关系变化和情绪状态，构建团队记忆
        </p>
      </div>

      <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-6 space-y-5">
        {/* 时间选择 */}
        <div>
          <label className="block text-sm font-semibold text-slate-700 mb-1.5">事件时间</label>
          <input
            type="datetime-local"
            value={eventTime}
            onChange={(e) => setEventTime(e.target.value)}
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 focus:border-transparent"
          />
          <p className="text-[11px] text-slate-400 mt-1">可修改为过去或未来的任意时间（支持时间穿梭补录/推演）</p>
        </div>

        {/* 场景标签 */}
        <div>
          <label className="block text-sm font-semibold text-slate-700 mb-1.5">
            场景标签 <span className="text-slate-400 font-normal">（可选）</span>
          </label>
          <input
            type="text"
            value={scene}
            onChange={(e) => setScene(e.target.value)}
            placeholder="如：周会决策、排期争论、非正式交流..."
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 focus:border-transparent"
          />
        </div>

        {/* 人物多选 */}
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <label className="block text-sm font-semibold text-slate-700">
              涉及人物
              {selectedMembers.length > 0 && (
                <span className="ml-2 text-xs font-normal text-brand-600">
                  已选 {selectedMembers.length} 人
                </span>
              )}
            </label>
            {totalPages > 1 && (
              <span className="text-[11px] text-slate-400">
                第 {currentPage}/{totalPages} 页 · 共 {members.length} 人
              </span>
            )}
          </div>

          {/* 已选成员 chips(跨页可见) */}
          {selectedMembers.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-3">
              {selectedMembers.map((id) => {
                const m = members.find((x) => x.id === id)
                return (
                  <span
                    key={id}
                    className="inline-flex items-center gap-1 bg-brand-50 text-brand-700 text-xs px-2 py-1 rounded-full border border-brand-200"
                  >
                    {m?.name || id}
                    <button
                      type="button"
                      onClick={() => toggleMember(id)}
                      className="hover:bg-brand-200 rounded-full p-0.5"
                      title="移除"
                    >
                      <X size={11} />
                    </button>
                  </span>
                )
              })}
            </div>
          )}

          {/* 当前页成员 */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {members
              .slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)
              .map((m) => {
                const checked = selectedMembers.includes(m.id)
                return (
                  <button
                    key={m.id}
                    onClick={() => toggleMember(m.id)}
                    className={`flex items-center gap-2 px-3 py-2.5 rounded-lg border-2 transition-all ${
                      checked
                        ? 'border-brand-500 bg-brand-50 text-brand-700'
                        : 'border-slate-200 hover:border-slate-300 text-slate-600'
                    }`}
                  >
                    <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${
                      checked ? 'bg-brand-500 text-white' : 'bg-slate-100 text-slate-400'
                    }`}>
                      {checked ? '✓' : m.name[0]}
                    </div>
                    <div className="text-left min-w-0">
                      <div className="text-xs font-semibold truncate">{m.name}</div>
                      <div className="text-[10px] opacity-70 truncate">{m.role}</div>
                    </div>
                  </button>
                )
              })}
          </div>

          {/* 分页控件 */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between mt-3">
              <button
                type="button"
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                className="flex items-center gap-1 text-xs text-slate-600 hover:text-brand-600 disabled:opacity-30 disabled:cursor-not-allowed px-2 py-1"
              >
                <ChevronLeft size={14} />
                上一页
              </button>
              <div className="flex items-center gap-1">
                {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => setCurrentPage(p)}
                    className={`w-7 h-7 rounded-md text-xs font-medium transition-colors ${
                      p === currentPage
                        ? 'bg-brand-600 text-white'
                        : 'text-slate-600 hover:bg-slate-100'
                    }`}
                  >
                    {p}
                  </button>
                ))}
              </div>
              <button
                type="button"
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
                className="flex items-center gap-1 text-xs text-slate-600 hover:text-brand-600 disabled:opacity-30 disabled:cursor-not-allowed px-2 py-1"
              >
                下一页
                <ChevronRight size={14} />
              </button>
            </div>
          )}
        </div>

        {/* 摘要输入 */}
        <div>
          <label className="block text-sm font-semibold text-slate-700 mb-1.5">事件摘要</label>
          <textarea
            rows={4}
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            placeholder="描述发生的事情、争议或决议。例如：张三认为李四的新技术方案过于保守，两人在会议上激辩，最终张三强行决定采用新方案。"
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 focus:border-transparent resize-none"
          />
        </div>

        {/* 错误提示 */}
        {error && (
          <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">
            <AlertTriangle size={15} />
            {error}
          </div>
        )}

        {/* 提交按钮 */}
        <button
          onClick={handleSubmit}
          disabled={loading}
          className="w-full flex items-center justify-center gap-2 bg-brand-600 text-white py-2.5 rounded-lg font-medium text-sm hover:bg-brand-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? (
            <>
              <Loader2 size={16} className="animate-spin" />
              分析并写入记忆中...
            </>
          ) : (
            <>
              <Send size={16} />
              提交记录
            </>
          )}
        </button>
      </div>

      {/* 解析结果展示 */}
      {result && (
        <div className="mt-6 bg-white rounded-2xl shadow-sm border border-slate-100 p-6 fade-in">
          <div className="flex items-center gap-2 mb-4">
            <CheckCircle2 size={18} className="text-emerald-500" />
            <h3 className="text-sm font-bold text-slate-800">解析完成 · 已写入团队记忆</h3>
            {result.mock_mode && (
              <span className="text-[10px] bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full">
                降级模式
              </span>
            )}
            <span className="text-[10px] bg-slate-100 text-slate-500 px-2 py-0.5 rounded-full">
              置信度 {(result.parsed_analysis.confidence * 100).toFixed(0)}%
            </span>
          </div>

          <div className="space-y-4">
            {/* 事务影响 */}
            <div>
              <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-500 mb-1">
                <Sparkles size={12} /> 事务影响
              </div>
              <p className="text-sm text-slate-700 bg-slate-50 rounded-lg px-3 py-2">
                {result.parsed_analysis.task}
              </p>
            </div>

            {/* 情绪状态 */}
            {result.parsed_analysis.emotions?.length > 0 && (
              <div>
                <div className="text-xs font-semibold text-slate-500 mb-1">情绪状态</div>
                <div className="flex gap-2 flex-wrap">
                  {result.parsed_analysis.emotions.map((emo, i) => (
                    <div key={i} className="bg-brand-50 rounded-lg px-3 py-1.5 text-xs">
                      <span className="font-semibold text-brand-700">{memberName(emo.member_id)}</span>
                      <span className="text-slate-600 ml-1.5">{emo.emotion}</span>
                      <span className="text-slate-400 ml-1">({emo.intensity}/10)</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 关系变化 */}
            {result.parsed_analysis.relations?.length > 0 && (
              <div>
                <div className="text-xs font-semibold text-slate-500 mb-1">关系变化</div>
                <div className="space-y-1.5">
                  {result.parsed_analysis.relations.map((rel, i) => (
                    <div key={i} className="flex items-center gap-2 text-xs bg-slate-50 rounded-lg px-3 py-2">
                      <span className="font-medium text-slate-700">{memberName(rel.from)} → {memberName(rel.to)}</span>
                      <span className={`font-bold ${rel.trust_delta < 0 ? 'text-red-500' : rel.trust_delta > 0 ? 'text-emerald-500' : 'text-slate-400'}`}>
                        信任 {rel.trust_delta > 0 ? '+' : ''}{rel.trust_delta}
                      </span>
                      <span className={`font-bold ${rel.sentiment_delta < 0 ? 'text-red-500' : rel.sentiment_delta > 0 ? 'text-emerald-500' : 'text-slate-400'}`}>
                        情绪 {rel.sentiment_delta > 0 ? '+' : ''}{rel.sentiment_delta}
                      </span>
                      <span className="text-slate-400 ml-auto">{rel.tag}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
