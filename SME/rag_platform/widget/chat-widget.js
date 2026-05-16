(function () {
  function createWidget(config) {
    const apiBase = config.apiBase;
    const apiKey = config.apiKey;
    const externalUserId = config.externalUserId;
    const sessionId = config.sessionId || `sess-${Date.now()}`;

    const style = document.createElement('style');
    style.textContent = `
      .sme-chat-fab{position:fixed;right:24px;bottom:24px;background:#155dfc;color:#fff;border:none;border-radius:999px;padding:14px 16px;cursor:pointer;z-index:99999;box-shadow:0 10px 30px rgba(0,0,0,.2)}
      .sme-chat-box{position:fixed;right:24px;bottom:84px;width:360px;max-height:72vh;background:#0b1220;color:#f8fafc;border:1px solid #22314d;border-radius:16px;display:none;flex-direction:column;overflow:hidden;z-index:99999}
      .sme-chat-head{padding:12px 14px;background:#111a2e;font-weight:700}
      .sme-chat-body{padding:12px;height:420px;overflow:auto;background:#0b1220}
      .sme-msg{margin-bottom:10px;padding:10px;border-radius:10px;font-size:13px;white-space:pre-wrap}
      .sme-user{background:#1d4ed8}
      .sme-bot{background:#18243a}
      .sme-chat-input{display:flex;gap:8px;padding:10px;background:#111a2e}
      .sme-chat-input input{flex:1;border-radius:10px;border:1px solid #2f4368;background:#0b1220;color:#fff;padding:10px}
      .sme-chat-input button{border:none;border-radius:10px;background:#16a34a;color:#fff;padding:10px 12px;cursor:pointer}
    `;
    document.head.appendChild(style);

    const fab = document.createElement('button');
    fab.className = 'sme-chat-fab';
    fab.textContent = 'Support';

    const box = document.createElement('div');
    box.className = 'sme-chat-box';
    box.innerHTML = `
      <div class="sme-chat-head">SME Assistant</div>
      <div class="sme-chat-body" id="smeChatBody"></div>
      <div class="sme-chat-input">
        <input id="smeChatInput" placeholder="Ask about APIs, workflows, SQL, architecture..." />
        <button id="smeChatSend">Send</button>
      </div>
    `;

    document.body.appendChild(fab);
    document.body.appendChild(box);

    let conversationId = null;
    const body = box.querySelector('#smeChatBody');
    const input = box.querySelector('#smeChatInput');
    const send = box.querySelector('#smeChatSend');

    function appendMessage(role, text) {
      const el = document.createElement('div');
      el.className = `sme-msg ${role === 'user' ? 'sme-user' : 'sme-bot'}`;
      el.textContent = text;
      body.appendChild(el);
      body.scrollTop = body.scrollHeight;
      return el;
    }

    async function ask() {
      const q = input.value.trim();
      if (!q) return;
      input.value = '';
      appendMessage('user', q);
      const botNode = appendMessage('bot', '');

      const res = await fetch(`${apiBase}/chat/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-api-key': apiKey,
        },
        body: JSON.stringify({
          question: q,
          conversation_id: conversationId,
          external_user_id: externalUserId,
          session_id: sessionId,
        }),
      });

      if (!res.ok || !res.body) {
        botNode.textContent = 'Request failed';
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split('\n\n');
        buffer = events.pop() || '';

        for (const e of events) {
          const lines = e.split('\n');
          const event = lines.find((l) => l.startsWith('event:'))?.replace('event:', '').trim();
          const dataLine = lines.find((l) => l.startsWith('data:'))?.replace('data:', '').trim();
          if (!event || !dataLine) continue;
          const data = JSON.parse(dataLine);
          if (event === 'meta') conversationId = data.conversation_id;
          if (event === 'token') botNode.textContent += data.text;
        }
      }
    }

    fab.onclick = () => {
      box.style.display = box.style.display === 'flex' ? 'none' : 'flex';
      box.style.flexDirection = 'column';
    };
    send.onclick = ask;
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') ask(); });
  }

  window.SMEChatWidget = { createWidget };
})();
