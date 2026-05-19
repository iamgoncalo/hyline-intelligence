"""Camada de dados. Consolida:
  • Schema SQLite + ligações
  • Ingestão de CSV via pandas (Preference + Primavera)
  • Watcher filesystem (data/inbox/)
  • Seed de estações, membros de equipa e papéis

Tudo indexado a m². Cada evento de produção tem area_m2 obrigatória
(calculada na ingestão a partir de width_mm × height_mm).
"""
from __future__ import annotations

import json
import logging
import uuid
import shutil
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .config import cfg

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# SCHEMA
# ═══════════════════════════════════════════════════════════════════
SCHEMA = """
CREATE TABLE IF NOT EXISTS stations (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, sector TEXT NOT NULL,
    target_m2_per_hour REAL NOT NULL, kind TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY, customer TEXT,
    total_windows INTEGER NOT NULL, total_m2 REAL NOT NULL,
    deadline TEXT, priority INTEGER, status TEXT,
    m2_completed REAL DEFAULT 0.0
);

-- FONTE ÚNICA DE VERDADE · cada janela tem area_m2 obrigatória
CREATE TABLE IF NOT EXISTS production_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL, station_id TEXT NOT NULL,
    order_id TEXT, window_id TEXT NOT NULL,
    width_mm REAL NOT NULL, height_mm REAL NOT NULL,
    area_m2 REAL NOT NULL,        -- = width × height / 1e6
    phase TEXT NOT NULL, status TEXT NOT NULL,
    operator_id TEXT, source TEXT NOT NULL, ingested_ts TEXT NOT NULL,
    FOREIGN KEY (station_id) REFERENCES stations(id),
    UNIQUE (ts, station_id, window_id, status)
);
CREATE INDEX IF NOT EXISTS idx_events_ts      ON production_events(ts DESC);
CREATE INDEX IF NOT EXISTS idx_events_station ON production_events(station_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_events_order   ON production_events(order_id);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL, station_id TEXT NOT NULL,
    alert_type TEXT NOT NULL, severity INTEGER NOT NULL,
    routed_to TEXT NOT NULL, message TEXT NOT NULL,
    m2_impact REAL DEFAULT 0.0,
    ai_diagnosis TEXT, ai_actions TEXT,
    resolved_ts TEXT, resolution_note TEXT, resolved_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_alerts_ts       ON alerts(ts DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_unsolved ON alerts(resolved_ts) WHERE resolved_ts IS NULL;

CREATE TABLE IF NOT EXISTS roles (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, level INTEGER NOT NULL, color TEXT
);

CREATE TABLE IF NOT EXISTS members (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL,
    station_assigned TEXT, initials TEXT, active INTEGER DEFAULT 1,
    FOREIGN KEY (role) REFERENCES roles(id)
);

-- Decisões tomadas na plataforma (audit trail para "Are you sure?")
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL, member_id TEXT, kind TEXT NOT NULL,
    target TEXT, payload TEXT, confirmed INTEGER DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_decisions_ts ON decisions(ts DESC);

CREATE TABLE IF NOT EXISTS suppliers (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL,
    sustainability_score INTEGER NOT NULL, certifications TEXT,
    delivery_days INTEGER NOT NULL, location TEXT, contact TEXT
);

CREATE TABLE IF NOT EXISTS catalog (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, supplier_id TEXT NOT NULL,
    category TEXT NOT NULL, unit TEXT NOT NULL,
    price_eur REAL NOT NULL, co2_per_unit REAL NOT NULL,
    recycled_pct REAL NOT NULL, sustainability_score INTEGER NOT NULL,
    stock_level INTEGER NOT NULL,
    FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
);

CREATE TABLE IF NOT EXISTS cart (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    catalog_id TEXT NOT NULL, quantity INTEGER NOT NULL DEFAULT 1,
    added_ts TEXT NOT NULL,
    FOREIGN KEY (catalog_id) REFERENCES catalog(id)
);

CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT, confirmed INTEGER DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_actions_ts ON actions(ts DESC);

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT 'Nova conversa',
    created_ts TEXT NOT NULL,
    updated_ts TEXT NOT NULL,
    user_id TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    tool_calls TEXT,
    actions TEXT,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);
CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id, ts);
CREATE INDEX IF NOT EXISTS idx_conv_updated ON conversations(updated_ts DESC);

CREATE TABLE IF NOT EXISTS assistant_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0.0,
    fallback INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_usage_ts ON assistant_usage(ts DESC);
"""


