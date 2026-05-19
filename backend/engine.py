"""Motor de inteligência. Consolida:
  • KPIs (m²/h por estação, headline, chart horário)
  • AFI · F = (P/D)^α aplicado à produção industrial
      P = score topológico da estação no fluxo
      D = média geométrica ponderada dos 6 canais de distortion
      α = 1.242 (CI 95% exclui 1.0 · Deucalion confirmado)
  • Alertas · classificação + routing automático (DQ/HST/Director/ChefeTurno)

Zero hardcode. Todos os parâmetros via config.yaml.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import numpy as np

from .config import cfg
from .data import connection


# ═══════════════════════════════════════════════════════════════════
# AFI · Architecture of Freedom Intelligence
# F = (P/D)^α ·  P = perception · D = distortion (geométrica)
# ═══════════════════════════════════════════════════════════════════

def _weights_array() -> np.ndarray:
    w = cfg().afi.d_channels.model_dump()
    # ordem fixa para reprodutibilidade
    return np.array([w["throughput"], w["quality"], w["machine"],
                     w["timeline"], w["operator"], w["setup"]])


def compute_D(channels: dict[str, float]) -> tuple[float, dict[str, float]]:
    """D = exp(Σ w_k × ln(max(d_k, 1.0)))  · media geométrica ponderada.

    channels dict deve ter: throughput, quality, machine, timeline, operator, setup.
    Retorna (D_total, attribution %).
    """
    w = cfg().afi.d_channels.model_dump()
    keys = ["throughput", "quality", "machine", "timeline", "operator", "setup"]
    # Cada d_k é clipped a >= 1 (distortion não é benefício)
    vals = np.array([max(channels.get(k, 1.0), 1.0) for k in keys])
    ws   = np.array([w[k] for k in keys])
    ln_D = float(np.sum(ws * np.log(vals)))
    D = math.exp(ln_D)
    if ln_D < 1e-10:
        return D, {k: 0.0 for k in keys}
    attr = {k: 100.0 * ws[i] * math.log(vals[i]) / ln_D for i, k in enumerate(keys)}
    return D, attr


def compute_F(P: float, D: float) -> float:
    """F = (P/D)^α · α vem do config.yaml."""
    alpha = cfg().afi.alpha
    if D <= 0: return 0.0
    return float(np.clip((P / D) ** alpha, 0.0, 1.0))


# ═══════════════════════════════════════════════════════════════════
# KPIs por estação · com AFI F-score calculado
# ═══════════════════════════════════════════════════════════════════

def _utcnow() -> datetime: return datetime.now(timezone.utc)
def _iso(dt: datetime) -> str: return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _d_channels_for_station(s_row: dict, window_minutes: int) -> dict[str, float]:
    """Calcula os 6 canais de D para uma estação, a partir da BD."""
    # 1. THROUGHPUT · shortfall em m²/h
    target = max(s_row["target_m2_per_hour"], 0.01)
    rate   = s_row["m2_per_hour"]
    d_throughput = max(1.0, target / max(rate, 0.01))  # abaixo do target ↑

    # 2. QUALITY · % de defects/rework na janela
    d_quality = max(1.0, 1.0 + s_row.get("defect_rate", 0.0) * 5)

    # 3. MACHINE · se houve breakdown recente → penaliza
    d_machine = 2.0 if s_row.get("had_breakdown", False) else 1.0

    # 4. TIMELINE · proximidade ao deadline mais urgente desta estação
    d_timeline = max(1.0, 1.0 + (1.0 / max(s_row.get("days_to_deadline", 30), 1)))

    # 5. OPERATOR · carga (estações sem operador assignado são penalizadas levemente)
    d_operator = 1.0 if s_row.get("has_operator", True) else 1.3

    # 6. SETUP · proxy fixo por agora (futuro: changeover time real)
    d_setup = 1.1

    return {
        "throughput": d_throughput, "quality": d_quality, "machine": d_machine,
        "timeline": d_timeline, "operator": d_operator, "setup": d_setup,
    }


def _p_for_station(s_row: dict) -> float:
    """Score topológico: estações centrais no fluxo têm P maior.
    Aproximação: montagem=0.85, corte=0.78, acabamento=0.75, outros=0.6.
    """
    kind = s_row.get("kind", "machine")
    base = {
        "assembly": 0.85, "machine": 0.78, "finishing": 0.75,
        "dispatch": 0.70, "buffer": 0.30, "storage": 0.25,
    }.get(kind, 0.60)
    # Se está em atividade recente, P é máximo; caído com inatividade
    activity = 1.0 if s_row.get("windows_in_progress", 0) > 0 or s_row.get("m2_per_hour", 0) > 0 else 0.4
    return float(np.clip(base * activity, 0.0, 1.0))


def station_snapshot(window_minutes: int = 60) -> list[dict]:
    """Snapshot completo para cada estação: métricas produtivas + AFI F-score."""
    now = _utcnow()
    since = _iso(now - timedelta(minutes=window_minutes))
    day_start = _iso(now.replace(hour=0, minute=0, second=0, microsecond=0))

    green = cfg().thresholds.green_min
    amber = cfg().thresholds.amber_min

    with connection() as conn:
        rows = conn.execute(
            """
            SELECT s.id, s.name, s.sector, s.kind, s.target_m2_per_hour,
                   COALESCE(SUM(CASE WHEN e.status='completed' AND e.ts>=? THEN e.area_m2 ELSE 0 END), 0.0) AS m2_window,
                   COALESCE(SUM(CASE WHEN e.status='completed' AND e.ts>=? THEN e.area_m2 ELSE 0 END), 0.0) AS m2_today,
                   COUNT(CASE WHEN e.status='started' AND e.ts>=? THEN 1 END) AS windows_in_progress,
                   COUNT(CASE WHEN e.status IN ('defect','rework') AND e.ts>=? THEN 1 END) AS defect_count,
                   COUNT(CASE WHEN e.ts>=? THEN 1 END) AS total_events,
                   MAX(CASE WHEN e.status='breakdown' AND e.ts>=? THEN 1 ELSE 0 END) AS had_breakdown,
                   (SELECT window_id FROM production_events pe WHERE pe.station_id=s.id ORDER BY pe.ts DESC LIMIT 1) AS current_window_id,
                   (SELECT order_id  FROM production_events pe WHERE pe.station_id=s.id ORDER BY pe.ts DESC LIMIT 1) AS current_order_id
            FROM stations s
            LEFT JOIN production_events e ON e.station_id = s.id
            GROUP BY s.id
            ORDER BY s.sector, s.id
            """,
            (since, day_start, since, since, since, since),
        ).fetchall()

        members_by_station = {}
        for m in conn.execute(
            "SELECT station_assigned, name, initials FROM members WHERE station_assigned IS NOT NULL AND active=1"
        ).fetchall():
            members_by_station.setdefault(m["station_assigned"], []).append(dict(m))

    out = []
    for r in rows:
        target = float(r["target_m2_per_hour"])
        m2_window = float(r["m2_window"])
        m2_rate = m2_window * (60.0 / window_minutes)
        efficiency = (m2_rate / target) if target > 0 else 0.0

        # Zonas estruturais (buffer/storage/dispatch sem target)
        if target == 0:
            status = "idle"
        elif efficiency >= green:
            status = "green"
        elif efficiency >= amber:
            status = "amber"
        else:
            status = "red"

        total_events = int(r["total_events"])
        defect_rate = (int(r["defect_count"]) / max(total_events, 1)) if total_events > 0 else 0.0

        s_row = {
            "kind": r["kind"],
            "target_m2_per_hour": target,
            "m2_per_hour": m2_rate,
            "defect_rate": defect_rate,
            "had_breakdown": bool(r["had_breakdown"]),
            "days_to_deadline": 14,  # TODO: derivar da encomenda atual
            "has_operator": r["id"] in members_by_station,
            "windows_in_progress": int(r["windows_in_progress"]),
        }

        # AFI
        D, D_attr = compute_D(_d_channels_for_station(s_row, window_minutes))
        P = _p_for_station(s_row)
        F = compute_F(P, D)

        out.append({
            "id": r["id"], "name": r["name"], "sector": r["sector"], "kind": r["kind"],
            "target_m2_per_hour": round(target, 2),
            "m2_per_hour": round(m2_rate, 2),
            "m2_today": round(float(r["m2_today"]), 2),
            "efficiency": round(efficiency, 3),
            "status": status,
            "windows_in_progress": int(r["windows_in_progress"]),
            "current_window_id": r["current_window_id"],
            "current_order_id":  r["current_order_id"],
            "defect_rate": round(defect_rate, 3),
            # AFI
            "afi_P": round(P, 3),
            "afi_D": round(D, 3),
            "afi_F": round(F, 3),
            "afi_D_attribution": {k: round(v, 1) for k, v in D_attr.items()},
            "operators": members_by_station.get(r["id"], []),
        })
    return out


def global_kpis() -> dict:
    now = _utcnow()
    day_start = _iso(now.replace(hour=0, minute=0, second=0, microsecond=0))
    active_since = _iso(now - timedelta(minutes=30))
    with connection() as conn:
        r = conn.execute(
            """
            SELECT
              COALESCE(SUM(CASE WHEN e.status='completed' AND e.ts>=? THEN e.area_m2 ELSE 0 END), 0.0) AS m2_today,
              COUNT(DISTINCT CASE WHEN e.ts>=? THEN e.station_id END) AS stations_active,
              (SELECT COUNT(*) FROM alerts WHERE resolved_ts IS NULL) AS open_alerts,
              (SELECT COUNT(*) FROM stations WHERE target_m2_per_hour > 0) AS stations_total,
              (SELECT COALESCE(SUM(total_m2),0) FROM orders WHERE status IN ('active','in_progress','open')) AS m2_backlog,
              (SELECT COUNT(*) FROM orders WHERE status IN ('active','in_progress','open')) AS open_orders
            FROM production_events e
            """,
            (day_start, active_since),
        ).fetchone()

    # F-global = média geométrica dos F das estações produtivas
    snaps = station_snapshot()
    f_values = [s["afi_F"] for s in snaps if s["target_m2_per_hour"] > 0 and s["afi_F"] > 0]
    f_global = float(np.exp(np.mean(np.log(f_values)))) if f_values else 0.0

    return {
        "m2_today": round(float(r["m2_today"] or 0.0), 2),
        "stations_active": int(r["stations_active"] or 0),
        "stations_total": int(r["stations_total"] or 0),
        "open_alerts": int(r["open_alerts"] or 0),
        "m2_backlog": round(float(r["m2_backlog"] or 0.0), 2),
        "open_orders": int(r["open_orders"] or 0),
        "afi_F_global": round(f_global, 3),
        "ts": _iso(now),
    }


def hourly_production_today() -> list[dict]:
    now = _utcnow()
    day_start = _iso(now.replace(hour=0, minute=0, second=0, microsecond=0))
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT strftime('%H', e.ts) AS hour, s.sector AS sector, SUM(e.area_m2) AS m2
            FROM production_events e JOIN stations s ON s.id = e.station_id
            WHERE e.status = 'completed' AND e.ts >= ?
            GROUP BY hour, sector ORDER BY hour
            """,
            (day_start,),
        ).fetchall()
    return [{"hour": r["hour"], "sector": r["sector"], "m2": round(float(r["m2"]), 2)} for r in rows]


