// Backend base URL. Empty string = same origin (or the Vite dev proxy).
// For a Vercel deploy, set VITE_API_URL to your hosted FastAPI backend.
const API_URL = import.meta.env.VITE_API_URL ?? "";

export async function ask(question) {
  const res = await fetch(`${API_URL}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });

  if (!res.ok) {
    const detail =
      res.status === 503
        ? "The index is empty — the agent has no documentation loaded yet."
        : `The agent returned an error (${res.status}).`;
    throw new Error(detail);
  }
  return res.json();
}

const REFUSAL =
  /(does not|doesn't|not) (cover|contain|mention|specif|provide|include)|not (in|found)/i;

export function isRefusal(answer) {
  return REFUSAL.test(answer || "");
}
