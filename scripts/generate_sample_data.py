"""Gera CSVs de demonstração compatíveis com a fábrica real HYLINE.

Uso:
    python scripts/generate_sample_data.py          # apenas gera em sample_data/
    python scripts/generate_sample_data.py --drop   # também copia para data/inbox/
"""
from __future__ import annotations

import argparse
import random
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.config import cfg  # noqa: E402

SEED = 2026
random.seed(SEED)

SAMPLE_DIR = ROOT / "sample_data"
SAMPLE_DIR.mkdir(parents=True, exist_ok=True)

# Operadores reais HYLINE
OPERATORS = [
    {"id": "OP01", "name": "Carlos Silva",   "line": "correr", "shift": "manha"},
    {"id": "OP02", "name": "Ana Ferreira",   "line": "correr", "shift": "manha"},
    {"id": "OP03", "name": "João Santos",    "line": "abrir",  "shift": "manha"},
    {"id": "OP04", "name": "Marta Costa",   "line": "abrir",  "shift": "manha"},
    {"id": "OP05", "name": "Pedro Alves",   "line": "correr", "shift": "tarde"},
    {"id": "OP06", "name": "Sofia Nunes",   "line": "correr", "shift": "tarde"},
    {"id": "OP07", "name": "Miguel Rocha",  "line": "abrir",  "shift": "tarde"},
    {"id": "OP08", "name": "Inês Lopes",    "line": "abrir",  "shift": "tarde"},
    {"id": "OP09", "name": "Rui Martins",   "line": "correr", "shift": "manha"},
    {"id": "OP10", "name": "Beatriz Cruz",  "line": "abrir",  "shift": "manha"},
]
OP_IDS = [o["id"] for o in OPERATORS]

# Tipos de não conformidade reais para janelas PVC
NC_TYPES = [
    "Perfil desalinhado",
    "Vedante incompleto",
    "Vidro riscado",
    "Folga excessiva",
    "Cor fora de especificação",
]

# Empresas construtoras portuguesas realistas
CUSTOMERS = [
    "Construções Oliveira Lda",
    "Edifícios do Minho SA",
    "Residencial Esposende",
    "Obras Atlântico Lda",
    "Quinta do Pinhal Construções",
    "Viana Properties Lda",
    "Lusa Habitat SA",
    "Braga Imobiliária",
    "Porto Construções Norte",
    "Guimarães Reabilitação Lda",
]

# Referências realistas HYLINE
REF_CORRER = ["SC-60", "SC-70", "SC-82"]
REF_ABRIR  = ["AB-58", "AB-68", "AB-78"]
SIZES_MM   = [(600,1200),(900,1400),(1200,1500),(1400,2100),(2000,2200),(800,1600),(1000,2000)]


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _biased_ts(now: datetime, hours_total: float) -> datetime:
    """Gera timestamp com distribuição biased para as últimas 2 horas.

    Beta(3, 1) dá ~80% dos eventos nas últimas 2h/3 do período.
    Garante que a janela de 60 min do snapshot tem eventos suficientes.
    """
    start = now - timedelta(hours=hours_total)
    u = random.betavariate(3, 1)        # skew toward recent (u close to 1)
    secs = u * hours_total * 3600
    return start + timedelta(seconds=secs)


def generate_orders(n: int = 40) -> pd.DataFrame:
    rows = []
    today = datetime.now(timezone.utc).date()
    refs = REF_CORRER + REF_ABRIR
    for i in range(1, n + 1):
        n_windows = random.randint(4, 40)
        w, h = random.choice(SIZES_MM)
        unit_m2 = (w * h) / 1_000_000
        total_m2 = round(n_windows * unit_m2, 2)
        deadline = today + timedelta(days=random.randint(5, 45))
        status = random.choices(
            ["active", "in_progress", "in_progress", "open", "completed"], k=1,
        )[0]
        rows.append({
            "order_id":       f"ORD-2026-{i:04d}",
            "customer":       random.choice(CUSTOMERS),
            "total_windows":  n_windows,
            "total_m2":       total_m2,
            "deadline":       deadline.isoformat(),
            "priority":       random.randint(1, 5),
            "status":         status,
        })
    return pd.DataFrame(rows)


