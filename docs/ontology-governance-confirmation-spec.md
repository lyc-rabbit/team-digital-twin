# 本体治理确认流 Spec V1.1

状态：已按 V1.1 落地（分析只产工单，确认后才写图）  
范围：只修「分析 → 工单 → 人工确认 → 应用」。不推翻 V1.0 的本体模型、不删节点、不改图谱 `type`。  
模块：`backend/knowledge_governance` + `OntologyGovernancePanel` + 重建钩子

---

## 0. 要解决的四个问题

| # | 现状 | 目标 |
|---|------|------|
| P1 | 「类型体系」把图实例芯片当主界面，不能对「这个节点建议归哪一类」点同意/不同意 | 类型树只管类型；实例归类一律进工单 |
| P2 | 重建图谱 / 语义增强会自动写 `ontology_type` 和推断边，抢在确认之前 | 分析只产草稿+工单；未确认不得写业务图 |
| P3 | 类型页只有新增、合并类型名；不能改描述、调父子；也不能把某实例的本体类从 Event 语义改到 Knowledge | 类型 CRUD 补齐；实例「挪类」= 改 `ontology_type`，不是改 `type` |
| P4 | 语义分析的「类别/实例混淆、弱语义」只是说明文字 | 每条问题变成可操作工单 |

---

## 1. 原则（不可破）

1. **不删除**已有图谱节点。
2. **不修改**节点字段 `type`（Person 永远是 Person）。「Event 挪到 Knowledge」在本模块的含义是：该节点的 **`ontology_type`** 改为 `Knowledge`（或挂 `IS_A`），图谱 `type` 仍为 Event。若业务上认为抽错了实体，工单动作选「转实体治理」，不在本体层改 `type`。
3. **LLM 只建议**，禁止 LLM 直接写图、写工单终态。
4. **已确认决策必须能在重建后回放**（类似实体治理的 alias）。未确认的推断边不得进入影响力/晋升默认计算。
5. 实体治理 = SAME_AS；本体治理 = IS_A / PART_OF / `ontology_type`。禁止用合并类型去合并两个图实例。

---

## 2. 对象分层（开发时必须分开渲染）

```
OntologyType          类型体系页主对象（Person / Resource / DeliveryResource …）
        │
        ├── 描述、父类型、允许关系     ← 类型治理操作
        └── 实例列表（只读摘要）      ← 点进去是工单，不是改类型名

GraphNode             图实例（Angel、某次会议、越南代理交付资源）
        │
        ├── type                 锁定，本模块只读
        ├── ontology_type        仅「已应用」工单可写
        └── proposed_ontology_type  仅草稿，确认前可改建议值

SemanticWorkItem      工单（唯一可「同意/改建议后同意/忽略」的对象）
```

**禁止**：在类型树芯片上直接编辑实例名称、删除实例、把芯片拖成合并实体。

---

## 3. 确认状态机

### 3.1 图侧语义写入的两种模式

| 模式 | 何时 | 写 `ontology_type` | 写推断边（USES/IS_A/…） |
|------|------|-------------------|-------------------------|
| `propose` | 分析、重建、刷新分析 | 否（可写 `proposed_*` 到工单 payload） | 否 |
| `apply` | 用户确认单条/批量工单，或「应用已确认策略」 | 是 | 仅已确认的推断 |

重建钩子 `GraphBuilder._enhance_semantics` **必须改为 `propose`**。  
按钮「运行语义增强」默认 `propose`。  
仅当用户明确点「应用已确认项」或确认工单后走 `apply`。

### 3.2 工单状态

```
open → accepted | rejected | deferred
accepted 之后重建：按 payload 回放，状态保持 accepted，禁止同一指纹再开一张重复 open 单
rejected / deferred：重建时不回放；同一指纹默认不再自动打开（除非 force 重新分析）
```

指纹 `fingerprint = suggestion_type + object_type + object_id + 规范化 payload 键`  
例如：`CLASSIFY_INSTANCE|node|<nodeId>`

### 3.3 禁止行为

