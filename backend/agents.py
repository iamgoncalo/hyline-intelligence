"""Arquitectura de 4 agentes aplicada à HYLINE.

  1. MONITOR   — zero IA, tick de 60s, recomputa F=(P/D)^α
  2. ALERT     — dispara diagnóstico em alertas críticos (stub · pronto para Claude API)
  3. OPTIMISER — cada 15 min, sugere reatribuições via scipy.optimize
  4. CHATBOT   — responde perguntas em PT-PT (stub com regras)

Sem chamadas IA no hot path (HL-03 do AFI Master). Quando o API key do Claude
estiver disponível, trocar os stubs por chamadas reais em ALERT/CHATBOT/OPTIMISER.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta, timezone

import numpy as np

from .config import cfg
from . import data as dlayer
from .data import connection, record_decision
from .engine import open_alerts, scan_all, station_snapshot

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# Agent 1 · MONITOR (zero IA · tick 60s)
# ═══════════════════════════════════════════════════════════════════

class MonitorAgent:
    """Recalcula F/P/D para todas as estações e dispara scan de alertas.
    Pure Python. Nenhuma chamada a API externa. €0/mês.
    """
    name = "MONITOR"

    def tick(self) -> dict:
        fired = scan_all()
        return {"agent": self.name, "ts": _now_iso(), "fired": fired}


# ═══════════════════════════════════════════════════════════════════
# Agent 2 · ALERT (IA · crítico)
# ═══════════════════════════════════════════════════════════════════

class AlertAgent:
    """Quando há alerta severidade >= 3, gera diagnóstico e ações recomendadas.

    Stub heurístico até termos API key do Claude. Escreve ai_diagnosis e
    ai_actions no registo do alerta.
    """
    name = "ALERT"

    PLAYBOOK = {
        "quality": {
            "diagnosis": "Não-conformidade detectada. Verificar calibração da máquina e materiais de entrada.",
            "actions": [
                "Parar produção na estação e isolar janela afetada",
                "Notificar DQ para inspeção completa",
                "Verificar último setup / ferramenta utilizada",
            ],
        },
        "rework": {
            "diagnosis": "Retrabalho detectado · indica deriva do processo antes desta estação.",
            "actions": [
                "Rastrear causa-raiz nas estações a montante",
                "Validar especificações da encomenda",
                "Registar em RNC para análise DQ",
            ],
        },
        "breakdown": {
            "diagnosis": "Avaria de equipamento · produção bloqueada nesta estação.",
            "actions": [
                "Contactar HST para intervenção imediata",
                "Redirecionar trabalho para estação equivalente",
                "Abrir ordem de manutenção corretiva",
            ],
        },
        "safety": {
            "diagnosis": "Incidente de segurança · paragem obrigatória.",
            "actions": [
                "Evacuar zona e chamar HST",
                "Notificar Director de Produção",
                "Não retomar produção sem autorização HST",
            ],
        },
        "critical_delay": {
            "diagnosis": "Atraso crítico · produção abaixo de 50% do target por período sustentado.",
            "actions": [
                "Avaliar causa (operador? máquina? material?)",
                "Reatribuir recursos de estação com folga",
                "Priorizar em próxima ordem de produção",
            ],
        },
        "delay": {
            "diagnosis": "Desvio moderado vs target. Sem urgência mas requer atenção.",
            "actions": [
                "Verificar cadência atual",
                "Confirmar materiais disponíveis no buffer",
                "Monitorizar próximos 30 min",
            ],
        },
    }

    def process_new_alerts(self) -> int:
        """Anota ai_diagnosis / ai_actions nos alertas ainda sem diagnóstico."""
        processed = 0
        with connection() as conn:
            rows = conn.execute(
                "SELECT id, alert_type FROM alerts "
                "WHERE resolved_ts IS NULL AND ai_diagnosis IS NULL AND severity >= 3"
            ).fetchall()
            for r in rows:
                play = self.PLAYBOOK.get(r["alert_type"])
                if not play: continue
                conn.execute(
                    "UPDATE alerts SET ai_diagnosis=?, ai_actions=? WHERE id=?",
                    (play["diagnosis"], " | ".join(play["actions"]), r["id"]),
                )
                processed += 1
        return processed


# ═══════════════════════════════════════════════════════════════════
# Agent 3 · OPTIMISER (scipy · 15 min)
# ═══════════════════════════════════════════════════════════════════

class OptimiserAgent:
    """Propõe reatribuição de operadores a estações para minimizar F-débito global.

    Usa scipy.optimize.linear_sum_assignment (Hungarian algorithm) para resolver
    o problema de atribuição: N operadores × N estações produtivas.

    Retorna uma LISTA de propostas — não aplica nada automaticamente. Decisões
    aplicadas precisam de confirmação ("Are you sure?") na UI.
    """
    name = "OPTIMISER"

    def propose_reassignments(self) -> list[dict]:
        from scipy.optimize import linear_sum_assignment

        c = cfg()
        snap = station_snapshot()
        productive = [s for s in snap if s["target_m2_per_hour"] > 0]
        if not productive:
            return []

        with connection() as conn:
            ops = [dict(r) for r in conn.execute(
                "SELECT id, name, station_assigned FROM members WHERE role='operador' AND active=1"
            ).fetchall()]

        if not ops:
            return []

        # Matriz de custo: operador i × estação j
        # Custo = (1 - F) · afinidade (operador já estava lá paga -0.1 de bónus)
        n_ops, n_st = len(ops), len(productive)
        size = max(n_ops, n_st)
        cost = np.ones((size, size)) * 10.0  # padding para tornar quadrada

        for i, op in enumerate(ops):
            for j, st in enumerate(productive):
                base = 1.0 - st["afi_F"]  # estações com F baixo precisam de ajuda
                if op["station_assigned"] == st["id"]:
                    base -= 0.15
                cost[i, j] = base

        row_ind, col_ind = linear_sum_assignment(cost)

        proposals = []
        for i, j in zip(row_ind, col_ind):
            if i >= n_ops or j >= n_st: continue
            op = ops[i]
            st = productive[j]
            current = op["station_assigned"]
            if current == st["id"]:
                continue  # já lá está
            proposals.append({
                "operator_id":   op["id"],
                "operator_name": op["name"],
                "from_station":  current,
                "to_station":    st["id"],
                "to_station_name": st["name"],
                "to_station_F":  st["afi_F"],
                "gain_estimate": round(float(cost[i, j]), 3),
                "rationale":     f"Estação com F={st['afi_F']} (mais baixo) beneficia mais do operador",
            })
        return proposals[:5]  # top 5


# ═══════════════════════════════════════════════════════════════════
# Agent 4 · CHATBOT (stub PT-PT · on-demand)
# ═══════════════════════════════════════════════════════════════════

class ChatbotAgent:
    """Responde a perguntas em linguagem natural. Stub com regras.
    Quando chegar API key do Claude: trocar _answer() por chamada à API
    com compress_context injectado.
    """
    name = "CHATBOT"

    def answer(self, question: str) -> dict:
        q = (question or "").lower().strip()
        snap = station_snapshot()
        alerts = open_alerts()

        # Regras simples (linguagem de negócio, sem jargão interno)
        if any(k in q for k in ["desempenho", "performance", "f global", "freedom"]):
            from .engine import global_kpis
            f = global_kpis()['afi_F_global']
            n = len([s for s in snap if s['target_m2_per_hour']>0])
            return {"answer": f"Desempenho global = {f*100:.1f}% · média de {n} estações produtivas.",
                    "sources": ["engine.global_kpis"]}
        if any(k in q for k in ["pior", "crítica", "problema", "vermelha"]):
            reds = [s for s in snap if s["status"] == "red"]
            if not reds:
                return {"answer": "Zero estações em vermelho neste momento.", "sources": []}
            top = min(reds, key=lambda s: s["afi_F"])
            return {"answer": f"A estação mais crítica é **{top['name']}** · desempenho {top['afi_F']*100:.0f}% · eficiência {top['efficiency']*100:.0f}%.",
                    "sources": [top["id"]]}
        if any(k in q for k in ["alerta", "avaria"]):
            if not alerts:
                return {"answer": "Zero alertas abertos.", "sources": []}
            return {"answer": f"{len(alerts)} alertas abertos. Mais urgente: {alerts[0]['message']}",
                    "sources": [f"alert:{alerts[0]['id']}"]}
        if any(k in q for k in ["m² hoje", "m2 hoje", "produzido hoje", "produção hoje"]):
            from .engine import global_kpis
            return {"answer": f"Produção hoje: {global_kpis()['m2_today']:.1f} m².", "sources": ["engine.global_kpis"]}
        return {"answer": "Tenta: 'desempenho global', 'pior estação', 'alertas abertos' ou 'produção hoje'.",
                "sources": []}


# ═══════════════════════════════════════════════════════════════════
# Agent 5 · ASSISTANT (floating panel · ⌘K · intent + actions)
# ═══════════════════════════════════════════════════════════════════

_FACTORY_KNOWLEDGE = """
CONHECIMENTO DA FÁBRICA HYLINE — Esposende, Portugal:

