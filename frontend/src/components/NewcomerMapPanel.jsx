import React, { useEffect, useRef, useState } from 'react'
import {
  Map, Plus, ArrowLeft, Loader2, Sparkles, BookOpen, ListTodo, Target, ShieldAlert,
} from 'lucide-react'
import { api } from '../api/client.js'
import { beijingToday } from '../utils/beijingTime.js'
import { RecordEventButton } from './EventRecorderContext.jsx'

const LEVEL_DOT = {
  required: { cls: 'bg-red-50 text-red-700 border-red-100', label: '必须介入', icon: '🔴' },
  attention: { cls: 'bg-amber-50 text-amber-700 border-amber-100', label: '建议介入', icon: '🟡' },
  none: { cls: 'bg-emerald-50 text-emerald-700 border-emerald-100', label: '正常', icon: '🟢' },
}

export default function NewcomerMapPanel({ members }) {
  const [overview, setOverview] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [view, setView] = useState('list')
  const [detail, setDetail] = useState(null)
  const [addOpen, setAddOpen] = useState(false)
  const mountedRef = useRef(true)

  const loadOverview = async () => {
    const data = await api.listNewcomers()
    if (mountedRef.current) setOverview(data)
  }

  useEffect(() => {
    mountedRef.current = true
    ;(async () => {
      try {
        await loadOverview()
      } catch (err) {
        if (mountedRef.current) setError(err.message || '加载失败')
      } finally {
        if (mountedRef.current) setLoading(false)
      }
    })()
    return () => { mountedRef.current = false }
  }, [])

  const openDetail = async (employeeId) => {
    setError(null)
    const d = await api.getNewcomer(employeeId)
    setDetail(d)
    setView('detail')
  }

  if (loading) {
    return <div className="flex items-center justify-center h-full text-slate-400 text-sm">加载新人地图...</div>
  }

  if (view === 'detail' && detail) {
    return (
      <NewcomerDetail
        detail={detail}
        setDetail={setDetail}
        onBack={async () => {
          setView('list')
          setDetail(null)
          await loadOverview()
        }}
        onError={setError}
      />
    )
  }

  const summary = overview?.summary || {}
  const cards = overview?.newcomers || []

  return (
    <div className="p-6 max-w-6xl mx-auto fade-in space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
            <Map size={20} className="text-brand-600" />
            新人地图
          </h2>
          <p className="text-sm text-slate-500 mt-1">新人现在到哪里了？下一步做什么？什么时候需要你介入？</p>
        </div>
        <button
          onClick={() => setAddOpen(true)}
          className="flex items-center gap-1.5 text-sm font-medium text-white bg-brand-600 hover:bg-brand-700 px-3.5 py-2 rounded-lg"
        >
          <Plus size={15} /> 添加新人
        </button>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <Stat label="新人" value={summary.newcomer_count ?? 0} />
        <Stat label="需要我介入" value={summary.need_intervention ?? 0} accent="text-amber-600" />
        <Stat label="正常推进" value={summary.on_track ?? 0} accent="text-emerald-600" />
      </div>

      {error && <div className="text-xs bg-red-50 text-red-700 rounded-lg px-3 py-2">{error}</div>}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {cards.map((c) => (
          <button
            key={c.id}
            onClick={() => openDetail(c.employee_id)}
            className="text-left bg-white rounded-2xl border border-slate-100 p-5 hover:border-brand-200 transition-colors"
          >
            <div className="flex items-start justify-between mb-2">
              <div>
                <div className="font-bold text-slate-800">{c.employee_name}</div>
                <div className="text-[11px] text-slate-400">入职第 {c.days} 天</div>
              </div>
              <span className={`text-[10px] px-1.5 py-0.5 rounded border ${LEVEL_DOT[c.intervention_level]?.cls}`}>
                {LEVEL_DOT[c.intervention_level]?.icon} {LEVEL_DOT[c.intervention_level]?.label}
              </span>
            </div>
            <dl className="text-xs text-slate-600 space-y-1.5">
              <Row label="当前阶段" value={c.onboarding_stage_label} />
              <Row label="当前角色" value={c.current_role || '—'} />
              <Row label="目标角色" value={c.target_role || '未设置'} />
              <Row label="当前任务" value={c.current_task?.task_name || '暂无'} />
            </dl>
            <div className="mt-3 h-1.5 bg-slate-100 rounded-full overflow-hidden">
              <div className="h-full bg-brand-500" style={{ width: `${c.progress || 0}%` }} />
            </div>
            <div className="mt-3 text-xs font-medium text-brand-600">查看新人 →</div>
          </button>
        ))}
      </div>

      {cards.length === 0 && (
        <div className="bg-white rounded-2xl border border-slate-100 py-16 text-center text-sm text-slate-400">
          还没有新人。点击右上角添加，系统会自动生成入职指南和 L0 项目探索任务。
        </div>
      )}

      {addOpen && (
        <AddModal
          members={members}
          existing={new Set(cards.map((c) => c.employee_id))}
          roles={overview?.roles || []}
          onClose={() => setAddOpen(false)}
          onCreated={async (d) => {
            setAddOpen(false)
            setDetail(d)
            setView('detail')
            await loadOverview()
          }}
          onError={setError}
        />
      )}
    </div>
  )
}

