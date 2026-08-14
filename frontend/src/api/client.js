/**
 * API 客户端 —— 统一封装所有后端接口调用
 */

const BASE = '/api'

// 模块级缓存:批量重分析的 Promise。Dashboard 卸载后请求仍在,后端继续执行
let _reanalyzePromise = null
// AI Native 排名任务 Promise + 进度回调（支持页面切换后恢复）
let _rankingPromise = null
let _rankingProgressHandler = null
let _situationPromise = null
let _situationProgressHandler = null

function errorMessage(err, fallback = '请求失败') {
  const d = err?.detail
  if (typeof d === 'string' && d) return d
  if (Array.isArray(d)) {
    const parts = d.map((x) => x?.msg || x?.message || '').filter(Boolean)
    if (parts.length) return parts.join('；')
  }
  if (d && typeof d === 'object' && d.msg) return d.msg
  return fallback
}

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(errorMessage(err, res.statusText || '请求失败'))
  }
  return res.json()
}

export const api = {
  // 健康检查
  health: () => request('/health'),

  // LLM 配置
  getLlmConfig: () => request('/config/llm'),
  updateLlmConfig: (data) => request('/config/llm', {
    method: 'PUT',
    body: JSON.stringify(data),
  }),

  // 成员
  getMembers: () => request('/members'),
  getMember: (id) => request(`/members/${id}`),
  createMember: (data) => request('/members', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  updateMember: (id, data) => request(`/members/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),
  deleteMember: (id) => request(`/members/${id}`, {
    method: 'DELETE',
  }),

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
  reanalyzeEvent: (id) => request(`/events/${id}/reanalyze`, {
    method: 'POST',
  }),
  reanalyzeAll: () => {
    // 模块级缓存:同一时刻只允许一个批量重分析请求
    // 即使切换页面(Dashboard 卸载),Promise 仍在,后端继续执行
    // Dashboard 重新挂载时可通过 getReanalyzeStatus() 恢复 UI 状态
    if (!_reanalyzePromise) {
      _reanalyzePromise = request('/events/reanalyze-all', { method: 'POST' })
        .finally(() => { _reanalyzePromise = null })
    }
    return _reanalyzePromise
  },
  getReanalyzeStatus: () => _reanalyzePromise,

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

  // AI Native
  getAiNativeRoles: () => request('/ai-native/roles'),
  getAiNativeRoleDetail: (roleId) => request(`/ai-native/roles/${roleId}`),
  getAiNativeRankingStatus: () => request('/ai-native/ranking/status'),
  getAiNativeRankingPromise: () => _rankingPromise,
  onAiNativeRankingProgress: (handler) => {
    _rankingProgressHandler = handler
    return () => {
      if (_rankingProgressHandler === handler) _rankingProgressHandler = null
    }
  },
  /** 轮询排名任务直到结束；不触发新任务 */
  watchAiNativeRanking: () => {
    if (_rankingPromise) return _rankingPromise
    _rankingPromise = (async () => {
      for (;;) {
        const st = await request('/ai-native/ranking/status')
        if (typeof _rankingProgressHandler === 'function') {
          _rankingProgressHandler(st)
        }
        if (st.status === 'success' || st.status === 'failed' || st.status === 'idle') {
          return st
        }
        await new Promise((r) => setTimeout(r, 1200))
      }
    })().finally(() => { _rankingPromise = null })
    return _rankingPromise
  },
  /** 触发更新排名（幂等）；返回最终状态 */
  updateAiNativeRanking: async () => {
    const start = await request('/ai-native/ranking/update', { method: 'POST' })
    if (typeof _rankingProgressHandler === 'function') {
      _rankingProgressHandler(start)
    }
    if (start.status !== 'running') return start
    return api.watchAiNativeRanking()
  },
  updateAiNativeEvaluationScope: (roleId, data) => request(`/ai-native/roles/${roleId}/evaluation-scope`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),

  // 新人地图
  listNewcomers: () => request('/newcomers'),
  getNewcomer: (id) => request(`/newcomers/${encodeURIComponent(id)}`),
  createNewcomer: (data) => request('/newcomers', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  setNewcomerTargetRole: (id, data) => request(`/newcomers/${encodeURIComponent(id)}/target-role`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),
  getNewcomerGuide: (id) => request(`/newcomers/${encodeURIComponent(id)}/onboarding-guide`),
  saveNewcomerGuide: (id, data) => request(`/newcomers/${encodeURIComponent(id)}/onboarding-guide`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),
  generateNewcomerGuide: (id) => request(`/newcomers/${encodeURIComponent(id)}/onboarding-guide/generate`, {
    method: 'POST',
  }),
  publishNewcomerGuide: (id) => request(`/newcomers/${encodeURIComponent(id)}/onboarding-guide/publish`, {
    method: 'POST',
  }),
  getNewcomerTasks: (id) => request(`/newcomers/${encodeURIComponent(id)}/tasks`),
  recommendNewcomerTasks: (id) => request(`/newcomers/${encodeURIComponent(id)}/tasks/recommend`, {
    method: 'POST',
  }),
  getNewcomerAnalysisStatus: (id, kind = 'guide') => request(`/newcomers/${encodeURIComponent(id)}/analysis/status?kind=${kind}`),
  updateNewcomerTask: (taskId, data) => request(`/newcomer-tasks/${taskId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),
  completeNewcomerTask: (taskId, note = '') => request(`/newcomer-tasks/${taskId}/complete`, {
    method: 'POST',
    body: JSON.stringify({ note }),
  }),
  getNewcomerInterventions: () => request('/newcomers/interventions'),
  resolveNewcomerIntervention: (id) => request(`/newcomers/interventions/${id}/resolve`, {
    method: 'POST',
  }),

  // 日报
  importDailyReport: async (file) => {
    const form = new FormData()
    form.append('file', file)
    const res = await fetch(`${BASE}/daily-report/import`, { method: 'POST', body: form })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(err.detail || '导入失败')
    }
    return res.json()
  },
  getDailyImportTask: (taskId) => request(`/daily-report/import/${taskId}`),
  listDailyImportTasks: (limit = 20) => request(`/daily-report/import?limit=${limit}`),
  getDailyReports: (params = {}) => {
    const q = new URLSearchParams()
    if (params.date) q.set('date', params.date)
    if (params.date_from) q.set('date_from', params.date_from)
    if (params.date_to) q.set('date_to', params.date_to)
    if (params.member) q.set('member', params.member)
    if (params.project) q.set('project', params.project)
    if (params.skill) q.set('skill', params.skill)
    if (params.limit) q.set('limit', params.limit)
    return request(`/daily-report?${q}`)
  },
  getDailyReportHistory: (id) => request(`/daily-report/${id}/history`),
  getReportMemberStats: (days = 30) => request(`/report/statistics/member?days=${days}`),

  // 组织影响力图谱 OIG
  getOigGraph: (params = {}) => {
    const q = new URLSearchParams()
    if (params.types) q.set('types', params.types)
    if (params.relations) q.set('relations', params.relations)
    const qs = q.toString()
    return request(`/v1/graph${qs ? `?${qs}` : ''}`)
  },
  getOigStatus: () => request('/v1/graph/status'),
  rebuildOigGraph: () => request('/v1/graph/rebuild', { method: 'POST' }),
  getOigPersonNetwork: (id) => request(`/v1/person/${encodeURIComponent(id)}/network`),
  getOigLeadership: (id) => request(`/v1/person/${encodeURIComponent(id)}/leadership-profile`),
  getOigInfluenceRanking: () => request('/v1/influence/ranking'),
  getOigCommunity: () => request('/v1/community'),
  getOigRisk: () => request('/v1/risk'),
  extractOig: (text, sourceType = 'document') => request('/v1/extract', {
    method: 'POST',
    body: JSON.stringify({ text, source_type: sourceType }),
  }),
  getOigExtractHistory: (limit = 10) => request(`/v1/extract/history?limit=${limit}`),

  // 晋升推演
  getPromotionTemplates: () => request('/promotion/templates'),
  listPromotions: () => request('/promotion/simulations'),
  createPromotion: (data) => request('/promotion/simulations', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  getPromotion: (id) => request(`/promotion/simulations/${id}`),
  getPromotionStatus: (id) => request(`/promotion/simulations/${id}/status`),
  cancelPromotion: (id) => request(`/promotion/simulations/${id}/cancel`, { method: 'POST' }),
  updatePromotionWeights: (id, data) => request(`/promotion/simulations/${id}/weights`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),
  deletePromotion: (id) => request(`/promotion/simulations/${id}`, { method: 'DELETE' }),

  // 项目中心
  listProjects: (params = {}) => {
    const q = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '' && v !== false) q.set(k, v)
    })
    const qs = q.toString()
    return request(`/projects${qs ? `?${qs}` : ''}`)
  },
  createProject: (data) => request('/projects', { method: 'POST', body: JSON.stringify(data) }),
  getProject: (id) => request(`/projects/${encodeURIComponent(id)}`),
  updateProject: (id, data) => request(`/projects/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),
  deleteProject: (id) => request(`/projects/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  addProjectStage: (id, data) => request(`/projects/${encodeURIComponent(id)}/stages`, {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  updateProjectStage: (id, stageId, data) => request(`/projects/${encodeURIComponent(id)}/stages/${encodeURIComponent(stageId)}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),
  completeProjectStage: (id, stageId, data = {}) => request(`/projects/${encodeURIComponent(id)}/stages/${encodeURIComponent(stageId)}/complete`, {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  addProjectMember: (id, data) => request(`/projects/${encodeURIComponent(id)}/members`, {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  deleteProjectMember: (id, memberId) => request(`/projects/${encodeURIComponent(id)}/members/${encodeURIComponent(memberId)}`, {
    method: 'DELETE',
  }),
  addProjectMilestone: (id, data) => request(`/projects/${encodeURIComponent(id)}/milestones`, {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  updateProjectMilestone: (id, mid, data) => request(`/projects/${encodeURIComponent(id)}/milestones/${encodeURIComponent(mid)}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),
  addProjectRisk: (id, data) => request(`/projects/${encodeURIComponent(id)}/risks`, {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  updateProjectRisk: (id, rid, data) => request(`/projects/${encodeURIComponent(id)}/risks/${encodeURIComponent(rid)}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),
  addProjectActivity: (id, data) => request(`/projects/${encodeURIComponent(id)}/activities`, {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  addProjectObjective: (id, data) => request(`/projects/${encodeURIComponent(id)}/objectives`, {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  addProjectKr: (id, oid, data) => request(`/projects/${encodeURIComponent(id)}/objectives/${encodeURIComponent(oid)}/krs`, {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  addProjectRelation: (id, data) => request(`/projects/${encodeURIComponent(id)}/relations`, {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  deleteProjectRelation: (id, rid) => request(`/projects/${encodeURIComponent(id)}/relations/${encodeURIComponent(rid)}`, {
    method: 'DELETE',
  }),

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

  // 团队态势
  getSituationToday: () => request('/team-situation/today'),
  getSituationStatus: () => request('/team-situation/status'),
  getSituationReports: (params = {}) => {
    const q = new URLSearchParams()
    if (params.date) q.set('date', params.date)
    if (params.start_date) q.set('start_date', params.start_date)
    if (params.end_date) q.set('end_date', params.end_date)
    const qs = q.toString()
    return request(`/team-situation/reports${qs ? `?${qs}` : ''}`)
  },
  getSituationMember: (id) => request(`/team-situation/members/${encodeURIComponent(id)}`),
  getSituationProject: (id) => request(`/team-situation/projects/${encodeURIComponent(id)}`),
  getSituationTrends: (range = '7d') => request(`/team-situation/trends?range=${range}`),
  getSituationConfig: () => request('/team-situation/config'),
  updateSituationConfig: (data) => request('/team-situation/config', {
    method: 'PUT',
    body: JSON.stringify(data),
  }),
  addSituationContext: (data) => request('/team-situation/context', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  listSituationContext: (date) => request(`/team-situation/context${date ? `?date=${encodeURIComponent(date)}` : ''}`),
  patchSituationRisk: (id, status) => request(`/team-situation/risks/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  }),
  patchSituationQuestion: (id, status, answer = '') => request(`/team-situation/questions/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: JSON.stringify({ status, answer }),
  }),
  getSituationPromise: () => _situationPromise,
  onSituationProgress: (handler) => {
    _situationProgressHandler = handler
    return () => {
      if (_situationProgressHandler === handler) _situationProgressHandler = null
    }
  },
  watchSituationAnalyze: () => {
    if (_situationPromise) return _situationPromise
    _situationPromise = (async () => {
      for (;;) {
        const st = await request('/team-situation/status')
        if (typeof _situationProgressHandler === 'function') {
          _situationProgressHandler(st)
        }
        if (st.status === 'success' || st.status === 'failed' || st.status === 'idle') {
          return st
        }
        await new Promise((r) => setTimeout(r, 1200))
      }
    })().finally(() => { _situationPromise = null })
    return _situationPromise
  },
  analyzeSituation: async (idempotencyKey) => {
    const start = await request('/team-situation/analyze', {
      method: 'POST',
      body: JSON.stringify({ idempotency_key: idempotencyKey }),
    })
    if (typeof _situationProgressHandler === 'function') {
      _situationProgressHandler(start)
    }
    if (start.status !== 'running') return start
    return api.watchSituationAnalyze()
  },
}
