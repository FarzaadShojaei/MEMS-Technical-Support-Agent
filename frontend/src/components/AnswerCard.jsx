import { isRefusal } from "../api.js";
import Sources from "./Sources.jsx";

export default function AnswerCard({ data }) {
  const refused = isRefusal(data.answer);
  const sources = data.sources || [];

  return (
    <>
      <div className="card">
        <div className="card-body">
          <p className={refused ? "refusal" : ""}>{data.answer}</p>
        </div>
        <div className="meta">
          <span>
            latency <b>{data.latency_ms} ms</b>
          </span>
          <span>
            sources <b>{sources.length}</b>
          </span>
          <span>
            outcome <b>{refused ? "declined" : "answered"}</b>
          </span>
        </div>
      </div>

      {sources.length > 0 && <Sources sources={sources} />}
    </>
  );
}
