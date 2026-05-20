/* portfolio.js — project portfolio with country filtering */
'use strict';

let _filter = '';

const TYPE_LABELS = {
  sliding: 'Deslizante', sliding_opening: 'Deslizante/Abertura',
  opening: 'Abertura', pivot: 'Pivot', curved: 'Curvo',
  screen: 'Estore', facade: 'Fachada', sliding_door: 'Porta Deslizante',
};

function renderGrid() {
  const host = document.getElementById('portfolio-grid');
  if (!host) return;
  const data = (window.PORTFOLIO_DATA || []).filter(p =>
    !_filter || p.location.toLowerCase().includes(_filter.toLowerCase())
  );
  if (!data.length) {
    host.innerHTML = '<div style="font-size:13px;color:var(--ink-hint);padding:16px;">Sem projectos para este filtro.</div>';
    return;
  }
  host.innerHTML = data.map(p => `
    <div class="priority-card" style="cursor:default;transition:transform 0.15s,border-color 0.15s;"
         onmouseenter="this.style.transform='translateY(-2px)';this.style.borderColor='var(--tertiary)'"
         onmouseleave="this.style.transform='';this.style.borderColor=''">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
        <span style="font-family:'DM Mono',monospace;font-size:10px;color:var(--secondary);font-weight:500;text-transform:uppercase;letter-spacing:0.1em;">${p.product}</span>
        <span style="font-family:'DM Mono',monospace;font-size:11px;color:var(--ink-hint);">${p.year}</span>
      </div>
      <div style="font-family:'Cormorant Garamond',serif;font-size:20px;color:var(--primary);line-height:1.2;margin-bottom:6px;">${p.location}</div>
      <div style="font-size:12px;color:var(--ink-hint);">${p.type}</div>
    </div>`).join('');
}

const Portfolio = {
  filter(btn, country) {
    document.querySelectorAll('.cat-chip').forEach(b => b.classList.remove('is-active'));
    btn.classList.add('is-active');
    _filter = country;
    renderGrid();
  }
};

renderGrid();
