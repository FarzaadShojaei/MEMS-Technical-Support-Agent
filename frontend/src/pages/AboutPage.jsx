const PIPELINE = [
  ["Ingest", "PyMuPDF parses the datasheet; text is chunked with overlap."],
  ["Embed", "Chunks are embedded locally (MiniLM) into a Chroma vector store."],
  [
    "Retrieve",
    "Hybrid: dense vectors + BM25 lexical, fused with Reciprocal Rank Fusion.",
  ],
  [
    "Answer",
    "An LLM writes a grounded answer with page citations — or declines when the docs don't cover it.",
  ],
];

const METRICS = [
  ["Retrieval hit@5", "0.52", "0.76"],
  ["Retrieval MRR", "0.37", "0.54"],
  ["Answer correctness", "0.38", "0.54"],
  ["Faithfulness", "0.88", "0.79"],
];

export default function AboutPage() {
  return (
    <div className="about">
      <h1>How it works</h1>
      <p className="lede">
        A retrieval-augmented support agent for the STMicroelectronics LSM6DSOX
        IMU, built to both <b>answer</b> from the datasheet and be{" "}
        <b>measured</b> — with a QA-grade evaluation harness behind it.
      </p>

      <section className="block">
        <h2>Pipeline</h2>
        <ol className="steps">
          {PIPELINE.map(([name, desc], i) => (
            <li key={name}>
              <span className="idx">{String(i + 1).padStart(2, "0")}</span>
              <div>
                <div className="step-name">{name}</div>
                <div className="step-desc">{desc}</div>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="block">
        <h2>Measured, not assumed</h2>
        <p className="prose">
          Answers are graded against a 24-question golden set spanning seven
          question types, using deterministic checks for exact values and an
          LLM judge only where paraphrase matters. Adding hybrid retrieval moved
          the numbers — and a regression gate protects them in CI.
        </p>
        <table className="metrics">
          <thead>
            <tr>
              <th>Metric</th>
              <th>Dense</th>
              <th>Hybrid</th>
            </tr>
          </thead>
          <tbody>
            {METRICS.map(([label, dense, hybrid]) => (
              <tr key={label}>
                <td>{label}</td>
                <td className="num">{dense}</td>
                <td className="num hi">{hybrid}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="foot">
          Faithfulness dips slightly because the improved agent attempts more
          answers instead of refusing — more surface area, still grounded.
        </p>
      </section>

      <section className="block">
        <h2>Stack</h2>
        <p className="prose stack">
          FastAPI · PyMuPDF · sentence-transformers · Chroma · rank-bm25 ·
          Ollama / Groq · React · pytest · GitHub Actions · Docker
        </p>
      </section>
    </div>
  );
}
