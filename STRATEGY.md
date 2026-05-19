# STRATEGY.md · HYLINE Intelligence

> Documento estratégico de referência. Lê isto antes de tudo.
> Compilado de emails recebidos, requisitos da HYLINE, e tendências
> de mercado para a indústria de janelas PVC em Portugal · Maio 2026.

---

## 1. Ponto de situação · onde estamos hoje

| Item | Estado |
|---|---|
| Backend funcional (5 ficheiros Python) | ✅ Existe · validado em browser real |
| Frontend (7 vistas, twin, drawer, alertas) | ✅ Existe · 13 checks passam |
| Procurement com 8 fornecedores · 11 itens | ✅ Backend + JS · Smoke test passou |
| Assistente com regras PT-PT | ✅ Funciona offline e online |
| Assistente com **Gemini real (function calling)** | ❌ Falta integrar |
| CSV export (6 datasets) | ✅ Funciona |
| Procurement UI 100% funcional | ⚠️ Falta validação completa em browser |
| Homepage simplificada (3 KPIs clicáveis) | ⚠️ Twin a renderizar 0 estações em última iteração — bug por corrigir |
| Deploy em Railway | ❌ Falta configurar |
| Apresentação 20 Mai | 1 dia disponível |
| Repositório no GitHub | ✅ `iamgoncalo/hyline-intelligence` criado |

**Bottom line:** temos ~90% do produto pronto, mas precisamos de **estabilizar o que existe + adicionar Gemini real + deploy** antes de 20 Mai.

---

## 2. Emails recebidos · o que a HYLINE pediu (estabelecido)

### Email Joana Barbosa · 15 Abril 2026 (informação confirmada da HYLINE)

> "Recebemos hoje, por parte da HYLINE, nova informação que vos poderá
> ajudar no desenvolvimento das soluções."

**(a) Indicadores que já controlam:**
- m² produzidos a nível **diário** e **mensal**
- Não conformidades (qualidade)

**(b) Indicadores que QUEREM implementar — o pedido específico:**
- **m² produzidos POR ESTAÇÃO** — controlo granular por posto de trabalho
- *Esta é a feature central do MVP.*

**(c) Fluxo de decisão · cadeia de responsabilidade:**

```
Operador / Chefe de Turno
       │
       │  questões operacionais (1º nível, autonomia local)
       ▼
   Departamento Qualidade (DQ)   ←  se for qualidade
   Departamento HST              ←  se for avaria/segurança
       │
       │  escalonamento
       ▼
Director de Produção             ←  decisão final · Filipe Gonçalves
```

**(d) Organograma da produção** — anexado por email (não temos cópia digital).

**(e) Layout da fábrica · planta simplificada:**

Duas linhas paralelas + 6 fases sequenciais por linha:
```
                      ┌─ Série de Correr ─┐
Receção materiais ────┤                    ├──── Embalamento ──── Expedição
                      └─ Série de Abrir ──┘

Fases por linha: Corte → Mecanização → Pré-montagem → Montagem → Colagem Vidro → Embalamento
```

Ala esquerda auxiliar: linha de ferro + projectos especiais.

### Email Joana Barbosa · 10 Abril 2026

> "Devido ao período de férias que atravessamos, a HYLINE não nos
> conseguiu enviar a informação solicitada [...] Reforçamos que a Fase 4
> – Desenvolvimento das soluções arrancou já a 06 de abril."

### Email Joana Barbosa · 3 Abril 2026 (visita 31 Mar)

> "Ficou claro que este momento foi determinante para o arranque desta fase."

### Datas confirmadas
| Quando | Evento |
|---|---|
| 6 Abr – 13 Mai | Fase 4 · Desenvolvimento |
| **20 Mai 10h00** | Fase 5 · Apresentação @ HYLINE |
| **27 Mai 17h30** | Fase 6 · Resultados @ Tenda Start Me Up |

### Critérios de avaliação (4)
1. **Adequação ao desafio** — resolver o problema real da HYLINE
2. **Potencial de aplicabilidade** — pode ser usado já amanhã
3. **Inovação e criatividade** — diferencia das outras propostas
4. **Qualidade da apresentação** — 10 minutos · demo + pitch

### Prémio
- €500 em serviços de empreendedorismo
- Possível **estágio na HYLINE**

### Sistemas existentes (não partir do zero — instrução explícita)
- **Primavera** — ERP · ordens, clientes, prazos
- **Preference** — chão de fábrica · eventos, fases, status técnico
- **Power BI** — dashboards actuais
- **Excel** — tudo o resto

