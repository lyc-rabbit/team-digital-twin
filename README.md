# 团队数字孪生系统 · Team Digital Twin

一个具有记忆与推理能力的团队数字孪生系统——通过记录团队事件，自动解析事务进展、人际关系变化和情绪状态，并基于 DeepSeek 大模型进行智能问答和决策模拟推演。

## 核心功能

- **事件录入与自动解析**：输入一段非结构化事件描述，系统自动提取事务影响、关系变化（信任度+情绪值双维度）和情绪状态
- **3×3 关系状态网格**：可视化团队成员之间的双向关系得分，支持时间衰减计算
- **日历视图**：FullCalendar 月/周/日视图，按场景着色，点击查看事件完整解析
- **智能问答**：基于历史事件和关系数据，回答关于团队状态的问题
- **模拟推演**：输入假设场景，推演每位成员的心理活动、公开表态和最终决定

## 技术架构

```
前端 React + Tailwind CSS + FullCalendar
    │
后端 FastAPI + SQLite（事件溯源模式）
    │
硅基流动 DeepSeek API（V3 解析 + R1 推演）
```

## 环境要求

### Python 环境(后端)

- **Python 版本**:3.9 及以上(推荐 3.10 / 3.11)
  - 项目使用了 `list[str]` 等内置泛型语法([PEP 585](https://peps.python.org/pep-0585/)),需 Python 3.9+
- **依赖包**(见 [backend/requirements.txt](backend/requirements.txt)):

  | 包名 | 版本 | 用途 |
  |------|------|------|
  | fastapi | 0.115.6 | Web 框架 |
  | uvicorn[standard] | 0.34.0 | ASGI 服务器 |
  | openai | 1.59.7 | DeepSeek API SDK |
  | pydantic | 2.10.4 | 数据校验 |
  | python-dotenv | 1.0.1 | 环境变量加载 |

- **推荐安装方式**(Windows):

  ```bash
    conda activate team-twin
    cd d:\pro\research\team-digital-twin-main\backend
    pip install -r requirements.txt
    python main.py
  ```

  Linux / macOS:

  ```bash
  cd backend
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  ```

### Node.js 环境(前端)

- **Node.js 版本**:18 及以上(需支持 Vite)
- **包管理器**:npm(随 Node.js 安装)

## 快速开始

### 1. 后端

```bash
cd backend
pip install -r requirements.txt

# 配置 API Key（可选，不配置则进入降级模式）
cp .env.example .env
# 编辑 .env 填入 SILICONFLOW_API_KEY

python main.py
```

### 2. 前端

```bash
cd frontend
npm install
npm run dev
```

### 3. 一键启动

```bash
chmod +x start.sh
./start.sh
```

访问 http://localhost:5173 即可使用。

## 项目结构

```
team-twin/
├── start.sh                  # 一键启动脚本
├── backend/
│   ├── .env.example          # API Key 配置模板
│   ├── database.py           # 数据库 + 事件溯源 + 初始数据
│   ├── llm_client.py         # DeepSeek 集成 + 降级 mock
│   ├── memory_engine.py      # 关系重放 + 衰减计算
│   ├── event_processor.py    # 事件解析链路
│   ├── main.py               # FastAPI 路由
│   └── requirements.txt
└── frontend/
    ├── src/
    │   ├── App.jsx               # 主框架 + 可折叠侧边栏
    │   ├── api/client.js         # API 封装
    │   └── components/
    │       ├── Dashboard.jsx     # 总览（健康度+关系网格+情绪）
    │       ├── EventLogger.jsx   # 事件录入
    │       ├── CalendarView.jsx  # 日历视图
    │       └── ChatPanel.jsx     # 智能对话+模拟推演
    └── ...
```

## 配置说明

| 环境变量 | 说明 | 默认值 |
|----------|------|--------|
| `SILICONFLOW_API_KEY` | 硅基流动 API Key | 空（降级模式） |
| `SILICONFLOW_BASE_URL` | API 端点 | `https://api.siliconflow.cn/v1` |
| `DEEPSEEK_MODEL_EXTRACT` | 事件解析模型 | `deepseek-ai/DeepSeek-V3` |
| `DEEPSEEK_MODEL_SIMULATE` | 模拟推演模型 | `deepseek-ai/DeepSeek-R1` |
| `DEEPSEEK_MODEL_CHAT` | 问答模型 | `deepseek-ai/DeepSeek-V3` |

## 降级模式

未配置 `SILICONFLOW_API_KEY` 时，系统自动切换到规则引擎模式：
- 事件解析：基于关键词匹配提取情绪和关系变化
- 模拟推演：基于人设模板生成推演结果
- 智能问答：基于本地数据生成简单回答

配置 API Key 后所有功能自动切换到 DeepSeek 真实推理。
