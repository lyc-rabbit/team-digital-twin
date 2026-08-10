import React, { useState, useRef, useEffect } from 'react'
import { Send, Loader2, MessageSquareText, FlaskConical, User, Bot } from 'lucide-react'
import { api } from '../api/client.js'

const SAMPLE_QUESTIONS = [
  '分析近一周张三和李四之间的合作状态，有哪些潜在风险？',
  '目前团队中谁和谁的关系最紧张？原因是什么？',
  '王五在团队中扮演什么角色？他对团队氛围有什么影响？',
]

const SAMPLE_SCENARIOS = [
  '老板突然要求下周上线新版，周末全员加班',
  '张三提出要砍掉李四负责的技术重构计划，把人力全部转到新功能',
  '一个重要客户威胁要流失，需要团队 48 小时内给出应对方案',
]

function renderMarkdown(text) {
  // 简易 Markdown 渲染：处理标题、加粗、列表
  if (!text) return ''
  let html = text
    // 转义 HTML
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    // 代码块
    .replace(/```([\s\S]*?)```/g, '<pre class="bg-slate-800 text-slate-100 rounded-lg p-3 overflow-x-auto text-xs my-2">$1</pre>')
    // 标题
    .replace(/^### (.+)$/gm, '<h4 class="font-bold text-slate-800 mt-3 mb-1">$1</h4>')
    .replace(/^## (.+)$/gm, '<h3 class="font-bold text-slate-800 mt-3 mb-1">$1</h3>')
    // 加粗
    .replace(/\*\*(.+?)\*\*/g, '<strong class="font-semibold text-slate-700">$1</strong>')
    // 引用块
    .replace(/^&gt; (.+)$/gm, '<blockquote class="border-l-2 border-amber-400 bg-amber-50 pl-3 py-1 text-amber-700 text-xs my-1">$1</blockquote>')
    // 列表
    .replace(/^- (.+)$/gm, '<li class="ml-4 text-slate-600">$1</li>')
    // 换行
    .replace(/\n/g, '<br/>')

  return html
}

export default function ChatPanel({ members }) {
  const [mode, setMode] = useState('query') // 'query' | 'simulate'
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const scrollRef = useRef(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages, loading])

  const handleSend = async (text) => {
    const content = text || input
    if (!content.trim() || loading) return

    const userMsg = { role: 'user', content, mode }
    setMessages((prev) => [...prev, userMsg])
    setInput('')
    setLoading(true)

    try {
      let res
      if (mode === 'query') {
        res = await api.query(content)
      } else {
        res = await api.simulate(content)
      }
      const aiMsg = { role: 'ai', content: res.response, mode, mockMode: res.mock_mode }
      setMessages((prev) => [...prev, aiMsg])
    } catch (err) {
      setMessages((prev) => [...prev, { role: 'ai', content: `出错: ${err.message}`, mode, error: true }])
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const switchMode = (newMode) => {
    setMode(newMode)
    setMessages([])
    setInput('')
  }

  return (
    <div className="flex flex-col h-full fade-in">
      {/* 头部 */}
      <div className="px-6 py-4 border-b border-slate-200 bg-white">
        <div className="flex items-center gap-2 mb-3">
          {mode === 'query' ? <MessageSquareText size={20} className="text-brand-600" /> : <FlaskConical size={20} className="text-brand-600" />}
          <h2 className="text-lg font-bold text-slate-800">
            {mode === 'query' ? '智能问答 · 团队知心者' : '模拟推演 · 行为预测引擎'}
          </h2>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => switchMode('query')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              mode === 'query' ? 'bg-brand-600 text-white' : 'bg-slate-100 text-slate-500 hover:bg-slate-200'
            }`}
          >
            <MessageSquareText size={13} /> 问答模式
          </button>
          <button
            onClick={() => switchMode('simulate')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              mode === 'simulate' ? 'bg-brand-600 text-white' : 'bg-slate-100 text-slate-500 hover:bg-slate-200'
            }`}
          >
            <FlaskConical size={13} /> 模拟推演
          </button>
        </div>
      </div>

      {/* 对话区域 */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-6 space-y-4">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div className="text-4xl mb-3">{mode === 'query' ? '🧠' : '🔮'}</div>
            <h3 className="text-sm font-semibold text-slate-700 mb-1">
              {mode === 'query' ? '基于团队历史记忆回答你的问题' : '输入假设场景，推演团队 3 人的反应'}
            </h3>
            <p className="text-xs text-slate-400 mb-6 max-w-md">
              {mode === 'query'
                ? '系统会检索所有历史事件、关系变化和情绪状态，给出有理有据的分析'
                : '结合人设、当前关系状态和历史事件，模拟每人的心理活动、公开表态和最终决定'}
            </p>

            {/* 示例提示 */}
            <div className="w-full max-w-xl space-y-2">
              <p className="text-[11px] text-slate-400 font-medium">
                {mode === 'query' ? '试试这些问题：' : '试试这些场景：'}
              </p>
              {(mode === 'query' ? SAMPLE_QUESTIONS : SAMPLE_SCENARIOS).map((sample, i) => (
                <button
                  key={i}
                  onClick={() => handleSend(sample)}
                  className="w-full text-left text-xs text-slate-600 bg-white border border-slate-200 rounded-lg px-3 py-2.5 hover:border-brand-300 hover:bg-brand-50 transition-colors"
                >
                  {sample}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
            {/* 头像 */}
            <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${
              msg.role === 'user' ? 'bg-brand-600 text-white' : msg.error ? 'bg-red-100 text-red-500' : 'bg-slate-700 text-white'
            }`}>
              {msg.role === 'user' ? <User size={15} /> : <Bot size={15} />}
            </div>

            {/* 消息内容 */}
            <div className={`max-w-[75%] ${msg.role === 'user' ? 'items-end' : ''}`}>
              {msg.mockMode && (
                <div className="text-[10px] text-amber-600 bg-amber-50 inline-block px-2 py-0.5 rounded-full mb-1">
                  降级模式（规则引擎）
                </div>
              )}
              <div
                className={`rounded-2xl px-4 py-2.5 text-sm ${
                  msg.role === 'user'
                    ? 'bg-brand-600 text-white rounded-tr-sm'
                    : msg.error
                    ? 'bg-red-50 text-red-600 rounded-tl-sm'
                    : 'bg-white border border-slate-100 text-slate-700 rounded-tl-sm shadow-sm'
                }`}
              >
                {msg.role === 'ai' && !msg.error ? (
                  <div dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }} />
                ) : (
                  msg.content
                )}
              </div>
            </div>
          </div>
        ))}

        {/* 加载中 */}
        {loading && (
          <div className="flex gap-3">
            <div className="w-8 h-8 rounded-full bg-slate-700 text-white flex items-center justify-center flex-shrink-0">
              <Bot size={15} />
            </div>
            <div className="bg-white border border-slate-100 rounded-2xl rounded-tl-sm shadow-sm px-4 py-3 flex items-center gap-2">
              <Loader2 size={14} className="animate-spin text-slate-400" />
              <span className="text-xs text-slate-400">
                {mode === 'query' ? '检索团队记忆中...' : '推演团队行为中...'}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* 输入框 */}
      <div className="p-4 border-t border-slate-200 bg-white">
        <div className="flex gap-2 items-end">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={1}
            placeholder={
              mode === 'query'
                ? '输入关于团队的问题...'
                : '描述一个假设场景，如：项目延期，要求本周全员加班...'
            }
            className="flex-1 border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 focus:border-transparent resize-none max-h-32"
            style={{ minHeight: '40px' }}
          />
          <button
            onClick={() => handleSend()}
            disabled={loading || !input.trim()}
            className="bg-brand-600 text-white p-2.5 rounded-lg hover:bg-brand-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Send size={16} />
          </button>
        </div>
        <p className="text-[10px] text-slate-300 mt-1.5">
          {mode === 'query' ? '问答模式基于历史事件和关系数据作答' : '模拟推演使用 DeepSeek-R1 深度推理（降级模式用规则引擎）'}
        </p>
      </div>
    </div>
  )
}
