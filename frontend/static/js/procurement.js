/* procurement.js — product configurator */
'use strict';
const $ = id => document.getElementById(id);
const fetchJSON = async (url, opts) => { const r = await fetch(url, opts); if (!r.ok) throw new Error(r.status); return r.json(); };

const RAL_COLORS = {
  'RAL 9005': '#0a0a0a', 'RAL 7016': '#293133', 'RAL 9010': '#f4f4f0',
  'RAL 9006': '#a5a5a5', 'RAL 8022': '#1a1a1a', 'Personalizado': '#6FAF82',
  'Carvalho natural': '#8B6914', 'Nogueira': '#5C3D1E', 'Wengué': '#2C1A10',
};
const TYPE_LABELS = {
  sliding:'Deslizante', sliding_opening:'Deslizante/Abertura', opening:'Abertura',
  pivot:'Pivot', curved:'Curvo', screen:'Estore', facade:'Fachada', sliding_door:'Porta Deslizante',
};

let _product = null;
let _color   = '';
let _glass   = '';

// Build left product list
function buildProductList() {
  const host = $('product-list');
  if (!host) return;
  host.innerHTML = (window.PRODUCTS_CFG || []).map(p => `
    <div id="pcard-${p.id}" onclick="Cfg.select('${p.id}')"
         style="padding:12px 14px;border:1px solid var(--hairline);border-radius:12px;cursor:pointer;transition:all 0.12s;margin-bottom:4px;">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:6px;">
        <span style="font-size:14px;font-weight:500;color:var(--primary);">${p.name}</span>
        <span style="font-family:'DM Mono',monospace;font-size:9px;color:var(--ink-hint);text-transform:uppercase;border:1px solid var(--hairline);border-radius:4px;padding:1px 5px;white-space:nowrap;">${TYPE_LABELS[p.type]||p.type}</span>
      </div>
      <div style="font-size:11px;color:var(--ink-hint);margin-top:4px;line-height:1.3;">${p.description}</div>
    </div>`).join('');
}

function selectProductCard(id) {
  document.querySelectorAll('[id^=pcard-]').forEach(el => {
    el.style.borderColor = '';
    el.style.background  = '';
  });
  const card = $(`pcard-${id}`);
  if (card) { card.style.borderColor = 'var(--primary)'; card.style.background = 'var(--surface-soft)'; }
}

