/* home.js — homepage: factory twin + live events + kpi fetch */
'use strict';

const $ = id => document.getElementById(id);
const $q = s  => document.querySelector(s);
const fetchJSON = async (url, opts) => { const r = await fetch(url, opts); if (!r.ok) throw new Error(r.status); return r.json(); };
const nf = (v, d=1) => v == null ? '--' : Number(v).toLocaleString('pt-PT', {minimumFractionDigits:d, maximumFractionDigits:d});

// Key data available as globals injected by template:
// window.FACTORY_CONFIG — factory layout (corridors, crosswalks, fiducials, viewbox_width/height)
// window.STATIONS_CFG   — array of station configs (id, name, sector, x, y, w, h, kind, target_m2_per_hour)
// window.MEMBERS_CFG    — array of members

// ── Station live data (refreshed from /api/stations) ─────────────
let stationsLive = [];
let selectedStation = null;

// ── Twin mode state ───────────────────────────────────────────────
let _twinMode = 'mapa';

const TwinMode = {
  set(btn, mode) {
    _twinMode = mode;
    document.querySelectorAll('.twin-mode-btn').forEach(b => b.classList.remove('is-active'));
    btn.classList.add('is-active');
    buildTwin();
  }
};

// ── Build factory twin SVG (dispatcher) ──────────────────────────
function buildTwin() {
  if (_twinMode === 'mapa')     buildTwinMapa();
  else if (_twinMode === 'calor')    buildTwinCalor();
  else if (_twinMode === 'fluxo')    buildTwinFluxo();
  else if (_twinMode === 'metricas') buildTwinMetricas();
}

