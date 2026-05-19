# PROMPTS.md · Library for Claude Code sessions

Copy-paste these as the **first message** in `claude` (or via `claude < prompt.txt`).
Each prompt is self-contained and respects the hard limits in CLAUDE.md.

---

## 0. Session warmup (always first)

```
Lê o CLAUDE.md neste repo antes de fazer qualquer coisa. Confirma que entendes:
  1. Há um limite duro de 5 ficheiros Python no backend.
  2. Zero números hardcoded — tudo vem do config.yaml.
  3. Linguagem PT-PT em toda a UI, zero jargão AFI (F, P, D, α nunca visíveis).
  4. Assistente Gemini com fallback baseado em regras.
  5. Refresh ao segundo, zero chamadas AI no tick do monitor.

Quando estiveres pronto, responde apenas: "CLAUDE.md lido · 16 secções · pronto."
```

---

## 1. Bootstrap do repositório

```
Estou a clonar este repo limpo. Faz o setup completo:

  1. Cria .venv e instala requirements.txt
  2. playwright install chromium
  3. Copia .env.example para .env
  4. Corre python scripts/generate_sample_data.py --drop
  5. Corre python scripts/smoke_test.py e cola o output
  6. Arranca o servidor em background e abre http://localhost:8000
  7. Corre python scripts/browser_test.py
  8. Se algum teste falhar, para e diagnostica antes de continuar

No fim, dá-me um resumo do estado: quantos eventos ingeridos, quantas
estações, quantos itens no catálogo, e se há erros JS na consola.
```

---

## 2. Adicionar a integração Gemini ao Assistente

```
O Assistente actualmente usa regras simples em agents.py. Quero adicionar
o Gemini 2.0 Flash com function calling, mantendo as regras como fallback.

Requisitos:
  • Usar google-generativeai (já em requirements.txt)
  • Tools: open_view, search_catalog, add_to_cart, checkout, get_station_status,
    suggest_reassignment, global_kpis
  • Se GEMINI_API_KEY não estiver no .env, cair em fallback silencioso
  • Custo: cap de 100 chamadas/dia · expor /api/assistant/usage
  • Resposta sempre em PT-PT
  • A acção (open_view, add_to_cart, etc) volta ao frontend como
    {"actions": [{"kind": "...", "target": "...", "label": "..."}]}
  • O frontend já tem o handler para isto em app.js (função handleAction)

Hard limits: tudo dentro de backend/agents.py. Não criar gemini.py.
Não tocar nos outros 4 ficheiros do backend excepto se for óbvio.

Antes de tocar em código, lê agents.py inteiro e diz-me o que vais mudar.
```

---

## 3. Adicionar um novo tipo de alerta

```
Quero adicionar um novo tipo de alerta: "stock_baixo" — disparado quando
algum item do catálogo cai abaixo de 20% do nível inicial.

Faz isto:
  1. Adicionar a rota de routing em config.yaml -> alerts.routing
     (responsável: Director de Produção)
  2. Adicionar a regra de geração em engine.py (não criar ficheiro novo)
  3. Adicionar a sugestão automática no Assistente: quando há stock_baixo,
     sugerir "encomendar X" com botão Action
  4. Testar: forçar um item a 15% e verificar que o alerta aparece na UI

Não toques no schema da BD. Os alertas já têm a coluna alert_type.
```

---

## 4. Optimização de performance da homepage

```
O homepage está a fazer 8 fetches em paralelo a cada 1s. Quero reduzir
isto a 2 fetches sem perder fidelidade dos dados.

Plano:
  1. Criar endpoint /api/dashboard/snapshot que junta kpi + stations +
     orders + alerts numa única resposta JSON
  2. Adicionar If-None-Match com ETag baseado no timestamp do último evento
  3. O frontend chama /api/dashboard/snapshot e /api/agents/status apenas
  4. Sustentabilidade, equipa, conexões — só carregam quando se abre a vista

Cuidados:
  • Não quebrar o tween dos números (frontend espera shape igual)
  • Manter os endpoints individuais para retrocompatibilidade
  • Testar com browser_test.py — todos os 13 checks têm de passar

Antes de mexer, mostra-me o plano de patches.
```

