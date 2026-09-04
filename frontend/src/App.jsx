import React, { useState, useEffect, useCallback } from 'react'
import {
  LayoutDashboard, MessageSquareText, Activity, ChevronRight, Users, Settings,
  Sparkles, FileSpreadsheet, Network, TrendingUp, Map, Radar, FolderKanban,
  Layers, Award, ArrowUpRight, Plus, FlaskConical, GitFork, Clock, ScrollText,
} from 'lucide-react'
import { api } from './api/client.js'
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
import SettingsPanel from './components/SettingsPanel.jsx'
import { EventRecorderProvider, useEventRecorder } from './components/EventRecorderContext.jsx'

const NAV_GROUPS = [
  {
    id: 'glance',
    label: '看团队',
    items: [
      { id: 'team-situation', label: '团队态势', icon: Radar },
      { id: 'dashboard', label: '总览', icon: LayoutDashboard },
      { id: 'calendar', label: '日历', icon: Activity },
      { id: 'daily-report', label: '日报', icon: FileSpreadsheet },
    ],
  },
  {
    id: 'work',
    label: '做项目',
    items: [
      { id: 'project-center', label: '项目中心', icon: FolderKanban },
    ],
  },
  {
    id: 'people',
    label: '带人成长',
    items: [
      { id: 'newcomer-map', label: '新人地图', icon: Map },
      { id: 'cadre-growth', label: '干部成长', icon: Award },
      { id: 'upward', label: '向上协同', icon: ArrowUpRight },
      { id: 'ai-native', label: '角色卡', icon: Sparkles },
      { id: 'promotion', label: '晋升领导', icon: TrendingUp },
    ],
  },
  {
    id: 'org',
    label: '看关系',
    items: [
      { id: 'influence-graph', label: '人物关系网', icon: Network },
      { id: 'fact-governance', label: '事实管理', icon: ScrollText },
      { id: 'entity-governance', label: '实体治理', icon: Layers },
      { id: 'ontology-governance', label: '本体治理', icon: GitFork },
      { id: 'temporal-graph', label: '时间轴分析', icon: Clock },
    ],
  },
  {
    id: 'sim',
    label: '推演',
    items: [
      { id: 'sim-lab', label: '模拟实验室', icon: FlaskConical },
      { id: 'chat', label: '智能对话', icon: MessageSquareText },
    ],
  },
  {
    id: 'admin',
    label: '配置',
    items: [
      { id: 'members', label: '成员管理', icon: Users },
    ],
  },
]

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

