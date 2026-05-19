# HYLINE Intelligence

> Uma plataforma de inteligência para fábricas de janelas em PVC.
> Vê o que está a acontecer, em tempo real, e age — em vez de só reportar.

Plataforma desenvolvida por [**planta smart homes**](https://planta.design)
para a HYLINE, no âmbito do concurso *Challenges You* via START Esposende.

---

## O que é

A HYLINE produz janelas em PVC. Tem duas fontes de dados que não falam uma com a outra:

- **Primavera** (ERP) — encomendas, clientes, prazos
- **Preference** (chão de fábrica) — eventos de produção, fases, status

Cada uma exporta CSVs. Ninguém junta os dois. O Chefe de Turno corre entre
postos com folhas impressas; o Director de Produção pede relatórios para
saber o estado de uma encomenda; o Departamento de Qualidade descobre
falhas com 48h de atraso.

A **HYLINE Intelligence** resolve isto. Uma única plataforma que:

1. Lê os dois CSVs continuamente, junta-os pela única fonte de verdade — o **metro quadrado**
2. Mostra o estado de **24 estações** num gémeo digital ao segundo
3. Encaminha alertas automaticamente para o responsável certo (HST, DQ, Director, Chefe)
4. Sugere **compras sustentáveis** quando o stock baixa, com score de sustentabilidade ≥85
5. Permite ao Director conversar com um **assistente** que abre vistas, encomenda materiais, e propõe optimizações de equipa

---

## Stack

| Camada | Tecnologia |
|---|---|
| Backend | Python 3.12 · FastAPI · Pydantic · SQLite |
| Frontend | Jinja2 · vanilla JS · SVG nativo (zero dependências) |
| AI | Google Gemini 2.0 Flash (function calling) com fallback baseado em regras |
| Ingestão | Watchdog em `data/inbox/` · esquemas CSV configuráveis |
| Deploy | Railway (backend) · Vercel (preview estático) |

**Cinco ficheiros Python no backend. Apenas.** É uma regra dura.

---

## Princípios

- **Designing to Free.** A interface não substitui o operador — dá-lhe contexto.
- **What gets smarter gets cheaper.** Custo de IA total ≤ €7/mês.
- **Single source of truth.** O metro quadrado. Cada janela tem `area_m2` calculado uma vez.
- **Are you sure?** Toda a decisão escreve no audit trail. Confirmação obrigatória.
- **Português de Portugal.** Não brasileiro. Não inglês. Não jargão técnico na UI.

---

## Como correr

```bash
git clone https://github.com/iamgoncalo/hyline-intelligence
cd hyline-intelligence

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

cp .env.example .env
# (opcional) coloca a GEMINI_API_KEY · sem ela, o assistente usa regras

python scripts/generate_sample_data.py --drop
python -m backend.app

# Abre http://localhost:8000
```

**Preview offline** (HTML único, sem backend, para apresentações):

```bash
python scripts/render_standalone.py
open hyline_dashboard_preview.html
```

---

## Estrutura

```
hyline-intelligence/
├── CLAUDE.md                  ← instruções para Claude Code
├── config.yaml                ← fonte única de verdade
├── backend/                   ← 5 ficheiros Python, nada mais
├── frontend/                  ← um template Jinja2, um CSS, um JS
├── scripts/                   ← geração de dados, testes, deploy
├── sample_data/               ← CSVs de exemplo
└── docs/                      ← arquitectura, deploy, talking points
```

---

## Roadmap

- [x] Backend modular com 5 ficheiros · 30+ endpoints
- [x] Dashboard com 7 vistas · 24 estações no twin
- [x] Sistema de procurement com 8 fornecedores reais
- [x] Assistente com tool-use (Gemini) e fallback
- [x] CSV export (eventos, encomendas, alertas, estações, equipa, audit)
- [x] Browser tests (Playwright)
- [ ] Validação física no chão da fábrica HYLINE (Junho)
- [ ] App mobile para Chefes de Turno (iOS/Android)

---

## Licença

MIT · ver [LICENSE](LICENSE).

---

## Contacto

**Gonçalo Melo de Magalhães** — fundador, planta smart homes
[hi@planta.design](mailto:hi@planta.design) · [ORCID](https://orcid.org/0009-0008-6255-7724)

Concurso: **Challenges You** via START Esposende. Apresentação: **20 Maio 2026**.