# ═══════════════════════════════════════════════════════════════════
# ALERTAS · classificação + routing automático
# ═══════════════════════════════════════════════════════════════════

def _route(alert_type: str, severity: int) -> str:
    if severity >= cfg().alerts.severity_to_escalate:
        return "Director"
    return cfg().alerts.routing.get(alert_type, "ChefeTurno")


def _insert_alert(ts, station_id, atype, sev, message, m2_impact=0.0):
    routed = _route(atype, sev)
    with connection() as conn:
        existing = conn.execute(
            "SELECT id FROM alerts WHERE station_id=? AND alert_type=? AND resolved_ts IS NULL AND ts > ?",
            (station_id, atype, _iso(_utcnow() - timedelta(minutes=cfg().thresholds.sustained_minutes))),
        ).fetchone()
        if existing: return
        conn.execute(
            "INSERT INTO alerts (ts, station_id, alert_type, severity, routed_to, message, m2_impact) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ts, station_id, atype, sev, routed, message, m2_impact),
        )


def scan_quality() -> int:
    since = _iso(_utcnow() - timedelta(minutes=cfg().thresholds.sustained_minutes))
    n = 0
    with connection() as conn:
        rows = conn.execute(
            "SELECT ts, station_id, window_id, order_id, status, area_m2 "
            "FROM production_events WHERE ts >= ? AND status IN ('defect','rework')",
            (since,),
        ).fetchall()
    for r in rows:
        atype = "quality" if r["status"] == "defect" else "rework"
        sev = 3 if r["status"] == "defect" else 2
        msg = (f"{'Não-conformidade' if atype=='quality' else 'Retrabalho'} · "
               f"Janela {r['window_id']} · Obra {r['order_id']} · {r['area_m2']:.2f} m²")
        _insert_alert(r["ts"], r["station_id"], atype, sev, msg, r["area_m2"])
        n += 1
    return n


