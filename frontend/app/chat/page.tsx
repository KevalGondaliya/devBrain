"use client";

import { useState } from "react";
import { useAuth } from "@/lib/auth";
import { sendChat, ApiError, type ChatMessage } from "@/lib/api";
import { RequireToken } from "@/components/RequireToken";

export default function ChatPage() {
  return (
    <div>
      <h1>Chat</h1>
      <p className="subtitle">
        Sends <code>POST /chat</code>. Routing is keyword-based against five
        flagship intents (see backend docs) — not a full agentic tool-use
        loop.
      </p>
      <RequireToken>
        <ChatBody />
      </RequireToken>
    </div>
  );
}

function ChatBody() {
  const { token } = useAuth();
  const [history, setHistory] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastMeta, setLastMeta] = useState<{
    intent: string;
    orchestrator: string | null;
  } | null>(null);

  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    const message = input.trim();
    if (!message || loading) return;
    setInput("");
    setError(null);
    const nextHistory: ChatMessage[] = [
      ...history,
      { role: "user", content: message },
    ];
    setHistory(nextHistory);
    setLoading(true);
    try {
      const res = await sendChat(token, message, history);
      setHistory([...nextHistory, { role: "assistant", content: res.reply }]);
      setLastMeta({ intent: res.intent, orchestrator: res.orchestrator });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to send message");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card">
      {error ? <div className="error-box">{error}</div> : null}
      <div className="chat-window">
        {history.length === 0 ? (
          <div className="muted">No messages yet — say hello.</div>
        ) : (
          history.map((m, i) => (
            <div key={i} className={`chat-msg ${m.role}`}>
              {m.content}
            </div>
          ))
        )}
        {loading ? <div className="chat-msg assistant muted">…</div> : null}
      </div>
      {lastMeta ? (
        <div className="chat-meta">
          intent: <code>{lastMeta.intent}</code>
          {lastMeta.orchestrator ? (
            <>
              {" "}
              · orchestrator: <code>{lastMeta.orchestrator}</code>
            </>
          ) : null}
        </div>
      ) : null}
      <form className="chat-input-row" style={{ marginTop: "0.75rem" }} onSubmit={handleSend}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about a project, daily briefing, cross-system investigation…"
        />
        <button className="btn" type="submit" disabled={loading}>
          Send
        </button>
      </form>
    </div>
  );
}