const Cfg = {
  select(id) {
    _product = (window.PRODUCTS_CFG || []).find(p => p.id === id);
    if (!_product) return;
    selectProductCard(id);

    // Show panels
    const cfgEl = $('configurator');
    const specsEl = $('specs-panel');
    if (cfgEl) { cfgEl.style.display = 'flex'; }
    if (specsEl) { specsEl.style.display = 'flex'; }

    // Populate centre
    const nm = $('cfg-product-name'); if (nm) nm.textContent = _product.name;
    const ds = $('cfg-product-desc'); if (ds) ds.textContent = _product.description;

    // Colors
    _color = _product.colors[0] || '';
    const colorHost = $('cfg-colors');
    if (colorHost) {
      colorHost.innerHTML = _product.colors.map(c => {
        const hex = RAL_COLORS[c] || '#888';
        return `<button onclick="Cfg.setColor(this,'${c}')"
          style="width:28px;height:28px;border-radius:50%;background:${hex};border:2px solid ${c===_color?'var(--primary)':'var(--hairline)'};cursor:pointer;" title="${c}"></button>`;
      }).join('');
    }

    // Glass
    _glass = (_product.glass_options || [])[0] || '';
    const glassHost = $('cfg-glass');
    if (glassHost) {
      glassHost.innerHTML = (_product.glass_options || []).map(g =>
        `<button class="chat-chip ${g===_glass?'is-selected':''}" onclick="Cfg.setGlass(this,'${g}')"
           style="${g===_glass?'background:var(--primary);color:#fff;border-color:var(--primary)':''}">${g}</button>`
      ).join('');
    }

    // Set min delivery date
    const del = $('cfg-delivery');
    if (del) {
      const minDate = new Date();
      minDate.setDate(minDate.getDate() + _product.lead_time_days);
      del.min = minDate.toISOString().slice(0,10);
      del.value = minDate.toISOString().slice(0,10);
    }

    // Motor label
    const motLabel = $('cfg-motor-label');
    const motCheck = $('cfg-motorized');
    if (motCheck && motLabel) {
      motCheck.onchange = () => { motLabel.textContent = motCheck.checked ? 'Sim' : 'Não'; };
    }

    // Specs panel
    const specsContent = $('cfg-specs-content');
    if (specsContent && _product.specs) {
      const s = _product.specs;
      specsContent.innerHTML = `
        <div class="metric-row">
          <span class="metric-row__label">Perfil visível</span>
          <span class="metric-row__value" style="font-size:20px;">${_product.profile_mm}</span>
          <span class="metric-row__unit">mm</span>
        </div>
        ${s.uw_value != null ? `<div class="metric-row">
          <span class="metric-row__label">Isolamento Uw</span>
          <span class="metric-row__value" style="font-size:20px;">${s.uw_value}</span>
          <span class="metric-row__unit">W/m²K</span>
        </div>` : ''}
        ${s.rw_db != null ? `<div class="metric-row">
          <span class="metric-row__label">Isolamento Acústico</span>
          <span class="metric-row__value" style="font-size:20px;">${s.rw_db}</span>
          <span class="metric-row__unit">dB</span>
        </div>` : ''}
        <div class="metric-row">
          <span class="metric-row__label">Vão máximo</span>
          <span class="metric-row__value" style="font-size:20px;">${s.max_span_m}</span>
          <span class="metric-row__unit">m</span>
        </div>
        <div class="metric-row">
          <span class="metric-row__label">Prazo de entrega</span>
          <span class="metric-row__value" style="font-size:20px;">${_product.lead_time_days}</span>
          <span class="metric-row__unit">dias</span>
        </div>
        <div style="margin-top:12px;">
          <div class="section-title">Certificações</div>
          <div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:6px;">
            ${(_product.certifications||[]).map(cert =>
              `<span style="font-size:10px;border:1px solid var(--hairline);border-radius:4px;padding:2px 7px;color:var(--secondary);">${cert}</span>`
            ).join('')}
          </div>
        </div>
        <a href="/portfolio" style="display:block;margin-top:16px;font-size:12px;color:var(--secondary);text-decoration:underline;">Ver Portfolio</a>`;
    }

    this.calc();
  },

  setColor(btn, color) {
    _color = color;
    document.querySelectorAll('#cfg-colors button').forEach(b => b.style.borderColor = 'var(--hairline)');
    btn.style.borderColor = 'var(--primary)';
  },

  setGlass(btn, glass) {
    _glass = glass;
    document.querySelectorAll('#cfg-glass button').forEach(b => {
      b.style.background = ''; b.style.color = ''; b.style.borderColor = '';
    });
    btn.style.background = 'var(--primary)';
    btn.style.color = '#fff';
    btn.style.borderColor = 'var(--primary)';
  },

  calc() {
    if (!_product) return;
    const w = parseFloat($('cfg-width')?.value || 1200);
    const h = parseFloat($('cfg-height')?.value || 2200);
    const u = parseInt($('cfg-units')?.value || 1);
    const m2 = (w * h * u / 1_000_000).toFixed(2);
    const motorized = $('cfg-motorized')?.checked;
    const mid = (_product.price_min_eur + _product.price_max_eur) / 2;
    const est = Math.round(mid * u + (motorized ? 800 : 0));
    const m2El = $('cfg-m2'); if (m2El) m2El.textContent = m2;
    const valEl = $('cfg-value'); if (valEl) {
      const k = est >= 1000 ? `${(est/1000).toFixed(0)}k` : est;
      valEl.textContent = `A partir de €${k}`;
    }
  },

  async submit() {
    if (!_product) return;
    if (!confirm('Confirmas o envio do pedido de proposta?')) return;
    const body = {
      product_id: _product.id,
      width_mm:   parseFloat($('cfg-width')?.value || 1200),
      height_mm:  parseFloat($('cfg-height')?.value || 2200),
      units:      parseInt($('cfg-units')?.value || 1),
      color:      _color,
      glass:      _glass,
      motorized:  $('cfg-motorized')?.checked || false,
      client:     $('cfg-client')?.value || '',
      architect:  $('cfg-architect')?.value || '',
      delivery_date: $('cfg-delivery')?.value || '',
      country:    $('cfg-country')?.value || 'Portugal',
      notes:      $('cfg-notes')?.value || '',
    };
    try {
      const r = await fetchJSON('/api/orders/quote', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify(body),
      });
      const res = $('cfg-result');
      if (res) res.textContent = `Proposta ${r.quote_ref} criada · €${r.estimated_eur.toLocaleString('pt-PT')} · entrega em ${r.lead_time_days} dias · válida até ${r.valid_until}`;
    } catch (e) { alert('Erro ao criar proposta: ' + e.message); }
  },
};

buildProductList();
