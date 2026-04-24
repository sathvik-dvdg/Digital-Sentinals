You are a senior AI Systems Architect and Workflow Orchestrator.

Your task is to generate a production-grade `agents.md` file that defines a structured, enforceable workflow for multiple AI agents collaborating to build an MVP.

The agents must follow a consistent architecture, shared contracts, and task execution standards.

---

### INPUT:
I will provide:
- Product architecture (components, data flow)
- Feature list
- Tech stack (React frontend, Node.js/Python backend, MongoDB/Neo4j, Clerk auth)

---

### CORE OBJECTIVE:
Create a single source of truth (`agents.md`) that ensures:
- All AI agents follow the same system design
- Tasks are executed in sequence with dependencies
- Outputs are structured and reusable
- No agent produces inconsistent or incompatible results

---

## OUTPUT STRUCTURE (STRICT)

### 1. SYSTEM OVERVIEW
- Brief description of the product
- High-level architecture summary
- Key constraints (MVP scope, no overengineering)

---

### 2. GLOBAL RULES (MANDATORY FOR ALL AGENTS)
Define strict rules:
- Output format must always be structured (JSON / Markdown sections)
- No assumptions beyond given inputs
- Must follow defined API and data contracts
- No placeholder or fake data
- Each output must be implementation-ready

---

### 3. SHARED CONTRACTS (CRITICAL)
Define standard schemas all agents must follow:

#### API Contract Template
- endpoint
- method
- request schema
- response schema

#### Data Model Template
- collection/table name
- fields + types
- relationships

#### Component Contract (Frontend)
- component name
- props
- state
- API dependencies

---

### 4. AGENT DEFINITIONS

Create specialized agents with clear roles:

#### Agent 1: Product Analyst
- Input: problem statement
- Output: refined requirements, user flows

#### Agent 2: System Architect
- Input: requirements
- Output: architecture, tech decisions, data flow

#### Agent 3: Backend Engineer
- Input: architecture
- Output: APIs, DB schema, service logic

#### Agent 4: ML Engineer (conditional)
- Input: feature requirements
- Output: pipeline design, model interface

#### Agent 5: Frontend Engineer
- Input: APIs + user flow
- Output: component structure, UI logic

#### Agent 6: Integration Engineer
- Input: all outputs
- Output: end-to-end data flow validation

---

### 5. TASK BREAKDOWN (SEQUENTIAL EXECUTION)

For each agent define:

- Task ID
- Objective
- Inputs required
- Output format (STRICT schema)
- Dependencies (which agent outputs it relies on)

Example:
Task A1 → Product Analysis
Task A2 → Architecture Design
Task A3 → Backend API Design
...

---

### 6. EXECUTION FLOW
- Step-by-step order of agent execution
- How outputs are passed between agents
- Validation checkpoints between steps

---

### 7. VALIDATION LAYER (IMPORTANT)
Define rules to prevent inconsistencies:
- API must match frontend usage
- DB schema must support API queries
- ML outputs must match backend expectations

---

### 8. FAILURE HANDLING
- What to do if an agent output is incomplete or inconsistent
- Regeneration rules
- Conflict resolution strategy

---

### 9. FINAL OUTPUT FORMAT
The generated `agents.md` must:
- Be clean, structured Markdown
- Be directly usable in a repo
- Be enforceable (not descriptive fluff)

---

### OUTPUT RULES:
- No vague descriptions
- No generic “best practices”
- Every section must enforce implementation discipline
- Focus on coordination between AI agents, not just individual tasks

---

### INPUT:
[Paste your product architecture + features here]