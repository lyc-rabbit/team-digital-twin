<p align="center">
  <img src="frontend/public/favicon.svg" width="56" height="56" alt="Team Digital Twin">
</p>

<h1 align="center">Team Digital Twin</h1>

<p align="center">
  <a href="./README.md">中文</a> · <strong>English</strong>
</p>

<p align="center">
  <strong>One set of facts · many viewpoints</strong><br>
  Turn what actually happened at work into organizational memory you can trace, question, and simulate.
</p>

<p align="center">
  <em>A workplace digital twin: evidence → facts → knowledge graph → insight.<br>
  Not another chatbot sitting on an org chart.</em>
</p>

<p align="center">
  <img src="docs/assets/hero-team-digital-twin.png" alt="Team Digital Twin — people, evidence, and an organization graph" width="100%">
</p>

<p align="center">
  <a href="#a-ten-minute-story"><strong>The story</strong></a>
  ·
  <a href="#quick-start"><strong>Quick start</strong></a>
  ·
  <a href="docs/scenarios-and-storylines.md"><strong>Demo script</strong></a>
  ·
  <a href="docs/ontology-governance-confirmation-spec.md"><strong>Ontology spec</strong></a>
</p>

---

## Why most “org intelligence” is wrong

Directories, OKRs, daily reports, and LLM summaries often produce a **beautiful wrong graph**:

| The system infers… | Reality is often… |
|---|---|
| Listed as project owner → this person did all the engineering | A leader’s name is on it; an engineer shipped it |
| Reports to X → X mentored them | Reporting is cadence; mentoring is a behavior |
| Outcome attributed to X → X created the outcome | Ownership can sit with a leader; contribution still belongs to whoever designed it |
| Senior title → high capability and readiness | A title is not evidence |

Team Digital Twin turns this into an **auditable pipeline**: the LLM only extracts candidates; **writing to the graph requires human confirmation**. After that, analysis and simulation still cannot swap meanings across semantic domains.

<p align="center">
  <img src="docs/assets/pipeline.svg" alt="Materials → facts → graph → analysis → simulation" width="100%">
</p>

<p align="center">
  <img src="docs/assets/layers-evidence-to-insight.png" alt="From raw materials to facts, graph, and insight" width="100%">
</p>

**The standing rule: facts may prove facts. Facts must not be used for unconstrained cross-domain inference.**

---

## What this is good at

<table>
<tr>
<td width="50%">

**Facts are first-class**  
Every edge and every situation call has to point back to a source, quote, time, and confidence. Confirmed facts are not edited in place.

</td>
<td width="50%">

**Responsibility is split, not swallowed by “owns”**  
Organizational, execution, management, and reporting responsibility are recorded separately. Outcome ownership ≠ technical contribution ≠ mentoring.

</td>
</tr>
<tr>
<td>

**One fact base, four management workflows**  
The boss looks for where to intervene; the lead looks at the team; the project looks at delivery; the employee looks at growth. Change the viewpoint, not the data.

</td>
<td>

**Simulate, then write — no mysterious model score**  
The simulation lab computes readiness / impact from rules and evidence, then asks the model to summarize. If you cannot show the basis, it is not a simulation.

</td>
</tr>
</table>

<p align="center">
  <img src="docs/assets/story-ownership-vs-contribution.png" alt="Organizational ownership is not the same as technical contribution" width="88%">
</p>

<p align="center">
  <sub>The same outcome can “belong” to a leader; the technical contribution still sits with the person who designed it.</sub>
</p>

---

## Four viewpoints, four first questions

The UI is organized by **who is looking**, not by technical modules.

| Viewpoint | What they need to see first |
|---|---|
| **Boss** | Is the company / department stable? Where do I need to step in? |
| **Lead** | Who is overloaded, who is a single point of failure, is the bench deep enough, should I intervene with a newcomer? |
| **Project owner** | Can we ship on time? Where is it stuck, and who holds the resources? |
| **Employee** | Was what I did recorded? What kind of evidence am I still missing to move up? |

The sidebar maps to seven capability groups:

| Group | What it is for |
|---|---|
| **Org cockpit** | Exceptions first: project situation, talent, stability, key people, risk radar |
| **Team management** | People: load, division of work, dependencies, leadership bench, newcomer map |
| **Projects & work** | Delivery: progress, blockers, reviews; daily reports and calendar share one evidence chain |
| **Personal growth** | Role, verified capabilities, traceable contribution, promotion readiness |
| **Org relations** | Reporting is only one layer; also work, decision, resource, information, and informal networks |
| **Org analysis** | Health, influence, dependency, power, promotion, and what-if simulation |
| **Org assets** | People, events, facts, graph, ontology, and data quality — where the graph came from, and whether it can be changed |

Global **Record event** button: write down what happened → it lands on the calendar → pending facts are generated → the graph is written only after you confirm.

---

## A ten-minute story

A product line is shipping “AI customer support, phase 1.” On paper, lead A is the project owner; engineer B did the architecture and core implementation. A reports progress to the business every week, and is also B’s manager.

| Person | The system should record | The system must not auto-record |
|---|---|---|
| Lead A | Management responsibility, reporting responsibility, outcome ownership | Technical contribution, “mentored B” |
| Engineer B | Execution responsibility, technical / architecture contribution | “Never was OWNER, therefore capability is zero” |

**Demo beat (click through the product):**

