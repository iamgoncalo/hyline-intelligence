/* alertas.js — 4-column alert board with slide-out drawer */
'use strict';
const $ = id => document.getElementById(id);
const fetchJSON = async (url, opts) => { const r = await fetch(url, opts); if (!r.ok) throw new Error(r.status); return r.json(); };
const _confirm = (t, b, fn) => (window.confirm2 ? window.confirm2(t, b, fn) : (confirm(`${t}\n${b}`) && fn()));

const ROLES = ['Director','HST','DQ','ChefeTurno'];
const ROLE_LABELS = {'Director':'Director','HST':'Chefe de Turno','DQ':'Qualidade','ChefeTurno':'Produção'};
const SEV_COLORS = {4: 'var(--red)', 3: 'var(--amber)', 2: 'var(--secondary)'};

let _allAlerts = [];

function sevClass(sev) {
  if (sev >= 4) return 'sev-4';
  if (sev >= 3) return 'sev-3';
  return 'sev-2';
}

function renderCard(a) {
  const sc = sevClass(a.severity || 2);
  const ts = (a.ts || '').slice(11, 16);
  return `<div class="alert-card ${sc}" style="cursor:pointer;" onclick="Alerts.openDrawer(${a.id})">
    <div class="alert-card__station">${a.station_name || '--'}</div>
    <div class="alert-card__type">${(a.alert_type||'').replace(/_/g,' ')}</div>
    <div class="alert-card__msg">${(a.message||'').slice(0,80)}${(a.message||'').length>80?'…':''}</div>
    <div class="alert-card__footer">SEV ${a.severity||'?'} · ${ts}</div>
  </div>`;
}

async function load() {
  try {
    _allAlerts = await fetchJSON('/api/alerts?limit=50');
    ROLES.forEach(role => {
      const list = $(`list-${role}`);
      const cnt  = $(`cnt-${role}`);
      if (!list) return;
      const mine = _allAlerts.filter(a => a.routed_to === role);
      if (cnt) cnt.textContent = mine.length;
      list.innerHTML = mine.length ? mine.map(renderCard).join('') : '<div class="alert-col__empty">Sem alertas</div>';
    });
    // Update open drawer if active
    const drawer = $('alert-drawer');
    if (drawer && drawer.classList.contains('is-open')) {
      const idEl = drawer.querySelector('[data-alert-id]');
      if (idEl) {
        const id = parseInt(idEl.dataset.alertId);
        const fresh = _allAlerts.find(a => a.id === id);
        if (fresh) Alerts.renderDrawer(fresh);
      }
    }
  } catch (e) { console.error(e); }
}

const Alerts = {
  openDrawer(alertId) {
    const alert = _allAlerts.find(a => a.id === alertId);
    if (!alert) return;
    this.renderDrawer(alert);
    const drawer = $('alert-drawer');
    if (drawer) drawer.classList.add('is-open');
  },

  renderDrawer(a) {
    const content = $('alert-drawer-content');
    if (!content) return;
    const sevColor = SEV_COLORS[a.severity || 2] || 'var(--secondary)';
    const ts = new Date((a.ts||'').replace('Z','')).toLocaleString('pt-PT', {day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
    content.innerHTML = `
      <div data-alert-id="${a.id}">
        <span class="drawer-sev-badge" style="background:${sevColor};color:#fff;">SEV ${a.severity||'?'}</span>
        <h2 style="font-family:'Cormorant Garamond',serif;font-size:26px;color:var(--primary);font-weight:400;margin:0 0 6px;">${a.station_name || 'Estação'}</h2>
        <p style="font-size:12px;color:var(--ink-hint);margin:0 0 20px;">${ts} · ${(a.alert_type||'').replace(/_/g,' ')}</p>

        <div style="font-size:13px;color:var(--primary);line-height:1.5;padding:16px;background:var(--surface-soft);border-radius:10px;margin-bottom:20px;">
          ${a.message || 'Sem diagnóstico disponível.'}
        </div>

        <div class="section-title">Encaminhado para</div>
        <p style="font-size:14px;font-weight:500;color:var(--primary);margin-top:4px;">${ROLE_LABELS[a.routed_to] || a.routed_to || '--'}</p>

        ${a.m2_impact != null ? `<div class="section-title" style="margin-top:16px;">Impacto estimado</div>
        <p style="font-family:'DM Mono',monospace;font-size:20px;color:var(--red);margin-top:4px;">${a.m2_impact.toFixed(1)} m²</p>` : ''}

        <div class="drawer-action-row">
          <button class="drawer-btn drawer-btn--danger" onclick="Alerts.resolve(${a.id})">Resolver</button>
          <button class="drawer-btn drawer-btn--ghost" onclick="Alerts.showTransferDrawer(${a.id})">Transferir</button>
          ${a.routed_to !== 'Director' ? `<button class="drawer-btn drawer-btn--ghost" onclick="Alerts.escalate(${a.id})">Escalar para Director</button>` : ''}
        </div>

        <div id="transfer-drawer-opts" style="display:none;margin-top:12px;">
          <div class="section-title">Transferir para</div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px;">
            ${ROLES.filter(r => r !== a.routed_to).map(r =>
              `<button class="transfer-opt" onclick="Alerts.transfer(${a.id},'${r}')">${ROLE_LABELS[r]}</button>`
            ).join('')}
          </div>
        </div>
      </div>`;
  },

  showTransferDrawer(id) {
    const opts = $('transfer-drawer-opts');
    if (opts) opts.style.display = opts.style.display === 'none' ? 'block' : 'none';
  },

  closeDrawer() {
    const drawer = $('alert-drawer');
    if (drawer) drawer.classList.remove('is-open');
  },

  async resolve(id) {
    _confirm('Resolver alerta', 'Esta acção será registada no audit trail.', async () => {
      try {
        await fetch(`/api/alerts/${id}/resolve`, {
          method: 'POST', headers: {'Content-Type':'application/json'},
          body: JSON.stringify({confirmed: true, note: 'Resolvido via dashboard'})
        });
        this.closeDrawer();
        load();
      } catch (e) { alert('Erro: ' + e.message); }
    });
  },

  async transfer(id, role) {
    _confirm('Transferir alerta', `Vai ser encaminhado para ${ROLE_LABELS[role]}.`, async () => {
      try {
        await fetch(`/api/alerts/${id}/transfer`, {
          method: 'PATCH', headers: {'Content-Type':'application/json'},
          body: JSON.stringify({to_role: role})
        });
        load();
        const opts = $('transfer-drawer-opts');
        if (opts) opts.style.display = 'none';
      } catch (e) { alert('Erro: ' + e.message); }
    });
  },

  async escalate(id) {
    _confirm('Escalar para Director', 'O alerta será marcado como Severidade 4 e encaminhado para o Director.', async () => {
      try {
        await fetch(`/api/alerts/${id}/transfer`, {
          method: 'PATCH', headers: {'Content-Type':'application/json'},
          body: JSON.stringify({to_role: 'Director'})
        });
        load();
      } catch (e) { alert('Erro: ' + e.message); }
    });
  }
};

load();
setInterval(load, 5000);
