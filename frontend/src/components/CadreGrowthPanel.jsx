import React, { useEffect, useState } from 'react'
import { Award, Loader2 } from 'lucide-react'
import { api } from '../api/client.js'
import { RecordEventButton } from './EventRecorderContext.jsx'

const STATUS_CLS = {
  '已验证': 'text-emerald-700 bg-emerald-50',
  '形成中': 'text-amber-700 bg-amber-50',
  '未验证': 'text-slate-500 bg-slate-100',
}

export default function CadreGrowthPanel({ members = [] }) {
  const [profiles, setProfiles] = useState([])
  const [selected, setSelected] = useState(null)
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.listCadreProfiles().then((d) => {
      setProfiles(d.profiles || [])
      if (!selected && (d.profiles || [])[0]) setSelected(d.profiles[0].person_id)
    }).catch((e) => setError(e.message)).finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!selected) return
    api.getCadreProfile(selected).then(setDetail).catch((e) => setError(e.message))
  }, [selected])

  if (loading) {
    return <div className="flex items-center justify-center h-full text-slate-400 text-sm"><Loader2 size={16} className="animate-spin mr-2" />加载干部成长档案...</div>
  }

  return (
    <div className="p-6 max-w-6xl mx-auto fade-in space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
            <Award size={20} className="text-brand-600" /> 干部成长
          </h2>
          <p className="text-sm text-slate-500 mt-1">第一期只做成长档案：已完成经历、能力验证状态、缺失经历。不做复杂算法。</p>
        </div>
        <RecordEventButton context={{ source: 'cadre', person_id: selected, event_type: 'people_development' }} />
      </div>
      {error && <div className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</div>}

      <div className="grid grid-cols-1 lg:grid-cols-[240px_1fr] gap-4">
        <aside className="bg-white rounded-2xl border border-slate-100 p-3 space-y-1">
          {profiles.map((p) => (
            <button key={p.person_id} onClick={() => setSelected(p.person_id)}
              className={`w-full text-left px-3 py-2 rounded-lg text-sm ${selected === p.person_id ? 'bg-brand-50 text-brand-800' : 'hover:bg-slate-50 text-slate-700'}`}>
              <div className="font-semibold">{p.name}</div>
              <div className="text-[11px] text-slate-400">{p.current_stage}</div>
            </button>
          ))}
          {!profiles.length && <p className="text-xs text-slate-400 p-3">暂无成员</p>}
        </aside>

        {detail && (
          <div className="space-y-4">
            <section className="bg-white rounded-2xl border border-slate-100 p-5">
              <div className="text-[11px] text-slate-400">当前阶段</div>
              <h3 className="text-lg font-bold text-slate-800 mt-0.5">{detail.current_stage}</h3>
              <p className="text-sm text-slate-500">{detail.name} · {detail.role}</p>
            </section>
            <section className="bg-white rounded-2xl border border-slate-100 p-5">
              <h3 className="text-sm font-bold text-slate-800 mb-2">已完成经历</h3>
              {(detail.experiences || []).length ? (
                <ul className="text-sm text-slate-700 space-y-1">
                  {detail.experiences.map((x) => <li key={x}>· {x}</li>)}
                </ul>
              ) : <p className="text-xs text-slate-400">尚无项目或培养经历。请从项目中心或事件录入补充。</p>}
            </section>
            <section className="bg-white rounded-2xl border border-slate-100 p-5">
              <h3 className="text-sm font-bold text-slate-800 mb-3">能力</h3>
              <div className="space-y-2">
                {(detail.capabilities || []).map((c) => (
                  <div key={c.id} className="flex items-center justify-between text-sm">
                    <span className="text-slate-700">{c.label}</span>
                    <span className={`text-[11px] font-medium px-2 py-0.5 rounded ${STATUS_CLS[c.status] || STATUS_CLS['未验证']}`}>{c.status}</span>
                  </div>
                ))}
              </div>
            </section>
            <section className="bg-white rounded-2xl border border-slate-100 p-5">
              <h3 className="text-sm font-bold text-slate-800 mb-2">缺失经历</h3>
              {(detail.missing_experiences || []).length ? (
                <ul className="text-sm text-amber-800 space-y-1">
                  {detail.missing_experiences.map((x) => <li key={x}>· {x}</li>)}
                </ul>
              ) : <p className="text-xs text-emerald-700">关键经历较完整</p>}
            </section>
          </div>
        )}
      </div>
    </div>
  )
}
