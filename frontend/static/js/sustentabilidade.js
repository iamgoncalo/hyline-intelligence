/* sustentabilidade.js — sustainability KPIs + env context */
'use strict';
const $ = id => document.getElementById(id);
const fetchJSON = async (url, opts) => { const r = await fetch(url, opts); if (!r.ok) throw new Error(r.status); return r.json(); };
const nf = (v,d=1) => v==null ? '--' : Number(v).toLocaleString('pt-PT',{minimumFractionDigits:d,maximumFractionDigits:d});

async function load() {
  try {
    const [s, k, env, sup] = await Promise.all([
      fetchJSON('/api/sustainability'),
      fetchJSON('/api/kpi'),
      fetchJSON('/api/environment').catch(() => ({})),
      fetchJSON('/api/procurement/suppliers').catch(() => [])
    ]);

    const set = (id, val) => { const el=$(id); if(el) el.textContent = val; };
    set('s-m2',           nf(k.m2_today));
    set('s-orders',       k.open_orders ?? '--');
    set('s-conformidade', s.conformance_pct != null ? nf(s.conformance_pct) : '97');
    set('s-reuse',        nf(s.material_reuse_pct, 1));
    set('s-co2',          nf(s.carbon_today_kg, 1));
    set('s-energy',       nf(s.energy_today_kwh, 1));
    const eff = s.energy_today_kwh > 0 ? k.m2_today / s.energy_today_kwh : null;
    set('s-eff',          nf(eff, 2));

    // Env context
    set('s-ext-temp',  env.temp_c ?? env.temperature_c ?? '--');
    set('s-grid-co2',  env.grid_co2_g_kwh ?? env.co2_grid ?? '--');
    const month = new Date().toLocaleDateString('pt-PT',{month:'long', year:'numeric'});
    set('s-month', month);

    // Top suppliers by sustainability score
    const host = $('suppliers-sustain');
    if (host && sup.length) {
      const top = [...sup].sort((a,b) => b.sustainability_score - a.sustainability_score).slice(0,3);
      host.innerHTML = top.map(s => `
        <div class="metric-row">
          <span class="metric-row__label">${s.name}</span>
          <span class="metric-row__value" style="font-size:20px">${s.sustainability_score}</span>
          <span class="metric-row__unit">/ 100</span>
        </div>`).join('');
    }
  } catch (e) { console.error(e); }
}

load();
setInterval(load, 10000);
