/* ══════════════════════════════════════════════════════════════════
 * HYLINE · app.js · v3 · live + connected + WOW
 * ══════════════════════════════════════════════════════════════════ */

const App = (() => {
  const INIT = JSON.parse(document.getElementById('initial-data').textContent);
  const REFRESH_MS = (INIT.refresh_seconds || 10) * 1000;

  // Live state
  let stationsLive = [];
  let alertsLive   = [];
  let ordersLive   = [];
  let kpiLive      = null;
  let selectedStationId = null;
  let selectedOrderId   = null;
  let tweenValues = {};
  let m2Rate = 0;
  let chartTrends = null;

  // Procurement state
  let procActiveCat = '';
  let procEcoOnly   = false;

  // Chat state
  const __chat = { currentConvId: null, conversations: [] };

  // ── Utils ───────────────────────────────────────────────────
  const $  = (s, el=document) => el.querySelector(s);
  const $$ = (s, el=document) => Array.from(el.querySelectorAll(s));
  const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
  const nf = (v, d=1) => (v == null ? '—' : Number(v).toLocaleString('pt-PT', { minimumFractionDigits: d, maximumFractionDigits: d }));
  const f3 = v => (v == null ? '—' : Number(v).toFixed(3));
  const f2 = v => (v == null ? '—' : Number(v).toFixed(2));
  const fetchJSON = async (url, opts) => {
    const r = await fetch(url, opts);
    if (!r.ok) throw new Error(`${url} → ${r.status}`);
    return r.json();
  };

  // Number tween — animates a text element's value smoothly
  function tweenNumber(elId, target, decimals = 1, duration = 800){
    const node = $('#' + elId);
    if (!node) return;
    const start = tweenValues[elId] != null ? tweenValues[elId] : (parseFloat(node.textContent.replace(',','.')) || 0);
    if (!Number.isFinite(start) || !Number.isFinite(target)){ node.textContent = nf(target, decimals); tweenValues[elId] = target; return; }
    const t0 = performance.now();
    function step(t){
      const p = Math.min(1, (t - t0) / duration);
      const e = 1 - Math.pow(1 - p, 3); // ease-out-cubic
      const v = start + (target - start) * e;
      node.textContent = nf(v, decimals);
      if (p < 1) requestAnimationFrame(step);
      else tweenValues[elId] = target;
    }
    requestAnimationFrame(step);
  }

  // ── Navigation ─────────────────────────────────────────────
  function switchView(name){
    $$('.nav__item').forEach(b => b.classList.toggle('is-active', b.dataset.view === name));
    $$('.view').forEach(v => v.classList.toggle('is-active', v.dataset.view === name));
    const titles = {
      home:          ['Homepage','Produção'],
      alerts:        ['Alertas','Monitorização'],
      action:        ['Ação','4 Agentes'],
      scale:         ['Escala','Mercado & Estratégia'],
      procurement:   ['Procurement','Catálogo Sustentável'],
      sustain:       ['Sustentabilidade','Circularidade'],
      conversations: ['Conversas','Histórico do Assistente'],
      settings:      ['Definições','Equipa & Parâmetros'],
    }[name] || ['—','—'];
    $('#view-title').innerHTML = `${titles[0]} <span>·</span> ${titles[1]}`;
    if (name === 'scale')         renderTrendsChart();
    if (name === 'settings')      { renderConnections(); renderArchitecture(); renderExport(); }
    if (name === 'procurement')   renderProcurement();
    if (name === 'conversations') loadConversations();
  }

  // ── Clock + live m² ticker (runs every second) ────────────
  function tickClock(){
    const now = new Date();
    $('#clock').textContent = now.toLocaleTimeString('pt-PT', { hour:'2-digit', minute:'2-digit', second:'2-digit' });
    // Tick the m² value up at the estimated production rate
    if (kpiLive && m2Rate > 0){
      const prev = tweenValues['k-m2'] != null ? tweenValues['k-m2'] : kpiLive.m2_today;
      const next = prev + m2Rate;
      tweenValues['k-m2'] = next;
      const node = $('#k-m2');
      if (node) node.textContent = nf(next, 1);
    }
  }

  // ══════════════════════════════════════════════════════════
  // DIGITAL TWIN
  // ══════════════════════════════════════════════════════════
  function buildTwinSVG(hostEl){
    const f = INIT.factory;
    const vbw = f.viewbox_width, vbh = f.viewbox_height;
    const snapById = Object.fromEntries(stationsLive.map(s => [s.id, s]));

    // Defs: gradient fills for station statuses
    const defs = `
      <defs>
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
        <filter id="sh" x="-20%" y="-20%" width="140%" height="140%">
          <feDropShadow dx="0" dy="1" stdDeviation="1.5" flood-color="#1B3A21" flood-opacity="0.12"/>
        </filter>
      </defs>
    `;

    // Floor background with subtle grid
    const floor = `<rect class="floor-bg" x="0" y="0" width="${vbw}" height="${vbh}" rx="4"/>`;

    // Corridors
    const corridors = f.corridors.map(c =>
      `<rect class="corridor-rect" x="${c.x}" y="${c.y}" width="${c.w}" height="${c.h}" rx="2"/>`
    ).join('');
    const crosswalks = f.crosswalks.map(c =>
      `<rect class="crosswalk-rect" x="${c.x}" y="${c.y}" width="${c.w}" height="${c.h}"/>`
    ).join('');

    // Stations
    const stations = INIT.stations.map(s => {
      const live = snapById[s.id] || {};
      const kind = s.kind;
      let cls = 'station-rect';
      if (kind === 'buffer')        cls += ' is-buffer';
      else if (kind === 'storage')  cls += ' is-storage';
      else if (kind === 'dispatch') cls += ' is-dispatch';
      else {
        const st = live.status || 'idle';
        cls += ' is-' + st;
      }
      if (selectedStationId === s.id) cls += ' is-selected';

      const cx = s.x + s.w / 2;
      const cy = s.y + s.h / 2;
      const isProd = s.target_m2_per_hour > 0;
      const showMetric = isProd && live.m2_per_hour != null;
      const metric = showMetric
        ? `<text class="station-metric" x="${cx}" y="${cy + 10}">${nf(live.m2_per_hour, 2)}/${nf(s.target_m2_per_hour, 1)} m²/h</text>`
        : '';
      const fBadge = (isProd && live.afi_F != null)
        ? `<text class="station-metric" x="${cx}" y="${cy + 22}" style="font-weight:600">${Math.round(live.afi_F * 100)}%</text>`
        : '';
      const perfBar = (isProd && live.afi_F != null && s.w > 60)
        ? `<rect class="station-perf-bar" x="${s.x + 2}" y="${s.y + s.h - 5}" width="${Math.max(2, (s.w - 4) * live.afi_F)}" height="3" rx="1.5"/>`
        : '';
      // Breathing dot for active stations
      const statusDot = (isProd && live.status && live.status !== 'idle')
        ? `<circle class="status-dot" cx="${s.x + s.w - 10}" cy="${s.y + 10}" r="4"
            fill="${live.status === 'green' ? '#6FAF82' : live.status === 'amber' ? '#D97706' : '#B91C1C'}"/>`
        : '';
      return `
        <g data-station="${s.id}">
          <rect class="${cls}" x="${s.x}" y="${s.y}" width="${s.w}" height="${s.h}" rx="3"
                data-sid="${s.id}"/>
          <text class="station-label" x="${cx}" y="${cy - 4}">${s.name}</text>
          ${metric}
          ${fBadge}
          ${perfBar}
          ${statusDot}
        </g>`;
    }).join('');

    // Fiducials
    const fids = f.fiducials.map(fd => `
      <g>
        <rect class="fiducial" x="${fd.x}" y="${fd.y}" width="10" height="10"/>
        <rect class="fiducial-in" x="${fd.x+1}" y="${fd.y+1}" width="4" height="4"/>
        <rect class="fiducial-in" x="${fd.x+5}" y="${fd.y+5}" width="4" height="4"/>
      </g>`).join('');

    // Sector labels
    const sectors = `
      <text class="sector-label" x="85"  y="${vbh - 14}">Pré-Produção</text>
      <text class="sector-label" x="305" y="${vbh - 14}">Série de Correr</text>
      <text class="sector-label" x="565" y="${vbh - 14}">Série de Abrir</text>
      <text class="sector-label" x="855" y="${vbh - 14}">Expedição</text>
    `;

    // Flow particles (group for animation)
    const particles = `<g id="flow-particles"></g>`;

    hostEl.innerHTML = `
<svg class="twin-svg" viewBox="0 0 ${vbw} ${vbh}" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid meet">
  ${defs}
  ${floor}
  ${corridors}
  ${crosswalks}
  ${particles}
  ${stations}
  ${fids}
  ${sectors}
</svg>`;

    // Attach click handlers
    $$('[data-sid]', hostEl).forEach(rect => {
      rect.addEventListener('click', () => selectStation(rect.dataset.sid));
    });

    startFlowAnimation();
  }

  // Flow particles — travel along corridors, feels like material moving
  let flowAnimHandle = null;
  const FLOW_PATHS = [
    // [startX, startY, endX, endY, duration_ms]
    // corridor top (west to east)
    { from: [20, 30],  to: [960, 30],  dur: 8000 },
    // corridor west (top to bottom)
    { from: [177, 70], to: [177, 790], dur: 6000 },
    // corridor center
    { from: [422, 70], to: [422, 940], dur: 7000 },
    // corridor east
    { from: [712, 70], to: [712, 940], dur: 7500 },
    // extra short flows (into stations)
    { from: [200, 320], to: [200, 610], dur: 4000 },
    { from: [495, 280], to: [495, 490], dur: 3500 },
  ];
  function startFlowAnimation(){
    if (flowAnimHandle) cancelAnimationFrame(flowAnimHandle);
    const host = $('#flow-particles');
    if (!host) return;
    host.innerHTML = '';
    const particles = FLOW_PATHS.map((p, i) => {
      const c = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      c.setAttribute('class', 'flow-particle');
      c.setAttribute('r', 2.8);
      c.setAttribute('cx', p.from[0]);
      c.setAttribute('cy', p.from[1]);
      host.appendChild(c);
      return { node: c, path: p, offset: (i / FLOW_PATHS.length) };
    });
    const t0 = performance.now();
    function tick(t){
      particles.forEach(pt => {
        const elapsed = (t - t0) + pt.offset * pt.path.dur;
        const p = ((elapsed % pt.path.dur) / pt.path.dur);
        const x = pt.path.from[0] + (pt.path.to[0] - pt.path.from[0]) * p;
        const y = pt.path.from[1] + (pt.path.to[1] - pt.path.from[1]) * p;
        pt.node.setAttribute('cx', x);
        pt.node.setAttribute('cy', y);
        pt.node.setAttribute('opacity', 0.4 + 0.6 * Math.sin(p * Math.PI));
      });
      flowAnimHandle = requestAnimationFrame(tick);
    }
    flowAnimHandle = requestAnimationFrame(tick);
  }

  // ══════════════════════════════════════════════════════════
  // STATION SELECTION / DETAIL DRAWER
  // ══════════════════════════════════════════════════════════
  function selectStation(id){
    selectedStationId = id;
    const s = stationsLive.find(x => x.id === id) || INIT.stations.find(x => x.id === id);
    if (!s) return;
    const live = stationsLive.find(x => x.id === id) || {};

    // Update SVG highlight
    $$('.twin .station-rect').forEach(r => r.classList.toggle('is-selected', r.dataset.sid === id));

    // Populate drawer
    $('#d-sector').textContent = (s.sector || '').toUpperCase();
    $('#d-title').textContent  = s.name;
    $('#d-meta').textContent   = s.target_m2_per_hour > 0
      ? `Target ${nf(s.target_m2_per_hour, 1)} m²/h · eficiência actual ${nf((live.efficiency||0)*100, 0)}% · ${live.windows_in_progress||0} em curso`
      : `Zona estrutural · ${s.kind}`;

    $('#d-f').textContent = live.afi_F != null ? `${Math.round(live.afi_F * 100)}%` : '—';

    const attr = live.afi_D_attribution || {};
    const keys = ['throughput','quality','machine','timeline','operator','setup'];
    const factorName = {
      throughput: 'cadência',
      quality:    'qualidade',
      machine:    'equipamento',
      timeline:   'prazo',
      operator:   'operador',
      setup:      'setup',
    };
    $('#d-bars').innerHTML = keys.map(k => {
      const v = attr[k] || 0;
      return `<div class="detail__bar-row">
        <span>${factorName[k]}</span>
        <span class="detail__bar-track"><span class="detail__bar-fill" style="width:${Math.min(100,v)}%"></span></span>
        <span style="text-align:right">${Math.round(v)}%</span>
      </div>`;
    }).join('');

    // Operators
    const ops = (live.operators || []).length > 0 ? live.operators : (INIT.members.filter(m => m.station_assigned === id));
    $('#d-ops').innerHTML = ops.length
      ? ops.map(o => `<div class="detail__op">
            <div class="detail__op-avatar">${o.initials || (o.name||'').split(' ').map(x=>x[0]).slice(0,2).join('')}</div>
            <div><div style="font-size:12.5px; font-weight:500">${o.name}</div><div style="font-size:10.5px; color:var(--ink-hint)">Operador</div></div>
         </div>`).join('')
      : '<div style="font-size:11.5px; color:var(--ink-hint); padding:6px 2px">Sem operador atribuído.</div>';

    // Alerts for this station
    const stationAlerts = alertsLive.filter(a => a.station_id === id);
    $('#d-alerts').innerHTML = stationAlerts.length
      ? stationAlerts.map(a => `<div class="detail__alert"><strong>${a.alert_type.toUpperCase()}</strong> · ${a.message}</div>`).join('')
      : '<div style="font-size:11.5px; color:var(--ink-hint); padding:6px 2px">Zero alertas abertos nesta estação.</div>';

    $('#detail').classList.add('is-open');
  }
  function closeDetail(){
    selectedStationId = null;
    $$('.twin .station-rect.is-selected').forEach(r => r.classList.remove('is-selected'));
    $('#detail').classList.remove('is-open');
  }

  // Highlight stations by order (click order in rail)
  function selectOrder(orderId){
    selectedOrderId = orderId;
    $$('.order').forEach(o => o.classList.toggle('is-selected', o.dataset.oid === orderId));
    // Find stations currently processing this order
    const matching = stationsLive.filter(s => s.current_order_id === orderId).map(s => s.id);
    $$('.twin .station-rect').forEach(r => {
      r.classList.remove('is-highlight');
      if (matching.includes(r.dataset.sid)) r.classList.add('is-highlight');
    });
    // auto-remove highlight after 3s
    setTimeout(() => $$('.twin .station-rect.is-highlight').forEach(r => r.classList.remove('is-highlight')), 3000);
  }

  // Highlight station via alert click
  function selectAlertStation(stationId){
    selectStation(stationId);
  }

  // ══════════════════════════════════════════════════════════
  // DATA REFRESH PIPELINE
  // ══════════════════════════════════════════════════════════
  async function refreshAll(){
    try {
      const [kpi, stations, alerts, orders] = await Promise.all([
        fetchJSON('/api/kpi'),
        fetchJSON('/api/stations'),
        fetchJSON('/api/alerts'),
        fetchJSON('/api/orders?limit=10'),
      ]);
      const prevM2 = kpiLive ? kpiLive.m2_today : null;
      kpiLive = kpi;
      stationsLive = stations;
      alertsLive = alerts;
      ordersLive = orders;

      // Estimate m² production rate per second for live ticker
      // (sum of all green/amber stations' m²/h divided by 3600)
      const totalHourly = stations.filter(s => s.target_m2_per_hour > 0).reduce((a,s) => a + (s.m2_per_hour || 0), 0);
      m2Rate = totalHourly / 3600;

      // Tween KPI numbers
      tweenNumber('k-m2', kpi.m2_today, 1);
      tweenValues['k-m2'] = kpi.m2_today;
      $('#k-m2-delta').textContent = prevM2 != null ? `+${nf(kpi.m2_today - prevM2, 1)} desde última sync` : 'a sincronizar...';
      // Desempenho as percentage
      const fPct = (kpi.afi_F_global || 0) * 100;
      tweenNumber('k-f', fPct, 1);
      $('#k-orders').textContent = kpi.open_orders;
      $('#k-backlog').textContent = `${nf(kpi.m2_backlog, 0)} m² em carteira`;
      $('#k-alerts').textContent = kpi.open_alerts;

      // Count alerts by role
      const byRole = { Director:0, HST:0, DQ:0, ChefeTurno:0 };
      alerts.forEach(a => byRole[a.routed_to] = (byRole[a.routed_to]||0) + 1);
      const parts = Object.entries(byRole).filter(([_,n]) => n > 0).map(([k,n]) => `${k} ${n}`);
      $('#k-alerts-routed').textContent = parts.length ? parts.join(' · ') : 'zero · sistema estável';

      // Station status counts for chips
      const cnt = { green:0, amber:0, red:0 };
      stations.filter(s => s.target_m2_per_hour > 0).forEach(s => { if (cnt[s.status] != null) cnt[s.status]++; });
      $('#chip-green').textContent = cnt.green;
      $('#chip-amber').textContent = cnt.amber;
      $('#chip-red').textContent = cnt.red;

      // Nav badge
      const np = $('#nav-alerts-count');
      if (kpi.open_alerts > 0){ np.style.display='inline-block'; np.textContent = kpi.open_alerts; }
      else { np.style.display='none'; }

      buildTwinSVG($('#twin-host'));
      renderLiveFeed();
      renderOrdersRail(orders);
      renderAlertsStrip(alerts);
      renderAlertsBoard(alerts);

      // If detail is open, re-populate with fresh data
      if (selectedStationId) selectStation(selectedStationId);

      $('#last-refresh').textContent = 'sincronizado';
    } catch(e){
      console.error('refreshAll falhou:', e);
      $('#last-refresh').textContent = 'erro · backend offline';
    }
  }

  // ── Rail: orders (clickable → highlights twin) ────────────
  function renderOrdersRail(orders){
    const host = $('#orders-col');
    host.innerHTML = '';
    $('#orders-total').textContent = orders.length;
    if (!orders.length){
      host.innerHTML = '<div style="padding:14px; color:var(--ink-hint); font-size:11px">Zero obras activas.</div>';
      return;
    }
    orders.forEach(o => {
      const pct = Math.round(o.progress_pct || 0);
      const daysLeft = o.deadline ? Math.ceil((new Date(o.deadline) - Date.now()) / 86400000) : null;
      const urgent = daysLeft != null && daysLeft < 7;
      const row = el('div', 'order' + (selectedOrderId === o.id ? ' is-selected' : ''));
      row.dataset.oid = o.id;
      row.innerHTML = `
        <div class="order__head">
          <span class="order__id">${o.id}</span>
          <span class="order__prio ${urgent ? 'is-urgent':''}">P${o.priority||'—'}${daysLeft!=null?` · ${daysLeft}d`:''}</span>
        </div>
        <div class="order__name">${o.customer || '—'} · ${o.total_windows} janelas</div>
        <div class="order__meta">
          <span>${nf(o.total_m2, 1)} m²</span>
          <span>${pct}%</span>
        </div>
        <div class="order__bar"><span style="width:${Math.min(pct, 100)}%"></span></div>
      `;
      row.addEventListener('click', () => selectOrder(o.id));
      host.appendChild(row);
    });
  }

  // ── Rail: alerts strip (clickable → selects station) ──────
  function renderAlertsStrip(alerts){
    const host = $('#alerts-strip');
    $('#alerts-strip-count').textContent = alerts.length;
    host.innerHTML = '';
    if (!alerts.length){
      host.innerHTML = '<div style="padding:14px; color:var(--ink-hint); font-size:11px">Zero alertas abertos.</div>';
      return;
    }
    alerts.slice(0, 6).forEach(a => {
      const sev = a.severity >= 4 ? 4 : a.severity >= 3 ? 3 : 2;
      const chip = el('div', `alert-chip alert-chip--sev${sev}`);
      chip.innerHTML = `
        <div class="alert-chip__dot"></div>
        <div class="alert-chip__body">
          <div class="alert-chip__station">${a.station_name}</div>
          <div class="alert-chip__msg">${a.message}</div>
        </div>
        <div class="alert-chip__role">${a.routed_to}</div>
      `;
      chip.addEventListener('click', () => selectAlertStation(a.station_id));
      host.appendChild(chip);
    });
  }

  // ── Alerts board (full view) ───────────────────────────────
  function renderAlertsBoard(alerts){
    const cols = { Director: $('#col-director'), HST: $('#col-hst'), DQ: $('#col-dq'), ChefeTurno: $('#col-chefe') };
    Object.values(cols).forEach(c => c && (c.innerHTML = ''));
    const counts = { Director:0, HST:0, DQ:0, ChefeTurno:0 };

    alerts.forEach(a => {
      const col = cols[a.routed_to] || cols.ChefeTurno;
      if (!col) return;
      counts[a.routed_to] = (counts[a.routed_to]||0) + 1;
      const time = new Date(a.ts).toLocaleTimeString('pt-PT', { hour:'2-digit', minute:'2-digit' });
      const card = el('div', 'alert-card');
      card.innerHTML = `
        <div class="alert-card__head">
          <div class="alert-card__station">${a.station_name}</div>
          <div class="alert-chip__dot" style="background:${a.severity >= 4 ? '#B91C1C' : a.severity >= 3 ? '#D97706' : '#6FAF82'}; width:8px; height:8px; border-radius:50%"></div>
        </div>
        <div class="alert-card__msg">${a.message}</div>
        ${a.ai_diagnosis ? `<div class="alert-card__diag">IA · ${a.ai_diagnosis}</div>` : ''}
        <div class="alert-card__foot">
          <span class="alert-card__type">${a.alert_type} · sev ${a.severity}</span>
          <span class="alert-card__meta">${time}</span>
        </div>
        <div style="margin-top:10px; display:flex; gap:6px; justify-content:flex-end">
          <button class="btn btn--ghost btn--sm" onclick="event.stopPropagation(); App.switchView('home'); setTimeout(()=>App.selectAlertStation('${a.station_id}'), 300)">Ver no Twin</button>
          <button class="btn btn--ghost btn--sm" onclick="event.stopPropagation(); App.transferAlert(${a.id}, '${a.routed_to}')">↗ Transferir</button>
          <button class="btn btn--sm" onclick="event.stopPropagation(); App.resolveAlert(${a.id}, '${a.station_name.replace(/'/g,'')}')">Resolver</button>
        </div>
      `;
      cols[a.routed_to] && cols[a.routed_to].appendChild(card);
    });

    $('#cnt-director').textContent = counts.Director;
    $('#cnt-hst').textContent = counts.HST;
    $('#cnt-dq').textContent = counts.DQ;
    $('#cnt-chefe').textContent = counts.ChefeTurno;
  }

  // ══════════════════════════════════════════════════════════
  // OTHER VIEWS
  // ══════════════════════════════════════════════════════════
  function renderAgents(){
    const host = $('#agents-bar'); if (!host) return;
    host.innerHTML = '';
    INIT.agents.forEach(a => {
      const card = el('div', 'agent');
      card.innerHTML = `
        <div class="agent__status"></div>
        <div class="agent__name">${a.name}</div>
        <div class="agent__role">${a.role}</div>
      `;
      host.appendChild(card);
    });
  }

  function renderPriorities(){
    const host = $('#priorities-list'); if (!host) return;
    host.innerHTML = '';
    INIT.priorities.forEach(p => {
      const r = el('div', 'priority');
      r.innerHTML = `
        <div>
          <div class="priority__title">${p.title}</div>
          <div class="priority__meta">horizonte ${p.horizon_months}m · ${p.id}</div>
        </div>
        <div class="priority__conf">${Math.round(p.confidence * 100)}%</div>
      `;
      host.appendChild(r);
    });
  }

  async function renderTeam(){
    try {
      const t = await fetchJSON('/api/team');
      const rolesById = Object.fromEntries(t.roles.map(r => [r.id, r]));
      const host = $('#team-list'); if (!host) return;
      host.innerHTML = '';
      t.members.forEach(m => {
        const role = rolesById[m.role] || { name: m.role, color: '#4A7C59' };
        const badgeCls = { director:'director', hst:'hst', dq:'dq', chefe:'chefe' }[m.role] || 'op';
        const row = el('div', 'team-row');
        row.innerHTML = `
          <div class="team-avatar" style="background: linear-gradient(135deg, ${role.color}, ${role.color}CC)">${m.initials}</div>
          <div>
            <div class="team-row__name">${m.name}</div>
            <div class="team-row__role">${role.name}</div>
            ${m.station_assigned ? `<div class="team-row__station">${m.station_assigned}</div>` : ''}
          </div>
          <span class="badge badge--${badgeCls}">L${role.level}</span>
        `;
        host.appendChild(row);
      });
    } catch(e) { console.error(e); }
  }

  async function renderSustain(){
    try {
      const s = await fetchJSON('/api/sustainability');
      $('#s-co2').textContent = nf(s.carbon_today_kg, 0);
      $('#s-energy').textContent = nf(s.energy_today_kwh, 0);
      $('#s-energy-coef').textContent = `coef. ${s.energy_kwh_per_m2} kWh/m²`;
      $('#s-reuse').textContent = nf(s.material_reuse_pct, 0) + '%';
      $('#s-reuse-bar').style.width = s.material_reuse_pct + '%';
      $('#s-reuse-target').textContent = s.targets.reuse_increase_pct;
      $('#s-co2-target').textContent = `meta: -${s.targets.carbon_reduction_pct}% vs baseline`;
    } catch(e) { console.error(e); }
  }

  async function refreshOptimiser(){
    try {
      const props = await fetchJSON('/api/agents/optimiser');
      const host = $('#optimiser-list'); if (!host) return;
      host.innerHTML = '';
      if (!props.length){
        host.innerHTML = '<div style="padding:18px; color:var(--ink-hint); font-size:12px">Configuração actual é óptima. Zero reatribuições sugeridas.</div>';
        return;
      }
      props.forEach(p => {
        const row = el('div', 'prop-row');
        row.innerHTML = `
          <div>
            <div class="prop-row__op">${p.operator_name}</div>
            <div class="prop-row__move">${p.from_station || '(sem estação)'} → <b>${p.to_station_name}</b></div>
          </div>
          <div style="display:flex; align-items:center">
            <span class="prop-row__f">${Math.round(p.to_station_F * 100)}%</span>
            <button class="btn btn--solid btn--sm">Aplicar</button>
          </div>`;
        row.querySelector('button').addEventListener('click', () => applyProposal(p));
        host.appendChild(row);
      });
    } catch(e) { console.error(e); }
  }

  function applyProposal(p){
    confirmDialog('Aplicar reatribuição?',
      `Mover <b>${p.operator_name}</b> de <b>${p.from_station || '(sem estação)'}</b> para <b>${p.to_station_name}</b> (desempenho ${Math.round(p.to_station_F*100)}%).<br><br>Esta acção fica no audit trail.`,
      async () => {
        await fetchJSON('/api/decisions', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({ member_id: p.operator_id, kind:'reassign_operator', target: p.to_station, payload:{from:p.from_station, to:p.to_station}, confirmed:true }),
        });
        addChatMsg(`Reatribuição aplicada · ${p.operator_name} → ${p.to_station_name}`, 'bot');
      });
  }

  // Native SVG line chart — usa nova estrutura {source, terms, suggestions}
  async function renderTrendsChart(){
    const host = $('#trends-chart'); if (!host) return;
    let data;
    try { data = await fetchJSON('/api/scale/trends'); }
    catch(e){ host.innerHTML = '<div style="padding:20px; color:var(--ink-hint)">Erro ao carregar trends.</div>'; return; }

    // Source pill
    const srcEl = $('#trends-source');
    if (srcEl){
      const labels = { google_live: '● LIGADO · Google Trends', config_fallback: '○ FALLBACK · snapshot' };
      const colors = { google_live: 'var(--tertiary)',         config_fallback: 'var(--amber)' };
      srcEl.textContent = (labels[data.source] || data.source) + ' · ' + (data.geo || '');
      srcEl.style.color = colors[data.source] || 'var(--ink-hint)';
    }

    // Render suggestions
    renderTrendsSuggestions(data.suggestions || []);

    // Chart
    const months = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'];
    const colors = ['#1B3A21','#4A7C59','#6FAF82','#AE572F'];
    const trends = data.terms || [];

    const W = 900, H = 420, PAD_L = 56, PAD_R = 24, PAD_T = 30, PAD_B = 90;
    const innerW = W - PAD_L - PAD_R;
    const innerH = H - PAD_T - PAD_B;
    if (trends.length === 0 || !trends[0].series.length){
      host.innerHTML = '<div style="padding:20px; color:var(--ink-hint)">Sem dados de trends.</div>';
      return;
    }
    const xStep = innerW / (months.length - 1);
    const yMax = 100, yMin = 0;
    const scaleY = v => PAD_T + innerH * (1 - (v - yMin) / (yMax - yMin));
    const scaleX = i => PAD_L + i * xStep;

    let svg = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg" style="font-family:'DM Mono',monospace">`;

    [0, 25, 50, 75, 100].forEach(v => {
      const y = scaleY(v);
      svg += `<line x1="${PAD_L}" y1="${y}" x2="${W - PAD_R}" y2="${y}" stroke="#E5EEE8" stroke-width="1"/>`;
      svg += `<text x="${PAD_L - 12}" y="${y + 4}" text-anchor="end" font-size="11" fill="#8FA896">${v}</text>`;
    });
    months.forEach((m, i) => {
      svg += `<text x="${scaleX(i)}" y="${H - PAD_B + 20}" text-anchor="middle" font-size="11" fill="#8FA896">${m}</text>`;
    });
    trends.forEach((t, idx) => {
      const color = colors[idx % colors.length];
      const pts = t.series.map((v, i) => `${scaleX(i)},${scaleY(v)}`).join(' ');
      const areaPath = `M ${scaleX(0)},${scaleY(0)} L ${pts.split(' ').join(' L ')} L ${scaleX(months.length-1)},${scaleY(0)} Z`;
      svg += `<path d="${areaPath}" fill="${color}" opacity="0.04"/>`;
      svg += `<polyline points="${pts}" fill="none" stroke="${color}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>`;
      t.series.forEach((v, i) => {
        svg += `<circle cx="${scaleX(i)}" cy="${scaleY(v)}" r="3" fill="#fff" stroke="${color}" stroke-width="2"/>`;
      });
    });
    const legendY = H - 40;
    let legendX = PAD_L;
    const legendItemWidth = innerW / Math.max(trends.length, 1);
    trends.forEach((t, idx) => {
      const color = colors[idx % colors.length];
      const cx = legendX + legendItemWidth / 2;
      svg += `<line x1="${cx - 40}" y1="${legendY}" x2="${cx - 20}" y2="${legendY}" stroke="${color}" stroke-width="2.4"/>`;
      svg += `<circle cx="${cx - 30}" cy="${legendY}" r="3" fill="#fff" stroke="${color}" stroke-width="2"/>`;
      svg += `<text x="${cx - 12}" y="${legendY + 4}" font-family="DM Sans" font-size="11.5" fill="#4A7C59" font-weight="500">${t.term}</text>`;
      legendX += legendItemWidth;
    });
    svg += `</svg>`;
    host.innerHTML = svg;
  }

  function renderTrendsSuggestions(suggestions){
    const host = $('#trends-suggestions'); if (!host) return;
    if (!suggestions.length){
      host.innerHTML = '<div style="padding:14px; color:var(--ink-hint); font-size:11.5px">Sem sugestões accionáveis no momento. Mercado estável.</div>';
      return;
    }
    const palette = {
      act:   { color:'#B91C1C', bg:'rgba(185,28,28,0.06)',  label:'AGIR'    },
      watch: { color:'#D97706', bg:'rgba(217,119,6,0.06)',  label:'VIGIAR' },
      info:  { color:'#4A7C59', bg:'rgba(74,124,89,0.06)',  label:'INFO'   },
    };
    host.innerHTML = suggestions.map(s => {
      const p = palette[s.priority] || palette.info;
      const arrow = s.delta_pct >= 0 ? '↑' : '↓';
      return `
        <div style="padding:12px 14px; background:${p.bg}; border-left:3px solid ${p.color}; border-radius:8px">
          <div style="display:flex; justify-content:space-between; align-items:baseline; margin-bottom:6px">
            <span style="font:600 9.5px 'DM Mono',monospace; letter-spacing:.18em; color:${p.color}">${p.label}</span>
            <span style="font:500 11px 'DM Mono',monospace; color:${p.color}">${arrow} ${Math.abs(s.delta_pct).toFixed(0)}%</span>
          </div>
          <div style="font-size:12.5px; font-weight:500; color:var(--primary); margin-bottom:4px">${s.term}</div>
          <div style="font-size:11.5px; color:var(--ink-soft); line-height:1.45">${s.action}</div>
        </div>`;
    }).join('');
  }

  // ── Architecture (Definições) ─────────────────────────────
  async function renderArchitecture(){
    try {
      const a = await fetchJSON('/api/architecture');
      const host = $('#arch-host'); if (!host) return;
      host.innerHTML = `
        <div style="display:flex;flex-direction:column;gap:14px">
          <div>
            <div class="rail__section-title" style="font-size:9.5px; margin-bottom:8px">Backend · 5 ficheiros</div>
            <div style="display:flex;flex-direction:column;gap:5px">
              ${a.backend_files.map(f => `
                <div style="display:grid;grid-template-columns:auto 1fr auto;gap:10px;padding:8px 10px;background:var(--surface-soft);border-radius:7px">
                  <span style="font:500 11px 'DM Mono',monospace; color:var(--primary)">${f.file}</span>
                  <span style="font-size:11px; color:var(--ink-soft); line-height:1.35">${f.role}</span>
                  <span style="font:500 10px 'DM Mono',monospace; color:var(--ink-hint)">${f.lines}L</span>
                </div>`).join('')}
            </div>
          </div>

          <div>
            <div class="rail__section-title" style="font-size:9.5px; margin-bottom:8px">CSVs · entradas</div>
            <div style="display:flex;flex-direction:column;gap:8px">
              ${a.csv_files.map(c => `
                <div style="padding:10px 12px;background:var(--surface-soft);border-radius:8px">
                  <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:4px">
                    <span style="font:500 11.5px 'DM Mono',monospace; color:var(--primary)">${c.name}</span>
                    <span style="font-size:9.5px; color:var(--ink-hint); letter-spacing:.1em; text-transform:uppercase">${c.produced_by}</span>
                  </div>
                  <div style="font-size:11px; color:var(--ink-soft); margin-bottom:4px">${c.purpose}</div>
                  <div style="font:500 9.5px 'DM Mono',monospace; color:var(--secondary); line-height:1.5">${c.columns.join(' · ')}</div>
                </div>`).join('')}
            </div>
          </div>

          <div>
            <div class="rail__section-title" style="font-size:9.5px; margin-bottom:8px">Fluxo · do CSV ao ecrã</div>
            <div style="display:flex;flex-direction:column;gap:4px">
              ${a.flow.map((s, i, arr) => `
                <div style="display:grid;grid-template-columns:24px 1fr; gap:10px; align-items:start; padding:6px 0">
                  <div style="width:22px;height:22px;border-radius:50%;background:var(--primary);color:#fff;display:flex;align-items:center;justify-content:center;font:600 10px 'DM Mono',monospace">${s.step}</div>
                  <div>
                    <div style="font-size:11.5px; font-weight:500; color:var(--primary)">${s.title}</div>
                    <div style="font:500 9.5px 'DM Mono',monospace; color:var(--ink-hint); margin-top:1px">${s.actor}</div>
                  </div>
                </div>`).join('')}
            </div>
          </div>
        </div>
      `;
    } catch(e){ console.error(e); }
  }

  // ── Chatbot ────────────────────────────────────────────────
  function addChatMsg(text, who){
    const log = $('#chat-log'); if (!log) return;
    const msg = el('div', 'chat-msg chat-msg--' + who);
    msg.innerHTML = text;
    log.appendChild(msg);
    log.scrollTop = log.scrollHeight;
  }
  async function chatSend(){
    const input = $('#chat-input'); const q = input.value.trim(); if (!q) return;
    input.value = '';
    addChatMsg(q, 'user');
    try {
      const r = await fetchJSON('/api/agents/chatbot', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({question:q}) });
      addChatMsg(r.answer, 'bot');
    } catch(e) { addChatMsg('Erro · backend não respondeu.', 'bot'); }
  }

  // ── Confirm dialog ─────────────────────────────────────────
  let pendingConfirm = null;
  function confirmDialog(title, text, onOk){
    $('#confirm-title').textContent = title;
    $('#confirm-text').innerHTML = text;
    pendingConfirm = onOk;
    $('#confirm-box').classList.add('is-open');
  }
  function confirmOk(){ const f = pendingConfirm; pendingConfirm = null; $('#confirm-box').classList.remove('is-open'); if (f) f(); }
  function confirmCancel(){ pendingConfirm = null; $('#confirm-box').classList.remove('is-open'); }
  function confirm(title, text, onOk){ confirmDialog(title, text, onOk); }

  function resolveAlert(id, stationName){
    confirmDialog('Resolver alerta?',
      `Confirma resolução do alerta em <b>${stationName}</b>? Esta acção fica no audit trail.`,
      async () => {
        await fetchJSON(`/api/alerts/${id}/resolve`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({note:'Resolvido via UI', resolved_by:'U01', confirmed:true}) });
        refreshAll();
      });
  }

  function saveThreshold(key, value){
    confirmDialog('Guardar parâmetro?',
      `Alterar <b>${key}</b> para <b>${value}</b>?<br><br>No modo demo, a alteração fica no audit trail (o config.yaml persiste).`,
      async () => {
        await fetchJSON('/api/decisions', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({kind:'update_threshold', target:key, payload:{key,value}, confirmed:true}) });
      });
  }

  // ── Connections (Definições · CSV pipeline) ───────────────
  async function renderConnections(){
    try {
      const c = await fetchJSON('/api/connections');
      const host = $('#conn-host'); if (!host) return;

      const badge = (status) => {
        const m = { connected: ['#6FAF82', 'Ligado'], awaiting: ['#D97706', 'À espera'] };
        const [color, text] = m[status] || ['#8FA896', status];
        return `<span style="display:inline-flex;align-items:center;gap:6px;font:500 10.5px 'DM Mono',monospace;color:${color}">
          <span style="width:7px;height:7px;border-radius:50%;background:${color};box-shadow:0 0 0 3px ${color}22"></span>
          ${text.toUpperCase()}
        </span>`;
      };

      let html = `
        <div style="display:flex;flex-direction:column;gap:14px">
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
            ${c.pipelines.map(p => `
              <div style="padding:14px 16px;background:var(--surface-soft);border-radius:12px">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
                  <div style="font-family:'Cormorant Garamond',serif;font-weight:500;font-size:18px;text-transform:capitalize">${p.source}</div>
                  ${badge(p.status)}
                </div>
                <div style="font-size:10.5px;color:var(--ink-hint);line-height:1.5">
                  Colunas esperadas · <span style="font-family:'DM Mono',monospace;color:var(--secondary)">${p.schema.join(' · ')}</span>
                </div>
                <div style="margin-top:8px;font:500 11px 'DM Mono',monospace;color:var(--secondary)">
                  ${p.files_processed} processados · ${p.files_pending} pendentes
                </div>
              </div>
            `).join('')}
          </div>

          <div style="padding:14px 16px;background:var(--surface-soft);border-radius:12px">
            <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:10px">
              <div class="rail__section-title">Drop-zone</div>
              <div style="font:500 10px 'DM Mono',monospace;color:var(--ink-hint)">${c.inbox_path}</div>
            </div>
            <label id="conn-drop" style="display:flex;flex-direction:column;align-items:center;gap:6px;padding:22px;border:2px dashed var(--hairline);border-radius:10px;cursor:pointer;transition:border-color .2s,background .2s">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#4A7C59" stroke-width="1.6"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/></svg>
              <div style="font-size:12.5px;color:var(--primary);font-weight:500">Clica para upload · ou arrasta um CSV</div>
              <div style="font-size:10.5px;color:var(--ink-hint)">Nomes: <span class="font-mono">preference_*.csv</span> · <span class="font-mono">primavera_*.csv</span></div>
              <input id="conn-file" type="file" accept=".csv" style="display:none">
            </label>
            <div id="conn-upload-status" style="margin-top:8px;font-size:11px;color:var(--ink-hint);min-height:16px"></div>
          </div>

          <div style="padding:14px 16px;background:var(--surface-soft);border-radius:12px">
            <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:10px">
              <div class="rail__section-title">Últimos processados</div>
              <div style="font:500 10px 'DM Mono',monospace;color:var(--ink-hint)">${c.totals.events.toLocaleString('pt-PT')} eventos · ${c.totals.orders} encomendas</div>
            </div>
            <div style="display:flex;flex-direction:column;gap:5px;max-height:200px;overflow-y:auto">
              ${c.processed_files.length === 0
                ? '<div style="font-size:11px;color:var(--ink-hint);padding:4px">Nenhum ficheiro processado ainda.</div>'
                : c.processed_files.map(f => `
                    <div style="display:grid;grid-template-columns:1fr auto auto;gap:10px;padding:6px 10px;background:#fff;border-radius:7px;font-family:'DM Mono',monospace;font-size:10.5px">
                      <span style="color:var(--primary)">${f.name}</span>
                      <span style="color:var(--ink-hint)">${f.size_kb} KB</span>
                      <span style="color:var(--tertiary)">✓</span>
                    </div>`).join('')}
            </div>
          </div>
        </div>
      `;
      host.innerHTML = html;

      // Wire upload
      const fileInput = $('#conn-file');
      const drop = $('#conn-drop');
      const status = $('#conn-upload-status');
      if (fileInput && drop){
        fileInput.addEventListener('change', async () => {
          const f = fileInput.files[0]; if (!f) return;
          status.textContent = 'A enviar ' + f.name + '...';
          const fd = new FormData(); fd.append('file', f);
          try {
            const r = await fetch('/api/connections/upload', { method:'POST', body: fd });
            if (!r.ok){ status.textContent = 'Erro · ' + (await r.text()); status.style.color='var(--red)'; return; }
            const res = await r.json();
            status.textContent = `✓ ${f.name} · ${res.result.rows || 0} linhas ingeridas`;
            status.style.color = 'var(--tertiary)';
            setTimeout(() => { renderConnections(); refreshAll(); }, 500);
          } catch(e){ status.textContent = 'Erro: ' + e.message; status.style.color='var(--red)'; }
          fileInput.value = '';
        });
        drop.addEventListener('dragover', e => { e.preventDefault(); drop.style.borderColor='var(--primary)'; drop.style.background='#EDF4EF'; });
        drop.addEventListener('dragleave', () => { drop.style.borderColor=''; drop.style.background=''; });
        drop.addEventListener('drop', e => {
          e.preventDefault(); drop.style.borderColor=''; drop.style.background='';
          const f = e.dataTransfer.files[0]; if (f){ fileInput.files = e.dataTransfer.files; fileInput.dispatchEvent(new Event('change')); }
        });
      }
    } catch(e){ console.error(e); }
  }

  // ── Export CSV (Python-generated, downloadable) ────────────
  async function renderExport(){
    try {
      const list = await fetchJSON('/api/export');
      const host = $('#export-host'); if (!host) return;
      host.innerHTML = list.map(e => `
        <button class="export-row" data-key="${e.key}">
          <div class="export-row__left">
            <div class="export-row__label">${e.label}</div>
            <div class="export-row__desc">${e.desc}</div>
          </div>
          <div class="export-row__right">
            <span class="export-row__count">${e.rows.toLocaleString('pt-PT')}</span>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
          </div>
        </button>
      `).join('');
      $$('.export-row', host).forEach(btn => {
        btn.addEventListener('click', () => downloadCSV(btn.dataset.key, list.find(x => x.key === btn.dataset.key)));
      });
    } catch(e){ console.error(e); }
  }

  async function downloadCSV(key, meta){
    const btn = $(`.export-row[data-key="${key}"]`);
    if (btn){ btn.classList.add('is-downloading'); }
    try {
      const r = await fetch(`/api/export/${key}`);
      if (!r.ok) throw new Error(`${r.status}`);
      const blob = await r.blob();
      const cd = r.headers.get('content-disposition') || '';
      const match = /filename="([^"]+)"/.exec(cd);
      const fname = match ? match[1] : `hyline_${key}.csv`;
      // Trigger download
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = fname;
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      if (btn){ btn.classList.remove('is-downloading'); btn.classList.add('is-done'); setTimeout(() => btn.classList.remove('is-done'), 1400); }
    } catch(e){
      if (btn){ btn.classList.remove('is-downloading'); }
      alert('Erro ao exportar: ' + e.message);
    }
  }

  // ══════════════════════════════════════════════════════════
  // PROCUREMENT
  // ══════════════════════════════════════════════════════════
  function catLabel(cat){
    return {perfis:'Perfis', vidro:'Vidro', ferragens:'Ferragens', consumiveis:'Consumíveis'}[cat] || cat;
  }

  async function renderProcurement(){
    await Promise.all([loadCatalog(), loadCart()]);
    $$('.chip-filter').forEach(btn => {
      btn.onclick = () => {
        $$('.chip-filter').forEach(b => b.classList.remove('is-active'));
        btn.classList.add('is-active');
        procActiveCat = btn.dataset.cat;
        loadCatalog();
      };
    });
    const ecoChk = $('#eco-toggle-chk');
    if (ecoChk) ecoChk.onchange = () => { procEcoOnly = ecoChk.checked; loadCatalog(); };
  }

  async function loadCatalog(){
    const minSust = procEcoOnly ? 85 : 0;
    let url = `/api/procurement/catalog?min_sustainability=${minSust}`;
    if (procActiveCat) url += `&category=${procActiveCat}`;
    try {
      const items = await fetchJSON(url);
      const grid = $('#catalog-grid'); if (!grid) return;
      if (!items.length){
        grid.innerHTML = '<div style="padding:24px;color:var(--ink-hint);font-size:12.5px">Sem itens com estes filtros.</div>';
        return;
      }
      grid.innerHTML = '';
      items.forEach(item => {
        const ecoColor = item.sustainability_score >= 85 ? 'var(--tertiary)' : item.sustainability_score >= 70 ? 'var(--amber)' : 'var(--red)';
        const certs = item.certifications ? item.certifications.split(',').map(c => `<span class="cert-tag">${c.trim()}</span>`).join('') : '';
        const card = el('div', 'cat-card');
        card.innerHTML = `
          <div class="cat-card__head">
            <span class="cat-card__cat">${catLabel(item.category)}</span>
            <span class="score-pill" style="background:${ecoColor}22;color:${ecoColor};border:1px solid ${ecoColor}44">${item.sustainability_score}</span>
          </div>
          <div class="cat-card__name">${item.name}</div>
          <div class="cat-card__supplier">${item.supplier_name}</div>
          <div class="cat-card__row">
            <span class="cat-card__price">${nf(item.price_eur,2)}€/${item.unit}</span>
            <span class="cat-card__stock">${item.stock_level.toLocaleString('pt-PT')} un.</span>
          </div>
          <div class="cat-card__certs">${certs}</div>
          <button class="btn btn--solid btn--sm" style="width:100%;margin-top:10px">+ Adicionar</button>`;
        card.querySelector('button').addEventListener('click', () => addToCart(item.id));
        grid.appendChild(card);
      });
    } catch(e){ console.error(e); }
  }

  async function addToCart(catalogId){
    try {
      await fetchJSON('/api/procurement/cart/add', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({catalog_id: catalogId, quantity: 1}),
      });
      loadCart();
    } catch(e){ console.error(e); }
  }

  async function loadCart(){
    try {
      const items = await fetchJSON('/api/procurement/cart');
      const list = $('#cart-list'); const countEl = $('#cart-count');
      const totalEl = $('#cart-total'); const ecoEl = $('#cart-eco-score');
      if (!list) return;
      if (countEl) countEl.textContent = items.length;
      if (!items.length){
        list.innerHTML = '<div style="padding:14px 4px;color:var(--ink-hint);font-size:11.5px">Carrinho vazio.</div>';
        if (totalEl) totalEl.textContent = '0,00€';
        if (ecoEl)   ecoEl.textContent = '—';
        return;
      }
      const total   = items.reduce((a, i) => a + i.subtotal_eur, 0);
      const ecoAvg  = Math.round(items.reduce((a, i) => a + i.sustainability_score, 0) / items.length);
      list.innerHTML = '';
      items.forEach(item => {
        const row = el('div', 'cart-item');
        row.innerHTML = `
          <div class="cart-item__info">
            <div class="cart-item__name">${item.name}</div>
            <div class="cart-item__meta">${item.quantity} ${item.unit} · ${nf(item.subtotal_eur,2)}€</div>
          </div>
          <button class="cart-item__remove" title="Remover">✕</button>`;
        row.querySelector('button').addEventListener('click', () => removeFromCart(item.id));
        list.appendChild(row);
      });
      if (totalEl) totalEl.textContent = nf(total,2) + '€';
      if (ecoEl){
        ecoEl.textContent = ecoAvg + '/100';
        ecoEl.style.color = ecoAvg >= 85 ? 'var(--tertiary)' : 'var(--amber)';
      }
    } catch(e){ console.error(e); }
  }

  function removeFromCart(cartId){
    confirmDialog('Remover do carrinho?', 'Remover este item do carrinho?',
      async () => {
        await fetch(`/api/procurement/cart/${cartId}`, {method:'DELETE'});
        loadCart();
      });
  }

  function clearCart(){
    confirmDialog('Limpar carrinho?', 'Remover todos os itens? Esta acção não pode ser revertida.',
      async () => {
        const items = await fetchJSON('/api/procurement/cart');
        await Promise.all(items.map(i => fetch(`/api/procurement/cart/${i.id}`, {method:'DELETE'})));
        loadCart();
      });
  }

  function checkout(){
    confirmDialog('Confirmar compra?',
      'Confirmar encomenda de todos os itens no carrinho? Esta acção fica no audit trail.',
      async () => {
        const r = await fetchJSON('/api/procurement/checkout', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({confirmed: true}),
        });
        loadCart();
      });
  }

  // ══════════════════════════════════════════════════════════
  // DOCK + CONVERSATIONS
  // ══════════════════════════════════════════════════════════

  function relativeTime(ts){
    const diff = Math.floor((Date.now() - new Date(ts).getTime()) / 1000);
    if (diff < 60)   return 'agora';
    if (diff < 3600) return `${Math.floor(diff/60)} min`;
    if (diff < 86400) return `${Math.floor(diff/3600)} h`;
    return `${Math.floor(diff/86400)} d`;
  }

  function renderMsgText(text){
    return (text || '').replace(/\n/g,'<br>').replace(/\*\*(.*?)\*\*/g,'<strong>$1</strong>');
  }

  function renderConvStream(messages){
    const host = $('#conv-stream'); if (!host) return;
    if (!messages || !messages.length){
      host.innerHTML = '<div class="conv-stream__empty">Ainda sem mensagens nesta conversa</div>';
      return;
    }
    host.innerHTML = '';
    messages.forEach(m => {
      if (m.role === 'user'){
        const div = el('div', 'msg msg--user');
        div.innerHTML = renderMsgText(m.content);
        host.appendChild(div);
        return;
      }
      if (m.role === 'assistant'){
        const div = el('div', 'msg msg--bot');
        div.innerHTML = renderMsgText(m.content);
        // Tool chips
        const toolCalls = m.tool_calls ? (typeof m.tool_calls === 'string' ? JSON.parse(m.tool_calls) : m.tool_calls) : [];
        toolCalls.forEach(tc => {
          const chip = el('div', 'msg__tool-chip');
          chip.textContent = `↳ ${toolLabel(tc.name)} ${toolArgs(tc.args)}`;
          div.appendChild(chip);
        });
        // Action buttons
        const actions = m.actions ? (typeof m.actions === 'string' ? JSON.parse(m.actions) : m.actions) : [];
        if (actions.length){
          const bar = el('div', 'msg__actions');
          actions.forEach(a => {
            if (a.kind === 'open_view'){
              const btn = el('button', 'msg__action-btn');
              btn.textContent = a.label;
              btn.onclick = () => switchView(a.target);
              bar.appendChild(btn);
            }
          });
          div.appendChild(bar);
        }
        host.appendChild(div);
      }
    });
    host.scrollTop = host.scrollHeight;
  }

  function toolLabel(name){
    return {
      open_view:'Navegou para', search_catalog:'Procurou catálogo',
      add_to_cart:'Adicionou ao carrinho', checkout:'Confirmou compra',
      get_station_status:'Consultou estação', suggest_reassignment:'Propostas reatribuição',
      global_kpis:'KPIs globais',
    }[name] || name;
  }
  function toolArgs(args){
    if (!args) return '';
    const parts = Object.entries(args).map(([k,v]) => `${v}`).join(', ');
    return parts ? `(${parts})` : '';
  }

  function renderConvList(items){
    const host = $('#conv-list-items'); if (!host) return;
    if (!items.length){
      host.innerHTML = '<div class="conv-list__empty">Sem conversas ainda.<br>Escreve na barra em baixo.</div>';
      return;
    }
    host.innerHTML = '';
    items.forEach(c => {
      const btn = el('button', 'conv-item' + (c.id === __chat.currentConvId ? ' is-active' : ''));
      btn.innerHTML = `
        <div class="conv-item__title">${c.title || 'Nova conversa'}</div>
        <div class="conv-item__preview">${c.preview || '—'}</div>
        <div class="conv-item__time">${relativeTime(c.updated_ts)}</div>
        <span class="conv-item__del" title="Eliminar">✕</span>`;
      btn.addEventListener('click', (e) => {
        if (e.target.classList.contains('conv-item__del')){ deleteConversation(c.id); return; }
        selectConversation(c.id);
      });
      host.appendChild(btn);
    });
  }

  async function loadConversations(){
    try {
      const items = await fetchJSON('/api/conversations');
      __chat.conversations = items;
      renderConvList(items);
      if (__chat.currentConvId){
        const found = items.find(c => c.id === __chat.currentConvId);
        if (found) selectConversation(__chat.currentConvId);
      } else if (items.length) {
        selectConversation(items[0].id);
      } else {
        const host = $('#conv-stream');
        if (host) host.innerHTML = '<div class="conv-stream__empty">Seleciona uma conversa ou inicia uma nova na barra em baixo</div>';
      }
    } catch(e){ console.error(e); }
  }

  async function selectConversation(convId){
    __chat.currentConvId = convId;
    $$('.conv-item').forEach(b => b.classList.toggle('is-active', b.querySelector('.conv-item__title') && b.dataset.cid === convId));
    // Mark active on the rendered items (re-render list to reflect)
    renderConvList(__chat.conversations);
    try {
      const conv = await fetchJSON(`/api/conversations/${convId}`);
      renderConvStream(conv.messages || []);
    } catch(e){ console.error(e); }
  }

  async function newConversation(){
    __chat.currentConvId = null;
    if (document.querySelector('.view.is-active[data-view="conversations"]')){
      const host = $('#conv-stream');
      if (host) host.innerHTML = '<div class="conv-stream__empty">Escreve na barra em baixo para começar</div>';
      renderConvList(__chat.conversations);
    }
    const inp = $('#dock-input'); if (inp){ inp.focus(); }
  }

  function deleteConversation(convId){
    confirmDialog('Eliminar conversa?',
      'Esta acção não pode ser revertida. Tens a certeza?',
      async () => {
        await fetch(`/api/conversations/${convId}`, {method:'DELETE'});
        if (__chat.currentConvId === convId) __chat.currentConvId = null;
        loadConversations();
      });
  }

  async function updateDockStatus(){
    const dot = $('#dock-status'); if (!dot) return;
    try {
      const u = await fetchJSON('/api/assistant/usage');
      if (u.gemini_active){
        dot.textContent = '●';
        dot.className = 'dock__status';
        dot.title = `Gemini 2.5 Flash · ${u.today.calls}/${u.daily_cap} hoje`;
      } else {
        dot.textContent = '○';
        dot.className = 'dock__status is-offline';
        dot.title = 'Modo regras locais · sem chave Gemini';
      }
    } catch(_){ dot.textContent = '○'; dot.className = 'dock__status is-offline'; }
  }

  async function dockSend(){
    const inp = $('#dock-input'); if (!inp) return;
    const q = inp.value.trim(); if (!q) return;
    inp.value = '';

    const dot = $('#dock-status');
    if (dot){ dot.className = 'dock__status is-thinking'; dot.textContent = '●'; }

    // Navigate to conversations view before request so user sees it forming
    if (!document.querySelector('.view.is-active[data-view="conversations"]')){
      switchView('conversations');
    }

    // Optimistically render user message
    const stream = $('#conv-stream');
    if (stream){
      const existing = stream.querySelector('.conv-stream__empty');
      if (existing) existing.remove();
      const umsg = el('div', 'msg msg--user');
      umsg.innerHTML = renderMsgText(q);
      stream.appendChild(umsg);
      stream.scrollTop = stream.scrollHeight;
    }

    try {
      const r = await fetchJSON('/api/assistant', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({question: q, conversation_id: __chat.currentConvId}),
      });
      __chat.currentConvId = r.conversation_id;

      // Reload full conversation (includes persisted messages)
      await loadConversations();

      // Auto-navigate after tool call (with 1.2s delay)
      const navAction = (r.actions || []).find(a => a.kind === 'open_view');
      if (navAction){
        setTimeout(() => switchView(navAction.target), 1200);
      }
    } catch(e){
      if (stream){
        const err = el('div', 'msg msg--bot');
        err.textContent = 'Erro · assistente não respondeu.';
        stream.appendChild(err);
      }
    } finally {
      if (dot){ dot.className = 'dock__status'; dot.textContent = '●'; }
      updateDockStatus();
    }
  }

  // ── Alert Transfer ─────────────────────────────────────────
  function transferAlert(alertId, currentRole){
    const roles = ['HST','DQ','Director','ChefeTurno'].filter(r => r !== currentRole);
    const menu = el('div', 'transfer-menu');
    menu.style.cssText = 'position:fixed;background:var(--surface);border:1px solid var(--hairline);border-radius:10px;box-shadow:0 8px 24px rgba(27,58,33,.15);padding:6px;z-index:300';
    menu.innerHTML = roles.map(r => `<button class="btn btn--ghost btn--sm" style="display:block;width:100%;text-align:left;margin-bottom:2px" onclick="App._doTransfer(${alertId},'${r}',this.closest('.transfer-menu'))">${r}</button>`).join('');
    document.body.appendChild(menu);
    menu.style.top = '50%'; menu.style.left = '50%'; menu.style.transform = 'translate(-50%,-50%)';
    const close = () => { if (menu.parentNode) menu.parentNode.removeChild(menu); };
    setTimeout(() => document.addEventListener('click', close, {once:true}), 100);
  }

  async function _doTransfer(alertId, toRole, menuEl){
    if (menuEl && menuEl.parentNode) menuEl.parentNode.removeChild(menuEl);
    await fetchJSON(`/api/alerts/${alertId}/transfer`, {
      method:'PATCH', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({to_role: toRole}),
    });
    const toast = el('div');
    toast.style.cssText = 'position:fixed;bottom:90px;right:24px;background:var(--primary);color:#fff;padding:12px 20px;border-radius:10px;font-size:13px;z-index:400;animation:msgIn .3s ease-out';
    toast.textContent = `Alerta transferido para ${toRole}`;
    document.body.appendChild(toast);
    setTimeout(() => { if (toast.parentNode) toast.parentNode.removeChild(toast); }, 2000);
    refreshAll();
  }

  // ── Mission 8: Import CSV ──────────────────────────────────
  async function importFile(type, input){
    const file = input.files[0]; if (!file) return;
    const statusEl = $(`#import-${type}-status`);
    if (statusEl) statusEl.textContent = 'A importar...';
    const fd = new FormData(); fd.append('file', file);
    try {
      const r = await fetch(`/api/import/${type}`, { method: 'POST', body: fd });
      const d = await r.json();
      if (statusEl) statusEl.textContent = `✓ ${d.records} registos`;
      setTimeout(() => refreshAll(), 500);
    } catch(e) {
      if (statusEl){ statusEl.textContent = 'Erro'; statusEl.style.color = 'var(--red)'; }
    }
    input.value = '';
  }

  // ── Mission 9: Role Switcher ───────────────────────────────
  const ROLES = {
    director: {av:'JM', name:'Joana Martins',  title:'Director Produção',   highlight:['Director']},
    chefe:    {av:'CS', name:'Carlos Silva',    title:'Chefe de Turno',      highlight:['ChefeTurno']},
    dq:       {av:'AF', name:'Ana Ferreira',    title:'Departamento Qualidade', highlight:['DQ']},
    hst:      {av:'PR', name:'Pedro Rocha',     title:'HST',                 highlight:['HST']},
  };
  let currentRole = 'director';

  function toggleRoleMenu(){
    const m = $('#role-menu');
    if (m) m.style.display = m.style.display === 'none' ? 'block' : 'none';
  }

  function setRole(role){
    currentRole = role;
    const r = ROLES[role];
    const av = $('#role-avatar'); if (av) av.textContent = r.av;
    const nm = $('#role-name');   if (nm) nm.textContent = r.name;
    const ti = $('#role-title');  if (ti) ti.textContent = r.title;
    const menu = $('#role-menu'); if (menu) menu.style.display = 'none';
    localStorage.setItem('hyline_role', role);
    // Highlight relevant alert columns
    $$('.alerts-col').forEach(col => {
      const title = col.querySelector('.alerts-col__title')?.textContent || '';
      const active = role === 'director' || r.highlight.some(h => title.includes(h.replace('ChefeTurno','Chefe')));
      col.style.opacity = active ? '1' : '0.45';
    });
    renderAlertsBoard(alertsLive);
  }

  document.addEventListener('click', e => {
    const menu = $('#role-menu');
    const btn  = $('#role-btn');
    if (menu && btn && !btn.contains(e.target) && !menu.contains(e.target)){
      menu.style.display = 'none';
    }
  });

  // ── Mission 2: Live Feed ───────────────────────────────────
  async function renderLiveFeed(){
    try {
      const events = await fetchJSON('/api/events?limit=20');
      const host = $('#live-feed-list'); if (!host) return;
      host.innerHTML = '';
      if (!events.length){
        host.innerHTML = '<div style="padding:14px;color:var(--ink-hint);font-size:11px">Sem eventos recentes.</div>';
        return;
      }
      events.forEach(ev => {
        const isOk   = ev.status === 'completed';
        const isWarn = ['defect','rework'].includes(ev.status);
        const isErr  = ['breakdown','safety'].includes(ev.status);
        const statusCls = isOk ? 'ok' : isWarn ? 'warn' : 'err';
        const statusLabel = {completed:'✓', defect:'NC', rework:'RW', breakdown:'AVA', safety:'SEG'}[ev.status] || ev.status;
        const ts = ev.ts || ev.timestamp || ev.created_at || '';
        const time = ts ? new Date(ts).toLocaleTimeString('pt-PT',{hour:'2-digit',minute:'2-digit'}) : '--:--';
        const m2 = ev.area_m2 ? `${(+ev.area_m2).toFixed(2)}m²` : '';
        const stationName = ev.station_name || ev.station_id || '—';
        const row = el('div', `feed-event feed-event--${ev.status || 'completed'}`);
        row.innerHTML = `
          <span class="feed-time">${time}</span>
          <div><div class="feed-station">${stationName}</div><div style="font-size:9px;color:var(--ink-hint)">${m2}</div></div>
          <span class="feed-status feed-status--${statusCls}">${statusLabel}</span>`;
        host.appendChild(row);
      });
    } catch(e){ /* silent */ }
  }

  // ── Init ───────────────────────────────────────────────────
  function init(){
    $$('.nav__item').forEach(b => b.addEventListener('click', () => switchView(b.dataset.view)));

    tickClock();
    setInterval(tickClock, 1000);  // ← ticks every SECOND. m² value increments in real-time.

    renderAgents();
    renderPriorities();
    renderTeam();
    renderSustain();
    renderConnections();
    renderArchitecture();
    renderExport();
    refreshOptimiser();

    addChatMsg('Olá. Experimenta perguntas como: <i>"desempenho global"</i> · <i>"pior estação"</i> · <i>"alertas abertos"</i> · <i>"produção hoje"</i>', 'bot');

    // Dock wiring
    const dockInp = $('#dock-input');
    const dockSnd = $('#dock-send');
    const dockNew = $('#dock-newchat');
    if (dockInp) dockInp.addEventListener('keydown', e => { if (e.key === 'Enter'){ e.preventDefault(); dockSend(); } });
    if (dockSnd) dockSnd.addEventListener('click', dockSend);
    if (dockNew) dockNew.addEventListener('click', newConversation);

    // ⌘K / Ctrl+K focuses dock input
    document.addEventListener('keydown', e => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k'){
        e.preventDefault();
        const inp = $('#dock-input'); if (inp){ inp.focus(); inp.select(); }
      }
    });

    updateDockStatus();
    setInterval(updateDockStatus, 30000);

    // Restore saved role
    const savedRole = localStorage.getItem('hyline_role');
    if (savedRole && ROLES[savedRole]) setRole(savedRole);

    refreshAll();
    setInterval(refreshAll, REFRESH_MS);
  }

  return {
    init, switchView,
    selectStation, selectOrder, selectAlertStation, closeDetail,
    confirm, confirmOk, confirmCancel,
    resolveAlert, saveThreshold,
    chatSend, refreshOptimiser, applyProposal,
    refreshConnections: renderConnections,
    addToCart, removeFromCart, clearCart, checkout, loadCart,
    dockSend, newConversation, deleteConversation,
    loadConversations, selectConversation, updateDockStatus,
    transferAlert, _doTransfer,
    importFile, toggleRoleMenu, setRole,
  };
})();

window.App = App;
document.addEventListener('DOMContentLoaded', () => {
  App.init();
  document.getElementById('confirm-ok').addEventListener('click', App.confirmOk);
});