- `enhance_graph` 里 `_classify_nodes` 直接 `upsert_node(ontology_type=…)`（未确认）。
- `_write_inferred` 把未确认推断写入 `oig_edges`（未确认）。
- `_refresh_suggestions` 里 `DELETE pending` 导致用户已看到的工单被冲掉；**只 upsert 同指纹的 open 单，不得删除 accepted/rejected**。

---

## 4. 工单模型（把分析变成可操作项）

沿用表 `semantic_suggestion`，扩展字段（缺列则 ALTER）：

| 字段 | 说明 |
|------|------|
| id | 工单 ID |
| fingerprint | 去重键，UNIQUE |
| suggestion_type | 见 4.1 |
| object_type | `node` / `edge` / `ontology_type` / `cluster` |
| object_id | 节点/边/类型 id |
| status | open / accepted / rejected / deferred |
| confidence | 0–1 |
| problem_code | 对应分析 `problems[].code` |
| title | 短标题，中文，一句话 |
| reason | 为什么建议 |
| current_json | 当前状态快照 |
| proposed_json | 建议动作（用户确认前可编辑） |
| applied_json | 实际应用结果（回放用） |
| source | `analyze` / `rebuild` / `manual` |
| created_time / updated_time | 北京时间 |

`proposed_json` 必须能被后端无歧义执行，禁止只存自然语言。

### 4.1 工单类型与动作

#### A. `CLASSIFY_INSTANCE`（P1 / P3 实例挪类）

触发：节点 `type` 与名称/邻居可能不一致；或分析 `NAME_TYPE_AMBIGUITY`；或用户从类型页点实例。

```json
{
  "node_id": "event_12",
  "graph_type": "Event",
  "current_ontology_type": "Event",
  "proposed_ontology_type": "Knowledge",
  "candidates": ["Event", "Knowledge", "Project"]
}
```

应用：`node.ontology_type = proposed_ontology_type`，**不改 `type`**。可选写 `IS_A` 到对应本体类节点（若图上存在类节点）。

UI：下拉改 `proposed_ontology_type` 后再「同意」。

#### B. `HIERARCHY_REFACTOR`（类别 vs 实例）

触发：`CLASS_INSTANCE_MIX`、`FLAT_RESOURCE_FAMILY`、hierarchy_candidates。

```json
{
  "child_id": "...",
  "child_name": "越南代理交付资源",
  "parent_id": "...",
  "parent_name": "交付资源",
  "proposed_ontology_type": "DeliveryResource",
  "do_not_merge": true
}
```

应用：子节点 `ontology_type`；写 `IS_A`/`PART_OF`（推断标记 + `confirmed=true`）。禁止 SAME_AS。

#### C. `WEAK_RELATION`（弱语义）

触发：`HAS_RESOURCE` / 泛化「关联」、分析 `WEAK_RELATION_SEMANTICS`。

```json
{
  "edge_id": "proj|HAS_RESOURCE|res",
  "source": "...",
  "target": "...",
  "current_relation": "HAS_RESOURCE",
  "proposed_relation": "USES",
  "keep_original": true
}
```

应用：保留原边，**新增**语义边 `USES`（或用户改选的 `DEPENDS_ON`/`PART_OF`），`confirmed=true`。禁止删 `HAS_RESOURCE`。

#### D. `TYPE_SCHEMA`（类型页：描述 / 父子）

触发：用户在类型页编辑，或分析建议某类型应有 parent。

```json
{
  "type_id": "ot_deliveryresource",
  "name": "DeliveryResource",
  "description": "...",
  "parent_id": "ot_resource"
}
```

应用：`upsert_type`。改父子不移动图实例。若需要，可同时批量生成 `CLASSIFY_INSTANCE` 草稿（仍须逐条或「对本类型下未分类实例全部同意」）。

类型页的「保存描述 / 改父类型」可以 **直接 apply**（这是本体层元数据，不是图实例），但必须 `snapshot` 以便回滚。不必每条描述改动都先变工单。  
**实例归类**必须走工单。

