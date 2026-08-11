import { isRefusal } from "../api.js";
import Sources from "./Sources.jsx";

function Pending() {
  return (
    <div className="loading">
      <span className="sweep" /> querying the datasheet…
    </div>
  );
}

function AssistantBody({ data, error }) {
  if (error) {
    return <p className="err">{error} Check that the server is running.</p>;
  }
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

export default function Message({ message }) {
  if (message.role === "user") {
    return (
      <div className="turn user">
        <div className="bubble">{message.text}</div>
      </div>
    );
  }

  return (
    <div className="turn assistant">
      <div className="who">Agent</div>
      {message.pending ? (
        <Pending />
      ) : (
        <AssistantBody data={message.data} error={message.error} />
      )}
    </div>
  );
}
