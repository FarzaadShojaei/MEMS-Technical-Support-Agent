# Frontend — LSM6DSOX Support Agent

A Vite + React single-page app for the RAG support agent. It talks to the
FastAPI backend's `POST /ask` endpoint and renders the answer with page-level
citations, latency, and a declined/answered outcome.

## Run locally

```bash
npm install
npm run dev            # http://localhost:5173
```

`npm run dev` proxies `/ask` and `/health` to `http://localhost:8000`
(see `vite.config.js`), so just have the FastAPI backend running there — no CORS
setup needed for local development.

## Build

```bash
npm run build          # outputs to dist/
npm run preview        # serve the production build locally
```

## Deploy to Vercel (frontend) + a hosted backend

This is the split-architecture version:

- **Backend** (FastAPI + retrieval + LLM) → a container host such as Hugging
  Face Spaces or Render (see the backend's `DEPLOY.md`). It can't run on Vercel.
- **Frontend** (this app) → Vercel.

Steps:

1. Deploy the backend first and note its URL, e.g.
   `https://your-user-your-space.hf.space`.
2. On the backend, set `CORS_ORIGINS` to your Vercel URL (e.g.
   `https://your-app.vercel.app`) so the browser is allowed to call it.
3. On Vercel: import the repo, set the project root to `frontend/`, and add an
   environment variable:

   ```
   VITE_API_URL = https://your-user-your-space.hf.space
   ```

4. Vercel auto-detects Vite. Build command `npm run build`, output `dist/`.

## Structure

```
src/
  main.jsx              entry
  App.jsx               layout + request state
  api.js                fetch wrapper + refusal detection
  styles.css            design tokens + styles
  components/
    AskBox.jsx          textarea + example chips
    AnswerCard.jsx      answer + latency/outcome meta
    Sources.jsx         expandable page-cited excerpts
```

## Note

If you prefer to keep a single deployment, the backend already serves an
equivalent vanilla-HTML UI at `/` — this React app is the alternative for a
separate, Vercel-hosted frontend.
