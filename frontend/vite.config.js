import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev proxy: forward /ask and /health to the FastAPI backend so `npm run dev`
// works against a locally-running server with no CORS fuss.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/ask": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
});
