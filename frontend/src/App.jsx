import React, { useState, useEffect, useCallback } from 'react'
import { CalendarPlus, LayoutDashboard, MessageSquareText, Activity, ChevronRight } from 'lucide-react'
import { api } from './api/client.js'
import Dashboard from './components/Dashboard.jsx'
import EventLogger from './components/EventLogger.jsx'
import CalendarView from './components/CalendarView.jsx'
import ChatPanel from './components/ChatPanel.jsx'

const NAV_ITEMS = [
  { id: 'dashboard', label: '总览', icon: LayoutDashboard },
  { id: 'calendar', label: '日历', icon: Activity },
  { id: 'logger', label: '录入事件', icon: CalendarPlus },
  { id: 'chat', label: '智能对话', icon: MessageSquareText },
]

export default function App() {
  const [activeView, setActiveView] = useState('dashboard')
  const [members, setMembers] = useState([])
  const [mockMode, setMockMode] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)
  const [collapsed, setCollapsed] = useState(false)

  const triggerRefresh = useCallback(() => {
    setRefreshKey((k) => k + 1)
  }, [])

  useEffect(() => {
    api.health().then((data) => setMockMode(data.mock_mode)).catch(() => {})
    api.getMembers().then(setMembers).catch(() => {})
  }, [])

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-slate-100">
      {/* 侧边栏 —— 可缩起/展开 */}
      <aside
        className={`bg-slate-900 text-white flex flex-col flex-shrink-0 transition-all duration-300 ease-in-out relative ${
          collapsed ? 'w-[60px]' : 'w-56'
        }`}
      >
        {/* 顶部 Logo 区 */}
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

        {/* 导航菜单 */}
        <nav className="flex-1 p-3 space-y-1">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon
            const active = activeView === item.id
            return (
              <button
                key={item.id}
                onClick={() => setActiveView(item.id)}
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
                {collapsed && active && (
                  <span className="absolute left-[60px] bg-slate-800 text-white text-xs px-2 py-1 rounded-md whitespace-nowrap shadow-lg z-50 pointer-events-none">
                    {item.label}
                  </span>
                )}
              </button>
            )
          })}
        </nav>

        {/* 底部状态区 */}
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
          {!collapsed && (
            <p className="text-[10px] text-slate-500 mt-2 px-3">
              {mockMode ? '未配置 API Key，使用规则引擎' : '硅基流动 DeepSeek'}
            </p>
          )}
        </div>

        {/* 缩起/展开切换按钮 —— 贴在侧边栏右边缘 */}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="absolute -right-3 top-20 w-6 h-6 bg-slate-700 hover:bg-brand-600 text-white rounded-full flex items-center justify-center shadow-lg transition-colors z-50 border-2 border-slate-900"
          title={collapsed ? '展开菜单' : '收起菜单'}
        >
          {collapsed ? <ChevronRight size={14} /> : <ChevronRight size={14} className="rotate-180" />}
        </button>
      </aside>

      {/* 主内容区 */}
      <main className="flex-1 overflow-y-auto">
        {activeView === 'dashboard' && (
          <Dashboard key={refreshKey} members={members} />
        )}
        {activeView === 'calendar' && (
          <CalendarView key={refreshKey} members={members} />
        )}
        {activeView === 'logger' && (
          <EventLogger members={members} onSaved={triggerRefresh} />
        )}
        {activeView === 'chat' && (
          <ChatPanel members={members} key={refreshKey} />
        )}
      </main>
    </div>
  )
}
