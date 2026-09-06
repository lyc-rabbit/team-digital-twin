import React, { useState, useEffect, useCallback, useMemo } from 'react'
import { ChevronRight, ChevronDown, Settings, Plus } from 'lucide-react'
import NavIcon from './components/NavIcon.jsx'
import { api } from './api/client.js'
import {
  OBSERVERS, groupsForObserver, findNavItem, observerById,
  readObserver, writeObserver,
} from './ia.js'
import Dashboard from './components/Dashboard.jsx'
import CalendarView from './components/CalendarView.jsx'
import ChatPanel from './components/ChatPanel.jsx'
import MemberManager from './components/MemberManager.jsx'
import AiNativePanel from './components/AiNativePanel.jsx'
import DailyReportPanel from './components/DailyReportPanel.jsx'
import InfluenceGraphPanel from './components/InfluenceGraphPanel.jsx'
import PromotionPanel from './components/PromotionPanel.jsx'
import NewcomerMapPanel from './components/NewcomerMapPanel.jsx'
import TeamSituationPanel from './components/TeamSituationPanel.jsx'
import ProjectCenterPanel from './components/ProjectCenterPanel.jsx'
import CadreGrowthPanel from './components/CadreGrowthPanel.jsx'
import UpwardCollabPanel from './components/UpwardCollabPanel.jsx'
import SimulationLabPanel from './components/SimulationLabPanel.jsx'
import EntityGovernancePanel from './components/EntityGovernancePanel.jsx'
import OntologyGovernancePanel from './components/OntologyGovernancePanel.jsx'
import TemporalGraphPanel from './components/TemporalGraphPanel.jsx'
import FactGovernancePanel from './components/FactGovernancePanel.jsx'
import OrgCockpitPanel from './components/OrgCockpitPanel.jsx'
import SettingsPanel from './components/SettingsPanel.jsx'
import { EventRecorderProvider, useEventRecorder } from './components/EventRecorderContext.jsx'

function EventFab() {
  const { openDraft } = useEventRecorder()
  return (
    <button
      type="button"
      onClick={() => openDraft({ source: 'global' })}
      className="fixed right-6 bottom-6 z-40 w-14 h-14 rounded-full bg-brand-600 hover:bg-brand-700 text-white shadow-lg flex items-center justify-center"
      title="记录事件"
    >
      <Plus size={22} />
    </button>
  )
}

function groupOf(itemId) {
  return findNavItem(itemId)?.group || null
}

