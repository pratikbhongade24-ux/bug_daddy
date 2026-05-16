'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import { apiFetch, apiJson } from '@/lib/api';
import { getStoredUser } from '@/lib/storage';

type ChatMessage = {
  id?: number;
  role: 'user' | 'assistant';
  content: string;
  citations?: Array<{ file_path?: string; score?: number }>;
};

type WidgetState = {
  open: boolean;
  minimized: boolean;
  sessionId: string;
  conversationId: number | null;
  messages: ChatMessage[];
};

const WIDGET_STATE_KEY = 'bugDaddySupportWidgetState';

function createSessionId() {
  return `support-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function loadState(): WidgetState {
  if (typeof window === 'undefined') {
    return { open: false, minimized: false, sessionId: createSessionId(), conversationId: null, messages: [] };
  }

  try {
    const raw = localStorage.getItem(WIDGET_STATE_KEY);
    if (!raw) {
      return { open: false, minimized: false, sessionId: createSessionId(), conversationId: null, messages: [] };
    }
    const parsed = JSON.parse(raw) as Partial<WidgetState>;
    return {
      open: Boolean(parsed.open),
      minimized: Boolean(parsed.minimized),
      sessionId: parsed.sessionId || createSessionId(),
      conversationId: parsed.conversationId ?? null,
      messages: Array.isArray(parsed.messages) ? parsed.messages.slice(-40) : [],
    };
  } catch {
    return { open: false, minimized: false, sessionId: createSessionId(), conversationId: null, messages: [] };
  }
}

function normalizeAssistantText(content: string): string {
  return content
    .replace(/\r/g, '')
    .replace(/^(#{1,6})(\S)/gm, '$1 $2')
    .replace(/\n{3,}/g, '\n\n')
    .replace(/\u00a0/g, ' ');
}

export function SupportChatWidget() {
  const [mounted, setMounted] = useState(false);
  const [state, setState] = useState<WidgetState>(() => loadState());
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bodyRef = useRef<HTMLDivElement | null>(null);

  const canSend = useMemo(() => input.trim().length > 0 && !sending, [input, sending]);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted) return;
    localStorage.setItem(WIDGET_STATE_KEY, JSON.stringify(state));
  }, [state, mounted]);

  useEffect(() => {
    if (!bodyRef.current) return;
    bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [state.messages, state.open, state.minimized]);

  useEffect(() => {
    if (!mounted || state.messages.length > 0) return;

    const hydrate = async () => {
      setLoadingHistory(true);
      setError(null);
      try {
        const conversations = await apiJson<Array<{ id: number }>>(`/support/conversations?session_id=${encodeURIComponent(state.sessionId)}`);
        const conversation = conversations[0];
        if (!conversation) return;
        const messages = await apiJson<ChatMessage[]>(`/support/messages/${conversation.id}`);
        setState((prev) => ({
          ...prev,
          conversationId: conversation.id,
          messages: messages.map((m) => (m.role === 'assistant' ? { ...m, content: normalizeAssistantText(m.content) } : m)),
        }));
      } catch {
        // Keep widget usable even if history load fails.
      } finally {
        setLoadingHistory(false);
      }
    };

    hydrate();
  }, [mounted, state.messages.length, state.sessionId]);

  async function sendMessage() {
    const question = input.trim();
    if (!question || sending) return;

    setInput('');
    setError(null);
    setSending(true);

    const userMessage: ChatMessage = { role: 'user', content: question };
    const assistantMessage: ChatMessage = { role: 'assistant', content: '' };

    setState((prev) => ({
      ...prev,
      open: true,
      minimized: false,
      messages: [...prev.messages, userMessage, assistantMessage],
    }));

    try {
      const user = getStoredUser();
      const payload = {
        conversation_id: state.conversationId,
        session_id: state.sessionId,
        question,
        filters: user?.role === 'admin' ? {} : { environment: 'dev' },
      };

      const response = await apiFetch('/support/chat/stream', {
        method: 'POST',
        body: JSON.stringify(payload),
      });

      if (!response.ok || !response.body) {
        throw new Error('Support request failed');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split('\n\n');
        buffer = events.pop() || '';

        for (const eventBlock of events) {
          const lines = eventBlock.split('\n');
          const event = lines.find((line) => line.startsWith('event:'))?.replace('event:', '').trim();
          const dataLine = lines.find((line) => line.startsWith('data:'))?.replace('data:', '').trim();
          if (!event || !dataLine) continue;
          const data = JSON.parse(dataLine) as Record<string, unknown>;

          if (event === 'meta' && typeof data.conversation_id === 'number') {
            setState((prev) => ({ ...prev, conversationId: data.conversation_id as number }));
          }

          if (event === 'token' && typeof data.text === 'string') {
            setState((prev) => {
              if (prev.messages.length === 0) return prev;
              const next = [...prev.messages];
              const last = next[next.length - 1];
              if (last.role !== 'assistant') return prev;
              next[next.length - 1] = { ...last, content: normalizeAssistantText(`${last.content}${String(data.text)}`) };
              return { ...prev, messages: next };
            });
          }
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to get support response');
      setState((prev) => {
        const next = [...prev.messages];
        const last = next[next.length - 1];
        if (last?.role === 'assistant' && !last.content) {
          next[next.length - 1] = { role: 'assistant', content: 'I could not reach support right now. Please try again.' };
        }
        return { ...prev, messages: next };
      });
    } finally {
      setSending(false);
    }
  }

  function resetConversation() {
    setState({ open: true, minimized: false, sessionId: createSessionId(), conversationId: null, messages: [] });
    setError(null);
  }

  if (!mounted) return null;

  return (
    <>
      <button
        className="support-fab"
        type="button"
        onClick={() => setState((prev) => ({ ...prev, open: !prev.open, minimized: false }))}
        aria-label="Open support assistant"
      >
        <span className="support-fab-dot" />
        Support
      </button>

      <section className={`support-widget ${state.open ? 'open' : ''} ${state.minimized ? 'min' : ''}`} aria-live="polite">
        <header className="support-widget-head">
          <div className="support-widget-brand">
            <span className="support-widget-badge">GX</span>
            <div>
              <h3>Grab Support Assistant</h3>
              <p>Fast SME guidance for incidents, APIs, and workflows</p>
            </div>
          </div>
          <div className="support-widget-actions">
            <button type="button" onClick={() => setState((prev) => ({ ...prev, minimized: !prev.minimized }))} aria-label="Minimize">
              {state.minimized ? 'Expand' : 'Min'}
            </button>
            <button type="button" onClick={() => setState((prev) => ({ ...prev, open: false }))} aria-label="Close">
              Close
            </button>
          </div>
        </header>

        {!state.minimized ? (
          <>
            <div className="support-widget-body" ref={bodyRef}>
              {loadingHistory ? <div className="support-info">Loading previous conversation...</div> : null}
              {state.messages.length === 0 && !loadingHistory ? (
                <div className="support-info">Ask about KYC, disbursement, API contracts, SQL flows, or architecture decisions.</div>
              ) : null}
              {state.messages.map((msg, idx) => (
                <article key={`${msg.role}-${idx}-${msg.content.length}`} className={`support-msg-wrap ${msg.role === 'user' ? 'user' : 'bot'}`}>
                  <span className="support-msg-role">{msg.role === 'user' ? 'You' : 'Assistant'}</span>
                  <div className={`support-msg ${msg.role === 'user' ? 'user' : 'bot'}`}>
                    {msg.role === 'assistant' ? (
                      <div className="support-md">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {msg.content || (sending ? 'Thinking...' : '')}
                        </ReactMarkdown>
                      </div>
                    ) : (
                      <p>{msg.content}</p>
                    )}
                  </div>
                </article>
              ))}
            </div>

            {error ? <div className="support-error">{error}</div> : null}

            <footer className="support-widget-input">
              <input
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') void sendMessage();
                }}
                placeholder="Ask support..."
                maxLength={6000}
              />
              <button type="button" disabled={!canSend} onClick={() => void sendMessage()}>
                {sending ? '...' : 'Send'}
              </button>
              <button type="button" className="ghost" onClick={resetConversation}>
                New
              </button>
            </footer>
          </>
        ) : null}
      </section>
    </>
  );
}