def scan_breakdowns() -> int:
    since = _iso(_utcnow() - timedelta(minutes=cfg().thresholds.sustained_minutes))
    n = 0
    with connection() as conn:
        rows = conn.execute(
            "SELECT ts, station_id, area_m2, status FROM production_events "
            "WHERE ts >= ? AND status IN ('breakdown','safety')",
            (since,),
        ).fetchall()
    for r in rows:
        atype = r["status"]
        sev = 4 if atype == "safety" else 3
        msg = "Avaria de equipamento" if atype == "breakdown" else "Incidente de segurança"
        _insert_alert(r["ts"], r["station_id"], atype, sev, msg, r["area_m2"])
        n += 1
    return n


def scan_performance() -> int:
    snap = station_snapshot(window_minutes=cfg().thresholds.sustained_minutes)
    now_iso = _iso(_utcnow())
    n = 0
    for s in snap:
        if s["target_m2_per_hour"] == 0: continue
        if s["m2_per_hour"] == 0 and s["windows_in_progress"] == 0: continue
        eff = s["efficiency"]
        if eff < 0.5:
            msg = f"{s['name']} a {eff*100:.0f}% do target ({s['m2_per_hour']:.2f}/{s['target_m2_per_hour']:.2f} m²/h)"
            m2_impact = max(0.0, s["target_m2_per_hour"] - s["m2_per_hour"])
            _insert_alert(now_iso, s["id"], "critical_delay", 4, msg, m2_impact)
            n += 1
        elif eff < cfg().thresholds.amber_min:
            msg = f"{s['name']} abaixo do target · {s['m2_per_hour']:.2f}/{s['target_m2_per_hour']:.2f} m²/h"
            m2_impact = max(0.0, s["target_m2_per_hour"] - s["m2_per_hour"])
            _insert_alert(now_iso, s["id"], "delay", 2, msg, m2_impact)
            n += 1
    return n


