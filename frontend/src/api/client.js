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
  getEventChain: (id) => request(`/events/${id}/chain`),
  getEventTaxonomy: () => request('/events/taxonomy'),
  getEventTemplate: (eventType, eventTag) => {
    const q = new URLSearchParams()
    if (eventType) q.set('event_type', eventType)
    if (eventTag) q.set('event_tag', eventTag)
    return request(`/events/template?${q}`)
  },
  suggestEventTags: (data) => request('/events/suggest-tags', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
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
  getRelationshipPair: (fromId, toId) => request(`/relationships/pair?from_id=${encodeURIComponent(fromId)}&to_id=${encodeURIComponent(toId)}`),
  getRelationshipScore: (fromId, toId, dimension = 'trust') => request(
    `/relationships/score?from_id=${encodeURIComponent(fromId)}&to_id=${encodeURIComponent(toId)}&dimension=${encodeURIComponent(dimension)}`,
  ),
  getRelationshipEvidence: (id) => request(`/relationships/evidence/${id}`),

  getGrowthStandards: (roleId) => request(`/growth/standards/${encodeURIComponent(roleId)}`),
  listCadreProfiles: () => request('/growth/cadre'),
  getCadreProfile: (id) => request(`/growth/cadre/${encodeURIComponent(id)}`),
  getUpwardArchive: (id, managerId) => request(
    `/growth/upward/${encodeURIComponent(id)}${managerId ? `?manager_id=${encodeURIComponent(managerId)}` : ''}`,
  ),
  getUpwardFacts: (id, managerId, projectId) => {
    const q = new URLSearchParams()
    if (managerId) q.set('manager_id', managerId)
    if (projectId) q.set('project_id', projectId)
    const qs = q.toString()
    return request(`/growth/upward/${encodeURIComponent(id)}/facts${qs ? `?${qs}` : ''}`)
  },
  generateUpwardReport: (id, data) => request(`/growth/upward/${encodeURIComponent(id)}/report`, {
    method: 'POST',
    body: JSON.stringify(data || {}),
  }),
  getTwinBootstrap: () => request('/twin/bootstrap'),
  runTwinSimulate: (data) => request('/twin/simulate', { method: 'POST', body: JSON.stringify(data || {}) }),
  listTwinSimulations: () => request('/twin/simulations'),
  getTwinSimulation: (id) => request(`/twin/simulations/${encodeURIComponent(id)}`),
  listTwinPredictions: (personId, kind) => {
    const q = new URLSearchParams()
    if (personId) q.set('person_id', personId)
    if (kind) q.set('kind', kind)
    const qs = q.toString()
    return request(`/twin/predictions${qs ? `?${qs}` : ''}`)
  },
  recordTwinActual: (id, data) => request(`/twin/predictions/${encodeURIComponent(id)}/actual`, {
    method: 'POST',
    body: JSON.stringify(data || {}),
  }),
  getTwinGrowth: (id, days = 90) => request(`/twin/growth/${encodeURIComponent(id)}?days=${days}`),
  getTwinPath: (id) => request(`/twin/path/${encodeURIComponent(id)}`),
  runTwinMentoring: (data) => request('/twin/mentoring', { method: 'POST', body: JSON.stringify(data || {}) }),
  runTwinMatch: (data) => request('/twin/match', { method: 'POST', body: JSON.stringify(data || {}) }),
  createTwinPlan: (data) => request('/twin/training/plan', { method: 'POST', body: JSON.stringify(data || {}) }),
  optimizeTwinPlan: (id) => request(`/twin/training/optimize/${encodeURIComponent(id)}`),
  compareTwinSchemes: (data) => request('/twin/training/compare', { method: 'POST', body: JSON.stringify(data || {}) }),
  simulateTwinCohort: (data) => request('/twin/training/cohort', { method: 'POST', body: JSON.stringify(data || {}) }),
  expandTwinOrg: (data) => request('/twin/org/expand', { method: 'POST', body: JSON.stringify(data || {}) }),
  getTwinPipeline: () => request('/twin/org/pipeline'),
  getTwinStructures: () => request('/twin/org/structures'),
  getTwinDeparture: (id) => request(`/twin/org/departure/${encodeURIComponent(id)}`),
  getTwinKnowledge: (id) => request(`/twin/org/knowledge/${encodeURIComponent(id)}`),
  getTwinInformal: () => request('/twin/org/informal'),
  predictTwinConflict: (data) => request('/twin/org/conflict', { method: 'POST', body: JSON.stringify(data || {}) }),
  getTwinAuth: (id, projectId) => request(
    `/twin/leadership/auth/${encodeURIComponent(id)}${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ''}`,
  ),
  getTwinPolicies: () => request('/twin/policies'),
  saveTwinPolicy: (data) => request('/twin/policies', { method: 'POST', body: JSON.stringify(data || {}) }),
  getTwinPolicy: (id) => request(`/twin/policies/${encodeURIComponent(id)}`),
  addTwinPolicyOutcome: (id, data) => request(`/twin/policies/${encodeURIComponent(id)}/outcome`, {
    method: 'POST',
    body: JSON.stringify(data || {}),
  }),
  getPromotionGrowth: (id) => request(`/growth/promotion/${encodeURIComponent(id)}`),
  getNewcomerStages: (id) => request(`/newcomers/${encodeURIComponent(id)}/stages`),
  saveNewcomerStage: (id, stageId, data) => request(`/newcomers/${encodeURIComponent(id)}/stages/${encodeURIComponent(stageId)}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),
  getProjectGrowth: (projectId) => request(`/projects/${encodeURIComponent(projectId)}/growth-evidence`),
  saveProjectGrowth: (projectId, personId, data) => request(`/projects/${encodeURIComponent(projectId)}/growth-evidence/${encodeURIComponent(personId)}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),
  projectGrowthToEvent: (projectId, personId, createdBy) => request(
    `/projects/${encodeURIComponent(projectId)}/growth-evidence/${encodeURIComponent(personId)}/to-event${createdBy ? `?created_by=${encodeURIComponent(createdBy)}` : ''}`,
    { method: 'POST' },
  ),

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
  getDailyReportStyles: () => request('/daily-report/styles'),
  saveDailyReportStyle: (styleId, data) => request(`/daily-report/styles/${styleId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),
  rewriteDailyReport: (data) => request('/daily-report/rewrite', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  ingestDailyReport: (data) => request('/daily-report/ingest', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  getReportMemberStats: (days = 30) => request(`/report/statistics/member?days=${days}`),

  // 组织影响力图谱 OIG
  getOigGraph: (params = {}) => {
    const q = new URLSearchParams()
    if (params.types) q.set('types', params.types)
    if (params.relations) q.set('relations', params.relations)
    if (params.asOf) q.set('asOf', params.asOf)
    if (params.includeHistory) q.set('includeHistory', 'true')
    const qs = q.toString()
    return request(`/v1/graph${qs ? `?${qs}` : ''}`)
  },
  getOigStatus: () => request('/v1/graph/status'),
  rebuildOigGraph: () => request('/v1/graph/rebuild', { method: 'POST' }),
  getOigPersonNetwork: (id) => request(`/v1/person/${encodeURIComponent(id)}/network`),
  getOigLeadership: (id) => request(`/v1/person/${encodeURIComponent(id)}/leadership-profile`),
  getOigInfluenceRanking: (params = {}) => {
    const q = new URLSearchParams()
    if (params.asOf) q.set('asOf', params.asOf)
    if (params.dateFrom) q.set('dateFrom', params.dateFrom)
    if (params.dateTo) q.set('dateTo', params.dateTo)
    const qs = q.toString()
    return request(`/v1/influence/ranking${qs ? `?${qs}` : ''}`)
  },
  getOigCommunity: () => request('/v1/community'),
  getOigRisk: () => request('/v1/risk'),
  extractOig: (text, sourceType = 'document') => request('/v1/extract', {
    method: 'POST',
    body: JSON.stringify({ text, source_type: sourceType }),
  }),
  applyOigExtract: (data) => request('/v1/extract/apply', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  getOigExtractHistory: (limit = 10) => request(`/v1/extract/history?limit=${limit}`),

  // 实体治理 / 统一实体层
  getEntityGovernanceOverview: () => request('/entity-governance/overview'),
  detectEntityDuplicates: (data = {}) => request('/entity-governance/detect', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  getEntityDetectStatus: () => request('/entity-governance/detect/status'),
  listEntityCandidates: (params = {}) => {
    const q = new URLSearchParams()
    if (params.status) q.set('status', params.status)
    if (params.entityType) q.set('entityType', params.entityType)
    if (params.minScore != null) q.set('minScore', params.minScore)
    if (params.page) q.set('page', params.page)
    if (params.pageSize) q.set('pageSize', params.pageSize)
    return request(`/entity-governance/candidates?${q}`)
  },
  getEntityCandidate: (id) => request(`/entity-governance/candidates/${encodeURIComponent(id)}`),
  mergeEntities: (data) => request('/entity-governance/merge', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  rejectEntityCandidate: (data) => request('/entity-governance/reject', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  skipEntityCandidate: (data) => request('/entity-governance/skip', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  unmergeEntities: (mergeId) => request(`/entity-governance/unmerge/${encodeURIComponent(mergeId)}`, {
    method: 'POST',
  }),
  listEntityMerges: (includeUnmerged = true) => request(`/entity-governance/merges?includeUnmerged=${includeUnmerged}`),
  getEntityMerge: (id) => request(`/entity-governance/merges/${encodeURIComponent(id)}`),
  addEntityAlias: (data) => request('/entity-governance/aliases', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  resolveEntity: (data) => request('/entity-resolution/resolve', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  getKgOverview: () => request('/knowledge-governance/overview'),
  getKgAnalyze: () => request('/knowledge-governance/analyze'),
  getKgOntologyDraft: () => request('/knowledge-governance/ontology/draft'),
  applyKgOntology: () => request('/knowledge-governance/ontology/apply', { method: 'POST' }),
  getKgTypes: () => request('/knowledge-governance/ontology/types'),
  getKgSchema: () => request('/knowledge-governance/ontology/schema'),
  saveKgTypeProperties: (id, properties) => request(
    `/knowledge-governance/ontology/types/${encodeURIComponent(id)}/properties`,
    { method: 'PUT', body: JSON.stringify({ properties }) },
  ),
  getKgRelations: () => request('/knowledge-governance/ontology/relations'),
  saveKgRelation: (data) => request('/knowledge-governance/ontology/relations', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  deleteKgRelation: (id) => request(`/knowledge-governance/ontology/relations/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  }),
  getKgConstraints: () => request('/knowledge-governance/ontology/constraints'),
  saveKgConstraint: (data) => request('/knowledge-governance/ontology/constraints', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  deleteKgConstraint: (id) => request(`/knowledge-governance/ontology/constraints/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  }),
  createKgType: (data) => request('/knowledge-governance/ontology/types', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  updateKgType: (id, data) => request(`/knowledge-governance/ontology/types/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),
  mergeKgTypes: (data) => request('/knowledge-governance/ontology/types/merge', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  deleteKgType: (id) => request(`/knowledge-governance/ontology/types/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  }),
  getKgRules: () => request('/knowledge-governance/rules'),
  setKgRuleStatus: (id, status) => request(`/knowledge-governance/rules/${encodeURIComponent(id)}/status`, {
    method: 'POST',
    body: JSON.stringify({ status }),
  }),
  enhanceKg: () => request('/knowledge-governance/analyze/publish', { method: 'POST' }),
  publishKgAnalyze: (force = false) => request(
    `/knowledge-governance/analyze/publish?force=${force ? 'true' : 'false'}`,
    { method: 'POST' },
  ),
  applyKgConfirmed: () => request('/knowledge-governance/apply-confirmed', { method: 'POST' }),
  getKgWorkItems: (params = {}) => {
    const q = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') q.set(k, v)
    })
    return request(`/knowledge-governance/work-items?${q}`)
  },
  patchKgWorkItem: (id, proposed) => request(`/knowledge-governance/work-items/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: JSON.stringify({ proposed }),
  }),
  acceptKgWorkItem: (id, proposed) => request(`/knowledge-governance/work-items/${encodeURIComponent(id)}/accept`, {
    method: 'POST',
    body: JSON.stringify(proposed ? { proposed } : {}),
  }),
  rejectKgWorkItem: (id) => request(`/knowledge-governance/work-items/${encodeURIComponent(id)}/reject`, {
    method: 'POST',
  }),
  deferKgWorkItem: (id) => request(`/knowledge-governance/work-items/${encodeURIComponent(id)}/defer`, {
    method: 'POST',
  }),
  classifyKgInstance: (nodeId, extra = {}) => request('/knowledge-governance/work-items/classify', {
    method: 'POST',
    body: JSON.stringify({ nodeId, typeId: extra.typeId, ontologyType: extra.ontologyType }),
  }),
  getKgInstance: (nodeId) => request(`/knowledge-governance/instances/${encodeURIComponent(nodeId)}`),
  retireKgInstance: (nodeId) => request(`/knowledge-governance/instances/${encodeURIComponent(nodeId)}`, {
    method: 'DELETE',
  }),
  getKgInferred: (limit = 80) => request(`/knowledge-governance/inferred?limit=${limit}`),
  getKgSuggestions: (status = 'open') => request(`/knowledge-governance/work-items?status=${status}`),
  acceptKgSuggestion: (id, proposed) => request(`/knowledge-governance/work-items/${encodeURIComponent(id)}/accept`, {
    method: 'POST',
    body: JSON.stringify(proposed ? { proposed } : {}),
  }),
  ignoreKgSuggestion: (id) => request(`/knowledge-governance/work-items/${encodeURIComponent(id)}/reject`, {
    method: 'POST',
  }),
  getKgRevisions: () => request('/knowledge-governance/revisions'),
  rollbackKg: (revisionId) => request('/knowledge-governance/rollback', {
    method: 'POST',
    body: JSON.stringify({ revisionId }),
  }),

  getTemporalOverview: () => request('/temporal/overview'),
  getTemporalSnapshot: (asOf) => request(`/temporal/snapshot?asOf=${encodeURIComponent(asOf)}`),
  getTemporalFacts: (params = {}) => {
    const q = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') q.set(k, v)
    })
    return request(`/temporal/facts?${q}`)
  },
  getTemporalRange: (objectId, dateFrom, dateTo, predicates) => {
    const q = new URLSearchParams({ objectId, dateFrom, dateTo })
    if (predicates) q.set('predicates', predicates)
    return request(`/temporal/range?${q}`)
  },
  getPersonTimeline: (id) => request(`/temporal/person/${encodeURIComponent(id)}/timeline`),
  getProjectTimeline: (id) => request(`/temporal/project/${encodeURIComponent(id)}/timeline`),
  applyTemporalEvent: (data) => request('/temporal/events', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  listTemporalEvents: (limit = 40) => request(`/temporal/events?limit=${limit}`),
  getTemporalInfluence: (params = {}) => {
    const q = new URLSearchParams()
    if (params.asOf) q.set('asOf', params.asOf)
    if (params.dateFrom) q.set('dateFrom', params.dateFrom)
    if (params.dateTo) q.set('dateTo', params.dateTo)
    return request(`/temporal/influence?${q}`)
  },

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

  getFactOverview: () => request('/fact-governance/overview'),
  listFacts: (params = {}) => {
    const q = new URLSearchParams()
    if (params.status) q.set('status', params.status)
    if (params.q) q.set('q', params.q)
    if (params.page) q.set('page', params.page)
    if (params.pageSize) q.set('pageSize', params.pageSize)
    return request(`/fact-governance/facts?${q}`)
  },
  createFact: (data) => request('/fact-governance/facts', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  getFact: (id) => request(`/fact-governance/facts/${encodeURIComponent(id)}`),
  confirmFact: (id) => request(`/fact-governance/facts/${encodeURIComponent(id)}/confirm`, { method: 'POST' }),
  rejectFact: (id, reason = '') => request(`/fact-governance/facts/${encodeURIComponent(id)}/reject`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  }),
  getFactImpact: (id) => request(`/fact-governance/facts/${encodeURIComponent(id)}/impact`),
  deleteFact: (id, data = {}) => request(`/fact-governance/facts/${encodeURIComponent(id)}/delete`, {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  supersedeFact: (id, data) => request(`/fact-governance/facts/${encodeURIComponent(id)}/supersede`, {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  extractFacts: (data) => request('/fact-governance/extract', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  listFactJobs: () => request('/fact-governance/jobs'),
  listFactConflicts: () => request('/fact-governance/conflicts'),
  listFactRebuildTasks: () => request('/fact-governance/rebuild-tasks'),
}