function buildTwinMapa() {
  const host = $('twin-host');
  if (!host || !window.FACTORY_CONFIG) return;
  const f = window.FACTORY_CONFIG;
  const vw = f.viewbox_width, vh = f.viewbox_height;
  const snapById = Object.fromEntries(stationsLive.map(s => [s.id, s]));

  const defs = `<defs>
    <linearGradient id="grad-green" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#CFEAD9" stop-opacity="0.92"/>
      <stop offset="100%" stop-color="#A6D5B7" stop-opacity="0.75"/>
    </linearGradient>
    <linearGradient id="grad-amber" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#FBD9A0" stop-opacity="0.85"/>
      <stop offset="100%" stop-color="#F3B870" stop-opacity="0.7"/>
    </linearGradient>
    <linearGradient id="grad-red" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#F6B5B5" stop-opacity="0.85"/>
      <stop offset="100%" stop-color="#E28B8B" stop-opacity="0.7"/>
    </linearGradient>
  </defs>`;

  const floor = `<rect class="floor-bg" x="0" y="0" width="${vw}" height="${vh}" rx="4"/>`;
  const corridors = (f.corridors||[]).map(c => `<rect class="corridor-rect" x="${c.x}" y="${c.y}" width="${c.w}" height="${c.h}" rx="2"/>`).join('');
  const crosswalks = (f.crosswalks||[]).map(c => `<rect class="crosswalk-rect" x="${c.x}" y="${c.y}" width="${c.w}" height="${c.h}"/>`).join('');

  const stations = (window.STATIONS_CFG||[]).map(s => {
    const live = snapById[s.id] || {};
    const kind = s.kind;
    let cls = 'station-rect';
    if (kind === 'buffer') cls += ' is-buffer';
    else if (kind === 'storage') cls += ' is-storage';
    else if (kind === 'dispatch') cls += ' is-dispatch';
    else cls += ' is-' + (live.status || 'idle');
    if (selectedStation === s.id) cls += ' is-selected';
    const cx = s.x + s.w/2, cy = s.y + s.h/2;
    const isProd = s.target_m2_per_hour > 0;
    const fBadge = (isProd && live.afi_F != null) ? `<text class="station-metric" x="${cx}" y="${cy+14}" style="font-weight:600">${Math.round(live.afi_F*100)}%</text>` : '';
    const perfBar = (isProd && live.afi_F != null && s.w > 60) ? `<rect class="station-perf-bar" x="${s.x+2}" y="${s.y+s.h-5}" width="${Math.max(2,(s.w-4)*live.afi_F)}" height="3" rx="1.5"/>` : '';
    const statusDot = (isProd && live.status && live.status !== 'idle') ? `<circle class="status-dot" cx="${s.x+s.w-10}" cy="${s.y+10}" r="4" fill="${live.status==='green'?'#6FAF82':live.status==='amber'?'#D97706':'#B91C1C'}"/>` : '';
    return `<g data-sid="${s.id}" class="station-group" style="cursor:pointer">
      <rect class="${cls}" x="${s.x}" y="${s.y}" width="${s.w}" height="${s.h}" rx="3" data-sid="${s.id}"/>
      <text class="station-label" x="${cx}" y="${cy-2}">${s.name}</text>
      ${fBadge}${perfBar}${statusDot}
    </g>`;
  }).join('');

  const fids = (f.fiducials||[]).map(fd => `<g><rect class="fiducial" x="${fd.x}" y="${fd.y}" width="10" height="10"/><rect class="fiducial-in" x="${fd.x+1}" y="${fd.y+1}" width="4" height="4"/><rect class="fiducial-in" x="${fd.x+5}" y="${fd.y+5}" width="4" height="4"/></g>`).join('');
  const sectors = `<text class="sector-label" x="85" y="${vh-14}">Pre-Producao</text><text class="sector-label" x="305" y="${vh-14}">Serie de Correr</text><text class="sector-label" x="565" y="${vh-14}">Serie de Abrir</text><text class="sector-label" x="855" y="${vh-14}">Expedicao</text>`;

  host.innerHTML = `<svg class="twin-svg" viewBox="0 0 ${vw} ${vh}" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid meet">
    ${defs}${floor}${corridors}${crosswalks}
    <g id="flow-particles"></g>
    ${stations}${fids}${sectors}
  </svg>`;

  // Click handlers + tooltip
  const tooltip = $('twin-tooltip');
  host.querySelectorAll('.station-group').forEach(g => {
    g.addEventListener('click', () => { selectedStation = g.dataset.sid; buildTwin(); });
    g.addEventListener('mousemove', (e) => {
      if (!tooltip) return;
      const sid = g.dataset.sid;
      const s = stationsLive.find(x => x.id === sid) || (window.STATIONS_CFG||[]).find(x => x.id === sid) || {};
      const sc = (window.STATIONS_CFG||[]).find(x => x.id === sid) || {};
      tooltip.innerHTML = `<strong style="color:var(--primary)">${sc.name||sid}</strong><br>
        Desempenho: ${s.afi_F != null ? Math.round(s.afi_F*100)+'%' : '--'}<br>
        Producao: ${(s.m2_per_hour||0).toFixed(1)} / ${sc.target_m2_per_hour||'--'} m²/h<br>
        Estado: ${s.status||'idle'}`;
      tooltip.style.display = 'block';
      tooltip.style.left = (e.clientX + 12) + 'px';
      tooltip.style.top  = (e.clientY - 10) + 'px';
    });
    g.addEventListener('mouseleave', () => { if (tooltip) tooltip.style.display = 'none'; });
  });
  startParticles(host);
}