### Restrições estabelecidas em conversa
- ❌ **Sem sensores físicos** (nenhuma vez)
- ❌ **Sem APIs externas** (Primavera/Preference só via CSV import)
- ❌ **Sem valores hardcoded** em código Python
- ✅ **Dados sintéticos mas comportamentalmente realistas** (não aleatórios)
- ✅ **Linguagem PT-PT** (não brasileiro, não inglês na UI)
- ✅ **5 ficheiros backend máximo**

---

## 3. Objectivos do MVP

### Objectivo primário
Resolver o pedido específico da HYLINE: **monitorizar m² produzidos por estação em tempo real**, com routing automático de alertas para a pessoa certa.

### Objectivos secundários (diferenciadores)
1. **Assistente Gemini** com tool-use — abre vistas, encomenda materiais, propõe optimizações por voz
2. **Procurement sustentável** — 8 fornecedores reais + score sustentabilidade ≥85
3. **Audit trail** de todas as decisões (são-poucas-acções-mas-fortes)
4. **Digital Twin** das 24 estações com partículas de fluxo
5. **Swarm Intelligence** subjacente (ACO/PSO para optimização)

### O que NÃO é objectivo
- Substituir Primavera ou Preference (integrar, não substituir)
- Forçar uso por todos os operadores (focar em DG + Chefes de Turno)
- Ter dados reais (toda a apresentação corre com dados sintéticos)

---

## 4. Estratégia técnica · backend

### Os 5 ficheiros Python (não mais)

```
backend/
├── config.py    Pydantic loader · valida config.yaml · única fonte de verdade
├── data.py      SQLite · ingestão Preference/Primavera · watchdog · seed_all
├── engine.py    KPIs · cálculo Desempenho · alertas · Google Trends + sugestões
├── agents.py    4 agentes: Monitorização · Diagnóstico · Otimização · Assistente (Gemini)
└── app.py       FastAPI · Jinja2 · ~30 endpoints
```

### Stack confirmada

| Camada | Tecnologia | Razão |
|---|---|---|
| Linguagem | Python 3.12 | Estável, AsyncIO maduro |
| API | FastAPI 0.115 | Async, OpenAPI auto, Pydantic v2 nativo |
| Validação | Pydantic 2.9 | Type-safe, valida config no startup |
| BD | SQLite | Zero ops, ficheiro único, suficiente para 100k events |
| Templates | Jinja2 3.1 | Server-side render, zero build step |
| Watchdog | watchdog 5.0 | Detecta CSV no inbox em <1s |
| Charts | SVG nativo escrito à mão | Zero dependências, controlo total |
| AI | google-generativeai 0.8 + fallback regras | Custo controlado, falha graceful |
| Testes | playwright (browser real) | Apanha bugs que pytest não vê |
| HTTP client | httpx 0.28 | Async-first |
| ML/Optim | scipy 1.14 (Hungarian) + numpy 1.26 | Otimização de atribuições |

### Bibliotecas que NÃO usamos (decisão consciente)

| Não usar | Porquê |
|---|---|
| Django | Muito pesado para 5 ficheiros |
| SQLAlchemy | sqlite3 stdlib chega; menos magia |
| Celery / Redis | Watchdog + asyncio chega |
| React / Vue | Server-render é mais rápido para o caso |
| Chart.js / D3 | SVG nativo é mais controlável |
| Docker (em dev) | Overhead desnecessário; uvicorn directo |
| pytest-asyncio | TestClient resolve |

---

## 5. Estratégia técnica · frontend

### Princípios
1. **Server-rendered first** — Jinja2 entrega HTML pronto, JS hidrata depois
2. **Zero build step** — sem webpack, sem vite, sem TypeScript
3. **Zero CDN runtime** — fontes em produção: self-hosted
4. **CSS variables** para temas (já implementado)
5. **Mobile-first breakpoint** a 900px

### Estrutura de ficheiros

```
frontend/
├── templates/
│   └── dashboard.html.j2          7 secções + drawer + assistente flutuante + modal
└── static/
    ├── css/planta.css             ~500 linhas · CSS variables · zero frameworks
    ├── js/app.js                  ~1100 linhas · módulos: render, fetch, agents, procurement
    └── factory.svg                Layout original da HYLINE como referência
```