#### E. `INFER_RELATION`（自动推理待确认）

触发：推理引擎在 `propose` 模式产出的候选边。

```json
{
  "source": "...",
  "target": "...",
  "relation": "USES",
  "valid_from": "2026-06-01",
  "valid_to": "",
  "rule_id": "...",
  "rule_name": "ResourceHierarchyPropagation",
  "explanation": "…有效: 2026-06~2026-09"
}
```

应用：写入图边 + `temporal_fact`（若时态层可用），属性 `inferred=true, confirmed=true`。

忽略：不写边。重建后不得再自动写这条（指纹拒绝）。

---

## 5. 分析 → 工单映射（P4）

分析器继续只读。新增 `service.publish_work_items(report, inferred_candidates)`：

| problems.code | 生成 |
|---------------|------|
| `CLASS_INSTANCE_MIX` | 每个 class/instance 对或未挂总类的实例 → `HIERARCHY_REFACTOR` |
| `FLAT_RESOURCE_FAMILY` | 每个 cluster member（排除总类名自身）→ `HIERARCHY_REFACTOR` 或批量 `CLASSIFY_INSTANCE` |
| `WEAK_RELATION_SEMANTICS` | 每条弱边 → `WEAK_RELATION` |
| `NAME_TYPE_AMBIGUITY` | 每个同名跨 type 组 → 每节点一张 `CLASSIFY_INSTANCE`（candidates=出现过的类型） |

无 problem 但有推理候选：每条候选 → `INFER_RELATION`（可按 rule 折叠展示，确认仍按边）。

**同指纹 open 单**：更新 reason/confidence/proposed，保留 id。  
**已 accepted/rejected**：不新建；`force=true` 的「重新分析」才把 rejected 变回 open。

---

## 6. 重建图谱逻辑（P2）

顺序保持：

```
clear 操作图 → 组织/日报/事件/资源 → 影响力/圈层
→ kg.propose()          # 只分析 + 工单，不写 ontology_type/推断边
→ replay_accepted()     # 回放 accepted 工单的 applied_json
→ temporal.sync()
→ neo4j
```

`replay_accepted()`：按 accepted 时间序执行 apply 函数，幂等。  
未确认的 `proposed_ontology_type` 不得出现在业务查询默认视图。

前端「重建图谱」文案需标明：不会自动采纳未确认本体建议。

---

## 7. API（在现有 `/api/knowledge-governance` 上扩展）

保持 overview / analyze / types。调整语义：

| 方法 | 路径 | 行为 |
|------|------|------|
| GET | `/analyze` | 只读报告；可选 `?publish=true` 同步工单 |
| POST | `/analyze/publish` | 跑分析并 upsert 工单，**propose 模式** |
| GET | `/work-items` | `status, type, problem_code, page` |
| PATCH | `/work-items/{id}` | 只改 `proposed_json`（open 状态） |
| POST | `/work-items/{id}/accept` | 应用 proposed → 写图 |
| POST | `/work-items/{id}/reject` | 忽略 |
| POST | `/work-items/{id}/defer` | 暂不处理 |
| POST | `/work-items/accept-batch` | ids[]，部分失败要返回每条结果 |
| PUT | `/ontology/types/{id}` | 直接改描述/parent_id + snapshot |
| POST | `/ontology/types` | 新增类型 |
| POST | `/ontology/types/merge` | 只合并 **OntologyType**，响应里写明「不会合并图实例」 |
| POST | `/enhance` | **改为 propose**；旧的一键写图删除或改名为 `/apply-confirmed` |
| POST | `/apply-confirmed` | 回放全部 accepted（重建后补写） |

废弃或改语义：`POST /ontology/apply` 不再等于「分析完立刻全图增强」。若保留，应等于「对当前全部 open 工单一键接受」（高危，UI 要二次确认，且默认不做）。

---

## 8. 前端（`OntologyGovernancePanel`）

### 8.1 信息架构