function buildTwinCalor() {
  const host = $('twin-host');
  if (!host || !window.FACTORY_CONFIG) return;
  const f = window.FACTORY_CONFIG;
  const vw = f.viewbox_width, vh = f.viewbox_height;
  const snapById = Object.fromEntries(stationsLive.map(s => [s.id, s]));
  const perfColor = p => `hsl(${Math.round(p * 135)}, 65%, 32%)`;

  const floor = `<rect class="floor-bg" x="0" y="0" width="${vw}" height="${vh}" rx="4"/>`;
  const corridors = (f.corridors||[]).map(c => `<rect class="corridor-rect" x="${c.x}" y="${c.y}" width="${c.w}" height="${c.h}" rx="2"/>`).join('');

  const stations = (window.STATIONS_CFG||[]).map(s => {
    const live = snapById[s.id] || {};
    const isProd = s.target_m2_per_hour > 0;
    if (!isProd) return `<rect x="${s.x}" y="${s.y}" width="${s.w}" height="${s.h}" rx="3" fill="var(--surface-soft)" stroke="var(--hairline)" stroke-width="0.5" opacity="0.5"/>`;
    const perf = live.afi_F != null ? live.afi_F : 0.5;
    return `<g title="${s.name}: ${Math.round(perf*100)}%">
      <rect x="${s.x}" y="${s.y}" width="${s.w}" height="${s.h}" rx="3" fill="${perfColor(perf)}"/>
    </g>`;
  }).join('');

  // Gradient legend
  const lx = Math.round(vw*0.2), lw = Math.round(vw*0.6);
  const legend = `
    <defs><linearGradient id="heatGrad" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="hsl(0,65%,32%)"/>
      <stop offset="50%" stop-color="hsl(67,65%,32%)"/>
      <stop offset="100%" stop-color="hsl(135,65%,32%)"/>
    </linearGradient></defs>
    <rect x="${lx}" y="${vh-22}" width="${lw}" height="8" rx="4" fill="url(#heatGrad)"/>
    <text x="${lx}" y="${vh-6}" font-family="DM Mono" font-size="9" fill="rgba(27,58,33,0.5)">0%</text>
    <text x="${lx+lw/2}" y="${vh-6}" text-anchor="middle" font-family="DM Mono" font-size="9" fill="rgba(27,58,33,0.5)">50%</text>
    <text x="${lx+lw}" y="${vh-6}" text-anchor="end" font-family="DM Mono" font-size="9" fill="rgba(27,58,33,0.5)">100% Desempenho</text>`;

  host.innerHTML = `<svg class="twin-svg" viewBox="0 0 ${vw} ${vh}" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid meet">
    ${legend}${floor}${corridors}${stations}
  </svg>`;
}

function buildTwinFluxo() {
  const host = $('twin-host');
  if (!host || !window.FACTORY_CONFIG) return;
  const f = window.FACTORY_CONFIG;
  const vw = f.viewbox_width, vh = f.viewbox_height;
  const snapById = Object.fromEntries(stationsLive.map(s => [s.id, s]));

  const floor = `<rect class="floor-bg" x="0" y="0" width="${vw}" height="${vh}" rx="4"/>`;
  const corridors = (f.corridors||[]).map(c => `<rect class="corridor-rect" x="${c.x}" y="${c.y}" width="${c.w}" height="${c.h}" rx="2"/>`).join('');

  // Stations as circles with labels
  const stations = (window.STATIONS_CFG||[]).map(s => {
    const live = snapById[s.id] || {};
    const cx = s.x + s.w/2, cy = s.y + s.h/2;
    const r = Math.min(s.w, s.h) / 2 - 2;
    const isProd = s.target_m2_per_hour > 0;
    const status = isProd ? (live.status || 'idle') : 'idle';
    const fill = status === 'green' ? '#6FAF82' : status === 'amber' ? '#D97706' : status === 'red' ? '#B91C1C' : 'rgba(27,58,33,0.15)';
    const label = s.name.length > 10 ? s.name.slice(0,10) + '...' : s.name;
    return `<g>
      <circle cx="${cx}" cy="${cy}" r="${Math.max(r,8)}" fill="${fill}" opacity="0.85" stroke="#fff" stroke-width="1.5"/>
      <text x="${cx}" y="${cy+4}" text-anchor="middle" font-family="DM Mono" font-size="8" fill="#fff">${Math.round((live.afi_F||0)*100)}%</text>
      <text x="${cx}" y="${cy+Math.max(r,8)+12}" text-anchor="middle" font-family="DM Mono" font-size="8" fill="rgba(27,58,33,0.6)">${label}</text>
    </g>`;
  }).join('');

  host.innerHTML = `<svg class="twin-svg" viewBox="0 0 ${vw} ${vh}" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid meet">
    ${floor}${corridors}${stations}
    <g id="flow-particles"></g>
  </svg>`;
  startParticles(host);
}

