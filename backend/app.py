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
from fastapi import FastAPI, HTTPException, UploadFile, File
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

    # ── Dashboard HTML (renderizado server-side) ────────────────
    @app.get("/", response_class=HTMLResponse)
    def dashboard() -> HTMLResponse:
        tmpl = env.get_template("dashboard.html.j2")
        productive_count = sum(1 for s in c.stations if s.target_m2_per_hour > 0)
        stations_json = json.dumps(
            [s.model_dump() for s in c.stations], ensure_ascii=False, separators=(",", ":"),
        )
        members_json = json.dumps(
            [m.model_dump() for m in c.teams.members], ensure_ascii=False, separators=(",", ":"),
        )
        trends_json = json.dumps(
            [t.model_dump() for t in c.scale.trends_pt], ensure_ascii=False, separators=(",", ":"),
        )
        priorities_json = json.dumps(
            [p.model_dump() for p in c.scale.strategic_priorities], ensure_ascii=False, separators=(",", ":"),
        )
        sustain_json = json.dumps(c.sustainability.model_dump(), ensure_ascii=False, separators=(",", ":"))

        html = tmpl.render(
            app_name=c.app.name,
            app_tagline=c.app.tagline,
            refresh_seconds=c.app.dashboard_refresh_seconds,
            factory=c.factory.model_dump(),
            stations=c.stations,
            stations_json=stations_json,
            productive_count=productive_count,
            fiducials=c.factory.fiducials,
            brand=c.brand.model_dump(),
            roles=c.teams.roles,
            members=c.teams.members,
            members_json=members_json,
            trends_json=trends_json,
            priorities_json=priorities_json,
            sustain_json=sustain_json,
            afi_alpha=c.afi.alpha,
            thresholds=c.thresholds.model_dump(),
            agents=registry().status(),
        )
        return HTMLResponse(html)

    # ── Core API ─────────────────────────────────────────────────
    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "app": c.app.name, "version": c.app.version}

    @app.get("/api/config/factory")
    def factory_layout() -> dict:
        return {"factory": c.factory.model_dump(), "stations": [s.model_dump() for s in c.stations]}

    @app.get("/api/kpi")
    def kpi_headline() -> dict:
        return engine.global_kpis()

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
            {"step": 1, "title": "CSV cai em data/inbox/",     "actor": "Sistema externo / Drag-drop UI"},
            {"step": 2, "title": "Watcher detecta + ingere",   "actor": "backend/data.py"},
            {"step": 3, "title": "SQLite armazena",            "actor": "data/hyline.db"},
            {"step": 4, "title": "Engine recalcula KPIs",      "actor": "backend/engine.py"},
            {"step": 5, "title": "Agentes processam alertas",  "actor": "backend/agents.py"},
            {"step": 6, "title": "API serve para o dashboard", "actor": "backend/app.py"},
            {"step": 7, "title": "UI actualiza ao segundo",    "actor": "frontend/static/js/app.js"},
        ]
        return {"backend_files": backend_files, "csv_files": csv_files, "flow": flow}

    # ── Sustainability ───────────────────────────────────────────
    @app.get("/api/sustainability")
    def sustainability() -> dict:
        s = c.sustainability.model_dump()
        kpi = engine.global_kpis()
        s["m2_today"] = kpi["m2_today"]
        s["carbon_today_kg"] = round(kpi["m2_today"] * s["carbon_per_m2_produced"], 1)
        s["energy_today_kwh"] = round(kpi["m2_today"] * s["energy_kwh_per_m2"], 1)
        return s

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
    uvicorn.run(app, host=c.app.host, port=c.app.port, log_level="info")


if __name__ == "__main__":
    main()
