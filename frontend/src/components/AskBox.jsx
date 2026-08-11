import { useState } from "react";

const EXAMPLES = [
  "What is the WHO_AM_I value?",
  "Which accelerometer full-scale ranges are supported?",
  "How do I activate the gyroscope from power-down?",
  "Gyroscope sensitivity at ±2000 dps?",
];

export default function AskBox({ onAsk, busy }) {
  const [q, setQ] = useState("");

  function submit() {
    onAsk(q);
  }

  function onKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <>
      <div className="ask">
        <textarea
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={onKeyDown}
          rows={2}
          placeholder="Ask about registers, ranges, configuration…"
          aria-label="Your question"
        />
        <div className="ask-row">
          <span className="hint">Enter to send · Shift+Enter for newline</span>
          <button className="send" onClick={submit} disabled={busy}>
            Ask
          </button>
        </div>
      </div>

      <div className="chips">
        {EXAMPLES.map((ex) => (
          <button
            key={ex}
            className="chip"
            onClick={() => {
              setQ(ex);
              onAsk(ex);
            }}
          >
            {ex}
          </button>
        ))}
      </div>
    </>
  );
}
