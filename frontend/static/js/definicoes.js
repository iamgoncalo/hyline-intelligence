/* definicoes.js — settings: team, connections, architecture, exports */
'use strict';
const $ = id => document.getElementById(id);
const fetchJSON = async (url, opts) => { const r = await fetch(url, opts); if (!r.ok) throw new Error(r.status); return r.json(); };

const Def = {
  tab(btn, name) {
    document.querySelectorAll('.def-tab').forEach(b => b.classList.remove('is-active'));
    document.querySelectorAll('.def-panel').forEach(p => p.classList.remove('is-active'));
    btn.classList.add('is-active');
    const panel = $(`panel-${name}`);
    if (panel) panel.classList.add('is-active');
    Def._load(name);
  },
  _loaded: {},
  async _load(name) {
    if (Def._loaded[name]) return;
    Def._loaded[name] = true;
    if (name === 'equipa')       loadTeam();
    if (name === 'conexoes')     loadConnections();
    if (name === 'arquitectura') loadArch();
    if (name === 'exportar')     loadExports();
  }
};

async function loadTeam() {
  try {
    const t = await fetchJSON('/api/team');
    const tbody = $('team-tbody');
    if (!tbody) return;
    const rolesById = Object.fromEntries(t.roles.map(r => [r.id, r]));
    tbody.innerHTML = t.members.map(m => {
      const role = rolesById[m.role] || {};
      return `<tr>
        <td>${m.name}</td>
        <td>${role.name || m.role}</td>
        <td style="font-family:'DM Mono',monospace;font-size:12px;">${m.station_assigned || '--'}</td>
      </tr>`;
    }).join('');
  } catch {}
}

async function loadConnections() {
  try {
    const c = await fetchJSON('/api/connections');
    const host = $('conn-list');
    if (!host) return;
    host.innerHTML = (c.pipelines || []).map(p => `
      <div class="conn-row">
        <div class="conn-dot ${p.status}"></div>
        <div>
          <div class="conn-name">${p.source.charAt(0).toUpperCase() + p.source.slice(1)}</div>
          <div class="conn-status">${p.status === 'connected' ? 'Ligado' : 'A aguardar'} · ${p.files_processed} ficheiros processados</div>
        </div>
      </div>`).join('');
  } catch {}
}

async function loadArch() {
  try {
    const a = await fetchJSON('/api/architecture');
    const host = $('arch-flow');
    if (!host) return;
    host.innerHTML = (a.flow || []).map(step => `
      <div class="metric-row" style="display:flex;align-items:flex-start;gap:16px;">
        <span style="font-family:'DM Mono',monospace;font-size:11px;color:var(--ink-hint);flex-shrink:0;margin-top:2px;">${step.step}</span>
        <div>
          <div style="font-size:13px;font-weight:500;">${step.title}</div>
          <div style="font-size:12px;color:var(--ink-hint);">${step.actor}</div>
        </div>
      </div>`).join('');
  } catch {}
}

async function loadExports() {
  try {
    const exports = await fetchJSON('/api/export');
    const host = $('export-btns');
    if (!host) return;
    host.innerHTML = exports.map(e => `
      <a class="export-btn" href="/api/export/${e.key}" download>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
        ${e.label} (${e.rows} linhas)
      </a>`).join('');
  } catch {}
}

// Load initial tab (equipa is first)
Def._load('equipa');
