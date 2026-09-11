<p align="center">
  <img src="frontend/public/favicon.svg" width="56" height="56" alt="团队数字孪生">
</p>

<h1 align="center">团队数字孪生</h1>

<p align="center">
  <strong>中文</strong> · <a href="./README.en.md">English</a>
</p>

<p align="center">
  <strong>同一事实 · 多视角</strong><br>
  把职场里真正发生的事，变成可追溯、可追问、可推演的组织记忆。
</p>

<p align="center">
  <em>A workplace digital twin: evidence → facts → knowledge graph → insight.<br>
  Not another chatbot sitting on an org chart.</em>
</p>

<p align="center">
  <img src="docs/assets/hero-team-digital-twin.png" alt="Team Digital Twin — 人、证据与组织图谱" width="100%">
</p>

<p align="center">
  <a href="#十分钟讲清一件事"><strong>看故事</strong></a>
  ·
  <a href="#快速开始"><strong>立刻跑起来</strong></a>
  ·
  <a href="docs/scenarios-and-storylines.md"><strong>演示脚本</strong></a>
  ·
  <a href="docs/ontology-governance-confirmation-spec.md"><strong>本体规范</strong></a>
</p>

---

## 为什么现有「组织智能」经常是错的

通讯录、OKR、日报、大模型总结，最后往往画出一张**漂亮的错误网**：

| 系统常这样推 | 现实往往是 |
|---|---|
| 编制上「负责」项目 → 此人做了全部技术 | 领导挂名，工程师把系统送上线 |
| 向谁汇报 → 此人培养了谁 | 汇报是节奏，培养是行为 |
| 成果挂在谁名下 → 此人创造了成果 | 归属可以归领导，贡献仍在做架构的人身上 |
| 职位高 → 能力高、准备度高 | 头衔不是证据 |

团队数字孪生把这件事做成一条**可审计流水线**：LLM 只抽取候选，**写图谱必须人确认**；确认之后，分析与推演也不得跨语义域偷换概念。

<p align="center">
  <img src="docs/assets/pipeline.svg" alt="材料 → 事实 → 图谱 → 分析 → 推演" width="100%">
</p>

<p align="center">
  <img src="docs/assets/layers-evidence-to-insight.png" alt="从原始材料到事实、图谱与洞察" width="100%">
</p>

**总规则：事实可以证明事实；事实不能跨语义域无条件推理。**

---

## 核心卖点

<table>
<tr>
<td width="50%">

**事实层是一等公民**  
每条关系、每个态势判断，都要能指回来源、原文、时间与置信度。已确认事实不原地改写。

</td>
<td width="50%">

**责任被拆开，而不是被「负责」吞掉**  
组织责任、执行责任、管理责任、汇报责任分开记；成果归属 ≠ 技术贡献 ≠ 培养行为。

</td>
</tr>
<tr>
<td>

**同一套事实，四种管理工作流**  
老板看介入点，领导看团队，项目看交付，员工看成长。换视角不换数据。

</td>
<td>

**推演先算再写，不靠模型打神秘分**  
模拟实验室用规则与证据算出准备度 / 冲击，再让模型写摘要。说得出依据，才叫推演。

</td>
</tr>
</table>

<p align="center">
  <img src="docs/assets/story-ownership-vs-contribution.png" alt="组织挂名负责不等于技术贡献" width="88%">
</p>

<p align="center">
  <sub>同一成果可以「归领导」，技术贡献仍记在做架构的人身上。</sub>
</p>

---

## 四种视角，打开系统先回答不同的问题

界面按「谁在看」组织，而不是按技术模块堆砌。

| 视角 | 他们打开系统，先要看见 |
|---|---|
| **老板** | 公司 / 部门现在稳不稳？哪里需要我介入？ |
| **领导** | 谁过载、谁是单点、梯队够不够、新人要不要插手？ |
| **项目负责人** | 能不能按期交付？卡在哪、资源在谁手里？ |
| **员工** | 我做了什么被记下了吗？往上走还缺哪一类证据？ |

侧边栏对应七组能力：

| 分组 | 用来干什么 |
|---|---|
| **组织驾驶舱** | 异常优先：项目态势、人才、稳定性、关键人物与风险雷达 |
| **团队管理** | 管人：负载、分工、依赖、干部梯队、新人地图 |
| **项目与工作** | 管事：进度、阻塞、复盘；日报与日历进同一条证据链 |
| **个人成长** | 角色、已验证能力、可追溯贡献、晋升准备度 |
| **组织关系** | 汇报只是一层；还有工作、决策、资源、信息与非正式网络 |
| **组织分析** | 健康度、影响力、依赖、权力、晋升与 What-if 模拟 |
| **组织资产** | 人员、事件、事实、图谱、本体与数据质量——图谱从哪来、能不能改 |

全局悬浮按钮 **记录事件**：先写下发生了什么 → 进日历 → 生成待确认事实 → 你点确认才写图。

---

## 十分钟讲清一件事

产品线要上线「AI 客服一期」。编制上领导 A 是项目负责人，工程师 B 做架构和核心开发。领导每周向业务汇报，同时也是 B 的上级。

| 人 | 系统应记下 | 系统不得自动记下 |
|---|---|---|
| 领导 A | 管理责任、汇报责任、成果归属 | 技术贡献、培养了 B |
| 工程师 B | 执行责任、技术 / 架构贡献 | 「没当 OWNER 所以能力为零」 |

**演示节奏（可对着产品点）：**