def get_db_path() -> Path:
    p = Path(cfg().paths.db)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


@contextmanager
def connection():
    conn = sqlite3.connect(get_db_path(), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    try:
        yield conn
    finally:
        conn.close()


def init_schema() -> None:
    with connection() as conn:
        conn.executescript(SCHEMA)


def seed_all() -> None:
    """Popula stations, roles, members a partir de config.yaml."""
    c = cfg()
    with connection() as conn:
        # Stations
        for s in c.stations:
            conn.execute(
                "INSERT INTO stations (id, name, sector, target_m2_per_hour, kind) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET name=excluded.name, sector=excluded.sector, "
                "target_m2_per_hour=excluded.target_m2_per_hour, kind=excluded.kind",
                (s.id, s.name, s.sector, s.target_m2_per_hour, s.kind),
            )
        # Roles
        for r in c.teams.roles:
            conn.execute(
                "INSERT INTO roles (id, name, level, color) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET name=excluded.name, level=excluded.level, color=excluded.color",
                (r.id, r.name, r.level, r.color),
            )
        # Members
        for m in c.teams.members:
            conn.execute(
                "INSERT INTO members (id, name, role, station_assigned, initials) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET name=excluded.name, role=excluded.role, "
                "station_assigned=excluded.station_assigned, initials=excluded.initials",
                (m.id, m.name, m.role, m.station_assigned, m.initials),
            )
        # Suppliers
        for s in c.procurement.suppliers:
            conn.execute(
                "INSERT INTO suppliers (id, name, category, sustainability_score, certifications, delivery_days, location, contact) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET name=excluded.name, category=excluded.category, "
                "sustainability_score=excluded.sustainability_score, certifications=excluded.certifications, "
                "delivery_days=excluded.delivery_days, location=excluded.location, contact=excluded.contact",
                (s.id, s.name, s.category, s.sustainability_score, ",".join(s.certifications), s.delivery_days, s.location, s.contact),
            )
        # Catalog
        for item in c.procurement.catalog:
            conn.execute(
                "INSERT INTO catalog (id, name, supplier_id, category, unit, price_eur, co2_per_unit, recycled_pct, sustainability_score, stock_level) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET name=excluded.name, supplier_id=excluded.supplier_id, "
                "category=excluded.category, unit=excluded.unit, price_eur=excluded.price_eur, "
                "co2_per_unit=excluded.co2_per_unit, recycled_pct=excluded.recycled_pct, "
                "sustainability_score=excluded.sustainability_score, stock_level=excluded.stock_level",
                (item.id, item.name, item.supplier_id, item.category, item.unit,
                 item.price_eur, item.co2_per_unit, item.recycled_pct, item.sustainability_score, item.stock_level),
            )


# ═══════════════════════════════════════════════════════════════════
# INGESTÃO CSV · Primavera + Preference → SQLite
# ═══════════════════════════════════════════════════════════════════

def parse_preference(path: Path) -> pd.DataFrame:
    schema = cfg().csv_schema.preference
    df = pd.read_csv(path)
    missing = [c for c in schema.values() if c not in df.columns]
    if missing:
        raise ValueError(f"Preference CSV · colunas em falta: {missing}")
    out = pd.DataFrame({
        "ts":          pd.to_datetime(df[schema["ts_col"]], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "station_id":  df[schema["station_col"]].astype(str),
        "window_id":   df[schema["window_col"]].astype(str),
        "order_id":    df[schema["order_col"]].astype(str),
        "width_mm":    pd.to_numeric(df[schema["width_col"]], errors="coerce"),
        "height_mm":   pd.to_numeric(df[schema["height_col"]], errors="coerce"),
        "phase":       df[schema["phase_col"]].astype(str),
        "status":      df[schema["status_col"]].astype(str),
        "operator_id": df[schema["operator_col"]].astype(str),
    })
    # O m² é calculado UMA vez, aqui, a partir de dimensões puras.
    out["area_m2"] = (out["width_mm"] * out["height_mm"]) / 1_000_000.0
    out = out.dropna(subset=["width_mm", "height_mm", "area_m2"])
    out = out[(out["area_m2"] > 0.01) & (out["area_m2"] < 20.0)]
    out["source"] = "preference"
    out["ingested_ts"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return out


def parse_primavera(path: Path) -> pd.DataFrame:
    schema = cfg().csv_schema.primavera
    df = pd.read_csv(path)
    missing = [c for c in schema.values() if c not in df.columns]
    if missing:
        raise ValueError(f"Primavera CSV · colunas em falta: {missing}")
    out = pd.DataFrame({
        "id":            df[schema["order_col"]].astype(str),
        "customer":      df[schema["customer_col"]].astype(str),
        "total_windows": pd.to_numeric(df[schema["windows_col"]], errors="coerce").astype("Int64"),
        "total_m2":      pd.to_numeric(df[schema["m2_col"]], errors="coerce"),
        "deadline":      df[schema["deadline_col"]].astype(str),
        "priority":      pd.to_numeric(df[schema["priority_col"]], errors="coerce").astype("Int64"),
        "status":        df[schema["status_col"]].astype(str),
    })
    return out.dropna(subset=["id", "total_m2", "total_windows"])


def detect_source(path: Path) -> str | None:
    n = path.name.lower()
    if n.startswith("preference"): return "preference"
    if n.startswith("primavera"):  return "primavera"
    return None


def ingest_file(path: Path) -> dict:
    src = detect_source(path)
    if src is None:
        raise ValueError(f"CSV desconhecido (nome deve começar com preference_ ou primavera_): {path.name}")
    stats = {"file": path.name, "source": src, "rows": 0}
    if src == "preference":
        df = parse_preference(path)
        stats["rows"] = len(df)
        _write_events(df)
    else:
        df = parse_primavera(path)
        stats["rows"] = len(df)
        _write_orders(df)
    # Arquivar
    proc = Path(cfg().paths.processed); proc.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    shutil.move(str(path), str(proc / f"{ts}__{path.name}"))
    log.info("Ingerido %s: %d linhas (%s)", path.name, stats["rows"], src)
    return stats


def _write_events(df: pd.DataFrame) -> None:
    if df.empty: return
    rows = [
        (r["ts"], r["station_id"], r["order_id"], r["window_id"],
         float(r["width_mm"]), float(r["height_mm"]), float(r["area_m2"]),
         r["phase"], r["status"], r["operator_id"], r["source"], r["ingested_ts"])
        for _, r in df.iterrows()
    ]
    with connection() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO production_events "
            "(ts, station_id, order_id, window_id, width_mm, height_mm, area_m2, phase, status, operator_id, source, ingested_ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        # Recalcular m²_completed por encomenda (only completed events)
        conn.execute(
            "UPDATE orders SET m2_completed = COALESCE((SELECT SUM(area_m2) FROM production_events "
            "WHERE order_id = orders.id AND status = 'completed'), 0)"
        )


def _write_orders(df: pd.DataFrame) -> None:
    if df.empty: return
    rows = [
        (r["id"], r["customer"], int(r["total_windows"]), float(r["total_m2"]),
         r["deadline"], int(r["priority"]) if pd.notna(r["priority"]) else None, r["status"])
        for _, r in df.iterrows()
    ]
    with connection() as conn:
        conn.executemany(
            "INSERT INTO orders (id, customer, total_windows, total_m2, deadline, priority, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET customer=excluded.customer, total_windows=excluded.total_windows, "
            "total_m2=excluded.total_m2, deadline=excluded.deadline, priority=excluded.priority, status=excluded.status",
            rows,
        )


def ingest_inbox() -> list[dict]:
    inbox_cfg = Path(cfg().paths.inbox)
    inbox = inbox_cfg if inbox_cfg.is_absolute() else Path.cwd() / inbox_cfg
    inbox.mkdir(parents=True, exist_ok=True)
    results = []
    for f in sorted(inbox.glob("*.csv")):
        try:
            results.append(ingest_file(f))
        except Exception as e:  # noqa: BLE001
            log.exception("Falhou ingestão %s: %s", f.name, e)
            results.append({"file": f.name, "error": str(e)})
    return results


# ═══════════════════════════════════════════════════════════════════
# WATCHER · detecção automática
# ═══════════════════════════════════════════════════════════════════

class _InboxHandler(FileSystemEventHandler):
    def on_created(self, event) -> None:
        if event.is_directory: return
        p = Path(event.src_path)
        if p.suffix.lower() != ".csv": return
        time.sleep(0.5)  # deixar o write terminar
        try:
            ingest_file(p)
        except Exception as e:  # noqa: BLE001
            log.exception("Watcher · falha em %s: %s", p, e)


def start_watcher() -> Observer:
    ingest_inbox()
    inbox = Path(cfg().paths.inbox)
    inbox.mkdir(parents=True, exist_ok=True)
    obs = Observer()
    obs.schedule(_InboxHandler(), str(inbox), recursive=False)
    obs.daemon = True
    obs.start()
    log.info("Watcher ativo em %s", inbox)
    return obs


def start_periodic_tick(tick_fn) -> threading.Thread:
    """Lança uma thread que chama tick_fn a cada refresh_seconds."""
    def _loop():
        interval = cfg().app.refresh_seconds
        while True:
            try:
                tick_fn()
            except Exception as e:  # noqa: BLE001
                log.exception("Tick falhou: %s", e)
            time.sleep(interval)
    t = threading.Thread(target=_loop, daemon=True, name="hyline-tick")
    t.start()
    log.info("Tick ativo (cada %ds)", cfg().app.refresh_seconds)
    return t


# ═══════════════════════════════════════════════════════════════════
# Consultas de conveniência usadas por outras camadas
# ═══════════════════════════════════════════════════════════════════

def fetch_members() -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT m.id, m.name, m.role, m.station_assigned, m.initials, r.name AS role_name, r.level, r.color "
            "FROM members m JOIN roles r ON r.id = m.role WHERE m.active = 1 ORDER BY r.level DESC, m.name"
        ).fetchall()
    return [dict(r) for r in rows]


def fetch_orders(limit: int = 20) -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT id, customer, total_windows, total_m2, m2_completed, deadline, priority, status, "
            "ROUND(100.0 * COALESCE(m2_completed,0) / NULLIF(total_m2,0), 1) AS progress_pct "
            "FROM orders "
            "WHERE status IN ('active','in_progress','open') "
            "ORDER BY priority ASC, deadline ASC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def record_decision(member_id: str | None, kind: str, target: str | None, payload: str) -> int:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with connection() as conn:
        cur = conn.execute(
            "INSERT INTO decisions (ts, member_id, kind, target, payload) VALUES (?, ?, ?, ?, ?)",
            (ts, member_id, kind, target, payload),
        )
        return cur.lastrowid


def recent_decisions(limit: int = 20) -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT d.id, d.ts, d.kind, d.target, d.payload, d.confirmed, m.name AS member_name "
            "FROM decisions d LEFT JOIN members m ON m.id = d.member_id "
            "ORDER BY d.ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════════
# PROCUREMENT · catálogo + carrinho + checkout
# ═══════════════════════════════════════════════════════════════════

def fetch_suppliers() -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT * FROM suppliers ORDER BY sustainability_score DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def fetch_catalog(category: str | None = None, min_sustainability: int = 0) -> list[dict]:
    conds = ["c.sustainability_score >= ?"]
    params: list = [min_sustainability]
    if category:
        conds.append("c.category = ?")
        params.append(category)
    where = " AND ".join(conds)
    with connection() as conn:
        rows = conn.execute(
            f"SELECT c.id, c.name, c.supplier_id, c.category, c.unit, c.price_eur, "
            f"c.co2_per_unit, c.recycled_pct, c.sustainability_score, c.stock_level, "
            f"s.name AS supplier_name, s.certifications, s.delivery_days "
            f"FROM catalog c JOIN suppliers s ON s.id = c.supplier_id "
            f"WHERE {where} ORDER BY c.sustainability_score DESC, c.name",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def cart_add(catalog_id: str, quantity: int = 1, added_by: str | None = None) -> dict:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with connection() as conn:
        existing = conn.execute(
            "SELECT id FROM cart WHERE catalog_id = ?", (catalog_id,)
        ).fetchone()
        if existing:
            conn.execute("UPDATE cart SET quantity = quantity + ? WHERE catalog_id = ?", (quantity, catalog_id))
            return {"cart_id": existing["id"], "updated": True}
        cur = conn.execute(
            "INSERT INTO cart (catalog_id, quantity, added_ts) VALUES (?, ?, ?)",
            (catalog_id, quantity, ts),
        )
        return {"cart_id": cur.lastrowid, "updated": False}


def cart_list() -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT cart.id, cart.catalog_id, cart.quantity, cart.added_ts, "
            "c.name, c.category, c.unit, c.price_eur, c.sustainability_score, "
            "c.co2_per_unit, c.recycled_pct, s.name AS supplier_name "
            "FROM cart "
            "JOIN catalog c ON c.id = cart.catalog_id "
            "JOIN suppliers s ON s.id = c.supplier_id "
            "ORDER BY cart.added_ts"
        ).fetchall()
    items = [dict(r) for r in rows]
    for item in items:
        item["subtotal_eur"] = round(item["price_eur"] * item["quantity"], 2)
    return items


def cart_remove(cart_id: int) -> None:
    with connection() as conn:
        conn.execute("DELETE FROM cart WHERE id = ?", (cart_id,))


def cart_checkout(member_id: str | None = None) -> dict:
    items = cart_list()
    if not items:
        return {"ok": False, "reason": "Carrinho vazio"}
    total_eur = round(sum(i["subtotal_eur"] for i in items), 2)
    eco_score = round(sum(i["sustainability_score"] for i in items) / len(items))
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload_dict: dict = {"items": len(items), "total_eur": total_eur, "eco_score": eco_score}
    if member_id:
        payload_dict["initiated_by"] = member_id
    payload = json.dumps(payload_dict, ensure_ascii=False)
    with connection() as conn:
        cur = conn.execute(
            "INSERT INTO actions (ts, kind, payload, confirmed) VALUES (?, 'procurement_checkout', ?, 1)",
            (ts, payload),
        )
        action_id = cur.lastrowid
        conn.execute("DELETE FROM cart")
    return {"ok": True, "action_id": action_id, "items": len(items), "total_eur": total_eur, "eco_score": eco_score}


def recent_actions(limit: int = 20) -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT * FROM actions ORDER BY ts DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════════
# ASSISTANT USAGE · tracking de custos Gemini
# ═══════════════════════════════════════════════════════════════════

def log_assistant_call(
    model: str, input_tokens: int, output_tokens: int,
    cost_usd: float, fallback: bool = False,
) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with connection() as conn:
        conn.execute(
            "INSERT INTO assistant_usage (ts, model, input_tokens, output_tokens, cost_usd, fallback) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (ts, model, input_tokens, output_tokens, cost_usd, int(fallback)),
        )


# ═══════════════════════════════════════════════════════════════════
# CONVERSATIONS · histórico persistente do assistente
# ═══════════════════════════════════════════════════════════════════

def conv_create(user_id: str | None = None) -> dict:
    conv_id = str(uuid.uuid4())
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with connection() as conn:
        conn.execute(
            "INSERT INTO conversations (id, title, created_ts, updated_ts, user_id) VALUES (?, 'Nova conversa', ?, ?, ?)",
            (conv_id, ts, ts, user_id),
        )
    return {"id": conv_id, "title": "Nova conversa", "created_ts": ts, "updated_ts": ts, "user_id": user_id}


def conv_list(limit: int = 50) -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT c.id, c.title, c.created_ts, c.updated_ts, c.user_id, "
            "COUNT(m.id) AS message_count, "
            "(SELECT m2.content FROM messages m2 WHERE m2.conversation_id=c.id AND m2.role='user' ORDER BY m2.ts LIMIT 1) AS first_user_msg "
            "FROM conversations c LEFT JOIN messages m ON m.conversation_id=c.id "
            "GROUP BY c.id ORDER BY c.updated_ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
    result = []
    for r in rows:
        row = dict(r)
        first = row.pop("first_user_msg") or ""
        row["preview"] = first[:80]
        result.append(row)
    return result


def conv_get(conv_id: str) -> dict | None:
    with connection() as conn:
        r = conn.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)).fetchone()
    return dict(r) if r else None


