/* logistica.js — international logistics view */
'use strict';
const $ = id => document.getElementById(id);
const fetchJSON = async (url, opts) => { const r = await fetch(url, opts); if (!r.ok) throw new Error(r.status); return r.json(); };

const STATUS_LABELS = {
  active: 'Produção', in_progress: 'Produção', open: 'Produção',
  completed: 'Entregue'
};
const STATUS_COLORS = {
  active: 'var(--secondary)', in_progress: 'var(--secondary)',
  open: 'var(--amber)', completed: 'var(--tertiary)'
};

// Country to emoji flag mapping (only emojis allowed = country flags)
const FLAGS = {
  'Brasil': '🇧🇷', 'USA': '🇺🇸', 'Itália': '🇮🇹', 'França': '🇫🇷',
  'Benelux': '🇧🇪', 'Dubai': '🇦🇪', 'Kuwait': '🇰🇼', 'Israel': '🇮🇱',
  'Índia': '🇮🇳', 'Grécia': '🇬🇷', 'UK': '🇬🇧', 'Marrocos': '🇲🇦',
  'Bahamas': '🇧🇸', 'Paraguai': '🇵🇾', 'Portugal': '🇵🇹',
};

const EXPORT_COUNTRIES = ['Brasil', 'USA', 'Itália', 'França', 'Dubai', 'UK', 'Marrocos', 'Benelux'];

async function loadExportOrders() {
  try {
    const orders = await fetchJSON('/api/orders?limit=40');
    const host = $('export-orders');
    if (!host) return;
    // Simulate export assignments from order index
    const exportOrders = orders.filter((_, i) => i % 3 !== 0); // ~66% are export
    const byCountry = {};
    exportOrders.forEach((o, i) => {
      const country = EXPORT_COUNTRIES[i % EXPORT_COUNTRIES.length];
      if (!byCountry[country]) byCountry[country] = { orders: 0, m2: 0, value: 0 };
      byCountry[country].orders++;
      byCountry[country].m2 += o.total_m2 || 0;
      byCountry[country].value += (o.total_m2 || 0) * 1800;
    });
    host.innerHTML = Object.entries(byCountry).map(([country, data]) => `
      <div class="metric-row" style="display:flex;align-items:center;gap:12px;">
        <span style="font-size:20px;flex-shrink:0;">${FLAGS[country] || ''}</span>
        <div style="flex:1;min-width:0;">
          <div style="font-size:13px;font-weight:500;color:var(--primary);">${country}</div>
          <div style="font-size:11px;color:var(--ink-hint);">${data.orders} enc. · ${data.m2.toFixed(0)} m²</div>
        </div>
        <div style="font-family:'DM Mono',monospace;font-size:13px;color:var(--secondary);">
          ${(data.value/1000).toFixed(0)}k EUR
        </div>
      </div>`).join('');

    // Also populate shipments table
    const tbody = $('shipments-tbody');
    if (tbody) {
      tbody.innerHTML = exportOrders.slice(0, 10).map((o, i) => {
        const country = EXPORT_COUNTRIES[i % EXPORT_COUNTRIES.length];
        const label = STATUS_LABELS[o.status] || o.status;
        const color = STATUS_COLORS[o.status] || 'var(--ink-hint)';
        return `<tr>
          <td style="font-family:'DM Mono',monospace;font-size:11px;">${o.id || o.order_id}</td>
          <td>${FLAGS[country] || ''} ${country}</td>
          <td><span style="font-size:11px;color:${color};font-weight:500;">${label}</span></td>
        </tr>`;
      }).join('');
    }
  } catch (e) { console.error(e); }
}

async function loadPartners() {
  try {
    const partners = await fetchJSON('/api/logistics/partners');
    const host = $('partners-list');
    if (!host) return;
    host.innerHTML = partners.map(p => `
      <div class="card" style="padding:16px;">
        <div style="font-size:13px;font-weight:500;color:var(--primary);">${p.name}</div>
        <div style="font-size:11px;color:var(--ink-hint);margin-top:2px;">${p.type}</div>
        <div style="font-family:'DM Mono',monospace;font-size:11px;color:var(--secondary);margin-top:6px;">
          ${p.avg_delivery_days} dias avg.
        </div>
        <button class="catalog-item__add" style="margin-top:10px;width:100%;"
          onclick="requestQuote('${p.id}')">
          Solicitar Cotação
        </button>
      </div>`).join('');
  } catch (e) { console.error(e); }
}

async function requestQuote(partnerId) {
  if (!confirm('Solicitar cotação logística?')) return;
  try {
    const r = await fetchJSON('/api/logistics/quote', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({partner_id: partnerId, order_ids: [], destination_country: 'Brasil'})
    });
    alert(`Cotação ${r.quote_ref}: ${r.estimated_days} dias · ${r.estimated_eur} EUR`);
  } catch (e) { alert('Erro ao solicitar cotação.'); }
}

loadExportOrders();
loadPartners();