### Vistas
1. **Homepage** — Twin central + 3 KPIs clicáveis + Obras + Alertas
2. **Alertas** — 4 colunas (HST · DQ · Director · Chefe)
3. **Ação** — 4 agentes + propostas de reatribuição + chat
4. **Escala** — Mercado (Google Trends) + Sugestões + Prioridades estratégicas
5. **Procurement** — Catálogo (filtros eco) + Carrinho + Checkout sustentável
6. **Sustentabilidade** — CO₂, energia, circularidade
7. **Definições** — Equipa · Parâmetros · CSV Pipeline · Arquitectura

---

## 6. Swarm Intelligence · como o aplicamos

O AFI (Architecture of Freedom Intelligence) traz três algoritmos de
Swarm Intelligence directamente aplicáveis à HYLINE:

### (a) ACO · Ant Colony Optimization · routing de ordens

Quando uma encomenda pode ir tanto pela Série Correr como pela Série Abrir,
qual escolher?

- **Feromonas digitais** = histórico de m²/h efectivos em cada linha
- **Heurística α** = peso da experiência passada
- **Heurística β** = peso do estado actual (backlog, avarias)
- **Evaporação ρ** = quão depressa a memória esquece

Resultado: routing dinâmico que aprende com os dados reais.

### (b) PSO · Particle Swarm Optimization · alocação de operadores

No início do turno, qual operador para qual estação?

- 30 partículas (combinações possíveis)
- Cada partícula é uma atribuição completa
- Fitness = Desempenho global previsto
- Convergência em 100 iterações

Resultado: sugestão à Chefe de Turno em <2 segundos.

### (c) Stigmergy · trail-based coordination

Os eventos do chão de fábrica deixam "rastos" no SQLite:
- Cada janela completada deixa um "trail" de tempo de ciclo
- O sistema aprende padrões sem programação explícita
- Anomalias destacam-se automaticamente (z-score > 2)

### Como mostrar isto na apresentação
- **Não falar de jargão.** Nunca dizer "Ant Colony", "PSO", "Stigmergy".
- **Falar de outcomes.** "Sugere a melhor combinação de operadores em 2 segundos."
- **Mostrar a UI.** O painel de Otimização tem 3 sugestões com botão "Aplicar".

---

## 7. Tendências de mercado · janelas PVC Portugal 2026

> Dados do `config.yaml` (snapshot dos termos seguidos no Google Trends PT, 12 meses).

### Tendências em alta
1. **Eficiência energética como diferenciador** (+27%) → janelas com **U-value baixo** são premium
2. **Reabilitação habitacional** (peak 92/100) → IFRRU, Vale Eficiência, fundos UE estão a mover mercado
3. **PVC reciclado** → Saint-Gobain Cradle2Cradle, REHAU Geneo com 72% reciclado
4. **Triplo vidro baixa emissividade** → padrão Passivhaus a ganhar tracção

### Tendências em baixa
- Janelas de alumínio puro (sem corte térmico): -15% YoY
- Janelas single-pane: praticamente extintas no novo

### O que isto significa para a HYLINE
A HYLINE produz PVC, está bem posicionada. O nosso dashboard:
- Mostra estes trends na vista Escala
- O assistente sugere "encomendar vidro sustentável" e mostra topo 3 com score ≥85
- Prioriza fornecedores com certificações (ISO 14001, EPD, Cradle2Cradle)

### Fornecedores com maior score sustentabilidade no catálogo
| Score | Fornecedor | Categoria |
|---|---|---|
| 93 | EcoSeal Vedantes | Vedantes 100% reciclados |
| 91 | Saint-Gobain Glass Portugal | Vidro |
| 88 | REHAU Polímeros Portugal | Perfis (VinylPlus) |
| 85 | Kömmerling Ibéria | Perfis (greenline) |

---

## 8. Como abrir o Claude Code · setup limpo

### Pré-requisitos
- macOS 13+ / Ubuntu 20.04+ / Windows com WSL2
- Node.js 18+ (`node --version`)
- Git
- Conta Claude Pro/Max **ou** chave API Anthropic

### Instalação (30 segundos)

```bash
# Via npm (recomendado)
npm install -g @anthropic-ai/claude-code@latest
claude --version    # deve mostrar 2.x.x

# Autenticar
claude auth login   # abre browser, OAuth com a tua conta
```

### Primeira sessão no repositório

```bash
# Clonar o repo
git clone https://github.com/iamgoncalo/hyline-intelligence
cd hyline-intelligence

# Inicializar (opcional, se quiseres /init para criar CLAUDE.md)
# JÁ TEMOS CLAUDE.md — não correr /init

# Abrir Claude Code
claude
```

Primeira mensagem (cola exactamente):

