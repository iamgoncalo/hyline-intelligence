/* conversas.js — persistent conversations with Gemini assistant */
'use strict';
const $ = id => document.getElementById(id);
const fetchJSON = async (url, opts) => { const r = await fetch(url, opts); if (!r.ok) throw new Error(r.status); return r.json(); };

let activeConvId = null;

// ── Render conversation list ────────────────────────────────────────
async function loadConvList() {
  try {
    const convs = await fetchJSON('/api/conversations');
    const host = $('conv-list');
    if (!host) return;
    if (!convs.length) {
      host.innerHTML = '<div class="conv-list__empty">Ainda sem conversas.<br>Comeca a perguntar em baixo.</div>';
      return;
    }
    host.innerHTML = convs.map(c => `
      <div class="conv-item ${c.id === activeConvId ? 'is-active' : ''}"
           onclick="selectConv('${c.id}')">
        <div class="conv-item__title">${c.title || 'Nova conversa'}</div>
        <div class="conv-item__date">${(c.created_ts||'').slice(0,10)}</div>
      </div>`).join('');
  } catch {}
}

// ── Select a conversation ───────────────────────────────────────────
async function selectConv(id) {
  activeConvId = id;
  loadConvList();
  try {
    const conv = await fetchJSON(`/api/conversations/${id}`);
    renderStream(conv.messages || []);
  } catch {}
}

// ── Render messages stream ──────────────────────────────────────────
function renderStream(messages) {
  const stream = $('conv-stream');
  if (!stream) return;
  if (!messages.length) {
    stream.innerHTML = '<div class="conv-stream__empty">Pergunta algo a fabrica.</div>';
    return;
  }
  stream.innerHTML = messages.map(m => `
    <div class="msg-row ${m.role === 'user' ? 'user' : 'bot'}">
      <div class="msg-bubble">${(m.content || '').replace(/\n/g,'<br>')}</div>
    </div>`).join('');
  stream.scrollTop = stream.scrollHeight;
}

// ── Send message ────────────────────────────────────────────────────
async function sendMessage() {
  const inp = $('conv-input');
  const q = (inp?.value || '').trim();
  if (!q) return;
  if (inp) inp.value = '';

  const stream = $('conv-stream');
  // Append user message
  if (stream) {
    const empties = stream.querySelectorAll('.conv-stream__empty');
    empties.forEach(e => e.remove());
    const row = document.createElement('div');
    row.className = 'msg-row user';
    row.innerHTML = `<div class="msg-bubble">${q}</div>`;
    stream.appendChild(row);
    stream.scrollTop = stream.scrollHeight;
  }

  // Typing indicator
  let typingEl = null;
  if (stream) {
    typingEl = document.createElement('div');
    typingEl.className = 'msg-row bot';
    typingEl.innerHTML = `<div class="msg-bubble"><div class="chat-typing"><span></span><span></span><span></span></div></div>`;
    stream.appendChild(typingEl);
    stream.scrollTop = stream.scrollHeight;
  }

  try {
    const r = await fetchJSON('/api/assistant', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({question: q, conversation_id: activeConvId})
    });
    activeConvId = r.conversation_id;
    if (typingEl) typingEl.remove();

    if (stream) {
      const row = document.createElement('div');
      row.className = 'msg-row bot';
      row.innerHTML = `<div class="msg-bubble">${(r.answer||'').replace(/\n/g,'<br>')}</div>`;
      stream.appendChild(row);
      stream.scrollTop = stream.scrollHeight;
    }
    loadConvList();
  } catch (e) {
    if (typingEl) typingEl.remove();
    if (stream) {
      const row = document.createElement('div');
      row.className = 'msg-row bot';
      row.innerHTML = `<div class="msg-bubble">Erro ao contactar o assistente.</div>`;
      stream.appendChild(row);
    }
  }
}

// ── New conversation ────────────────────────────────────────────────
async function newConv() {
  try {
    const c = await fetchJSON('/api/conversations', {method:'POST'});
    activeConvId = c.id;
    const stream = $('conv-stream');
    if (stream) stream.innerHTML = '<div class="conv-stream__empty">Pergunta algo a fabrica.</div>';
    loadConvList();
  } catch {}
}

// ── Wire events ─────────────────────────────────────────────────────
const sendBtn = $('conv-send');
const inp     = $('conv-input');
const newBtn  = $('conv-new-btn');
if (sendBtn) sendBtn.addEventListener('click', sendMessage);
if (inp)     inp.addEventListener('keydown', e => { if (e.key === 'Enter') sendMessage(); });
if (newBtn)  newBtn.addEventListener('click', newConv);

// ── Handle dock question (from sessionStorage) ──────────────────────
const pendingQ = sessionStorage.getItem('dock_question');
if (pendingQ) {
  sessionStorage.removeItem('dock_question');
  // Create a new conv and send pending question
  fetchJSON('/api/conversations', {method:'POST'}).then(c => {
    activeConvId = c.id;
    loadConvList();
    const inp = $('conv-input');
    if (inp) inp.value = pendingQ;
    sendMessage();
  }).catch(() => {});
} else {
  // Load existing conversations, auto-select first
  (async () => {
    try {
      const convs = await fetchJSON('/api/conversations');
      if (convs.length) {
        await selectConv(convs[0].id);
      } else {
        loadConvList();
      }
    } catch {}
  })();
}