function buildTwinMetricas() {
  const host = $('twin-host');
  if (!host) return;
  if (_animHandle) { cancelAnimationFrame(_animHandle); _animHandle = null; }

  const snapById = Object.fromEntries(stationsLive.map(s => [s.id, s]));
  const productive = (window.STATIONS_CFG||[]).filter(s => s.target_m2_per_hour > 0);
  const sorted = productive.map(s => ({...s, ...snapById[s.id]})).sort((a, b) => (a.afi_F||1) - (b.afi_F||1));

  host.innerHTML = `<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;height:100%;overflow-y:auto;align-content:start;padding:4px;">
    ${sorted.map(s => {
      const perf = s.afi_F != null ? Math.round(s.afi_F * 100) : '--';
      const status = s.status || 'idle';
      const borderColor = status === 'green' ? 'var(--tertiary)' : status === 'amber' ? 'var(--amber)' : status === 'red' ? 'var(--red)' : 'var(--hairline)';
      const trend = s.afi_F > 0.9 ? '↑' : s.afi_F > 0.7 ? '→' : '↓';
      return `<div style="border:1px solid var(--hairline);border-left:3px solid ${borderColor};border-radius:10px;padding:10px 12px;background:#fff;">
        <div style="font-size:9px;color:var(--ink-hint);text-transform:uppercase;letter-spacing:0.06em;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${s.name}</div>
        <div style="font-family:'DM Mono',monospace;font-size:24px;color:var(--primary);margin-top:2px;line-height:1;">${perf}%</div>
        <div style="font-size:10px;color:var(--ink-hint);margin-top:2px;">${(s.m2_per_hour||0).toFixed(1)} / ${s.target_m2_per_hour||'--'} m²/h ${trend}</div>
      </div>`;
    }).join('')}
  </div>`;
}

// ── Flow particles ────────────────────────────────────────────────
let _animHandle = null;
const PATHS = [
  {from:[20,30],  to:[960,30],  dur:8000},
  {from:[177,70], to:[177,790], dur:6000},
  {from:[422,70], to:[422,940], dur:7000},
  {from:[20,490], to:[177,490], dur:3000},
  {from:[950,70], to:[950,790], dur:7500},
];

function startParticles(host) {
  if (_animHandle) cancelAnimationFrame(_animHandle);
  const gEl = host.querySelector('#flow-particles');
  if (!gEl) return;
  const ns = 'http://www.w3.org/2000/svg';
  const particles = PATHS.map((p,i) => {
    const c = document.createElementNS(ns, 'circle');
    c.setAttribute('class','flow-particle');
    c.setAttribute('r','4');
    gEl.appendChild(c);
    return { el:c, ...p, offset: i * (p.dur / PATHS.length) };
  });
  function tick(t) {
    particles.forEach(pt => {
      const prog = ((t + pt.offset) % pt.dur) / pt.dur;
      const x = pt.from[0] + (pt.to[0]-pt.from[0]) * prog;
      const y = pt.from[1] + (pt.to[1]-pt.from[1]) * prog;
      pt.el.setAttribute('cx', x);
      pt.el.setAttribute('cy', y);
    });
    _animHandle = requestAnimationFrame(tick);
  }
  _animHandle = requestAnimationFrame(tick);
}

// ── Refresh station data ──────────────────────────────────────────
async function refreshStations() {
  try {
    stationsLive = await fetchJSON('/api/stations');
    buildTwin();
  } catch {}
}

