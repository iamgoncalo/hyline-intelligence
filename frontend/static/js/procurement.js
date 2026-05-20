/* procurement.js — catalog + cart */
'use strict';
const $ = id => document.getElementById(id);
const fetchJSON = async (url, opts) => { const r = await fetch(url, opts); if (!r.ok) throw new Error(r.status); return r.json(); };

let activeCat = '';
let ecoOnly = false;
let catalog = [];

function ecoClass(score) {
  return score >= 85 ? '<span class="eco-badge">ECO</span>' : '';
}

function renderCatalog() {
  const grid = $('catalog-grid');
  if (!grid) return;
  let items = catalog;
  if (activeCat) items = items.filter(i => i.category === activeCat);
  if (ecoOnly)   items = items.filter(i => i.sustainability_score >= 85);

  const lbl = $('cat-label');
  if (lbl) lbl.textContent = `${items.length} item${items.length!==1?'s':''}`;

  grid.innerHTML = items.map(i => `
    <div class="catalog-item">
      <div class="catalog-item__name">${i.name}${ecoClass(i.sustainability_score)}</div>
      <span class="catalog-item__score">${i.sustainability_score}</span>
      <div class="catalog-item__meta">${i.unit} · ${i.price_eur.toFixed(2)} EUR · CO&#x2082; ${i.co2_per_unit} kg/un</div>
      <button class="catalog-item__add" onclick="Proc.add('${i.id}')">Adicionar</button>
    </div>`).join('') || '<div style="font-size:13px;color:var(--ink-hint);">Sem itens</div>';
}

async function loadCart() {
  try {
    const cart = await fetchJSON('/api/procurement/cart');
    const list = $('cart-list');
    const btn  = $('cart-checkout');
    if (!list) return;
    if (!cart.length) {
      list.innerHTML = '<div class="cart-empty">Carrinho vazio</div>';
      if (btn) btn.style.display = 'none';
      return;
    }
    list.innerHTML = cart.map(item => `
      <div class="cart-item">
        <span class="cart-item__name">${item.name || item.catalog_id} ×${item.quantity}</span>
        <button class="cart-item__remove" onclick="Proc.remove(${item.id})">Remover</button>
      </div>`).join('');
    if (btn) btn.style.display = '';
  } catch {}
}

const Proc = {
  filterCat(btn, cat) {
    document.querySelectorAll('.cat-chip').forEach(b => b.classList.remove('is-active'));
    btn.classList.add('is-active');
    activeCat = cat;
    renderCatalog();
  },
  async add(catalogId) {
    if (!confirm(`Adicionar ao carrinho?`)) return;
    try {
      await fetchJSON('/api/procurement/cart/add', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({catalog_id: catalogId, quantity: 1})
      });
      loadCart();
    } catch (e) { alert('Erro: ' + e.message); }
  },
  async remove(cartId) {
    try {
      await fetch(`/api/procurement/cart/${cartId}`, {method:'DELETE'});
      loadCart();
    } catch {}
  },
  async checkout() {
    if (!confirm('Confirmas a compra de todos os itens do carrinho?')) return;
    try {
      await fetchJSON('/api/procurement/checkout', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({confirmed: true})
      });
      alert('Compra confirmada. Accao registada.');
      loadCart();
    } catch (e) { alert('Erro: ' + e.message); }
  }
};

// Eco toggle
const ecoInput = document.getElementById('eco-filter');
if (ecoInput) ecoInput.addEventListener('change', () => { ecoOnly = ecoInput.checked; renderCatalog(); });

// Init
(async () => {
  try { catalog = await fetchJSON('/api/procurement/catalog'); renderCatalog(); } catch {}
  loadCart();
})();
