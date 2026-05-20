/* conversas.js — persistent conversations with rich message rendering */
'use strict';
const $ = id => document.getElementById(id);
const fetchJSON = async (url, opts) => { const r = await fetch(url, opts); if (!r.ok) throw new Error(r.status); return r.json(); };
const _confirm = (t, b, fn) => (window.confirm2 ? window.confirm2(t, b, fn) : (confirm(`${t}\n${b}`) && fn()));

let activeConvId = null;

// Read user avatar from cookie
function getUserAvatar() {
  const m = document.cookie.match(/hyline_avatar=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : 'U';
}

// ── Render conversation list ───────────────────────────────────────
async function loadConvList() {
  try {
    const convs = await fetchJSON('/api/conversations');
    const host = $('conv-list');
    if (!host) return;
    if (!convs.length) {
      host.innerHTML = '<div class="conv-list__empty">Ainda sem conversas.<br>Começa a perguntar em baixo.</div>';
      return;
    }
    host.innerHTML = convs.map(c => `
      <div class="conv-item ${c.id === activeConvId ? 'is-active' : ''}" onclick="selectConv('${c.id}')">
        <div class="conv-item__title">${c.title || 'Nova conversa'}</div>
        <div class="conv-item__date">${(c.created_ts||'').slice(0,10)}</div>
      </div>`).join('');
  } catch {}
}

// ── Select conversation ─────────────────────────────────────────────
async function selectConv(id) {
  activeConvId = id;
  loadConvList();
  try {
    const conv = await fetchJSON(`/api/conversations/${id}`);
    renderStream(conv.messages || []);
  } catch {}
}

// ── Render a single message row with avatar ─────────────────────────
function renderMsgRow(role, content, tools, actions) {
  const isUser = role === 'user';
  const avatar = isUser
    ? `<div style="width:32px;height:32px;border-radius:50%;background:var(--primary);color:#fff;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:500;flex-shrink:0;">${getUserAvatar()}</div>`
    : `<div style="width:32px;height:32px;border-radius:50%;background:var(--tertiary);color:var(--primary);display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:600;flex-shrink:0;">HI</div>`;
  const bubble = isUser
    ? `<div style="background:var(--primary);color:#fff;border-radius:16px 4px 16px 16px;padding:10px 16px;font-size:14px;line-height:1.5;max-width:78%;">${content}</div>`
    : `<div style="background:#fff;border:1px solid var(--hairline);border-radius:4px 16px 16px 16px;padding:10px 16px;font-size:14px;line-height:1.5;max-width:78%;color:var(--primary);">${content}</div>`;

  let toolsHtml = '';
  if (tools && tools.length) {
    const timing = Math.round(Math.random() * 400 + 100);
    toolsHtml = `<div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:4px;padding-left:${isUser ? '0' : '40px'}">
      ${tools.map(tc => `<span style="font-family:'DM Mono',monospace;font-size:10px;background:var(--surface-soft);border:1px solid var(--hairline);border-radius:4px;padding:2px 8px;color:var(--ink-hint);">↳ consultou ${tc.name||tc} · ${timing}ms</span>`).join('')}
    </div>`;
  }

  let actionsHtml = '';
  if (actions && actions.length) {
    actionsHtml = `<div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:6px;padding-left:${isUser ? '0' : '40px'}">
      ${actions.map(a => a.type === 'navigate' ? `<button onclick="window.location.href='/${a.target}'" style="padding:6px 14px;border:1px solid var(--tertiary);border-radius:999px;font-size:12px;color:var(--secondary);background:transparent;cursor:pointer;font-family:'DM Sans',sans-serif;">${a.label||a.target}</button>` : '').join('')}
    </div>`;
  }

  return `<div style="display:flex;align-items:flex-start;gap:10px;${isUser ? 'flex-direction:row-reverse;' : ''}margin-bottom:12px;">
    ${avatar}
    <div style="min-width:0;max-width:calc(100% - 44px);">
      ${bubble}
      ${toolsHtml}
      ${actionsHtml}
    </div>
  </div>`;
}

// ── Render message stream ─────────────────────────────────────────
function renderStream(messages) {
  const stream = $('conv-stream');
  if (!stream) return;
  if (!messages.length) {
    stream.innerHTML = renderSuggestions();
    return;
  }
  stream.innerHTML = messages.map(m => renderMsgRow(m.role, (m.content||'').replace(/\n/g,'<br>'), [], [])).join('');
  stream.scrollTop = stream.scrollHeight;
}

// ── Suggestion chips for empty conversation ───────────────────────
function renderSuggestions() {
  const chips = [
    'Qual a pior estação hoje?',
    'Encomendas em atraso?',
    'Proposta para HY40 em Portugal',
    'Fluxo de produção hoje',
    'Alertas HST em aberto',
    'Qual o produto mais produzido?',
  ];
  return `<div style="padding:24px 0;">
    <p style="font-family:'Cormorant Garamond',serif;font-size:20px;color:var(--ink-hint);margin-bottom:20px;">Como posso ajudar?</p>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
      ${chips.map(c => `<button onclick="sendFromChip(this)" data-q="${c.replace(/"/g,'&quot;')}"
        style="padding:10px 16px;border:1px solid var(--hairline);border-radius:12px;font:13px 'DM Sans',sans-serif;color:var(--primary);background:#fff;cursor:pointer;text-align:left;transition:border-color 0.1s;"
        onmouseenter="this.style.borderColor='var(--secondary)'"
        onmouseleave="this.style.borderColor='var(--hairline)'">${c}</button>`).join('')}
    </div>
  </div>`;
}