```
Lê o CLAUDE.md neste repo antes de fazer qualquer coisa. Confirma que
entendes os 15 hard limits. Quando estiveres pronto, responde apenas:
"CLAUDE.md lido · 17 secções · pronto."
```

### Comandos úteis do Claude Code

| Comando | Faz |
|---|---|
| `claude` | Inicia sessão interactiva |
| `/clear` | Limpa contexto (útil se ficar lento) |
| `/init` | Cria CLAUDE.md inicial (não usar, já temos) |
| `/bug` | Reporta bug para a Anthropic |
| `/compact` | Comprime conversa antiga |
| `Esc duplo` | Cancela uma operação a meio |

### Gotchas comuns

1. **Não correr `sudo npm install`** — usa nvm ou `~/.npm-global`
2. **Windows? WSL2 sempre.** PowerShell tem fricção desnecessária
3. **`.env` nunca no Git.** Já está no `.gitignore` que entreguei
4. **Cada sessão começa com /clear** se a anterior foi longa
5. **Plan mode (`/plan`)** — peço-lhe plano antes de mexer em código

---

## 9. Checklist · como tudo funciona em alta inteligência

### Pré-demo (até 19 Mai)

#### Backend
- [ ] 5 ficheiros Python (não mais, não menos)
- [ ] Pydantic valida config.yaml no startup
- [ ] D-weights somam exactamente 1.0
- [ ] Zero hardcoded numbers (CI verifica)
- [ ] Watchdog detecta CSV em <1s
- [ ] SQLite cria índices ao primeiro arranque
- [ ] Smoke test: 12 endpoints retornam 200

#### Frontend
- [ ] 7 vistas navegáveis sem erro JS
- [ ] Twin renderiza 24 estações
- [ ] Drawer abre ao clicar em estação
- [ ] 3 KPIs no homepage são clicáveis e navegam
- [ ] Procurement: filtros eco, adicionar, remover, checkout funcionam
- [ ] Assistente flutuante abre com ⌘K
- [ ] CSV download produz ficheiro válido (≥20 linhas)
- [ ] Confirm dialog ("Are you sure?") em todas as acções escritas

#### AI / Assistente
- [ ] Gemini com function calling implementado em agents.py
- [ ] Fallback baseado em regras se GEMINI_API_KEY ausente
- [ ] Cap diário de chamadas (100/dia)
- [ ] Endpoint `/api/assistant/usage` expõe gasto

#### Linguagem & UI
- [ ] Zero "F", "P", "D", "α", "scipy", "Python puro" visível
- [ ] Tudo em PT-PT (não brasileiro)
- [ ] Brand lowercase: "hyline", "planta"
- [ ] Source pill mostra LIGADO/FALLBACK no Trends
- [ ] Dados sintéticos rotulados SIMULADO

#### Testes
- [ ] Playwright corre os 13 checks em verde
- [ ] Console JS sem erros (apenas fontes em sandbox podem falhar)
- [ ] Screenshot de cada vista guardado em `docs/screenshots/`

#### Deploy
- [ ] Railway configurado (ou alternativa)
- [ ] .env com GEMINI_API_KEY em production
- [ ] Health check em `/`
- [ ] HTTPS obrigatório
- [ ] Backup do SQLite ao final do dia

### Demo (20 Mai 10h00)