1. **成员管理** 录入 A、B  
2. **记录事件**：B 完成接口与上线，A 做周报汇报  
3. **事实管理** 确认时把「负责」拆开——不要只留一条笼统的 OWNER  
4. **人物关系 / 驾驶舱**：A 是管理与归属，B 是执行与技术；没有「上级 = 导师」  
5. **模拟实验室**：问「B 能不能往管理岗走」——看证据，而不是看有没有当过负责人

逐步操作、每个页面「应该看到什么」，以及完整演示脚本，见 **[场景与故事线](docs/scenarios-and-storylines.md)**。

---

## 和「再包一层 ChatGPT」有什么不一样

1. **模型不准直接写图。** 抽取只产生待确认事实；确认、冲突处理、软删与失效都走治理。
2. **推理默认禁止跨域。** 「从汇报推出培养、从 OWNER 推出贡献」会变成撤销工单，进不了默认影响力 / 晋升计算。
3. **分析可回放。** 关系分、态势、准备度要能点到事件或事实，而不是一句空评语。
4. **无 Key 也能演示。** 未配置模型时自动降级为规则 / Mock，页面仍可点通。

这是可运行的研究原型与演示系统，不是已经在生产环境替你做绩效的产品。  
**请不要把本系统的分数、圈层或晋升推演当作正式绩效考核或人事处分依据。**

---

## 快速开始

**需要：** Python 3.9+（推荐 3.11）、Node.js 18+。

### 1. 后端

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS / Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # 可选：填入 SILICONFLOW_API_KEY
python main.py                # http://127.0.0.1:8000
```

macOS / Linux 也可在仓库根目录执行 `./start.sh`。

### 2. 前端

```bash
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

### 3. 可选：Neo4j

```bash
docker compose up -d          # 浏览器 http://localhost:7474
# 默认用户 neo4j / 密码见 docker-compose.yml
```

不配 Neo4j 时图谱走 SQLite，功能可完整演示。

### 4. 第一次打开建议

1. 左上角切换视角（老板 / 领导 / 项目负责人 / 员工），感受「同一事实 · 多视角」。
2. **组织资产 → 人员** 建几个人（仓库不预置 Mock 人设）。
3. 右下角 **记录事件**，写一条上线或指导。
4. **事实** 里确认待确认项，把「负责」拆开。
5. 回到驾驶舱、关系网、模拟实验室，检查系统有没有偷换概念。

---

## 架构

```
React + Tailwind + Vite          FastAPI + SQLite
驾驶舱 / 关系 / 事实 / 推演   ←→  事件溯源 · 事实治理 · 本体规则
        │                              │
        │                         可选 Neo4j
        ▼
  OpenAI 兼容网关（默认硅基流动 DeepSeek）
  抽取 V3 · 推演 R1 · 问答 V3
  无 Key 时自动降级为规则 / Mock
```

| 层 | 技术 |
|---|---|
| 前端 | React 18、Vite、Tailwind CSS、FullCalendar |
| 后端 | FastAPI、Pydantic、SQLite（事件、事实、本体） |
| 图存储 | SQLite 默认可跑通；[docker-compose.yml](docker-compose.yml) 可挂 Neo4j 5 |
| 模型 | OpenAI 兼容客户端，默认硅基流动 DeepSeek |

复制 `backend/.env.example` 为 `backend/.env`：

| 变量 | 含义 | 默认 |
|---|---|---|
| `SILICONFLOW_API_KEY` | 硅基流动 Key，空则降级 | 空 |
| `SILICONFLOW_BASE_URL` | API 根路径 | `https://api.siliconflow.cn/v1` |
| `DEEPSEEK_MODEL_EXTRACT` | 抽取 | `deepseek-ai/DeepSeek-V3` |
| `DEEPSEEK_MODEL_SIMULATE` | 推演 | `deepseek-ai/DeepSeek-R1` |
| `DEEPSEEK_MODEL_CHAT` | 问答 | `deepseek-ai/DeepSeek-V3` |
| `NEO4J_URI` / `USER` / `PASSWORD` | 可选图数据库 | 见 `.env.example` |

Key 在 [硅基流动](https://cloud.siliconflow.cn/) 申请。也可以把 Base URL 指到任何 OpenAI 兼容网关，并改模型名。

---

## 仓库与文档

```
team-digital-twin/
├── docs/                          # 场景预期、本体规范、宣传图
├── docker-compose.yml             # 可选 Neo4j
├── start.sh                       # 启动后端
├── backend/                       # FastAPI · 事实治理 · 本体 · 图谱算法
└── frontend/                      # React SPA · 四种观察者视角
```

- [场景与故事线](docs/scenarios-and-storylines.md) — 演示、验收、对外讲解的主文档
- [本体治理确认规范](docs/ontology-governance-confirmation-spec.md) — 工单、回放、不改节点 `type`
- [文档目录](docs/README.md)
- [宣传图说明](docs/assets/README.md)

---

## 适合拿去讲什么

- 组织智能 / 知识图谱 / 数字孪生方向的展示、课程与论文实验
- 想把「AI 管人」做成可审计流水线、而不是提示词玩具的团队
- 对「贡献被领导汇报吃掉」这类职场语义问题感兴趣的产品与研究伙伴

欢迎 Issue / PR：拦住非法推理、补可复现故事线、改进无 Key 降级体验。

个人开发，赞助走 [爱发电](https://afdian.com/a/lyc-rabbit)（请杯咖啡 / 一起盯着做 / 认真撑这个项目）。代码始终开源。

许可协议将在正式公开仓库时给出（计划使用宽松的 OSI 许可）。在此之前，代码仅供学习与协作讨论。

---

抽取与推演默认走 DeepSeek 系列（经硅基流动）。图算法、时态事实和本体工单，是为了让模型**少做它不该做的决定**。