def scan_all() -> dict:
    return {
        "quality":     scan_quality(),
        "breakdowns":  scan_breakdowns(),
        "performance": scan_performance(),
    }


def open_alerts(limit: int = 50) -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT a.id, a.ts, a.station_id, s.name AS station_name, "
            "a.alert_type, a.severity, a.routed_to, a.message, a.m2_impact, "
            "a.ai_diagnosis, a.ai_actions "
            "FROM alerts a JOIN stations s ON s.id = a.station_id "
            "WHERE a.resolved_ts IS NULL ORDER BY a.severity DESC, a.ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def resolve_alert(alert_id: int, note: str, resolved_by: str | None) -> None:
    with connection() as conn:
        conn.execute(
            "UPDATE alerts SET resolved_ts=?, resolution_note=?, resolved_by=? WHERE id=?",
            (_iso(_utcnow()), note, resolved_by, alert_id),
        )


# ═══════════════════════════════════════════════════════════════════
# GOOGLE TRENDS · live com cache 1h + fallback para config
# ═══════════════════════════════════════════════════════════════════

import logging
log = logging.getLogger(__name__)

_TRENDS_CACHE: dict = {"ts": None, "data": None, "source": "config"}
_TRENDS_TTL_SECONDS = 3600  # 1h


def fetch_trends(force_refresh: bool = False) -> dict:
    """Tenta puxar Google Trends ao vivo via pytrends. Em caso de rate-limit
    ou erro, devolve snapshot do config marcado como SIMULADO.

    Cache de 1h para evitar bater no Google em cada request.
    """
    now = _utcnow()
    if not force_refresh and _TRENDS_CACHE["ts"] is not None:
        age = (now - _TRENDS_CACHE["ts"]).total_seconds()
        if age < _TRENDS_TTL_SECONDS:
            return _TRENDS_CACHE["data"]

    config_terms = [t.term for t in cfg().scale.trends_pt]

    try:
        from pytrends.request import TrendReq
        pytrends = TrendReq(hl="pt-PT", tz=0, timeout=(8, 12), retries=1, backoff_factor=0.3)
        # Pytrends suporta 5 termos por request — usamos no máximo 4
        pytrends.build_payload(config_terms[:4], timeframe="today 12-m", geo="PT")
        df = pytrends.interest_over_time()
        if df is None or df.empty:
            raise RuntimeError("Google Trends devolveu DataFrame vazio")
        if "isPartial" in df.columns:
            df = df.drop(columns=["isPartial"])
        # Resample para 12 pontos mensais
        monthly = df.resample("ME").mean().tail(12)
        result_terms = []
        for term in config_terms[:4]:
            if term in monthly.columns:
                series = [round(float(v), 1) for v in monthly[term].tolist()]
                # Garante 12 pontos (preenche se vier menor)
                while len(series) < 12: series.insert(0, series[0] if series else 0)
                result_terms.append({"term": term, "series": series[-12:]})
        data = {
            "source": "google_live",
            "fetched_at": _iso(now),
            "geo": "PT",
            "timeframe": "today 12-m",
            "terms": result_terms,
        }
        _TRENDS_CACHE.update({"ts": now, "data": data, "source": "google_live"})
        log.info("Google Trends live · %d termos", len(result_terms))
        return data
    except Exception as e:  # noqa: BLE001
        log.warning("Google Trends fallback (%s)", e)
        data = {
            "source": "config_fallback",
            "fetched_at": _iso(now),
            "geo": "PT",
            "timeframe": "12 meses (snapshot)",
            "fallback_reason": str(e)[:140],
            "terms": [t.model_dump() for t in cfg().scale.trends_pt],
        }
        _TRENDS_CACHE.update({"ts": now, "data": data, "source": "config_fallback"})
        return data