| Tab | 主对象 | 可做的事 |
|-----|--------|----------|
| 语义分析 | 报告 + 工单计数 | 刷新分析（propose）；点问题跳到工单过滤 |
| 待确认工单 | SemanticWorkItem | 改建议、同意、忽略、暂缓；按 problem_code 筛选 |
| 类型体系 | OntologyType 树 | 选中类型：改描述、改父类型（下拉即可，拖拽可选）、新增、合并类型 |
| 关系推理 | 规则 + 已确认/待确认推断 | 规则开关；待确认推断是 `INFER_RELATION` 工单的视图，不是已写边 |
| 回滚 | ontology_revision | 回滚类型/规则；**不**回滚已删节点（本来就不能删） |

去掉把「本体草稿整包应用」当作唯一确认口。草稿可保留只读预览，CTA 改为「生成工单」。

### 8.2 类型体系页布局

```
左：类型树（只显示类型名、实例数量）
右：
  - 类型元数据：名称只读（改名=高级，V1.1 可不做）、描述可编辑、父类型下拉、保存
  - 「本类型下的图实例」列表：名称、graph_type、ontology_type、若有 open 工单显示「待确认」
  - 行操作：「建议重分类」→ 打开/创建 CLASSIFY_INSTANCE 工单
```

合并类型：文案必须是「合并本体类型 A 到 B」，二次确认「不会把图里的人/事件合成一个节点」。

### 8.3 工单卡片（所有类型统一）

- 标题、问题码、置信度、当前 vs 建议  
- 可编辑建议（分类下拉 / 关系下拉 / 父节点）  
- 同意 / 忽略 / 暂缓  
- 同意后展示应用结果：写了哪些 `ontology_type`、新增了哪条边（原边仍在）

### 8.4 顶栏按钮

- 「刷新分析」→ publish 工单，不写图  
- 删除或降级「运行语义增强」；若保留，改为「生成待确认推理工单」  
- 「应用已确认项」→ apply-confirmed（重建后用）

---

## 9. 与时态 / 影响力

未确认推断边：不写 `oig_edges`，故默认影响力看不到。  
已确认推断边：`confirmed=true`，重建后回放，时态 `valid_from/to` 从工单 proposed 带入。

---

## 10. 开发顺序

1. 工单指纹 + 停止 `clear_pending`；analyze publish  
2. `enhance_graph(mode=propose|apply)`；重建改 propose + replay accepted  
3. 四种工单 apply 实现（CLASSIFY / HIERARCHY / WEAK_RELATION / INFER）  
4. 类型 PUT 描述与 parent  
5. 前端：待确认 Tab + 类型页改版 + 分析跳转  
6. 回归：重建后 accepted 仍在；rejected 不再写边；图 `type` 不变

---

## 11. 验收

**AC1** 打开类型体系：主树是 Resource → DeliveryResource 等类型，不是一排会议芯片。芯片或列表仅在右侧实例区，且可点「建议重分类」。

**AC2** 仅「刷新分析 / 重建」之后，图上 `ontology_type` 不会被批量改掉；工单为 open。确认后该节点才出现新的 `ontology_type`。

**AC3** 用户把某 Event 实例的建议类改为 Knowledge 并同意：`type` 仍为 Event，`ontology_type=Knowledge`。

**AC4** 弱语义工单同意后：原 `HAS_RESOURCE` 仍在，并多一条 `USES`。

**AC5** 分析里的 CLASS_INSTANCE_MIX / WEAK_RELATION_SEMANTICS 至少各有对应 open 工单（有数据时）。

**AC6** 改类型描述、改父类型可保存并可回滚；合并两个 OntologyType 不会减少图节点数。

**AC7** 重建图谱后：accepted 工单效果还在；rejected 的推断边不会回来。

---

## 12. 明确不做（本迭代）

- 拖拽改图实例之间的业务边（那是图谱编辑，不是本体确认）  
- 用本体工单做 Angel=Angel Zhang（实体治理）  
- LLM 自动 accept  
- 修改 Neo4j 节点 label 作为换类手段