1. **People** — add A and B  
2. **Record event** — B finished the API and launch; A delivered the weekly report  
3. **Facts** — when confirming, split “owns it”; do not leave a single vague OWNER  
4. **Relations / cockpit** — A is management and ownership; B is execution and engineering; no “manager = mentor”  
5. **Simulation lab** — ask “can B move into a management role?” — look at evidence, not at whether they were ever listed as owner

Step-by-step clicks, expected UI on each page, and a full demo script: **[Scenarios and storylines](docs/scenarios-and-storylines.md)** (Chinese).

---

## How this is not “ChatGPT with an org chart”

1. **The model must not write the graph.** Extraction only produces pending facts. Confirmation, conflicts, soft-delete, and invalidation all go through governance.
2. **Cross-domain inference is off by default.** “Reporting ⇒ mentoring” or “OWNER ⇒ contribution” becomes a revoke ticket, and does not enter default influence / promotion scoring.
3. **Analysis is replayable.** Relationship scores, situation, and readiness have to point at events or facts, not an empty caption.
4. **It still demos without an API key.** With no model configured, the stack falls back to rules / mocks; pages remain clickable.

This is a runnable research prototype and demo — not a production performance-review product.  
**Do not treat scores, circles, or promotion simulations from this system as formal appraisal or HR discipline.**

---

## Quick start

**You need:** Python 3.9+ (3.11 recommended), Node.js 18+.

### 1. Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS / Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # optional: set SILICONFLOW_API_KEY
python main.py                # http://127.0.0.1:8000
```

On macOS / Linux you can also run `./start.sh` from the repo root.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

### 3. Optional: Neo4j

```bash
docker compose up -d          # browser: http://localhost:7474
# default user neo4j / password in docker-compose.yml
```

Without Neo4j, the graph runs on SQLite. The full demo still works.

### 4. First-run path

1. Switch viewpoint in the top-left (Boss / Lead / Project owner / Employee) and feel “one set of facts · many viewpoints.”
2. **Org assets → People** — add a few people (the repo does not ship mock personas).
3. Bottom-right **Record event** — write a launch or a coaching moment.
4. In **Facts**, confirm pending items and split “owns.”
5. Go back to the cockpit, relation graph, and simulation lab. Check whether the system is still swapping meanings.

---

## Architecture

```
React + Tailwind + Vite          FastAPI + SQLite
Cockpit / relations / facts    ←→  event sourcing · fact governance · ontology rules
        │                              │
        │                         optional Neo4j
        ▼
  OpenAI-compatible gateway (SiliconFlow DeepSeek by default)
  Extract: V3 · Simulate: R1 · Chat: V3
  No API key → rules / mock fallback
```

| Layer | Stack |
|---|---|
| Frontend | React 18, Vite, Tailwind CSS, FullCalendar |
| Backend | FastAPI, Pydantic, SQLite (events, facts, ontology) |
| Graph store | SQLite is enough to run; [docker-compose.yml](docker-compose.yml) can attach Neo4j 5 |
| Models | OpenAI-compatible client, SiliconFlow DeepSeek by default |

Copy `backend/.env.example` to `backend/.env`:

| Variable | Meaning | Default |
|---|---|---|
| `SILICONFLOW_API_KEY` | SiliconFlow key; empty = fallback | empty |
| `SILICONFLOW_BASE_URL` | API root | `https://api.siliconflow.cn/v1` |
| `DEEPSEEK_MODEL_EXTRACT` | Extraction | `deepseek-ai/DeepSeek-V3` |
| `DEEPSEEK_MODEL_SIMULATE` | Simulation | `deepseek-ai/DeepSeek-R1` |
| `DEEPSEEK_MODEL_CHAT` | Chat | `deepseek-ai/DeepSeek-V3` |
| `NEO4J_URI` / `USER` / `PASSWORD` | Optional graph DB | see `.env.example` |

Get a key at [SiliconFlow](https://cloud.siliconflow.cn/). You can also point the base URL at any OpenAI-compatible gateway and change the model names.

---

## Repo map and docs

```
team-digital-twin/
├── docs/                          # scenarios, ontology spec, promo art
├── docker-compose.yml             # optional Neo4j
├── start.sh                       # start backend
├── backend/                       # FastAPI · fact governance · ontology · graph algorithms
└── frontend/                      # React SPA · four observer viewpoints
```

- [Scenarios and storylines](docs/scenarios-and-storylines.md) — demo, acceptance, and the main talk track (Chinese)
- [Ontology governance confirmation spec](docs/ontology-governance-confirmation-spec.md) — tickets, replay, do not change node `type` (Chinese)
- [Docs index](docs/README.md)
- [Promo art notes](docs/assets/README.md)

---

## Who this is for

- Demos, courses, and paper experiments in org intelligence / knowledge graphs / digital twins
- Teams that want “AI managing people” as an auditable pipeline, not a prompt toy
- Product and research partners who care when reporting eats contribution

Issues and PRs are welcome: block illegal inference, add reproducible storylines, improve the no-key fallback.

This is a solo project. Sponsorship: [Afdian](https://afdian.com/a/lyc-rabbit) (coffee / follow the build / back the project). The code stays open source.

A license will be published with the public repo (a permissive OSI license is planned). Until then, the code is for learning and collaboration.

---

Extraction and simulation default to DeepSeek via SiliconFlow. Graph algorithms, temporal facts, and ontology tickets exist so the model **does fewer decisions it should not make**.
