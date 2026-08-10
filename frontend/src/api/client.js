/**
 * API 客户端 —— 统一封装所有后端接口调用
 */

const BASE = '/api'

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || '请求失败')
  }
  return res.json()
}

export const api = {
  // 健康检查
  health: () => request('/health'),

  // 成员
  getMembers: () => request('/members'),
  getMember: (id) => request(`/members/${id}`),

  // 事件
  getEvents: (params = {}) => {
    const q = new URLSearchParams()
    if (params.date_from) q.set('date_from', params.date_from)
    if (params.date_to) q.set('date_to', params.date_to)
    if (params.member_id) q.set('member_id', params.member_id)
    if (params.include_hypothetical !== undefined) q.set('include_hypothetical', params.include_hypothetical)
    return request(`/events?${q}`)
  },
  getEventDetail: (id) => request(`/events/${id}`),
  logEvent: (data) => request('/events/log', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  // 关系
  getRelationships: (atTime) => {
    const q = new URLSearchParams()
    if (atTime) q.set('at_time', atTime)
    return request(`/relationships?${q}`)
  },
  getRelationshipHistory: (memberPair, days = 30) => {
    const q = new URLSearchParams({ days })
    if (memberPair) q.set('member_pair', memberPair)
    return request(`/relationships/history?${q}`)
  },

  // 状态
  getStates: (atTime) => {
    const q = new URLSearchParams()
    if (atTime) q.set('at_time', atTime)
    return request(`/states?${q}`)
  },

  // 仪表盘
  getDashboard: (atTime) => {
    const q = new URLSearchParams()
    if (atTime) q.set('at_time', atTime)
    return request(`/dashboard?${q}`)
  },

  // 对话
  query: (message) => request('/chat/query', {
    method: 'POST',
    body: JSON.stringify({ message }),
  }),
  simulate: (scenario) => request('/chat/simulate', {
    method: 'POST',
    body: JSON.stringify({ scenario }),
  }),
  getChatHistory: (limit = 20) => request(`/chat/history?limit=${limit}`),
}
