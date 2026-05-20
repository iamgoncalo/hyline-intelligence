"""FastAPI app + Jinja2 render + bootstrap.

Endpoints:
    GET  /                            Dashboard (Jinja2 renderiza todo o HTML)
    GET  /api/kpi                     Métricas globais
    GET  /api/stations                Snapshot estações com AFI F/P/D
    GET  /api/orders                  Encomendas activas com progresso
    GET  /api/alerts                  Alertas abertos
    POST /api/alerts/{id}/resolve     Marcar resolvido (Are-you-sure na UI)
    POST /api/decisions               Registar decisão (Are-you-sure confirmed)
    GET  /api/production/hourly       m²/hora hoje por sector
    GET  /api/agents/status           Estado dos 4 agentes
    GET  /api/agents/optimiser        Propostas de reatribuição
    POST /api/agents/chatbot          Resposta do chatbot (pergunta em PT-PT)
    GET  /api/scale/trends            Google Trends (dados do config)
    GET  /api/scale/priorities        Prioridades estratégicas
    GET  /api/sustainability          KPIs de sustentabilidade
    GET  /api/team                    Equipa (membros + roles)
    GET  /api/decisions               Histórico de decisões
    GET  /api/connections             Status das connections (Primavera/Preference)
    POST /api/connections/upload      Upload CSV directo para inbox
    GET  /api/config/factory          Layout do chão de fábrica
    GET  /api/health                  Healthcheck
    GET  /static/...                  CSS, JS, SVG
"""
from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
import asyncio
import math
import random
import time
from fastapi import FastAPI, HTTPException, UploadFile, File, WebSocket, WebSocketDisconnect, Request, Response, Form
from fastapi.responses import RedirectResponse
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel

from . import data as dlayer
from . import engine
from .agents import registry
from .config import cfg

logging.basicConfig(level=logging.INFO, format="%(asctime)s · %(levelname)s · %(name)s · %(message)s")
log = logging.getLogger("hyline")


def _line_count(path: str) -> int:
    try:
        return sum(1 for _ in open(path, "r", encoding="utf-8"))
    except Exception:
        return 0


# ═══════════════════════════════════════════════════════════════════
# Pydantic request bodies
# ═══════════════════════════════════════════════════════════════════

class ResolveAlertBody(BaseModel):
    note: str = ""
    resolved_by: str | None = None
    confirmed: bool = False


class DecisionBody(BaseModel):
    member_id: str | None = None
    kind: str
    target: str | None = None
    payload: dict | str
    confirmed: bool


class ChatBody(BaseModel):
    question: str


class CartAddBody(BaseModel):
    catalog_id: str
    quantity: int = 1


class CheckoutBody(BaseModel):
    confirmed: bool


class AssistantBody(BaseModel):
    question: str
    conversation_id: str | None = None


class ConvRenameBody(BaseModel):
    title: str


class AlertTransferBody(BaseModel):
    to_role: str


class LogisticsQuoteBody(BaseModel):
    partner_id: str
    order_ids: list[str]
    destination_country: str


def build_live_payload() -> dict:
    """Build second-by-second live data. All base values from cfg().ws_live — zero hardcodes."""
    t = time.time()
    wsl = cfg().ws_live
    temp      = wsl.interior_base_temp_c       + 0.3 * math.sin(t / 120)       + random.gauss(0, 0.05)
    humidity  = wsl.interior_humidity_base_pct + 2.0 * math.sin(t / 200 + 1.0) + random.gauss(0, 0.3)
    co2       = wsl.interior_co2_base_ppm      + 80  * math.sin(t / 300 + 2.0) + random.gauss(0, 5.0)
    noise_db  = wsl.interior_noise_base_db     + 3.0 * math.sin(t / 45)        + random.gauss(0, 1.0)
    prod_rate = wsl.prod_rate_base_m2_min      + 0.4 * math.sin(t / 600)       + random.gauss(0, 0.02)
    kpis = engine.global_kpis()
    with dlayer.connection() as conn:
        alerts_count = conn.execute(
            "SELECT COUNT(*) FROM alerts WHERE resolved_ts IS NULL"
        ).fetchone()[0]
    return {
        "ts":               round(t, 3),
        "temp_c":           round(temp, 1),
        "humidity_pct":     round(humidity, 1),
        "co2_ppm":          int(round(co2)),
        "noise_db":         round(noise_db, 1),
        "prod_rate_m2_min": round(prod_rate, 3),
        "m2_today":         round(kpis["m2_today"], 1),
        "afi_f_global":     round(kpis.get("afi_F_global", 0), 3),
        "alerts_open":      alerts_count,
    }


