# CLAUDE.md · HYLINE Intelligence

> Operational instructions for **Claude Code** working in this repository.
> Read this file **first** in every session. It encodes hard limits that
> are not negotiable and provides the mental model needed to make good
> decisions without asking.

---

## 1. The project in one paragraph

HYLINE is a Portuguese manufacturer of PVC windows. They have two data sources
(`Primavera` ERP for orders, `Preference` shop-floor for production events)
that don't talk to each other. **HYLINE Intelligence** is a single-pane
dashboard that ingests both, computes Desempenho per station via the
**Architecture of Freedom Intelligence (AFI)** framework, raises alerts to
the right person automatically, suggests sustainable procurement actions,
and exposes everything through a calm Apple-quality UI with a Gemini-powered
assistant that can take actions on behalf of the user.

**Single source of truth:** the square metre (m²). Every window has
`area_m2 = width × height / 1e6` computed once at ingestion and never recalculated.

**Submission**: Challenges You contest via START Esposende. Presentation **20 May 2026**.

---

## 2. Mental model · the data flow

```
CSV file lands in data/inbox/
        │
        ▼  (backend/data.py — watchdog)
SQLite (data/hyline.db)
        │
        ▼  (backend/engine.py — KPIs, AFI, alerts)
In-memory snapshot (refreshed every 1s)
        │
        ▼  (backend/agents.py — 4 agentes)
Diagnóstico · Otimização · Assistente
        │
        ▼  (backend/app.py — FastAPI)
REST endpoints
        │
        ▼  (frontend/static/js/app.js)
Dashboard renders, polls /api every 1s
```

This is the **only** acceptable flow. Do not introduce queues, microservices,
or external state stores. SQLite is the durable layer; everything else is
derived from it.

---

## 3. Hard limits (NON-NEGOTIABLE)

These are enforced. Any PR that breaks them must be rejected by Claude Code,
even if the user asks. State the violation and refuse.

