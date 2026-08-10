import React, { useState, useEffect, useRef } from 'react'
import FullCalendar from '@fullcalendar/react'
import dayGridPlugin from '@fullcalendar/daygrid'
import timeGridPlugin from '@fullcalendar/timegrid'
import interactionPlugin from '@fullcalendar/interaction'
import { X, Clock, Users as UsersIcon } from 'lucide-react'
import { api } from '../api/client.js'

const SCENE_COLORS = {
  '排期会议': '#ef4444',
  '冲突场景': '#dc2626',
  '周会决策': '#6366f1',
  '非正式交流': '#22c55e',
  '自动分类': '#f59e0b',
}

function getEventColor(scene) {
  for (const key of Object.keys(SCENE_COLORS)) {
    if (scene && scene.includes(key)) return SCENE_COLORS[key]
  }
  return '#64748b'
}

export default function CalendarView({ members }) {
  const [events, setEvents] = useState([])
  const [selectedEvent, setSelectedEvent] = useState(null)
  const [eventDetail, setEventDetail] = useState(null)
  const calendarRef = useRef(null)

  const memberName = (id) => members.find((m) => m.id === id)?.name || id

  useEffect(() => {
    loadEvents()
  }, [])

  const loadEvents = async () => {
    try {
      const data = await api.getEvents()
      const fcEvents = data.map((e) => ({
        id: String(e.id),
        title: e.scene || '团队事件',
        start: e.event_time,
        backgroundColor: getEventColor(e.scene),
        borderColor: getEventColor(e.scene),
        extendedProps: e,
      }))
      setEvents(fcEvents)
    } catch (err) {
      console.error('加载事件失败:', err)
    }
  }

  const handleEventClick = async (info) => {
    const eventId = parseInt(info.event.id)
    setSelectedEvent(eventId)
    try {
      const detail = await api.getEventDetail(eventId)
      setEventDetail(detail)
    } catch (err) {
      console.error('加载事件详情失败:', err)
    }
  }

  return (
    <div className="p-6 max-w-7xl mx-auto fade-in">
      <div className="mb-4">
        <h2 className="text-xl font-bold text-slate-800">日历视图</h2>
        <p className="text-sm text-slate-500 mt-1">按日/周/月浏览团队事件 · 点击事件卡片查看详情</p>
      </div>

      <div className="grid grid-cols-3 gap-4">
        {/* 日历主体 */}
        <div className="col-span-2 bg-white rounded-2xl shadow-sm border border-slate-100 p-4">
          <FullCalendar
            ref={calendarRef}
            plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
            initialView="dayGridMonth"
            headerToolbar={{
              left: 'prev,next today',
              center: 'title',
              right: 'dayGridMonth,timeGridWeek,timeGridDay',
            }}
            locale="zh-cn"
            height="auto"
            events={events}
            eventClick={handleEventClick}
            dayMaxEvents={3}
            eventDisplay="block"
            buttonText={{
              today: '今天',
              month: '月',
              week: '周',
              day: '日',
            }}
          />

          {/* 图例 */}
          <div className="flex items-center gap-3 mt-3 pt-3 border-t border-slate-100">
            <span className="text-[11px] text-slate-400">场景类型：</span>
            {Object.entries(SCENE_COLORS).map(([name, color]) => (
              <div key={name} className="flex items-center gap-1">
                <div className="w-3 h-3 rounded" style={{ background: color }}></div>
                <span className="text-[11px] text-slate-500">{name}</span>
              </div>
            ))}
          </div>
        </div>

        {/* 事件详情面板 */}
        <div className="col-span-1">
          {eventDetail ? (
            <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-5 sticky top-6 fade-in">
              <div className="flex items-center justify-between mb-3">
                <span
                  className="text-[11px] font-medium px-2 py-0.5 rounded text-white"
                  style={{ background: getEventColor(eventDetail.scene) }}
                >
                  {eventDetail.scene || '未分类'}
                </span>
                <button
                  onClick={() => { setEventDetail(null); setSelectedEvent(null) }}
                  className="text-slate-300 hover:text-slate-500"
                >
                  <X size={16} />
                </button>
              </div>

              <div className="flex items-center gap-1.5 text-[11px] text-slate-400 mb-3">
                <Clock size={11} />
                {eventDetail.event_time}
              </div>

              <div className="flex items-center gap-1.5 text-[11px] text-slate-500 mb-3">
                <UsersIcon size={11} />
                {eventDetail.involved_members?.map(memberName).join('、')}
              </div>

              <div className="mb-4">
                <div className="text-[11px] font-semibold text-slate-400 mb-1">原始描述</div>
                <p className="text-xs text-slate-700 leading-relaxed bg-slate-50 rounded-lg p-3">
                  {eventDetail.raw_summary}
                </p>
              </div>

              {eventDetail.parsed_task && (
                <div className="mb-4">
                  <div className="text-[11px] font-semibold text-slate-400 mb-1">事务影响</div>
                  <p className="text-xs text-slate-700 bg-blue-50 rounded-lg p-3">
                    {eventDetail.parsed_task}
                  </p>
                </div>
              )}

              {eventDetail.emotions?.length > 0 && (
                <div className="mb-4">
                  <div className="text-[11px] font-semibold text-slate-400 mb-1">情绪状态</div>
                  <div className="space-y-1">
                    {eventDetail.emotions.map((emo, i) => (
                      <div key={i} className="flex items-center justify-between text-xs bg-slate-50 rounded px-2 py-1">
                        <span className="font-medium text-slate-600">{memberName(emo.member_id)}</span>
                        <span className="text-slate-500">{emo.emotion}</span>
                        <span className="text-slate-400">{emo.intensity}/10</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {eventDetail.relations?.length > 0 && (
                <div>
                  <div className="text-[11px] font-semibold text-slate-400 mb-1">关系变化</div>
                  <div className="space-y-1">
                    {eventDetail.relations.map((rel, i) => (
                      <div key={i} className="text-xs bg-slate-50 rounded px-2 py-1.5">
                        <div className="font-medium text-slate-600 mb-0.5">
                          {memberName(rel.from_member_id)} → {memberName(rel.to_member_id)}
                        </div>
                        <div className="flex gap-3 text-[11px]">
                          <span className={rel.trust_delta < 0 ? 'text-red-500' : 'text-emerald-500'}>
                            信任 {rel.trust_delta > 0 ? '+' : ''}{rel.trust_delta}
                          </span>
                          <span className={rel.sentiment_delta < 0 ? 'text-red-500' : 'text-emerald-500'}>
                            情绪 {rel.sentiment_delta > 0 ? '+' : ''}{rel.sentiment_delta}
                          </span>
                        </div>
                        {rel.tag && <div className="text-[10px] text-slate-400 mt-0.5">{rel.tag}</div>}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {eventDetail.confidence && (
                <div className="mt-3 pt-3 border-t border-slate-100 text-[10px] text-slate-400">
                  解析置信度: {(eventDetail.confidence * 100).toFixed(0)}%
                </div>
              )}
            </div>
          ) : (
            <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-8 text-center sticky top-6">
              <div className="text-3xl mb-2">📅</div>
              <p className="text-sm text-slate-400">点击日历中的事件卡片</p>
              <p className="text-xs text-slate-300 mt-1">查看详细解析结果</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
