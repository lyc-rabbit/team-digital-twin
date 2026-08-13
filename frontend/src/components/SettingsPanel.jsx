import React, { useState, useEffect } from 'react'
import {
  X, Save, Loader2, AlertTriangle, CheckCircle2,
  KeyRound, Server, Cpu, Eye, EyeOff, RotateCw,
} from 'lucide-react'
import { api } from '../api/client.js'

export default function SettingsPanel({ open, onClose, onSaved }) {
  const [config, setConfig] = useState(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)
  const [showKey, setShowKey] = useState(false)
  // 标记 API Key 输入框是否有用户输入(区分"未修改"和"清空")
  const [apiKeyInput, setApiKeyInput] = useState('')
  const [apiKeyEdited, setApiKeyEdited] = useState(false)

  // 加载配置
  useEffect(() => {
    if (!open) return
    setLoading(true)
    setError(null)
    setSuccess(null)
    setApiKeyInput('')
    setApiKeyEdited(false)
    setShowKey(false)
    api.getLlmConfig()
      .then((data) => setConfig(data))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [open])

  const handleApiKeyChange = (val) => {
    setApiKeyInput(val)
    setApiKeyEdited(true)
  }

  const handleSave = async () => {
    if (!config) return
    setSaving(true)
    setError(null)
    setSuccess(null)
    try {
      const payload = {}
      // API Key:只有用户编辑过才提交(空串=清空降级模式)
      if (apiKeyEdited) {
        payload.api_key = apiKeyInput
      }
      if (config.base_url) payload.base_url = config.base_url
      if (config.model_extract) payload.model_extract = config.model_extract
      if (config.model_simulate) payload.model_simulate = config.model_simulate
      if (config.model_chat) payload.model_chat = config.model_chat

      const res = await api.updateLlmConfig(payload)
      setSuccess(res.message)
      onSaved?.()
      // 重新加载配置(显示脱敏后的新 Key)
      const fresh = await api.getLlmConfig()
      setConfig(fresh)
      setApiKeyInput('')
      setApiKeyEdited(false)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  if (!open) return null

  return (
    <div
      className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl shadow-xl max-w-lg w-full max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 头部 */}
        <div className="flex items-center justify-between p-5 border-b border-slate-100">
          <h3 className="font-bold text-slate-800 flex items-center gap-2">
            <Cpu size={18} className="text-brand-600" />
            大模型配置
          </h3>
          <button
            onClick={onClose}
            className="p-1 text-slate-400 hover:text-slate-600 rounded-md"
          >
            <X size={18} />
          </button>
        </div>

        <div className="p-5 space-y-5">
          {loading && (
            <div className="flex items-center justify-center py-8">
              <Loader2 size={24} className="animate-spin text-brand-500" />
            </div>
          )}

          {error && (
            <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">
              <AlertTriangle size={15} />
              {error}
            </div>
          )}

          {success && (
            <div className="flex items-start gap-2 text-sm text-amber-700 bg-amber-50 rounded-lg px-3 py-2">
              <RotateCw size={15} className="mt-0.5 flex-shrink-0" />
              <span>{success}</span>
            </div>
          )}

          {config && !loading && (
            <>
              {/* 当前状态 */}
              <div className={`rounded-lg px-3 py-2 text-xs flex items-center gap-2 ${
                config.mock_mode
                  ? 'bg-amber-50 text-amber-700'
                  : 'bg-emerald-50 text-emerald-700'
              }`}>
                <div className={`w-2 h-2 rounded-full ${
                  config.mock_mode ? 'bg-amber-400 pulse-soft' : 'bg-emerald-400'
                }`} />
                {config.mock_mode ? '当前:降级模式(规则引擎)' : '当前:DeepSeek 已连接'}
              </div>

              {/* API Key */}
              <div>
                <label className="block text-sm font-semibold text-slate-700 mb-1.5 flex items-center gap-1.5">
                  <KeyRound size={14} />
                  硅基流动 API Key
                </label>
                {!apiKeyEdited ? (
                  // 显示当前脱敏值,点击可编辑
                  <div className="flex items-center gap-2">
                    <div className="flex-1 border border-slate-200 rounded-lg px-3 py-2 text-sm bg-slate-50 text-slate-500">
                      {config.api_key_masked || '(未配置,降级模式)'}
                    </div>
                    <button
                      onClick={() => {
                        setApiKeyInput('')
                        setApiKeyEdited(true)
                      }}
                      className="text-xs text-brand-600 hover:text-brand-700 font-medium px-2 py-2"
                    >
                      修改
                    </button>
                  </div>
                ) : (
                  <div className="relative">
                    <input
                      type={showKey ? 'text' : 'password'}
                      value={apiKeyInput}
                      onChange={(e) => handleApiKeyChange(e.target.value)}
                      placeholder="sk-..."
                      className="w-full border border-slate-200 rounded-lg px-3 py-2 pr-9 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 focus:border-transparent"
                    />
                    <button
                      onClick={() => setShowKey(!showKey)}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                    >
                      {showKey ? <EyeOff size={15} /> : <Eye size={15} />}
                    </button>
                    <p className="text-[11px] text-slate-400 mt-1">
                      留空保存=清空(降级模式);在
                      <a href="https://cloud.siliconflow.cn/" target="_blank" rel="noreferrer" className="text-brand-600 hover:underline mx-0.5">
                        siliconflow.cn
                      </a>
                      获取
                    </p>
                  </div>
                )}
              </div>

              {/* Base URL */}
              <div>
                <label className="block text-sm font-semibold text-slate-700 mb-1.5 flex items-center gap-1.5">
                  <Server size={14} />
                  API 端点
                </label>
                <input
                  type="text"
                  value={config.base_url}
                  onChange={(e) => setConfig({ ...config, base_url: e.target.value })}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 focus:border-transparent"
                />
              </div>

              {/* 模型配置 */}
              <div className="space-y-3 pt-2 border-t border-slate-100">
                <p className="text-xs font-semibold text-slate-500">模型配置(按场景分层)</p>

                <div>
                  <label className="block text-xs text-slate-600 mb-1">
                    事件解析 <span className="text-slate-400">(快+便宜)</span>
                  </label>
                  <input
                    type="text"
                    value={config.model_extract}
                    onChange={(e) => setConfig({ ...config, model_extract: e.target.value })}
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 focus:border-transparent"
                  />
                </div>

                <div>
                  <label className="block text-xs text-slate-600 mb-1">
                    模拟推演 <span className="text-slate-400">(深度推理)</span>
                  </label>
                  <input
                    type="text"
                    value={config.model_simulate}
                    onChange={(e) => setConfig({ ...config, model_simulate: e.target.value })}
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 focus:border-transparent"
                  />
                </div>

                <div>
                  <label className="block text-xs text-slate-600 mb-1">
                    智能问答 <span className="text-slate-400">(日常对话)</span>
                  </label>
                  <input
                    type="text"
                    value={config.model_chat}
                    onChange={(e) => setConfig({ ...config, model_chat: e.target.value })}
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 focus:border-transparent"
                  />
                </div>
              </div>

              {error && (
                <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">
                  <AlertTriangle size={15} />
                  {error}
                </div>
              )}
            </>
          )}
        </div>

        {/* 底部按钮 */}
        {config && !loading && (
          <div className="flex gap-2 p-5 border-t border-slate-100">
            <button
              onClick={onClose}
              className="flex-1 border border-slate-200 text-slate-600 py-2 rounded-lg font-medium text-sm hover:bg-slate-50 transition-colors"
            >
              取消
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              className="flex-1 flex items-center justify-center gap-2 bg-brand-600 text-white py-2 rounded-lg font-medium text-sm hover:bg-brand-700 transition-colors disabled:opacity-50"
            >
              {saving ? (
                <>
                  <Loader2 size={15} className="animate-spin" />
                  保存中...
                </>
              ) : (
                <>
                  <Save size={15} />
                  保存配置
                </>
              )}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