LINHAS DE PRODUÇÃO:
- Série de Correr: janelas deslizantes. Refs: SC-60, SC-70, SC-82.
  Fases: Corte → Mecanização → Pré-montagem → Montagem → Colagem Vidro → Embalamento
- Série de Abrir: janelas de batente. Refs: AB-58, AB-68, AB-78.
  Mesmas 6 fases, linha paralela à Série Correr.
Ala auxiliar: linha de ferro e projectos especiais.

MÉTRICAS-CHAVE:
- Target normal por estação: 2.5–3.5 m²/h
- Desempenho saudável: >75% (Desempenho = eficiência composta)
- Não conformidades aceitáveis: <3% das unidades

FLUXO DE DECISÃO (cadeia de responsabilidade):
- Avaria de equipamento → alerta HST → intervenção ≤30 min
- Não conformidade / qualidade → alerta DQ → registo e análise de causa
- Produção abaixo de target por >15 min → alerta Chefe de Turno → reatribuição
- Qualquer escalada grave → Director de Produção (Filipe Gonçalves)

OPERADORES EM TURNO:
- Linha Correr: Carlos Silva, Ana Ferreira, Rui Martins
- Linha Abrir: João Santos, Marta Costa, Beatriz Cruz
- Turno tarde: Pedro Alves, Sofia Nunes, Miguel Rocha, Inês Lopes