import hashlib as _hashlib
import os as _os

_SESSION_SECRET = _os.environ.get("SESSION_SECRET", "hyline-demo-2026")


def _make_token(user_id: str) -> str:
    return _hashlib.sha256(f"{user_id}:{_SESSION_SECRET}".encode()).hexdigest()[:32]


def _check_session(request: Request) -> dict | None:
    """Returns user dict from cfg() if valid session, None otherwise."""
    token   = request.cookies.get("hyline_session")
    user_id = request.cookies.get("hyline_user")
    if not token or not user_id:
        return None
    if token != _make_token(user_id):
        return None
    return next((u for u in cfg().users if u.id == user_id), None)


# ═══════════════════════════════════════════════════════════════════
# App factory
# ═══════════════════════════════════════════════════════════════════

def create_app() -> FastAPI:
    c = cfg()
    app = FastAPI(title=c.app.name, version=c.app.version)

    frontend = Path(c.paths.frontend)
    templates_dir = frontend / "templates"
    static_dir = frontend / "static"

    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(["html", "html.j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    # ── Page routes (multi-page v3 architecture) ──────────────────

    # ── Auth routes ───────────────────────────────────────────────
    @app.get("/login", response_class=HTMLResponse)
    def login_get(request: Request):
        if _check_session(request):
            return RedirectResponse("/", status_code=302)
        tmpl = env.get_template("pages/login.html")
        error = request.query_params.get("error", "")
        return HTMLResponse(tmpl.render(app_name=c.app.name, error=error))

    @app.post("/login", response_class=HTMLResponse)
    async def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
        user = next((u for u in c.users if u.id == username and u.password == password), None)
        if not user:
            return RedirectResponse("/login?error=1", status_code=302)
        response = RedirectResponse("/", status_code=302)
        token = _make_token(user.id)
        response.set_cookie("hyline_session", token, httponly=True, samesite="lax")
        response.set_cookie("hyline_user",    user.id, httponly=True, samesite="lax")
        response.set_cookie("hyline_name",    user.name, httponly=False, samesite="lax")
        response.set_cookie("hyline_role",    user.role, httponly=False, samesite="lax")
        response.set_cookie("hyline_avatar",  user.avatar, httponly=False, samesite="lax")
        return response

    @app.get("/logout")
    def logout():
        response = RedirectResponse("/login", status_code=302)
        response.delete_cookie("hyline_session")
        response.delete_cookie("hyline_user")
        response.delete_cookie("hyline_name")
        response.delete_cookie("hyline_role")
        response.delete_cookie("hyline_avatar")
        return response

    def _page(name: str, active: str, **ctx) -> HTMLResponse:
        tmpl = env.get_template(f"pages/{name}.html")
        return HTMLResponse(tmpl.render(active=active, app_name=c.app.name, **ctx))

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        user = _check_session(request)
        if not user:
            return RedirectResponse("/login", status_code=302)
        factory_json  = json.dumps(c.factory.model_dump(), ensure_ascii=False, separators=(",", ":"))
        stations_json = json.dumps([s.model_dump() for s in c.stations], ensure_ascii=False, separators=(",", ":"))
        members_json  = json.dumps([m.model_dump() for m in c.teams.members], ensure_ascii=False, separators=(",", ":"))
        return _page("home", "home",
                     factory_json=factory_json,
                     stations_json=stations_json,
                     members_json=members_json)

    @app.get("/alertas", response_class=HTMLResponse)
    def alertas_page(request: Request):
        if not _check_session(request): return RedirectResponse("/login", status_code=302)
        return _page("alertas", "alertas")

    @app.get("/acao", response_class=HTMLResponse)
    def acao_page(request: Request):
        if not _check_session(request): return RedirectResponse("/login", status_code=302)
        return _page("acao", "acao")

    @app.get("/escala", response_class=HTMLResponse)
    def escala_page(request: Request):
        if not _check_session(request): return RedirectResponse("/login", status_code=302)
        return _page("escala", "escala")

    @app.get("/procurement", response_class=HTMLResponse)
    def procurement_page(request: Request):
        if not _check_session(request): return RedirectResponse("/login", status_code=302)
        return _page("procurement", "procurement")

    @app.get("/sustentabilidade", response_class=HTMLResponse)
    def sustentabilidade_page(request: Request):
        if not _check_session(request): return RedirectResponse("/login", status_code=302)
        return _page("sustentabilidade", "sustentabilidade")

    @app.get("/logistica", response_class=HTMLResponse)
    def logistica_page(request: Request):
        if not _check_session(request): return RedirectResponse("/login", status_code=302)
        return _page("logistica", "logistica")

    @app.get("/definicoes", response_class=HTMLResponse)
    def definicoes_page(request: Request):
        if not _check_session(request): return RedirectResponse("/login", status_code=302)
        return _page("definicoes", "definicoes")

    @app.get("/conversas", response_class=HTMLResponse)
    def conversas_page(request: Request):
        if not _check_session(request): return RedirectResponse("/login", status_code=302)
        return _page("conversas", "conversas")

    # ── WebSocket live feed (1s sinusoidal oscillations) ──────────
    connected_ws: set = set()

    @app.websocket("/ws/live")
    async def live_feed(ws: WebSocket):
        await ws.accept()
        connected_ws.add(ws)
        try:
            while True:
                await asyncio.sleep(1)
                try:
                    payload = build_live_payload()
                except Exception as exc:
                    log.warning("WS payload error: %s", exc)
                    continue
                dead = []
                for client in list(connected_ws):
                    try:
                        await client.send_text(json.dumps(payload))
                    except Exception:
                        dead.append(client)
                for client in dead:
                    connected_ws.discard(client)
        except (WebSocketDisconnect, Exception):
            connected_ws.discard(ws)

    # ── Core API ─────────────────────────────────────────────────
    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "app": c.app.name, "version": c.app.version}

    @app.get("/api/config/factory")
    def factory_layout() -> dict:
        return {"factory": c.factory.model_dump(), "stations": [s.model_dump() for s in c.stations]}

    @app.get("/api/kpi")
    def kpi_headline() -> dict:
        kpis = engine.global_kpis()
        m2_today = kpis["m2_today"]
        # Extended HYLINE KPIs — order value from m² × avg_price_per_m2
        with dlayer.connection() as conn:
            active_orders = conn.execute(
                "SELECT total_m2 FROM orders WHERE status IN ('active','in_progress','open')"
            ).fetchall()
            nc_count = conn.execute(
                "SELECT COUNT(*) FROM production_events WHERE status IN ('defect','rework') "
                "AND DATE(ts)=DATE('now')"
            ).fetchone()[0]
            total_events_today = conn.execute(
                "SELECT COUNT(*) FROM production_events WHERE DATE(ts)=DATE('now')"
            ).fetchone()[0]
            m2_week = conn.execute(
                "SELECT COALESCE(SUM(area_m2),0) FROM production_events "
                "WHERE status='completed' AND ts>=DATETIME('now','-7 days')"
            ).fetchone()[0]
            m2_month = conn.execute(
                "SELECT COALESCE(SUM(area_m2),0) FROM production_events "
                "WHERE status='completed' AND ts>=DATETIME('now','-30 days')"
            ).fetchone()[0]
            ops_active = conn.execute(
                "SELECT COUNT(DISTINCT operator_id) FROM production_events "
                "WHERE ts>=DATETIME('now','-1 hour')"
            ).fetchone()[0]
        total_m2_orders = sum(float(r[0] or 0) for r in active_orders)
        orders_value_eur = round(total_m2_orders * cfg().products.avg_price_per_m2_eur)
        n_orders = len(active_orders)
        nc_pct = round(100 * nc_count / max(total_events_today, 1), 2)
        return {
            "m2_today":           round(m2_today, 1),
            "m2_week":            round(float(m2_week), 1),
            "m2_month":           round(float(m2_month), 1),
            "performance_pct":    round(kpis.get("afi_F_global", 0) * 100, 1),
            "orders_active":      n_orders,
            "orders_value_eur":   orders_value_eur,
            "orders_export_pct":  round(cfg().markets.export_pct * 100, 1),
            "avg_order_value_eur": round(orders_value_eur / max(n_orders, 1)),
            "top_product_line":   "HYLINE Classic",
            "top_export_country": cfg().markets.top_export_country,
            "non_conformity_pct": nc_pct,
            "alerts_open":        kpis["open_alerts"],
            "operators_active":   ops_active,
            # backward compat
            "afi_F_global":       kpis.get("afi_F_global", 0),
            "open_alerts":        kpis["open_alerts"],
            "open_orders":        n_orders,
            "m2_backlog":         kpis.get("m2_backlog", 0),
        }

    @app.get("/api/stations")
    def stations() -> list[dict]:
        # Merge snapshot live + metadata de config
        snap = {s["id"]: s for s in engine.station_snapshot()}
        out = []
        for sc in c.stations:
            base = sc.model_dump()
            live = snap.get(sc.id, {})
            merged = {**base, **live}
            if sc.target_m2_per_hour == 0:
                merged["status"] = "idle"
                merged.setdefault("efficiency", 0)
                merged.setdefault("m2_per_hour", 0)
                merged.setdefault("m2_today", 0)
            out.append(merged)
        return out

    @app.get("/api/orders")
    def orders(limit: int = 20) -> list[dict]:
        return dlayer.fetch_orders(limit=limit)

    @app.get("/api/alerts")
    def alerts_list(limit: int = 50) -> list[dict]:
        return engine.open_alerts(limit=limit)

    @app.post("/api/alerts/{alert_id}/resolve")
    def alert_resolve(alert_id: int, body: ResolveAlertBody) -> dict:
        if not body.confirmed:
            raise HTTPException(400, "Decisão não confirmada · are-you-sure é obrigatório")
        engine.resolve_alert(alert_id, note=body.note, resolved_by=body.resolved_by)
        dlayer.record_decision(
            member_id=body.resolved_by, kind="resolve_alert",
            target=str(alert_id),
            payload=json.dumps({"note": body.note}, ensure_ascii=False),
        )
        return {"ok": True, "id": alert_id}

    @app.patch("/api/alerts/{alert_id}/transfer")
    def alert_transfer(alert_id: int, body: AlertTransferBody) -> dict:
        to_role = body.to_role
        valid_roles = {"HST", "DQ", "Director", "ChefeTurno"}
        if to_role not in valid_roles:
            raise HTTPException(400, f"Role inválido. Opções: {valid_roles}")
        with dlayer.connection() as conn:
            existing = conn.execute(
                "SELECT a.id, s.name AS station_name FROM alerts a JOIN stations s ON s.id=a.station_id WHERE a.id=?",
                (alert_id,),
            ).fetchone()
            if not existing:
                raise HTTPException(404, "Alerta não encontrado")
            conn.execute("UPDATE alerts SET routed_to=? WHERE id=?", (to_role, alert_id))
        dlayer.record_decision(
            member_id="U01", kind="transfer_alert",
            target=str(alert_id),
            payload=json.dumps({"to_role": to_role}, ensure_ascii=False),
        )
        return {"ok": True, "alert_id": alert_id, "to_role": to_role}

    @app.get("/api/production/hourly")
    def production_hourly() -> list[dict]:
        return engine.hourly_production_today()

    # ── Agentes ──────────────────────────────────────────────────
    @app.get("/api/agents/status")
    def agents_status() -> list[dict]:
        return registry().status()

    @app.get("/api/agents/optimiser")
    def agents_optimiser() -> list[dict]:
        return registry().optimiser.propose_reassignments()

    @app.post("/api/agents/chatbot")
    def agents_chatbot(body: ChatBody) -> dict:
        return registry().chatbot.answer(body.question)

    # ── Decisions (Are-you-sure audit trail) ─────────────────────
    @app.post("/api/decisions")
    def post_decision(body: DecisionBody) -> dict:
        if not body.confirmed:
            raise HTTPException(400, "Decisão não confirmada · are-you-sure é obrigatório")
        payload = body.payload if isinstance(body.payload, str) else json.dumps(body.payload, ensure_ascii=False)
        did = dlayer.record_decision(body.member_id, body.kind, body.target, payload)
        return {"ok": True, "id": did}

    @app.get("/api/decisions")
    def get_decisions(limit: int = 20) -> list[dict]:
        return dlayer.recent_decisions(limit=limit)

    # ── Team ─────────────────────────────────────────────────────
    @app.get("/api/team")
    def team() -> dict:
        return {
            "roles":   [r.model_dump() for r in c.teams.roles],
            "members": dlayer.fetch_members(),
        }

    # ── Scale ────────────────────────────────────────────────────
    @app.get("/api/scale/trends")
    def scale_trends() -> dict:
        return engine.trends_with_suggestions()

    @app.get("/api/scale/priorities")
    def scale_priorities() -> list[dict]:
        return [p.model_dump() for p in c.scale.strategic_priorities]

    @app.get("/api/architecture")
    def architecture() -> dict:
        """Mostra como tudo se interliga: ficheiros backend + endpoints + vistas."""
        backend_files = [
            {"file": "backend/config.py", "lines": _line_count("backend/config.py"),
             "role": "Carrega config.yaml · valida tudo · única fonte de verdade"},
            {"file": "backend/data.py", "lines": _line_count("backend/data.py"),
             "role": "SQLite + ingestão Preference/Primavera + watcher do data/inbox"},
            {"file": "backend/engine.py", "lines": _line_count("backend/engine.py"),
             "role": "Cálculo de desempenho + KPIs + alertas + Google Trends"},
            {"file": "backend/agents.py", "lines": _line_count("backend/agents.py"),
             "role": "4 agentes: monitorização · diagnóstico · otimização · assistente"},
            {"file": "backend/app.py", "lines": _line_count("backend/app.py"),
             "role": "FastAPI · serve dashboard + 18 endpoints + WebSocket-ready"},
        ]
        csv_files = [
            {"name": "preference_*.csv", "purpose": "Eventos chão de fábrica (todas as janelas, fases, status)",
             "columns": list(c.csv_schema.preference.values()),
             "produced_by": "Sistema Preference (linha de produção)"},
            {"name": "primavera_*.csv", "purpose": "Encomendas e clientes (ERP)",
             "columns": list(c.csv_schema.primavera.values()),
             "produced_by": "ERP Primavera"},
        ]
        flow = [
            {"step": 1, "title": "CSV cai em data/inbox/",     "actor": "Primavera ERP / Preference"},
            {"step": 2, "title": "Watcher detecta + ingere",   "actor": "backend/data.py"},
            {"step": 3, "title": "SQLite armazena",            "actor": "data/hyline.db"},
            {"step": 4, "title": "Engine recalcula KPIs",      "actor": "backend/engine.py"},
            {"step": 5, "title": "Agentes processam alertas",  "actor": "backend/agents.py"},
            {"step": 6, "title": "Gemini responde perguntas",  "actor": "Gemini 2.5 Flash · API"},
            {"step": 7, "title": "API serve para o dashboard", "actor": "backend/app.py · FastAPI"},
            {"step": 8, "title": "UI actualiza ao segundo",    "actor": "frontend/js/app.js"},
            {"step": 9, "title": "Deploy em Railway",          "actor": "railway.app · auto-deploy"},
        ]
        return {"backend_files": backend_files, "csv_files": csv_files, "flow": flow}

    # ── Environment · Esposende / Minho ──────────────────────────
    @app.get("/api/environment")
    def environment() -> dict:
        return engine.get_environmental_context()

    # ── Live events feed (for homepage right column) ──────────────
    @app.get("/api/events")
    def events_feed(limit: int = 20) -> list[dict]:
        with dlayer.connection() as conn:
            rows = conn.execute(
                "SELECT e.ts, s.name AS station_name, e.status, e.area_m2, "
                "e.operator_id, e.order_id "
                "FROM production_events e JOIN stations s ON s.id=e.station_id "
                "ORDER BY e.ts DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Import endpoints (Mission 8) ──────────────────────────────
    @app.post("/api/import/orders")
    async def import_orders(file: UploadFile = File(...)) -> dict:
        if not (file.filename or "").lower().endswith(".csv"):
            raise HTTPException(400, "Só ficheiros CSV são aceites.")
        inbox = Path(c.paths.inbox); inbox.mkdir(parents=True, exist_ok=True)
        dest = inbox / "primavera_orders.csv"
        with dest.open("wb") as out:
            shutil.copyfileobj(file.file, out)
        try:
            res = dlayer.ingest_file(dest)
        except Exception as e:
            raise HTTPException(422, f"Falhou ingestão: {e}")
        return {"ok": True, "records": res.get("rows", 0)}

    @app.post("/api/import/events")
    async def import_events(file: UploadFile = File(...)) -> dict:
        if not (file.filename or "").lower().endswith(".csv"):
            raise HTTPException(400, "Só ficheiros CSV são aceites.")
        inbox = Path(c.paths.inbox); inbox.mkdir(parents=True, exist_ok=True)
        dest = inbox / "preference_events.csv"
        with dest.open("wb") as out:
            shutil.copyfileobj(file.file, out)
        try:
            res = dlayer.ingest_file(dest)
        except Exception as e:
            raise HTTPException(422, f"Falhou ingestão: {e}")
        return {"ok": True, "records": res.get("rows", 0)}

    # ── Sustainability ───────────────────────────────────────────
    @app.get("/api/sustainability")
    def sustainability() -> dict:
        s = c.sustainability.model_dump()
        kpi = engine.global_kpis()
        s["m2_today"] = kpi["m2_today"]
        s["carbon_today_kg"] = round(kpi["m2_today"] * s["carbon_per_m2_produced"], 1)
        s["energy_today_kwh"] = round(kpi["m2_today"] * s["energy_kwh_per_m2"], 1)
        return s

    # ── Google Sheets CSV exports ─────────────────────────────────
    @app.get("/api/export/sheets/{dataset}")
    def export_sheets(dataset: str):
        import csv, io
        from fastapi.responses import StreamingResponse
        valid = {"orders", "events", "kpis"}
        if dataset not in valid:
            raise HTTPException(404, f"Dataset deve ser um de: {valid}")
        buf = io.StringIO()
        writer = csv.writer(buf)
        with dlayer.connection() as conn:
            if dataset == "orders":
                rows = conn.execute(
                    "SELECT id,customer,total_windows,total_m2,m2_completed,deadline,priority,status "
                    "FROM orders ORDER BY priority,deadline"
                ).fetchall()
                writer.writerow(["order_id","cliente","pecas","m2_total","m2_concluido","prazo","prioridade","estado"])
            elif dataset == "events":
                rows = conn.execute(
                    "SELECT ts,station_id,window_id,order_id,width_mm,height_mm,area_m2,phase,status,operator_id "
                    "FROM production_events ORDER BY ts DESC LIMIT 10000"
                ).fetchall()
                writer.writerow(["timestamp","estacao","janela","encomenda","largura_mm","altura_mm","area_m2","fase","estado","operador"])
            elif dataset == "kpis":
                rows = conn.execute(
                    "SELECT DATE(ts) AS dia, SUM(area_m2) AS m2, COUNT(*) AS pecas, "
                    "SUM(CASE WHEN status IN('defect','rework') THEN 1 ELSE 0 END) AS nc "
                    "FROM production_events WHERE ts>=DATETIME('now','-30 days') GROUP BY dia ORDER BY dia"
                ).fetchall()
                writer.writerow(["data","m2_produzidos","pecas_produzidas","nao_conformidades"])
        for r in rows:
            writer.writerow(list(r))
        buf.seek(0)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        fname = f"hyline_{dataset}_{ts}.csv"
        return StreamingResponse(
            iter(["﻿" + buf.getvalue()]),  # BOM for Excel/Sheets UTF-8
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{fname}"', "Cache-Control": "no-store"},
        )

    # ── CSV Export · pure Python stdlib ──────────────────────────
    @app.get("/api/export/{dataset}")
    def export_csv(dataset: str):
        """Exporta dados em CSV. Datasets: events, orders, alerts, stations, team, decisions."""
        import csv
        import io
        from fastapi.responses import StreamingResponse

        datasets = {
            "events":     ("SELECT ts, station_id, window_id, order_id, width_mm, height_mm, area_m2, phase, status, operator_id, source FROM production_events ORDER BY ts DESC LIMIT 10000", "eventos_producao"),
            "orders":     ("SELECT id, customer, total_windows, total_m2, m2_completed, deadline, priority, status FROM orders ORDER BY priority, deadline", "encomendas"),
            "alerts":     ("SELECT a.ts, s.name AS estacao, a.alert_type AS tipo, a.severity AS severidade, a.routed_to AS encaminhado, a.message AS mensagem, a.m2_impact AS m2_impacto, a.resolved_ts FROM alerts a JOIN stations s ON s.id=a.station_id ORDER BY a.ts DESC", "alertas"),
            "stations":   ("SELECT id, name, sector, target_m2_per_hour, kind FROM stations ORDER BY sector, id", "estacoes"),
            "team":       ("SELECT m.id, m.name, r.name AS role, r.level, m.station_assigned FROM members m JOIN roles r ON r.id=m.role ORDER BY r.level DESC, m.name", "equipa"),
            "decisions":  ("SELECT d.ts, m.name AS membro, d.kind AS tipo, d.target AS alvo, d.payload, d.confirmed FROM decisions d LEFT JOIN members m ON m.id=d.member_id ORDER BY d.ts DESC", "decisoes"),
        }
        if dataset not in datasets:
            raise HTTPException(404, f"Dataset desconhecido. Opções: {list(datasets.keys())}")

        query, fname_base = datasets[dataset]
        with dlayer.connection() as conn:
            rows = conn.execute(query).fetchall()

        buf = io.StringIO()
        if rows:
            writer = csv.writer(buf, lineterminator="\n")
            writer.writerow(rows[0].keys())
            for r in rows:
                writer.writerow([r[k] for k in r.keys()])
        buf.seek(0)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        fname = f"hyline_{fname_base}_{ts}.csv"
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{fname}"',
                "Cache-Control": "no-store",
            },
        )

    @app.get("/api/export")
    def list_exports() -> list[dict]:
        """Lista todos os datasets exportáveis com contagens actuais."""
        with dlayer.connection() as conn:
            counts = {
                "events":    conn.execute("SELECT COUNT(*) FROM production_events").fetchone()[0],
                "orders":    conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
                "alerts":    conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0],
                "stations":  conn.execute("SELECT COUNT(*) FROM stations").fetchone()[0],
                "team":      conn.execute("SELECT COUNT(*) FROM members").fetchone()[0],
                "decisions": conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0],
            }
        return [
            {"key": "events",    "label": "Eventos de Produção", "rows": counts["events"],    "desc": "Todas as janelas já processadas · até 10 000 linhas"},
            {"key": "orders",    "label": "Encomendas",          "rows": counts["orders"],    "desc": "Estado e progresso de cada obra"},
            {"key": "alerts",    "label": "Alertas",             "rows": counts["alerts"],    "desc": "Histórico completo de alertas"},
            {"key": "stations",  "label": "Estações",            "rows": counts["stations"],  "desc": "Configuração das 24 estações"},
            {"key": "team",      "label": "Equipa",              "rows": counts["team"],      "desc": "Membros, roles e atribuições"},
            {"key": "decisions", "label": "Audit Trail",         "rows": counts["decisions"], "desc": "Todas as decisões tomadas na plataforma"},
        ]

    # ── Connections · CSV pipeline status ────────────────────────
    @app.get("/api/connections")
    def connections() -> dict:
        inbox = Path(c.paths.inbox); inbox.mkdir(parents=True, exist_ok=True)
        proc  = Path(c.paths.processed); proc.mkdir(parents=True, exist_ok=True)

        pending = sorted([p for p in inbox.glob("*.csv")])
        processed = sorted([p for p in proc.glob("*.csv")], reverse=True)[:15]

        with dlayer.connection() as conn:
            stats = conn.execute(
                "SELECT "
                "(SELECT COUNT(*) FROM production_events) AS events, "
                "(SELECT COUNT(*) FROM orders) AS orders, "
                "(SELECT COUNT(*) FROM alerts) AS alerts_total, "
                "(SELECT MAX(ingested_ts) FROM production_events) AS last_ingest"
            ).fetchone()

        def _info(name: str, is_connected: bool):
            return {
                "source": name,
                "status": "connected" if is_connected else "awaiting",
                "files_pending": len([f for f in pending if f.name.lower().startswith(name)]),
                "files_processed": len([f for f in processed if name in f.name.lower()]),
                "schema": list((c.csv_schema.preference if name=="preference" else c.csv_schema.primavera).values()),
            }

        return {
            "watcher_active": True,
            "inbox_path": str(inbox),
            "processed_path": str(proc),
            "pipelines": [
                _info("preference", stats["events"] > 0),
                _info("primavera",  stats["orders"] > 0),
            ],
            "pending_files": [{"name": f.name, "size_kb": round(f.stat().st_size/1024, 1)} for f in pending],
            "processed_files": [{"name": f.name, "size_kb": round(f.stat().st_size/1024, 1),
                                 "ts": f.stem.split("__")[0] if "__" in f.stem else None}
                                for f in processed],
            "totals": dict(stats),
        }

    @app.post("/api/connections/upload")
    async def connection_upload(file: UploadFile = File(...)) -> dict:
        name = (file.filename or "").lower()
        if not name.endswith(".csv"):
            raise HTTPException(400, "Só CSVs são aceites.")
        if not (name.startswith("preference") or name.startswith("primavera")):
            raise HTTPException(400, "Nome do ficheiro deve começar com 'preference_' ou 'primavera_'.")
        inbox = Path(c.paths.inbox); inbox.mkdir(parents=True, exist_ok=True)
        dest = inbox / file.filename
        with dest.open("wb") as out:
            shutil.copyfileobj(file.file, out)
        # Ingerir imediatamente
        try:
            res = dlayer.ingest_file(dest)
        except Exception as e:  # noqa: BLE001
            log.exception("Upload · ingestão falhou")
            raise HTTPException(422, f"Ficheiro recebido mas falhou ingestão: {e}")
        return {"ok": True, "result": res}

    # ── Procurement ──────────────────────────────────────────────
    @app.get("/api/procurement/catalog")
    def procurement_catalog(category: str | None = None, min_sustainability: int = 0) -> list[dict]:
        return dlayer.fetch_catalog(category=category, min_sustainability=min_sustainability)

    @app.get("/api/procurement/suppliers")
    def procurement_suppliers() -> list[dict]:
        return dlayer.fetch_suppliers()

    @app.get("/api/procurement/cart")
    def procurement_cart() -> list[dict]:
        return dlayer.cart_list()

    @app.post("/api/procurement/cart/add")
    def procurement_cart_add(body: CartAddBody) -> dict:
        import sqlite3
        try:
            return dlayer.cart_add(body.catalog_id, body.quantity)
        except sqlite3.IntegrityError:
            raise HTTPException(422, f"Item '{body.catalog_id}' não existe no catálogo.")

    @app.delete("/api/procurement/cart/{cart_id}")
    def procurement_cart_remove(cart_id: int) -> dict:
        dlayer.cart_remove(cart_id)
        return {"ok": True}

    @app.post("/api/procurement/checkout")
    def procurement_checkout(body: CheckoutBody) -> dict:
        if not body.confirmed:
            raise HTTPException(400, "Decisão não confirmada · are-you-sure é obrigatório")
        return dlayer.cart_checkout()

    @app.get("/api/actions")
    def actions_list(limit: int = 20) -> list[dict]:
        return dlayer.recent_actions(limit=limit)

    # ── Logistics ─────────────────────────────────────────────────
    @app.get("/api/logistics/partners")
    def logistics_partners() -> list[dict]:
        return [p.model_dump() for p in c.logistics.shipping_partners]

    @app.post("/api/logistics/quote")
    def logistics_quote(body: LogisticsQuoteBody) -> dict:
        partner = next((p for p in c.logistics.shipping_partners if p.id == body.partner_id), None)
        if not partner:
            raise HTTPException(404, f"Parceiro '{body.partner_id}' não encontrado")
        base_days = partner.avg_delivery_days + c.logistics.customs_clearance_days
        surcharge = 150 if body.destination_country not in c.markets.primary else 0
        est_eur   = len(body.order_ids) * 320 + surcharge
        import uuid
        quote_ref = f"QT-{datetime.now(timezone.utc).strftime('%Y-%m')}-{str(uuid.uuid4())[:6].upper()}"
        dlayer.record_decision(
            member_id=None, kind="logistics_quote",
            target=body.destination_country,
            payload=json.dumps({
                "partner": body.partner_id, "orders": body.order_ids,
                "est_days": base_days, "est_eur": est_eur, "ref": quote_ref,
            }, ensure_ascii=False),
        )
        return {"estimated_days": base_days, "estimated_eur": est_eur, "quote_ref": quote_ref}

    # ── Assistant (floating panel · richer intents) ───────────
    @app.post("/api/assistant")
    def assistant(body: AssistantBody) -> dict:
        return registry().assistant.answer(body.question, conversation_id=body.conversation_id)

    @app.get("/api/assistant/usage")
    def assistant_usage() -> dict:
        return dlayer.get_assistant_usage()

    # ── Conversations ─────────────────────────────────────────
    @app.get("/api/conversations")
    def conversations_list(limit: int = 50) -> list[dict]:
        return dlayer.conv_list(limit=limit)

    @app.post("/api/conversations")
    def conversations_create() -> dict:
        return dlayer.conv_create()

    @app.get("/api/conversations/{conv_id}")
    def conversations_get(conv_id: str) -> dict:
        conv = dlayer.conv_get(conv_id)
        if conv is None:
            raise HTTPException(404, "Conversa não encontrada")
        conv["messages"] = dlayer.conv_messages(conv_id)
        return conv

    @app.patch("/api/conversations/{conv_id}")
    def conversations_rename(conv_id: str, body: ConvRenameBody) -> dict:
        if not dlayer.conv_get(conv_id):
            raise HTTPException(404, "Conversa não encontrada")
        dlayer.conv_rename(conv_id, body.title.strip() or "Nova conversa")
        return {"ok": True}

    @app.delete("/api/conversations/{conv_id}")
    def conversations_delete(conv_id: str) -> dict:
        if not dlayer.conv_get(conv_id):
            raise HTTPException(404, "Conversa não encontrada")
        dlayer.conv_delete(conv_id)
        return {"ok": True}

    # ── Admin · seed demo data (Railway / fresh deploys) ─────────
    @app.post("/api/admin/seed")
    def admin_seed() -> dict:
        import shutil as _shutil
        import pathlib as _pathlib
        src   = _pathlib.Path("sample_data")
        inbox = _pathlib.Path(c.paths.inbox)
        inbox.mkdir(parents=True, exist_ok=True)
        for f in src.glob("*.csv"):
            _shutil.copy(f, inbox / f.name)
        dlayer.seed_all()
        dlayer.ingest_inbox()
        with dlayer.connection() as conn:
            events = conn.execute("SELECT COUNT(*) FROM production_events").fetchone()[0]
            orders = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        return {"ok": True, "events": events, "orders": orders}

    # ── Static ───────────────────────────────────────────────────
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    return app


def bootstrap() -> None:
    log.info("Bootstrapping HYLINE · %s", cfg().app.version)
    dlayer.init_schema()
    dlayer.seed_all()
    dlayer.start_watcher()
    dlayer.start_periodic_tick(lambda: registry().tick())


# Module-level app (para `python -m backend.app` e uvicorn)
bootstrap()
app = create_app()


def main() -> None:
    c = cfg()
    import os; uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", c.app.port)), log_level="info")


if __name__ == "__main__":
    main()