export default function App() {
  const [activeView, setActiveView] = useState('team-situation')
  const [members, setMembers] = useState([])
  const [mockMode, setMockMode] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)
  const [collapsed, setCollapsed] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [openProjectId, setOpenProjectId] = useState(null)

  const triggerRefresh = useCallback(() => {
    setRefreshKey((k) => k + 1)
  }, [])

  useEffect(() => {
    api.health().then((data) => setMockMode(data.mock_mode)).catch(() => {})
    api.getMembers().then(setMembers).catch(() => {})
  }, [refreshKey])

  return (
    <EventRecorderProvider members={members} onSaved={triggerRefresh}>
      <div className="flex h-screen w-screen overflow-hidden bg-slate-100">
        <aside
          className={`bg-slate-900 text-white flex flex-col flex-shrink-0 transition-all duration-300 ease-in-out relative ${
            collapsed ? 'w-[60px]' : 'w-56'
          }`}
        >
          <div className={`p-5 border-b border-slate-700 flex items-center ${collapsed ? 'justify-center' : ''}`}>
            <div className="flex items-center gap-2 overflow-hidden">
              <div className="w-9 h-9 bg-brand-500 rounded-lg flex items-center justify-center text-lg flex-shrink-0">
                👥
              </div>
              {!collapsed && (
                <div className="fade-in whitespace-nowrap">
                  <h1 className="font-bold text-sm leading-tight">团队数字孪生</h1>
                  <p className="text-[10px] text-slate-400">Digital Twin System</p>
                </div>
              )}
            </div>
          </div>

          <nav className="flex-1 p-3 space-y-4 overflow-y-auto">
            {NAV_GROUPS.map((group) => (
              <div key={group.id} className="space-y-1">
                {!collapsed && (
                  <div className="px-3 pt-1 pb-0.5 text-[10px] font-semibold tracking-wide text-slate-500">
                    {group.label}
                  </div>
                )}
                {collapsed && group.id !== NAV_GROUPS[0].id && (
                  <div className="mx-2 my-1 border-t border-slate-700" />
                )}
                {group.items.map((item) => {
                  const Icon = item.icon
                  const active = activeView === item.id
                  return (
                    <button
                      key={item.id}
                      onClick={() => {
                        setActiveView(item.id)
                        if (item.id !== 'project-center') setOpenProjectId(null)
                      }}
                      title={collapsed ? item.label : ''}
                      className={`w-full flex items-center rounded-lg text-sm font-medium transition-all ${
                        collapsed ? 'justify-center px-0 py-2.5' : 'gap-3 px-3 py-2.5'
                      } ${
                        active
                          ? 'bg-brand-600 text-white'
                          : 'text-slate-400 hover:bg-slate-800 hover:text-white'
                      }`}
                    >
                      <Icon size={17} className="flex-shrink-0" />
                      {!collapsed && <span className="whitespace-nowrap">{item.label}</span>}
                    </button>
                  )
                })}
              </div>
            ))}
          </nav>

          <div className="p-3 border-t border-slate-700">
            <div
              className={`rounded-lg text-xs flex items-center ${
                collapsed ? 'justify-center px-0 py-2' : 'gap-2 px-3 py-2'
              } ${mockMode ? 'bg-amber-500/15 text-amber-300' : 'bg-emerald-500/15 text-emerald-300'}`}
              title={mockMode ? '降级模式 · 未配置 API Key，使用规则引擎' : 'DeepSeek 已连接 · 硅基流动'}
            >
              <div className={`rounded-full flex-shrink-0 ${mockMode ? 'bg-amber-400 pulse-soft' : 'bg-emerald-400'} ${collapsed ? 'w-2.5 h-2.5' : 'w-2 h-2'}`} />
              {!collapsed && <span>{mockMode ? '降级模式' : 'DeepSeek 已连接'}</span>}
            </div>
            <button
              onClick={() => setSettingsOpen(true)}
              title="配置大模型"
              className={`mt-2 w-full flex items-center rounded-lg text-xs font-medium transition-all text-slate-400 hover:bg-slate-800 hover:text-white ${
                collapsed ? 'justify-center px-0 py-2' : 'gap-2 px-3 py-2'
              }`}
            >
              <Settings size={14} className="flex-shrink-0" />
              {!collapsed && <span>配置</span>}
            </button>
          </div>

          <button
            onClick={() => setCollapsed(!collapsed)}
            className="absolute -right-3 top-20 w-6 h-6 bg-slate-700 hover:bg-brand-600 text-white rounded-full flex items-center justify-center shadow-lg transition-colors z-50 border-2 border-slate-900"
            title={collapsed ? '展开菜单' : '收起菜单'}
          >
            {collapsed ? <ChevronRight size={14} /> : <ChevronRight size={14} className="rotate-180" />}
          </button>
        </aside>

        <main className="flex-1 overflow-y-auto relative">
          {activeView === 'dashboard' && (
            <Dashboard key={refreshKey} members={members} />
          )}
          {activeView === 'calendar' && (
            <CalendarView key={refreshKey} members={members} />
          )}
          {activeView === 'members' && (
            <MemberManager members={members} onMembersChange={triggerRefresh} />
          )}
          {activeView === 'daily-report' && (
            <DailyReportPanel members={members} />
          )}
          {activeView === 'project-center' && (
            <ProjectCenterPanel members={members} initialProjectId={openProjectId} />
          )}
          {activeView === 'team-situation' && (
            <TeamSituationPanel
              members={members}
              onOpenProject={(id) => {
                setOpenProjectId(id)
                setActiveView('project-center')
              }}
            />
          )}
          {activeView === 'ai-native' && (
            <AiNativePanel members={members} />
          )}
          {activeView === 'newcomer-map' && (
            <NewcomerMapPanel members={members} />
          )}
          {activeView === 'cadre-growth' && (
            <CadreGrowthPanel members={members} />
          )}
          {activeView === 'upward' && (
            <UpwardCollabPanel members={members} />
          )}
          {activeView === 'influence-graph' && (
            <InfluenceGraphPanel members={members} />
          )}
          {activeView === 'fact-governance' && (
            <FactGovernancePanel />
          )}
          {activeView === 'entity-governance' && (
            <EntityGovernancePanel />
          )}
          {activeView === 'ontology-governance' && (
            <OntologyGovernancePanel />
          )}
          {activeView === 'temporal-graph' && (
            <TemporalGraphPanel members={members} />
          )}
          {activeView === 'promotion' && (
            <PromotionPanel members={members} />
          )}
          {activeView === 'sim-lab' && (
            <SimulationLabPanel members={members} />
          )}
          {activeView === 'chat' && (
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
