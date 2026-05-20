/* escala.js — trends chart + priorities + env context */
'use strict';
const $ = id => document.getElementById(id);
const fetchJSON = async (url, opts) => { const r = await fetch(url, opts); if (!r.ok) throw new Error(r.status); return r.json(); };

// ── Trends SVG chart ──────────────────────────────────────────────
function renderTrends(data) {
  const host = $('trends-chart');
  if (!host || !data.terms?.length) return;
  const W = host.offsetWidth || 600, H = host.offsetHeight || 260;
  const PAD = {l:48, r:24, t:16, b:32};
  const terms = data.terms;
  const COLORS = ['#1B3A21','#4A7C59','#6FAF82','#C9821A'];
  const months = terms[0]?.series?.map((_,i) => {
    const d = new Date(); d.setMonth(d.getMonth() - (terms[0].series.length - 1 - i));
    return d.toLocaleDateString('pt-PT',{month:'short'});
  }) || [];

  const allVals = terms.flatMap(t => t.series || []).filter(v => v != null);
  const minV = Math.min(...allVals), maxV = Math.max(...allVals) || 100;
  const scaleX = i => PAD.l + (i / Math.max(months.length-1,1)) * (W - PAD.l - PAD.r);
  const scaleY = v => PAD.t + (1 - (v - minV) / Math.max(maxV - minV, 1)) * (H - PAD.t - PAD.b);

  let svg = `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:100%;font-family:'DM Sans',sans-serif">`;

  // Grid
  [0,25,50,75,100].forEach(v => {
    const y = scaleY(v);
    svg += `<line x1="${PAD.l}" y1="${y}" x2="${W-PAD.r}" y2="${y}" stroke="rgba(27,58,33,0.08)" stroke-width="1"/>`;
    svg += `<text x="${PAD.l-8}" y="${y+4}" text-anchor="end" font-size="10" fill="rgba(27,58,33,0.4)">${v}</text>`;
  });
  months.forEach((m, i) => {
    svg += `<text x="${scaleX(i)}" y="${H-PAD.b+18}" text-anchor="middle" font-size="10" fill="rgba(27,58,33,0.4)">${m}</text>`;
  });

  terms.forEach((t, ti) => {
    const color = COLORS[ti % COLORS.length];
    const series = t.series || [];
    const pts = series.map((v,i) => `${scaleX(i)},${scaleY(v)}`).join(' ');
    const areaPath = `M${scaleX(0)},${scaleY(minV)} ` +
      series.map((v,i) => `L${scaleX(i)},${scaleY(v)}`).join(' ') +
      ` L${scaleX(series.length-1)},${scaleY(minV)} Z`;
    svg += `<path d="${areaPath}" fill="${color}" opacity="0.05"/>`;
    svg += `<polyline points="${pts}" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>`;
    series.forEach((v,i) => {
      if (i === series.length-1)
        svg += `<circle cx="${scaleX(i)}" cy="${scaleY(v)}" r="3" fill="#fff" stroke="${color}" stroke-width="2"/>`;
    });
    svg += `<text x="${scaleX(series.length-1)+8}" y="${scaleY(series[series.length-1])+4}" font-size="11" fill="${color}">${t.term}</text>`;
  });
  svg += '</svg>';
  host.innerHTML = svg;
}

// ── Priorities ────────────────────────────────────────────────────
function renderPriorities(items) {
  const host = $('priorities-list');
  if (!host) return;
  // Keep section title
  const title = host.querySelector('.section-title');
  host.innerHTML = '';
  if (title) host.appendChild(title);
  items.forEach(p => {
    const div = document.createElement('div');
    div.className = 'priority-card';
    div.innerHTML = `
      <div class="priority-card__title">${p.title}</div>
      <div class="priority-card__conf">Confianca ${Math.round(p.confidence*100)}% · ${p.horizon_months} meses</div>
      <div class="priority-bar"><div class="priority-bar__fill" style="width:${p.confidence*100}%"></div></div>`;
    host.appendChild(div);
  });
}

// ── Environment ───────────────────────────────────────────────────
async function loadEnv() {
  try {
    const e = await fetchJSON('/api/environment');
    const set = (id, val) => { const el=$(id); if(el) el.textContent = val ?? '--'; };
    set('env-temp', e.temp_c ?? e.temperature_c);
    set('env-hum',  e.humidity_pct);
    set('env-co2',  e.grid_co2_g_kwh ?? e.co2_grid);
    const src = $('env-source');
    if (src) src.textContent = `Fonte: ${e.source || 'IPMA Esposende · REN'}`;
  } catch {}
}

// ── Init ──────────────────────────────────────────────────────────
async function init() {
  try {
    const [trendsData, priorities] = await Promise.all([
      fetchJSON('/api/scale/trends'),
      fetchJSON('/api/scale/priorities')
    ]);
    renderTrends(trendsData);
    renderPriorities(priorities);
  } catch {}
  loadEnv();
}
init();
