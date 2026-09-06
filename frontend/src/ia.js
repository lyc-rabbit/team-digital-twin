/**
 * 信息架构：一级按「谁在看、要回答什么问题」划分，
 * 二级才按系统能力挂载。现有面板全部保留，只改变位置。
 */

export const OBSERVER_KEY = 'tdt_observer'

export const OBSERVERS = [
  {
    id: 'boss',
    label: '老板',
    home: 'cockpit-overview',
    question: '公司 / 部门现在怎么样？',
    hint: '异常优先，看哪里需要介入',
  },
  {
    id: 'leader',
    label: '领导',
    home: 'team-situation',
    question: '我的团队现在怎么样？我该怎么管理？',
    hint: '管人：负载、依赖、梯队',
  },
  {
    id: 'pm',
    label: '项目负责人',
    home: 'work-overview',
    question: '事情能不能按计划完成？哪里卡住了？',
    hint: '管事：进度、阻塞、资源',
  },
  {
    id: 'employee',
    label: '员工',
    home: 'growth-work',
    question: '我现在处于什么位置？我该做什么？怎么成长？',
    hint: '看自己：工作、角色、成长',
  },
]

export const NAV_GROUPS = [
  {
    id: 'cockpit',
    label: '组织驾驶舱',
    icon: 'cockpit',
    question: '公司 / 部门现在怎么样？',
    hideFor: [],
    items: [
      { id: 'cockpit-overview', label: '总览', view: 'org-cockpit', question: '哪里需要我介入？' },
      { id: 'cockpit-projects', label: '业务 / 项目态势', view: 'team-situation', props: { initialTab: 'projects' }, question: '项目是否安全？' },
      { id: 'cockpit-talent', label: '人才态势', view: 'team-situation', props: { initialTab: 'members' }, question: '人才是否合理？' },
      { id: 'cockpit-stability', label: '组织稳定性', view: 'dashboard', question: '协作与情绪是否健康？' },
      { id: 'cockpit-key-people', label: '关键人物', view: 'influence-graph', props: { preset: 'influence' }, question: '谁不可替代？' },
      { id: 'cockpit-resources', label: '关键资源', view: 'influence-graph', props: { preset: 'resource' }, question: '资源掌握在谁手里？' },
      { id: 'cockpit-risks', label: '风险雷达', view: 'team-situation', props: { initialTab: 'risks' }, question: '组织风险在哪？' },
      { id: 'cockpit-changes', label: '重大变化', view: 'team-situation', props: { initialTab: 'trends' }, question: '最近发生了什么？' },
    ],
  },
  {
    id: 'team',
    label: '团队管理',
    icon: 'team',
    question: '我的团队现在怎么样？我该怎么管理？',
    hideFor: [],
    items: [
      { id: 'team-situation', label: '团队态势', view: 'team-situation', props: { initialTab: 'today' }, question: '作为领导，我现在应该管理什么？' },
      { id: 'team-structure', label: '团队结构', view: 'influence-graph', props: { preset: 'reporting' }, question: '名义上的组织是什么？' },
      { id: 'team-load', label: '工作负载', view: 'team-situation', props: { initialTab: 'members' }, question: '谁过载、谁闲置？' },
      { id: 'team-division', label: '人员分工', view: 'project-center', question: '人是怎么分到事情上的？' },
      { id: 'team-dependency', label: '人员依赖', view: 'influence-graph', props: { preset: 'risk' }, question: '谁是单点？替代是否不足？' },
      { id: 'team-relations', label: '团队关系', view: 'dashboard', question: '协作与信任现在怎样？' },
      { id: 'team-pipeline', label: '人才梯队', view: 'cadre-growth', question: '干部成长到哪一步？' },
      { id: 'team-newcomer', label: '新人地图', view: 'newcomer-map', question: '新人到哪了？要不要介入？' },
      { id: 'team-advice', label: '管理建议', view: 'team-situation', props: { initialTab: 'today' }, question: '系统建议你先管什么？' },
    ],
  },
  {
    id: 'work',
    label: '项目与工作',
    icon: 'work',
    question: '事情能不能按计划完成？',
    hideFor: [],
    items: [
      { id: 'work-overview', label: '项目总览', view: 'project-center', question: '事情能不能交付？' },
      { id: 'work-detail', label: '项目详情', view: 'project-center', question: '这个项目现在卡在哪？' },
      { id: 'work-stages', label: '阶段进度', view: 'project-center', question: '当前阶段是否按计划？' },
      { id: 'work-division', label: '工作分工', view: 'project-center', question: '谁在做哪一块？' },
      { id: 'work-flow', label: '工作流', view: 'calendar', question: '事件与节奏如何展开？' },
      { id: 'work-deps', label: '任务依赖', view: 'influence-graph', props: { preset: 'work' }, question: '工作上谁依赖谁？' },
      { id: 'work-risks', label: '阻塞与风险', view: 'team-situation', props: { initialTab: 'projects' }, question: '哪里卡住了？' },
      { id: 'work-resources', label: '项目资源', view: 'influence-graph', props: { preset: 'resource' }, question: '项目缺什么资源？' },
      { id: 'work-review', label: '项目复盘', view: 'temporal-graph', props: { initialTab: 'project' }, question: '这段工作是怎么走过来的？' },
      { id: 'work-daily', label: '日报', view: 'daily-report', question: '工作事实从日报进来。' },
    ],
  },
  {
    id: 'growth',
    label: '个人成长',
    icon: 'growth',
    question: '我现在处于什么位置？我该做什么？怎么成长？',
    hideFor: [],
    items: [
      { id: 'growth-work', label: '我的工作', view: 'daily-report', question: '我最近做了什么？' },
      { id: 'growth-role', label: '我的角色', view: 'ai-native', question: '我在组织里承担什么角色？' },
      { id: 'growth-capability', label: '我的能力', view: 'cadre-growth', question: '哪些能力已被验证？' },
      { id: 'growth-contribution', label: '我的贡献', view: 'cadre-growth', question: '我留下了哪些可追溯贡献？' },
      { id: 'growth-influence', label: '我的影响力', view: 'influence-graph', props: { preset: 'influence' }, question: '我在协作网里有多关键？' },
      { id: 'growth-path', label: '我的成长路径', view: 'newcomer-map', question: '下一步该做什么？' },
      { id: 'growth-network', label: '我的关系网络', view: 'upward', question: '我和上级、同事怎么协同？' },
      { id: 'growth-promo', label: '晋升准备度', view: 'promotion', question: '往上走还缺什么？' },
      { id: 'growth-advice', label: '成长建议', view: 'upward', question: '向上协同还要补什么？' },
    ],
  },
  {
    id: 'relations',
    label: '组织关系',
    icon: 'relations',
    question: '权力、资源、影响实际如何流动？',
    hideFor: [],
    items: [
      { id: 'rel-overview', label: '关系总览', view: 'influence-graph', props: { preset: 'overview' }, question: '组织关系的全貌是什么？' },
      { id: 'rel-people', label: '人物关系', view: 'influence-graph', props: { preset: 'people' }, question: '人与人怎么连在一起？' },
      { id: 'rel-work', label: '工作关系', view: 'influence-graph', props: { preset: 'work' }, question: '实际上谁在和谁一起干活？' },
      { id: 'rel-decision', label: '决策关系', view: 'influence-graph', props: { preset: 'decision' }, question: '实际上谁影响决策？' },
      { id: 'rel-reporting', label: '汇报关系', view: 'influence-graph', props: { preset: 'reporting' }, question: '名义上的组织是什么？' },
      { id: 'rel-resource', label: '资源关系', view: 'influence-graph', props: { preset: 'resource' }, question: '资源到底掌握在谁手里？' },
      { id: 'rel-info', label: '信息关系', view: 'influence-graph', props: { preset: 'information' }, question: '知识和信息流向谁？' },
      { id: 'rel-informal', label: '非正式组织', view: 'influence-graph', props: { preset: 'informal' }, question: '组织真实的影响网络是什么？' },
      { id: 'rel-conflict', label: '冲突与联盟', view: 'influence-graph', props: { preset: 'conflict' }, question: '谁在对抗、谁在结盟？' },
      { id: 'rel-influence', label: '影响力网络', view: 'influence-graph', props: { preset: 'community' }, question: '谁处在关键路口？' },
    ],
  },
  {
    id: 'analysis',
    label: '组织分析',
    icon: 'analysis',
    question: '系统为什么得出这个判断？',
    hideFor: [],
    items: [
      { id: 'an-health', label: '组织健康', view: 'dashboard', question: '健康度是怎么算出来的？' },
      { id: 'an-stability', label: '团队稳定性', view: 'team-situation', props: { initialTab: 'today' }, question: '团队为什么稳定或不稳定？' },
      { id: 'an-talent', label: '人才分析', view: 'cadre-growth', question: '能力证据是否支撑评价？' },
      { id: 'an-influence', label: '影响力分析', view: 'influence-graph', props: { preset: 'influence' }, question: '谁是核心人物，依据是什么？' },
      { id: 'an-dependency', label: '依赖分析', view: 'influence-graph', props: { preset: 'risk' }, question: '单点依赖从何而来？' },
      { id: 'an-power', label: '权力分析', view: 'influence-graph', props: { preset: 'promo' }, question: '领导力结构如何构成？' },
      { id: 'an-risk', label: '风险分析', view: 'team-situation', props: { initialTab: 'risks' }, question: '风险判断的证据是什么？' },
      { id: 'an-promo', label: '晋升推演', view: 'promotion', question: '晋升会怎样冲击组织？' },
      { id: 'an-sim', label: '组织模拟', view: 'sim-lab', props: { initialTab: 'org' }, question: '如果这样变，组织会怎样？' },
      { id: 'an-ai', label: 'AI 分析', view: 'chat', question: '用对话追问判断依据。' },
      { id: 'an-temporal', label: '时间轴分析', view: 'temporal-graph', props: { initialTab: 'snapshot' }, question: '判断是否随时间变化？' },
    ],
  },
  {
    id: 'assets',
    label: '组织资产',
    icon: 'assets',
    question: '系统掌握了哪些事实？数据是否可信？',
    hideFor: ['employee'],
    items: [
      { id: 'as-people', label: '人员', view: 'members', question: '组织里有哪些人？' },
      { id: 'as-roles', label: '角色', view: 'ai-native', question: '角色卡与职责如何定义？' },
      { id: 'as-projects', label: '项目', view: 'project-center', question: '项目主数据在哪维护？' },
      { id: 'as-work', label: '工作', view: 'daily-report', question: '工作记录从哪来？' },
      { id: 'as-events', label: '事件', view: 'calendar', question: '发生过哪些事件？' },
      { id: 'as-facts', label: '事实', view: 'fact-governance', props: { initialTab: 'all' }, question: '哪些事实已确认、哪些有冲突？' },
      { id: 'as-graph', label: '知识图谱', view: 'influence-graph', props: { preset: 'overview' }, question: '图谱里有哪些节点和边？' },
      { id: 'as-ontology', label: '本体治理', view: 'ontology-governance', props: { initialTab: 'analyze' }, question: '类型与语义是否干净？' },
      { id: 'as-rules', label: '关系规则', view: 'ontology-governance', props: { initialTab: 'constraints' }, question: '哪些推理被允许或禁止？' },
      { id: 'as-sources', label: '数据来源', view: 'fact-governance', props: { initialTab: 'jobs' }, question: '事实从哪抽取？' },
      { id: 'as-quality', label: '数据质量', view: 'entity-governance', question: '实体是否对齐、有无重复？' },
    ],
  },
]

export function groupsForObserver(observerId) {
  return NAV_GROUPS.filter((g) => !(g.hideFor || []).includes(observerId))
}

export function findNavItem(itemId) {
  for (const g of NAV_GROUPS) {
    const item = g.items.find((it) => it.id === itemId)
    if (item) return { group: g, item }
  }
  return null
}

export function observerById(id) {
  return OBSERVERS.find((o) => o.id === id) || OBSERVERS[0]
}

export function readObserver() {
  try {
    const v = localStorage.getItem(OBSERVER_KEY)
    if (OBSERVERS.some((o) => o.id === v)) return v
  } catch {
    /* ignore */
  }
  return 'leader'
}

export function writeObserver(id) {
  try {
    localStorage.setItem(OBSERVER_KEY, id)
  } catch {
    /* ignore */
  }
}