| # | Passo | Duração |
|---|---|---|
| 1 | Abrir dashboard, mostrar twin com 24 estações | 30s |
| 2 | Clicar numa estação vermelha · drawer abre | 30s |
| 3 | Navegar para Alertas · 4 colunas routed | 45s |
| 4 | Navegar para Ação · 4 agentes + sugestões otimização | 45s |
| 5 | Abrir Procurement · filtrar ≥85 sustentável · adicionar 2 itens | 60s |
| 6 | Pressionar ⌘K · Assistente abre · "encomendar vidro sustentável" | 45s |
| 7 | Voltar a Procurement · Confirmar Compra (audit action #1) | 30s |
| 8 | Definições · 4 colunas · download CSV | 30s |
| **Total** | | **~5 min** |

Resto: 5 min Q&A.

---

## 10. Segurança · checklist obrigatória

### Antes do commit
- [ ] `.env` no `.gitignore` (já está)
- [ ] `data/hyline.db` no `.gitignore` (já está)
- [ ] Nenhuma API key no código (procurar por `sk-`, `AIzaSy`, `gsk_`)
- [ ] CORS configurado (não permitir `*` em prod)
- [ ] Rate limiting (limitar `/api/assistant` a 60/min por IP)

### Em produção
- [ ] HTTPS obrigatório (Railway dá grátis)
- [ ] `GEMINI_API_KEY` em variáveis de ambiente, nunca no código
- [ ] Logs sem PII (não logar conteúdo dos CSVs raw)
- [ ] CSP header: `default-src 'self'`
- [ ] Confirm dialog em **todas** as escritas (já está)

### Auth (não no MVP, mas decidir)
- Para apresentação: **sem auth** (demo local)
- Para piloto na HYLINE: HTTP Basic com .htpasswd em Railway
- Para produção: OAuth (Google/Microsoft) via `python-multipart` + JWT

---

## 11. Plano para fechar hoje

Ordenado por prioridade. Cada bloco ≈ 30-60 minutos.

### Bloco 1 · Estabilizar o que existe (NÃO adicionar features novas)
1. Corrigir o bug "twin renderiza 0 estações" na última iteração
2. Re-correr `scripts/browser_test.py` até passar 13/13
3. Re-correr `scripts/smoke_test.py` até passar 12/12

### Bloco 2 · Integrar Gemini real
1. Adicionar `google-generativeai==0.8.3` (já em requirements)
2. Em `agents.py`, criar `AssistantAgent.answer_with_gemini()`
3. 7 tools: `open_view`, `search_catalog`, `add_to_cart`, `checkout`, `get_station_status`, `suggest_reassignment`, `global_kpis`
4. Fallback se `GEMINI_API_KEY` ausente (mantém regras actuais)
5. Endpoint `/api/assistant/usage` para tracking de custo

### Bloco 3 · Deploy
1. Criar `railway.json` ou `Procfile`
2. Push para `iamgoncalo/hyline-intelligence`
3. Conectar Railway ao GitHub
4. Variáveis: `GEMINI_API_KEY`, `PORT`, `DB_PATH=/data/hyline.db`
5. Volume persistente em `/data`
6. Testar URL pública

### Bloco 4 · Preparar apresentação
1. Slides (5 slides): problema · solução · arquitectura · demo · próximos passos
2. Cronometrar a demo 3 vezes (deve dar ≤5 min)
3. Tirar screenshots de cada vista (HD, 1440×900)
4. Preparar respostas para 3 perguntas previsíveis:
   - "Quanto custa por mês para a HYLINE?"
   - "Como integra com o Primavera?"
   - "E se não houver internet?"

---

## 12. Que perguntas decidir contigo agora

Antes de avançar com Bloco 2 (Gemini), preciso de saber:

**A.** O Claude Code que vais abrir vai partir do ZIP que já entreguei,
ou queres que recomece do zero usando só o CLAUDE.md?
*Recomendação:* partir do ZIP. Está 90% pronto.

**B.** A `GEMINI_API_KEY` — vais buscá-la ao Google AI Studio agora,
ou queres adiar para depois da demo?
*Recomendação:* já. A chave gratuita dá para a demo inteira sem custo.
[https://aistudio.google.com/apikey](https://aistudio.google.com/apikey)

**C.** Deploy em Railway ou ficamos com localhost para 20 Mai?
*Recomendação:* Railway. Mostra que é production-ready, ponto de
inovação extra para o critério "Potencial de aplicabilidade".

---

## 13. Risco · o que pode correr mal

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| Wifi falha na HYLINE | Média | Alto | Levar HTML standalone offline · funciona 100% sem rede |
| Gemini API rate-limited | Baixa | Médio | Fallback de regras já implementado |
| Demo passa-se das 5 min | Média | Baixo | Cronometrar 3× antes |
| Júri pergunta sobre integração real Primavera | Alta | Médio | Ter slide "Roadmap Q3" pronto |
| Erro JS inesperado durante demo | Baixa | Alto | Browser test cobre 13 fluxos; refresh resolve |

---

## 14. Próximo prompt para o Claude Code (copy-paste)

Quando estiveres em `claude` no repo:

```
Boas. Lê o CLAUDE.md e o STRATEGY.md. Faz isto pela ordem:

1. Corre `python scripts/browser_test.py` e diz-me o que falha (sem
   corrigir).
2. Se algum check falha, mostra-me o stack trace e propõe a alteração
   mais pequena possível.
3. Aplica a alteração só depois de eu dizer "ok".
4. Re-corre o teste até 13/13 passarem.

Não inicies nada novo até este teste passar.
```

---

**Última actualização:** 19 Mai 2026 · Gonçalo Melo de Magalhães
