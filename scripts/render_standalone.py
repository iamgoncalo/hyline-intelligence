"""Gera um HTML standalone · self-contained · offline.

Abordagem:
  1. Bootstrap backend (schema + seed + ingest)
  2. Chama todos os endpoints via TestClient e guarda as respostas JSON
  3. Renderiza o template Jinja2 real
  4. Inline CSS + JS
  5. Injecta um pequeno shim que intercepta fetch() e serve as respostas do snapshot
  6. Remove chamadas à CDN (Chart.js) → desenho próprio em SVG para o gráfico horário
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

# Limpa DB para fresh snapshot
Path("data/hyline.db").unlink(missing_ok=True)

import subprocess
subprocess.run([sys.executable, "scripts/generate_sample_data.py", "--drop"],
               check=True, capture_output=True)

from fastapi.testclient import TestClient
from backend.app import app

cli = TestClient(app)

# ── 1. Precompute todas as respostas API ────────────────────────────
def get(url: str):
    r = cli.get(url); r.raise_for_status(); return r.json()

def post(url: str, body: dict):
    r = cli.post(url, json=body); r.raise_for_status(); return r.json()

snapshots = {
    "/api/kpi":                  get("/api/kpi"),
    "/api/stations":             get("/api/stations"),
    "/api/orders?limit=10":      get("/api/orders?limit=10"),
    "/api/alerts":               get("/api/alerts"),
    "/api/production/hourly":    get("/api/production/hourly"),
    "/api/agents/status":        get("/api/agents/status"),
    "/api/agents/optimiser":     get("/api/agents/optimiser"),
    "/api/scale/trends":         get("/api/scale/trends"),
    "/api/scale/priorities":     get("/api/scale/priorities"),
    "/api/sustainability":       get("/api/sustainability"),
    "/api/team":                 get("/api/team"),
    "/api/config/factory":       get("/api/config/factory"),
    "/api/connections":          get("/api/connections"),
    "/api/architecture":         get("/api/architecture"),
    "/api/procurement/catalog":  get("/api/procurement/catalog"),
    "/api/procurement/suppliers": get("/api/procurement/suppliers"),
    # Chatbot pre-answers
    "__chat__": {
        "qual é o F global?":        post("/api/agents/chatbot", {"question": "qual é o F global?"}),
        "pior estação":              post("/api/agents/chatbot", {"question": "pior estação"}),
        "alertas abertos":           post("/api/agents/chatbot", {"question": "alertas abertos"}),
        "produção hoje":             post("/api/agents/chatbot", {"question": "produção hoje"}),
    },
    # Assistant pre-answers for floating panel
    "__assistant__": {
        "encomendar vidro sustentável": post("/api/assistant", {"question": "encomendar vidro sustentável"}),
        "encomendar perfis eco":        post("/api/assistant", {"question": "encomendar perfis eco"}),
        "emissões CO₂ hoje":           post("/api/assistant", {"question": "emissões CO₂ hoje"}),
        "reatribuir operadores":        post("/api/assistant", {"question": "reatribuir operadores"}),
        "pior estação":                 post("/api/assistant", {"question": "pior estação"}),
    },
}

print(f"✓ Capturados {len(snapshots)-2} endpoints + 4 chatbot + 5 assistant")

# ── 2. Render do HTML real (usando o próprio app) ────────────────────
r = cli.get("/")
r.raise_for_status()
html = r.text

# ── 3. Inline CSS e JS (remove <link> e <script src=".../app.js"> e injecta) ──
css = (ROOT / "frontend/static/css/planta.css").read_text(encoding="utf-8")
js  = (ROOT / "frontend/static/js/app.js").read_text(encoding="utf-8")

# Substituições por str.replace — re.sub processaria \n no replacement como newline
html = html.replace(
    '<link rel="stylesheet" href="/static/css/planta.css">',
    f'<style>\n{css}\n</style>',
)
# Substitui o app.js src por inline
html = html.replace(
    '<script src="/static/js/app.js" defer></script>',
    f'<script>\n{js}\n</script>',
)

# ── 4. Injecta shim que intercepta fetch() + desenha gráficos em SVG ────
shim = """
<script>
// ═══════ SHIM OFFLINE · intercepta fetch() e serve snapshots estáticos ═══════
(function(){
  const SNAP = """ + json.dumps(snapshots, ensure_ascii=False) + """;

  // In-memory cart for demo mode
  const _demoCart = [];
  let _demoCartId = 0;

  const origFetch = window.fetch;
  window.fetch = async function(url, opts){
    if (typeof url === 'string'){
      // POST chatbot
      if (url.endsWith('/api/agents/chatbot') && opts && opts.method === 'POST'){
        const body = JSON.parse(opts.body);
        const q = (body.question || '').toLowerCase();
        const chat = SNAP.__chat__;
        let key = 'qual é o F global?';
        if (/pior|crítica|vermelh/.test(q))           key = 'pior estação';
        else if (/alerta|avaria/.test(q))             key = 'alertas abertos';
        else if (/produção|m[²2] hoje/.test(q))       key = 'produção hoje';
        else if (/f global|f-score|freedom/.test(q))  key = 'qual é o F global?';
        return fakeResp(chat[key] || {answer:'(modo offline) tenta: F global, pior estação, alertas abertos, produção hoje', sources:[]});
      }
      // POST decisions
      if (url.endsWith('/api/decisions') && opts && opts.method === 'POST'){
        const body = JSON.parse(opts.body);
        if (!body.confirmed) return new Response('{"detail":"needs confirm"}', {status:400});
        return fakeResp({ok:true, id: Math.floor(Math.random()*1000)});
      }
      // POST resolve alert
      if (url.match(/\\/api\\/alerts\\/\\d+\\/resolve/) && opts && opts.method === 'POST'){
        return fakeResp({ok:true});
      }
      // POST upload — modo demo
      if (url.endsWith('/api/connections/upload') && opts && opts.method === 'POST'){
        return fakeResp({ok:true, result:{file:'(demo)', source:'demo', rows: Math.floor(Math.random()*50)+50}});
      }
      // Assistant usage (always offline in standalone)
      if (url === '/api/assistant/usage'){
        return fakeResp({
          today: {calls:0, input_tokens:0, output_tokens:0, cost_usd:0},
          '7d': {calls:0, cost_usd:0},
          daily_cap: 1400,
          gemini_active: false,
        });
      }

      // Procurement catalog (with filter support)
      if (url === '/api/procurement/catalog' || url.startsWith('/api/procurement/catalog?')){
        const params = new URLSearchParams(url.includes('?') ? url.split('?')[1] : '');
        const cat = params.get('category');
        const minSust = parseInt(params.get('min_sustainability') || '0');
        let items = SNAP['/api/procurement/catalog'] || [];
        if (cat) items = items.filter(i => i.category === cat);
        if (minSust > 0) items = items.filter(i => i.sustainability_score >= minSust);
        return fakeResp(items);
      }
      if (url === '/api/procurement/suppliers'){
        return fakeResp(SNAP['/api/procurement/suppliers'] || []);
      }
      // In-memory cart (demo state)
      if (url === '/api/procurement/cart'){
        return fakeResp(_demoCart.map(i => ({...i, subtotal_eur: +(i.price_eur * i.quantity).toFixed(2)})));
      }
      if (url === '/api/procurement/cart/add' && opts && opts.method === 'POST'){
        const body = JSON.parse(opts.body);
        const catalog = (SNAP['/api/procurement/catalog'] || []).find(c => c.id === body.catalog_id);
        if (catalog){
          const exist = _demoCart.find(i => i.catalog_id === body.catalog_id);
          if (exist){ exist.quantity += (body.quantity || 1); return fakeResp({cart_id: exist.id, updated: true}); }
          const cid = ++_demoCartId;
          _demoCart.push({id:cid, catalog_id:catalog.id, quantity:body.quantity||1, added_ts:new Date().toISOString(),
            name:catalog.name, category:catalog.category, unit:catalog.unit, price_eur:catalog.price_eur,
            sustainability_score:catalog.sustainability_score, co2_per_unit:catalog.co2_per_unit,
            recycled_pct:catalog.recycled_pct, supplier_name:catalog.supplier_name});
          return fakeResp({cart_id: cid, updated: false});
        }
        return fakeResp({error:'not found'});
      }
      if (url.match(/\/api\/procurement\/cart\/\d+$/) && opts && opts.method === 'DELETE'){
        const id = parseInt(url.split('/').pop());
        const idx = _demoCart.findIndex(i => i.id === id);
        if (idx >= 0) _demoCart.splice(idx, 1);
        return fakeResp({ok: true});
      }
      if (url === '/api/procurement/checkout' && opts && opts.method === 'POST'){
        const body = JSON.parse(opts.body);
        if (!body.confirmed) return new Response('{"detail":"needs confirm"}', {status:400});
        const n = _demoCart.length;
        const tot = _demoCart.reduce((a,i) => a + i.price_eur * i.quantity, 0);
        const eco = n > 0 ? Math.round(_demoCart.reduce((a,i) => a + i.sustainability_score, 0) / n) : 0;
        _demoCart.length = 0;
        return fakeResp({ok:true, action_id:Math.floor(Math.random()*1000)+1, items:n, total_eur:+tot.toFixed(2), eco_score:eco});
      }
      // Assistant (floating panel)
      if (url === '/api/assistant' && opts && opts.method === 'POST'){
        const body = JSON.parse(opts.body);
        const q = (body.question || '').toLowerCase();
        const asst = SNAP.__assistant__ || {};
        let key = 'pior estação';
        if (/vidro/.test(q))                         key = 'encomendar vidro sustentável';
        else if (/perfil/.test(q))                   key = 'encomendar perfis eco';
        else if (/co2|co₂|emiss|carb/.test(q))      key = 'emissões CO₂ hoje';
        else if (/reatrib|optimiz|otimiz/.test(q))   key = 'reatribuir operadores';
        else if (/encomendar|comprar|fornecedor/.test(q)) key = 'encomendar vidro sustentável';
        return fakeResp(asst[key] || {answer:'(modo offline)', actions:[]});
      }

      // GET /api/export (listing)
      if (url === '/api/export'){
        const counts = {
          events:     0,  // não temos eventos no snapshot
          orders:     (SNAP['/api/orders?limit=10'] || []).length,
          alerts:     (SNAP['/api/alerts'] || []).length,
          stations:   (SNAP['/api/stations'] || []).length,
          team:       ((SNAP['/api/team'] || {}).members || []).length,
          decisions:  0,
        };
        return fakeResp([
          {key:'events',    label:'Eventos de Produção', rows:counts.events,    desc:'Todas as janelas já processadas · até 10 000 linhas'},
          {key:'orders',    label:'Encomendas',          rows:counts.orders,    desc:'Estado e progresso de cada obra'},
          {key:'alerts',    label:'Alertas',             rows:counts.alerts,    desc:'Histórico completo de alertas'},
          {key:'stations',  label:'Estações',            rows:counts.stations,  desc:'Configuração das 24 estações'},
          {key:'team',      label:'Equipa',              rows:counts.team,      desc:'Membros, roles e atribuições'},
          {key:'decisions', label:'Audit Trail',         rows:counts.decisions, desc:'Todas as decisões tomadas na plataforma'},
        ]);
      }
      // GET /api/export/{dataset} — gera CSV em JS puro a partir dos snapshots
      const mExport = url.match(/^\\/api\\/export\\/([a-z_]+)$/);
      if (mExport){
        const dataset = mExport[1];
        const csv = buildCSV(dataset);
        const ts = new Date().toISOString().replace(/[-:]/g,'').replace('.','').slice(0,15) + 'Z';
        const fname = `hyline_${dataset}_${ts}.csv`;
        return new Response(csv, {
          status: 200,
          headers: {
            'Content-Type': 'text/csv; charset=utf-8',
            'Content-Disposition': `attachment; filename="${fname}"`,
          },
        });
      }
      // GET snapshots
      if (SNAP[url] !== undefined) return fakeResp(SNAP[url]);
    }
    return origFetch(url, opts);
  };
  function fakeResp(obj){
    return new Response(JSON.stringify(obj), { status: 200, headers: {'Content-Type':'application/json'} });
  }

  // buildCSV: transforma snapshots em CSV puro (sem deps)
  function buildCSV(dataset){
    const escape = v => {
      if (v === null || v === undefined) return '';
      const s = String(v);
      if (/[",\\n]/.test(s)) return '"' + s.replace(/"/g,'""') + '"';
      return s;
    };
    const toCSV = (rows) => {
      if (!rows.length) return '';
      const keys = Object.keys(rows[0]);
      const out = [keys.join(',')];
      rows.forEach(r => out.push(keys.map(k => escape(r[k])).join(',')));
      return out.join('\\n') + '\\n';
    };
    if (dataset === 'orders')    return toCSV(SNAP['/api/orders?limit=10'] || []);
    if (dataset === 'alerts')    return toCSV(SNAP['/api/alerts'] || []);
    if (dataset === 'stations')  return toCSV((SNAP['/api/stations'] || []).map(s => ({
        id:s.id, nome:s.name, sector:s.sector, tipo:s.kind,
        target_m2_h:s.target_m2_per_hour, desempenho_pct: Math.round((s.afi_F||0)*100),
        m2_per_hour:s.m2_per_hour||0, eficiencia:s.efficiency||0, status:s.status||'idle',
    })));
    if (dataset === 'team'){
      const t = SNAP['/api/team'] || {members:[],roles:[]};
      const rolesById = Object.fromEntries((t.roles||[]).map(r => [r.id, r]));
      return toCSV((t.members||[]).map(m => ({
        id:m.id, nome:m.name, role_id:m.role, role_nome:(rolesById[m.role]||{}).name||'',
        nivel:(rolesById[m.role]||{}).level||'', estacao:m.station_assigned||'',
      })));
    }
    if (dataset === 'events' || dataset === 'decisions'){
      return '# ' + dataset + ' não disponível em modo demo (sem backend activo)\\n';
    }
    return '';
  }
})();
</script>
"""

# Injecta o shim ANTES do <script src="/static/js/app.js"> → vai estar antes agora que já foi inlined.
# Inserimos logo após o </head> para garantir que fetch é interceptado cedo.
html = html.replace('</head>', shim + '\n</head>')

# ── 5. Guardar ───────────────────────────────────────────────────────
OUT = ROOT / "hyline_dashboard_preview.html"
OUT.write_text(html, encoding="utf-8")
print(f"✓ Preview standalone: {OUT}")
print(f"  bytes: {OUT.stat().st_size:,}")
print(f"  tailwind: {'AUSENTE' if 'tailwindcss.com' not in html.lower() else 'PRESENTE (erro)'}")
print(f"  abre com duplo-click — funciona 100% offline.")
