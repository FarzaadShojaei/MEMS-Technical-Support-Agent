export default function Sources({ sources }) {
  return (
    <div className="sources">
      <h3>Retrieved from</h3>
      {sources.map((s, i) => (
        <details className="src" key={s.chunk_id ?? i}>
          <summary>
            <span className="file">{s.source}</span>
            <span className="pg">p.{s.page}</span>
            <span className="caret">›</span>
          </summary>
          <div className="excerpt">{(s.text || "").trim().slice(0, 600)}</div>
        </details>
      ))}
    </div>
  );
}
