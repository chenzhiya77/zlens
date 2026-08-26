import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev: Vite serves the SPA and proxies /api to the FastAPI backend (no CORS).
// Prod: the build lands in src/zlens/web/static_dist, hosted by FastAPI itself
// (single-process delivery, see AGENTS.md architecture rules).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
  build: {
    outDir: "../src/zlens/web/static_dist",
    emptyOutDir: true,
  },
});