// ── Refresh KPIs ──────────────────────────────────────────────────
async function refreshKPIs() {
  try {
    const k = await fetchJSON('/api/kpi');
    const set = (id, val) => { const el = $(id); if (el) el.textContent = val; };
    set('k-perf', k.performance_pct != null ? Math.round(k.performance_pct) : '--');
    set('k-export', k.orders_export_pct != null ? Math.round(k.orders_export_pct) : '--');
    set('k-quality', k.non_conformity_pct != null ? (100 - k.non_conformity_pct).toFixed(1) : '--');
    const carteira = $('k-carteira');
    if (carteira && k.orders_value_eur != null) {
      const m = k.orders_value_eur / 1_000_000;
      carteira.textContent = m >= 1
        ? `${m.toFixed(1)}M EUR`
        : `${Math.round(k.orders_value_eur / 1000)}k EUR`;
    }
    const alertsEl = $('k-alerts');
    if (alertsEl) {
      alertsEl.style.color = (k.alerts_open || 0) > 0 ? 'var(--red)' : 'var(--tertiary)';
    }
    // Mini alert summary
    const alertSummary = $('home-alert-summary');
    if (alertSummary) {
      const open = k.alerts_open || 0;
      alertSummary.style.display = 'block';
      if (open > 0) {
        alertSummary.style.background = 'rgba(192,57,43,0.07)';
        alertSummary.style.color = 'var(--red)';
        alertSummary.style.border = '1px solid rgba(192,57,43,0.15)';
        alertSummary.textContent = `${open} alert${open!==1?'as':'a'} em curso`;
      } else {
        alertSummary.style.background = 'rgba(111,175,130,0.1)';
        alertSummary.style.color = 'var(--secondary)';
        alertSummary.style.border = '1px solid rgba(111,175,130,0.2)';
        alertSummary.textContent = 'Sem alertas activos';
      }
    }
  } catch {}
}

// ── Events feed ────────────────────────────────────────────────────
async function refreshEvents() {
  try {
    const events = await fetchJSON('/api/events?limit=30');
    const list = $('events-list');
    if (!list) return;
    list.innerHTML = events.map(e => {
      const ts = e.ts ? e.ts.slice(11,16) : '--:--';
      const cls = e.status || 'completed';
      const m2  = e.area_m2 ? Number(e.area_m2).toFixed(2) : '--';
      return `<div class="event-item">
        <span class="event-dot ${cls}"></span>
        <span class="event-time">${ts}</span>
        <span class="event-text">${e.station_name || '--'} · ${m2} m²</span>
      </div>`;
    }).join('');
  } catch {}
}

// ── Product mix chart ─────────────────────────────────────────────
async function refreshProductMix() {
  try {
    const mix = await fetchJSON('/api/production/mix');
    const host = $('product-mix-chart');
    if (!host || !mix.length) return;
    const maxM2 = Math.max(...mix.map(m => m.m2_today), 0.1);
    host.innerHTML = mix.map(m => `
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
        <span style="font-size:10px;color:var(--ink-hint);width:64px;flex-shrink:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${m.product_line}</span>
        <div style="flex:1;height:6px;background:var(--surface-soft);border-radius:3px;overflow:hidden;">
          <div style="width:${(m.m2_today/maxM2*100).toFixed(1)}%;height:100%;background:var(--tertiary);border-radius:3px;transition:width 0.4s;"></div>
        </div>
        <span style="font-family:'DM Mono',monospace;font-size:10px;color:var(--ink-hint);flex-shrink:0;">${m.m2_today}m²</span>
      </div>`).join('');
  } catch {}
}

// ── Homepage left column clock ──────────────────────────────────
function tickHomeClock() {
  const now = new Date();
  const clockEl = $('home-clock');
  if (clockEl) clockEl.textContent = now.toLocaleTimeString('pt-PT', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
  const shiftEl = $('home-shift');
  if (shiftEl) {
    const h = now.getHours();
    shiftEl.textContent = h >= 7 && h < 15 ? 'Turno da Manha · 07:00–15:00' :
                          h >= 15 && h < 23 ? 'Turno da Tarde · 15:00–23:00' :
                          'Turno da Noite · 23:00–07:00';
  }
  const dateEl = $('home-date');
  if (dateEl) dateEl.textContent = now.toLocaleDateString('pt-PT', {weekday:'long', day:'numeric', month:'long'});
}
setInterval(tickHomeClock, 1000);
tickHomeClock();

// ── Init ────────────────────────────────────────────────────────────
refreshStations();
refreshKPIs();
refreshEvents();
refreshProductMix();
setInterval(refreshStations, 2000);
setInterval(refreshKPIs, 5000);
setInterval(refreshEvents, 2000);
setInterval(refreshProductMix, 5000);

// Also listen for live WS updates to refresh station colours
document.addEventListener('live', () => { refreshStations(); });
