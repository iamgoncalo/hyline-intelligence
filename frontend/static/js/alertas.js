/* alertas.js — alertas page: 4-column kanban board */
'use strict';
const $ = id => document.getElementById(id);
const fetchJSON = async (url, opts) => { const r = await fetch(url, opts); if (!r.ok) throw new Error(r.status); return r.json(); };

const ROLES = ['Director','HST','DQ','ChefeTurno'];

function sevClass(sev) {
  if (sev >= 4) return 'sev-4';
  if (sev >= 3) return 'sev-3';
  return 'sev-2';
}

function renderCard(a) {
  const sc = sevClass(a.severity || 2);
  const ts = (a.ts || '').slice(11,16);
  const id = `card-${a.id}`;
  return `<div class="alert-card ${sc}" id="${id}">
    <div class="alert-card__station">${a.station_name || '--'}</div>
    <div class="alert-card__type">${(a.alert_type||'').replace(/_/g,' ')}</div>
    <div class="alert-card__msg">${a.message || ''}</div>
    <div class="alert-card__footer">SEV ${a.severity||'?'} · ${ts}</div>
    <div class="alert-card__actions">
      <button class="alert-action" onclick="Alerts.resolve(${a.id})">Resolver</button>
      <button class="alert-action" onclick="Alerts.showTransfer(${a.id})">Transferir</button>
    </div>
    <div class="transfer-options" id="tf-${a.id}">
      ${ROLES.map(r => `<button class="transfer-opt" onclick="Alerts.transfer(${a.id},'${r}')">${r}</button>`).join('')}
    </div>
  </div>`;
}

async function load() {
  try {
    const alerts = await fetchJSON('/api/alerts?limit=50');
    ROLES.forEach(role => {
      const list = $(`list-${role}`);
      const cnt  = $(`cnt-${role}`);
      if (!list) return;
      const mine = alerts.filter(a => a.routed_to === role);
      if (cnt) cnt.textContent = mine.length;
      list.innerHTML = mine.length ? mine.map(renderCard).join('') : '<div class="alert-col__empty">Sem alertas</div>';
    });
  } catch (e) { console.error(e); }
}

const Alerts = {
  showTransfer(id) {
    const el = $(`tf-${id}`);
    if (el) el.classList.toggle('is-open');
  },
  async transfer(id, role) {
    if (!confirm(`Transferir alerta para ${role}?`)) return;
    try {
      await fetch(`/api/alerts/${id}/transfer`, {
        method:'PATCH',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({to_role: role})
      });
      load();
    } catch (e) { alert('Erro: ' + e.message); }
  },
  async resolve(id) {
    if (!confirm('Confirmas a resolucao deste alerta?')) return;
    try {
      await fetch(`/api/alerts/${id}/resolve`, {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({confirmed:true, note:'Resolvido via dashboard'})
      });
      load();
    } catch (e) { alert('Erro: ' + e.message); }
  }
};

load();
setInterval(load, 5000);