---

## 5. Mobile responsivo

```
Vou apresentar o dashboard num iPad em modo retrato (768x1024). Hoje
o layout é desktop-only.

Quero:
  1. Breakpoint a 900px: a sidebar nav colapsa para uma top bar
  2. Os 3 KPI cards passam para horizontal scroll em mobile
  3. O twin do homepage mantém-se central, ocupa 60vh
  4. O drawer de detalhe abre fullscreen em mobile (não slide-from-right)
  5. O Assistente flutuante passa a tomar 90vw com cantos quadrados em mobile

Toca apenas em frontend/static/css/planta.css e frontend/templates/dashboard.html.j2.
Não toques no app.js excepto se for inevitável.

Testa com viewport 768x1024 no browser_test e tira screenshot.
```

---

## 6. Deploy para Railway

```
Vou fazer deploy do backend para Railway.

Faz:
  1. Criar railway.json com {builder:"NIXPACKS", startCommand:"python -m backend.app"}
  2. Criar Procfile equivalente como fallback
  3. Adicionar PORT do env (Railway injecta) ao app.py
  4. Verificar que SQLite vai sobreviver a redeploys (montar volume em /data?)
  5. Documentar em docs/DEPLOYMENT.md:
     • variáveis de ambiente (GEMINI_API_KEY, etc)
     • como fazer upload de CSVs em prod (drag-drop UI funciona)
     • como ver logs
  6. Health check em / em vez de /health (Railway default)

Não inventes complexidade: nada de Docker custom se Nixpacks chegar.
```

---

## 7. Audit antes da apresentação (20 Maio)

```
Vai apresentar dia 20 Maio. Faz uma auditoria final:

  1. Corre todos os testes: smoke + browser
  2. Abre o standalone preview num browser e tira screenshots de cada vista
  3. Verifica que cada botão na UI tem uma acção real (zero dead clicks)
  4. Verifica que não há "F", "P", "D", "α", "scipy", "Python puro" em
     lugar nenhum visível ao utilizador
  5. Verifica que tudo está em PT-PT (procura por palavras inglesas no template)
  6. Verifica que o backend arranca em <3 segundos
  7. Faz uma checklist em docs/PRESENTATION_PT.md com os 8 passos da demo
     e cronometra cada um

Reporta:
  • Quantos testes passam
  • Lista de violações encontradas
  • Tempos de cada passo da demo
  • Screenshot da homepage final
```

---

## 8. Adicionar item ao catálogo

```
Quero adicionar 3 novos itens de procurement à HYLINE:

  - SAINT-GOBAIN SGG ECLAZ · vidro de alta performance · €58/m² · 75% reciclado
  - REHAU TOTAL70 · perfil de gama média · €19/m · 50% reciclado
  - ALUPLAST IDEAL 8000 · perfil premium · €27/m · 55% reciclado

Faz só uma edição em config.yaml (secção procurement.catalog) e na de
suppliers se for novo. Reinicia o backend (apaga data/hyline.db para forçar
re-seed) e confirma que aparecem em /api/procurement/catalog.

Não toques em código Python.
```

---

## 9. Quando algo parte

```
Estou a ver um erro [DESCRIÇÃO]. Faz isto na ordem:

  1. Mostra o stack trace completo
  2. Lê o ficheiro mais relevante e mostra-me as 10 linhas à volta do erro
  3. Propõe o fix mais pequeno possível (não refactores)
  4. Aplica o fix
  5. Corre o teste que cobre essa zona
  6. Se passar, faz commit com mensagem "fix: ..."

Nunca apliques try/except apenas para esconder o erro.
```

---

## 10. Ajuda · que prompt usar?

| Quero... | Prompt |
|---|---|
| Começar do zero num repo limpo | §0 + §1 |
| Adicionar feature nova de UI | §2 (adaptar) |
| Adicionar feature de backend | §3 (adaptar) |
| Tornar a app mais rápida | §4 |
| Suportar mobile | §5 |
| Pôr em produção | §6 |
| Preparar a apresentação | §7 |
| Adicionar dados | §8 |
| Debugar um erro | §9 |