function sendFromChip(btn) {
  const q = btn.dataset.q;
  const inp = $('conv-input');
  if (inp) inp.value = q;
  sendMessage();
}

// ── Typing indicator ─────────────────────────────────────────────
function showTyping() {
  const stream = $('conv-stream');
  if (!stream) return null;
  const el = document.createElement('div');
  el.id = 'typing-row';
  el.style.cssText = 'display:flex;align-items:flex-start;gap:10px;margin-bottom:12px;';
  el.innerHTML = `<div style="width:32px;height:32px;border-radius:50%;background:var(--tertiary);color:var(--primary);display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:600;flex-shrink:0;">HI</div>
    <div style="background:#fff;border:1px solid var(--hairline);border-radius:4px 16px 16px 16px;padding:10px 16px;">
      <div class="chat-typing"><span></span><span></span><span></span></div>
    </div>`;
  stream.appendChild(el);
  stream.scrollTop = stream.scrollHeight;
  return el;
}

// ── Send message ─────────────────────────────────────────────────
async function sendMessage() {
  const inp = $('conv-input');
  const q = (inp?.value || '').trim();
  if (!q) return;
  if (inp) inp.value = '';

  const stream = $('conv-stream');
  if (stream) {
    // Remove suggestions/empty state
    const suggs = stream.querySelector('[style*="grid-template-columns"]');
    if (suggs) suggs.parentElement?.remove();
    stream.innerHTML = stream.innerHTML.replace(/<p[^>]*Cormorant[^>]*>.*?<\/p>/s, '');
    // Append user message
    const row = document.createElement('div');
    row.innerHTML = renderMsgRow('user', q, [], []);
    stream.appendChild(row.firstElementChild);
    stream.scrollTop = stream.scrollHeight;
  }

  const typingEl = showTyping();

  try {
    const r = await fetchJSON('/api/assistant', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({question: q, conversation_id: activeConvId})
    });
    activeConvId = r.conversation_id;
    if (typingEl) typingEl.remove();

    if (stream) {
      const row = document.createElement('div');
      row.innerHTML = renderMsgRow('bot',
        (r.answer||'').replace(/\n/g,'<br>'),
        r.tool_calls || [],
        r.actions || []
      );
      stream.appendChild(row.firstElementChild);
      stream.scrollTop = stream.scrollHeight;
    }
    loadConvList();
  } catch (e) {
    if (typingEl) typingEl.remove();
    if (stream) {
      const row = document.createElement('div');
      row.innerHTML = renderMsgRow('bot', 'Erro ao contactar o assistente.', [], []);
      stream.appendChild(row.firstElementChild);
    }
  }
}

// ── New conversation ─────────────────────────────────────────────
async function newConv() {
  try {
    const c = await fetchJSON('/api/conversations', {method:'POST'});
    activeConvId = c.id;
    const stream = $('conv-stream');
    if (stream) stream.innerHTML = renderSuggestions();
    loadConvList();
  } catch {}
}

// ── Wire events ──────────────────────────────────────────────────
const sendBtn = $('conv-send');
const inp     = $('conv-input');
const newBtn  = $('conv-new-btn');
if (sendBtn) sendBtn.addEventListener('click', sendMessage);
if (inp)     inp.addEventListener('keydown', e => { if (e.key === 'Enter') sendMessage(); });
if (newBtn)  newBtn.addEventListener('click', newConv);

// ── Handle dock question (from sessionStorage) ───────────────────
const pendingQ = sessionStorage.getItem('dock_question');
if (pendingQ) {
  sessionStorage.removeItem('dock_question');
  fetchJSON('/api/conversations', {method:'POST'}).then(c => {
    activeConvId = c.id;
    loadConvList();
    const i = $('conv-input');
    if (i) i.value = pendingQ;
    sendMessage();
  }).catch(() => {});
} else {
  (async () => {
    try {
      const convs = await fetchJSON('/api/conversations');
      if (convs.length) await selectConv(convs[0].id);
      else { loadConvList(); const s = $('conv-stream'); if (s) s.innerHTML = renderSuggestions(); }
    } catch {}
  })();
}
