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

const RAL_HEX = {
  'RAL 9005': '#0a0a0a', 'RAL 7016': '#293133', 'RAL 9010': '#f4f4f0',
  'RAL 9006': '#a5a5a5', 'RAL 8022': '#1a1a1a',
};

function renderProductSVG(product) {
  const pmm = product.profile_mm || 40;
  const profileLabel = `perfil visível: ${pmm}mm`;
  const isWood = product.id === 'HYPIWOOD' || product.id === 'HYSTYLEWOOD';
  const stroke = isWood ? '#8B6914' : 'var(--primary)';
  const glass = `rgba(111,175,130,0.06)`;
  const type = product.type;

  if (type === 'sliding' || type === 'sliding_opening' || type === 'sliding_door') {
    // Two sliding panels
    const woodGrain = isWood ? `<line x1="30" y1="60" x2="130" y2="60" stroke="${stroke}" stroke-width="0.4" opacity="0.4"/>
      <line x1="30" y1="80" x2="130" y2="80" stroke="${stroke}" stroke-width="0.4" opacity="0.4"/>
      <line x1="30" y1="100" x2="130" y2="100" stroke="${stroke}" stroke-width="0.4" opacity="0.4"/>
      <line x1="30" y1="120" x2="130" y2="120" stroke="${stroke}" stroke-width="0.4" opacity="0.4"/>
      <line x1="140" y1="60" x2="260" y2="60" stroke="${stroke}" stroke-width="0.4" opacity="0.4"/>
      <line x1="140" y1="80" x2="260" y2="80" stroke="${stroke}" stroke-width="0.4" opacity="0.4"/>
      <line x1="140" y1="100" x2="260" y2="100" stroke="${stroke}" stroke-width="0.4" opacity="0.4"/>
      <line x1="140" y1="120" x2="260" y2="120" stroke="${stroke}" stroke-width="0.4" opacity="0.4"/>` : '';
    return `<svg viewBox="0 0 300 200" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="20" y="20" width="260" height="160" rx="2" stroke="${stroke}" stroke-width="1.5"/>
      <rect x="25" y="25" width="120" height="150" rx="1" stroke="${stroke}" stroke-width="1"/>
      <rect x="140" y="25" width="135" height="150" rx="1" stroke="${stroke}" stroke-width="1"/>
      <rect x="26" y="26" width="118" height="148" fill="${glass}"/>
      <rect x="141" y="26" width="133" height="148" fill="${glass}"/>
      ${woodGrain}
      <rect x="190" y="88" width="4" height="24" rx="2" fill="${stroke}"/>
      <line x1="20" y1="12" x2="280" y2="12" stroke="var(--tertiary)" stroke-width="0.5"/>
      <text x="150" y="9" text-anchor="middle" font-family="DM Mono" font-size="8" fill="var(--tertiary)">largura configurável</text>
      <text x="150" y="195" text-anchor="middle" font-family="DM Mono" font-size="9" fill="var(--ink-hint)">${profileLabel}</text>
    </svg>`;
  }

  if (type === 'opening') {
    // Tilt-turn window with opening arc
    return `<svg viewBox="0 0 300 200" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="20" y="20" width="260" height="160" rx="2" stroke="${stroke}" stroke-width="1.5"/>
      <rect x="25" y="25" width="250" height="150" rx="1" fill="${glass}" stroke="${stroke}" stroke-width="1"/>
      <circle cx="26" cy="40" r="3" fill="${stroke}"/>
      <circle cx="26" cy="160" r="3" fill="${stroke}"/>
      <rect x="266" y="88" width="4" height="24" rx="2" fill="${stroke}"/>
      <path d="M 275 100 Q 220 55 150 26" stroke="var(--tertiary)" stroke-width="0.75" stroke-dasharray="4,3"/>
      <path d="M 150 175 L 275 100" stroke="var(--tertiary)" stroke-width="0.75" stroke-dasharray="4,3"/>
      <text x="150" y="195" text-anchor="middle" font-family="DM Mono" font-size="9" fill="var(--ink-hint)">${profileLabel}</text>
    </svg>`;
  }

  if (type === 'pivot') {
    // Tall pivot door with centre axis
    const woodGrain2 = isWood ? `<line x1="95" y1="30" x2="95" y2="175" stroke="${stroke}" stroke-width="0.4" opacity="0.35"/>
      <line x1="115" y1="30" x2="115" y2="175" stroke="${stroke}" stroke-width="0.4" opacity="0.35"/>
      <line x1="175" y1="30" x2="175" y2="175" stroke="${stroke}" stroke-width="0.4" opacity="0.35"/>
      <line x1="195" y1="30" x2="195" y2="175" stroke="${stroke}" stroke-width="0.4" opacity="0.35"/>` : '';
    return `<svg viewBox="0 0 300 220" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="60" y="20" width="180" height="185" rx="2" stroke="${stroke}" stroke-width="1.5"/>
      <rect x="65" y="25" width="170" height="175" rx="1" fill="${glass}" stroke="${stroke}" stroke-width="0.8"/>
      ${woodGrain2}
      <line x1="150" y1="20" x2="150" y2="205" stroke="${stroke}" stroke-width="1.5" stroke-dasharray="0"/>
      <circle cx="150" cy="20" r="4" fill="${stroke}"/>
      <circle cx="150" cy="205" r="4" fill="${stroke}"/>
      <path d="M 150 112 Q 120 70 65 45" stroke="var(--tertiary)" stroke-width="0.75" stroke-dasharray="5,3"/>
      <path d="M 150 112 Q 180 70 235 45" stroke="var(--tertiary)" stroke-width="0.75" stroke-dasharray="5,3"/>
      <text x="150" y="218" text-anchor="middle" font-family="DM Mono" font-size="9" fill="var(--ink-hint)">eixo central · ${profileLabel}</text>
    </svg>`;
  }

  if (type === 'curved') {
    // Curved frame
    return `<svg viewBox="0 0 300 200" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M 30 20 Q 150 5 270 20 L 270 180 Q 150 195 30 180 Z" stroke="${stroke}" stroke-width="1.5" fill="${glass}"/>
      <path d="M 36 30 Q 150 18 264 30 L 264 170 Q 150 182 36 170 Z" stroke="${stroke}" stroke-width="0.8" fill="none"/>
      <rect x="252" y="88" width="4" height="24" rx="2" fill="${stroke}"/>
      <path d="M 30 5 Q 150 -12 270 5" stroke="var(--tertiary)" stroke-width="0.5" stroke-dasharray="3,2"/>
      <text x="150" y="195" text-anchor="middle" font-family="DM Mono" font-size="9" fill="var(--ink-hint)">sistema curvo · ${profileLabel}</text>
    </svg>`;
  }

  if (type === 'facade') {
    // Curtain wall grid
    const panels = [];
    for (let col = 0; col < 3; col++) {
      for (let row = 0; row < 4; row++) {
        const x = 20 + col * 88, y = 20 + row * 42;
        panels.push(`<rect x="${x}" y="${y}" width="83" height="37" fill="${glass}" stroke="${stroke}" stroke-width="0.8"/>`);
      }
    }
    return `<svg viewBox="0 0 300 200" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="18" y="18" width="264" height="170" rx="1" stroke="${stroke}" stroke-width="1.5"/>
      ${panels.join('')}
      <text x="150" y="198" text-anchor="middle" font-family="DM Mono" font-size="9" fill="var(--ink-hint)">fachada · vão máximo ${product.specs?.max_span_m||8}m</text>
    </svg>`;
  }

  if (type === 'screen') {
    // Screen/protection rolled at top
    return `<svg viewBox="0 0 300 200" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="20" y="20" width="260" height="160" rx="2" stroke="${stroke}" stroke-width="1.5"/>
      <rect x="25" y="25" width="250" height="150" rx="1" fill="${glass}" stroke="${stroke}" stroke-width="0.8"/>
      <rect x="20" y="14" width="260" height="14" rx="2" stroke="${stroke}" stroke-width="1" fill="var(--surface-soft)"/>
      ${[35,45,55,65,75,85].map(y => `<line x1="25" y1="${y}" x2="275" y2="${y}" stroke="${stroke}" stroke-width="1.5" opacity="0.5"/>`).join('')}
      <text x="150" y="195" text-anchor="middle" font-family="DM Mono" font-size="9" fill="var(--ink-hint)">HYFLY · Red Dot Award</text>
    </svg>`;
  }

  // Fallback: generic window
  return `<svg viewBox="0 0 300 200" fill="none" xmlns="http://www.w3.org/2000/svg">
    <rect x="20" y="20" width="260" height="160" rx="2" stroke="${stroke}" stroke-width="1.5"/>
    <rect x="25" y="25" width="250" height="150" fill="${glass}" stroke="${stroke}" stroke-width="0.8"/>
    <text x="150" y="115" text-anchor="middle" font-family="Cormorant Garamond" font-size="20" fill="${stroke}">${product.name}</text>
    <text x="150" y="195" text-anchor="middle" font-family="DM Mono" font-size="9" fill="var(--ink-hint)">${profileLabel}</text>
  </svg>`;
}

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
        <div style="display:flex;align-items:center;gap:8px;">
          <div style="width:40px;height:30px;flex-shrink:0;opacity:0.7;">${renderProductSVG(p)}</div>
          <span style="font-size:14px;font-weight:500;color:var(--primary);">${p.name}</span>
        </div>
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
      // Show SVG illustration in specs panel (prepend after innerHTML is set)
      const illusDiv = document.createElement('div');
      illusDiv.className = 'product-illustration';
      illusDiv.style.cssText = 'width:100%;margin-bottom:16px;opacity:0.85;';
      illusDiv.innerHTML = renderProductSVG(_product);
      specsContent.insertBefore(illusDiv, specsContent.firstChild);
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
    const _confirm2 = (t, b, fn) => (window.confirm2 ? window.confirm2(t, b, fn) : (confirm(`${t}\n${b}`) && fn()));
    const units = parseInt($('cfg-units')?.value || 1);
    const client = $('cfg-client')?.value || 'Cliente';
    _confirm2(
      'Solicitar Proposta',
      `${_product.name} · ${units} unidade${units!==1?'s':''} · ${client}`,
      async () => {
        const body = {
          product_id: _product.id,
          width_mm:   parseFloat($('cfg-width')?.value || 1200),
          height_mm:  parseFloat($('cfg-height')?.value || 2200),
          units:      parseInt($('cfg-units')?.value || 1),
          color:      _color, glass: _glass,
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
      }
    );
  },
};

buildProductList();
