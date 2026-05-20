/* acao.js — Gemini chat + agent status + optimiser proposals */
'use strict';
const $ = id => document.getElementById(id);
const fetchJSON = async (url, opts) => { const r = await fetch(url, opts); if (!r.ok) throw new Error(r.status); return r.json(); };

let convId = null;

// ── Chat ──────────────────────────────────────────────────────────
function appendMsg(text, role) {
  const body = $('acao-chat-body');
  if (!body) return;
  const row = document.createElement('div');
  row.className = `msg-row ${role}`;
  row.innerHTML = `<div class="msg-bubble">${text}</div>`;
  body.appendChild(row);
  body.scrollTop = body.scrollHeight;
  return row;
}

function showTyping() {
  const body = $('acao-chat-body');
  if (!body) return null;
  const el = document.createElement('div');
  el.className = 'msg-row bot';
  el.id = 'typing-indicator';
  el.innerHTML = `<div class="msg-bubble"><div class="chat-typing"><span></span><span></span><span></span></div></div>`;
  body.appendChild(el);
  body.scrollTop = body.scrollHeight;
  return el;
}

function hideTyping() {
  const el = $('typing-indicator');
  if (el) el.remove();
}

async function send(question) {
  if (!question.trim()) return;
  // Hide chips on first send
  const chips = $('acao-chips');
  if (chips) chips.style.display = 'none';

  appendMsg(question, 'user');
  const inp = $('acao-input');
  if (inp) inp.value = '';

  showTyping();
  try {
    const r = await fetchJSON('/api/assistant', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({question, conversation_id: convId})
    });
    convId = r.conversation_id;
    hideTyping();

    const body = $('acao-chat-body');
    const row = document.createElement('div');
    row.className = 'msg-row bot';
    let html = `<div class="msg-bubble">${(r.answer || '').replace(/\n/g,'<br>')}</div>`;
    // Tool chips
    if (r.tool_calls && r.tool_calls.length) {
      html += `<div class="msg-tools">${r.tool_calls.map(tc => `<span class="msg-tool-chip">${tc.name}</span>`).join('')}</div>`;
    }
    // Action buttons
    if (r.actions && r.actions.length) {
      html += `<div class="msg-tools">${r.actions.map(a =>
        a.type === 'navigate'
          ? `<button class="msg-action-chip" onclick="window.location.href='/${a.target}'">${a.label || a.target}</button>`
          : ''
      ).join('')}</div>`;
    }
    row.innerHTML = html;
    body.appendChild(row);
    body.scrollTop = body.scrollHeight;
  } catch (e) {
    hideTyping();
    appendMsg('Erro ao contactar o assistente.', 'bot');
  }
}

const AcaoChat = {
  chip(q) { send(q); }
};

// ── Wire input ────────────────────────────────────────────────────
const sendBtn = $('acao-send');
const inp = $('acao-input');
if (sendBtn) sendBtn.addEventListener('click', () => send(inp?.value || ''));
if (inp)     inp.addEventListener('keydown', e => { if (e.key === 'Enter') send(inp.value); });

// ── Agents status ─────────────────────────────────────────────────
async function loadAgents() {
  try {
    const agents = await fetchJSON('/api/agents/status');
    agents.forEach(a => {
      const id = a.id || '';
      const key = id.toLowerCase().replace(/[^a-z]/g,'');
      const dot = $(`dot-${key}`);
      if (dot) {
        dot.className = `agent-dot ${a.active ? 'is-active' : 'is-idle'}`;
      }
    });
  } catch {}
}

// ── Proposals ─────────────────────────────────────────────────────
async function loadProposals() {
  try {
    const props = await fetchJSON('/api/agents/optimiser');
    const list = $('proposals-list');
    if (!list) return;
    if (!props.length) {
      list.innerHTML = '<div style="font-size:13px;color:var(--ink-hint);padding:8px 0;">Sem propostas no momento</div>';
      return;
    }
    list.innerHTML = props.map(p => `
      <div class="proposal-row">
        <div class="proposal-info">
          <div class="proposal-name">${p.operator_name || p.operator_id}</div>
          <div class="proposal-detail">${p.from_station} &rarr; ${p.to_station}</div>
        </div>
        <span class="proposal-gain">+${Math.round((p.gain_pct||0))}%</span>
        <button class="proposal-apply" onclick="applyProposal(this, '${p.operator_id}','${p.to_station}')">Aplicar</button>
      </div>`).join('');
  } catch {}
}

async function applyProposal(btn, opId, station) {
  if (!confirm(`Confirmas reatribuicao de ${opId} para ${station}?`)) return;
  btn.textContent = 'Aplicado';
  btn.disabled = true;
}

loadAgents();
loadProposals();
