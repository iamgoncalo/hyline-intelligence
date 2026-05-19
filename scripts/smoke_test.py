"""Smoke test end-to-end para a arquitectura v2 (5 ficheiros backend).
Corre:  python scripts/smoke_test.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

# Ensure clean DB for testing
Path("data/hyline.db").unlink(missing_ok=True)

from backend.config import load_config
from backend.data import init_schema, seed_all, ingest_inbox
from backend.engine import global_kpis, station_snapshot, open_alerts
from backend.agents import registry


def main() -> int:
    print("· HYLINE smoke test v2 ·")

    c = load_config("config.yaml")
    ws = sum(c.afi.d_channels.model_dump().values())
    assert abs(ws - 1.0) < 1e-6
    print(f"  [1] config · {len(c.stations)} stations · {len(c.teams.members)} members · α={c.afi.alpha}")

    init_schema(); seed_all()
    print("  [2] schema + seed OK")

    # Regenerate sample CSVs
    import subprocess
    subprocess.run([sys.executable, "scripts/generate_sample_data.py", "--drop"], check=True, capture_output=True)

    results = ingest_inbox()
    rows = sum(r.get("rows", 0) for r in results)
    print(f"  [3] ingerido · {rows} linhas")

    reg = registry()
    r = reg.tick()
    print(f"  [4] tick · {r['fired']} · alert_processed={r['alert_processed']}")

    snap = station_snapshot()
    productive = [s for s in snap if s["target_m2_per_hour"] > 0]
    assert len(snap) == 24
    print(f"  [5] snapshot · {len(snap)} stations · F min={min(s['afi_F'] for s in productive):.3f} max={max(s['afi_F'] for s in productive):.3f}")

    k = global_kpis()
    print(f"  [6] KPIs · m²today={k['m2_today']} · F_global={k['afi_F_global']} · alerts={k['open_alerts']}")

    al = open_alerts()
    for a in al[:3]:
        print(f"       alert [{a['routed_to']}] {a['station_name']} · {a['message'][:60]}")

    props = reg.optimiser.propose_reassignments()
    print(f"  [7] optimiser · {len(props)} propostas")

    for q in ["qual é o F global?", "pior estação", "alertas abertos"]:
        resp = reg.chatbot.answer(q)
        print(f"  [8] chat · {q} → {resp['answer'][:70]}")

    # HTTP
    from fastapi.testclient import TestClient
    from backend.app import app
    cli = TestClient(app)
    endpoints = ["/api/health", "/api/kpi", "/api/stations", "/api/orders",
                 "/api/alerts", "/api/production/hourly", "/api/agents/status",
                 "/api/agents/optimiser", "/api/scale/trends", "/api/scale/priorities",
                 "/api/sustainability", "/api/team", "/api/config/factory"]
    for ep in endpoints:
        r = cli.get(ep)
        assert r.status_code == 200, f"{ep} → {r.status_code}"
    print(f"  [9] HTTP · {len(endpoints)} endpoints · 200 OK")

    r = cli.post("/api/agents/chatbot", json={"question": "F global"})
    assert r.status_code == 200
    print(f"  [10] chatbot POST · OK")

    r = cli.post("/api/decisions", json={"kind":"test","target":"x","payload":{"ok":True},"confirmed":True})
    assert r.status_code == 200
    r = cli.post("/api/decisions", json={"kind":"test","target":"x","payload":{},"confirmed":False})
    assert r.status_code == 400
    print(f"  [11] are-you-sure enforcement OK")

    r = cli.get("/")
    assert r.status_code == 200 and "HYLINE" in r.text
    assert "tailwindcss" not in r.text.lower()
    print(f"  [12] dashboard · {len(r.text):,} bytes · zero Tailwind")

    print("· DONE ·")
    return 0


if __name__ == "__main__":
    sys.exit(main())
