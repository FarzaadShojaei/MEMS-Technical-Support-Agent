import { useState } from "react";

export default function Composer({ onAsk, busy }) {
  const [q, setQ] = useState("");

  function submit() {
    if (busy) return;
    onAsk(q);
    setQ("");
  }

  function onKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <div className="composer">
      <div className="ask">
        <textarea
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={onKeyDown}
          rows={1}
          placeholder="Ask about registers, ranges, configuration…"
          aria-label="Your question"
        />
        <div className="ask-row">
          <span className="hint">Enter to send · Shift+Enter for newline</span>
          <button className="send" onClick={submit} disabled={busy}>
            {busy ? "…" : "Ask"}
          </button>
        </div>
      </div>
    </div>
  );
}