def generate_events(orders: pd.DataFrame, hours_back: float = 9.0) -> pd.DataFrame:
    """Gera eventos de produção com distribuição temporal realista.

    Target demo distribution: 35% green, 40% amber, 25% red
    A maioria dos eventos está nas últimas 2h para que o snapshot de 60 min
    mostre actividade em todas as estações.
    """
    productive = [s for s in cfg().stations if s.target_m2_per_hour > 0]
    now = datetime.now(timezone.utc)

    # Performance por estação — mix realista para demo
    performance: dict[str, float] = {}
    for s in productive:
        # Base: mix que dá ~35% green, 40% amber, 25% red
        r = random.random()
        if r < 0.35:
            perf = random.uniform(0.92, 1.08)   # green (>= 0.90)
        elif r < 0.75:
            perf = random.uniform(0.72, 0.89)   # amber (0.70–0.90)
        else:
            perf = random.uniform(0.40, 0.69)   # red (< 0.70)
        performance[s.id] = perf

    # Estações específicas para demo narrativa
    performance.update({
        "ST-COR-01": 0.98,   # Montagem Correr 01 — verde (bom operador)
        "ST-COR-02": 0.81,   # Montagem Correr 02 — amber
        "ST-PRE-02": 0.48,   # Prensa 01 — vermelho crítico
        "ST-ABR-01": 0.55,   # Montagem Abrir 01 — vermelho
        "ST-COR-F1": 0.95,   # Acabamento Correr 01 — verde
        "ST-ABR-F2": 0.88,   # Acabamento Abrir 02 — verde
    })

    active_orders = orders[
        orders["status"].isin(["active", "in_progress", "open"])
    ]["order_id"].tolist()
    if not active_orders:
        active_orders = orders["order_id"].tolist()

    rows = []
    window_counter = 1

    # Mapa de operadores por linha
    correr_ops = [o["id"] for o in OPERATORS if o["line"] == "correr"]
    abrir_ops  = [o["id"] for o in OPERATORS if o["line"] == "abrir"]

    for s in productive:
        perf = performance[s.id]
        # Gera eventos proporcionais à performance e ao tempo
        expected = max(2, int(s.target_m2_per_hour * hours_back * perf * 0.6))
        line_ops = correr_ops if s.sector == "correr" else abrir_ops
        if not line_ops:
            line_ops = OP_IDS

        for _ in range(expected):
            w, h = random.choice(SIZES_MM)
            ts = _biased_ts(now, hours_back)
            window_id = f"W-{window_counter:06d}"
            window_counter += 1

            # 3% non-conformities
            nc_roll = random.random()
            if nc_roll < 0.01:
                status = "defect"
            elif nc_roll < 0.04:
                status = "rework"
            else:
                status = "completed"

            rows.append({
                "timestamp":   _iso(ts),
                "station_id":  s.id,
                "window_id":   window_id,
                "order_id":    random.choice(active_orders),
                "width_mm":    w,
                "height_mm":   h,
                "phase":       s.sector,
                "status":      status,
                "operator_id": random.choice(line_ops),
            })

    # ── Alertas forçados para demo completo ──────────────────────

    # Director — incidente de segurança Prensa 01 (sev 4 → escalada Director)
    rows.append({
        "timestamp":   _iso(now - timedelta(minutes=4)),
        "station_id":  "ST-PRE-02",
        "window_id":   f"W-{window_counter:06d}",
        "order_id":    random.choice(active_orders),
        "width_mm":    1200, "height_mm": 1400,
        "phase":       "pre", "status": "safety",
        "operator_id": "OP09",
    })
    window_counter += 1

    # HST — avaria Montagem Correr 02
    rows.append({
        "timestamp":   _iso(now - timedelta(minutes=8)),
        "station_id":  "ST-COR-02",
        "window_id":   f"W-{window_counter:06d}",
        "order_id":    random.choice(active_orders),
        "width_mm":    1200, "height_mm": 1600,
        "phase":       "correr", "status": "breakdown",
        "operator_id": "OP02",
    })
    window_counter += 1

    # DQ — não conformidade Desembalagem
    rows.append({
        "timestamp":   _iso(now - timedelta(minutes=9)),
        "station_id":  "ST-EXP-01",
        "window_id":   f"W-{window_counter:06d}",
        "order_id":    random.choice(active_orders),
        "width_mm":    900, "height_mm": 1400,
        "phase":       "expedicao", "status": "defect",
        "operator_id": "OP04",
    })
    window_counter += 1

    # Director — atraso crítico Prensa 01 (abaixo de 50% target)
    # Garante vários eventos na janela recente mas com baixa m²/h
    for _ in range(3):
        ts = now - timedelta(minutes=random.randint(5, 55))
        rows.append({
            "timestamp":   _iso(ts),
            "station_id":  "ST-PRE-02",
            "window_id":   f"W-{window_counter:06d}",
            "order_id":    random.choice(active_orders),
            "width_mm":    600, "height_mm": 800,
            "phase":       "pre", "status": "completed",
            "operator_id": "OP09",
        })
        window_counter += 1

    # ChefeTurno — produção abaixo do target Montagem Abrir 01
    # Apenas 1 evento na janela de 60 min → garante alerta de delay
    for _ in range(1):
        ts = now - timedelta(minutes=random.randint(5, 55))
        rows.append({
            "timestamp":   _iso(ts),
            "station_id":  "ST-ABR-01",
            "window_id":   f"W-{window_counter:06d}",
            "order_id":    random.choice(active_orders),
            "width_mm":    800, "height_mm": 1200,
            "phase":       "abrir", "status": "completed",
            "operator_id": "OP03",
        })
        window_counter += 1

    df = pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)
    return df


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--drop", action="store_true",
                        help="Também copia os CSVs para data/inbox/")
    args = parser.parse_args()

    orders = generate_orders(n=40)
    events = generate_events(orders, hours_back=9.0)

    # Verificações
    nc = events[events["status"].isin(["defect","rework"])]
    ops_used = events["operator_id"].unique()
    print(f"✓ {len(orders)} encomendas geradas")
    print(f"✓ {len(events)} eventos gerados")
    print(f"  └ não-conformidades: {len(nc)}")
    print(f"  └ operadores com eventos: {len(ops_used)}/10")

    orders_path = SAMPLE_DIR / "primavera_orders.csv"
    events_path = SAMPLE_DIR / "preference_events.csv"
    orders.to_csv(orders_path, index=False)
    events.to_csv(events_path, index=False)

    print(f"✓ {orders_path.relative_to(ROOT)}")
    print(f"✓ {events_path.relative_to(ROOT)}")

    if args.drop:
        inbox_cfg = Path(cfg().paths.inbox)
        inbox = inbox_cfg if inbox_cfg.is_absolute() else ROOT / inbox_cfg
        inbox.mkdir(parents=True, exist_ok=True)
        shutil.copy(orders_path, inbox / orders_path.name)
        shutil.copy(events_path, inbox / events_path.name)
        try:
            shown = inbox.relative_to(ROOT)
        except ValueError:
            shown = inbox
        print(f"✓ Copiados para {shown}/ — watcher ingere automaticamente.")


if __name__ == "__main__":
    main()