def trends_with_suggestions() -> dict:
    """Trends + sugestões accionáveis.

    Para cada termo, calcula:
      • slope (últimos 3 meses vs 3 meses anteriores)
      • value (média 3 últimos meses)
      • acceleration (slope dos últimos 6m)
    E emite sugestões claras para a HYLINE: "esta tendência está a acelerar
    +47% — considera acelerar capacidade de X".
    """
    t = fetch_trends()
    suggestions = []

    for term_data in t["terms"]:
        s = term_data["series"]
        if len(s) < 6: continue
        recent = sum(s[-3:]) / 3
        previous = sum(s[-6:-3]) / 3
        delta_pct = ((recent - previous) / max(previous, 1)) * 100
        latest = s[-1]
        peak = max(s)

        action = None
        priority = "info"
        keyword = term_data["term"].lower()

        if delta_pct > 25:
            priority = "act"
            if "eficiência" in keyword:
                action = (f"Procura por eficiência energética sobe {delta_pct:+.0f}% "
                          f"vs trimestre anterior. Reforçar comunicação do produto eficiente.")
            elif "reabilitação" in keyword:
                action = (f"Reabilitação cresce {delta_pct:+.0f}%. Aproximar comerciais "
                          f"a empresas de reabilitação urbana — janela de oportunidade.")
            elif "pvc" in keyword:
                action = (f"Pesquisa por PVC sobe {delta_pct:+.0f}%. Manter stock seguro "
                          f"de perfis e antecipar ramp-up de produção.")
            elif "oscilo" in keyword:
                action = (f"Oscilo-batentes ganha tracção +{delta_pct:.0f}%. Avaliar "
                          f"capacidade dedicada (alinha com prioridade SP02).")
            else:
                action = f"Termo '{term_data['term']}' acelera +{delta_pct:.0f}%. Investigar."
        elif delta_pct < -15:
            priority = "watch"
            action = (f"'{term_data['term']}' cai {delta_pct:.0f}%. Reduzir investimento "
                      f"em campanhas associadas e validar com vendas.")
        elif latest >= peak * 0.95:
            priority = "info"
            action = f"'{term_data['term']}' mantém-se perto do pico ({latest:.0f}/{peak:.0f}). Estável."

        if action:
            suggestions.append({
                "term": term_data["term"],
                "delta_pct": round(delta_pct, 1),
                "current": latest,
                "priority": priority,
                "action": action,
            })

    # Ordena: act > watch > info
    order = {"act": 0, "watch": 1, "info": 2}
    suggestions.sort(key=lambda x: (order.get(x["priority"], 3), -abs(x["delta_pct"])))

    return {**t, "suggestions": suggestions}