CONTEXTO AMBIENTAL — ESPOSENDE (Maio 2026):
- Temperatura exterior: ~16°C, Humidade: 73%
- Rede eléctrica Portugal: 71% renováveis → ~0.118 kgCO₂/kWh (maio, hidroelétrica alta)
- Verão aproxima-se: prever maior consumo de energia em Junho/Julho

QUANDO TE PERGUNTAM SOBRE PRODUÇÃO: usa SEMPRE as ferramentas primeiro.
NUNCA inventes números. Se não há dados: "Ainda sem dados para este período."
"""

_SYSTEM_PROMPT = """És o assistente da HYLINE Intelligence — uma plataforma de
monitorização de produção de janelas. O teu nome é simplesmente
"Assistente".

PERSONALIDADE
- Fala como um colega inteligente e descontraído, não como um robot.
- Tom: directo, caloroso, sem formalidades excessivas.
- Podes fazer humor leve se a conversa pedir.
- Nunca digas que és o Google, Gemini, ou um modelo de linguagem.
- Se alguém perguntar quem és: "Sou o assistente da HYLINE. Conheço
  esta fábrica melhor do que ninguém."

INTELIGÊNCIA
- Podes falar de qualquer assunto — mas tens contexto único sobre esta
  fábrica, estas encomendas, estes operadores.
