/* shared.js — loaded on every page via base.html */
'use strict';

// Use window assignments so page-specific const $ declarations don't conflict
window.$ = id => document.getElementById(id);
window.fetchJSON = async (url, opts) => {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(`${r.status} ${url}`);
  return r.json();
};

// ── Clock ────────────────────────────────────────────────────────
function tickClock() {
  const el = $('clock');
  if (!el) return;
  const now = new Date();
  el.textContent = now.toLocaleTimeString('pt-PT', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}
setInterval(tickClock, 1000);
tickClock();

// ── WebSocket live feed ──────────────────────────────────────────
const _ws = (() => {
  let ws = null;
  let retryMs = 1500;

  function connect() {
    try {
      ws = new WebSocket(`ws://${location.host}/ws/live`);
    } catch (e) { return; }

    ws.onopen = () => {
      retryMs = 1500;
      const dot = $('dock-dot');
      if (dot) { dot.classList.add('is-online'); dot.classList.remove('is-offline'); dot.title = 'Ligado · dados ao segundo'; }
      const ss = $('sync-status');
      if (ss) ss.textContent = 'sincronizado';
    };

    ws.onmessage = (evt) => {
      let d;
      try { d = JSON.parse(evt.data); } catch { return; }

      // Update all [data-live] elements
      document.querySelectorAll('[data-live]').forEach(el => {
        const key = el.dataset.live;
        if (d[key] !== undefined) el.textContent = _fmt(key, d[key]);
      });

      // Update nav alert badge
      const badge = $('nav-alerts-count');
      if (badge && d.alerts_open !== undefined) badge.textContent = d.alerts_open;

      // Dispatch event for page-specific handlers
      document.dispatchEvent(new CustomEvent('live', { detail: d }));
    };

    ws.onclose = () => {
      const dot = $('dock-dot');
      if (dot) { dot.classList.remove('is-online'); dot.classList.add('is-offline'); }
      setTimeout(connect, retryMs);
      retryMs = Math.min(retryMs * 1.5, 30000);
    };

    ws.onerror = () => ws.close();
  }

  connect();
})();

function _fmt(key, val) {
  if (key === 'temp_c')           return Number(val).toFixed(1);
  if (key === 'humidity_pct')     return Number(val).toFixed(1);
  if (key === 'co2_ppm')          return Math.round(val);
  if (key === 'noise_db')         return Number(val).toFixed(1);
  if (key === 'm2_today')         return Number(val).toLocaleString('pt-PT', {minimumFractionDigits:1, maximumFractionDigits:1});
  if (key === 'prod_rate_m2_min') return Number(val).toFixed(3);
  return val;
}

// ── Dock logic ───────────────────────────────────────────────────
const dockInput = $('dock-input');
const dockSend  = $('dock-send');
const dockNew   = $('dock-new');

if (dockSend) {
  dockSend.addEventListener('click', () => {
    const q = (dockInput?.value || '').trim();
    if (!q) return;
    // Store question and navigate to conversations
    sessionStorage.setItem('dock_question', q);
    window.location.href = '/conversas';
  });
}

if (dockInput) {
  dockInput.addEventListener('keydown', e => {
    if (e.key === 'Enter') dockSend?.click();
  });
}

if (dockNew) {
  dockNew.addEventListener('click', () => {
    sessionStorage.removeItem('dock_question');
    window.location.href = '/conversas';
  });
}

// ── Update dock Gemini status ─────────────────────────────────────
async function updateDockStatus() {
  try {
    const u = await fetchJSON('/api/assistant/usage');
    const dot = $('dock-dot');
    if (!dot) return;
    if (u.gemini_active) {
      dot.classList.add('is-online'); dot.classList.remove('is-offline');
      dot.title = `Gemini 2.0 Flash · ${u.today?.calls ?? 0}/${u.daily_cap ?? 1400}`;
    } else {
      dot.classList.remove('is-online'); dot.classList.add('is-offline');
      dot.title = 'Modo regras locais';
    }
  } catch {}
}
setTimeout(updateDockStatus, 2000);
