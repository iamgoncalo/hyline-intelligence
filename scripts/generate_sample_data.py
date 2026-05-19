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


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_orders(n: int = 40) -> pd.DataFrame:
    customers = [
        "Casa Porto Lda", "Edifícios do Norte", "Construtora Aveiro",
        "Vilas do Minho", "Residencial Esposende", "Obras & Cª",
        "Atlântico Construções", "Quinta do Pinhal", "Viana Properties",
        "Lusa Habitat",
    ]
    rows = []
    today = datetime.now(timezone.utc).date()
    for i in range(1, n + 1):
        n_windows = random.randint(4, 40)
        avg_area = random.uniform(1.2, 3.5)
        total_m2 = round(n_windows * avg_area, 2)
        deadline = today + timedelta(days=random.randint(3, 45))
        status = random.choices(
            ["active", "in_progress", "in_progress", "open", "completed"], k=1,
        )[0]
        rows.append({
            "order_id": f"ORD-2026-{i:04d}",
            "customer": random.choice(customers),
            "total_windows": n_windows,
            "total_m2": total_m2,
            "deadline": deadline.isoformat(),
            "priority": random.randint(1, 5),
            "status": status,
        })
    return pd.DataFrame(rows)


def generate_events(orders: pd.DataFrame, hours_back: int = 10) -> pd.DataFrame:
    """Gera eventos de produção apenas para estações produtivas.
    Inclui uma avaria numa das prensas para demo realista.
    """
    productive = [s for s in cfg().stations if s.target_m2_per_hour > 0]
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=hours_back)

    # Factor de performance por estação — realista (mix verde/amber/vermelho)
    performance = {s.id: random.uniform(0.55, 1.05) for s in productive}
    # Forçar estados específicos para demo
    forced = {
        "ST-PRE-02": 0.45,   # Prensa 01 — crítico
        "ST-COR-02": 0.78,   # Montagem Correr 02 — amber
        "ST-COR-01": 0.98,   # Montagem Correr 01 — verde
        "ST-ABR-01": 0.52,   # Montagem Abrir 01 — vermelho
        "ST-COR-F1": 0.92,   # Acabamento Correr 01 — verde
    }
    performance.update({k: v for k, v in forced.items() if k in performance})

    active_orders = orders[orders["status"].isin(["active", "in_progress", "open"])]["order_id"].tolist()
    if not active_orders:
        active_orders = orders["order_id"].tolist()

    rows = []
    window_counter = 1
    for s in productive:
        expected = max(1, int(s.target_m2_per_hour * hours_back * performance[s.id] / 2.0))
        for _ in range(expected):
            width = random.choice([600, 800, 900, 1000, 1200, 1400, 1600, 1800])
            height = random.choice([800, 1000, 1200, 1400, 1600, 1800, 2000, 2200])
            ts = start + timedelta(seconds=random.uniform(0, hours_back * 3600))
            window_id = f"W-{window_counter:06d}"
            window_counter += 1
            status = random.choices(
                ["completed"]*8 + ["rework", "defect"], k=1,
            )[0]
            rows.append({
                "timestamp": _iso(ts),
                "station_id": s.id,
                "window_id": window_id,
                "order_id": random.choice(active_orders),
                "width_mm": width,
                "height_mm": height,
                "phase": s.sector,
                "status": status,
                "operator_id": f"OP-{random.randint(1, 12):02d}",
            })

    # Injectar uma avaria para testar o routing → HST
    rows.append({
        "timestamp": _iso(now - timedelta(minutes=6)),
        "station_id": "ST-COR-02",
        "window_id": f"W-{window_counter:06d}",
        "order_id": random.choice(active_orders),
        "width_mm": 1200,
        "height_mm": 1600,
        "phase": "correr",
        "status": "breakdown",
        "operator_id": "OP-05",
    })

    df = pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)
    return df


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--drop", action="store_true",
                        help="Também copia os CSVs para data/inbox/ (watcher ingere automaticamente)")
    args = parser.parse_args()

    orders = generate_orders(n=40)
    events = generate_events(orders, hours_back=10)

    orders_path = SAMPLE_DIR / "primavera_orders.csv"
    events_path = SAMPLE_DIR / "preference_events.csv"
    orders.to_csv(orders_path, index=False)
    events.to_csv(events_path, index=False)

    print(f"✓ {len(orders)} encomendas → {orders_path.relative_to(ROOT)}")
    print(f"✓ {len(events)} eventos    → {events_path.relative_to(ROOT)}")

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
