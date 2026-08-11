import { useState, useRef, useEffect } from "react";

import { ask } from "../api.js";
import Composer from "../components/Composer.jsx";
import Message from "../components/Message.jsx";

const EXAMPLES = [
  "What is the WHO_AM_I value?",
  "Which accelerometer full-scale ranges are supported?",
  "How do I activate the gyroscope from power-down?",
  "Gyroscope sensitivity at ±2000 dps?",
];

let idSeq = 0;
const nextId = () => ++idSeq;

export default function ChatPage() {
  const [messages, setMessages] = useState([]);
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef(null);

  // Scroll to the newest message whenever the conversation grows or updates.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  async function handleAsk(question) {
    const q = question.trim();
    if (q.length < 3 || busy) return;

    const pendingId = nextId();
    setMessages((m) => [
      ...m,
      { id: nextId(), role: "user", text: q },
      { id: pendingId, role: "assistant", pending: true },
    ]);
    setBusy(true);

    try {
      const data = await ask(q);
      setMessages((m) =>
        m.map((msg) =>
          msg.id === pendingId ? { ...msg, pending: false, data } : msg,
        ),
      );
    } catch (e) {
      setMessages((m) =>
        m.map((msg) =>
          msg.id === pendingId
            ? { ...msg, pending: false, error: e.message }
            : msg,
        ),
      );
    } finally {
      setBusy(false);
    }
  }

  const empty = messages.length === 0;

  return (
    <div className="chat">
      {empty ? (
        <div className="intro">
          <h1>Ask the datasheet.</h1>
          <p className="lede">
            A retrieval-augmented agent that answers from ST&apos;s LSM6DSOX
            documentation and <b>cites the page</b> — or tells you plainly when
            the answer isn&apos;t in the docs.
          </p>
          <div className="chips">
            {EXAMPLES.map((ex) => (
              <button
                key={ex}
                className="chip"
                onClick={() => handleAsk(ex)}
                disabled={busy}
              >
                {ex}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="thread">
          {messages.map((m) => (
            <Message key={m.id} message={m} />
          ))}
          <div ref={bottomRef} />
        </div>
      )}

      <Composer onAsk={handleAsk} busy={busy} />
    </div>
  );
}
