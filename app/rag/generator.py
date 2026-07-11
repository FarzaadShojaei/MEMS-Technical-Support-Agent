"""Answer generation: retrieved chunks -> grounded, cited answer.

Key design choice (this is a *support* agent): the system prompt instructs
the model to answer ONLY from the provided context and to explicitly say
when the documentation doesn't contain the answer. Phase 2's eval measures
how well this actually holds.
"""

from openai import OpenAI

from app.config import settings

SYSTEM_PROMPT = """\
You are a technical support assistant for the STMicroelectronics LSM6DSOX \
MEMS sensor. Answer the user's question using ONLY the documentation \
excerpts provided in the context.

Rules:
- Ground every claim in the context. Do not use outside knowledge.
- Cite the excerpts you used by their [n] markers, e.g. "... (see [2])".
- Use exact register names, addresses, and values from the context.
- If the context does not contain the answer, say exactly that: state that \
the provided documentation does not cover it. Never guess or invent values.
- Be concise and technically precise.
"""


def _client() -> OpenAI:
    return OpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key)


def build_context(chunks: list[dict]) -> str:
    blocks = []
    for i, c in enumerate(chunks, start=1):
        blocks.append(f"[{i}] (source: {c['source']}, page {c['page']})\n{c['text']}")
    return "\n\n---\n\n".join(blocks)


def generate_answer(question: str, chunks: list[dict]) -> str:
    context = build_context(chunks)
    resp = _client().chat.completions.create(
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Context:\n\n{context}\n\nQuestion: {question}"},
        ],
    )
    return resp.choices[0].message.content or ""
