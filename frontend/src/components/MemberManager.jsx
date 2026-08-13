import React, { useState } from 'react'
import {
  UserPlus, Pencil, Trash2, X, Save, Loader2,
  AlertTriangle, CheckCircle2, Users,
} from 'lucide-react'
import { api } from '../api/client.js'

const EMPTY_FORM = {
  id: '',
  name: '',
  role: '',
  persona: '',
  decision_style: '',
  weaknesses: '',
}

export default function MemberManager({ members, onMembersChange }) {
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)

  const openCreate = () => {
    setForm(EMPTY_FORM)
    setEditingId(null)
    setError(null)
    setShowForm(true)
  }

  const openEdit = (m) => {
    setForm({
      id: m.id,
      name: m.name || '',
      role: m.role || '',
      persona: m.persona || '',
      decision_style: m.decision_style || '',
      weaknesses: m.weaknesses || '',
    })
    setEditingId(m.id)
    setError(null)
    setShowForm(true)
  }

  const closeForm = () => {
    setShowForm(false)
    setEditingId(null)
    setForm(EMPTY_FORM)
    setError(null)
  }

  const handleSubmit = async () => {
    if (!form.id.trim() || !form.name.trim() || !form.role.trim() || !form.persona.trim()) {
      setError('ID、姓名、角色、人设不能为空')
      return
    }
    setLoading(true)
    setError(null)
    setSuccess(null)
    try {
      if (editingId) {
        // 编辑模式:不传 id(id 不可改)
        await api.updateMember(editingId, {
          name: form.name,
          role: form.role,
          persona: form.persona,
          decision_style: form.decision_style || undefined,
          weaknesses: form.weaknesses || undefined,
        })
        setSuccess(`成员「${form.name}」已更新`)
      } else {
        await api.createMember({
          id: form.id,
          name: form.name,
          role: form.role,
          persona: form.persona,
          decision_style: form.decision_style || undefined,
          weaknesses: form.weaknesses || undefined,
        })
        setSuccess(`成员「${form.name}」已新增`)
      }
      setShowForm(false)
      setForm(EMPTY_FORM)
      onMembersChange?.()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async (m) => {
    if (!window.confirm(`确认删除成员「${m.name}」?\n\n历史事件将保留为不可变事实,但该成员的关系日志和情绪日志会被级联删除。`)) {
      return
    }
    setLoading(true)
    setError(null)
    try {
      const res = await api.deleteMember(m.id)
      setSuccess(res.message || `成员「${m.name}」已删除`)
      onMembersChange?.()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="p-6 max-w-5xl mx-auto fade-in">
      {/* 头部 */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
            <Users size={20} className="text-brand-600" />
            团队成员管理
          </h2>
          <p className="text-sm text-slate-500 mt-1">
            管理团队成员的人设、决策风格与弱点。共 {members.length} 位成员
          </p>
        </div>
        <button
          onClick={openCreate}
          className="flex items-center gap-2 bg-brand-600 text-white px-4 py-2 rounded-lg font-medium text-sm hover:bg-brand-700 transition-colors"
        >
          <UserPlus size={16} />
          新增成员
        </button>
      </div>

      {/* 提示条 */}
      {error && (
        <div className="mb-4 flex items-center gap-2 text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">
          <AlertTriangle size={15} />
          {error}
        </div>
      )}
      {success && (
        <div className="mb-4 flex items-center gap-2 text-sm text-emerald-700 bg-emerald-50 rounded-lg px-3 py-2">
          <CheckCircle2 size={15} />
          {success}
        </div>
      )}

      {/* 成员列表 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {members.map((m) => (
          <div
            key={m.id}
            className="bg-white rounded-2xl shadow-sm border border-slate-100 p-5 hover:shadow-md transition-shadow"
          >
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-brand-100 text-brand-700 flex items-center justify-center font-bold">
                  {m.name[0]}
                </div>
                <div>
                  <h3 className="font-bold text-slate-800">{m.name}</h3>
                  <p className="text-xs text-slate-500">{m.role}</p>
                </div>
              </div>
              <div className="flex gap-1">
                <button
                  onClick={() => openEdit(m)}
                  className="p-1.5 text-slate-400 hover:text-brand-600 hover:bg-brand-50 rounded-md transition-colors"
                  title="编辑"
                >
                  <Pencil size={15} />
                </button>
                <button
                  onClick={() => handleDelete(m)}
                  className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-md transition-colors"
                  title="删除"
                >
                  <Trash2 size={15} />
                </button>
              </div>
            </div>

            <div className="space-y-2 text-xs">
              <div>
                <span className="font-semibold text-slate-600">人设:</span>
                <span className="text-slate-600 ml-1">{m.persona}</span>
              </div>
              {m.decision_style && (
                <div>
                  <span className="font-semibold text-slate-600">决策风格:</span>
                  <span className="text-slate-600 ml-1">{m.decision_style}</span>
                </div>
              )}
              {m.weaknesses && (
                <div>
                  <span className="font-semibold text-slate-600">弱点:</span>
                  <span className="text-slate-600 ml-1">{m.weaknesses}</span>
                </div>
              )}
              <div className="pt-2 mt-2 border-t border-slate-100 text-[10px] text-slate-400">
                ID: {m.id}
              </div>
            </div>
          </div>
        ))}
      </div>

      {members.length === 0 && (
        <div className="text-center py-12 text-slate-400">
          <Users size={40} className="mx-auto mb-2 opacity-50" />
          <p className="text-sm">暂无成员,点击右上角「新增成员」开始</p>
        </div>
      )}

      {/* 弹窗表单 */}
      {showForm && (
        <div
          className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4"
          onClick={closeForm}
        >
          <div
            className="bg-white rounded-2xl shadow-xl max-w-lg w-full max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between p-5 border-b border-slate-100">
              <h3 className="font-bold text-slate-800">
                {editingId ? '编辑成员' : '新增成员'}
              </h3>
              <button
                onClick={closeForm}
                className="p-1 text-slate-400 hover:text-slate-600 rounded-md"
              >
                <X size={18} />
              </button>
            </div>

            <div className="p-5 space-y-4">
              {/* ID */}
              <div>
                <label className="block text-sm font-semibold text-slate-700 mb-1.5">
                  成员 ID <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={form.id}
                  onChange={(e) => setForm({ ...form, id: e.target.value })}
                  disabled={!!editingId}
                  placeholder="如:user_d(英文+下划线,创建后不可改)"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 focus:border-transparent disabled:bg-slate-50 disabled:text-slate-400"
                />
              </div>

              {/* 姓名 */}
              <div>
                <label className="block text-sm font-semibold text-slate-700 mb-1.5">
                  姓名 <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="如:赵六"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 focus:border-transparent"
                />
              </div>

              {/* 角色 */}
              <div>
                <label className="block text-sm font-semibold text-slate-700 mb-1.5">
                  角色 <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={form.role}
                  onChange={(e) => setForm({ ...form, role: e.target.value })}
                  placeholder="如:设计师、测试负责人"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 focus:border-transparent"
                />
              </div>

              {/* 人设 */}
              <div>
                <label className="block text-sm font-semibold text-slate-700 mb-1.5">
                  人设描述 <span className="text-red-500">*</span>
                </label>
                <textarea
                  rows={3}
                  value={form.persona}
                  onChange={(e) => setForm({ ...form, persona: e.target.value })}
                  placeholder="性格、沟通风格、做事偏好等"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 focus:border-transparent resize-none"
                />
              </div>

              {/* 决策风格 */}
              <div>
                <label className="block text-sm font-semibold text-slate-700 mb-1.5">
                  决策风格 <span className="text-slate-400 font-normal">(可选)</span>
                </label>
                <input
                  type="text"
                  value={form.decision_style}
                  onChange={(e) => setForm({ ...form, decision_style: e.target.value })}
                  placeholder="如:数据导向、直觉驱动、折中"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 focus:border-transparent"
                />
              </div>

              {/* 弱点 */}
              <div>
                <label className="block text-sm font-semibold text-slate-700 mb-1.5">
                  弱点 / 雷区 <span className="text-slate-400 font-normal">(可选)</span>
                </label>
                <textarea
                  rows={2}
                  value={form.weaknesses}
                  onChange={(e) => setForm({ ...form, weaknesses: e.target.value })}
                  placeholder="容易被什么激怒、哪些场景下决策会失准"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 focus:border-transparent resize-none"
                />
              </div>

              {error && (
                <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">
                  <AlertTriangle size={15} />
                  {error}
                </div>
              )}
            </div>

            <div className="flex gap-2 p-5 border-t border-slate-100">
              <button
                onClick={closeForm}
                className="flex-1 border border-slate-200 text-slate-600 py-2 rounded-lg font-medium text-sm hover:bg-slate-50 transition-colors"
              >
                取消
              </button>
              <button
                onClick={handleSubmit}
                disabled={loading}
                className="flex-1 flex items-center justify-center gap-2 bg-brand-600 text-white py-2 rounded-lg font-medium text-sm hover:bg-brand-700 transition-colors disabled:opacity-50"
              >
                {loading ? (
                  <>
                    <Loader2 size={15} className="animate-spin" />
                    保存中...
                  </>
                ) : (
                  <>
                    <Save size={15} />
                    {editingId ? '保存修改' : '新增'}
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