def conv_messages(conv_id: str) -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY ts", (conv_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def conv_add_message(
    conv_id: str, role: str, content: str,
    tool_calls: list | None = None, actions: list | None = None,
) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with connection() as conn:
        conn.execute(
            "INSERT INTO messages (conversation_id, ts, role, content, tool_calls, actions) VALUES (?, ?, ?, ?, ?, ?)",
            (conv_id, ts, role, content,
             json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None,
             json.dumps(actions, ensure_ascii=False) if actions else None),
        )
        conn.execute("UPDATE conversations SET updated_ts=? WHERE id=?", (ts, conv_id))


def conv_rename(conv_id: str, new_title: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with connection() as conn:
        conn.execute("UPDATE conversations SET title=?, updated_ts=? WHERE id=?", (new_title, ts, conv_id))


def conv_delete(conv_id: str) -> None:
    with connection() as conn:
        conn.execute("DELETE FROM messages WHERE conversation_id=?", (conv_id,))
        conn.execute("DELETE FROM conversations WHERE id=?", (conv_id,))


def conv_auto_title(conv_id: str) -> str:
    with connection() as conn:
        row = conn.execute("SELECT title FROM conversations WHERE id=?", (conv_id,)).fetchone()
        if not row or row["title"] != "Nova conversa":
            return row["title"] if row else ""
        first = conn.execute(
            "SELECT content FROM messages WHERE conversation_id=? AND role='user' ORDER BY ts LIMIT 1",
            (conv_id,),
        ).fetchone()
        if not first:
            return "Nova conversa"
        title = first["content"][:40].strip()
        if len(first["content"]) > 40:
            title += "…"
        conn.execute("UPDATE conversations SET title=? WHERE id=?", (title, conv_id))
    return title


def get_assistant_usage() -> dict:
    import os
    today_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with connection() as conn:
        t = conn.execute(
            "SELECT COUNT(*) AS calls, COALESCE(SUM(input_tokens),0) AS inp, "
            "COALESCE(SUM(output_tokens),0) AS out, COALESCE(SUM(cost_usd),0) AS cost "
            "FROM assistant_usage WHERE ts >= ? AND fallback = 0",
            (today_prefix,),
        ).fetchone()
        w = conn.execute(
            "SELECT COUNT(*) AS calls, COALESCE(SUM(cost_usd),0) AS cost "
            "FROM assistant_usage WHERE ts >= ?",
            (week_ago,),
        ).fetchone()
    return {
        "today": {
            "calls": t["calls"], "input_tokens": t["inp"],
            "output_tokens": t["out"], "cost_usd": round(t["cost"], 6),
        },
        "7d": {"calls": w["calls"], "cost_usd": round(w["cost"], 6)},
        "daily_cap": cfg().ai.daily_cap_calls,
        "gemini_active": bool(os.environ.get("GEMINI_API_KEY")),
    }