| ID | Rule |
|---|---|
| **HL-01** | Maximum **5 backend Python files**: `config.py`, `data.py`, `engine.py`, `agents.py`, `app.py`. Plus `__init__.py`. Nothing else in `backend/`. |
| **HL-02** | **Zero hardcoded numbers** in any backend `.py`. All numerics come from `config.yaml` validated by Pydantic. |
| **HL-03** | **Zero AI calls** in the 1-second monitoring tick. Cost ceiling: €0.20/day, €7/month total AI spend. |
| **HL-04** | Brand: lowercase `planta` and `hyline` always. Never `HYLINE` in copy except the wordmark logo. |
| **HL-05** | Language: **European Portuguese** (PT-PT, not PT-BR) for everything user-facing. English allowed for code comments and API responses' technical fields. |
| **HL-06** | **AFI internal terms are never visible in the UI.** Translation table: `F → Desempenho`, `P → Fluxo`, `D → Fricção`, `α → Sensibilidade`. Never show `F = (P/D)^α`, never show `α=1,242`, never show `Python puro · tick 60s`. |
| **HL-07** | F = P / D is treated as a **hypothesis under test**, never a proven law. In any academic-context output, say so. |
| **HL-08** | D-weights must sum to **exactly 1.0** at startup. Pydantic validates this. |
| **HL-09** | `seed=2026` for all stochastic operations. |
| **HL-10** | D is always **geometric** (`exp(Σ wₖ·ln(max(dₖ, 1.0)))`), never additive. |
| **HL-11** | "Are you sure?" confirm dialog on **every** decision that writes to the audit trail (resolve alert, apply reassignment, checkout, save threshold, reset). |
| **HL-12** | Refresh interval = **1 second**. Both the watcher tick and the dashboard fetch. |
| **HL-13** | Every numeric output that comes from simulated data is labeled `SIMULADO` in the UI. When the source is real CSVs, it shows `LIGADO`. |
| **HL-14** | No flexbox-only DOCX. If a deliverable is a Word doc, use the docx library directly (we don't ship Word docs from this app — but if asked, follow the rule). |
| **HL-15** | No emoji in UI, no icon-only buttons without label, no grey except hairline (`#E5EEE8`). |

---

## 4. The 5 backend files · what each does

```
backend/
├── __init__.py        empty (or version string)
├── config.py          Pydantic loader for config.yaml · single source of truth
├── data.py            SQLite schema · ingestion · watchdog · seed_all
├── engine.py          KPIs · AFI Desempenho · alert classification · Trends · suggestions
├── agents.py          4 agents: Monitorização · Diagnóstico · Otimização · Assistente
└── app.py             FastAPI · Jinja2 render · ~30 endpoints
```

**If you find yourself wanting a 6th file, you are wrong.** Refactor inside
one of the existing five. Common temptations to resist:
- "I want a `procurement.py`" → no, this goes in `data.py` (catalog/cart queries) + `app.py` (endpoints).
- "I want a `gemini.py`" → no, this is part of `agents.py` (Assistente agent).
- "I want a `routes/` folder" → no, FastAPI routes live in `app.py` and only there.

---

## 5. The 4 agents (UI-visible names in PT-PT)

| Agent | Internal | UI name | Tick | AI? | Cost/month |
|---|---|---|---|---|---|
| Monitor | `MonitorAgent` | **Monitorização** | 1s | no | €0.00 |
| Alert | `AlertAgent` | **Diagnóstico** | on-trigger | yes (Gemini) | €0.36 |
| Optimiser | `OptimiserAgent` | **Otimização** | 15min | yes (scipy + Gemini for rationale) | €0.18 |
| Chatbot | `AssistantAgent` | **Assistente** | on-message | yes (Gemini with tool-use) | €4.88 |

The Assistente is the front-door for everything. It must be able to:
- Open any view (`open_view`, target=name)
- Search the catalog and recommend sustainable items
- Add items to cart (with confirm)
- Trigger procurement checkout (with confirm)
- Suggest operator reassignments (links to Otimização output)
- Answer factual questions about KPIs

---

## 6. config.yaml is the contract

Every parameter the system uses is in `config.yaml`. Adding a new parameter
**requires**:
1. Add to `config.yaml`
2. Add to the matching Pydantic model in `config.py`
3. Reference via `cfg().section.field` in code, never as a literal

Top-level sections:
```yaml
app:            # name, port, refresh_seconds
paths:          # inbox, processed, db
afi:            # alpha, weights (must sum to 1.0)
factory:        # viewBox, sector positions
stations:       # 24 stations · 19 productive + 5 structural
thresholds:     # green_min, amber_min, sustained_minutes
alerts:         # routing rules per type
teams:          # roles + members
csv_schema:     # column mappings for Primavera + Preference
scale:          # Google Trends terms + strategic priorities
sustainability: # carbon, energy coefficients
brand:          # colors, fonts
procurement:    # suppliers + catalog (8 + 11 items minimum)
```

---

## 7. Decision-making rules for Claude Code

When the user asks you to do something:

1. **Read CLAUDE.md** (this file) before touching code.
2. **Read the relevant skill** if creating files: docx → `pptx → ...
3. **Check `config.yaml` first.** If the answer might already be a config value, it is.
4. **Refuse silently-bad asks**: if the user asks to hardcode a number, say "that violates HL-02, putting in config.yaml under section X".
5. **Test before declaring done.** Use playwright for real-browser tests. Don't trust `python --check` alone.
6. **Prefer minimal changes.** A small edit that works beats a rewrite.
7. **Show your work**: when you change behaviour, run the smoke test and paste the output.

---

## 8. Common tasks · short recipes

### Add a new endpoint
```
1. Edit backend/app.py inside the create_app() function
2. Use existing dlayer / engine functions; don't bypass them
3. Return plain dicts (FastAPI serialises); use Pydantic only for inputs
4. Test with TestClient before exposing
```

### Add a new procurement item
```
1. Edit config.yaml under procurement.catalog
2. Wipe DB: rm data/hyline.db
3. Restart: python -m backend.app  (auto-seeds from config)
```

### Add a new agent capability (Gemini tool-call)
```
1. Define the tool schema in agents.py inside AssistantAgent
2. Add the handler that maps to existing dlayer / engine functions
3. Add the intent recognition in the answer() method
4. Add a UI suggestion chip in templates/dashboard.html.j2
```

### Run end-to-end
```bash
python scripts/generate_sample_data.py --drop
python -m backend.app                       # http://localhost:8000
python scripts/browser_test.py              # validates 13 checks
python scripts/render_standalone.py         # produces hyline_dashboard_preview.html
```

---

## 9. Gemini integration · how it must work

The Assistente agent uses **Google Gemini 2.0 Flash** with **function calling**.

```python
# agents.py — AssistantAgent.answer()
import google.generativeai as genai

TOOLS = [
    {"name": "open_view",            "description": "Navega para uma vista do dashboard", "parameters": {"target": {"type":"string", "enum":["home","alerts","action","scale","procurement","sustain","settings"]}}},
    {"name": "search_catalog",       "description": "Procura itens no catálogo de fornecedores",  "parameters": {"category": {...}, "min_sustainability": {...}}},
    {"name": "add_to_cart",          "description": "Adiciona item ao carrinho",                 "parameters": {"catalog_id": {...}, "quantity": {...}}},
    {"name": "checkout",             "description": "Confirma compra (requer confirmação)",      "parameters": {"confirmed": {"type":"boolean"}}},
    {"name": "get_station_status",   "description": "Devolve estado actual de uma estação",       "parameters": {"station_id": {...}}},
    {"name": "suggest_reassignment", "description": "Pede sugestão de reatribuição",              "parameters": {}},
    {"name": "global_kpis",          "description": "Devolve KPIs globais (m², desempenho, alertas)", "parameters": {}},
]

# Gemini decides which tool to call; we execute it and feed back the result.
# Final answer is in PT-PT, with actionable buttons attached.
```

**Fallback policy**: if `GEMINI_API_KEY` is not set or the call fails, fall
back to the rule-based answer() that already exists. The dashboard must
**never** be unusable due to Gemini being unavailable.

**Cost ceiling**: Gemini 2.0 Flash is ~$0.10 / 1M input tokens. Average
question is ~500 tokens. Hard cap of 10k calls/month = €5. The Assistente
includes a daily counter exported via `/api/assistant/usage`.

---

## 10. Frontend rules

- **HTML/CSS/JS only**, no React, no Vue, no bundler. The dashboard is one
  Jinja2 template + one CSS file + one JS file. Total < 200 KB minified.
- **No external CDN at runtime** for fonts (Google Fonts is OK during dev,
  but the standalone preview must be self-contained).
- **No Chart.js** or other charting library. SVG charts are written by hand.
- **No emoji**. The only character allowed outside Latin range is `²` (square),
  `·` (middle dot), `→` (right arrow), `↑↓` (up/down trend), `✓` (done).
- **Mobile breakpoint** at 900px (single-column rail collapses to top bar).
- **Touch targets** minimum 36×36 px.

---

## 11. Quality bar · what "done" means

A feature is done when **all** of these are true:

- [ ] config.yaml updated (if it adds parameters)
- [ ] backend smoke test passes (`python scripts/smoke_test.py`)
- [ ] browser test passes (`python scripts/browser_test.py`) — all 13 checks green
- [ ] Standalone preview regenerates without console errors
- [ ] UI strings in PT-PT, no AFI jargon visible
- [ ] Every new button has a confirmed action (no dead clicks)
- [ ] Screenshot taken at 1440×900, attached to PR
- [ ] No new dependencies unless absolutely necessary

---

## 12. Things to never do

- ❌ Never call `pytrends` synchronously in a request handler (it's a 3-12s
  blocking call). Wrap in cache with TTL ≥ 1h. Fallback to config snapshot
  on failure. Mark source as `LIGADO` or `FALLBACK` in the UI.
- ❌ Never reference the user's previous projects (HORSE CFT, Renault, Cacia)
  in HYLINE materials. They are clients of Planta, not relevant here.
- ❌ Never write "F-debt" or "Custo de Atrito" or any AFI internal term in
  the UI. The translation table in §3 is law.
- ❌ Never ship without running browser_test.py. Trusting only Python tests
  is what caused the previous "twin renders 0 stations" bug.
- ❌ Never commit `data/hyline.db` or `.env`. The `.gitignore` covers this;
  don't override.

---

## 13. The Architecture of Freedom Intelligence (AFI) · context for engine.py

> This section explains the maths so future Claude Code sessions can reason
> about it. It is NOT user-facing. Hard limit HL-06 still applies.

For each station `s` with target throughput `T_s m²/h` and observed
throughput `t_s`:

```
Efficiency:         η_s = t_s / T_s
Perception P_s:     topological score · how easy material flows in/out
                     (BFS from input buffers; weighted by station kind)
Distortion D_s:     geometric mean of 6 weighted channels
                     D_s = exp(Σ wₖ · ln(max(dₖ, 1.0)))
                     where wₖ are channel weights summing to 1.0
                     and dₖ ∈ [0, 100] is the % distortion in that channel.

Desempenho F_s:     (P_s / D_s)^α        with α ≈ 1.242

D channels for HYLINE (weights sum to 1.0):
  cadência    0.35    — throughput vs target
  qualidade   0.25    — non-conformities ratio
  equipamento 0.15    — machine downtime
  prazo       0.15    — backlog vs deadline pressure
  operador    0.05    — operator presence
  setup       0.05    — changeover time
```

These are starting weights. The user may calibrate them via `/api/thresholds`.

---

## 14. Repository structure

```
hyline-intelligence/
├── CLAUDE.md                  ← you are here
├── README.md                  ← public-facing project intro
├── PROMPTS.md                 ← prompt library for Claude Code sessions
├── LICENSE                    ← MIT
├── .gitignore
├── .env.example               ← GEMINI_API_KEY, etc
├── requirements.txt
├── config.yaml                ← single source of truth
├── backend/
│   ├── __init__.py
│   ├── config.py
│   ├── data.py
│   ├── engine.py
│   ├── agents.py
│   └── app.py
├── frontend/
│   ├── templates/
│   │   └── dashboard.html.j2
│   └── static/
│       ├── css/planta.css
│       ├── js/app.js
│       └── factory.svg
├── scripts/
│   ├── generate_sample_data.py
│   ├── smoke_test.py
│   ├── browser_test.py
│   └── render_standalone.py
├── sample_data/
│   ├── preference_events.csv
│   └── primavera_orders.csv
├── data/                      ← gitignored
│   ├── inbox/
│   ├── processed/
│   └── hyline.db
└── docs/
    ├── ARCHITECTURE.md        ← deep dive on AFI maths
    ├── DEPLOYMENT.md          ← Railway + secrets
    └── PRESENTATION_PT.md     ← talking points for 20 May
```

---

## 15. First-session checklist for Claude Code

When the user opens this repo with `claude` for the first time:

```bash
# 1. Bootstrap
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium     # for browser tests

# 2. Verify environment
cp .env.example .env
# Edit .env to add GEMINI_API_KEY (optional; rule-based fallback exists)

# 3. Generate seed data
python scripts/generate_sample_data.py --drop

# 4. Smoke test
python scripts/smoke_test.py
# Expected: 12/12 endpoints return 200; 8 suppliers; 11 catalog items

# 5. Live run
python -m backend.app
# Open http://localhost:8000 — confirm twin renders 24 stations

# 6. Standalone preview (for offline demo)
python scripts/render_standalone.py
# Produces hyline_dashboard_preview.html — open with double-click
```

If any step fails, **stop and diagnose** before continuing. Don't paper over
errors with try/except.

---

## 16. The 20 May presentation · what we are showing

5-minute pitch. The demo flow must work end-to-end without restart:

1. **Open dashboard** → twin renders, 24 stations, live KPIs, 3 KPI cards clicáveis
2. **Click a red station** → drawer opens, Desempenho %, factores, operadores, alertas
3. **Click "Alertas"** → 4 colunas routed (HST / DQ / Director / Chefe)
4. **Click "Ação"** → 4 agentes visíveis, propostas de reatribuição, assistente
5. **Open Procurement** → catálogo com 11 itens, filtrar por "≥85 sustentável", adicionar 2 itens, abrir carrinho, ver score 89/100
6. **Pressionar ⌘K** → assistente abre, perguntar *"encomendar vidro sustentável"* → top 3 itens com botão para abrir Procurement
7. **Voltar a Procurement → Confirmar Compra** → are-you-sure → action #1 criada
8. **Definições** → mostrar 4 colunas (Equipa, Parâmetros, Connections, Arquitectura), download CSV das estações

Each step must take ≤ 15 seconds. Total demo: 4 minutes + 1 minute Q&A.

---

## 17. When in doubt

> "What gets smarter gets cheaper." — Law of Intelligent Midas

If you're about to add complexity, ask: does this make the next change
easier or harder? If harder, find another way.

> "Designing to Free."

The user is HYLINE's Chefe de Turno or Director de Produção. They are
busy, they don't read manuals, they know the factory floor better than
any algorithm ever will. The dashboard's job is to **give them the right
piece of information at the right moment** and let them decide.

Never override human judgment. Always require confirmation. Always show
the source of every number.

---

**End of CLAUDE.md.** Read again at the start of each session.
