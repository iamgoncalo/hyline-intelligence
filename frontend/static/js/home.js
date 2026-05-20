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

// ── Build factory twin SVG ────────────────────────────────────────
function buildTwin() {
  const host = $('twin-host');
  if (!host || !window.FACTORY_CONFIG) return;
  const f  = window.FACTORY_CONFIG;
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

  const corridors = (f.corridors || []).map(c =>
    `<rect class="corridor-rect" x="${c.x}" y="${c.y}" width="${c.w}" height="${c.h}" rx="2"/>`
  ).join('');

  const crosswalks = (f.crosswalks || []).map(c =>
    `<rect class="crosswalk-rect" x="${c.x}" y="${c.y}" width="${c.w}" height="${c.h}"/>`
  ).join('');

  const stations = (window.STATIONS_CFG || []).map(s => {
    const live = snapById[s.id] || {};
    const kind = s.kind;
    let cls = 'station-rect';
    if      (kind === 'buffer')   cls += ' is-buffer';
    else if (kind === 'storage')  cls += ' is-storage';
    else if (kind === 'dispatch') cls += ' is-dispatch';
    else {
      const st = live.status || 'idle';
      cls += ' is-' + st;
    }
    if (selectedStation === s.id) cls += ' is-selected';

    const cx = s.x + s.w / 2, cy = s.y + s.h / 2;
    const isProd = s.target_m2_per_hour > 0;
    const fBadge = (isProd && live.afi_F != null)
      ? `<text class="station-metric" x="${cx}" y="${cy + 14}" style="font-weight:600">${Math.round(live.afi_F * 100)}%</text>` : '';
    const perfBar = (isProd && live.afi_F != null && s.w > 60)
      ? `<rect class="station-perf-bar" x="${s.x+2}" y="${s.y+s.h-5}" width="${Math.max(2,(s.w-4)*live.afi_F)}" height="3" rx="1.5"/>` : '';
    const statusDot = (isProd && live.status && live.status !== 'idle')
      ? `<circle class="status-dot" cx="${s.x+s.w-10}" cy="${s.y+10}" r="4"
           fill="${live.status==='green'?'#6FAF82':live.status==='amber'?'#D97706':'#B91C1C'}"/>` : '';
    return `<g data-sid="${s.id}" style="cursor:pointer">
      <rect class="${cls}" x="${s.x}" y="${s.y}" width="${s.w}" height="${s.h}" rx="3" data-sid="${s.id}"/>
      <text class="station-label" x="${cx}" y="${cy - 2}">${s.name}</text>
      ${fBadge}${perfBar}${statusDot}
    </g>`;
  }).join('');

  const fids = (f.fiducials || []).map(fd =>
    `<g><rect class="fiducial" x="${fd.x}" y="${fd.y}" width="10" height="10"/>
     <rect class="fiducial-in" x="${fd.x+1}" y="${fd.y+1}" width="4" height="4"/>
     <rect class="fiducial-in" x="${fd.x+5}" y="${fd.y+5}" width="4" height="4"/></g>`
  ).join('');

  const sectors = `
    <text class="sector-label" x="85"  y="${vh-14}">Pre-Producao</text>
    <text class="sector-label" x="305" y="${vh-14}">Serie de Correr</text>
    <text class="sector-label" x="565" y="${vh-14}">Serie de Abrir</text>
    <text class="sector-label" x="855" y="${vh-14}">Expedicao</text>`;

  host.innerHTML = `<svg class="twin-svg" viewBox="0 0 ${vw} ${vh}" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid meet">
    ${defs}${floor}${corridors}${crosswalks}
    <g id="flow-particles"></g>
    ${stations}${fids}${sectors}
  </svg>`;

  // Click handlers
  host.querySelectorAll('[data-sid]').forEach(el => {
    el.addEventListener('click', () => {
      selectedStation = el.dataset.sid;
      buildTwin();
    });
  });

  startParticles(host);
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