- Quando tens dados relevantes, usa as ferramentas PRIMEIRO, depois
  responde. Não inventes números.
- Quando a pergunta é geral (conversa, opinião, curiosidade), responde
  directamente sem chamar ferramentas.
""" + _FACTORY_KNOWLEDGE + """
CONTEXTO (continua a partir daqui):

ACÇÕES
- Se o utilizador quer ver algo → open_view() e menciona que navegaste.
- Se quer encomendar → search_catalog() e mostra as opções.
- Se quer saber o estado → get_station_status() ou global_kpis().
- Nunca navegues sem o utilizador pedir. Não sejas intrusivo.

ESTILO DE RESPOSTA
- Máximo 4 linhas por resposta. Sem listas com asteriscos.
- Usa português europeu natural. Podes usar "é que", "tipo", "pronto"
  quando o registo for informal.
- Se não souberes algo: diz que não sabes, sem drama.
- Nunca mostres IDs técnicos, pesos, ou termos internos do sistema."""


def _clean(text: str) -> str:
    """Remove markdown formatting so chat bubbles render plain text."""
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*',     r'\1', text)
    text = re.sub(r'^\s*[\*\-]\s+', '',   text, flags=re.MULTILINE)
    text = re.sub(r'\n{3,}',        '\n\n', text)
    return text.strip()


class AssistantAgent:
    """Assistente flutuante (⌘K). Dois caminhos:
      1. Gemini 2.5 Flash com function calling (quando GEMINI_API_KEY presente)
      2. Regras locais (fallback sempre disponível)
    Devolve sempre {answer: str, actions: [{kind, target, label}]}.
    """
    name = "ASSISTENTE"

    def answer(self, question: str, conversation_id: str | None = None, context: dict | None = None) -> dict:
        # 1. Create conversation if needed
        if not conversation_id:
            conv = dlayer.conv_create()
            conversation_id = conv["id"]

        # 2. Persist user message
        dlayer.conv_add_message(conversation_id, "user", question)

        # 3. Auto-title on first message
        dlayer.conv_auto_title(conversation_id)

        # 4. Load history (exclude the message just added; take last 20 for context)
        all_msgs = dlayer.conv_messages(conversation_id)
        history_msgs = all_msgs[:-1][-20:]

        # 5. Route to Gemini or rules
        if os.environ.get("GEMINI_API_KEY"):
            usage = dlayer.get_assistant_usage()
            if usage["today"]["calls"] < cfg().ai.daily_cap_calls:
                try:
                    result = self._answer_gemini(question, history_msgs, context)
                except Exception as e:
                    log.warning("Gemini fallback: %s", e)
                    dlayer.log_assistant_call(cfg().ai.gemini_model, 0, 0, 0.0, fallback=True)
                    result = self._answer_rules(question, context)
            else:
                result = self._answer_rules(question, context)
        else:
            result = self._answer_rules(question, context)

        # 6. Strip markdown from rules-path answers (Gemini path already cleaned)
        result["answer"] = _clean(result["answer"])

        # 7. Persist assistant response
        dlayer.conv_add_message(
            conversation_id, "assistant", result["answer"],
            tool_calls=result.get("tool_calls"),
            actions=result.get("actions"),
        )

        return {
            "conversation_id": conversation_id,
            "answer":          result["answer"],
            "actions":         result.get("actions", []),
            "tool_calls":      result.get("tool_calls", []),
        }

    # ── Gemini path ──────────────────────────────────────────────

    def _answer_gemini(self, question: str, history_msgs: list[dict], context: dict | None = None) -> dict:
        import google.genai as genai
        from google.genai import types

        c = cfg()
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        _actions: list[dict] = []
        _tool_calls: list[dict] = []

        # Manual schemas — avoids SDK introspection issues with closures
        S = types.Schema
        T = types.Type
        TOOLS = types.Tool(function_declarations=[
            types.FunctionDeclaration(
                name="open_view",
                description="Navega para uma vista do dashboard. Valores válidos para target: home, alerts, action, scale, procurement, sustain, settings.",
                parameters=S(type=T.OBJECT, properties={"target": S(type=T.STRING, description="Nome da vista")}, required=["target"]),
            ),
            types.FunctionDeclaration(
                name="search_catalog",
                description="Procura itens no catálogo. category pode ser: perfis, vidro, ferragens, consumiveis. min_sustainability entre 0 e 100.",
                parameters=S(type=T.OBJECT, properties={
                    "category": S(type=T.STRING, description="Categoria (opcional)"),
                    "min_sustainability": S(type=T.NUMBER, description="Score mínimo eco 0-100"),
                }),
            ),
            types.FunctionDeclaration(
                name="add_to_cart",
                description="Adiciona um item ao carrinho de procurement pelo catalog_id.",
                parameters=S(type=T.OBJECT, properties={
                    "catalog_id": S(type=T.STRING, description="ID do item ex: CAT-04"),
                    "quantity":   S(type=T.NUMBER, description="Quantidade"),
                }, required=["catalog_id", "quantity"]),
            ),
            types.FunctionDeclaration(
                name="checkout",
                description="Confirma a compra do carrinho. Só chamar quando o utilizador confirmar explicitamente.",
                parameters=S(type=T.OBJECT, properties={"confirmed": S(type=T.BOOLEAN, description="true para confirmar")}, required=["confirmed"]),
            ),
            types.FunctionDeclaration(
                name="get_station_status",
                description="Devolve estado actual de uma estação de produção pelo ID (ex: ST-COR-01).",
                parameters=S(type=T.OBJECT, properties={"station_id": S(type=T.STRING, description="ID da estação")}, required=["station_id"]),
            ),
            types.FunctionDeclaration(
                name="suggest_reassignment",
                description="Devolve propostas de reatribuição de operadores do agente Otimização.",
                parameters=S(type=T.OBJECT, properties={}),
            ),
            types.FunctionDeclaration(
                name="global_kpis",
                description="KPIs globais: m² produzidos hoje, Desempenho global %, alertas abertos.",
                parameters=S(type=T.OBJECT, properties={}),
            ),
            types.FunctionDeclaration(
                name="station_m2_by_hour",
                description="Devolve m² produzidos por hora numa estação nas últimas N horas. Útil para ver tendência de produção.",
                parameters=S(type=T.OBJECT, properties={
                    "station_id": S(type=T.STRING, description="ID da estação ex: ST-COR-01"),
                    "hours": S(type=T.NUMBER, description="Número de horas a analisar (default 8)"),
                }, required=["station_id"]),
            ),
            types.FunctionDeclaration(
                name="worst_station",
                description="Encontra a estação produtiva com pior Desempenho actual. Usa para responder a 'pior estação', 'mais crítica', 'maior problema'.",
                parameters=S(type=T.OBJECT, properties={}),
            ),
        ])

        def _exec(name: str, args: dict) -> dict:
            _tool_calls.append({"name": name, "args": dict(args)})
            if name == "open_view":
                t = str(args.get("target", "home"))
                action = {"kind": "open_view", "target": t, "label": f"Abrir {t}"}
                _actions.append(action)
                log.debug("open_view called → %s (actions so far: %d)", t, len(_actions))
                return {"ok": True, "navigated_to": t, "_action": action}
            if name == "search_catalog":
                items = dlayer.fetch_catalog(
                    category=str(args["category"]) if args.get("category") else None,
                    min_sustainability=int(args.get("min_sustainability", 0)),
                )[:5]
                return {"items": items, "count": len(items)}
            if name == "add_to_cart":
                res = dlayer.cart_add(str(args["catalog_id"]), max(1, int(args.get("quantity", 1))), added_by="gemini")
                return {"ok": True, "cart_id": res.get("cart_id")}
            if name == "checkout":
                if not args.get("confirmed", False):
                    return {"ok": False, "reason": "Precisa de confirmação explícita."}
                return dlayer.cart_checkout(member_id="gemini")
            if name == "get_station_status":
                snap = station_snapshot()
                s = next((x for x in snap if x["id"] == args.get("station_id")), None)
                return s or {"error": "estação não encontrada"}
            if name == "suggest_reassignment":
                return {"proposals": registry().optimiser.propose_reassignments()}
            if name == "global_kpis":
                from .engine import global_kpis as _k
                return _k()
            if name == "station_m2_by_hour":
                from .data import connection
                from .engine import _utcnow, _iso
                import math
                sid = str(args.get("station_id", ""))
                hrs = int(args.get("hours", 8))
                now = _utcnow()
                result_hours, result_m2 = [], []
                for h in range(hrs, 0, -1):
                    ts_start = _iso(now - timedelta(hours=h))
                    ts_end   = _iso(now - timedelta(hours=h-1))
                    with connection() as conn:
                        row = conn.execute(
                            "SELECT COALESCE(SUM(area_m2),0) AS m2 FROM production_events "
                            "WHERE station_id=? AND ts>=? AND ts<? AND status='completed'",
                            (sid, ts_start, ts_end),
                        ).fetchone()
                    result_hours.append(f"{now.hour - h:02d}h")
                    result_m2.append(round(float(row["m2"]), 2))
                return {"station": sid, "hours": result_hours, "m2": result_m2, "total": sum(result_m2)}
            if name == "worst_station":
                snap = station_snapshot()
                productive = [s for s in snap if s["target_m2_per_hour"] > 0 and s["afi_F"] is not None]
                if not productive:
                    return {"error": "sem dados de estações produtivas"}
                worst = min(productive, key=lambda s: s["afi_F"])
                return {
                    "station_id": worst["id"],
                    "name": worst["name"],
                    "desempenho_pct": round(worst["afi_F"] * 100, 1),
                    "status": worst["status"],
                    "m2_per_hour": worst["m2_per_hour"],
                    "target_m2_per_hour": worst["target_m2_per_hour"],
                    "operators": worst.get("operators", []),
                }
            return {"error": f"ferramenta desconhecida: {name}"}

        # Build contents: conversation history + current question
        contents = []
        for m in history_msgs:
            if m["role"] == "user":
                contents.append(types.Content(role="user",  parts=[types.Part(text=m["content"])]))
            elif m["role"] == "assistant":
                contents.append(types.Content(role="model", parts=[types.Part(text=m["content"])]))
        contents.append(types.Content(role="user", parts=[types.Part(text=question)]))
        response = None
        for _ in range(5):
            response = client.models.generate_content(
                model=c.ai.gemini_model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=_SYSTEM_PROMPT,
                    tools=[TOOLS],
                ),
            )
            fn_calls = [p.function_call for p in (response.candidates[0].content.parts or []) if p.function_call]
            if not fn_calls:
                break
            # Feed results back — capture each result and scan for _action
            contents.append(response.candidates[0].content)
            fn_parts = []
            for fc in fn_calls:
                result = _exec(fc.name, dict(fc.args))
                if "_action" in result and result["_action"] not in _actions:
                    _actions.append(result["_action"])
                    log.debug("_action collected from %s: %s", fc.name, result["_action"])
                fn_parts.append(types.Part(function_response=types.FunctionResponse(name=fc.name, response=result)))
            contents.append(types.Content(role="user", parts=fn_parts))

        # Log finish reason for debugging empty responses
        if response:
            for cand in (response.candidates or []):
                reason = getattr(cand, "finish_reason", None)
                log.debug("Gemini finish_reason=%s text_len=%s fn_calls_executed=%d",
                          reason, len(response.text or ""), len(_tool_calls))

        # Cost accounting
        um = response.usage_metadata if response else None
        in_tok  = getattr(um, "prompt_token_count",     0) or 0
        out_tok = getattr(um, "candidates_token_count", 0) or 0
        cost = (in_tok * c.ai.gemini_input_usd_per_m + out_tok * c.ai.gemini_output_usd_per_m) / 1_000_000
        dlayer.log_assistant_call(c.ai.gemini_model, in_tok, out_tok, round(cost, 8))

        raw_answer = (response.text if response else None) or ""
        if not raw_answer:
            # Gemini produced no text — synthesise a minimal acknowledgment
            if _actions:
                t = _actions[0]["target"]
                raw_answer = f"A navegar para {t}."
            elif _tool_calls:
                raw_answer = "Concluído."
            else:
                # Truly empty — fall back to rules so user always gets an answer
                log.warning("Gemini returned empty response for: %s", question[:80])
                return self._answer_rules(question, context)

        return {
            "answer":      _clean(raw_answer),
            "actions":     _actions,
            "tool_calls":  _tool_calls,
        }

    # ── Rules path (always available, zero cost) ─────────────────

    def _answer_rules(self, question: str, context: dict | None = None) -> dict:
        from .data import fetch_catalog
        from .engine import global_kpis

        q = (question or "").lower().strip()

        # Navigation shortcuts — explicit view requests
        _NAV = [
            (["procurement", "catálogo sustent", "catálog"],      "procurement", "Abrir Procurement"),
            (["alertas", "alerta", "avaria"],                      "alerts",      "Ver Alertas"),
            (["ação", "agentes", "otimizador", "reatribu"],        "action",      "Abrir Ação"),
            (["escala", "mercado", "tendência"],                   "scale",       "Ver Escala"),
            (["sustentabilidade"],                                 "sustain",     "Ver Sustentabilidade"),
            (["definições", "definicoes", "parâmetros"],           "settings",    "Ver Definições"),
            (["homepage", "início", "home"],                       "home",        "Ver Homepage"),
        ]
        nav_verbs = ["mostra", "abre", "vai para", "navega", "vai ao", "vai à", "ver o", "quero o", "quero ver"]
        if any(v in q for v in nav_verbs):
            for kws, target, label in _NAV:
                if any(k in q for k in kws):
                    return {
                        "answer":  f"A navegar para {target}.",
                        "actions": [{"kind": "open_view", "target": target, "label": label}],
                    }

        # Procurement
        if any(k in q for k in ["encomendar", "comprar", "fornecedor", "vidro", "perfil", "ferrag", "vedante"]):
            cat_map = {"vidro": "vidro", "perfil": "perfis", "ferrag": "ferragens",
                       "vedante": "consumiveis", "consumiv": "consumiveis"}
            cat = next((v for k, v in cat_map.items() if k in q), None)
            eco_only = any(k in q for k in ["sustent", "eco", "verde", "green"])
            min_sust = 85 if eco_only else 0
            items = fetch_catalog(category=cat, min_sustainability=min_sust)[:3]
            if not items:
                return {"answer": "Sem itens com esses critérios no catálogo.", "actions": []}
            cat_label = cat or "todos os materiais"
            threshold_txt = f" (eco ≥{min_sust})" if min_sust else ""
            lines = "\n".join(
                f"**{i['name']}** · {i['supplier_name']} · score {i['sustainability_score']}/100 · {i['price_eur']}€/{i['unit']}"
                for i in items
            )
            return {
                "answer":  f"Top {len(items)} para {cat_label}{threshold_txt}:\n{lines}",
                "actions": [{"kind": "open_view", "target": "procurement", "label": "Abrir Procurement"}],
            }

        # Sustainability
        if any(k in q for k in ["co2", "co₂", "emissões", "carbono", "energia", "sustentab"]):
            kpi = global_kpis()
            s = cfg().sustainability
            co2    = round(kpi["m2_today"] * s.carbon_per_m2_produced, 1)
            energy = round(kpi["m2_today"] * s.energy_kwh_per_m2, 1)
            return {
                "answer":  f"CO₂ hoje: **{co2:,.0f} kg CO₂e**. Energia: **{energy:,.0f} kWh**. Base: {kpi['m2_today']:.1f} m² produzidos.",
                "actions": [{"kind": "open_view", "target": "sustain", "label": "Ver Sustentabilidade"}],
            }

        # Optimiser / reassignment
        if any(k in q for k in ["reatribuir", "reatrib", "optimizar", "otimizar", "operador"]):
            snap = station_snapshot()
            reds = [s for s in snap if s["status"] == "red"]
            return {
                "answer":  f"Há **{len(reds)} estações em vermelho**. O Otimizador tem propostas de reatribuição prontas.",
                "actions": [{"kind": "open_view", "target": "action", "label": "Abrir Ação"}],
            }

        # Alerts
        if any(k in q for k in ["alerta", "avaria"]):
            alerts = open_alerts()
            if not alerts:
                return {"answer": "Zero alertas abertos — sistema estável.", "actions": []}
            return {
                "answer":  f"**{len(alerts)} alertas abertos.** Mais urgente: {alerts[0]['message']}",
                "actions": [{"kind": "open_view", "target": "alerts", "label": "Ver Alertas"}],
            }

        # Critical / worst station
        if any(k in q for k in ["pior", "crítica", "vermelha", "problema"]):
            snap = station_snapshot()
            reds = [s for s in snap if s["status"] == "red"]
            if not reds:
                return {"answer": "Zero estações em vermelho neste momento.", "actions": []}
            top = min(reds, key=lambda s: s["afi_F"])
            return {
                "answer":  f"A estação mais crítica é **{top['name']}** · Desempenho {top['afi_F']*100:.0f}% · eficiência {top['efficiency']*100:.0f}%.",
                "actions": [],
            }

        # KPIs / global performance
        if any(k in q for k in ["desempenho", "f global", "performance", "produção", "m²"]):
            kpi = global_kpis()
            snap = station_snapshot()
            n = len([s for s in snap if s["target_m2_per_hour"] > 0])
            return {
                "answer":  f"Desempenho global: **{kpi['afi_F_global']*100:.1f}%** · {n} estações produtivas. Produção hoje: **{kpi['m2_today']:.1f} m²**.",
                "actions": [],
            }

        # Default
        return {
            "answer":  "Experimenta: 'encomendar vidro sustentável', 'emissões CO₂ hoje', 'reatribuir operadores', 'alertas abertos' ou 'desempenho global'.",
            "actions": [],
        }


# ═══════════════════════════════════════════════════════════════════
# Registry · coordena os 4 agentes
# ═══════════════════════════════════════════════════════════════════

class AgentRegistry:
    def __init__(self):
        self.monitor   = MonitorAgent()
        self.alert     = AlertAgent()
        self.optimiser = OptimiserAgent()
        self.chatbot   = ChatbotAgent()
        self.assistant = AssistantAgent()

    def tick(self) -> dict:
        """Chamado pelo periodic_tick. MONITOR primeiro, depois ALERT processa."""
        r_mon = self.monitor.tick()
        r_ale = self.alert.process_new_alerts()
        return {**r_mon, "alert_processed": r_ale}

    def status(self) -> list[dict]:
        return [
            {"name": "Monitorização", "role": "Lê toda a fábrica em tempo real",            "ai": False, "cost_month_eur": 0.00},
            {"name": "Diagnóstico",   "role": "Identifica causas-raiz quando há desvios",    "ai": True,  "cost_month_eur": 0.36},
            {"name": "Otimização",    "role": "Sugere a melhor atribuição de pessoas",       "ai": True,  "cost_month_eur": 0.18},
            {"name": "Assistente",    "role": "Responde a perguntas em linguagem natural",   "ai": True,  "cost_month_eur": 4.88},
        ]


# Singleton
_REG: AgentRegistry | None = None
def registry() -> AgentRegistry:
    global _REG
    if _REG is None:
        _REG = AgentRegistry()
    return _REG


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