export default function App() {
  const [observerId, setObserverId] = useState(readObserver)
  const observer = observerById(observerId)
  const navGroups = useMemo(() => groupsForObserver(observerId), [observerId])

  const [activeView, setActiveView] = useState(() => observerById(readObserver()).home)
  const [members, setMembers] = useState([])
  const [mockMode, setMockMode] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)
  const [collapsed, setCollapsed] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [openProjectId, setOpenProjectId] = useState(null)
  const [openGroups, setOpenGroups] = useState(() => {
    const g = groupOf(observerById(readObserver()).home)
    return g ? { [g.id]: true } : { team: true }
  })

  const triggerRefresh = useCallback(() => {
    setRefreshKey((k) => k + 1)
  }, [])

  useEffect(() => {
    api.health().then((data) => setMockMode(data.mock_mode)).catch(() => {})
    api.getMembers().then(setMembers).catch(() => {})
  }, [refreshKey])

  useEffect(() => {
    const hit = findNavItem(activeView)
    if (!hit || (hit.group.hideFor || []).includes(observerId)) {
      setActiveView(observerById(observerId).home)
    }
  }, [activeView, observerId])

  const go = useCallback((itemId, extra = {}) => {
    const hit = findNavItem(itemId)
    if (!hit) return
    if ((hit.group.hideFor || []).includes(observerId)) return
    setActiveView(itemId)
    setOpenGroups((prev) => ({ ...prev, [hit.group.id]: true }))
    if (hit.item.view !== 'project-center') setOpenProjectId(null)
    if (extra.projectId) {
      setOpenProjectId(extra.projectId)
      setActiveView('work-detail')
    }
  }, [observerId])

  const switchObserver = (id) => {
    writeObserver(id)
    setObserverId(id)
    const next = observerById(id)
    const hit = findNavItem(next.home)
    setActiveView(next.home)
    setOpenProjectId(null)
    setOpenGroups(hit ? { [hit.group.id]: true } : {})
  }

  const navHit = findNavItem(activeView)
  const currentGroup = navHit?.group
  const currentItem = navHit?.item
  const view = currentItem?.view
  const viewProps = currentItem?.props || {}

  const toggleGroup = (group) => {
    setOpenGroups((prev) => ({ ...prev, [group.id]: !prev[group.id] }))
  }

  const openProject = (id) => {
    setOpenProjectId(id)
    setActiveView('work-detail')
    setOpenGroups((prev) => ({ ...prev, work: true }))
  }

  return (
    <EventRecorderProvider members={members} onSaved={triggerRefresh}>
      <div className="flex h-screen w-screen overflow-hidden bg-white">
        <aside
          className={`bg-white text-slate-800 border-r border-slate-100 flex flex-col flex-shrink-0 transition-all duration-300 ease-in-out relative ${
            collapsed ? 'w-[60px]' : 'w-64'
          }`}
        >
          <div className={`p-4 border-b border-slate-100 ${collapsed ? 'px-2' : ''}`}>
            <div className={`flex items-center gap-2 ${collapsed ? 'justify-center' : ''}`}>
              <img
                src="/favicon.svg"
                alt=""
                className="w-9 h-9 rounded-lg flex-shrink-0"
              />
              {!collapsed && (
                <div className="fade-in min-w-0">
                  <h1 className="font-bold text-sm leading-tight text-slate-900">团队数字孪生</h1>
                  <p className="text-[10px] text-slate-400 truncate">同一事实 · 多视角</p>
                </div>
              )}
            </div>
            {!collapsed && (
              <div className="mt-3">
                <div className="text-[10px] text-slate-400 mb-1">当前视角</div>
                <select
                  value={observerId}
                  onChange={(e) => switchObserver(e.target.value)}
                  className="w-full bg-white border border-slate-200 rounded-lg text-xs text-slate-800 px-2 py-1.5 outline-none focus:border-brand-400 focus:ring-1 focus:ring-brand-100"
                >
                  {OBSERVERS.map((o) => (
                    <option key={o.id} value={o.id}>{o.label}</option>
                  ))}
                </select>
                <p className="text-[10px] text-slate-400 mt-1.5 leading-relaxed">{observer.question}</p>
              </div>
            )}
            {collapsed && (
              <button
                type="button"
                title={`${observer.label}视角`}
                onClick={() => setCollapsed(false)}
                className="mt-2 w-full text-center text-[10px] text-slate-500"
              >
                {observer.label.slice(0, 1)}
              </button>
            )}
          </div>

          <nav className="flex-1 p-2 space-y-1 overflow-y-auto">
            {navGroups.map((group) => {
              const open = !!openGroups[group.id]
              const groupActive = currentGroup?.id === group.id
              return (
                <div key={group.id}>
                  <button
                    type="button"
                    onClick={() => {
                      if (collapsed) {
                        setCollapsed(false)
                        setOpenGroups((prev) => ({ ...prev, [group.id]: true }))
                        go(group.items[0].id)
                        return
                      }
                      toggleGroup(group)
                    }}
                    title={collapsed ? group.label : group.question}
                    className={`w-full flex items-center rounded-lg text-[13px] font-medium transition-all ${
                      collapsed ? 'justify-center px-0 py-2' : 'gap-2 px-2.5 py-2'
                    } ${
                      groupActive
                        ? 'bg-brand-50 text-brand-800'
                        : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                    }`}
                  >
                    <NavIcon name={group.icon} size={16} className="text-brand-600" />
                    {!collapsed && (
                      <>
                        <span className="flex-1 text-left truncate">{group.label}</span>
                        {open ? <ChevronDown size={14} className="text-slate-400" /> : <ChevronRight size={14} className="text-slate-400" />}
                      </>
                    )}
                  </button>
                  {!collapsed && open && (
                    <div className="mt-0.5 mb-2 ml-2 pl-2 border-l border-slate-200 space-y-0.5">
                      {group.items.map((item) => {
                        const active = activeView === item.id
                        return (
                          <button
                            key={item.id}
                            type="button"
                            onClick={() => go(item.id)}
                            title={item.question}
                            className={`w-full text-left px-2.5 py-1.5 rounded-md text-xs transition-colors ${
                              active
                                ? 'bg-brand-600 text-white'
                                : 'text-slate-500 hover:bg-slate-50 hover:text-slate-800'
                            }`}
                          >
                            {item.label}
                          </button>
                        )
                      })}
                    </div>
                  )}
                </div>
              )
            })}
          </nav>

          <div className="p-3 border-t border-slate-100">
            <div
              className={`rounded-lg text-xs flex items-center ${
                collapsed ? 'justify-center px-0 py-2' : 'gap-2 px-3 py-2'
              } ${mockMode ? 'bg-amber-50 text-amber-700' : 'bg-emerald-50 text-emerald-700'}`}
              title={mockMode ? '降级模式 · 未配置 API Key，使用规则引擎' : 'DeepSeek 已连接 · 硅基流动'}
            >
              <div className={`rounded-full flex-shrink-0 ${mockMode ? 'bg-amber-400 pulse-soft' : 'bg-emerald-400'} ${collapsed ? 'w-2.5 h-2.5' : 'w-2 h-2'}`} />
              {!collapsed && <span>{mockMode ? '降级模式' : 'DeepSeek 已连接'}</span>}
            </div>
            <button
              onClick={() => setSettingsOpen(true)}
              title="配置大模型"
              className={`mt-2 w-full flex items-center rounded-lg text-xs font-medium transition-all text-slate-500 hover:bg-slate-50 hover:text-slate-800 ${
                collapsed ? 'justify-center px-0 py-2' : 'gap-2 px-3 py-2'
              }`}
            >
              <Settings size={14} className="flex-shrink-0" />
              {!collapsed && <span>配置</span>}
            </button>
          </div>

          <button
            onClick={() => setCollapsed(!collapsed)}
            className="absolute -right-3 top-20 w-6 h-6 bg-white hover:bg-brand-600 hover:text-white text-slate-500 rounded-full flex items-center justify-center shadow-md transition-colors z-50 border border-slate-200 hover:border-brand-600"
            title={collapsed ? '展开菜单' : '收起菜单'}
          >
            {collapsed ? <ChevronRight size={14} /> : <ChevronRight size={14} className="rotate-180" />}
          </button>
        </aside>

        <main className="flex-1 overflow-y-auto relative bg-white">
          {currentItem && view !== 'org-cockpit' && (
            <div className="px-6 pt-4 pb-3 border-b border-slate-100">
              <div className="text-[11px] text-slate-400">
                {currentGroup?.label}
                <span className="mx-1.5">·</span>
                {observer.label}视角
              </div>
              <p className="text-xs text-slate-500 mt-0.5">
                正在回答：{currentItem.question || currentGroup?.question}
              </p>
            </div>
          )}
          {view === 'org-cockpit' && (
            <OrgCockpitPanel
              key={refreshKey}
              members={members}
              onNavigate={go}
              onOpenProject={openProject}
            />
          )}
          {view === 'dashboard' && (
            <Dashboard key={refreshKey} members={members} />
          )}
          {view === 'calendar' && (
            <CalendarView key={refreshKey} members={members} />
          )}
          {view === 'members' && (
            <MemberManager members={members} onMembersChange={triggerRefresh} />
          )}
          {view === 'daily-report' && (
            <DailyReportPanel members={members} />
          )}
          {view === 'project-center' && (
            <ProjectCenterPanel members={members} initialProjectId={openProjectId} />
          )}
          {view === 'team-situation' && (
            <TeamSituationPanel
              key={activeView}
              members={members}
              initialTab={viewProps.initialTab || 'today'}
              onOpenProject={openProject}
            />
          )}
          {view === 'ai-native' && (
            <AiNativePanel members={members} />
          )}
          {view === 'newcomer-map' && (
            <NewcomerMapPanel members={members} />
          )}
          {view === 'cadre-growth' && (
            <CadreGrowthPanel members={members} />
          )}
          {view === 'upward' && (
            <UpwardCollabPanel members={members} />
          )}
          {view === 'influence-graph' && (
            <InfluenceGraphPanel
              key={viewProps.preset || 'overview'}
              members={members}
              preset={viewProps.preset || 'overview'}
            />
          )}
          {view === 'fact-governance' && (
            <FactGovernancePanel key={viewProps.initialTab || 'all'} initialTab={viewProps.initialTab || 'all'} />
          )}
          {view === 'entity-governance' && (
            <EntityGovernancePanel />
          )}
          {view === 'ontology-governance' && (
            <OntologyGovernancePanel key={viewProps.initialTab || 'analyze'} initialTab={viewProps.initialTab || 'analyze'} />
          )}
          {view === 'temporal-graph' && (
            <TemporalGraphPanel
              key={viewProps.initialTab || 'snapshot'}
              members={members}
              initialTab={viewProps.initialTab || 'snapshot'}
            />
          )}
          {view === 'promotion' && (
            <PromotionPanel members={members} />
          )}
          {view === 'sim-lab' && (
            <SimulationLabPanel
              key={viewProps.initialTab || 'simulate'}
              members={members}
              initialTab={viewProps.initialTab || 'simulate'}
            />
          )}
          {view === 'chat' && (
            <ChatPanel members={members} key={refreshKey} />
          )}
          <EventFab />
        </main>

        <SettingsPanel
          open={settingsOpen}
          onClose={() => setSettingsOpen(false)}
          onSaved={triggerRefresh}
        />
      </div>
    </EventRecorderProvider>
  )
}