function NewcomerDetail({ detail, setDetail, onBack, onError }) {
  const nc = detail.newcomer
  const [tab, setTab] = useState('overview')
  const [busy, setBusy] = useState(false)
  const [guideEdit, setGuideEdit] = useState(false)
  const [guideDraft, setGuideDraft] = useState('')
  const [pollKind, setPollKind] = useState(null)

  useEffect(() => {
    if (!pollKind) return
    let stop = false
    ;(async () => {
      for (let i = 0; i < 80; i++) {
        if (stop) return
        const st = await api.getNewcomerAnalysisStatus(nc.employee_id, pollKind)
        if (st.status === 'success' || st.status === 'failed' || st.status === 'idle') {
          const d = await api.getNewcomer(nc.employee_id)
          setDetail(d)
          setPollKind(null)
          setBusy(false)
          if (st.status === 'failed') onError(st.message || '分析失败')
          return
        }
        await new Promise((r) => setTimeout(r, 1200))
      }
      setPollKind(null)
      setBusy(false)
    })()
    return () => { stop = true }
  }, [pollKind, nc.employee_id])

  const refresh = async () => {
    const d = await api.getNewcomer(nc.employee_id)
    setDetail(d)
  }

  const runGenerate = async () => {
    setBusy(true)
    await api.generateNewcomerGuide(nc.employee_id)
    setPollKind('guide')
  }

  const runRecommend = async () => {
    setBusy(true)
    await api.recommendNewcomerTasks(nc.employee_id)
    setPollKind('recommend')
  }

  const analyzing = busy || pollKind

  return (
    <div className="p-6 max-w-4xl mx-auto fade-in space-y-5">
      <button onClick={onBack} className="flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700">
        <ArrowLeft size={15} /> 返回新人地图
      </button>

      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-800">{nc.employee_name}</h2>
          <p className="text-sm text-slate-500 mt-1">入职第 {nc.days} 天 · {nc.current_role}</p>
        </div>
        <div className="flex items-center gap-2">
          <RecordEventButton context={{
            source: 'newcomer-map',
            person_id: nc.employee_id,
            newcomer_id: nc.id,
            stage_id: nc.onboarding_stage,
            role_id: nc.target_role_id,
            event_type: 'communication',
            event_tag: 'problem_raise',
          }} label="记录事件" />
          <label className="text-xs text-slate-600 flex items-center gap-2 bg-white border border-slate-200 rounded-lg px-3 py-2">
          <input
            type="checkbox"
            checked={!!nc.compete_in_ranking}
            onChange={async (e) => {
              const d = await api.setNewcomerTargetRole(nc.employee_id, {
                target_role_id: nc.target_role_id,
                compete_in_ranking: e.target.checked,
              })
              setDetail(d)
            }}
          />
          参与角色竞争
        </label>
        </div>
      </div>

      {analyzing && (
        <div className="bg-brand-50 border border-brand-100 rounded-xl px-4 py-3 text-sm text-brand-700 flex items-center gap-2">
          <Loader2 size={14} className="animate-spin" />
          {pollKind === 'guide' ? '正在生成入职指南…' : pollKind === 'recommend' ? '正在推荐培养任务…' : '处理中…'}
          <span className="text-[11px] text-brand-600">可切换页面，任务会继续</span>
        </div>
      )}

      <div className="flex gap-2 text-xs">
        {[
          ['overview', '总览'],
          ['stages', '阶段培养'],
          ['guide', '入职指南'],
          ['tasks', '培养任务'],
        ].map(([id, label]) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`px-3 py-1.5 rounded-lg ${tab === id ? 'bg-brand-600 text-white' : 'bg-white border border-slate-200 text-slate-600'}`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'overview' && (
        <div className="space-y-4">
          <section className="bg-white rounded-2xl border border-slate-100 p-5">
            <h3 className="text-sm font-bold text-slate-800 mb-2 flex items-center gap-1.5"><Target size={14} /> 当前目标角色</h3>
            <div className="flex items-center gap-3">
              <TargetRoleSelect nc={nc} setDetail={setDetail} />
              {detail.match_score != null && (
                <span className="text-sm font-bold text-brand-600">匹配度 {detail.match_score}</span>
              )}
            </div>
          </section>

          <section className="bg-white rounded-2xl border border-slate-100 p-5">
            <h3 className="text-sm font-bold text-slate-800 mb-3">培养阶段</h3>
            <ol className="space-y-2">
              {(detail.stages || []).map((s, i) => (
                <li key={s.id} className="flex items-center gap-2 text-sm">
                  <span className={`w-5 h-5 rounded-full text-[11px] flex items-center justify-center ${
                    s.state === 'done' ? 'bg-emerald-500 text-white' : s.state === 'current' ? 'bg-brand-600 text-white' : 'bg-slate-200 text-slate-500'
                  }`}>
                    {s.state === 'done' ? '✓' : i + 1}
                  </span>
                  <span className={s.state === 'current' ? 'font-semibold text-slate-800' : 'text-slate-600'}>{s.label}</span>
                </li>
              ))}
            </ol>
          </section>

          <section className="bg-white rounded-2xl border border-slate-100 p-5">
            <h3 className="text-sm font-bold text-slate-800 mb-2 flex items-center gap-1.5"><ListTodo size={14} /> 当前任务</h3>
            {detail.current_task ? (
              <TaskBlock
                task={detail.current_task}
                onChange={async (payload) => {
                  const res = await api.updateNewcomerTask(detail.current_task.id, payload)
                  if (res.detail) setDetail(res.detail)
                  else await refresh()
                }}
                onComplete={async () => {
                  const d = await api.completeNewcomerTask(detail.current_task.id)
                  setDetail(d)
                }}
              />
            ) : (
              <p className="text-xs text-slate-400">暂无进行中任务。可在「培养任务」中推荐下一任务。</p>
            )}
          </section>

          <section className="bg-white rounded-2xl border border-slate-100 p-5">
            <h3 className="text-sm font-bold text-slate-800 mb-3">能力成长</h3>
            <div className="space-y-2">
              {(detail.capabilities || []).map((c) => (
                <div key={c.id}>
                  <div className="flex justify-between text-[11px] text-slate-500 mb-0.5">
                    <span>{c.name}</span><span>{Math.round(c.score)}</span>
                  </div>
                  <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                    <div className="h-full bg-brand-500" style={{ width: `${Math.min(100, c.score)}%` }} />
                  </div>
                </div>
              ))}
            </div>
            {detail.gaps?.length > 0 && (
              <p className="text-[11px] text-slate-400 mt-3">能力差距：{detail.gaps.join('、')}</p>
            )}
          </section>

          <section className="bg-white rounded-2xl border border-slate-100 p-5">
            <h3 className="text-sm font-bold text-slate-800 mb-2">下一步</h3>
            <p className="text-sm text-slate-700">{detail.suggested_next}</p>
            <p className="text-xs text-slate-400 mt-1">系统建议：完成后进入下一等级真实任务。排名只作管理辅助，不作为人事结论。</p>
          </section>

          <section className="bg-white rounded-2xl border border-slate-100 p-5">
            <h3 className="text-sm font-bold text-slate-800 mb-2 flex items-center gap-1.5"><ShieldAlert size={14} /> 需要负责人介入</h3>
            {(detail.interventions || []).length === 0 ? (
              <p className="text-xs text-slate-400">无</p>
            ) : (
              <div className="space-y-2">
                {detail.interventions.map((iv) => (
                  <div key={iv.id} className={`rounded-lg border px-3 py-2 text-xs ${LEVEL_DOT[iv.level]?.cls || ''}`}>
                    <div className="font-medium">{LEVEL_DOT[iv.level]?.icon} {iv.reason}</div>
                    <div className="mt-0.5">建议：{iv.recommended_action}</div>
                    <button
                      className="mt-1 text-brand-600"
                      onClick={async () => {
                        await api.resolveNewcomerIntervention(iv.id)
                        await refresh()
                      }}
                    >
                      标记已处理
                    </button>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      )}

      {tab === 'stages' && (
        <StageRecordsTab detail={detail} onRefresh={refresh} />
      )}

      {tab === 'guide' && (
        <GuideTab
          detail={detail}
          guideEdit={guideEdit}
          setGuideEdit={setGuideEdit}
          guideDraft={guideDraft}
          setGuideDraft={setGuideDraft}
          analyzing={analyzing}
          onGenerate={runGenerate}
          onPublish={async () => {
            const d = await api.publishNewcomerGuide(nc.employee_id)
            setDetail(d)
          }}
          onSave={async () => {
            let content
            try {
              content = JSON.parse(guideDraft)
            } catch {
              onError('指南内容需为合法 JSON')
              return
            }
            await api.saveNewcomerGuide(nc.employee_id, { content, status: 'draft' })
            setGuideEdit(false)
            await refresh()
          }}
        />
      )}

      {tab === 'tasks' && (
        <TasksTab
          detail={detail}
          analyzing={analyzing}
          onRecommend={runRecommend}
          onRefresh={refresh}
          setDetail={setDetail}
        />
      )}
    </div>
  )
}

function TargetRoleSelect({ nc, setDetail }) {
  const [roles, setRoles] = useState([])
  useEffect(() => {
    api.getAiNativeRoles().then((d) => setRoles(d.roles || [])).catch(() => {})
  }, [])
  return (
    <select
      className="text-sm border border-slate-200 rounded-lg px-3 py-2 flex-1"
      value={nc.target_role_id || ''}
      onChange={async (e) => {
        const d = await api.setNewcomerTargetRole(nc.employee_id, {
          target_role_id: e.target.value,
          compete_in_ranking: nc.compete_in_ranking,
        })
        setDetail(d)
      }}
    >
      <option value="">未指定目标角色</option>
      {roles.map((r) => (
        <option key={r.id} value={r.id}>{r.name}</option>
      ))}
    </select>
  )
}

function GuideTab({ detail, guideEdit, setGuideEdit, guideDraft, setGuideDraft, analyzing, onGenerate, onPublish, onSave }) {
  const guide = detail.guide
  const sections = guide?.content?.sections || []
  return (
    <section className="bg-white rounded-2xl border border-slate-100 p-5 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-bold text-slate-800 flex items-center gap-1.5"><BookOpen size={14} /> 入职指南</h3>
        <div className="flex gap-2">
          <button disabled={analyzing} onClick={onGenerate} className="text-xs font-medium text-white bg-brand-600 disabled:opacity-50 px-2.5 py-1.5 rounded-lg flex items-center gap-1">
            <Sparkles size={12} /> AI 生成
          </button>
          <button onClick={() => {
            setGuideDraft(JSON.stringify(guide?.content || {}, null, 2))
            setGuideEdit(true)
          }} className="text-xs border border-slate-200 px-2.5 py-1.5 rounded-lg">编辑</button>
          <button onClick={onPublish} className="text-xs border border-brand-200 text-brand-700 px-2.5 py-1.5 rounded-lg">发布</button>
        </div>
      </div>
      <p className="text-[11px] text-slate-400">状态：{guide?.status || '无'} · 来源：{guide?.source || '—'}</p>
      {guideEdit ? (
        <div>
          <textarea className="w-full h-64 text-xs font-mono border border-slate-200 rounded-lg p-2" value={guideDraft} onChange={(e) => setGuideDraft(e.target.value)} />
          <div className="flex justify-end gap-2 mt-2">
            <button className="text-xs text-slate-500" onClick={() => setGuideEdit(false)}>取消</button>
            <button className="text-xs bg-brand-600 text-white px-3 py-1.5 rounded-lg" onClick={onSave}>保存草稿</button>
          </div>
        </div>
      ) : (
        <ol className="space-y-3">
          {sections.map((s) => (
            <li key={s.id}>
              <div className="text-xs font-semibold text-slate-800">{s.id} {s.title}</div>
              <p className="text-xs text-slate-600 mt-0.5 leading-relaxed">{s.body}</p>
            </li>
          ))}
          {!sections.length && <p className="text-xs text-slate-400">尚未生成指南</p>}
        </ol>
      )}
    </section>
  )
}

function TasksTab({ detail, analyzing, onRecommend, onRefresh, setDetail }) {
  return (
    <section className="bg-white rounded-2xl border border-slate-100 p-5 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-bold text-slate-800">培养任务 L0–L5</h3>
        <button disabled={analyzing} onClick={onRecommend} className="text-xs font-medium text-white bg-brand-600 disabled:opacity-50 px-2.5 py-1.5 rounded-lg">
          生成下一任务
        </button>
      </div>
      <p className="text-[11px] text-slate-400">不能直接跳到 L4。负责人可在任务上改等级。完成任务会写入能力证据，并影响目标角色匹配。</p>
      <div className="space-y-3">
        {(detail.tasks || []).map((t) => (
          <div key={t.id} className="border border-slate-100 rounded-xl p-3">
            <TaskBlock
              task={t}
              onChange={async (payload) => {
                const res = await api.updateNewcomerTask(t.id, payload)
                if (res.detail) setDetail(res.detail)
                else await onRefresh()
              }}
              onComplete={async () => {
                const d = await api.completeNewcomerTask(t.id)
                setDetail(d)
              }}
            />
          </div>
        ))}
        {!(detail.tasks || []).length && <p className="text-xs text-slate-400">暂无任务</p>}
      </div>
      {(detail.evidence || []).length > 0 && (
        <div className="pt-2 border-t border-slate-100">
          <div className="text-xs font-semibold text-slate-700 mb-2">能力证据</div>
          <ul className="text-[11px] text-slate-500 space-y-1">
            {detail.evidence.slice(0, 12).map((e) => (
              <li key={e.id}>✓ {e.capability_name} · {e.evidence_content}（{e.score}）</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}

function TaskBlock({ task, onChange, onComplete }) {
  return (
    <div>
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-sm font-semibold text-slate-800">{task.task_name}</div>
          <div className="text-[11px] text-slate-400 mt-0.5">
            {task.task_level} · 预计 {task.estimated_hours} 小时 · {task.ai_allowed ? '允许 AI' : '不允许 AI'} · {task.review_required ? '需要 Review' : '无需 Review'}
          </div>
        </div>
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">{task.status}</span>
      </div>
      {task.description && <p className="text-xs text-slate-600 mt-2 leading-relaxed">{task.description}</p>}
      {task.requirements?.length > 0 && (
        <ul className="text-xs text-slate-500 mt-2 list-disc list-inside">
          {task.requirements.map((r) => <li key={r}>{r}</li>)}
        </ul>
      )}
      <div className="flex flex-wrap gap-2 mt-3">
        {task.status === 'todo' && (
          <button className="text-[11px] bg-brand-600 text-white px-2 py-1 rounded" onClick={() => onChange({ status: 'in_progress' })}>开始</button>
        )}
        {task.status === 'in_progress' && (
          <>
            <button className="text-[11px] bg-emerald-600 text-white px-2 py-1 rounded" onClick={onComplete}>完成并记录证据</button>
            <button className="text-[11px] border border-amber-200 text-amber-700 px-2 py-1 rounded" onClick={() => onChange({ status: 'blocked', blocked_reason: '推进受阻' })}>标记阻塞</button>
            <button className="text-[11px] border border-slate-200 px-2 py-1 rounded" onClick={() => onChange({ help_requested: true })}>请求帮助</button>
          </>
        )}
        {task.status === 'blocked' && (
          <button className="text-[11px] bg-brand-600 text-white px-2 py-1 rounded" onClick={() => onChange({ status: 'in_progress', blocked_reason: '' })}>恢复进行</button>
        )}
        {['L0', 'L1', 'L2', 'L3', 'L4', 'L5'].map((lv) => (
          <button
            key={lv}
            className={`text-[10px] px-1.5 py-0.5 rounded ${task.task_level === lv ? 'bg-slate-800 text-white' : 'bg-slate-100 text-slate-500'}`}
            onClick={() => onChange({ task_level: lv })}
          >
            {lv}
          </button>
        ))}
      </div>
    </div>
  )
}

function AddModal({ members, existing, roles, onClose, onCreated, onError }) {
  const available = members.filter((m) => !existing.has(m.id))
  const [employeeId, setEmployeeId] = useState(available[0]?.id || '')
  const [entryDate, setEntryDate] = useState(beijingToday)
  const [targetRoleId, setTargetRoleId] = useState('developer')
  const [compete, setCompete] = useState(false)
  const [saving, setSaving] = useState(false)

  const save = async () => {
    if (!employeeId) return
    setSaving(true)
    try {
      const d = await api.createNewcomer({
        employee_id: employeeId,
        entry_date: entryDate,
        target_role_id: targetRoleId,
        compete_in_ranking: compete,
      })
      onCreated(d)
    } catch (e) {
      onError(e.message || '创建失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl w-full max-w-md p-5" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-sm font-bold text-slate-800 mb-3">添加新人</h3>
        <label className="block text-xs text-slate-600 mb-2">
          成员
          <select className="mt-1 w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={employeeId} onChange={(e) => setEmployeeId(e.target.value)}>
            {available.map((m) => <option key={m.id} value={m.id}>{m.name} · {m.role}</option>)}
          </select>
        </label>
        <label className="block text-xs text-slate-600 mb-2">
          入职日期
          <input type="date" className="mt-1 w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={entryDate} onChange={(e) => setEntryDate(e.target.value)} />
        </label>
        <label className="block text-xs text-slate-600 mb-2">
          目标角色
          <select className="mt-1 w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" value={targetRoleId} onChange={(e) => setTargetRoleId(e.target.value)}>
            {roles.map((r) => <option key={r.id} value={r.id}>{r.role_name}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-2 text-xs text-slate-600 mb-4">
          <input type="checkbox" checked={compete} onChange={(e) => setCompete(e.target.checked)} />
          新人是否参与角色竞争（刚入职建议关闭）
        </label>
        {!available.length && <p className="text-xs text-amber-600 mb-2">没有可添加的成员</p>}
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="text-sm text-slate-500 px-3 py-2">取消</button>
          <button onClick={save} disabled={saving || !employeeId} className="text-sm font-medium text-white bg-brand-600 disabled:opacity-50 px-3.5 py-2 rounded-lg">
            {saving ? '创建中...' : '创建'}
          </button>
        </div>
      </div>
    </div>
  )
}

function StageRecordsTab({ detail, onRefresh }) {
  const nc = detail.newcomer || {}
  const records = detail.stage_records || []
  const [openId, setOpenId] = useState(records.find((s) => s.stage_id === nc.onboarding_stage)?.stage_id || records[0]?.stage_id)
  const rec = records.find((s) => s.stage_id === openId) || records[0]
  const [form, setForm] = useState(rec || {})
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setForm(records.find((s) => s.stage_id === openId) || {})
  }, [openId, detail])

  const save = async () => {
    setSaving(true)
    try {
      await api.saveNewcomerStage(nc.employee_id, form.stage_id, {
        stage_goal: form.stage_goal,
        role_requirements: form.role_requirements,
        human_ai_division: form.human_ai_division,
        self_eval: form.self_eval,
        mentor_eval: form.mentor_eval,
        result: form.result,
        passed: form.passed,
      })
      await onRefresh()
    } finally {
      setSaving(false)
    }
  }

  const setDivision = (idx, key, value) => {
    const rows = [...(form.human_ai_division || [])]
    rows[idx] = { ...rows[idx], [key]: value }
    setForm({ ...form, human_ai_division: rows })
  }

  if (!records.length) {
    return <p className="text-xs text-slate-400">暂无阶段记录。保存一次事件后会自动带出当前阶段。</p>
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-1.5">
        {records.map((s) => (
          <button key={s.stage_id} onClick={() => setOpenId(s.stage_id)}
            className={`text-xs px-3 py-1.5 rounded-full border ${openId === s.stage_id ? 'bg-brand-600 text-white border-brand-600' : 'bg-white border-slate-200 text-slate-600'}`}>
            {s.stage_label}{s.passed ? ' ✓' : ''}
          </button>
        ))}
      </div>
      {form && (
        <section className="bg-white rounded-2xl border border-slate-100 p-5 space-y-3">
          <h3 className="text-sm font-bold text-slate-800">{form.stage_label}</h3>
          <label className="block text-xs text-slate-600">阶段目标
            <textarea className="mt-1 w-full border rounded-lg px-3 py-2 text-sm" rows={2} value={form.stage_goal || ''} onChange={(e) => setForm({ ...form, stage_goal: e.target.value })} />
          </label>
          <label className="block text-xs text-slate-600">岗位要求
            <textarea className="mt-1 w-full border rounded-lg px-3 py-2 text-sm" rows={2} value={form.role_requirements || ''} onChange={(e) => setForm({ ...form, role_requirements: e.target.value })} />
          </label>
          <div>
            <div className="text-xs font-semibold text-slate-700 mb-2">人 / AI 分工</div>
            <table className="w-full text-xs">
              <thead>
                <tr className="text-slate-400">
                  <th className="text-left py-1">工作项</th>
                  <th>人</th>
                  <th>AI</th>
                  <th>最终责任</th>
                </tr>
              </thead>
              <tbody>
                {(form.human_ai_division || []).map((row, i) => (
                  <tr key={row.item || i} className="border-t border-slate-50">
                    <td className="py-1.5">{row.item}</td>
                    <td className="text-center">{cellMark(row.human)}</td>
                    <td className="text-center">{cellMark(row.ai)}</td>
                    <td className="text-center">
                      <select className="border rounded px-1 py-0.5" value={row.owner || '人'} onChange={(e) => setDivision(i, 'owner', e.target.value)}>
                        <option>人</option>
                        <option>AI</option>
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <label className="block text-xs text-slate-600">新人自评
            <textarea className="mt-1 w-full border rounded-lg px-3 py-2 text-sm" rows={2} value={form.self_eval || ''} onChange={(e) => setForm({ ...form, self_eval: e.target.value })} />
          </label>
          <label className="block text-xs text-slate-600">导师评价
            <textarea className="mt-1 w-full border rounded-lg px-3 py-2 text-sm" rows={2} value={form.mentor_eval || ''} onChange={(e) => setForm({ ...form, mentor_eval: e.target.value })} />
          </label>
          <label className="block text-xs text-slate-600">阶段结果
            <textarea className="mt-1 w-full border rounded-lg px-3 py-2 text-sm" rows={2} value={form.result || ''} onChange={(e) => setForm({ ...form, result: e.target.value })} />
          </label>
          <div>
            <div className="text-xs font-semibold text-slate-700 mb-1">事实事件</div>
            {(form.events || []).length === 0 ? <p className="text-xs text-slate-400">本阶段还没有关联事件</p> : form.events.map((e) => (
              <div key={e.id} className="text-xs text-slate-600 py-1 border-b border-slate-50">
                {(e.event_time || '').slice(0, 10)} · {(e.raw_summary || '').slice(0, 80)}
              </div>
            ))}
          </div>
          <label className="flex items-center gap-2 text-xs text-slate-600">
            <input type="checkbox" checked={!!form.passed} onChange={(e) => setForm({ ...form, passed: e.target.checked })} />
            本阶段已达标
          </label>
          <button onClick={save} disabled={saving} className="text-sm bg-brand-600 text-white px-3 py-1.5 rounded-lg disabled:opacity-50">
            {saving ? '保存中...' : '保存阶段记录'}
          </button>
        </section>
      )}
    </div>
  )
}

function cellMark(v) {
  if (v === true || v === 'yes') return '✅'
  if (v === false || v === 'no') return '❌'
  if (v === 'review') return 'Review'
  if (v === 'assist') return '辅助'
  return String(v || '—')
}

function Stat({ label, value, accent }) {
  return (
    <div className="bg-white rounded-2xl p-5 border border-slate-100">
      <div className="text-xs text-slate-500">{label}</div>
      <div className={`text-3xl font-bold text-slate-800 mt-1 ${accent || ''}`}>{value}</div>
    </div>
  )
}

function Row({ label, value }) {
  return (
    <div className="flex justify-between gap-2">
      <span className="text-slate-400">{label}</span>
      <span className="font-medium text-slate-700 truncate">{value}</span>
    </div>
  )
}
